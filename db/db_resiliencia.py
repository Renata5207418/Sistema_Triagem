from pathlib import Path
import sqlite3
import logging
from datetime import datetime

class ResilienciaDB:
    def __init__(self, db_path=None):
        if db_path is None:
            # Garante que aponta para a raiz do projeto (SISTEMA_TRIAGEM/banco_rpa.db)
            raiz_projeto = Path(__file__).parent.parent
            self.db_path = raiz_projeto / "banco_rpa.db"
        else:
            self.db_path = db_path
            
        self._criar_tabelas()

    def _conectar(self):
        return sqlite3.connect(self.db_path)

    def _criar_tabelas(self):
        """Cria todas as tabelas necessárias para o ecossistema RPA."""
        with self._conectar() as conn:
            
            # ==========================================
            # 1. TABELA DE DOWNLOADS (A "Capa" da OS)
            # ==========================================
            conn.execute("""
                CREATE TABLE IF NOT EXISTS downloads (
                    id_ticket INTEGER PRIMARY KEY,
                    cod_emp TEXT,
                    nome_emp TEXT,                    
                    status TEXT,
                    caminho_pasta TEXT,            
                    qtd_anexos_esperados INTEGER,  
                    tentativas INTEGER DEFAULT 0,
                    ultima_tentativa TIMESTAMP,
                    erro_detalhe TEXT,
                    verificado INTEGER DEFAULT 0,
                    auditado_por TEXT,
                    data_auditoria TEXT
                )                
            """)
            
            # Ajustes na tabela de downloads (caso seja um banco antigo)
            colunas_novas_down = [
                "ADD COLUMN descricao TEXT",
                "ADD COLUMN caminho_pasta TEXT",
                "ADD COLUMN qtd_anexos_esperados INTEGER",
                "ADD COLUMN auditado_por TEXT",
                "ADD COLUMN data_auditoria TEXT"
            ]
            for alteracao in colunas_novas_down:
                try: conn.execute(f"ALTER TABLE downloads {alteracao}")
                except sqlite3.OperationalError: pass

            # ==========================================
            # 2. TABELAS DA TRIAGEM (Rastreabilidade e IA)
            # ==========================================
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
                    data_processamento TEXT,
                    texto_extraido TEXT,
                    status_tomados TEXT DEFAULT 'PENDENTE',
                    FOREIGN KEY(id_ticket) REFERENCES downloads(id_ticket)
                )
            """)
            
            # Ajustes para bancos antigos da triagem
            colunas_triados = [
                "ADD COLUMN texto_extraido TEXT",
                "ADD COLUMN status_tomados TEXT DEFAULT 'PENDENTE'"
            ]
            for alt in colunas_triados:
                try: conn.execute(f"ALTER TABLE documentos_triados {alt}")
                except sqlite3.OperationalError: pass

            conn.execute("""
                CREATE TABLE IF NOT EXISTS tickets_triados (
                    id_ticket INTEGER PRIMARY KEY,
                    status_triagem TEXT,
                    divergencia TEXT,
                    data_conclusao TEXT,
                    FOREIGN KEY(id_ticket) REFERENCES downloads(id_ticket)
                )
            """)

            # ==========================================
            # 3. TABELA DE CACHE (ReceitaWS / Domínio)
            # ==========================================
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cache_fornecedores (
                    cnpj TEXT PRIMARY KEY,
                    razao_social TEXT,
                    uf TEXT,
                    municipio TEXT,
                    cnae TEXT,
                    data_ultima_consulta TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # ==========================================
            # 4. TABELA DE RESULTADOS TOMADOS (Layout Domínio)
            # ==========================================
            conn.execute("""
                CREATE TABLE IF NOT EXISTS resultados_tomados (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    id_ticket INTEGER,           
                    id_documento INTEGER,        
                    
                    -- Campos extraídos (na ordem do layout esperado)
                    cpf_cnpj TEXT,
                    razao_social TEXT,
                    uf TEXT,
                    municipio TEXT,
                    endereco TEXT,
                    numero_documento TEXT,
                    serie TEXT,
                    data_emissao TEXT,
                    situacao TEXT,
                    acumulador TEXT,
                    cfop TEXT,
                    valor_servicos TEXT,
                    valor_descontos TEXT,
                    valor_contabil TEXT,
                    base_calculo TEXT,
                    aliquota_iss TEXT,
                    valor_iss_normal TEXT,
                    valor_iss_retido TEXT,
                    valor_irrf TEXT,
                    valor_pis TEXT,
                    valor_cofins TEXT,
                    valor_csll TEXT,
                    valor_crf TEXT,
                    valor_inss TEXT,
                    codigo_item TEXT,
                    quantidade TEXT,
                    valor_unitario TEXT,
                    tomador TEXT,
                    
                    data_processamento TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(id_ticket) REFERENCES downloads(id_ticket),
                    FOREIGN KEY(id_documento) REFERENCES documentos_triados(id)
                )
            """)

            # ==========================================
            # 5. TABELA DE USUÁRIOS (Autenticação)
            # ==========================================
            conn.execute("""
                CREATE TABLE IF NOT EXISTS usuarios (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    full_name TEXT,
                    hashed_password TEXT NOT NULL,
                    is_active INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # ==========================================
            # 6. TABELA DE MALHA FISCAL (Conciliação AWS vs TriaBot)
            # ==========================================
            conn.execute("""
                CREATE TABLE IF NOT EXISTS malha_fiscal_tomadas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cod_empresa TEXT,
                    competencia TEXT,
                    numero_nota TEXT,
                    cnpj_prestador TEXT,
                    origem TEXT, -- 'AWS', 'TRIABOT', 'AMBOS'
                    valor_nota REAL,
                    status_conciliacao TEXT, -- 'BATEU', 'FALTA_NO_TRIABOT', 'DIVERGENCIA_VALOR'
                    data_atualizacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # ==========================================
            # 7. TABELAS DE FECHAMENTO CONTÁBIL 
            # ==========================================
            conn.execute("""
                CREATE TABLE IF NOT EXISTS controle_pastas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    apelido TEXT,
                    competencia TEXT,
                    pasta_liberada_em TEXT,
                    documentos_json TEXT,
                    updated_at TEXT
                )
            """)

            # ==========================================
            # 8. CONFIGURAÇÃO DE EMPRESAS 
            # ==========================================
            conn.execute("""
                CREATE TABLE IF NOT EXISTS empresas_config (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    apelido TEXT UNIQUE,
                    tipo TEXT DEFAULT 'VITALICIA', -- 'VITALICIA' ou 'MENSAL'
                    ativa INTEGER DEFAULT 1,       -- 1 para Ativa, 0 para Inativa
                    competencia_unica TEXT,        -- Se for MENSAL, guarda qual mês (Ex: 2026-04)
                    criada_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # ==========================================
            # 9. TABELAS DE VALIDAÇÃO DA MALHA 
            # ==========================================
            conn.execute("""
                CREATE TABLE IF NOT EXISTS malha_fiscal_validacao (
                    cod_empresa TEXT,
                    competencia TEXT,
                    verificado INTEGER DEFAULT 0,
                    auditado_por TEXT,
                    data_auditoria TEXT,
                    PRIMARY KEY (cod_empresa, competencia)
                )
            """)

    # ==========================================
    # MÉTODOS DE USUÁRIOS E AUTENTICAÇÃO
    # ==========================================
    def get_user_by_username(self, username):
        with self._conectar() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM usuarios WHERE username = ?", (username,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_user_by_email(self, email):
        with self._conectar() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM usuarios WHERE email = ?", (email,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def insert_user(self, username, email, full_name, hashed_password):
        with self._conectar() as conn:
            cursor = conn.execute("""
                INSERT INTO usuarios (username, email, full_name, hashed_password)
                VALUES (?, ?, ?, ?)
            """, (username, email, full_name, hashed_password))
            conn.commit()
            return cursor.lastrowid
            
    def update_password(self, username, new_hashed_password):
         with self._conectar() as conn:
            conn.execute("UPDATE usuarios SET hashed_password = ? WHERE username = ?", (new_hashed_password, username))
            conn.commit()       


    # ==========================================
    # MÉTODOS DE DOWNLOAD
    # ==========================================
    def registrar_ou_atualizar(self, id_ticket, cod_emp, nome_emp, status, caminho_pasta, qtd_anexos, erro=""):
        with self._conectar() as conn:
            conn.execute("""
                INSERT INTO downloads (id_ticket, cod_emp, nome_emp, status, caminho_pasta, qtd_anexos_esperados, tentativas, ultima_tentativa, erro_detalhe, verificado)
                VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, 0)
                ON CONFLICT(id_ticket) DO UPDATE SET
                    status = excluded.status,
                    caminho_pasta = excluded.caminho_pasta,
                    qtd_anexos_esperados = excluded.qtd_anexos_esperados,
                    ultima_tentativa = excluded.ultima_tentativa
            """, (id_ticket, cod_emp, nome_emp, status, str(caminho_pasta), qtd_anexos, datetime.now(), erro))

    def marcar_como_verificado(self, id_ticket):
        """Método para a API usar quando o usuário der o check no front-end."""
        self.executar_update("UPDATE downloads SET verificado = 1 WHERE id_ticket = ?", (id_ticket,))

    def desmarcar_verificado(self, id_ticket):
        """Caso o usuário queira voltar o ticket para pendente."""
        self.executar_update("UPDATE downloads SET verificado = 0 WHERE id_ticket = ?", (id_ticket,))

    def get_ticket_status(self, id_ticket):
        with self._conectar() as conn:
            res = conn.execute("SELECT status, tentativas FROM downloads WHERE id_ticket = ?", (id_ticket,)).fetchone()
            return res if res else (None, 0)

    def detectar_gaps(self, limite_retroativo=100):
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

    # ==========================================
    # MÉTODOS DA TRIAGEM
    # ==========================================
    def registrar_documento_triado(self, id_ticket, original, final, categoria, destino, status, erro="", texto_extraido=None):
        agora = datetime.now().isoformat()
        self.executar_update("""
            INSERT INTO documentos_triados 
            (id_ticket, nome_original, nome_final, categoria_ia, pasta_destino, status, motivo_erro, data_processamento, texto_extraido)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (id_ticket, original, final, categoria, destino, status, erro, agora, texto_extraido))

    def marcar_ticket_triado(self, id_ticket, status, divergencia=""):
        agora = datetime.now().isoformat()
        self.executar_update("""
            INSERT OR REPLACE INTO tickets_triados (id_ticket, status_triagem, divergencia, data_conclusao)
            VALUES (?, ?, ?, ?)
        """, (id_ticket, status, divergencia, agora))

    def get_tickets_pendentes_triagem(self):
        query = """
            SELECT d.id_ticket, d.caminho_pasta, d.qtd_anexos_esperados, d.cod_emp 
            FROM downloads d
            LEFT JOIN tickets_triados t ON d.id_ticket = t.id_ticket
            WHERE d.status = 'SUCESSO' AND t.id_ticket IS NULL
            ORDER BY d.id_ticket ASC
        """
        return self.executar_query_dict(query)

    # ==========================================
    # MÉTODOS DO MÓDULO TOMADOS (EXTRAÇÃO)
    # ==========================================
    def get_documentos_pendentes_tomados(self, limite=50):
        """
        Puxa documentos de notas de serviço que ainda não foram extraídos,
        GARANTINDO que o ticket inteiro já finalizou a triagem (Trava de Corrida).
        """
        query = """
            SELECT 
                d.id AS id_documento, 
                d.id_ticket, 
                d.nome_final, 
                d.pasta_destino, 
                d.texto_extraido,
                down.caminho_pasta AS pasta_raiz_ticket
            FROM documentos_triados d
            INNER JOIN tickets_triados t ON d.id_ticket = t.id_ticket
            INNER JOIN downloads down ON d.id_ticket = down.id_ticket
            WHERE d.categoria_ia = 'nota_servico' 
              AND d.status_tomados = 'PENDENTE'
              AND t.status_triagem = 'CONCLUIDO'
            ORDER BY d.id ASC
            LIMIT ?
        """
        return self.executar_query_dict(query, (limite,))

    def atualizar_status_tomados(self, id_documento, status_novo):
        """Atualiza a flag de controle após a IA extrair os dados da nota."""
        self.executar_update(
            "UPDATE documentos_triados SET status_tomados = ? WHERE id = ?",
            (status_novo, id_documento)
        )

    # ==========================================
    # MÉTODOS GENÉRICOS (Úteis para API e Workers)
    # ==========================================
    def executar_query_dict(self, query, params=()):
        """Executa um SELECT e retorna lista de dicionários."""
        with self._conectar() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def executar_update(self, query, params=()):
        """Executa INSERT/UPDATE/DELETE."""
        with self._conectar() as conn:
            conn.execute(query, params)
            conn.commit()

db = ResilienciaDB()
