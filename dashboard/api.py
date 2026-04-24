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

app = FastAPI(title="API Triagem Cloud", description="Backend para o Dashboard RPA")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)

DB_PATH = RAIZ_PROJETO / "banco_rpa.db"

class VerificacaoRequest(BaseModel): 
    usuario: str


class SenhaRequest(BaseModel): 
    senha: str


class AtualizarCategoriaRequest(BaseModel):
    nova_categoria: str


def executar_query_dict(query, params=()):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def executar_update(query, params=()):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(query, params)
        conn.commit()


# ==========================================
# ROTAS DE DOWNLOAD E RESUMO DO DASHBOARD
# ==========================================
@app.get("/api/download/tomados/{os_id}")
def baixar_tomados_zip(os_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        registros = [dict(r) for r in conn.execute("SELECT * FROM resultados_tomados WHERE id_ticket = ?", (os_id,)).fetchall()]

    if not registros: raise HTTPException(status_code=404, detail="Nenhum dado encontrado.")

    df = pd.DataFrame(registros)
    colunas_dominio = ['cpf_cnpj', 'razao_social', 'uf', 'municipio', 'endereco', 'numero_documento', 'serie', 'data_emissao', 'situacao', 'acumulador', 'cfop', 'valor_servicos', 'valor_descontos', 'valor_contabil', 'base_calculo', 'alq_iss', 'valor_iss_normal', 'valor_iss_retido', 'valor_irrf', 'valor_pis', 'valor_cofins', 'valor_csll', 'valor_crf', 'valor_inss', 'cod_item', 'quantidade', 'vlr_unitario', 'tomador']
    
    for col in colunas_dominio:
        if col not in df.columns: df[col] = ''
    df = df[colunas_dominio]
    df['situacao'] = '0' 
    
    df_csv = df.copy()
    df_csv['cpf_cnpj'] = df_csv['cpf_cnpj'].apply(lambda x: f'="{x}"') 
    df_csv['tomador'] = df_csv['tomador'].apply(lambda x: f'="{x}"')
    
    colunas_valores = ['valor_servicos', 'valor_contabil', 'base_calculo', 'valor_irrf', 'valor_pis', 'valor_cofins', 'valor_csll', 'valor_crf', 'valor_inss']
    for col in colunas_valores: df_csv[col] = df_csv[col].apply(lambda x: str(x).replace('.', ','))

    header_pt = ['CPF/CNPJ', 'Razão Social', 'UF', 'Município', 'Endereço', 'Número Documento', 'Série', 'Data', 'Situação', 'Acumulador', 'CFOP', 'Valor Serviços', 'Valor Descontos', 'Valor Contábil', 'Base de Calculo', 'Alíquota ISS', 'Valor ISS Normal', 'Valor ISS Retido', 'Valor IRRF', 'Valor PIS', 'Valor COFINS', 'Valor CSLL', 'Valo CRF', 'Valor INSS', 'Código do Item', 'Quantidade', 'Valor Unitário', 'Tomador']

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
        csv_geral = df_csv.to_csv(index=False, sep=';', header=header_pt, encoding='utf-8-sig')
        zipf.writestr("GERAL_IMPORTACAO.csv", csv_geral)
        for tomador, group in df_csv.groupby('tomador'):
            cnpj_clean = re.sub(r'[^0-9]', '', tomador)
            csv_indiv = group.to_csv(index=False, sep=';', header=header_pt, encoding='utf-8-sig')
            zipf.writestr(f"TOMADOS_CLI_{cnpj_clean}.csv", csv_indiv)

    zip_buffer.seek(0)
    return StreamingResponse(zip_buffer, media_type="application/zip", headers={"Content-Disposition": f"attachment; filename=OS{os_id}_Planilhas_Domínio.zip"})


@app.get("/api/resumo")
def get_resumo_dashboard(month: str = Query(None)):
    if not month: 
        month = datetime.now().strftime("%Y-%m")

    try:
        total_downloads = executar_query_dict("SELECT COUNT(*) as total FROM downloads WHERE strftime('%Y-%m', ultima_tentativa) = ?", (month,))[0]['total']
        empresas_ativas = executar_query_dict("SELECT COUNT(DISTINCT TRIM(CAST(cod_emp AS TEXT))) as total FROM downloads WHERE cod_emp IS NOT NULL AND cod_emp != '' AND strftime('%Y-%m', ultima_tentativa) = ?", (month,))[0]['total']
        os_sem_anexos = executar_query_dict("SELECT COUNT(*) as total FROM downloads WHERE (qtd_anexos_esperados = 0 OR qtd_anexos_esperados IS NULL) AND strftime('%Y-%m', ultima_tentativa) = ?", (month,))[0]['total']

        stats_triagem = executar_query_dict("""
            SELECT dt.status, COUNT(*) as qtd 
            FROM documentos_triados dt
            JOIN downloads d ON dt.id_ticket = d.id_ticket
            WHERE strftime('%Y-%m', d.ultima_tentativa) = ?
            GROUP BY dt.status
        """, (month,))

        top_empresas = executar_query_dict("""
            SELECT 
                TRIM(CAST(d.cod_emp AS TEXT)) as cod, 
                d.nome_emp as nome, 
                COUNT(DISTINCT d.id_ticket) as qtd_os,
                COUNT(dt.id) as qtd_docs
            FROM downloads d
            LEFT JOIN documentos_triados dt ON dt.id_ticket = d.id_ticket
            WHERE d.cod_emp IS NOT NULL AND d.cod_emp != '' AND strftime('%Y-%m', d.ultima_tentativa) = ?
            GROUP BY TRIM(CAST(d.cod_emp AS TEXT)), d.nome_emp
            ORDER BY qtd_os DESC, qtd_docs DESC
            LIMIT 5
        """, (month,))
        
        resumo = {
            "total_processado": total_downloads, 
            "empresas_ativas": empresas_ativas, 
            "os_sem_anexos": os_sem_anexos,
            "sucesso_triagem": 0, 
            "erros_atencao": 0, 
            "pendente_senha": 0, 
            "top_empresas": top_empresas
        }
        
        for stat in stats_triagem:
            if stat['status'] == 'SUCESSO': resumo['sucesso_triagem'] = stat['qtd']
            elif stat['status'] == 'ERRO': resumo['erros_atencao'] += stat['qtd']
            elif stat['status'] == 'PENDENTE_SENHA': resumo['pendente_senha'] = stat['qtd']
                
        return resumo
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))


def garantir_colunas_auditoria():
    with sqlite3.connect(DB_PATH) as conn:
        try: conn.execute("ALTER TABLE downloads ADD COLUMN auditado_por TEXT")
        except: pass
        try: conn.execute("ALTER TABLE downloads ADD COLUMN data_auditoria TEXT")
        except: pass
garantir_colunas_auditoria()


@app.get("/api/triagem/auditoria")
def get_auditoria_triagem():
    query = """
        SELECT dt.id, d.id_ticket as os, dt.nome_original as arquivo, dt.categoria_ia, dt.status as status_triagem, dt.status_tomados,
            d.status as status_download, d.cod_emp as cod_empresa, d.nome_emp as nome_empresa, d.descricao as mensagem,
            d.qtd_anexos_esperados, d.verificado, d.ultima_tentativa as data_os, d.auditado_por, d.data_auditoria
        FROM downloads d LEFT JOIN documentos_triados dt ON d.id_ticket = dt.id_ticket ORDER BY d.id_ticket DESC
    """
    try: return executar_query_dict(query)
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/os/{os_id}/verificar")
def verificar_os(os_id: int, request: VerificacaoRequest):
    data_atual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    executar_update("UPDATE downloads SET verificado = 1, auditado_por = ?, data_auditoria = ? WHERE id_ticket = ?", (request.usuario, data_atual, os_id))
    return {"mensagem": "OS validada!"}


@app.put("/api/os/{os_id}/desmarcar")
def desmarcar_os(os_id: int):
    executar_update("UPDATE downloads SET verificado = 0 WHERE id_ticket = ?", (os_id,))
    return {"mensagem": "OS desmarcada."}


@app.get("/api/erros/senhas")
def get_erros_senha():
    return executar_query_dict("SELECT id, id_ticket as os, nome_original, pasta_destino FROM documentos_triados WHERE status = 'ERRO' AND motivo_erro LIKE '%Senha%'")


@app.post("/api/documentos/{doc_id}/senha")
def resolver_senha(doc_id: int, request: SenhaRequest):
    executar_update("UPDATE documentos_triados SET status = 'PENDENTE_SENHA', motivo_erro = 'Aguardando Robô' WHERE id = ?", (doc_id,))
    return {"mensagem": "Senha registrada."}


@app.put("/api/documentos/{doc_id}/categoria")
def atualizar_categoria(doc_id: int, request: AtualizarCategoriaRequest):
    executar_update("UPDATE documentos_triados SET categoria_ia = ?, status = 'SUCESSO_MANUAL' WHERE id = ?", (request.nova_categoria, doc_id))
    return {"mensagem": "Categoria atualizada"}


# ==========================================
# ROTAS DA MALHA FISCAL 
# ==========================================
@app.get("/api/malha-fiscal/resumo/{competencia}")
def get_resumo_malha(competencia: str):
    query = """
        WITH clientes_com_tomadas AS (
            SELECT TRIM(CAST(d.cod_emp AS TEXT)) as cod_emp, d.nome_emp, COUNT(dt.id) as total_triabot_real
            FROM downloads d INNER JOIN documentos_triados dt ON d.id_ticket = dt.id_ticket
            WHERE strftime('%Y-%m', d.ultima_tentativa) = ? AND dt.categoria_ia LIKE '%nota%servico%' GROUP BY d.cod_emp, d.nome_emp
        ),
        resumo_malha AS (
            SELECT TRIM(CAST(cod_empresa AS TEXT)) as cod_empresa, MAX(data_atualizacao) as ultima_sincronizacao,
                COUNT(CASE WHEN origem IN ('AWS', 'AMBOS') THEN 1 END) as total_aws,
                SUM(CASE WHEN status_conciliacao = 'FALTA_NO_TRIABOT' THEN 1 ELSE 0 END) as qtd_faltantes,
                SUM(CASE WHEN status_conciliacao = 'DIVERGENCIA_VALOR' THEN 1 ELSE 0 END) as qtd_divergentes,
                SUM(CASE WHEN status_conciliacao = 'NOTA_FANTASMA_TRIABOT' THEN 1 ELSE 0 END) as qtd_fantasmas
            FROM malha_fiscal_tomadas WHERE competencia LIKE '%' || ? || '%' GROUP BY cod_empresa
        )
        SELECT c.cod_emp as cod_empresa, c.nome_emp as nome_empresa, COALESCE(r.ultima_sincronizacao, NULL) as ultima_sincronizacao,
            COALESCE(r.total_aws, 0) as total_aws, c.total_triabot_real as total_triabot, COALESCE(r.qtd_faltantes, 0) as qtd_faltantes,
            COALESCE(r.qtd_divergentes, 0) as qtd_divergentes, COALESCE(r.qtd_fantasmas, 0) as qtd_fantasmas,
            CAST(COALESCE(v.verificado, 0) AS INTEGER) as verificado, v.auditado_por, v.data_auditoria
        FROM clientes_com_tomadas c LEFT JOIN resumo_malha r ON c.cod_emp = r.cod_empresa
        LEFT JOIN malha_fiscal_validacao v ON c.cod_emp = TRIM(CAST(v.cod_empresa AS TEXT)) AND v.competencia LIKE '%' || ? || '%' ORDER BY c.nome_emp ASC
    """
    return executar_query_dict(query, (competencia, competencia, competencia))


@app.get("/api/malha-fiscal/detalhes/{cod_empresa}/{competencia}")
def get_detalhes_malha(cod_empresa: str, competencia: str):
    query = """
        SELECT m.*, (SELECT MAX(id_ticket) FROM resultados_tomados r WHERE r.numero_documento = m.numero_nota AND r.cpf_cnpj = m.cnpj_prestador 
             AND r.id_ticket IN (SELECT id_ticket FROM downloads WHERE TRIM(CAST(cod_emp AS TEXT)) = TRIM(CAST(m.cod_empresa AS TEXT)))) as os_onvio
        FROM malha_fiscal_tomadas m WHERE TRIM(CAST(m.cod_empresa AS TEXT)) = ? AND m.competencia LIKE '%' || ? || '%' ORDER BY m.status_conciliacao DESC
    """
    return executar_query_dict(query, (str(cod_empresa).strip(), competencia))


@app.post("/api/malha-fiscal/sincronizar/{cod_empresa}/{competencia}")
def sincronizar_malha_cliente(cod_empresa: str, competencia: str):
    try:
        db_dom = DatabaseConnection()
        if not db_dom.connect(): raise Exception("Falha ao conectar na Domínio.")
        cnpjs_grupo = db_dom.obter_cnpjs_do_grupo(cod_empresa)
        db_dom.close()
        
        if not cnpjs_grupo: raise Exception("CNPJ não encontrado.")
        notas_aws = buscar_xmls_aws(cnpjs_grupo[0], competencia)
        
        executar_update("DELETE FROM malha_fiscal_tomadas WHERE TRIM(CAST(cod_empresa AS TEXT)) = ? AND competencia = ?", (str(cod_empresa).strip(), competencia))
        
        for nota in notas_aws:
            triabot_match = executar_query_dict("SELECT valor_contabil FROM resultados_tomados WHERE numero_documento = ? AND cpf_cnpj = ? AND id_ticket IN (SELECT id_ticket FROM downloads WHERE cod_emp = ?)", (nota['numero'], nota['cnpj'], cod_empresa))
            status = "FALTA_NO_TRIABOT"
            if triabot_match:
                try: valor_triabot = float(triabot_match[0]['valor_contabil'].replace('.', '').replace(',', '.'))
                except: valor_triabot = 0.0
                status = "BATEU" if abs(valor_triabot - nota['valor']) <= 0.01 else "DIVERGENCIA_VALOR"
            executar_update("INSERT INTO malha_fiscal_tomadas (cod_empresa, competencia, numero_nota, cnpj_prestador, valor_nota, status_conciliacao, origem) VALUES (?, ?, ?, ?, ?, ?, 'AWS')", (cod_empresa, competencia, nota['numero'], nota['cnpj'], nota['valor'], status))

        notas_triabot = executar_query_dict("SELECT numero_documento, cpf_cnpj, valor_contabil FROM resultados_tomados WHERE id_ticket IN (SELECT id_ticket FROM downloads WHERE cod_emp = ? AND strftime('%Y-%m', ultima_tentativa) = ?)", (cod_empresa, competencia))
        for nota_tb in notas_triabot:
            if not executar_query_dict("SELECT id FROM malha_fiscal_tomadas WHERE cod_empresa = ? AND competencia = ? AND numero_nota = ? AND cnpj_prestador = ?", (cod_empresa, competencia, nota_tb['numero_documento'], nota_tb['cpf_cnpj'])):
                try: v_tb = float(nota_tb['valor_contabil'].replace('.', '').replace(',', '.'))
                except: v_tb = 0.0
                executar_update("INSERT INTO malha_fiscal_tomadas (cod_empresa, competencia, numero_nota, cnpj_prestador, valor_nota, status_conciliacao, origem) VALUES (?, ?, ?, ?, ?, 'NOTA_FANTASMA_TRIABOT', 'TRIABOT')", (cod_empresa, competencia, nota_tb['numero_documento'], nota_tb['cpf_cnpj'], v_tb))
        return {"mensagem": "Sincronização concluída."}
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))


class MalhaValidacaoRequest(BaseModel):
    usuario: str


@app.put("/api/malha-fiscal/validar/{cod_empresa}/{competencia}")
def validar_malha(cod_empresa: str, competencia: str, request: MalhaValidacaoRequest):
    data_atual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cod_str = str(cod_empresa).strip()
    executar_update("INSERT INTO malha_fiscal_validacao (cod_empresa, competencia, verificado, auditado_por, data_auditoria) VALUES (?, ?, 1, ?, ?) ON CONFLICT(cod_empresa, competencia) DO UPDATE SET verificado = 1, auditado_por = excluded.auditado_por, data_auditoria = excluded.data_auditoria", (cod_str, competencia, request.usuario, data_atual))
    
    row = executar_query_dict("SELECT apelido FROM empresas_config WHERE TRIM(CAST(codigo AS TEXT)) = ? OR apelido LIKE ? OR apelido LIKE ? OR apelido = ?", (cod_str, f"{cod_str}-%", f"{cod_str} - %", cod_str))
    if row:
        apelido_oficial = row[0]['apelido']
        row_pasta = executar_query_dict("SELECT id FROM controle_pastas WHERE apelido = ? AND competencia = ?", (apelido_oficial, competencia))
        if row_pasta: executar_update("UPDATE controle_pastas SET pasta_liberada_em = ?, updated_at = ? WHERE id = ?", (data_atual, data_atual, row_pasta[0]['id']))
        else: executar_update("INSERT INTO controle_pastas (apelido, competencia, pasta_liberada_em, documentos_json, updated_at) VALUES (?, ?, ?, '[]', ?)", (apelido_oficial, competencia, data_atual, data_atual))
    return {"mensagem": "Malha validada!"}


@app.put("/api/malha-fiscal/desmarcar/{cod_empresa}/{competencia}")
def desmarcar_malha(cod_empresa: str, competencia: str):
    cod_str = str(cod_empresa).strip()
    executar_update("UPDATE malha_fiscal_validacao SET verificado = 0 WHERE TRIM(CAST(cod_empresa AS TEXT)) = ? AND competencia = ?", (cod_str, competencia))
    row = executar_query_dict("SELECT apelido FROM empresas_config WHERE TRIM(CAST(codigo AS TEXT)) = ? OR apelido LIKE ? OR apelido LIKE ? OR apelido = ?", (cod_str, f"{cod_str}-%", f"{cod_str} - %", cod_str))
    if row: executar_update("UPDATE controle_pastas SET pasta_liberada_em = NULL, updated_at = datetime('now') WHERE apelido = ? AND competencia = ?", (row[0]['apelido'], competencia))
    return {"mensagem": "Desmarcado."}


# ==========================================
# ROTAS DE PRIORIDADE CONTÁBIL (FECHAMENTOS)
# ==========================================
class EmpresaConfigRequest(BaseModel):
    codigo: str 
    apelido: str
    tipo: str 
    competencia: Optional[str] = None

@app.get("/api/dominio/empresa/{codigo}")
def buscar_empresa_dominio(codigo: str):
    db_dom = DatabaseConnection()
    if not db_dom.connect():
        raise HTTPException(status_code=500, detail="Erro ao conectar na Domínio")
    
    try:
        cursor = db_dom.conn.cursor()
        # Busca o apelido e o nome da empresa na tabela da Domínio
        cursor.execute("SELECT apel_emp, nome_emp FROM bethadba.geempre WHERE codi_emp = ?", (codigo,))
        row = cursor.fetchone()
        
        if row:
            apel_emp = str(row[0]).strip().upper() if row[0] else ""
            nome_emp = str(row[1]).strip().upper() if row[1] else ""
            
            # Prioriza o apelido (que costuma ser mais limpo), se não tiver, usa o nome
            nome_final = apel_emp if len(apel_emp) > 2 else nome_emp
            
            return {"codigo": codigo, "apelido": nome_final}
        else:
            raise HTTPException(status_code=404, detail="Empresa não encontrada")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db_dom.close()

@app.get("/api/prioridades")
def get_prioridades(month: str = Query(None)):
    return executar_query_dict("SELECT codigo, apelido, tipo, ativa FROM empresas_config WHERE ativa = 1 AND (tipo = 'VITALICIA' OR (tipo = 'MENSAL' AND competencia_unica = ?))", (month,))

@app.get("/api/prioridades/config")
def get_todas_configs():
    return executar_query_dict("SELECT * FROM empresas_config ORDER BY ativa DESC, apelido ASC")

@app.post("/api/prioridades/config")
def save_empresa_config(req: EmpresaConfigRequest):
    executar_update("""
        INSERT INTO empresas_config (codigo, apelido, tipo, competencia_unica, ativa) 
        VALUES (?, ?, ?, ?, 1) 
        ON CONFLICT(apelido) DO UPDATE SET codigo = excluded.codigo, tipo = excluded.tipo, competencia_unica = excluded.competencia_unica, ativa = 1
    """, (req.codigo.strip(), req.apelido.strip().upper(), req.tipo, req.competencia))
    return {"mensagem": "Configuração salva"}

@app.put("/api/prioridades/config/{apelido}/toggle")
def toggle_empresa(apelido: str):
    executar_update("UPDATE empresas_config SET ativa = 1 - ativa WHERE apelido = ?", (apelido,))
    return {"mensagem": "Status alterado"}

@app.delete("/api/prioridades/config/{apelido}")
def delete_empresa_config(apelido: str):
    executar_update("DELETE FROM empresas_config WHERE apelido = ?", (apelido,))
    return {"mensagem": "Empresa removida"}

class RenameEmpresaRequest(BaseModel): novo_apelido: str

@app.put("/api/prioridades/config/{apelido}/renomear")
def renomear_empresa_config(apelido: str, req: RenameEmpresaRequest):
    novo_nome = req.novo_apelido.strip().upper()
    executar_update("UPDATE empresas_config SET apelido = ? WHERE apelido = ?", (novo_nome, apelido))
    executar_update("UPDATE controle_pastas SET apelido = ? WHERE apelido = ?", (novo_nome, apelido))
    return {"mensagem": "Renomeado!"}


@app.get("/api/fechamentos")
def get_fechamentos():
    pastas_db = executar_query_dict("SELECT * FROM controle_pastas")
    pastas_dict = {(p['apelido'], p['competencia']): dict(p) for p in pastas_db}    
    query_os = """
        SELECT d.id_ticket, d.cod_emp, d.ultima_tentativa, d.verificado as os_verificado, 
               d.data_auditoria as os_data, e.apelido, m.verificado as malha_verificado, 
               m.data_auditoria as malha_data
        FROM downloads d 
        JOIN empresas_config e ON TRIM(CAST(e.codigo AS TEXT)) = TRIM(CAST(d.cod_emp AS TEXT))
        LEFT JOIN malha_fiscal_validacao m ON TRIM(CAST(m.cod_empresa AS TEXT)) = TRIM(CAST(d.cod_emp AS TEXT)) 
             AND m.competencia = strftime('%Y-%m', d.ultima_tentativa) 
        WHERE d.ultima_tentativa IS NOT NULL
          AND EXISTS (
              SELECT 1 FROM documentos_triados dt 
              WHERE dt.id_ticket = d.id_ticket 
                AND dt.categoria_ia = 'nota_servico'
          )
    """
    try: 
        oss = executar_query_dict(query_os)
    except Exception: 
        oss = [] 
        
    for os_item in oss:
        comp = os_item['ultima_tentativa'][:7] 
        apelido = os_item['apelido']
        key = (apelido, comp)
        if key not in pastas_dict: 
            pastas_dict[key] = {"apelido": apelido, "competencia": comp, "pasta_liberada_em": None, "documentos_json": "[]"}
        
        docs_salvos = json.loads(pastas_dict[key]['documentos_json'])
        docs_limpos = [d for d in docs_salvos if not (d.get("isAuto") == True or str(d.get("nome", "")).startswith("OS #"))]
        
        is_validado = (str(os_item['os_verificado']) == '1') or (str(os_item['malha_verificado']) == '1')
        data_auditoria = os_item['os_data'] if str(os_item['os_verificado']) == '1' else os_item['malha_data']
        
        docs_limpos.append({
            "id": f"AUTO-{os_item['id_ticket']}", 
            "nome": f"OS #{os_item['id_ticket']}", 
            "recebido": os_item['ultima_tentativa'][:10], 
            "liberado_em": data_auditoria if is_validado else None, 
            "isAuto": True
        })
        pastas_dict[key]['documentos_json'] = json.dumps(docs_limpos)
        
    return list(pastas_dict.values())


@app.post("/api/fechamentos")
def save_fechamento(payload: dict):
    docs = json.loads(payload.get("documentos_json", "[]"))
    docs_manuais = [d for d in docs if not (d.get("isAuto") == True or str(d.get("nome", "")).startswith("OS #"))]
    apelido, competencia, liberado_em = payload["apelido"], payload["competencia"], payload.get("pasta_liberada_em")
    
    # 1. Atualiza controle de pastas
    row = executar_query_dict("SELECT id FROM controle_pastas WHERE apelido = ? AND competencia = ?", (apelido, competencia))
    if row: 
        executar_update("UPDATE controle_pastas SET pasta_liberada_em = ?, documentos_json = ?, updated_at = datetime('now') WHERE id = ?", (liberado_em, json.dumps(docs_manuais), row[0]['id']))
    else: 
        executar_update("INSERT INTO controle_pastas (apelido, competencia, pasta_liberada_em, documentos_json, updated_at) VALUES (?, ?, ?, ?, datetime('now'))", (apelido, competencia, liberado_em, json.dumps(docs_manuais)))
        
    # 2. Busca o código real no banco (Sem split!)
    row_emp = executar_query_dict("SELECT codigo FROM empresas_config WHERE apelido = ?", (apelido,))
    if not row_emp:
        raise HTTPException(status_code=404, detail="Empresa não configurada na carteira.")
    
    cod_empresa = row_emp[0]['codigo']
    
    # 3. Sincroniza com a Malha Fiscal
    if liberado_em is None: 
        executar_update("UPDATE malha_fiscal_validacao SET verificado = 0 WHERE TRIM(CAST(cod_empresa AS TEXT)) = ? AND competencia = ?", (cod_empresa, competencia))
    else: 
        executar_update("""
            INSERT INTO malha_fiscal_validacao (cod_empresa, competencia, verificado, auditado_por, data_auditoria) 
            VALUES (?, ?, 1, 'Via Fechamento', ?) 
            ON CONFLICT(cod_empresa, competencia) DO UPDATE SET verificado = 1, auditado_por = excluded.auditado_por, data_auditoria = excluded.data_auditoria
        """, (cod_empresa, competencia, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        
    return {"mensagem": "Sincronizado!"}

# ==========================================
# ROTAS DO DASHBOARD CHECKLIST E GESTTA
# ==========================================
class ChecklistToggleRequest(BaseModel):
    status: int
    month: str
    usuario: str

def garantir_tabela_checklist_mes():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS checklist_mes (id_tarefa INTEGER, competencia TEXT, status_manual INTEGER DEFAULT 0, usuario_conclusao TEXT, data_conclusao TEXT, PRIMARY KEY (id_tarefa, competencia))")
        try: conn.execute("ALTER TABLE checklist_mes ADD COLUMN usuario_conclusao TEXT")
        except: pass
        try: conn.execute("ALTER TABLE checklist_mes ADD COLUMN data_conclusao TEXT")
        except: pass
garantir_tabela_checklist_mes()

GESTTA_DB_PATH = "/home/usuario/PycharmProjects/APIGestta/gestta_tasks.db"


def buscar_progresso_gestta_remoto(termo, dia=None, competencia=None):
    if not os.path.exists(GESTTA_DB_PATH): return {"concluidas": 0, "total": 0}
    try:
        with sqlite3.connect(GESTTA_DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            query = "SELECT status FROM tasks WHERE name LIKE ?"
            params = [f"%{termo}%"]
            
            if competencia:
                query += " AND strftime('%Y-%m', due_date) = ?"
                params.append(competencia)
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            return {"concluidas": len([r for r in rows if r['status'] in ['DONE', 'DISCONSIDERED', 'FINALIZADO']]), "total": len(rows)}
    except Exception as e:
        return {"concluidas": 0, "total": 0}
    

@app.get("/api/dashboard/checklist")
def get_dashboard_checklist(month: str = Query(None)):
    if not month: month = datetime.now().strftime("%Y-%m")

    tarefas = executar_query_dict("SELECT * FROM dashboard_checklist ORDER BY tipo DESC, tarefa_nome ASC")
    checklist_final = []
    
    for t in tarefas:
        item = dict(t)
        if item['tipo'] == 'AUTO':
            progresso = buscar_progresso_gestta_remoto(item['termo_gestta'], item['dia_vencimento'], month)
            item['concluidas'], item['total'] = progresso['concluidas'], progresso['total']
            item['status_manual'] = 1 if (progresso['total'] > 0 and progresso['concluidas'] == progresso['total']) else 0
        else:
            status_row = executar_query_dict("SELECT status_manual, usuario_conclusao, data_conclusao FROM checklist_mes WHERE id_tarefa = ? AND competencia = ?", (item['id'], month))
            if status_row:
                item['status_manual'] = status_row[0]['status_manual']
                item['usuario_conclusao'] = status_row[0]['usuario_conclusao']
                item['data_conclusao'] = status_row[0]['data_conclusao']
            else:
                item['status_manual'], item['usuario_conclusao'], item['data_conclusao'] = 0, None, None
            item['concluidas'] = item['status_manual']
            item['total'] = 1
        checklist_final.append(item)
    return checklist_final


@app.put("/api/dashboard/checklist/{item_id}/toggle")
def toggle_checklist_manual(item_id: int, req: ChecklistToggleRequest):
    data_atual = datetime.now().strftime("%Y-%m-%d %H:%M") if req.status == 1 else None
    usuario = req.usuario if req.status == 1 else None
    executar_update("""
        INSERT INTO checklist_mes (id_tarefa, competencia, status_manual, usuario_conclusao, data_conclusao)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(id_tarefa, competencia) DO UPDATE SET status_manual = excluded.status_manual, usuario_conclusao = excluded.usuario_conclusao, data_conclusao = excluded.data_conclusao
    """, (item_id, req.month, req.status, usuario, data_atual))
    return {"mensagem": "Status atualizado"}


def popular_checklist_inicial():
    executar_update("DELETE FROM dashboard_checklist")
    
    tarefas = [
        # AUTOMATIZADAS GESTTA
        ('ISS PRESTADOS (03)', 'AUTO', 'ISS PRESTADOS (03)', None), 
        ('ISS (08)', 'AUTO', 'ISS (08)', None), 
        ('ISS (10)', 'AUTO', 'ISS (10)', None),
        ('ISS (15)', 'AUTO', 'ISS (15)', None),
        ('ISS (20)', 'AUTO', 'ISS (20)', None),
        ('ISS FIXO', 'AUTO', 'ISS FIXO', None),
        ('SINTEGRA', 'AUTO', 'SINTEGRA', None),        
        ('IRRF 3208 | ALUGUEL', 'AUTO', 'ALUGUEL', None),
        ('ISS RETIDO NA FONTE | RPA (10)', 'AUTO', 'ISS RETIDO NA FONTE | RPA (10)', None),
        ('ISS RETIDO NA FONTE | RPA (20)', 'AUTO', 'ISS RETIDO NA FONTE | RPA (20)', None),
        ('ISS RPA (20)', 'AUTO', 'ISS RPA (20)', None),
        ('RETENÇÃO ISS | SERVIÇOS TOMADOS (10)', 'AUTO', 'RETENÇÃO ISS | SERVIÇOS TOMADOS (10)', None),
        ('RETENÇÃO ISS | SERVIÇOS TOMADOS (15)', 'AUTO', 'RETENÇÃO ISS | SERVIÇOS TOMADOS (15)', None),
        ('RETENÇÃO ISS | SERVIÇOS TOMADOS (20)', 'AUTO', 'RETENÇÃO ISS | SERVIÇOS TOMADOS (20)', None),

        # MANUAIS   
        ('Inicio da entrega de empresas com Prioridade Contabil', 'MANUAL', None, None),
        ('Baixa dos documentos nos sistemas - CONTA AZUL | OMIE', 'MANUAL', None, None),
        ('Envio ISS FIXO', 'MANUAL', None, None),
        ('Envio Reinf prestados', 'MANUAL', None, None),
        ('Envio antecipado DCTFWEB - Esquadra | Talogy | LW', 'MANUAL', None, None),
        ('Revisão e envio Retenção', 'MANUAL', None, None),
        ('Aviso ao clientes sobre as guias não visualizadas DAS', 'MANUAL', None, None), 
        ('Aviso ao clientes sobre as guias não visualizadas PIS|COFINS', 'MANUAL', None, None),
        ('Notas SCRYTA Rotina automatica', 'MANUAL', None, None), 
        ('Agendamento de coletas', 'MANUAL', None, None)
    ]
    for nome, tipo, termo, dia in tarefas: 
        executar_update("INSERT INTO dashboard_checklist (tarefa_nome, tipo, termo_gestta, dia_vencimento) VALUES (?, ?, ?, ?)", (nome, tipo, termo, dia))

popular_checklist_inicial()

