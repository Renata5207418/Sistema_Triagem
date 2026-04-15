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
# RAIZ DO PROJETO
# ==========================================
RAIZ_PROJETO = Path(__file__).parent.parent
caminho_env = RAIZ_PROJETO / ".env"
load_dotenv(dotenv_path=caminho_env)

# --- CONFIGURAÇÕES GERAIS ---
EMAIL = os.getenv("ONVIO_USER")
SENHA = os.getenv("ONVIO_PASS")
SECRET_2FA = os.getenv("ONVIO_TOKEN")

# Pega o caminho do .env. Se estiver vazio, cria a pasta 'arquivos' na RAIZ do projeto
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
    """Tenta extrair ZIP/RAR. Se falhar ou tiver senha, gera alerta txt."""
    ext = caminho_arquivo.suffix.lower()
    try:
        if ext == ".zip":
            with zipfile.ZipFile(caminho_arquivo, 'r') as z:
                if z.testzip() is not None:
                    raise Exception("Arquivo ZIP corrompido.")
                z.extractall(pasta_destino)
        
        elif ext == ".rar":
            with rarfile.RarFile(caminho_arquivo, 'r') as r:
                if r.needs_password():
                    raise Exception("Arquivo RAR protegido por senha.")
                r.extractall(pasta_destino)
        
        # Se chegou aqui sem erro, apaga o compactado
        caminho_arquivo.unlink()
        return True, ""
    except Exception as e:
        erro_msg = str(e)
        logging.warning(f"Erro em {caminho_arquivo.name}: {erro_msg}")
        aviso = pasta_destino / "!!!_ERRO_NA_EXTRACAO_!!!.txt"
        with open(aviso, "w", encoding="utf-8") as f:
            f.write(f"Arquivo: {caminho_arquivo.name}\nErro: {erro_msg}\nVerifique manualmente.")
        return False, erro_msg


def descobrir_codigo_empresa(nome_onvio, mapa_empresas):
    """Busca ultra-resiliente para lidar com nomes truncados na Domínio."""
    if not nome_onvio: return "0"
    
    # 1. Limpeza
    def limpar(texto):
        t = texto.strip().upper()
        # Remove siglas e pontos comuns
        termos = [" LTDA", " S.A.", " S/A", " ME", " EPP", " S.S.", " S/S", " INDUSTRIAIS", " INDUSTRIAL", " COMERCIO", " SERVICOS"]
        for termo in termos:
            t = t.replace(termo, "")
        return re.sub(r'[^A-Z0-9 ]', '', t).strip()

    nome_onvio_limpo = limpar(nome_onvio)
    for nome_db, codigo in mapa_empresas.items():
        nome_db_limpo = limpar(nome_db)
        if nome_db_limpo in nome_onvio_limpo or nome_onvio_limpo in nome_db_limpo:
            logging.info(f"Match por contenção: '{nome_onvio}' -> Código: {codigo}")
            return codigo

    # 3. Tentativa 2: Fuzzy (Fumaça) com nota de corte adaptativa
    nomes_dominio = list(mapa_empresas.keys())
    # O token_set_ratio é ótimo para nomes truncados
    match = process.extractOne(nome_onvio_limpo, nomes_dominio, scorer=fuzz.token_set_ratio)
    
    # Se a similaridade for alta (80%+), aceitamos
    if match and match[1] >= 80:
        cod_empresa = mapa_empresas[match[0]]
        logging.info(f"Match Fuzzy ({int(match[1])}%): '{nome_onvio}' -> '{match[0]}' (Código: {cod_empresa})")
        return cod_empresa
    
    logging.warning(f"❌ Sem match seguro para: {nome_onvio}")
    return "0"


# ==========================================
# 2. COMUNICAÇÃO COM API ONVIO
# ==========================================
def capturar_sessao_onvio() -> dict:
    logging.info("Iniciando captura de sessão via Playwright...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=["--start-maximized"])
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
        
        # 1. ACESSO INICIAL
        logging.info("Acessando onvio.com.br/login...")
        page.goto("https://onvio.com.br/login/#/", wait_until="networkidle")
        
        # 2. O CLIQUE NO "ENTRAR"
        logging.info("Aguardando botão 'Entrar'...")
        try:
            btn_entrar = page.locator("#trauth-continue-signin-btn")
            btn_entrar.wait_for(state="visible", timeout=15000)
            btn_entrar.click(force=True)
            logging.info("Clicou em 'Entrar'. Aguardando redirecionamento para Thomson Reuters...")
            page.wait_for_url("**/auth.thomsonreuters.com/**", timeout=20000)
            time.sleep(2)
        except Exception as e:
            logging.error(f"Falha ao passar da primeira tela: {e}")
            browser.close()
            raise e

        # 3. PREENCHIMENTO DO E-MAIL
        try:
            logging.info(f"Preenchendo e-mail: {EMAIL}")
            page.wait_for_selector("input[name='username']", timeout=15000)
            page.fill("input[name='username']", EMAIL)
            
            # Clica no botão de prosseguir igual ao script funcional
            try:
                page.click("button[type='submit']", timeout=3000)
            except:
                page.click("#trauth-continue-signin-btn", timeout=3000)
            time.sleep(3)
        except Exception as e:
            logging.error("Não foi possível encontrar o campo de e-mail.")
            raise e

        # 4. PREENCHIMENTO DA SENHA
        try:
            logging.info("Aguardando campo de senha...")
            page.wait_for_selector("#password", timeout=15000)
            page.fill("#password", SENHA)
            
            # IGUAL AO SCRIPT FUNCIONAL: clica no botão específico em vez de dar Enter
            page.click("button._button-login-password", force=True)
            logging.info("Senha preenchida e confirmada.")
            time.sleep(4)
        except Exception as e:
            logging.error("Não foi possível encontrar o campo de senha.")
            raise e

        # 5. TRATAMENTO DO 2FA (A blindagem da sua outra aplicação)
        try:
            logging.info("Verificando se há seleção de método 2FA...")
            
            seletor_aria = "button[aria-label='Autenticador Google ou similar']"
            seletor_value = "button[value='otp::0']"

            if page.locator(seletor_aria).is_visible(timeout=5000):
                logging.info("Botão 'Autenticador Google' detectado (via aria-label). Clicando...")
                page.click(seletor_aria, force=True)
                time.sleep(2)
            elif page.locator(seletor_value).is_visible(timeout=2000):
                logging.info("Botão 'Autenticador Google' detectado (via value). Clicando...")
                page.click(seletor_value, force=True)
                time.sleep(2)
            elif page.locator("text=Autenticador Google").is_visible(timeout=2000):
                logging.info("Clicando no texto 'Autenticador Google' (fallback)...")
                page.click("text=Autenticador Google", force=True)
                time.sleep(2)

            # Tela do Código 2FA
            if (page.locator("text=código").count() > 0 or 
                page.locator("input[type='tel']").count() > 0 or 
                page.locator("text=verificação").count() > 0):
                
                logging.info("Tela de digitação do código detectada.")

                if SECRET_2FA:
                    totp = pyotp.TOTP(SECRET_2FA)
                    codigo = totp.now()
                    logging.info(f"Gerando token 2FA: {codigo}")

                    campo_code = page.locator("input[type='tel'], input[name='code'], input.input-code").first
                    if campo_code.is_visible(timeout=5000):
                        campo_code.fill(codigo)
                        
                        # Tenta clicar no submit ou verificar
                        try:
                            page.click("button[type='submit']", timeout=2000)
                        except:
                            pass
                        try:
                            page.click("button:has-text('Verificar')", timeout=2000)
                        except:
                            pass
                            
                        time.sleep(5)
                else:
                    logging.warning("2FA solicitado! Digite manualmente no navegador...")
                    time.sleep(30)
        except Exception as e:
            logging.info("Nenhum 2FA detectado ou tela já passou. Avançando...")
            time.sleep(5)

        # 6. CAPTURA DOS DADOS (API)
        logging.info("Navegando para o Portal do Cliente para interceptar a API...")
        page.goto("https://onvio.com.br/br-portal-do-cliente/service-requesting/general", wait_until="networkidle")
        
        # Aguarda o interceptor pegar o token
        timeout_intercept = time.time() + 20
        while not sessao["token"] and time.time() < timeout_intercept:
            time.sleep(1)

        browser.close()
        
        if not sessao["token"]:
            raise Exception("Falha ao capturar o Token UDSLongToken. Verifique se a página carregou as solicitações.")
            
        return sessao
    
    

def buscar_anexos(http, ticket_id):
    """Busca anexos tentando as rotas conhecidas."""
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
    """Lógica principal com prioridade total ao código vindo do Onvio."""
    uuid = ticket_obj.get("id")
    num_ticket = ticket_obj.get("identifier")
    
    # 1. Busca detalhes se necessário
    if not num_ticket:
        res = http.get(f"{URL_BASE_API}/tickets/{uuid}")
        if res.status_code == 200:
            ticket_obj = res.json()
            num_ticket = ticket_obj.get("identifier")
        else:
            logging.error(f"Não foi possível obter detalhes do UUID {uuid}")
            return False

    num_ticket = int(num_ticket)
    
    # 2. Verifica banco de resiliência
    status_atual, tentativas = db_res.get_ticket_status(num_ticket)
    if status_atual == "SUCESSO":
        return True

    # =========================================================
    # ESTRATÉGIA DE IDENTIFICAÇÃO (O PULO DO GATO)
    # =========================================================
    client_info = ticket_obj.get("clientExpanded", {})
    nome_cliente = str(client_info.get("name", "DESCONHECIDO")).strip().upper()
    
    # Tenta pegar o código direto do campo 'code' que você achou
    cod_onvio = client_info.get("code")
    
    if cod_onvio and str(cod_onvio).strip():
        cod_emp = str(cod_onvio).strip()
        logging.info(f"Código encontrado no Onvio: {cod_emp} para {nome_cliente}")
    else:
        # PLANO B: Se o código estiver vazio no Onvio, usa a inteligência de nomes
        logging.info(f"ℹCliente sem código no Onvio. Usando busca por nome para {nome_cliente}...")
        cod_emp = descobrir_codigo_empresa(nome_cliente, mapa_empresas)
    
    data_iso = ticket_obj.get("created", "")
    if data_iso:
        data_pura = data_iso.split("T")[0]
        ano, mes, _ = data_pura.split("-")
        pasta_periodo = f"{mes}.{ano}"
    else:
        pasta_periodo = "Sem_Data"

    # 3. Higienização e criação de pastas
    nome_pasta_cliente = re.sub(r'[\\/*?:"<>|]', "-", nome_cliente)
    
    anexos = buscar_anexos(http, uuid)
    
    if not anexos:
        logging.info(f"Ticket [{num_ticket}]: Sem anexos. Marcado como concluído.")
        db_res.registrar_ou_atualizar(
            id_ticket=num_ticket, 
            cod_emp=cod_emp, 
            nome_emp=nome_cliente, 
            status="SUCESSO", 
            caminho_pasta="", 
            qtd_anexos=0, 
            erro="", 
        )
        return True
    
    # 🚀 TRAVA DE TESTE: Baixa apenas os últimos 5 arquivos
    anexos_para_baixar = anexos[-5:]
    if len(anexos) > 5:
        logging.info(f"Ticket [{num_ticket}]: Limitando download para os últimos {len(anexos_para_baixar)} arquivos de {len(anexos)}.")

    # Tem anexo cria a pasta!
    pasta_ticket = PASTA_RAIZ / f"{cod_emp} - {nome_pasta_cliente}" / pasta_periodo / str(num_ticket)
    pasta_ticket.mkdir(parents=True, exist_ok=True)

    status_final = "SUCESSO"
    erro_detalhe = ""

    # CORREÇÃO AQUI: loop usa a lista limitada
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
            
            # Trata extração se for compactado
            if nome_arquivo.lower().endswith(('.zip', '.rar')):
                ok, msg = tratar_compactados(caminho_arq, pasta_ticket)
                if not ok:
                    status_final = "ALERTA_HUMANO"
                    erro_detalhe = msg
            
            logging.info(f"Ticket [{num_ticket}]: Arquivo {nome_arquivo} baixado.")
        else:
            status_final = "ERRO_API"
            erro_detalhe = "Falha ao gerar link de download"

    # CORREÇÃO AQUI: Salva a quantidade limitada para a Triagem não dar erro de divergência
    db_res.registrar_ou_atualizar(
        id_ticket=num_ticket, 
        cod_emp=cod_emp, 
        nome_emp=nome_cliente, 
        status=status_final, 
        caminho_pasta=str(pasta_ticket), 
        qtd_anexos=len(anexos_para_baixar), 
        erro=erro_detalhe, 
    )
    return status_final == "SUCESSO"


# ==========================================
# 4. ORQUESTRAÇÃO
# ==========================================
# ==========================================
# 4. ORQUESTRAÇÃO
# ==========================================
def executar_download():
    # 1. Banco Domínio
    db_dom = DatabaseConnection()
    if not db_dom.connect(): return
    mapa_empresas = db_dom.get_mapeamento_empresas()
    db_dom.close()

    # 2. Banco Resiliência
    db_res = ResilienciaDB()

    # 3. Onvio Session
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
        
        # 🚀 NOVA TRAVA DE TESTE: Pega apenas os 5 primeiros tickets (solicitações)
        tickets_para_teste = tickets[:5]
        logging.info(f"MODO TESTE: Processando apenas {len(tickets_para_teste)} solicitações de um total de {len(tickets)}.")
        
        for t in tickets_para_teste:
            baixar_ticket(http, db_res, t, mapa_empresas)

    # =======================================================
    # ⚠️ COMENTADO PARA TESTES: Evita baixar tickets extras 
    # =======================================================
    
    # 5. Caçar GAPS 
    # logging.info("Verificando se existem solicitações puladas (GAPs)...")
    # gaps = db_res.detectar_gaps(limite_retroativo=100)
    # for g_num in gaps:
    #     logging.info(f"Tentando recuperar GAP: {g_num}")
    #     res_gap = http.get(f"{URL_BASE_API}/tickets?identifier={g_num}")
    #     if res_gap.status_code == 200:
    #         items = res_gap.json().get("items", [])
    #         if items:
    #             baixar_ticket(http, db_res, items[0], mapa_empresas)

    # 6. Retentar erros e pendentes
    # logging.info("Retentando tickets com erro ou pendentes...")
    # retries = db_res.get_pendentes_para_retry()
    # for r_num in retries:
    #     res_retry = http.get(f"{URL_BASE_API}/tickets?identifier={r_num}")
    #     if res_retry.status_code == 200:
    #         items = res_retry.json().get("items", [])
    #         if items:
    #             baixar_ticket(http, db_res, items[0], mapa_empresas)

    logging.info("PROCESSO FINALIZADO!")


if __name__ == "__main__":
    executar_download()
