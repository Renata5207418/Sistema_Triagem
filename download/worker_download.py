import time
import logging
from download.main import executar_download

while True:
    try:
        executar_download()
    except Exception as e:
        logging.error(f"Erro no Download: {e}")
    
    # Dorme 10 min, independentemente do que a Triagem está fazendo
    time.sleep(600)