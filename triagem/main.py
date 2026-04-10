import os
import sys
import sqlite3
import logging
import shutil
import fitz  
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

pasta_atual = str(Path(__file__).parent)
if pasta_atual not in sys.path:
    sys.path.append(pasta_atual)

from motor_ia import classificar_documento_claude

# --- CONFIGURAÇÃO DE LOGS ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s [TRIAGEM] %(message)s", datefmt="%H:%M:%S")

# ==========================================
# CONFIGURAÇÕES GERAIS E BANCO
# ==========================================
RAIZ_PROJETO = Path(__file__).parent.parent
load_dotenv(dotenv_path=RAIZ_PROJETO / ".env")

DB_PATH = RAIZ_PROJETO / "banco_rpa.db"

MAPA_PASTAS = {
    'guia': 'DOCUMENTOS GERAIS',
    'boleto': 'DOCUMENTOS GERAIS',
    'invoice_exterior': 'INVOICE',
    'fatura_consumo': 'DOCUMENTOS GERAIS',
    'comprovante_pagamento': 'DOCUMENTOS GERAIS',
    'danfe': 'DANFE',
    'nota_servico': 'TOMADOS',
    'extrato': 'EXTRATO',
    'planilhas': 'PLANILHAS',
    'xml': 'XML'
}

# ==========================================
# 1. FUNÇÕES DE BANCO DE DADOS
# ==========================================
def setup_banco_triagem():
    """Cria a tabela de rastreabilidade da triagem se não existir."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS documentos_triados (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                id_ticket INTEGER,
                nome_original TEXT,
                nome_final TEXT,
                categoria_ia TEXT,
                pasta_destino TEXT,
                status TEXT,
                motivo_erro TEXT,
                data_processamento TEXT 
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tickets_triados (
                id_ticket INTEGER PRIMARY KEY,
                status_triagem TEXT,
                divergencia TEXT,
                data_conclusao TEXT 
            )
        """)

def registrar_documento(id_ticket, original, final, categoria, destino, status, erro=""):
    """Salva a custódia do documento individual no banco."""
    agora = datetime.now().isoformat()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            INSERT INTO documentos_triados 
            (id_ticket, nome_original, nome_final, categoria_ia, pasta_destino, status, motivo_erro, data_processamento)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (id_ticket, original, final, categoria, destino, status, erro, agora))

def marcar_ticket_triado(id_ticket, status, divergencia=""):
    """Marca a OS inteira como finalizada na triagem."""
    agora = datetime.now().isoformat()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            INSERT OR REPLACE INTO tickets_triados (id_ticket, status_triagem, divergencia, data_conclusao)
            VALUES (?, ?, ?, ?)
        """, (id_ticket, status, divergencia, agora))

def get_tickets_pendentes():
    """Busca tickets que tiveram download com sucesso, mas ainda não foram triados."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute("""
            SELECT d.id_ticket, d.caminho_pasta, d.qtd_anexos_esperados 
            FROM downloads d
            LEFT JOIN tickets_triados t ON d.id_ticket = t.id_ticket
            WHERE d.status = 'SUCESSO' AND t.id_ticket IS NULL
            ORDER BY d.id_ticket ASC
        """)
        return cursor.fetchall()


# ==========================================
# 2. FUNÇÕES DE ARQUIVO E IA
# ==========================================
def obter_nome_unico(caminho_destino: Path, nome_arquivo: str) -> Path:
    caminho_completo = caminho_destino / nome_arquivo
    if not caminho_completo.exists():
        return caminho_completo
    nome_base = caminho_completo.stem
    extensao = caminho_completo.suffix
    contador = 1
    while True:
        novo_caminho = caminho_destino / f"{nome_base}_{contador}{extensao}"
        if not novo_caminho.exists():
            return novo_caminho
        contador += 1

def limpar_pastas_vazias(pasta_raiz: Path):
    """Apaga subpastas vazias (ex: pastas de ZIP extraído)"""
    # Lista de pastas que não devemos apagar, mesmo que estejam vazias
    pastas_seguras = list(MAPA_PASTAS.values()) + ['LIMITE_PAGINAS', 'ERRO_PROCESSAMENTO', 'LOW_CONFIDENCE', 'IMAGEM_PRINT']
    
    for root, dirs, files in os.walk(pasta_raiz, topdown=False):
        for d in dirs:
            dir_path = Path(root) / d
            if dir_path.name not in pastas_seguras and not any(dir_path.iterdir()):
                try:
                    dir_path.rmdir()
                except OSError:
                    pass

def separar_nao_pdfs(pasta_ticket: Path, id_ticket: int):
    """Move planilhas, xml e imagens ANTES da IA processar os PDFs."""
    regras = {
        '.csv': 'PLANILHAS', '.xls': 'PLANILHAS', '.xlsx': 'PLANILHAS',
        '.png': 'IMAGEM_PRINT', '.jpg': 'IMAGEM_PRINT', '.jpeg': 'IMAGEM_PRINT',
        '.xml': 'XML'
    }
    for arquivo in list(pasta_ticket.rglob('*')):
        if arquivo.is_file():
            ext = arquivo.suffix.lower()
            if ext in regras:
                destino = pasta_ticket / regras[ext]
                # Só move se o arquivo já não estiver na pasta correta
                if arquivo.parent.name != regras[ext]:
                    destino.mkdir(exist_ok=True)
                    caminho_final = obter_nome_unico(destino, arquivo.name)
                    shutil.move(str(arquivo), str(caminho_final))
                    registrar_documento(id_ticket, arquivo.name, caminho_final.name, ext.replace('.', '').upper(), regras[ext], "SUCESSO")


# ==========================================
# 3. MOTOR PRINCIPAL
# ==========================================
def processar_ticket(id_ticket: int, caminho_pasta: str, qtd_esperada: int):
    pasta_ticket = Path(caminho_pasta)
    
    if not pasta_ticket.exists():
        logging.warning(f"Ticket {id_ticket}: Pasta não encontrada ({caminho_pasta}).")
        marcar_ticket_triado(id_ticket, "ERRO_PASTA", "Pasta física não encontrada.")
        return

    logging.info(f"--- Processando Ticket {id_ticket} ---")
    
    # 1. Conta o total de arquivos (incluindo em subpastas)
    arquivos_encontrados = len([f for f in pasta_ticket.rglob('*') if f.is_file()])
    
    # 2. Filtra o lixo
    separar_nao_pdfs(pasta_ticket, id_ticket)
    
    # Lista de pastas de segurança (o robô não mexe no que está aqui)
    pastas_seguranca = list(MAPA_PASTAS.values()) + ['LIMITE_PAGINAS', 'ERRO_PROCESSAMENTO', 'LOW_CONFIDENCE', 'IMAGEM_PRINT']
    
    # 3. IA apenas nos PDFs que sobraram
    for arquivo in list(pasta_ticket.rglob('*.pdf')):
        if arquivo.is_file():
            
            # Pula arquivos que já foram movidos para alguma pasta final
            if any(p in arquivo.parts for p in pastas_seguranca):
                continue
                
            try:
                doc = fitz.open(str(arquivo))
                
                # --- NOVA TRAVA: VERIFICAÇÃO DE SENHA ---
                if doc.needs_pass:
                    raise ValueError("PDF Protegido por Senha")
                
                if len(doc) > 250:
                    categoria_ia = "ignorar_tamanho"
                    destino = pasta_ticket / 'LIMITE_PAGINAS'
                    novo_nome = arquivo.name
                    doc.close()
                else:
                    texto = doc[0].get_text("text")[:2000]
                    doc.close()
                    
                    logging.info(f"Lendo [{arquivo.name}]...")
                    categoria_ia = classificar_documento_claude(texto)
                    
                    nome_pasta_final = MAPA_PASTAS.get(categoria_ia, 'LOW_CONFIDENCE')
                    destino = pasta_ticket / nome_pasta_final
                    
                    nome_limpo = arquivo.stem.replace(" ", "_")
                    novo_nome = f"{categoria_ia.upper()}_{nome_limpo}{arquivo.suffix}"
                
                destino.mkdir(exist_ok=True)
                caminho_final = obter_nome_unico(destino, novo_nome)
                shutil.move(str(arquivo), str(caminho_final))
                
                registrar_documento(id_ticket, arquivo.name, caminho_final.name, categoria_ia, destino.name, "SUCESSO")
                logging.info(f"-> {caminho_final.name}")
                
            except Exception as e:
                logging.error(f"Erro PDF {arquivo.name}: {e}")
                erro_dir = pasta_ticket / 'ERRO_PROCESSAMENTO'
                erro_dir.mkdir(exist_ok=True)
                caminho_final = obter_nome_unico(erro_dir, arquivo.name)
                shutil.move(str(arquivo), str(caminho_final))
                
                # Registra o erro no banco, limpando a mensagem feia se for de senha
                msg_erro = "PDF Protegido por Senha" if "Protegido por Senha" in str(e) else str(e)
                registrar_documento(id_ticket, arquivo.name, caminho_final.name, "ERRO", "ERRO_PROCESSAMENTO", "ERRO", msg_erro)

    limpar_pastas_vazias(pasta_ticket)
    
    # Validação final com base na quantidade que o Onvio prometeu
    if arquivos_encontrados != qtd_esperada:
        div = f"Esperava {qtd_esperada}, encontrou {arquivos_encontrados}"
        logging.warning(f"Ticket {id_ticket}: {div}")
        marcar_ticket_triado(id_ticket, "CONCLUIDO_COM_DIVERGENCIA", div)
    else:
        marcar_ticket_triado(id_ticket, "CONCLUIDO")
        logging.info(f"Ticket {id_ticket} 100% OK.")

def executar_triagem():
    logging.info("Iniciando Módulo de Triagem IA...")
    setup_banco_triagem()
    pendentes = get_tickets_pendentes()
    
    if not pendentes:
        logging.info("Nenhum ticket novo.")
        return
        
    for id_ticket, caminho_pasta, qtd_esperada in pendentes:
        if not caminho_pasta:
            marcar_ticket_triado(id_ticket, "SEM_ANEXOS")
            continue
        processar_ticket(id_ticket, caminho_pasta, qtd_esperada)

if __name__ == "__main__":
    executar_triagem()