import time
import logging
from triagem.main import executar_triagem

while True:
    try:        
        executar_triagem()
    except Exception as e:
        logging.error(f"Erro na Triagem: {e}")
    
    time.sleep(120) # Dorme só 2 min