import os
import sys
import logging
import shutil
import fitz  
import io
import base64
from pathlib import Path
from dotenv import load_dotenv

pasta_atual = str(Path(__file__).parent)
if pasta_atual not in sys.path:
    sys.path.append(pasta_atual)

from motor_ia import classificar_documento_claude
from db.db_resiliencia import db
from db.db_dominio import DatabaseConnection

# --- CONFIGURAÇÃO DE LOGS ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s [TRIAGEM] %(message)s", datefmt="%H:%M:%S")

# ==========================================
# CONFIGURAÇÕES GERAIS E REDE
# ==========================================
RAIZ_PROJETO = Path(__file__).parent.parent
load_dotenv(dotenv_path=RAIZ_PROJETO / ".env")

BASE_CLIENTES = Path(os.getenv("CLIENTES_DIR", RAIZ_PROJETO / "CLIENTES_REDE")) 

# Mapa atualizado com fatura_consumo para resolver as NFC-e de gás
MAPA_PASTAS = {
    'guia': 'DOCUMENTOS GERAIS', 
    'boleto': 'DOCUMENTOS GERAIS', 
    'invoice_exterior': 'INVOICE',
    'fatura_consumo': 'DANFE', 
    'comprovante_pagamento': 'DOCUMENTOS GERAIS',
    'danfe': 'DANFE', 
    'extrato': 'EXTRATO', 
    'planilhas': 'PLANILHAS', 
    'xml': 'XML',
    'fatura_locacao': 'DOCUMENTOS GERAIS' 
}

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
        # CORREÇÃO: Variável 'novo_caminho' corrigida (sem o 'i' extra)
        novo_caminho = caminho_destino / f"{nome_base}_{contador}{extensao}"
        if not novo_caminho.exists(): return novo_caminho
        contador += 1

def limpar_pastas_vazias(pasta_raiz: Path):
    pastas_seguras = list(MAPA_PASTAS.values()) + [
        'LIMITE_PAGINAS', 'ERRO_PROCESSAMENTO', 'LOW_CONFIDENCE', 'IMAGEM_PRINT', 
        'ERRO_EXTENSAO', 'NOTAS_DE_SERVICO'
    ]
    for root, dirs, files in os.walk(pasta_raiz, topdown=False):
        for d in dirs:
            dir_path = Path(root) / d
            if dir_path.name not in pastas_seguras and not any(dir_path.iterdir()):
                try: dir_path.rmdir()
                except OSError: pass

def separar_nao_pdfs(pasta_ticket: Path, id_ticket: int):
    regras = {
        '.csv': 'PLANILHAS', '.xls': 'PLANILHAS', '.xlsx': 'PLANILHAS',
        '.png': 'IMAGEM_PRINT', '.jpg': 'IMAGEM_PRINT', '.jpeg': 'IMAGEM_PRINT', 
        '.xml': 'XML', '.ofx': 'EXTRATO'
    }
    
    for arquivo in list(pasta_ticket.rglob('*')):
        if arquivo.is_file():
            ext = arquivo.suffix.lower()
            if ext == '.pdf': continue
                
            if ext in regras:
                nome_pasta = regras[ext]
                status_banco = "SUCESSO"
                motivo_banco = ""
                categoria_banco = ext.replace('.', '').upper()
            else:
                nome_pasta = 'ERRO_EXTENSAO'
                status_banco = "ERRO"
                motivo_banco = f"Extensão desconhecida: {ext}"
                categoria_banco = "DESCONHECIDO"

            destino = pasta_ticket / nome_pasta
            if arquivo.parent.name != nome_pasta:
                destino.mkdir(exist_ok=True)
                caminho_final = obter_nome_unico(destino, arquivo.name)
                shutil.move(str(arquivo), str(caminho_final))
                db.registrar_documento_triado(id_ticket, arquivo.name, caminho_final.name, categoria_banco, nome_pasta, status_banco, motivo_banco)

def mover_cliente_rede(id_ticket: int, pasta_ticket: Path, cod_emp: str):
    if not cod_emp or cod_emp == "0": return
    try:
        mes_ano = pasta_ticket.parent.name  
        ano = mes_ano.split(".")[1]         
        cliente_dir = None
        if BASE_CLIENTES.exists():
            for d in BASE_CLIENTES.iterdir():
                if d.is_dir() and (d.name.startswith(f"{cod_emp}-") or d.name.startswith(f"{cod_emp} -")):
                    cliente_dir = d
                    break
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
    
    pastas_seguranca = list(MAPA_PASTAS.values()) + [
        'LIMITE_PAGINAS', 'ERRO_PROCESSAMENTO', 'LOW_CONFIDENCE', 'IMAGEM_PRINT', 
        'ERRO_EXTENSAO', 'NOTAS_DE_SERVICO'
    ]
    
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

                # Preparação visual
                primeira_pag = fitz.open()
                primeira_pag.insert_pdf(doc, from_page=0, to_page=0)
                pdf_bytes = primeira_pag.tobytes()
                primeira_pag.close()
                doc.close() 
                
                pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')
                
                logging.info(f"Classificando visualmente [{arquivo.name}]...")
                resultado_ia = classificar_documento_claude(pdf_base64)
                categoria_ia = resultado_ia.get("categoria", "ignorar")
                
                status_banco = "SUCESSO"
                if categoria_ia == 'ERRO_API':
                    status_banco = "ERRO"
                    nome_pasta_final = "ERRO_PROCESSAMENTO"
                elif categoria_ia == 'ignorar':
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
                logging.info(f"-> {caminho_final.name} [{status_banco}]")
                
            except Exception as e:
                logging.error(f"Erro PDF {arquivo.name}: {e}")
                erro_dir = pasta_ticket / 'ERRO_PROCESSAMENTO'
                erro_dir.mkdir(exist_ok=True)
                caminho_final = obter_nome_unico(erro_dir, arquivo.name)
                shutil.move(str(arquivo), str(caminho_final))
                msg_erro = "PDF Protegido por Senha" if "Protegido por Senha" in str(e) else str(e)
                db.registrar_documento_triado(id_ticket, arquivo.name, caminho_final.name, "ERRO", "ERRO_PROCESSAMENTO", "ERRO", msg_erro)

    limpar_pastas_vazias(pasta_ticket)
    if arquivos_encontrados != qtd_esperada:
        db.marcar_ticket_triado(id_ticket, "CONCLUIDO_COM_DIVERGENCIA", f"Esperava {qtd_esperada}, encontrou {arquivos_encontrados}")
    else:
        db.marcar_ticket_triado(id_ticket, "CONCLUIDO")
    mover_cliente_rede(id_ticket, pasta_ticket, cod_emp)

def executar_triagem():
    logging.info("Iniciando Módulo de Triagem IA...")
    db._criar_tabelas()
    pendentes = db.get_tickets_pendentes_triagem()
    if not pendentes: return
    for p in pendentes:
        if not p['caminho_pasta']:
            db.marcar_ticket_triado(p['id_ticket'], "SEM_ANEXOS")
            continue
        processar_ticket(p['id_ticket'], p['caminho_pasta'], p['qtd_anexos_esperados'], p['cod_emp'])

if __name__ == "__main__":
    executar_triagem()
    