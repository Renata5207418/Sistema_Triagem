import os
import sys
import logging
import shutil
import fitz  
from pathlib import Path
from dotenv import load_dotenv

pasta_atual = str(Path(__file__).parent)
if pasta_atual not in sys.path:
    sys.path.append(pasta_atual)

from motor_ia import classificar_documento_claude
from db.db_resiliencia import db
from db.db_dominio import DatabaseConnection # <--- Importação do banco para validar CNPJs

# --- CONFIGURAÇÃO DE LOGS ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s [TRIAGEM] %(message)s", datefmt="%H:%M:%S")

# ==========================================
# CONFIGURAÇÕES GERAIS E REDE
# ==========================================
RAIZ_PROJETO = Path(__file__).parent.parent
load_dotenv(dotenv_path=RAIZ_PROJETO / ".env")

BASE_CLIENTES = Path(os.getenv("CLIENTES_DIR", RAIZ_PROJETO / "CLIENTES_REDE")) 

MAPA_PASTAS = {
    'guia': 'DOCUMENTOS GERAIS', 'boleto': 'DOCUMENTOS GERAIS', 'invoice_exterior': 'INVOICE',
    'fatura_consumo': 'DOCUMENTOS GERAIS', 'comprovante_pagamento': 'DOCUMENTOS GERAIS',
    'danfe': 'DANFE', 'extrato': 'EXTRATO', 'planilhas': 'PLANILHAS', 'xml': 'XML'
    # nota_servico foi removida daqui pois agora tem roteamento dinâmico
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
            # Evita apagar a raiz do NOTAS_DE_SERVICO se as subpastas estiverem vazias
            if dir_path.name not in pastas_seguras and not any(dir_path.iterdir()):
                try: dir_path.rmdir()
                except OSError: pass

def separar_nao_pdfs(pasta_ticket: Path, id_ticket: int):
    # Regras conhecidas (Adicionado o .ofx)
    regras = {
        '.csv': 'PLANILHAS', '.xls': 'PLANILHAS', '.xlsx': 'PLANILHAS',
        '.png': 'IMAGEM_PRINT', '.jpg': 'IMAGEM_PRINT', '.jpeg': 'IMAGEM_PRINT', 
        '.xml': 'XML', '.ofx': 'EXTRATO'
    }
    
    for arquivo in list(pasta_ticket.rglob('*')):
        if arquivo.is_file():
            ext = arquivo.suffix.lower()
            
            # Se for PDF, deixa para o motor da IA processar
            if ext == '.pdf':
                continue
                
            # Se for uma extensão conhecida
            if ext in regras:
                nome_pasta = regras[ext]
                status_banco = "SUCESSO"
                motivo_banco = ""
                categoria_banco = ext.replace('.', '').upper()
            else:
                # Malha fina para extensões bizarras (ex: .03)
                nome_pasta = 'ERRO_EXTENSAO'
                status_banco = "ERRO"
                motivo_banco = f"Extensão desconhecida: {ext}"
                categoria_banco = "DESCONHECIDO"
                logging.warning(f"Ticket {id_ticket}: Arquivo com extensão inválida detectado: {arquivo.name}")

            destino = pasta_ticket / nome_pasta
            
            # Move o arquivo se ele já não estiver na pasta certa
            if arquivo.parent.name != nome_pasta:
                destino.mkdir(exist_ok=True)
                caminho_final = obter_nome_unico(destino, arquivo.name)
                shutil.move(str(arquivo), str(caminho_final))
                
                db.registrar_documento_triado(
                    id_ticket, 
                    arquivo.name, 
                    caminho_final.name, 
                    categoria_banco, 
                    nome_pasta, 
                    status_banco, 
                    motivo_banco
                )

def mover_cliente_rede(id_ticket: int, pasta_ticket: Path, cod_emp: str):
    if not cod_emp or cod_emp == "0":
        logging.warning(f"Ticket {id_ticket}: cod_emp inválido ou 0. Não será copiado para a rede.")
        return

    try:
        mes_ano = pasta_ticket.parent.name  
        ano = mes_ano.split(".")[1]         
        
        cliente_dir = None
        if BASE_CLIENTES.exists():
            for d in BASE_CLIENTES.iterdir():
                if d.is_dir() and (d.name.startswith(f"{cod_emp}-") or d.name.startswith(f"{cod_emp} -")):
                    cliente_dir = d
                    break
        
        if not cliente_dir:
            logging.warning(f"Ticket {id_ticket}: Pasta de rede para cod_emp {cod_emp} não encontrada em {BASE_CLIENTES}.")
            return

        pasta_contabil_nome = next((d.name for d in cliente_dir.iterdir() if d.name.upper() in ["CONTÁBIL", "CONTABIL"]), "CONTÁBIL")
        nome_pasta_os = pasta_ticket.name 

        destino_contabil = cliente_dir / pasta_contabil_nome / "MOVIMENTO" / ano / mes_ano / "TRIAGEM_ROBO" / nome_pasta_os
        destino_fiscal = cliente_dir / "FISCAL" / "IMPOSTOS" / ano / mes_ano / "MCALC" / "TRIAGEM_ROBO" / nome_pasta_os

        os.makedirs(destino_contabil, exist_ok=True)
        os.makedirs(destino_fiscal, exist_ok=True)

        shutil.copytree(str(pasta_ticket), str(destino_contabil), dirs_exist_ok=True)
        shutil.copytree(str(pasta_ticket), str(destino_fiscal), dirs_exist_ok=True)

        logging.info(f"Ticket {id_ticket}: Copiado com sucesso para a rede ({cliente_dir.name}).")
    except Exception as e:
        logging.error(f"Ticket {id_ticket}: Erro ao tentar copiar para a rede: {e}")

# ==========================================
# 2. MOTOR PRINCIPAL
# ==========================================
def processar_ticket(id_ticket: int, caminho_pasta: str, qtd_esperada: int, cod_emp: str):
    pasta_ticket = Path(caminho_pasta)
    
    if not pasta_ticket.exists():
        logging.warning(f"Ticket {id_ticket}: Pasta não encontrada ({caminho_pasta}).")
        db.marcar_ticket_triado(id_ticket, "ERRO_PASTA", "Pasta física não encontrada.")
        return

    logging.info(f"--- Processando Ticket {id_ticket} (Cód: {cod_emp}) ---")
    
    # 1. Busca todos os CNPJs filiais do cliente dono do ticket
    cnpjs_cliente = []
    if cod_emp and cod_emp != "0":
        db_dom = DatabaseConnection()
        if db_dom.connect():
            cnpjs_cliente = db_dom.obter_cnpjs_do_grupo(cod_emp)
            db_dom.close()
    
    arquivos_encontrados = len([f for f in pasta_ticket.rglob('*') if f.is_file()])
    
    # 2. Varre as extensões não-PDF (incluindo as desconhecidas/erros)
    separar_nao_pdfs(pasta_ticket, id_ticket)
    
    pastas_seguranca = list(MAPA_PASTAS.values()) + [
        'LIMITE_PAGINAS', 'ERRO_PROCESSAMENTO', 'LOW_CONFIDENCE', 'IMAGEM_PRINT', 
        'ERRO_EXTENSAO', 'NOTAS_DE_SERVICO'
    ]
    
    for arquivo in list(pasta_ticket.rglob('*.pdf')):
        if arquivo.is_file():
            # Pula se já estiver em uma pasta finalizada
            if any(p in arquivo.parts for p in pastas_seguranca):
                continue
                
            try:
                doc = fitz.open(str(arquivo))
                if doc.needs_pass: raise ValueError("PDF Protegido por Senha")
                
                if len(doc) > 250:
                    destino = pasta_ticket / 'LIMITE_PAGINAS'
                    novo_nome = arquivo.name
                    doc.close()
                    destino.mkdir(exist_ok=True)
                    caminho_final = obter_nome_unico(destino, novo_nome)
                    shutil.move(str(arquivo), str(caminho_final))
                    db.registrar_documento_triado(id_ticket, arquivo.name, caminho_final.name, "ignorar_tamanho", "LIMITE_PAGINAS", "SUCESSO")
                    continue

                texto_bruto = doc[0].get_text("text")[:3000]
                doc.close()
                
                logging.info(f"Classificando [{arquivo.name}] com IA...")
                
                # O motor agora retorna um dicionário
                resultado_ia = classificar_documento_claude(texto_bruto[:1500])
                categoria_ia = resultado_ia.get("categoria", "LOW_CONFIDENCE")
                
                # Roteamento Inteligente de Pastas
                if categoria_ia == 'nota_servico':
                    cnpj_prestador = resultado_ia.get("cnpj_prestador")
                    cnpj_tomador = resultado_ia.get("cnpj_tomador")
                    
                    if cnpj_prestador in cnpjs_cliente:
                        nome_pasta_final = "NOTAS_DE_SERVICO/EMITIDAS"
                    elif cnpj_tomador in cnpjs_cliente:
                        nome_pasta_final = "NOTAS_DE_SERVICO/TOMADAS"
                    else:
                        nome_pasta_final = "NOTAS_DE_SERVICO/TERCEIROS"
                else:
                    nome_pasta_final = MAPA_PASTAS.get(categoria_ia, 'LOW_CONFIDENCE')
                
                destino = pasta_ticket / nome_pasta_final
                
                # Corrige barras no Windows/Linux para garantir a criação correta de subpastas
                destino = Path(os.path.normpath(str(destino))) 
                
                novo_nome = f"{categoria_ia.upper()}_{arquivo.stem.replace(' ', '_')}{arquivo.suffix}"
                
                destino.mkdir(parents=True, exist_ok=True)
                caminho_final = obter_nome_unico(destino, novo_nome)
                shutil.move(str(arquivo), str(caminho_final))
                
                texto_para_banco = texto_bruto if categoria_ia == 'nota_servico' else None
                
                db.registrar_documento_triado(
                    id_ticket, 
                    arquivo.name, 
                    caminho_final.name, 
                    categoria_ia, 
                    str(nome_pasta_final), 
                    "SUCESSO", 
                    texto_extraido=texto_para_banco
                )
                logging.info(f"-> {caminho_final.name}")
                
            except Exception as e:
                logging.error(f"Erro PDF {arquivo.name}: {e}")
                erro_dir = pasta_ticket / 'ERRO_PROCESSAMENTO'
                erro_dir.mkdir(exist_ok=True)
                caminho_final = obter_nome_unico(erro_dir, arquivo.name)
                shutil.move(str(arquivo), str(caminho_final))
                
                # O Erro de senha já será capturado aqui e salvo no banco para o Front-end
                msg_erro = "PDF Protegido por Senha" if "Protegido por Senha" in str(e) else str(e)
                
                db.registrar_documento_triado(
                    id_ticket, 
                    arquivo.name, 
                    caminho_final.name, 
                    "ERRO", 
                    "ERRO_PROCESSAMENTO", 
                    "ERRO", 
                    msg_erro
                )

    limpar_pastas_vazias(pasta_ticket)
    
    if arquivos_encontrados != qtd_esperada:
        div = f"Esperava {qtd_esperada}, encontrou {arquivos_encontrados}"
        logging.warning(f"Ticket {id_ticket}: {div}")
        db.marcar_ticket_triado(id_ticket, "CONCLUIDO_COM_DIVERGENCIA", div)
    else:
        db.marcar_ticket_triado(id_ticket, "CONCLUIDO")
        logging.info(f"Ticket {id_ticket} 100% OK.")

    mover_cliente_rede(id_ticket, pasta_ticket, cod_emp)


def executar_triagem():
    logging.info("Iniciando Módulo de Triagem IA...")
    db._criar_tabelas() # Garante que as tabelas existem
    pendentes = db.get_tickets_pendentes_triagem()
    
    if not pendentes:
        logging.info("Nenhum ticket novo.")
        return
        
    for p in pendentes:
        if not p['caminho_pasta']:
            db.marcar_ticket_triado(p['id_ticket'], "SEM_ANEXOS")
            continue
        processar_ticket(p['id_ticket'], p['caminho_pasta'], p['qtd_anexos_esperados'], p['cod_emp'])

if __name__ == "__main__":
    executar_triagem()
    