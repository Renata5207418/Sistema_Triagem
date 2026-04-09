import time
import logging
from download.main import executar_download

# Configura o log do orquestrador
logging.basicConfig(
    level=logging.INFO, 
    format="%(asctime)s [ORQUESTRADOR] %(message)s", 
    datefmt="%H:%M:%S"
)

def rodar_robo_continuamente(intervalo_minutos=15):
    """Roda a esteira completa a cada X minutos."""
    
    segundos = intervalo_minutos * 60
    
    logging.info("Iniciando o Orquestrador do Sistema de Triagem...")
    
    while True:
        logging.info("==================================================")
        logging.info("INICIANDO NOVA VARREDURA")
        logging.info("==================================================")
        
        try:
            # 1. ETAPA DE DOWNLOAD
            logging.info("Chamando módulo de Download...")
            executar_download()
            
            # 2. ETAPA DE TRIAGEM (No futuro)
            # logging.info("Chamando módulo de Triagem...")
            # executar_triagem()
            
            # 3. ETAPA DE TOMADOS (No futuro)
            # logging.info("Chamando módulo de Lançamento...")
            # executar_lancamento()
            
        except Exception as e:
            logging.error(f"Erro crítico na esteira: {e}")
            
        logging.info(f"Varredura concluída. O robô vai dormir por {intervalo_minutos} minutos...")
        time.sleep(segundos)

if __name__ == "__main__":
    rodar_robo_continuamente(intervalo_minutos=10)