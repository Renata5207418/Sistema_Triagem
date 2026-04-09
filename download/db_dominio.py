import os
import pyodbc
import logging
from pathlib import Path
from dotenv import load_dotenv


caminho_env = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=caminho_env)


class DatabaseConnection:
    def __init__(self):
        self.host = os.getenv("DOMINIO_HOST")
        self.port = os.getenv("DOMINIO_PORT", "2638")
        self.dbname = os.getenv("DOMINIO_DB")
        self.user = os.getenv("DOMINIO_USER")
        self.password = os.getenv("DOMINIO_PASSWORD")

        tcpip_host = "dominio.scryta" if self.host == "dominio" else self.host
        
        self.conn_str = (
            "DRIVER=SQL Anywhere 17;"
            f"UID={self.user};"
            f"PWD={self.password};"
            f"ENG=dominio;"
            f"DBN={self.dbname};"
            f"LINKS=TCPIP(host={tcpip_host}:{self.port});"
        )
        self.conn = None

    def connect(self):
        try:
            self.conn = pyodbc.connect(self.conn_str)
            return True
        except Exception as e:
            logging.error(f"Erro ao conectar na Domínio: {e}")
            return False

    def get_mapeamento_empresas(self):
        """Busca código, nome e apelido das empresas para um mapeamento mais preciso."""
        query = "SELECT codi_emp, nome_emp, apel_emp FROM bethadba.geempre"
        cursor = self.conn.cursor()
        mapeamento = {}
        try:
            logging.info("Consultando empresas e apelidos na Domínio...")
            cursor.execute(query)
            for row in cursor.fetchall():
                codigo = str(row[0])
                nome_completo = str(row[1]).strip().upper() if row[1] else ""
                apelido = str(row[2]).strip().upper() if row[2] else None
                
                # Ambos apontam para o mesmo código
                if nome_completo and len(nome_completo) > 2:
                    mapeamento[nome_completo] = codigo
                if apelido and len(apelido) > 2:
                    mapeamento[apelido] = codigo
                    
            return mapeamento
        except Exception as e:
            logging.error(f"Erro ao listar empresas: {e}")
            return {}
        finally:
            cursor.close()

    def close(self):
        if self.conn:
            self.conn.close()
