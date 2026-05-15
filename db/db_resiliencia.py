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
        self.popular_checklist_inicial()

    def _conectar(self):
        return sqlite3.connect(self.db_path, timeout=15.0)

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
            # Migração da coluna de OS na malha
            try: conn.execute("ALTER TABLE malha_fiscal_tomadas ADD COLUMN os_onvio TEXT")
            except sqlite3.OperationalError: pass

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
                    codigo TEXT, 
                    apelido TEXT UNIQUE,
                    tipo TEXT DEFAULT 'VITALICIA',
                    ativa INTEGER DEFAULT 1,
                    competencia_unica TEXT,
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
            # 10. CHECKLIST DO DASHBOARD (Painel Executivo)
            # ==========================================
            conn.execute("""
                CREATE TABLE IF NOT EXISTS dashboard_checklist (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tarefa_nome TEXT UNIQUE,
                    tipo TEXT, -- 'AUTO' ou 'MANUAL'
                    termo_gestta TEXT, -- Ex: 'ISS PRESTADOS'
                    dia_vencimento INTEGER, -- Ex: 10
                    status_manual INTEGER DEFAULT 0, -- 0 pendente, 1 concluído
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # --- MUDANÇA: Adicionando a coluna 'ativa' para o Soft Delete ---
            try: conn.execute("ALTER TABLE dashboard_checklist ADD COLUMN ativa INTEGER DEFAULT 1")
            except sqlite3.OperationalError: pass
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS checklist_mes (
                    id_tarefa INTEGER, 
                    competencia TEXT, 
                    status_manual INTEGER DEFAULT 0, 
                    usuario_conclusao TEXT, 
                    data_conclusao TEXT, 
                    PRIMARY KEY (id_tarefa, competencia)
                )
            """)
            try: conn.execute("ALTER TABLE checklist_mes ADD COLUMN usuario_conclusao TEXT")
            except sqlite3.OperationalError: pass
            try: conn.execute("ALTER TABLE checklist_mes ADD COLUMN data_conclusao TEXT")
            except sqlite3.OperationalError: pass

            # ==========================================
            # 11. ÍNDICES DE PERFORMANCE (VELOCIDADE MÁXIMA)
            # ==========================================
            # Cria os índices para evitar "Full Table Scans" nas consultas pesadas
            conn.execute("CREATE INDEX IF NOT EXISTS idx_doc_triados_ticket ON documentos_triados(id_ticket)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_downloads_data ON downloads(ultima_tentativa)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_malha_competencia ON malha_fiscal_tomadas(competencia)")

    def popular_checklist_inicial(self):
        # 1. Tarefas Automáticas (Gestta)
        tarefas_auto = [
            ('ISS FIXO', 'AUTO', 'ISS FIXO', None),
            ('ISS RPA(10)', 'AUTO', 'ISS RPA(10)', None),
            ('ISS RPA(15)', 'AUTO', 'ISS RPA(15)', None),
            ('ISS RPA(20)', 'AUTO', 'ISS RPA(20)', None),
            ('ISS PRESTADOS(03)', 'AUTO', 'ISS PRESTADOS(03)', None),
            ('ISS PRESTADOS(08)', 'AUTO', 'ISS PRESTADOS(08)', None),
            ('ISS PRESTADOS(10)', 'AUTO', 'ISS PRESTADOS(10)', None),
            ('ISS PRESTADOS(15)', 'AUTO', 'ISS PRESTADOS(15)', None),
            ('ISS PRESTADOS(20)', 'AUTO', 'ISS PRESTADOS(20)', None),
            ('ISS RETIDO(10)', 'AUTO', 'ISS RETIDO(10)', None),
            ('ISS RETIDO(15)', 'AUTO', 'ISS RETIDO(15)', None),
            ('ISS RETIDO(20)', 'AUTO', 'ISS RETIDO(20)', None),
            ('IRRF 3208|ALUGUEL', 'AUTO', 'IRRF 3208|ALUGUEL', None),
            ('REINF PRESTADOS', 'AUTO', 'REINF PRESTADOS', None),
            ('IMPORTAÇÃO|SCRYTA', 'AUTO', 'IMPORTAÇÃO|SCRYTA', None),
            ('CONTROLE FATOR R', 'AUTO', 'CONTROLE FATOR R', None),
            ('CONTROLE TRIAGEM|RETENÇÕES', 'AUTO', 'CONTROLE TRIAGEM|RETENÇÕES', None),
            ('ENCERRAMENTO COMPETÊNCIA ISS', 'AUTO', 'ENCERRAMENTO COMPETÊNCIA ISS', None),
            ('SINTEGRA(SC)', 'AUTO', 'SINTEGRA(SC)', None),
            ('FATURAMENTO PARA HONORÁRIO', 'AUTO', 'FATURAMENTO PARA HONORÁRIO', None),
        ]

        # 2. Tarefas Manuais 
        tarefas_manuais = [
            ('Inicio da entrega de empresas com Prioridade Contabil', 'MANUAL', None, None),
            ('Baixa dos documentos nos sistemas - CONTA AZUL | OMIE', 'MANUAL', None, None),
            ('Envio Reinf prestados', 'MANUAL', None, None),
            ('Envio antecipado DCTFWEB - Esquadra | Talogy | LW', 'MANUAL', None, None),
            ('Revisão e envio Retenção', 'MANUAL', None, None),
            ('Aviso ao clientes sobre as guias não visualizadas DAS', 'MANUAL', None, None), 
            ('Aviso ao clientes sobre as guias não visualizadas PIS|COFINS', 'MANUAL', None, None),
            ('Notas SCRYTA Rotina automatica', 'MANUAL', None, None), 
            ('Agendamento de coletas', 'MANUAL', None, None)
        ]

        # ---LIMPEZA DO BANCO ---
        nomes_validos = [t[0] for t in tarefas_auto]
        placeholders = ','.join(['?'] * len(nomes_validos))
        try:
            self.executar_update(
                f"DELETE FROM dashboard_checklist WHERE tipo = 'AUTO' AND tarefa_nome NOT IN ({placeholders})",
                tuple(nomes_validos)
            )
        except Exception as e:
            logging.error(f"Erro ao limpar tarefas antigas: {e}")

        tarefas_totais = tarefas_auto + tarefas_manuais
        for nome, tipo, termo, dia in tarefas_totais: 
            try:
                self.executar_update(
                    "INSERT OR IGNORE INTO dashboard_checklist (tarefa_nome, tipo, termo_gestta, dia_vencimento) VALUES (?, ?, ?, ?)", 
                    (nome, tipo, termo, dia)
                )
            except Exception:
                pass

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
        
        if destino == 'NOTAS_DE_SERVICO/TOMADAS' or destino == 'NOTAS_DE_SERVICO\\TOMADAS':
            status_tomados_inicial = 'PENDENTE'
        else:
            status_tomados_inicial = 'IGNORADO_NAO_E_TOMADO'

        self.executar_update("""
            INSERT INTO documentos_triados 
            (id_ticket, nome_original, nome_final, categoria_ia, pasta_destino, status, motivo_erro, data_processamento, texto_extraido, status_tomados)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (id_ticket, original, final, categoria, destino, status, erro, agora, texto_extraido, status_tomados_inicial))

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
        garantindo que o ticket inteiro já finalizou a triagem.

        Também retorna cod_empresa e competencia para permitir a primeira
        sincronização automática da malha fiscal com a AWS.
        """
        query = """
            SELECT 
                d.id AS id_documento, 
                d.id_ticket, 
                d.nome_final, 
                d.pasta_destino, 
                d.texto_extraido,
                down.caminho_pasta AS pasta_raiz_ticket,
                TRIM(CAST(down.cod_emp AS TEXT)) AS cod_empresa,
                strftime('%Y-%m', down.ultima_tentativa) AS competencia
            FROM documentos_triados d
            INNER JOIN tickets_triados t 
                ON d.id_ticket = t.id_ticket
            INNER JOIN downloads down 
                ON d.id_ticket = down.id_ticket
            WHERE d.categoria_ia = 'nota_servico' 
            AND d.pasta_destino = 'NOTAS_DE_SERVICO/TOMADAS'
            AND d.status_tomados = 'PENDENTE'
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
    # MÉTODOS DA MALHA FISCAL TOMADAS
    # ==========================================
    def malha_ja_sincronizada(self, cod_empresa, competencia):
        """
        Verifica se já existe consulta AWS salva para a empresa/competência.
        Usado para garantir a primeira consulta automática sem repetir.
        """
        rows = self.executar_query_dict("""
            SELECT id
            FROM malha_fiscal_tomadas
            WHERE TRIM(CAST(cod_empresa AS TEXT)) = ?
              AND competencia = ?
            LIMIT 1
        """, (str(cod_empresa).strip(), competencia))

        return len(rows) > 0

    def get_ultima_atualizacao_malha(self, cod_empresa, competencia):
        """
        Retorna a última data/hora em que a AWS foi consultada para essa empresa/competência.
        """
        rows = self.executar_query_dict("""
            SELECT MAX(data_atualizacao) AS ultima_atualizacao
            FROM malha_fiscal_tomadas
            WHERE TRIM(CAST(cod_empresa AS TEXT)) = ?
              AND competencia = ?
        """, (str(cod_empresa).strip(), competencia))

        if not rows:
            return None

        return rows[0].get("ultima_atualizacao")

    def limpar_malha_empresa_competencia(self, cod_empresa, competencia):
        """
        Limpa os dados antigos antes de uma nova sincronização AWS.
        """
        self.executar_update("""
            DELETE FROM malha_fiscal_tomadas
            WHERE TRIM(CAST(cod_empresa AS TEXT)) = ?
              AND competencia = ?
        """, (str(cod_empresa).strip(), competencia))

    def inserir_nota_malha(
        self,
        cod_empresa,
        competencia,
        numero_nota,
        cnpj_prestador,
        valor_nota,
        status_conciliacao,
        origem,
        data_atualizacao=None
    ):
        """
        Insere uma nota na malha fiscal local.
        """
        if data_atualizacao is None:
            data_atualizacao = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        self.executar_update("""
            INSERT INTO malha_fiscal_tomadas (
                cod_empresa,
                competencia,
                numero_nota,
                cnpj_prestador,
                origem,
                valor_nota,
                status_conciliacao,
                data_atualizacao
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(cod_empresa).strip(),
            competencia,
            numero_nota,
            cnpj_prestador,
            origem,
            valor_nota,
            status_conciliacao,
            data_atualizacao
        ))

    def buscar_resultado_tomado_para_malha(self, cod_empresa, numero_nota, cnpj_prestador):
        """
        Verifica se uma nota encontrada na AWS existe nos resultados processados pelo Tomados.
        """
        return self.executar_query_dict("""
            SELECT valor_contabil
            FROM resultados_tomados
            WHERE numero_documento = ?
              AND cpf_cnpj = ?
              AND id_ticket IN (
                  SELECT id_ticket
                  FROM downloads
                  WHERE TRIM(CAST(cod_emp AS TEXT)) = ?
              )
        """, (
            numero_nota,
            cnpj_prestador,
            str(cod_empresa).strip()
        ))

    def listar_tomados_empresa_competencia(self, cod_empresa, competencia):
        """
        Lista notas processadas pelo Tomados para a empresa/competência.
        Garante que a origem do documento era NOTAS_DE_SERVICO/TOMADAS.
        """
        return self.executar_query_dict("""
            SELECT 
                r.numero_documento, 
                r.cpf_cnpj, 
                r.valor_contabil
            FROM resultados_tomados r
            INNER JOIN downloads d
                ON r.id_ticket = d.id_ticket
            INNER JOIN documentos_triados dt
                ON r.id_documento = dt.id
            WHERE TRIM(CAST(d.cod_emp AS TEXT)) = ?
            AND dt.categoria_ia = 'nota_servico'
            AND dt.pasta_destino = 'NOTAS_DE_SERVICO/TOMADAS'
            AND (
                strftime('%Y-%m', d.ultima_tentativa) = ?
                OR substr(CAST(d.ultima_tentativa AS TEXT), 1, 7) = ?
                OR CAST(d.ultima_tentativa AS TEXT) LIKE ? || '%'
            )
        """, (
            str(cod_empresa).strip(),
            competencia,
            competencia,
            competencia
        ))

    def nota_malha_existe(self, cod_empresa, competencia, numero_nota, cnpj_prestador):
        """
        Verifica se determinada nota já existe na malha fiscal.
        """
        rows = self.executar_query_dict("""
            SELECT id
            FROM malha_fiscal_tomadas
            WHERE TRIM(CAST(cod_empresa AS TEXT)) = ?
              AND competencia = ?
              AND numero_nota = ?
              AND cnpj_prestador = ?
            LIMIT 1
        """, (
            str(cod_empresa).strip(),
            competencia,
            numero_nota,
            cnpj_prestador
        ))

        return len(rows) > 0  

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
