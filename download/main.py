import os
import re
import sys
import time
import logging
import requests
import pyotp
import zipfile
import rarfile
from pathlib import Path
from dotenv import load_dotenv
from rapidfuzz import process, fuzz
from playwright.sync_api import sync_playwright

pasta_atual = str(Path(__file__).parent)
if pasta_atual not in sys.path:
    sys.path.append(pasta_atual)

from db.db_dominio import DatabaseConnection
from db.db_resiliencia import ResilienciaDB
    
# --- CONFIGURAÇÃO DE LOGS ---
logging.basicConfig(
    level=logging.INFO, 
    format="%(asctime)s [%(levelname)s] %(message)s", 
    datefmt="%H:%M:%S"
)

# --- CONFIGURAÇÃO DO UNRAR (LINUX/WINDOWS) ---
if os.name == 'nt':  # Windows
    rarfile.tool_path = r'C:\Program Files\WinRAR\UnRAR.exe'
else:  # Linux
    rarfile.tool_path = 'unrar'

# ==========================================
# RAIZ DO PROJETO E VARIÁVEIS
# ==========================================
RAIZ_PROJETO = Path(__file__).parent.parent
caminho_env = RAIZ_PROJETO / ".env"
load_dotenv(dotenv_path=caminho_env)

# --- CONFIGURAÇÕES GERAIS ---
EMAIL = os.getenv("ONVIO_USER")
SENHA = os.getenv("ONVIO_PASS")
SECRET_2FA = os.getenv("ONVIO_TOKEN")

# TRAVA DE PRODUÇÃO: Nenhuma OS menor que essa será baixada
# Se não estiver no .env, assume 0 (baixa tudo)
OS_INICIAL = int(os.getenv("OS_INICIAL", "0"))

caminho_arquivos_env = os.getenv("CAMINHO_ARQUIVOS")
if caminho_arquivos_env:
    PASTA_RAIZ = Path(caminho_arquivos_env)
else:
    PASTA_RAIZ = RAIZ_PROJETO / "arquivos"

PASTA_RAIZ.mkdir(parents=True, exist_ok=True)
URL_BASE_API = "https://onvio.com.br/api/service-requesting/v1"


# ==========================================
# 1. AUXILIARES DE EXTRAÇÃO E BUSCA
# ==========================================
def tratar_compactados(caminho_arquivo, pasta_destino):
    teve_erro = False
    msg_erro = ""
    compactados_pendentes = [caminho_arquivo]
    
    while compactados_pendentes:
        arq_atual = compactados_pendentes.pop(0)
        ext = arq_atual.suffix.lower()
        
        try:
            if ext == ".zip":
                with zipfile.ZipFile(arq_atual, 'r') as z:
                    if z.testzip() is not None:
                        raise Exception("Arquivo ZIP corrompido.")
                    z.extractall(pasta_destino)
            
            elif ext == ".rar":
                with rarfile.RarFile(arq_atual, 'r') as r:
                    if r.needs_password():
                        raise Exception("Arquivo RAR protegido por senha.")
                    r.extractall(pasta_destino)
            
            if arq_atual.exists():
                arq_atual.unlink()
            
            for f in pasta_destino.rglob('*'):
                if f.is_file() and f.suffix.lower() in ['.zip', '.rar']:
                    if f not in compactados_pendentes:
                        compactados_pendentes.append(f)

        except Exception as e:
            erro_msg = str(e)
            logging.warning(f"Erro em {arq_atual.name}: {erro_msg}")
            aviso = pasta_destino / f"!!!_ERRO_NA_EXTRACAO_{arq_atual.name}_!!!.txt"
            with open(aviso, "w", encoding="utf-8") as f:
                f.write(f"Arquivo: {arq_atual.name}\nErro: {erro_msg}\nVerifique manualmente.")
            teve_erro = True
            msg_erro = erro_msg

    return not teve_erro, msg_erro


def descobrir_codigo_empresa(nome_onvio, mapa_empresas):
    if not nome_onvio: return "0"
    
    def limpar(texto):
        t = texto.strip().upper()
        termos = [" LTDA", " S.A.", " S/A", " ME", " EPP", " S.S.", " S/S", " INDUSTRIAIS", " INDUSTRIAL", " COMERCIO", " SERVICOS"]
        for termo in termos:
            t = t.replace(termo, "")
        return re.sub(r'[^A-Z0-9 ]', '', t).strip()

    nome_onvio_limpo = limpar(nome_onvio)
    for nome_db, codigo in mapa_empresas.items():
        nome_db_limpo = limpar(nome_db)
        if nome_db_limpo in nome_onvio_limpo or nome_onvio_limpo in nome_db_limpo:
            return codigo

    nomes_dominio = list(mapa_empresas.keys())
    match = process.extractOne(nome_onvio_limpo, nomes_dominio, scorer=fuzz.token_set_ratio)
    
    if match and match[1] >= 80:
        return mapa_empresas[match[0]]
    
    logging.warning(f"❌ Sem match seguro para: {nome_onvio}")
    return "0"


# ==========================================
# 2. COMUNICAÇÃO COM API ONVIO
# ==========================================
def capturar_sessao_onvio() -> dict:
    logging.info("Iniciando captura de sessão via Playwright (Modo Oculto)...")
    with sync_playwright() as p:
        #  headless=True para rodar em background sem abrir a janela, para ver o login trocar para False
        browser = p.chromium.launch(headless=True, args=["--start-maximized"])
        context = browser.new_context(viewport={"width": 1280, "height": 720})
        page = context.new_page()

        sessao = {"token": None, "url_completa": None, "headers": {}}

        def interceptar(request):
            if "/api/" in request.url and "tickets" in request.url and request.method == "GET":
                auth = request.headers.get("authorization") or request.headers.get("Authorization")
                if auth and "UDSLongToken" in auth and not sessao["token"]:
                    sessao["token"] = auth
                    sessao["url_completa"] = request.url
                    sessao["headers"] = request.headers
                    logging.info("Token e rota interceptados!")

        page.on("request", interceptar)
        
        logging.info("Acessando onvio.com.br/login...")
        page.goto("https://onvio.com.br/login/#/", wait_until="networkidle")
        
        try:
            btn_entrar = page.locator("#trauth-continue-signin-btn")
            btn_entrar.wait_for(state="visible", timeout=15000)
            btn_entrar.click(force=True)
            page.wait_for_url("**/auth.thomsonreuters.com/**", timeout=20000)
            time.sleep(2)
        except Exception as e:
            logging.error(f"Falha ao passar da primeira tela: {e}")
            browser.close()
            raise e

        try:
            page.wait_for_selector("input[name='username']", timeout=15000)
            page.fill("input[name='username']", EMAIL)
            try: page.click("button[type='submit']", timeout=3000)
            except: page.click("#trauth-continue-signin-btn", timeout=3000)
            time.sleep(3)
        except Exception as e:
            raise e

        try:
            page.wait_for_selector("#password", timeout=15000)
            page.fill("#password", SENHA)
            page.click("button._button-login-password", force=True)
            time.sleep(4)
        except Exception as e:
            raise e

        try:
            seletor_aria = "button[aria-label='Autenticador Google ou similar']"
            seletor_value = "button[value='otp::0']"

            if page.locator(seletor_aria).is_visible(timeout=5000):
                page.click(seletor_aria, force=True)
                time.sleep(2)
            elif page.locator(seletor_value).is_visible(timeout=2000):
                page.click(seletor_value, force=True)
                time.sleep(2)
            elif page.locator("text=Autenticador Google").is_visible(timeout=2000):
                page.click("text=Autenticador Google", force=True)
                time.sleep(2)

            if (page.locator("text=código").count() > 0 or 
                page.locator("input[type='tel']").count() > 0 or 
                page.locator("text=verificação").count() > 0):
                
                if SECRET_2FA:
                    totp = pyotp.TOTP(SECRET_2FA)
                    codigo = totp.now()

                    campo_code = page.locator("input[type='tel'], input[name='code'], input.input-code").first
                    if campo_code.is_visible(timeout=5000):
                        campo_code.fill(codigo)
                        try: page.click("button[type='submit']", timeout=2000)
                        except: pass
                        try: page.click("button:has-text('Verificar')", timeout=2000)
                        except: pass
                        time.sleep(5)
        except Exception as e:
            time.sleep(5)

        logging.info("Navegando para o Portal do Cliente para interceptar a API...")
        page.goto("https://onvio.com.br/br-portal-do-cliente/service-requesting/general", wait_until="networkidle")
        
        timeout_intercept = time.time() + 20
        while not sessao["token"] and time.time() < timeout_intercept:
            time.sleep(1)

        browser.close()
        
        if not sessao["token"]:
            raise Exception("Falha ao capturar o Token UDSLongToken.")
            
        return sessao
    

def buscar_anexos(http, ticket_id):
    rota_anexos = f"{URL_BASE_API}/tickets/{ticket_id}/attachments?limit=500"
    res = http.get(rota_anexos)
    
    if res.status_code == 200:
        dados = res.json()
        if isinstance(dados, list): return dados
        elif isinstance(dados, dict): return dados.get("items", dados.get("attachments", []))

    for rota in [f"{URL_BASE_API}/tickets/generic/{ticket_id}", f"{URL_BASE_API}/tickets/{ticket_id}"]:
        res = http.get(rota)
        if res.status_code == 200:
            anexos = res.json().get("attachmentsExpanded", [])
            if anexos: return anexos
                
    return []


# ==========================================
# 3. PROCESSAMENTO DE DOWNLOAD
# ==========================================
def baixar_ticket(http, db_res, ticket_obj, mapa_empresas):
    uuid = ticket_obj.get("id")
    num_ticket = ticket_obj.get("identifier")
    
    if not num_ticket:
        res = http.get(f"{URL_BASE_API}/tickets/{uuid}")
        if res.status_code == 200:
            ticket_obj = res.json()
            num_ticket = ticket_obj.get("identifier")
        else:
            return False

    num_ticket = int(num_ticket)

    # TRAVA DE PRODUÇÃO: Se a OS for menor que o limite configurado, pula na hora
    if num_ticket < OS_INICIAL:
        logging.info(f"OS [{num_ticket}] ignorada (Anterior à OS de Corte configurada: {OS_INICIAL})")
        return True # Retorna True para não prender no retry
    
    status_atual, tentativas = db_res.get_ticket_status(num_ticket)
    if status_atual == "SUCESSO":
        return True

    client_info = ticket_obj.get("clientExpanded", {})
    nome_cliente = str(client_info.get("name", "DESCONHECIDO")).strip().upper()
    cod_onvio = client_info.get("code")
    
    if cod_onvio and str(cod_onvio).strip():
        cod_emp = str(cod_onvio).strip()
    else:
        cod_emp = descobrir_codigo_empresa(nome_cliente, mapa_empresas)
    
    data_iso = ticket_obj.get("created", "")
    if data_iso:
        data_pura = data_iso.split("T")[0]
        ano, mes, _ = data_pura.split("-")
        pasta_periodo = f"{mes}.{ano}"
    else:
        pasta_periodo = "Sem_Data"

    nome_pasta_cliente = re.sub(r'[\\/*?:"<>|]', "-", nome_cliente)
    anexos = buscar_anexos(http, uuid)
    
    if not anexos:
        logging.info(f"Ticket [{num_ticket}]: Sem anexos. Marcado como concluído.")
        db_res.registrar_ou_atualizar(id_ticket=num_ticket, cod_emp=cod_emp, nome_emp=nome_cliente, status="SUCESSO", caminho_pasta="", qtd_anexos=0, erro="")
        return True
    
    anexos_para_baixar = anexos
    
    pasta_ticket = PASTA_RAIZ / f"{cod_emp} - {nome_pasta_cliente}" / pasta_periodo / str(num_ticket)
    pasta_ticket.mkdir(parents=True, exist_ok=True)

    status_final = "SUCESSO"
    erro_detalhe = ""

    for att in anexos_para_baixar:
        att_id = att.get("id")
        nome_arquivo = att.get("name", f"arquivo_{att_id}")
        
        res_link = http.get(f"{URL_BASE_API}/tickets/{uuid}/attachments/{att_id}")
        if res_link.status_code == 200:
            download_url = res_link.json().get("downloadUrl")
            caminho_arq = pasta_ticket / nome_arquivo
            
            with http.get(download_url, stream=True) as r_file:
                with open(caminho_arq, "wb") as f:
                    for chunk in r_file.iter_content(8192): f.write(chunk)
            
            if nome_arquivo.lower().endswith(('.zip', '.rar')):
                ok, msg = tratar_compactados(caminho_arq, pasta_ticket)
                if not ok:
                    status_final = "ALERTA_HUMANO"
                    erro_detalhe = msg
            
            logging.info(f"Ticket [{num_ticket}]: Arquivo {nome_arquivo} baixado.")
        else:
            status_final = "ERRO_API"
            erro_detalhe = "Falha ao gerar link de download"

    db_res.registrar_ou_atualizar(id_ticket=num_ticket, cod_emp=cod_emp, nome_emp=nome_cliente, status=status_final, caminho_pasta=str(pasta_ticket), qtd_anexos=len(anexos_para_baixar), erro=erro_detalhe)
    return status_final == "SUCESSO"


# ==========================================
# 4. ORQUESTRAÇÃO
# ==========================================
def executar_download():
    db_dom = DatabaseConnection()
    if not db_dom.connect(): return
    mapa_empresas = db_dom.get_mapeamento_empresas()
    db_dom.close()

    db_res = ResilienciaDB()

    sessao = capturar_sessao_onvio()
    if not sessao["token"]:
        logging.error("Falha ao capturar sessão.")
        return

    http = requests.Session()
    http.headers.update(sessao["headers"])
    http.headers["Authorization"] = sessao["token"]

    # 4. Processar lista atual da API
    logging.info("Processando lista atual de solicitações...")
    res = http.get(sessao["url_completa"])
    if res.status_code == 200:
        tickets = res.json().get("items", [])
        for t in tickets:
            baixar_ticket(http, db_res, t, mapa_empresas)

    # 5. Caçar GAPS (Com trava inteligente de produção)
    logging.info("Verificando se existem solicitações puladas (GAPs)...")
    gaps = db_res.detectar_gaps(limite_retroativo=100)
    for g_num in gaps:
        if g_num < OS_INICIAL: 
            continue # Não caça gaps anteriores à data de corte

        logging.info(f"Tentando recuperar GAP: {g_num}")
        res_gap = http.get(f"{URL_BASE_API}/tickets?identifier={g_num}")
        if res_gap.status_code == 200:
            items = res_gap.json().get("items", [])
            if items:
                baixar_ticket(http, db_res, items[0], mapa_empresas)

    # 6. Retentar erros e pendentes
    logging.info("Retentando tickets com erro ou pendentes...")
    retries = db_res.get_pendentes_para_retry()
    for r_num in retries:
        if r_num < OS_INICIAL: 
            continue # Não retenta arquivos antigos

        res_retry = http.get(f"{URL_BASE_API}/tickets?identifier={r_num}")
        if res_retry.status_code == 200:
            items = res_retry.json().get("items", [])
            if items:
                baixar_ticket(http, db_res, items[0], mapa_empresas)

    logging.info("PROCESSO FINALIZADO!")


if __name__ == "__main__":
    executar_download()
