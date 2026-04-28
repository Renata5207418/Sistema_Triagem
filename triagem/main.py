import os
import sys
import logging
import mimetypes
import shutil
import fitz
import io
import base64
from pathlib import Path
from dotenv import load_dotenv
import unicodedata

pasta_atual = str(Path(__file__).parent)
if pasta_atual not in sys.path:
    sys.path.append(pasta_atual)

from motor_ia import classificar_documento_claude
from db.db_resiliencia import db
from db.db_dominio import DatabaseConnection

# --- CONFIGURAÇÃO DE LOGS ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s [TRIAGEM] %(message)s", datefmt="%H:%M:%S")

RAIZ_PROJETO = Path(__file__).parent.parent
load_dotenv(dotenv_path=RAIZ_PROJETO / ".env")

BASE_CLIENTES = Path(os.getenv("CLIENTES_DIR", RAIZ_PROJETO / "CLIENTES_REDE"))

MAPA_PASTAS = {
    'guia': 'DOCUMENTOS GERAIS',
    'boleto': 'DOCUMENTOS GERAIS',
    'invoice_exterior': 'INVOICE',
    'fatura_consumo': 'FATURAS',
    'comprovante_pagamento': 'COMPROVANTES',
    'danfe': 'DANFE',
    'extrato': 'EXTRATO',
    'planilhas': 'PLANILHAS',
    'xml': 'XML',
    'fatura_locacao': 'FATURAS',
    'revisao_manual': 'REVISAO_MANUAL'
}

# ==========================================
# NOVA CAMADA PRÉ-IA (Detecta Frankensteins de graça)
# ==========================================
def normalizar_texto(texto: str) -> str:
    texto = texto.lower().strip()
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("utf-8")


def detectar_tipo_pagina(texto: str) -> str:
    t = normalizar_texto(texto)
    if "extrato consolidado" in t or "extrato de conta" in t or "saldo anterior" in t or "lancamentos do periodo" in t: 
        return "extrato"    
    if "linha digitavel" in t or ("ficha de compensacao" in t and "autenticacao mecanica" in t):
        return "boleto"    
    if "saldo anterior" in t or "lancamentos do periodo" in t or "saldo total" in t:
        return "extrato"    
    if "nfs-e" in t or "nota fiscal de servico" in t: 
        return "nota_servico"    
    if "documento de arrecadacao" in t or "gnre" in t or "simples nacional" in t or ("dam" in t and "prefeitura" in t):
        return "guia"    
    if "linha digitavel" in t or (("codigo de barras" in t or "ficha de compensacao" in t) and "banco" in t):
        return "boleto"    
    if "comprovante de pagamento" in t or "comprovante pix" in t or "recibo" in t:
        return "comprovante"    
    if "darf" in t and "lancamentos do periodo" not in t:
        return "guia"    
    return "desconhecido"


def analisar_documento_misto(doc) -> str:
    try:
        if len(doc) <= 2: return "OK"
        tipos = []
        paginas_com_texto = 0
        for i in range(min(len(doc), 6)):
            texto = doc[i].get_text("text")
            if not texto or len(texto.strip()) < 80: continue
            paginas_com_texto += 1
            tipos.append(detectar_tipo_pagina(texto))
        
        tipos_unicos = set(tipos)
        if "desconhecido" in tipos_unicos and len(tipos_unicos) > 1: tipos_unicos.remove("desconhecido")
        
        if "extrato" in tipos_unicos:
            # Remove falsos positivos comuns em extratos
            for falso_positivo in ["boleto", "guia"]:
                if falso_positivo in tipos_unicos:
                    tipos_unicos.remove(falso_positivo)
        
        if len(tipos_unicos) > 1:
            logging.info(f"Pré-IA: Frankenstein real detectado. Tipos={tipos_unicos}")
            return "DOCUMENTOS_UNIFICADOS"
        
        return "OK"
    except Exception as e:
        return "OK"

# ==========================================
# 1. FUNÇÕES DE ARQUIVO E REDE
# ==========================================
def obter_nome_unico(caminho_destino: Path, nome_arquivo: str) -> Path:
    caminho_completo = caminho_destino / nome_arquivo
    if not caminho_completo.exists(): return caminho_completo
    nome_base = caminho_completo.stem
    extensao = caminho_completo.suffix
    contador = 1
    while True:
        novo_caminho = caminho_destino / f"{nome_base}_{contador}{extensao}"
        if not novo_caminho.exists(): return novo_caminho
        contador += 1

def limpar_pastas_vazias(pasta_raiz: Path):
    pastas_seguras = list(MAPA_PASTAS.values()) + ['LIMITE_PAGINAS', 'ERRO_PROCESSAMENTO', 'LOW_CONFIDENCE', 'IMAGEM_PRINT', 'ERRO_EXTENSAO', 'NOTAS_DE_SERVICO', 'DOCUMENTOS_UNIFICADOS']
    for root, dirs, files in os.walk(pasta_raiz, topdown=False):
        for d in dirs:
            dir_path = Path(root) / d
            if dir_path.name not in pastas_seguras and not any(dir_path.iterdir()):
                try: dir_path.rmdir()
                except OSError: pass


def detectar_tipo_real(caminho_arquivo: Path):
    """Identifica o tipo de arquivo pelos Magic Bytes (DNA)."""
    SIGNATURES = {
        b'%PDF': ('.pdf', 'PDF'),
        b'PK\x03\x04': ('.zip', 'COMPACTADOS'), # Também identifica .xlsx e .docx
        b'Rar!\x1a\x07': ('.rar', 'COMPACTADOS'),
        b'\xff\xd8\xff': ('.jpg', 'IMAGEM_PRINT'),
        b'\x89PNG': ('.png', 'IMAGEM_PRINT'),
        b'\xd0\xcf\x11\xe0': ('.xls', 'PLANILHAS'),
        b'<?xml': ('.xml', 'XML'),
    }

    try:
        with open(caminho_arquivo, 'rb') as f:
            header = f.read(8)
        for sig, (ext, cat) in SIGNATURES.items():
            if header.startswith(sig):
                # Caso especial: XLSX/DOCX começam com PK igual ao ZIP
                # Mas para a triagem contábil, se não extraiu, tratamos como compactado/erro
                return ext, cat
    except:
        pass
    return None, None


def separar_nao_pdfs(pasta_ticket: Path, id_ticket: int):
    regras_extensao = {
        '.csv': 'PLANILHAS', 
        '.ofx': 'EXTRATO', 
        '.doc': 'DOCUMENTOS GERAIS', 
        '.docx': 'DOCUMENTOS GERAIS'
    }

    pastas_seguras = ['NOTAS_DE_SERVICO', 'DOCUMENTOS_UNIFICADOS', 'ERRO_PROCESSAMENTO', 'LIMITE_PAGINAS']

    for arquivo in list(pasta_ticket.rglob('*')):
        if not arquivo.is_file() or any(p in arquivo.parts for p in pastas_seguras):
            continue

        ext_original = arquivo.suffix.lower()        
        ext_dna, categoria_dna = detectar_tipo_real(arquivo)

        if ext_dna == '.pdf':
            if ext_original != '.pdf':
                novo_nome = arquivo.with_suffix('.pdf')
                arquivo.rename(novo_nome)
                logging.info(f"Resgatado PDF: {arquivo.name} -> {novo_nome.name}")
            continue # Deixa o PDF para o fluxo normal da IA

        if categoria_dna:
            destino = pasta_ticket / categoria_dna
            destino.mkdir(exist_ok=True)
            # Garante a extensão correta se ela não existia
            nome_final = arquivo.name if ext_original == ext_dna else arquivo.name + ext_dna
            caminho_final = obter_nome_unico(destino, nome_final)
            shutil.move(str(arquivo), str(caminho_final))
            db.registrar_documento_triado(id_ticket, arquivo.name, caminho_final.name, ext_dna.replace('.','').upper(), categoria_dna, "SUCESSO")
            logging.info(f"Movido por DNA: {arquivo.name} -> {categoria_dna}")
            continue

        if ext_original in regras_extensao:
            nome_pasta = regras_extensao[ext_original]
            destino = pasta_ticket / nome_pasta
            destino.mkdir(exist_ok=True)
            caminho_final = obter_nome_unico(destino, arquivo.name)
            shutil.move(str(arquivo), str(caminho_final))
            db.registrar_documento_triado(id_ticket, arquivo.name, caminho_final.name, ext_original.replace('.','').upper(), nome_pasta, "SUCESSO")
            continue

        if ext_original == '.pdf':
            continue

        nome_pasta = 'ERRO_EXTENSAO'
        destino = pasta_ticket / nome_pasta
        destino.mkdir(exist_ok=True)
        caminho_final = obter_nome_unico(destino, arquivo.name)
        shutil.move(str(arquivo), str(caminho_final))
        db.registrar_documento_triado(id_ticket, arquivo.name, caminho_final.name, "DESCONHECIDO", nome_pasta, "ERRO", f"DNA não identificado. Extensão: {ext_original}")


def mover_cliente_rede(id_ticket: int, pasta_ticket: Path, cod_emp: str):
    if not cod_emp or cod_emp == "0": return
    try:
        mes_ano = pasta_ticket.parent.name
        ano = mes_ano.split(".")[1]
        cliente_dir = None
        if BASE_CLIENTES.exists():
            for d in BASE_CLIENTES.iterdir():
                if d.is_dir() and (d.name.startswith(f"{cod_emp}-") or d.name.startswith(f"{cod_emp} -")):
                    cliente_dir = d; break
        if not cliente_dir: return
        pasta_contabil_nome = next((d.name for d in cliente_dir.iterdir() if d.name.upper() in ["CONTÁBIL", "CONTABIL"]), "CONTÁBIL")
        nome_pasta_os = pasta_ticket.name
        destino_contabil = cliente_dir / pasta_contabil_nome / "MOVIMENTO" / ano / mes_ano / "TRIAGEM_ROBO" / nome_pasta_os
        destino_fiscal = cliente_dir / "FISCAL" / "IMPOSTOS" / ano / mes_ano / "MCALC" / "TRIAGEM_ROBO" / nome_pasta_os
        os.makedirs(destino_contabil, exist_ok=True)
        os.makedirs(destino_fiscal, exist_ok=True)
        shutil.copytree(str(pasta_ticket), str(destino_contabil), dirs_exist_ok=True)
        shutil.copytree(str(pasta_ticket), str(destino_fiscal), dirs_exist_ok=True)
    except Exception as e:
        logging.error(f"Ticket {id_ticket}: Erro rede: {e}")

# ==========================================
# 2. MOTOR PRINCIPAL
# ==========================================
def processar_ticket(id_ticket: int, caminho_pasta: str, qtd_esperada: int, cod_emp: str):
    pasta_ticket = Path(caminho_pasta)
    if not pasta_ticket.exists():
        db.marcar_ticket_triado(id_ticket, "ERRO_PASTA", "Pasta física não encontrada.")
        return

    logging.info(f"--- Ticket {id_ticket} (Cód: {cod_emp}) ---")
    cnpjs_cliente = []
    if cod_emp and cod_emp != "0":
        db_dom = DatabaseConnection()
        if db_dom.connect():
            cnpjs_cliente = db_dom.obter_cnpjs_do_grupo(cod_emp)
            db_dom.close()

    arquivos_encontrados = len([f for f in pasta_ticket.rglob('*') if f.is_file()])
    separar_nao_pdfs(pasta_ticket, id_ticket)

    pastas_seguranca = list(MAPA_PASTAS.values()) + ['LIMITE_PAGINAS', 'ERRO_PROCESSAMENTO', 'LOW_CONFIDENCE', 'IMAGEM_PRINT', 'ERRO_EXTENSAO', 'NOTAS_DE_SERVICO', 'DOCUMENTOS_UNIFICADOS']

    for arquivo in list(pasta_ticket.rglob('*.pdf')):
        if arquivo.is_file():
            if any(p in arquivo.parts for p in pastas_seguranca): continue

            try:
                doc = fitz.open(str(arquivo))
                if doc.needs_pass: raise ValueError("PDF Protegido por Senha")

                if len(doc) > 250:
                    destino = pasta_ticket / 'LIMITE_PAGINAS'
                    doc.close()
                    destino.mkdir(exist_ok=True)
                    caminho_final = obter_nome_unico(destino, arquivo.name)
                    shutil.move(str(arquivo), str(caminho_final))
                    db.registrar_documento_triado(id_ticket, arquivo.name, caminho_final.name, "ignorar_tamanho", "LIMITE_PAGINAS", "SUCESSO")
                    continue

                # Pré-IA: Barra o Frankenstein
                decisao_pre_ia = analisar_documento_misto(doc)
                if decisao_pre_ia == "DOCUMENTOS_UNIFICADOS":
                    destino = pasta_ticket / 'DOCUMENTOS_UNIFICADOS'
                    destino.mkdir(exist_ok=True)
                    novo_nome = f"DOCUMENTO_UNIFICADO_{arquivo.stem.replace(' ', '_')}{arquivo.suffix}"
                    caminho_final = obter_nome_unico(destino, novo_nome)
                    doc.close()
                    shutil.move(str(arquivo), str(caminho_final))
                    db.registrar_documento_triado(id_ticket, arquivo.name, caminho_final.name, "documento_unificado", "DOCUMENTOS_UNIFICADOS", "ERRO", "Arquivo com múltiplos tipos. Fatiar.")
                    continue

                primeira_pag = fitz.open()
                primeira_pag.insert_pdf(doc, from_page=0, to_page=0)
                pdf_bytes = primeira_pag.tobytes()
                primeira_pag.close()
                doc.close()

                pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')

                logging.info(f"Classificando visualmente [{arquivo.name}]...")
                resultado_ia = classificar_documento_claude(pdf_base64)
                categoria_ia = resultado_ia.get("categoria", "revisao_manual")

                status_banco = "SUCESSO"
                if categoria_ia == 'ERRO_API':
                    status_banco = "ERRO"
                    nome_pasta_final = "ERRO_PROCESSAMENTO"
                elif categoria_ia == 'revisao_manual':
                    status_banco = "ATENCAO"
                    nome_pasta_final = "LOW_CONFIDENCE"
                elif categoria_ia == 'nota_servico':
                    cnpj_p = resultado_ia.get("cnpj_prestador")
                    cnpj_t = resultado_ia.get("cnpj_tomador")
                    if cnpj_p in cnpjs_cliente: nome_pasta_final = "NOTAS_DE_SERVICO/EMITIDAS"
                    elif cnpj_t in cnpjs_cliente: nome_pasta_final = "NOTAS_DE_SERVICO/TOMADAS"
                    else: nome_pasta_final = "NOTAS_DE_SERVICO/TERCEIROS"
                else:
                    nome_pasta_final = MAPA_PASTAS.get(categoria_ia, 'LOW_CONFIDENCE')
                    if nome_pasta_final == 'LOW_CONFIDENCE': status_banco = "ATENCAO"

                destino = Path(os.path.normpath(str(pasta_ticket / nome_pasta_final)))
                destino.mkdir(parents=True, exist_ok=True)
                novo_nome = f"{categoria_ia.upper()}_{arquivo.stem.replace(' ', '_')}{arquivo.suffix}"
                caminho_final = obter_nome_unico(destino, novo_nome)
                shutil.move(str(arquivo), str(caminho_final))
                db.registrar_documento_triado(id_ticket, arquivo.name, caminho_final.name, categoria_ia, str(nome_pasta_final), status_banco)

            # ERRO 1: Captura o corrompido que nem a IA salva
            except fitz.FileDataError:
                logging.error(f"Arquivo corrompido: {arquivo.name}")
                erro_dir = pasta_ticket / 'ERRO_PROCESSAMENTO'
                erro_dir.mkdir(exist_ok=True)
                caminho_final = obter_nome_unico(erro_dir, arquivo.name)
                shutil.move(str(arquivo), str(caminho_final))
                db.registrar_documento_triado(id_ticket, arquivo.name, caminho_final.name, "ERRO", "ERRO_PROCESSAMENTO", "ERRO", "Arquivo corrompido ou formato inválido.")

            # ERRO 2: Senhas e outros BOs
            except Exception as e:
                logging.error(f"Erro PDF {arquivo.name}: {e}")
                erro_dir = pasta_ticket / 'ERRO_PROCESSAMENTO'
                erro_dir.mkdir(exist_ok=True)
                caminho_final = obter_nome_unico(erro_dir, arquivo.name)
                shutil.move(str(arquivo), str(caminho_final))
                msg_erro = "Protegido por Senha" if "Protegido" in str(e) or "pass" in str(e).lower() else str(e)
                status_erro = "PENDENTE_SENHA" if "Senha" in msg_erro else "ERRO"
                db.registrar_documento_triado(id_ticket, arquivo.name, caminho_final.name, "ERRO", "ERRO_PROCESSAMENTO", status_erro, msg_erro)

    limpar_pastas_vazias(pasta_ticket)
    if arquivos_encontrados != qtd_esperada:
        db.marcar_ticket_triado(id_ticket, "CONCLUIDO_COM_DIVERGENCIA", f"Esperava {qtd_esperada}, encontrou {arquivos_encontrados}")
    else:
        db.marcar_ticket_triado(id_ticket, "CONCLUIDO")
    mover_cliente_rede(id_ticket, pasta_ticket, cod_emp)

def executar_triagem():
    logging.info("Iniciando Módulo de Triagem IA...")
    db._criar_tabelas()
    
    # BÔNUS: O main agora puxa arquivos novos que caíram na OS vindos do Upload de Reprocessamento!
    pendentes = db.get_tickets_pendentes_triagem()
    if not pendentes: return
    for p in pendentes:
        if not p['caminho_pasta']:
            db.marcar_ticket_triado(p['id_ticket'], "SEM_ANEXOS")
            continue
        processar_ticket(p['id_ticket'], p['caminho_pasta'], p['qtd_anexos_esperados'], p['cod_emp'])

if __name__ == "__main__":
    executar_triagem()
