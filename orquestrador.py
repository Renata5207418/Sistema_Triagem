import multiprocessing
import time
import logging
import sys
from pathlib import Path

pasta_raiz = str(Path(__file__).parent)
if pasta_raiz not in sys.path:
    sys.path.append(pasta_raiz)

from download.main import executar_download
from triagem.main import executar_triagem
from tomados.main import executar_tomados 

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")

# ==========================================
# LOOPS INDIVIDUAIS DE CADA ROBÔ
# ==========================================
def worker_download():
    """Busca novas solicitações a cada 1 hora."""
    while True:
        try:
            logging.info("[DOWNLOAD] Iniciando ciclo de busca no Onvio...")
            executar_download()
        except Exception as e:
            logging.error(f"[DOWNLOAD] Erro crítico: {e}")
        
        logging.info("[DOWNLOAD] Fila concluída. Dormindo por 1 hora...")
        time.sleep(3600)

def worker_triagem():
    """Pergunta ao banco se existem novos downloads a cada 2 minutos."""
    while True:
        try:
            executar_triagem()
        except Exception as e:
            logging.error(f"[TRIAGEM] Erro crítico: {e}")
        
        time.sleep(120)

def worker_tomados():
    """Pergunta ao banco se a triagem liberou novos lotes."""
    while True:
        try:
            processados = executar_tomados()
            
            if processados == 0:
                time.sleep(30) 
            else:
                time.sleep(5)  
        except Exception as e:
            logging.error(f"[TOMADOS] Erro crítico: {e}")
            time.sleep(60)

# ==========================================
# O CHEFE (ORQUESTRADOR CENTRAL)
# ==========================================
if __name__ == "__main__":
    logging.info("=== INICIANDO ORQUESTRADOR CENTRAL RPA ===")

    # Cria os processos separados na memória
    p_download = multiprocessing.Process(target=worker_download, name="Processo-Download")
    p_triagem = multiprocessing.Process(target=worker_triagem, name="Processo-Triagem")
    p_tomados = multiprocessing.Process(target=worker_tomados, name="Processo-Tomados")

    # Dá o 'play' nos 3 ao mesmo tempo
    p_download.start()
    p_triagem.start()
    p_tomados.start()

    # Mantém este terminal principal aberto escutando os robôs
    try:
        p_download.join()
        p_triagem.join()
        p_tomados.join()
    except KeyboardInterrupt:
        # Encerramento gracioso no CTRL+C
        logging.info("Encerrando todos os robôs de forma segura...")
        p_download.terminate()
        p_triagem.terminate()
        p_tomados.terminate()
        logging.info("Sistema finalizado.")