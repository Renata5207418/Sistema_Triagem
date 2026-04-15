import os
import re
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

    def obter_cnpjs_do_grupo(self, cod_emp: str) -> list:
        """
        Descobre o CNPJ da empresa pelo cod_emp e retorna uma lista 
        contendo esse CNPJ e de todas as suas filiais (mesmo radical).
        """
        if not self.conn:
            return []
            
        cursor = self.conn.cursor()
        try:
            # 1. Pega o CNPJ da empresa dona da OS
            cursor.execute("SELECT cgce_emp FROM bethadba.geempre WHERE codi_emp = ?", (cod_emp,))
            row = cursor.fetchone()
            
            if not row or not row[0]:
                return []
                
            cnpj_original = str(row[0])
            
            # 2. Limpa e extrai o radical (8 primeiros dígitos)
            clean = re.sub(r"\D", "", cnpj_original)[:8]
            radical = clean if len(clean) >= 8 else clean
            
            # 3. Busca todos os CNPJs que começam com esse radical
            query_filiais = "SELECT cgce_emp FROM bethadba.geempre WHERE cgce_emp LIKE ?"
            cursor.execute(query_filiais, (f"{radical}%",))
            
            # Retorna uma lista de strings limpas contendo apenas os números
            cnpjs_grupo = [re.sub(r"\D", "", str(r[0])) for r in cursor.fetchall() if r[0]]
            return cnpjs_grupo
            
        except Exception as e:
            logging.error(f"Erro ao buscar grupo de CNPJs para empresa {cod_emp}: {e}")
            return []
        finally:
            cursor.close()

    def close(self):
        if self.conn:
            self.conn.close()