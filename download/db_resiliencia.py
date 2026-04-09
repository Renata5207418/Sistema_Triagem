from pathlib import Path
import sqlite3
import logging
from datetime import datetime


class ResilienciaDB:
    def __init__(self, db_path=None):
        if db_path is None:
            raiz_projeto = Path(__file__).parent.parent
            self.db_path = raiz_projeto / "banco_rpa.db"
        else:
            self.db_path = db_path
            
        self._criar_tabela()

    def _conectar(self):
        return sqlite3.connect(self.db_path)

    def _criar_tabela(self):
        with self._conectar() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS downloads (
                    id_ticket INTEGER PRIMARY KEY,
                    cod_emp TEXT,
                    nome_emp TEXT,
                    descricao TEXT,
                    status TEXT, -- SUCESSO, PENDENTE, ALERTA_HUMANO, ERRO_API
                    tentativas INTEGER DEFAULT 0,
                    ultima_tentativa TIMESTAMP,
                    erro_detalhe TEXT
                )
            """)
            try:
                conn.execute("ALTER TABLE downloads ADD COLUMN descricao TEXT")
            except sqlite3.OperationalError:
                pass

    def registrar_ou_atualizar(self, id_ticket, cod_emp, nome_emp, status, erro="", descricao=""):
        with self._conectar() as conn:
            conn.execute("""
                INSERT INTO downloads (id_ticket, cod_emp, nome_emp, descricao, status, tentativas, ultima_tentativa, erro_detalhe)
                VALUES (?, ?, ?, ?, ?, 1, ?, ?)
                ON CONFLICT(id_ticket) DO UPDATE SET
                    status = excluded.status,
                    descricao = excluded.descricao,
                    tentativas = tentativas + 1,
                    ultima_tentativa = excluded.ultima_tentativa,
                    erro_detalhe = excluded.erro_detalhe
            """, (id_ticket, cod_emp, nome_emp, descricao, status, datetime.now(), erro))

    def get_ticket_status(self, id_ticket):
        with self._conectar() as conn:
            res = conn.execute("SELECT status, tentativas FROM downloads WHERE id_ticket = ?", (id_ticket,)).fetchone()
            return res if res else (None, 0)

    def detectar_gaps(self, limite_retroativo=100):
        """Encontra números de tickets que faltam entre o menor e maior ID do banco."""
        with self._conectar() as conn:
            res = conn.execute("SELECT MIN(id_ticket), MAX(id_ticket) FROM downloads").fetchone()
            if not res or not res[0]: return []
            
            menor, maior = res
            inicio = max(menor, maior - limite_retroativo)
            
            todos_sequenciais = set(range(inicio, maior + 1))
            existentes = set(row[0] for row in conn.execute("SELECT id_ticket FROM downloads WHERE id_ticket >= ?", (inicio,)))
            
            return list(todos_sequenciais - existentes)

    def get_pendentes_para_retry(self, max_tentativas=10):
        with self._conectar() as conn:
            cursor = conn.execute("""
                SELECT id_ticket FROM downloads 
                WHERE (status IN ('PENDENTE', 'ERRO_API')) 
                AND tentativas < ?
            """, (max_tentativas,))
            return [row[0] for row in cursor.fetchall()]
        