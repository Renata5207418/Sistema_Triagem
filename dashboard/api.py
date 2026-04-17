import os
import re
import io
import sys
import json
import sqlite3
import zipfile
import pandas as pd
from pathlib import Path
from datetime import datetime
from fastapi.responses import StreamingResponse
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from aws_service import buscar_xmls_aws

RAIZ_PROJETO = Path(__file__).parent.parent
sys.path.append(str(RAIZ_PROJETO))

from auth import auth
from db.db_dominio import DatabaseConnection

# --- CONFIGURAÇÕES ---
app = FastAPI(title="API Triagem Cloud", description="Backend para o Dashboard RPA")

# Permite que o frontend (React) converse com esta API sem bloqueios de CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)

RAIZ_PROJETO = Path(__file__).parent.parent
DB_PATH = RAIZ_PROJETO / "banco_rpa.db"

# --- MODELO PARA RECEBER O USUÁRIO ---
class VerificacaoRequest(BaseModel):
    usuario: str

# --- MODELOS DE DADOS (Para validação do que entra na API) ---
class SenhaRequest(BaseModel):
    senha: str


class AtualizarCategoriaRequest(BaseModel):
    nova_categoria: str


# --- FUNÇÕES DE BANCO DE DADOS ---
def executar_query_dict(query, params=()):
    """Executa uma query e retorna os resultados como uma lista de dicionários (pronto para JSON)."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row # Retorna as colunas com os nomes
        cursor = conn.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def executar_update(query, params=()):
    """Executa queries de atualização (INSERT, UPDATE)."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(query, params)
        conn.commit()


# ==========================================
# ROTAS DA API
# ==========================================
@app.get("/api/download/tomados/{os_id}")
def baixar_tomados_zip(os_id: int):
    """Gera ZIP apenas com os CSVs de importação (Geral e por Tomador)."""
    
    # 1. Busca os registros processados no banco
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        registros = [dict(r) for r in conn.execute("SELECT * FROM resultados_tomados WHERE id_ticket = ?", (os_id,)).fetchall()]

    if not registros:
        raise HTTPException(status_code=404, detail="Nenhum dado encontrado.")

    # 2. Prepara o DataFrame para garantir as 28 colunas da Domínio
    df = pd.DataFrame(registros)
    colunas_dominio = [
        'cpf_cnpj', 'razao_social', 'uf', 'municipio', 'endereco', 'numero_documento', 
        'serie', 'data_emissao', 'situacao', 'acumulador', 'cfop', 'valor_servicos', 
        'valor_descontos', 'valor_contabil', 'base_calculo', 'alq_iss', 'valor_iss_normal', 
        'valor_iss_retido', 'valor_irrf', 'valor_pis', 'valor_cofins', 'valor_csll', 
        'valor_crf', 'valor_inss', 'cod_item', 'quantidade', 'vlr_unitario', 'tomador'
    ]
    
    for col in colunas_dominio:
        if col not in df.columns: df[col] = ''
    
    df = df[colunas_dominio]
    df['situacao'] = '0' # Padrão regular
    
    # 3. Formatação técnica para Excel/Domínio (UTF-8 com assinatura e ponto-e-vírgula)
    df_csv = df.copy()
    df_csv['cpf_cnpj'] = df_csv['cpf_cnpj'].apply(lambda x: f'="{x}"') # Evita notação científica
    df_csv['tomador'] = df_csv['tomador'].apply(lambda x: f'="{x}"')
    
    colunas_valores = ['valor_servicos', 'valor_contabil', 'base_calculo', 'valor_irrf', 'valor_pis', 'valor_cofins', 'valor_csll', 'valor_crf', 'valor_inss']
    for col in colunas_valores:
        df_csv[col] = df_csv[col].apply(lambda x: str(x).replace('.', ',')) # Padrão decimal BR

    header_pt = ['CPF/CNPJ', 'Razão Social', 'UF', 'Município', 'Endereço', 'Número Documento', 'Série', 'Data', 'Situação', 'Acumulador', 'CFOP', 'Valor Serviços', 'Valor Descontos', 'Valor Contábil', 'Base de Calculo', 'Alíquota ISS', 'Valor ISS Normal', 'Valor ISS Retido', 'Valor IRRF', 'Valor PIS', 'Valor COFINS', 'Valor CSLL', 'Valo CRF', 'Valor INSS', 'Código do Item', 'Quantidade', 'Valor Unitário', 'Tomador']

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
        
        # --- GERAL.csv (Contém todas as notas da OS) ---
        csv_geral = df_csv.to_csv(index=False, sep=';', header=header_pt, encoding='utf-8-sig')
        zipf.writestr("GERAL_IMPORTACAO.csv", csv_geral)

        # --- CSVs Individuais (Um arquivo para cada tomador diferente na OS) ---
        for tomador, group in df_csv.groupby('tomador'):
            cnpj_clean = re.sub(r'[^0-9]', '', tomador)
            csv_indiv = group.to_csv(index=False, sep=';', header=header_pt, encoding='utf-8-sig')
            zipf.writestr(f"TOMADOS_CLI_{cnpj_clean}.csv", csv_indiv)

    zip_buffer.seek(0)
    return StreamingResponse(zip_buffer, media_type="application/zip", 
                             headers={"Content-Disposition": f"attachment; filename=OS{os_id}_Planilhas_Domínio.zip"})


@app.get("/api/resumo")
def get_resumo_dashboard():
    """Retorna as métricas principais para o topo do Dashboard."""
    try:
        total_downloads = executar_query_dict("SELECT COUNT(*) as total FROM downloads")[0]['total']
        
        # Pega estatísticas da triagem
        stats_triagem = executar_query_dict("""
            SELECT status, COUNT(*) as qtd 
            FROM documentos_triados 
            GROUP BY status
        """)
        
        # Formata para facilitar a vida do frontend
        resumo = {
            "total_processado": total_downloads,
            "sucesso_triagem": 0,
            "erros_atencao": 0,
            "pendente_senha": 0
        }
        
        for stat in stats_triagem:
            if stat['status'] == 'SUCESSO':
                resumo['sucesso_triagem'] = stat['qtd']
            elif stat['status'] == 'ERRO':
                resumo['erros_atencao'] += stat['qtd']
            elif stat['status'] == 'PENDENTE_SENHA':
                resumo['pendente_senha'] = stat['qtd']
                
        return resumo
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/fechamentos")
def get_fechamentos():
    """Busca fechamentos manuais e INJETA dinamicamente as OS automáticas da Malha."""
    # 1. Busca os fechamentos manuais salvos
    pastas_db = executar_query_dict("SELECT * FROM controle_pastas")
    pastas_dict = {(p['apelido'], p['competencia']): dict(p) for p in pastas_db}
    
    # 2. Busca TODAS as OS (Downloads) cruzando com a tabela de configuração de empresas
    query_os = """
        SELECT d.id_ticket, d.cod_emp, d.ultima_tentativa, d.verificado, d.data_auditoria, e.apelido
        FROM downloads d
        JOIN empresas_config e ON 
            e.apelido LIKE TRIM(CAST(d.cod_emp AS TEXT)) || ' - %' 
            OR e.apelido = TRIM(CAST(d.cod_emp AS TEXT))
    """
    try:
        oss = executar_query_dict(query_os)
    except Exception:
        oss = [] 
        
    # 3. Mescla as automações dentro das pastas
    for os_item in oss:
        if not os_item['ultima_tentativa']: continue
        comp = os_item['ultima_tentativa'][:7] 
        apelido = os_item['apelido']
        key = (apelido, comp)
        
        if key not in pastas_dict:
            pastas_dict[key] = {
                "apelido": apelido,
                "competencia": comp,
                "pasta_liberada_em": None,
                "documentos_json": "[]"
            }
        
        docs = json.loads(pastas_dict[key]['documentos_json'])
        id_auto = f"AUTO-{os_item['id_ticket']}"
        
        # Injeta a OS automática no JSON caso não exista
        if not any(d.get('id') == id_auto for d in docs):
            docs.append({
                "id": id_auto,
                "nome": f"OS #{os_item['id_ticket']} (Portal Domínio)",
                "recebido": os_item['ultima_tentativa'][:10],
                "liberado_em": os_item['data_auditoria'] if os_item['verificado'] else None,
                "isAuto": True # FLAG DE PROTEÇÃO
            })
        pastas_dict[key]['documentos_json'] = json.dumps(docs)
        
    return list(pastas_dict.values())


@app.post("/api/fechamentos")
def save_fechamento(payload: dict):
    """Salva os dados manuais e faz a SINCRONIZAÇÃO REVERSA com a Malha Fiscal."""
    docs = json.loads(payload.get("documentos_json", "[]"))
    
    # 1. PROTEÇÃO: Salva APENAS o que for manual (ignorando as automáticas da Malha)
    docs_manuais = [d for d in docs if not d.get("isAuto")]
    docs_json = json.dumps(docs_manuais)
    
    apelido = payload["apelido"]
    competencia = payload["competencia"]
    liberado_em = payload.get("pasta_liberada_em")
    
    # 2. SALVA NA PRIORIDADE CONTÁBIL
    row = executar_query_dict("SELECT id FROM controle_pastas WHERE apelido = ? AND competencia = ?", (apelido, competencia))
    if row:
        executar_update("UPDATE controle_pastas SET pasta_liberada_em = ?, documentos_json = ?, updated_at = datetime('now') WHERE id = ?", (liberado_em, docs_json, row[0]['id']))
    else:
        executar_update("INSERT INTO controle_pastas (apelido, competencia, pasta_liberada_em, documentos_json, updated_at) VALUES (?, ?, ?, ?, datetime('now'))", (apelido, competencia, liberado_em, docs_json))
        
    # ==========================================
    # 3. INTEGRAÇÃO REVERSA: PRIORIDADE -> MALHA FISCAL
    # ==========================================
    cod_empresa = apelido.split('-')[0].strip() # Isola o código (ex: "743 - TECNOFIT" -> "743")
    
    if liberado_em is None:
        # Se o usuário REABRIU o mês na Prioridade -> Desmarca o Check na Malha Fiscal
        executar_update("UPDATE malha_fiscal_validacao SET verificado = 0 WHERE TRIM(CAST(cod_empresa AS TEXT)) = ? AND competencia = ?", (cod_empresa, competencia))
    else:
        # Se o usuário CONCLUIU o mês na Prioridade -> Dá o Check verde na Malha Fiscal
        data_atual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        query_malha = """
            INSERT INTO malha_fiscal_validacao (cod_empresa, competencia, verificado, auditado_por, data_auditoria)
            VALUES (?, ?, 1, 'Via Fechamento', ?)
            ON CONFLICT(cod_empresa, competencia) DO UPDATE SET 
            verificado = 1, auditado_por = excluded.auditado_por, data_auditoria = excluded.data_auditoria
        """
        executar_update(query_malha, (cod_empresa, competencia, data_atual))

    return {"mensagem": "Pasta atualizada e sincronizada com a Malha!"}


# --- INÍCIO DA AUTO-CURA DO BANCO ---
def garantir_colunas_auditoria():
    """Garante que as colunas de auditoria existam no banco, prevenindo Erro 500."""
    with sqlite3.connect(DB_PATH) as conn:
        try: 
            conn.execute("ALTER TABLE downloads ADD COLUMN auditado_por TEXT")
        except sqlite3.OperationalError: 
            pass
            
        try: 
            conn.execute("ALTER TABLE downloads ADD COLUMN data_auditoria TEXT")
        except sqlite3.OperationalError: 
            pass
            
garantir_colunas_auditoria()
# --- FIM DA AUTO-CURA ---

@app.get("/api/triagem/auditoria")
def get_auditoria_triagem():
    query = """
        SELECT 
            dt.id,
            d.id_ticket as os, -- Mudamos para d.id_ticket para garantir que a OS apareça
            dt.nome_original as arquivo,
            dt.categoria_ia, 
            dt.status as status_triagem,
            dt.status_tomados,
            
            d.status as status_download,
            d.cod_emp as cod_empresa,
            d.nome_emp as nome_empresa,
            d.descricao as mensagem,
            d.qtd_anexos_esperados,
            d.verificado,
            d.ultima_tentativa as data_os,
            d.auditado_por,    
            d.data_auditoria

        FROM downloads d -- <--- COMEÇAMOS POR AQUI
        LEFT JOIN documentos_triados dt ON d.id_ticket = dt.id_ticket
        ORDER BY d.id_ticket DESC
    """
    try:
        return executar_query_dict(query)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/os/{os_id}/verificar")
def verificar_os(os_id: int, request: VerificacaoRequest):
    try:
        data_atual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        query = """
            UPDATE downloads 
            SET verificado = 1, 
                auditado_por = ?, 
                data_auditoria = ? 
            WHERE id_ticket = ?
        """
        executar_update(query, (request.usuario, data_atual, os_id))
        return {"mensagem": "OS validada com sucesso!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/os/{os_id}/desmarcar")
def desmarcar_os(os_id: int):
    try:
        executar_update("UPDATE downloads SET verificado = 0 WHERE id_ticket = ?", (os_id,))
        return {"mensagem": "OS retornada para pendentes."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/erros/senhas")
def get_erros_senha():
    """Retorna apenas os documentos que precisam de intervenção de senha."""
    query = """
        SELECT id, id_ticket as os, nome_original, pasta_destino
        FROM documentos_triados 
        WHERE status = 'ERRO' AND motivo_erro LIKE '%Senha%'
    """
    try:
        return executar_query_dict(query)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/documentos/{doc_id}/senha")
def resolver_senha(doc_id: int, request: SenhaRequest):
    """Recebe a senha do usuário e atualiza o banco para reprocessamento."""
    # NOTA FUTURA: Aqui precisaremos criar a coluna 'senha_temporaria' no banco 
    # para o worker_triagem ler. Por enquanto, só marcamos o status.
    try:
        query = "UPDATE documentos_triados SET status = 'PENDENTE_SENHA', motivo_erro = 'Aguardando Robô' WHERE id = ?"
        executar_update(query, (doc_id,))
        return {"mensagem": "Senha registrada com sucesso. Arquivo na fila de reprocessamento."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/documentos/{doc_id}/categoria")
def atualizar_categoria(doc_id: int, request: AtualizarCategoriaRequest):
    """Permite que o analista altere a categoria caso a IA tenha errado."""
    try:
        query = "UPDATE documentos_triados SET categoria_ia = ?, status = 'SUCESSO_MANUAL' WHERE id = ?"
        executar_update(query, (request.nova_categoria, doc_id))
        return {"mensagem": f"Categoria atualizada para {request.nova_categoria}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# ROTAS DA MALHA FISCAL (REVISADAS)
# ==========================================

@app.get("/api/malha-fiscal/resumo/{competencia}")
def get_resumo_malha(competencia: str):
    """Retorna os clientes, a contagem REAL do TriaBot e os erros após o Sync, incluindo validação."""
    query = """
        WITH clientes_com_tomadas AS (
            SELECT 
                TRIM(CAST(d.cod_emp AS TEXT)) as cod_emp, 
                d.nome_emp,
                COUNT(dt.id) as total_triabot_real
            FROM downloads d
            INNER JOIN documentos_triados dt ON d.id_ticket = dt.id_ticket
            WHERE strftime('%Y-%m', d.ultima_tentativa) = ?
              AND dt.categoria_ia LIKE '%nota%servico%'
            GROUP BY d.cod_emp, d.nome_emp
        ),
        resumo_malha AS (
            SELECT 
                TRIM(CAST(cod_empresa AS TEXT)) as cod_empresa,
                MAX(data_atualizacao) as ultima_sincronizacao,
                COUNT(CASE WHEN origem IN ('AWS', 'AMBOS') THEN 1 END) as total_aws,
                SUM(CASE WHEN status_conciliacao = 'FALTA_NO_TRIABOT' THEN 1 ELSE 0 END) as qtd_faltantes,
                SUM(CASE WHEN status_conciliacao = 'DIVERGENCIA_VALOR' THEN 1 ELSE 0 END) as qtd_divergentes,
                SUM(CASE WHEN status_conciliacao = 'NOTA_FANTASMA_TRIABOT' THEN 1 ELSE 0 END) as qtd_fantasmas
            FROM malha_fiscal_tomadas
            WHERE competencia LIKE '%' || ? || '%'
            GROUP BY cod_empresa
        )
        SELECT 
            c.cod_emp as cod_empresa,
            c.nome_emp as nome_empresa,
            COALESCE(r.ultima_sincronizacao, NULL) as ultima_sincronizacao,
            COALESCE(r.total_aws, 0) as total_aws,
            c.total_triabot_real as total_triabot,
            COALESCE(r.qtd_faltantes, 0) as qtd_faltantes,
            COALESCE(r.qtd_divergentes, 0) as qtd_divergentes,
            COALESCE(r.qtd_fantasmas, 0) as qtd_fantasmas,
            CAST(COALESCE(v.verificado, 0) AS INTEGER) as verificado,
            v.auditado_por, 
            v.data_auditoria
        FROM clientes_com_tomadas c
        LEFT JOIN resumo_malha r ON c.cod_emp = r.cod_empresa
        LEFT JOIN malha_fiscal_validacao v ON c.cod_emp = TRIM(CAST(v.cod_empresa AS TEXT)) AND v.competencia LIKE '%' || ? || '%'
        ORDER BY c.nome_emp ASC
    """
    try:
        return executar_query_dict(query, (competencia, competencia, competencia))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/malha-fiscal/detalhes/{cod_empresa}/{competencia}")
def get_detalhes_malha(cod_empresa: str, competencia: str):
    """Puxa as notas individuais para a sub-tabela expandida."""
    query = """
        SELECT * FROM malha_fiscal_tomadas 
        WHERE TRIM(CAST(cod_empresa AS TEXT)) = ? 
        AND competencia LIKE '%' || ? || '%' 
        ORDER BY status_conciliacao DESC
    """
    try:
        return executar_query_dict(query, (str(cod_empresa).strip(), competencia))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/malha-fiscal/sincronizar/{cod_empresa}/{competencia}")
def sincronizar_malha_cliente(cod_empresa: str, competencia: str):
    """Sincroniza dados da AWS com TriaBot."""
    try:
        db_dom = DatabaseConnection()
        if not db_dom.connect(): raise Exception("Falha ao conectar no banco da Domínio.")
        cnpjs_grupo = db_dom.obter_cnpjs_do_grupo(cod_empresa)
        db_dom.close()
        
        if not cnpjs_grupo: raise Exception(f"CNPJ não encontrado.")
        cnpj_cliente = cnpjs_grupo[0]         
        notas_aws = buscar_xmls_aws(cnpj_cliente, competencia)
        
        executar_update("DELETE FROM malha_fiscal_tomadas WHERE TRIM(CAST(cod_empresa AS TEXT)) = ? AND competencia = ?", (str(cod_empresa).strip(), competencia))
        
        for nota in notas_aws:
            triabot_match = executar_query_dict("""
                SELECT valor_contabil FROM resultados_tomados 
                WHERE numero_documento = ? AND cpf_cnpj = ? AND id_ticket IN (
                    SELECT id_ticket FROM downloads WHERE cod_emp = ?
                )
            """, (nota['numero'], nota['cnpj'], cod_empresa))

            status = "FALTA_NO_TRIABOT"
            valor_triabot = 0.0
            if triabot_match:
                try:
                    valor_triabot = float(triabot_match[0]['valor_contabil'].replace('.', '').replace(',', '.'))
                except: pass
                status = "BATEU" if abs(valor_triabot - nota['valor']) <= 0.01 else "DIVERGENCIA_VALOR"
            
            executar_update("""
                INSERT INTO malha_fiscal_tomadas 
                (cod_empresa, competencia, numero_nota, cnpj_prestador, valor_nota, status_conciliacao, origem)
                VALUES (?, ?, ?, ?, ?, ?, 'AWS')
            """, (cod_empresa, competencia, nota['numero'], nota['cnpj'], nota['valor'], status))

        # Adiciona notas que só existem no TriaBot (Fantasmas)
        notas_triabot = executar_query_dict("""
            SELECT numero_documento, cpf_cnpj, valor_contabil FROM resultados_tomados 
            WHERE id_ticket IN (SELECT id_ticket FROM downloads WHERE cod_emp = ? AND strftime('%Y-%m', ultima_tentativa) = ?)
        """, (cod_empresa, competencia))

        for nota_tb in notas_triabot:
            ja_existe = executar_query_dict("SELECT id FROM malha_fiscal_tomadas WHERE cod_empresa = ? AND competencia = ? AND numero_nota = ? AND cnpj_prestador = ?", (cod_empresa, competencia, nota_tb['numero_documento'], nota_tb['cpf_cnpj']))
            if not ja_existe:
                try: v_tb = float(nota_tb['valor_contabil'].replace('.', '').replace(',', '.'))
                except: v_tb = 0.0
                executar_update("INSERT INTO malha_fiscal_tomadas (cod_empresa, competencia, numero_nota, cnpj_prestador, valor_nota, status_conciliacao, origem) VALUES (?, ?, ?, ?, ?, 'NOTA_FANTASMA_TRIABOT', 'TRIABOT')", (cod_empresa, competencia, nota_tb['numero_documento'], nota_tb['cpf_cnpj'], v_tb))

        return {"mensagem": "Sincronização concluída."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class MalhaValidacaoRequest(BaseModel):
    usuario: str


@app.put("/api/malha-fiscal/validar/{cod_empresa}/{competencia}")
def validar_malha(cod_empresa: str, competencia: str, request: MalhaValidacaoRequest):
    data_atual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cod_str = str(cod_empresa).strip()
    
    # 1. VALIDA NA MALHA FISCAL (Ação original)
    query_malha = """
        INSERT INTO malha_fiscal_validacao (cod_empresa, competencia, verificado, auditado_por, data_auditoria)
        VALUES (?, ?, 1, ?, ?)
        ON CONFLICT(cod_empresa, competencia) DO UPDATE SET 
        verificado = 1, auditado_por = excluded.auditado_por, data_auditoria = excluded.data_auditoria
    """
    executar_update(query_malha, (cod_str, competencia, request.usuario, data_atual))
    
    # 2. INTEGRAÇÃO AUTOMÁTICA: PRIORIDADE CONTÁBIL
    # Busca a carteira de empresas e encontra o "apelido" que começa com esse código
    todas_empresas = executar_query_dict("SELECT apelido FROM empresas_config")
    apelido_oficial = None
    
    for emp in todas_empresas:
        apelido_banco = emp['apelido']
        cod_banco = apelido_banco.split('-')[0].strip() # Pega só o que vem antes do traço
        if cod_banco == cod_str:
            apelido_oficial = apelido_banco
            break
            
    # Se encontrou a empresa na carteira, fecha o mês dela automaticamente!
    if apelido_oficial:
        row = executar_query_dict("SELECT id FROM controle_pastas WHERE apelido = ? AND competencia = ?", (apelido_oficial, competencia))
        if row:
            executar_update("UPDATE controle_pastas SET pasta_liberada_em = ?, updated_at = ? WHERE id = ?", (data_atual, data_atual, row[0]['id']))
        else:
            executar_update("INSERT INTO controle_pastas (apelido, competencia, pasta_liberada_em, documentos_json, updated_at) VALUES (?, ?, ?, '[]', ?)", (apelido_oficial, competencia, data_atual, data_atual))

    return {"mensagem": "Malha validada e Prioridade Contábil atualizada!"}


@app.put("/api/malha-fiscal/desmarcar/{cod_empresa}/{competencia}")
def desmarcar_malha(cod_empresa: str, competencia: str):
    cod_str = str(cod_empresa).strip()
    
    # 1. DESMARCA NA MALHA FISCAL
    query = "UPDATE malha_fiscal_validacao SET verificado = 0 WHERE TRIM(CAST(cod_empresa AS TEXT)) = ? AND competencia = ?"
    executar_update(query, (cod_str, competencia))
    
    # 2. INTEGRAÇÃO AUTOMÁTICA: REABRE NA PRIORIDADE CONTÁBIL
    todas_empresas = executar_query_dict("SELECT apelido FROM empresas_config")
    apelido_oficial = None
    
    for emp in todas_empresas:
        cod_banco = emp['apelido'].split('-')[0].strip()
        if cod_banco == cod_str:
            apelido_oficial = emp['apelido']
            break
            
    if apelido_oficial:
        executar_update("UPDATE controle_pastas SET pasta_liberada_em = NULL, updated_at = datetime('now') WHERE apelido = ? AND competencia = ?", (apelido_oficial, competencia))

    return {"mensagem": "Validação removida em ambos os painéis."}

# ==========================================
# ROTAS DE PRIORIDADE CONTÁBIL (FECHAMENTOS)
# ==========================================
class EmpresaConfigRequest(BaseModel):
    apelido: str
    tipo: str 
    competencia: Optional[str] = None


@app.get("/api/prioridades")
def get_prioridades(month: str = Query(None)):
    """Busca empresas ativas: Vitalícias + Mensais daquela competência específica."""
    query = """
        SELECT apelido, tipo, ativa FROM empresas_config 
        WHERE ativa = 1 
        AND (tipo = 'VITALICIA' OR (tipo = 'MENSAL' AND competencia_unica = ?))
    """
    return executar_query_dict(query, (month,))


@app.get("/api/prioridades/config")
def get_todas_configs():
    """Retorna todas as empresas cadastradas para o modal de gerenciamento."""
    return executar_query_dict("SELECT * FROM empresas_config ORDER BY ativa DESC, apelido ASC")


@app.post("/api/prioridades/config")
def save_empresa_config(req: EmpresaConfigRequest):
    query = """
        INSERT INTO empresas_config (apelido, tipo, competencia_unica, ativa)
        VALUES (?, ?, ?, 1)
        ON CONFLICT(apelido) DO UPDATE SET 
            tipo = excluded.tipo,
            competencia_unica = excluded.competencia_unica,
            ativa = 1
    """
    executar_update(query, (req.apelido.upper(), req.tipo, req.competencia))
    return {"mensagem": "Configuração salva"}


@app.put("/api/prioridades/config/{apelido}/toggle")
def toggle_empresa(apelido: str):
    """Inativa ou Ativa uma empresa."""
    executar_update("UPDATE empresas_config SET ativa = 1 - ativa WHERE apelido = ?", (apelido,))
    return {"mensagem": "Status alterado"}


@app.delete("/api/prioridades/config/{apelido}")
def delete_empresa_config(apelido: str):
    """Remove permanentemente a empresa da lista de prioridades."""
    executar_update("DELETE FROM empresas_config WHERE apelido = ?", (apelido,))
    return {"mensagem": "Empresa removida"}


