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
from fastapi import FastAPI, HTTPException
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
    query = """
        INSERT INTO malha_fiscal_validacao (cod_empresa, competencia, verificado, auditado_por, data_auditoria)
        VALUES (?, ?, 1, ?, ?)
        ON CONFLICT(cod_empresa, competencia) DO UPDATE SET 
        verificado = 1, auditado_por = excluded.auditado_por, data_auditoria = excluded.data_auditoria
    """
    executar_update(query, (str(cod_empresa).strip(), competencia, request.usuario, data_atual))
    return {"mensagem": "Malha validada!"}

@app.put("/api/malha-fiscal/desmarcar/{cod_empresa}/{competencia}")
def desmarcar_malha(cod_empresa: str, competencia: str):
    query = "UPDATE malha_fiscal_validacao SET verificado = 0 WHERE TRIM(CAST(cod_empresa AS TEXT)) = ? AND competencia = ?"
    executar_update(query, (str(cod_empresa).strip(), competencia))
    return {"mensagem": "Validação removida."}


# ==========================================
# ROTAS DE PRIORIDADE CONTÁBIL (FECHAMENTOS)
# ==========================================
PRIORIDADES_FILE = RAIZ_PROJETO / "prioridades.json"

@app.get("/api/prioridades")
def get_prioridades():
    if not PRIORIDADES_FILE.exists():
        return []
    try:
        return json.loads(PRIORIDADES_FILE.read_text(encoding="utf-8"))
    except:
        return []


@app.post("/api/prioridades")
def save_prioridades(payload: list[str]):
    PRIORIDADES_FILE.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return {"mensagem": "Prioridades atualizadas"}


@app.get("/api/fechamentos")
def get_fechamentos():
    return executar_query_dict("SELECT * FROM controle_pastas")


@app.post("/api/fechamentos")
def save_fechamento(payload: dict):
    # Verifica se já existe para fazer UPDATE ou INSERT
    row = executar_query_dict(
        "SELECT id FROM controle_pastas WHERE apelido = ? AND competencia = ?", 
        (payload["apelido"], payload["competencia"])
    )
    
    docs_json = payload.get("documentos_json", "[]")
    if isinstance(docs_json, list):
        docs_json = json.dumps(docs_json)

    if row:
        executar_update('''
            UPDATE controle_pastas
            SET pasta_liberada_em = ?, documentos_json = ?, updated_at = datetime('now')
            WHERE id = ?
        ''', (payload.get("pasta_liberada_em"), docs_json, row[0]['id']))
    else:
        executar_update('''
            INSERT INTO controle_pastas (apelido, competencia, pasta_liberada_em, documentos_json, updated_at)
            VALUES (?, ?, ?, ?, datetime('now'))
        ''', (payload["apelido"], payload["competencia"], payload.get("pasta_liberada_em"), docs_json))
        
    return {"mensagem": "Pasta atualizada"}

    