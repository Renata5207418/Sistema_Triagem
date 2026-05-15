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
from fastapi.responses import StreamingResponse, FileResponse
from fastapi import FastAPI, HTTPException, Query, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import logging
from logging.handlers import TimedRotatingFileHandler
import shutil

RAIZ_PROJETO = Path(__file__).parent.parent
sys.path.append(str(RAIZ_PROJETO))

try:
    from dashboard.aws_service import buscar_xmls_aws
except ModuleNotFoundError:
    from aws_service import buscar_xmls_aws

from auth import auth
from db.db_dominio import DatabaseConnection
from db.db_resiliencia import db

app = FastAPI(title="API Triagem Cloud", description="Backend para o Dashboard RPA")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:5175",

        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "http://127.0.0.1:5175",

        "http://10.0.0.142:5173",
        "http://10.0.0.142:5174",
        "http://10.0.0.142:5175",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)

DB_PATH = RAIZ_PROJETO / "banco_rpa.db"


# ==========================================
# CONFIGURAÇÃO DE LOGS DA API
# ==========================================
pasta_logs = RAIZ_PROJETO / "logs"
pasta_logs.mkdir(exist_ok=True)

arquivo_log_api = pasta_logs / "api_backend.log"

file_handler_api = TimedRotatingFileHandler(
    filename=arquivo_log_api,
    when="midnight",
    interval=1,
    backupCount=30,
    encoding='utf-8'
)
file_handler_api.suffix = "%Y-%m-%d.log"

console_handler_api = logging.StreamHandler(sys.stdout)

# Configura o logger global da API
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] API: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[file_handler_api, console_handler_api]
)

class VerificacaoRequest(BaseModel): 
    usuario: str


class SenhaRequest(BaseModel): 
    senha: str


class AtualizarCategoriaRequest(BaseModel):
    nova_categoria: str


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
    colunas_dominio = [
        'cpf_cnpj', 'razao_social', 'uf', 'municipio', 'endereco', 
        'numero_documento', 'serie', 'data_emissao', 'situacao', 
        'acumulador', 'cfop', 'valor_servicos', 'valor_descontos', 
        'valor_contabil', 'base_calculo', 'aliquota_iss', 'valor_iss_normal', 
        'valor_iss_retido', 'valor_irrf', 'valor_pis', 'valor_cofins', 
        'valor_csll', 'valor_crf', 'valor_inss', 'codigo_item', 
        'quantidade', 'valor_unitario', 'tomador'
    ]

    for col in colunas_dominio:
        if col not in df.columns: df[col] = ''
    df = df[colunas_dominio]
    df['situacao'] = '0' 
    
    df_csv = df.copy()
    
    # 1. FAXINA DE TEXTO: Evita que o Excel pule de linha ou crie colunas falsas
    cols_texto = ['razao_social', 'uf', 'municipio']
    for col in cols_texto:
        df_csv[col] = df_csv[col].apply(lambda x: str(x).replace('\n', ' ').replace('\r', ' ').replace(';', ',').strip() if pd.notnull(x) else '')

    # 2. PROTEÇÃO DE CNPJ: O ="" impede o Excel de comer o zero a esquerda
    df_csv['cpf_cnpj'] = df_csv['cpf_cnpj'].apply(lambda x: f'="{x}"' if pd.notnull(x) and str(x).strip() else '=""') 
    df_csv['tomador'] = df_csv['tomador'].apply(lambda x: f'="{x}"' if pd.notnull(x) and str(x).strip() else '=""')
    
    # 3. O TRATOR DE MOEDAS: Arruma o 15,190,37 ou o 1.500.00
    def limpar_moeda_robusta(valor):
        if pd.isna(valor) or not str(valor).strip(): return ''
        v = str(valor).replace('R$', '').strip()
        v = re.sub(r'[^\d\,\.]', '', v)
        if not v: return ''
        if ',' not in v and '.' not in v: return v + ',00'
        sep = max(v.rfind(','), v.rfind('.'))
        inteiro = v[:sep].replace('.', '').replace(',', '')
        decimal = v[sep+1:]
        if len(decimal) == 1: decimal += '0'
        return f"{inteiro},{decimal[:2]}"

    colunas_valores = ['valor_servicos', 'valor_contabil', 'base_calculo', 'valor_irrf', 'valor_pis', 'valor_cofins', 'valor_csll', 'valor_crf', 'valor_inss']
    
    for col in colunas_valores: 
        df_csv[col] = df_csv[col].apply(limpar_moeda_robusta)

    header_pt = ['CPF/CNPJ', 'Razão Social', 'UF', 'Município', 'Endereço', 'Número Documento', 'Série', 'Data', 'Situação', 'Acumulador', 'CFOP', 'Valor Serviços', 'Valor Descontos', 'Valor Contábil', 'Base de Calculo', 'Alíquota ISS', 'Valor ISS Normal', 'Valor ISS Retido', 'Valor IRRF', 'Valor PIS', 'Valor COFINS', 'Valor CSLL', 'Valo CRF', 'Valor INSS', 'Código do Item', 'Quantidade', 'Valor Unitário', 'Tomador']

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
        csv_geral = df_csv.to_csv(index=False, sep=';', header=header_pt, encoding='utf-8-sig')
        zipf.writestr("GERAL_IMPORTACAO.csv", csv_geral)
        
        for tomador, group in df_csv.groupby('tomador'):
            cnpj_clean = re.sub(r'[^0-9]', '', str(tomador))
            if not cnpj_clean: cnpj_clean = "DESCONHECIDO"
            csv_indiv = group.to_csv(index=False, sep=';', header=header_pt, encoding='utf-8-sig')
            zipf.writestr(f"TOMADOS_CLI_{cnpj_clean}.csv", csv_indiv)

    zip_buffer.seek(0)
    return StreamingResponse(zip_buffer, media_type="application/zip", headers={"Content-Disposition": f"attachment; filename=OS{os_id}_Planilhas_Domínio.zip"})


@app.get("/api/resumo")
def get_resumo_dashboard(month: str = Query(None)):
    if not month: 
        month = datetime.now().strftime("%Y-%m")
        
    month_like = f"{month}%"

    try:
        total_downloads = db.executar_query_dict("SELECT COUNT(*) as total FROM downloads WHERE ultima_tentativa LIKE ?", (month_like,))[0]['total']
        empresas_ativas = db.executar_query_dict("SELECT COUNT(DISTINCT TRIM(CAST(cod_emp AS TEXT))) as total FROM downloads WHERE cod_emp IS NOT NULL AND cod_emp != '' AND ultima_tentativa LIKE ?", (month_like,))[0]['total']
        os_sem_anexos = db.executar_query_dict("SELECT COUNT(*) as total FROM downloads WHERE (qtd_anexos_esperados = 0 OR qtd_anexos_esperados IS NULL) AND ultima_tentativa LIKE ?", (month_like,))[0]['total']

        query_erros = """
            SELECT COUNT(*) as total
            FROM documentos_triados dt
            JOIN downloads d ON dt.id_ticket = d.id_ticket
            WHERE d.ultima_tentativa LIKE ?
              AND (
                  dt.status IN ('ERRO', 'ATENCAO', 'PENDENTE_SENHA', 'RESOLVIDO_UPLOAD')
                  OR COALESCE(dt.status_tomados, '') IN ('ERRO_EXTRACAO_IA', 'ERRO_TOMADOS', 'RESOLVIDO_UPLOAD')
              )
        """
        erros_atencao = db.executar_query_dict(query_erros, (month_like,))[0]['total']

        query_sucesso = """
            SELECT COUNT(*) as total
            FROM documentos_triados dt
            JOIN downloads d ON dt.id_ticket = d.id_ticket
            WHERE d.ultima_tentativa LIKE ?
              AND NOT (
                  (dt.status IN ('ERRO', 'ATENCAO', 'PENDENTE_SENHA') AND dt.categoria_ia IN ('revisao_manual', 'documento_unificado', 'ERRO', 'DESCONHECIDO'))
                  OR COALESCE(dt.status_tomados, '') IN ('ERRO_EXTRACAO_IA', 'ERRO_TOMADOS')
              )
        """
        sucesso_triagem = db.executar_query_dict(query_sucesso, (month_like,))[0]['total']

        top_empresas = db.executar_query_dict("""
            SELECT 
                TRIM(CAST(d.cod_emp AS TEXT)) as cod, 
                d.nome_emp as nome, 
                COUNT(DISTINCT d.id_ticket) as qtd_os,
                COUNT(dt.id) as qtd_docs
            FROM downloads d
            LEFT JOIN documentos_triados dt ON dt.id_ticket = d.id_ticket
            WHERE d.cod_emp IS NOT NULL AND d.cod_emp != '' AND d.ultima_tentativa LIKE ?
            GROUP BY TRIM(CAST(d.cod_emp AS TEXT)), d.nome_emp
            ORDER BY qtd_os DESC, qtd_docs DESC
            LIMIT 5
        """, (month_like,))
        
        # --- CÁLCULO DE PERFORMANCE INTELIGENTE ---
        agora = datetime.now()
        mes_atual = agora.strftime("%Y-%m")
        
        if month == mes_atual:
            # Se é o mês atual, foca nas últimas 24h para detectar lentidão (Operacional)
            query_perf = """
                SELECT AVG((julianday(t.data_conclusao) - julianday(d.ultima_tentativa)) * 1440) as tempo 
                FROM downloads d 
                JOIN tickets_triados t ON d.id_ticket = t.id_ticket 
                WHERE t.data_conclusao >= datetime('now', '-1 day')
                  AND t.data_conclusao IS NOT NULL
                  AND ((julianday(t.data_conclusao) - julianday(d.ultima_tentativa)) * 1440) < 120
            """
            label_tempo = "Performance (24h)"
        else:
            # Se é um mês passado, mostra a média do mês todo (Gerencial)
            query_perf = """
                SELECT AVG((julianday(t.data_conclusao) - julianday(d.ultima_tentativa)) * 1440) as tempo 
                FROM downloads d 
                JOIN tickets_triados t ON d.id_ticket = t.id_ticket 
                WHERE d.ultima_tentativa LIKE ? 
                  AND t.data_conclusao IS NOT NULL
                  AND ((julianday(t.data_conclusao) - julianday(d.ultima_tentativa)) * 1440) < 120
            """
            label_tempo = "Média Mensal"

        res_perf = db.executar_query_dict(query_perf, (month_like,) if month != mes_atual else ())
        tempo_medio = res_perf[0]['tempo'] if res_perf and res_perf[0]['tempo'] else 0
        
       # 2. RANKING DE ERROS (Agora com contagem segregada para o gráfico)
        query_ranking_erros = """
            SELECT 
                d.nome_emp as nome,
                COUNT(*) as total,
                SUM(CASE WHEN dt.status = 'PENDENTE_SENHA' THEN 1 ELSE 0 END) as qtd_senha,
                SUM(CASE WHEN dt.status_tomados IN ('ERRO_EXTRACAO_IA', 'ERRO_TOMADOS') THEN 1 ELSE 0 END) as qtd_ia,
                SUM(CASE 
                    WHEN dt.status = 'RESOLVIDO_UPLOAD' THEN 1 
                    WHEN dt.status IN ('ERRO', 'ATENCAO') AND dt.status_tomados NOT IN ('ERRO_EXTRACAO_IA', 'ERRO_TOMADOS') AND dt.status != 'PENDENTE_SENHA' THEN 1 
                    ELSE 0 
                END) as qtd_outros
            FROM documentos_triados dt 
            JOIN downloads d ON d.id_ticket = dt.id_ticket 
            WHERE d.ultima_tentativa LIKE ? 
              AND (
                  dt.status IN ('ERRO', 'ATENCAO', 'PENDENTE_SENHA', 'RESOLVIDO_UPLOAD')
                  OR COALESCE(dt.status_tomados, '') IN ('ERRO_EXTRACAO_IA', 'ERRO_TOMADOS', 'RESOLVIDO_UPLOAD')
              )
            GROUP BY d.nome_emp 
            ORDER BY total DESC 
            LIMIT 5
        """
        ranking_problemas = db.executar_query_dict(query_ranking_erros, (month_like,))
        
        resumo = {
            "total_processado": total_downloads, 
            "empresas_ativas": empresas_ativas, 
            "os_sem_anexos": os_sem_anexos,
            "sucesso_triagem": sucesso_triagem, 
            "erros_atencao": erros_atencao, 
            "pendente_senha": 0, 
            "top_empresas": top_empresas,
            "tempo_medio_minutos": round(tempo_medio, 1),
            "ranking_problemas": ranking_problemas,
            "label_tempo": label_tempo
        }
        
        return resumo
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/triagem/auditoria")
def get_auditoria_triagem():
    query = """
        SELECT dt.id, d.id_ticket as os, dt.nome_original as arquivo, dt.categoria_ia, dt.status as status_triagem, dt.status_tomados,
            d.status as status_download, d.cod_emp as cod_empresa, d.nome_emp as nome_empresa, d.descricao as mensagem,
            d.qtd_anexos_esperados, d.verificado, d.ultima_tentativa as data_os, d.auditado_por, d.data_auditoria
        FROM downloads d LEFT JOIN documentos_triados dt ON d.id_ticket = dt.id_ticket ORDER BY d.id_ticket DESC
    """
    try: return db.executar_query_dict(query)
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/os/{os_id}/verificar")
def verificar_os(os_id: int, request: VerificacaoRequest):
    os_atual = db.executar_query_dict("SELECT status FROM downloads WHERE id_ticket = ?", (os_id,))
    if not os_atual:
        raise HTTPException(status_code=404, detail="OS não encontrada.")
    status_atual = os_atual[0]['status']

    if status_atual == 'ALERTA_HUMANO':
        db.executar_update("UPDATE downloads SET status = 'SUCESSO' WHERE id_ticket = ?", (os_id,))
        db.executar_update("DELETE FROM tickets_triados WHERE id_ticket = ?", (os_id,))
        return {"mensagem": "OS enviada para reprocessamento!"}
    else:
        data_atual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db.executar_update("UPDATE downloads SET verificado = 1, auditado_por = ?, data_auditoria = ? WHERE id_ticket = ?", 
                        (request.usuario, data_atual, os_id))
        return {"mensagem": "OS validada com sucesso!"}
    

@app.put("/api/os/{os_id}/desmarcar")
def desmarcar_os(os_id: int):
    db.executar_update("UPDATE downloads SET verificado = 0 WHERE id_ticket = ?", (os_id,))
    return {"mensagem": "OS desmarcada."}


@app.get("/api/erros/senhas")
def get_erros_senha():
    return db.executar_query_dict("SELECT id, id_ticket as os, nome_original, pasta_destino FROM documentos_triados WHERE status = 'ERRO' AND motivo_erro LIKE '%Senha%'")


@app.post("/api/documentos/{doc_id}/senha")
def resolver_senha(doc_id: int, request: SenhaRequest):
    db.executar_update("UPDATE documentos_triados SET status = 'PENDENTE_SENHA', motivo_erro = 'Aguardando Robô' WHERE id = ?", (doc_id,))
    return {"mensagem": "Senha registrada."}


@app.put("/api/documentos/{doc_id}/categoria")
def atualizar_categoria(doc_id: int, request: AtualizarCategoriaRequest):
    db.executar_update("UPDATE documentos_triados SET categoria_ia = ?, status = 'SUCESSO_MANUAL' WHERE id = ?", (request.nova_categoria, doc_id))
    return {"mensagem": "Categoria atualizada"}


# ==========================================
# ROTAS DA MALHA FISCAL 
# ==========================================

def converter_valor_brl_para_float(valor):
    try:
        if valor is None: return 0.0
        if isinstance(valor, (int, float)): return float(valor)
        return float(str(valor).replace('.', '').replace(',', '.'))
    except:
        return 0.0


def limpar_numero_nota(numero):
    if not numero: return ""
    num_limpo = re.sub(r'[^0-9]', '', str(numero)).lstrip('0')
    return num_limpo if num_limpo else "0"


def sincronizar_aws_internamente(cod_empresa: str, competencia: str, forcar: bool = False):
    cod_empresa = str(cod_empresa).strip()

    if not forcar and db.malha_ja_sincronizada(cod_empresa, competencia):
        return {
            "sincronizou": False,
            "mensagem": "Malha já sincronizada anteriormente.",
            "ultima_atualizacao": db.get_ultima_atualizacao_malha(cod_empresa, competencia)
        }

    db_dom = DatabaseConnection()

    if not db_dom.connect():
        raise Exception("Falha ao conectar na Domínio.")

    try:
        cnpjs_grupo = db_dom.obter_cnpjs_do_grupo(cod_empresa)
    finally:
        db_dom.close()

    if not cnpjs_grupo:
        raise Exception("CNPJ não encontrado.")

    notas_aws = buscar_xmls_aws(cnpjs_grupo[0], competencia)
    data_sync = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    db.limpar_malha_empresa_competencia(cod_empresa, competencia)

    notas_triabot = db.listar_tomados_empresa_competencia(cod_empresa, competencia)
    notas_triabot_pendentes = list(notas_triabot)

    for nota_aws in notas_aws:
        cnpj_aws = re.sub(r'[^0-9]', '', str(nota_aws.get("cnpj", "")))
        num_aws_limpo = limpar_numero_nota(nota_aws.get("numero"))
        valor_aws = float(nota_aws.get("valor", 0.0))

        match_encontrado = None
        status = "FALTA_NO_TRIABOT"

        for tb in notas_triabot_pendentes:
            cnpj_tb = re.sub(r'[^0-9]', '', str(tb.get("cpf_cnpj", "")))
            num_tb_limpo = limpar_numero_nota(tb.get("numero_documento"))
            if cnpj_tb == cnpj_aws and num_tb_limpo == num_aws_limpo:
                match_encontrado = tb
                break

        if not match_encontrado:
            for tb in notas_triabot_pendentes:
                cnpj_tb = re.sub(r'[^0-9]', '', str(tb.get("cpf_cnpj", "")))
                valor_tb = converter_valor_brl_para_float(tb.get("valor_contabil"))
                if cnpj_tb == cnpj_aws and abs(valor_tb - valor_aws) <= 0.01:
                    match_encontrado = tb
                    break

        os_id = None
        if match_encontrado:
            valor_tb = converter_valor_brl_para_float(match_encontrado.get("valor_contabil"))
            status = "BATEU" if abs(valor_tb - valor_aws) <= 0.01 else "DIVERGENCIA_VALOR"
            notas_triabot_pendentes.remove(match_encontrado)

            os_id = match_encontrado.get("id_ticket")
            if not os_id:
                os_query = db.executar_query_dict(
                    "SELECT MAX(id_ticket) as os_id FROM resultados_tomados WHERE numero_documento = ? AND cpf_cnpj = ?",
                    (match_encontrado.get("numero_documento"), match_encontrado.get("cpf_cnpj"))
                )
                if os_query and os_query[0]['os_id']:
                    os_id = os_query[0]['os_id']

        db.inserir_nota_malha(
            cod_empresa=cod_empresa,
            competencia=competencia,
            numero_nota=nota_aws["numero"],
            cnpj_prestador=nota_aws["cnpj"], 
            valor_nota=valor_aws,
            status_conciliacao=status,
            origem="AWS",
            data_atualizacao=data_sync
        )

        if os_id:
            db.executar_update(
                "UPDATE malha_fiscal_tomadas SET os_onvio = ? WHERE cod_empresa = ? AND competencia = ? AND numero_nota = ? AND cnpj_prestador = ?",
                (str(os_id), cod_empresa, competencia, nota_aws["numero"], nota_aws["cnpj"])
            )

    for nota_tb in notas_triabot_pendentes:
        num_nota = nota_tb.get("numero_documento", "S/N")
        cnpj_prest = nota_tb.get("cpf_cnpj", "")
        
        db.inserir_nota_malha(
            cod_empresa=cod_empresa,
            competencia=competencia,
            numero_nota=num_nota,
            cnpj_prestador=cnpj_prest,
            valor_nota=converter_valor_brl_para_float(nota_tb.get("valor_contabil")),
            status_conciliacao="NOTA_FANTASMA_TRIABOT",
            origem="TRIABOT",
            data_atualizacao=data_sync
        )

        os_id = nota_tb.get("id_ticket")
        if not os_id:
            os_query = db.executar_query_dict(
                "SELECT MAX(id_ticket) as os_id FROM resultados_tomados WHERE numero_documento = ? AND cpf_cnpj = ?",
                (num_nota, cnpj_prest)
            )
            if os_query and os_query[0]['os_id']:
                os_id = os_query[0]['os_id']

        if os_id:
            db.executar_update(
                "UPDATE malha_fiscal_tomadas SET os_onvio = ? WHERE cod_empresa = ? AND competencia = ? AND numero_nota = ? AND cnpj_prestador = ?",
                (str(os_id), cod_empresa, competencia, num_nota, cnpj_prest)
            )

    return {
        "sincronizou": True,
        "mensagem": "Sincronização concluída.",
        "ultima_atualizacao": data_sync
    }


@app.post("/api/malha-fiscal/sincronizar-inicial/{cod_empresa}/{competencia}")
def sincronizar_malha_inicial(cod_empresa: str, competencia: str):
    try:
        resultado = sincronizar_aws_internamente(cod_empresa=cod_empresa, competencia=competencia, forcar=False)
        return resultado
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    

@app.get("/api/malha-fiscal/resumo/{competencia}")
def get_resumo_malha(competencia: str):
    comp_like = f"{competencia}%"
    query = """
        WITH clientes_com_tomadas AS (
            SELECT 
                TRIM(CAST(d.cod_emp AS TEXT)) as cod_emp, 
                d.nome_emp, 
                COUNT(dt.id) as total_triabot_real
            FROM downloads d 
            INNER JOIN documentos_triados dt 
                ON d.id_ticket = dt.id_ticket
            WHERE d.ultima_tentativa LIKE ? 
                AND dt.categoria_ia = 'nota_servico'
                AND dt.pasta_destino = 'NOTAS_DE_SERVICO/TOMADAS'
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
            WHERE competencia = ? 
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
        LEFT JOIN resumo_malha r 
            ON c.cod_emp = r.cod_empresa
        LEFT JOIN malha_fiscal_validacao v 
            ON c.cod_emp = TRIM(CAST(v.cod_empresa AS TEXT)) 
           AND v.competencia = ?
        ORDER BY c.nome_emp ASC
    """
    return db.executar_query_dict(query, (comp_like, competencia, competencia))


@app.get("/api/malha-fiscal/detalhes/{cod_empresa}/{competencia}")
def get_detalhes_malha(cod_empresa: str, competencia: str):
    query = """
        SELECT 
            m.*, 
            COALESCE(
                NULLIF(m.os_onvio, ''), 
                NULLIF(m.os_onvio, 'None'),
                (
                    SELECT MAX(r.id_ticket)
                    FROM resultados_tomados r
                    WHERE r.numero_documento = m.numero_nota 
                      AND r.cpf_cnpj = m.cnpj_prestador 
                      AND r.id_ticket IN (
                          SELECT id_ticket 
                          FROM downloads 
                          WHERE TRIM(CAST(cod_emp AS TEXT)) = TRIM(CAST(m.cod_empresa AS TEXT))
                      )
                )
            ) as os_onvio
        FROM malha_fiscal_tomadas m 
        WHERE TRIM(CAST(m.cod_empresa AS TEXT)) = ? 
          AND m.competencia = ? 
        ORDER BY m.status_conciliacao DESC
    """
    return db.executar_query_dict(query, (str(cod_empresa).strip(), competencia))


@app.post("/api/malha-fiscal/sincronizar/{cod_empresa}/{competencia}")
def sincronizar_malha_cliente(cod_empresa: str, competencia: str):
    try:
        resultado = sincronizar_aws_internamente(cod_empresa=cod_empresa, competencia=competencia, forcar=True)
        return resultado
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))  


# ==========================================
# ROTAS DE PRIORIDADE CONTÁBIL (FECHAMENTOS)
# ==========================================
class EmpresaConfigRequest(BaseModel):
    codigo: str 
    apelido: str
    tipo: str 
    competencia: Optional[str] = None

@app.get("/api/dominio/empresa/buscar")
def buscar_empresa_inteligente(termo: str = Query(..., min_length=1)):
    db_dom = DatabaseConnection()
    if not db_dom.connect():
        raise HTTPException(status_code=500, detail="Erro ao conectar na Domínio")
    
    try:
        cursor = db_dom.conn.cursor()
        if termo.isdigit():
            query = "SELECT codi_emp, apel_emp, nome_emp FROM bethadba.geempre WHERE codi_emp = ?"
            cursor.execute(query, (termo,))
        else:
            busca_fuzzy = f"%{termo.upper()}%"
            query = "SELECT TOP 20 codi_emp, apel_emp, nome_emp FROM bethadba.geempre WHERE apel_emp LIKE ? OR nome_emp LIKE ? ORDER BY apel_emp ASC"
            cursor.execute(query, (busca_fuzzy, busca_fuzzy))
        
        rows = cursor.fetchall()
        resultados = []
        for row in rows:
            codi_emp = str(row[0]).strip()
            apel_emp = str(row[1]).strip().upper() if row[0] else ""
            nome_emp = str(row[2]).strip().upper() if row[1] else ""
            resultados.append({"codigo": codi_emp, "apelido": apel_emp if len(apel_emp) > 2 else nome_emp})
        return resultados
    except Exception as e:
        logging.error(f"Erro ao buscar empresa '{termo}' na Domínio: {e}") 
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db_dom.close()

@app.get("/api/prioridades")
def get_prioridades(month: str = Query(None)):
    return db.executar_query_dict("SELECT codigo, apelido, tipo, ativa FROM empresas_config WHERE ativa = 1 AND (tipo = 'VITALICIA' OR (tipo = 'MENSAL' AND competencia_unica = ?))", (month,))

@app.get("/api/prioridades/config")
def get_todas_configs():
    return db.executar_query_dict("SELECT * FROM empresas_config ORDER BY ativa DESC, apelido ASC")

@app.post("/api/prioridades/config")
def save_empresa_config(req: EmpresaConfigRequest):
    db.executar_update("""
        INSERT INTO empresas_config (codigo, apelido, tipo, competencia_unica, ativa) 
        VALUES (?, ?, ?, ?, 1) 
        ON CONFLICT(apelido) DO UPDATE SET codigo = excluded.codigo, tipo = excluded.tipo, competencia_unica = excluded.competencia_unica, ativa = 1
    """, (req.codigo.strip(), req.apelido.strip().upper(), req.tipo, req.competencia))
    return {"mensagem": "Configuração salva"}

@app.put("/api/prioridades/config/{apelido}/toggle")
def toggle_empresa(apelido: str):
    db.executar_update("UPDATE empresas_config SET ativa = 1 - ativa WHERE apelido = ?", (apelido,))
    return {"mensagem": "Status alterado"}

@app.delete("/api/prioridades/config/{apelido}")
def delete_empresa_config(apelido: str):
    db.executar_update("DELETE FROM empresas_config WHERE apelido = ?", (apelido,))
    return {"mensagem": "Empresa removida"}

class RenameEmpresaRequest(BaseModel): 
    novo_apelido: str

@app.put("/api/prioridades/config/{apelido}/renomear")
def renomear_empresa_config(apelido: str, req: RenameEmpresaRequest):
    novo_nome = req.novo_apelido.strip().upper()
    db.executar_update("UPDATE empresas_config SET apelido = ? WHERE apelido = ?", (novo_nome, apelido))
    db.executar_update("UPDATE controle_pastas SET apelido = ? WHERE apelido = ?", (novo_nome, apelido))
    return {"mensagem": "Renomeado!"}


@app.get("/api/fechamentos")
def get_fechamentos(month: str = Query(None)):
    if not month: 
        month = datetime.now().strftime("%Y-%m")
        
    month_like = f"{month}%"
        
    pastas_db = db.executar_query_dict("SELECT * FROM controle_pastas WHERE competencia = ?", (month,))
    pastas_dict = {(p['apelido'], p['competencia']): dict(p) for p in pastas_db}    
    
    query_os = """
        SELECT d.id_ticket, d.cod_emp, d.ultima_tentativa, d.verificado as os_verificado, 
               d.data_auditoria as os_data, e.apelido, m.verificado as malha_verificado, 
               m.data_auditoria as malha_data
        FROM downloads d 
        JOIN empresas_config e ON TRIM(CAST(e.codigo AS TEXT)) = TRIM(CAST(d.cod_emp AS TEXT))
        LEFT JOIN malha_fiscal_validacao m ON TRIM(CAST(m.cod_empresa AS TEXT)) = TRIM(CAST(d.cod_emp AS TEXT)) 
             AND m.competencia = ?
        WHERE d.ultima_tentativa LIKE ?
          AND EXISTS (
              SELECT 1 FROM documentos_triados dt 
              WHERE dt.id_ticket = d.id_ticket 
                AND dt.categoria_ia = 'nota_servico'
          )
    """
    try: 
        oss = db.executar_query_dict(query_os, (month, month_like))
    except Exception as e: 
        logging.error(f"Erro em fechamentos: {e}")
        oss = [] 
        
    for os_item in oss:
        comp = os_item['ultima_tentativa'][:7] 
        apelido = os_item['apelido']
        key = (apelido, comp)
        if key not in pastas_dict: 
            pastas_dict[key] = {"apelido": apelido, "competencia": comp, "pasta_liberada_em": None, "documentos_json": "[]"}
        
        docs_salvos = json.loads(pastas_dict[key]['documentos_json'])
        docs_limpos = [d for d in docs_salvos if not (d.get("isAuto") == True or str(d.get("nome", "")).startswith("OS #"))]
        
        # AQUI ESTÁ A CORREÇÃO DE REGRA DE NEGÓCIO: Só olha para a aba da Malha!
        is_validado = str(os_item['malha_verificado']) == '1'
        data_auditoria = os_item['malha_data'] if is_validado else None
        
        docs_limpos.append({
            "id": f"AUTO-{os_item['id_ticket']}", 
            "nome": f"OS #{os_item['id_ticket']}", 
            "recebido": os_item['ultima_tentativa'][:10], 
            "liberado_em": data_auditoria, 
            "isAuto": True
        })
        pastas_dict[key]['documentos_json'] = json.dumps(docs_limpos)
        
    return list(pastas_dict.values())


@app.post("/api/fechamentos")
def save_fechamento(payload: dict):
    docs = json.loads(payload.get("documentos_json", "[]"))
    docs_manuais = [d for d in docs if not (d.get("isAuto") == True or str(d.get("nome", "")).startswith("OS #"))]
    apelido, competencia, liberado_em = payload["apelido"], payload["competencia"], payload.get("pasta_liberada_em")
    
    row = db.executar_query_dict("SELECT id FROM controle_pastas WHERE apelido = ? AND competencia = ?", (apelido, competencia))
    if row: 
        db.executar_update("UPDATE controle_pastas SET pasta_liberada_em = ?, documentos_json = ?, updated_at = datetime('now') WHERE id = ?", (liberado_em, json.dumps(docs_manuais), row[0]['id']))
    else: 
        db.executar_update("INSERT INTO controle_pastas (apelido, competencia, pasta_liberada_em, documentos_json, updated_at) VALUES (?, ?, ?, ?, datetime('now'))", (apelido, competencia, liberado_em, json.dumps(docs_manuais)))
        
    row_emp = db.executar_query_dict("SELECT codigo FROM empresas_config WHERE apelido = ?", (apelido,))
    if not row_emp:
        raise HTTPException(status_code=404, detail="Empresa não configurada na carteira.")
    
    cod_empresa = row_emp[0]['codigo']
    
    if liberado_em is None: 
        db.executar_update("UPDATE malha_fiscal_validacao SET verificado = 0 WHERE TRIM(CAST(cod_empresa AS TEXT)) = ? AND competencia = ?", (cod_empresa, competencia))
    else: 
        db.executar_update("""
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


class TarefaChecklist(BaseModel):
    tarefa_nome: str
    tipo: str
    termo_gestta: Optional[str] = None
    dia_vencimento: Optional[int] = None
    ativa: int = 1

# Rota para o modal listar TODAS as tarefas (ativas e inativas)
@app.get("/api/dashboard/checklist-config")
def listar_config_checklist():
    return db.executar_query_dict("SELECT * FROM dashboard_checklist ORDER BY ativa DESC, tipo DESC, tarefa_nome ASC")

# Rota para criar ou editar
@app.post("/api/dashboard/checklist-config")
def salvar_config_checklist(tarefa: TarefaChecklist, id_tarefa: int = Query(None)):
    if id_tarefa:
        db.executar_update("""
            UPDATE dashboard_checklist 
            SET tarefa_nome = ?, tipo = ?, termo_gestta = ?, dia_vencimento = ?, ativa = ?
            WHERE id = ?
        """, (tarefa.tarefa_nome, tarefa.tipo, tarefa.termo_gestta, tarefa.dia_vencimento, tarefa.ativa, id_tarefa))
        return {"mensagem": "Tarefa atualizada!"}
    else:
        db.executar_update("""
            INSERT INTO dashboard_checklist (tarefa_nome, tipo, termo_gestta, dia_vencimento, ativa) 
            VALUES (?, ?, ?, ?, ?)
        """, (tarefa.tarefa_nome, tarefa.tipo, tarefa.termo_gestta, tarefa.dia_vencimento, tarefa.ativa))
        return {"mensagem": "Tarefa criada!"}

# Rota para "excluir" (Soft Delete)
@app.delete("/api/dashboard/checklist-config/{id_tarefa}")
def excluir_config_checklist(id_tarefa: int):
    db.executar_update("UPDATE dashboard_checklist SET ativa = 0 WHERE id = ?", (id_tarefa,))
    return {"mensagem": "Tarefa desativada com sucesso!"}
    

GESTTA_DB_PATH = os.getenv("GESTTA_DB_PATH")

def buscar_progresso_gestta_remoto(termo, dia=None, competencia=None):
    if not os.path.exists(GESTTA_DB_PATH): return {"concluidas": 0, "total": 0}
    try:
        with sqlite3.connect(GESTTA_DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # TRUQUE 1: Flexibilizar a busca (resolve o espaço do "ISS RPA (10)")
            termo_flexivel = termo.replace(" ", "%").replace("(", "%").replace(")", "%")
            
            query = "SELECT status FROM tasks WHERE name LIKE ?"
            params = [f"%{termo_flexivel}%"]
            
            if competencia:
                query += " AND strftime('%Y-%m', due_date) = ?"
                params.append(competencia)
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            # TRUQUE 2: Usar exatamente a regra do seu backend.py (FINISHED_STATUS)
            status_concluidos = ['DONE', 'DISCONSIDERED']
            
            concluidas = len([r for r in rows if str(r['status']).upper() in status_concluidos])
            
            return {"concluidas": concluidas, "total": len(rows)}
    except Exception as e:
        return {"concluidas": 0, "total": 0}


@app.get("/api/dashboard/checklist")
def get_dashboard_checklist(month: str = Query(None)):
    if not month: month = datetime.now().strftime("%Y-%m")

    tarefas = db.executar_query_dict("SELECT * FROM dashboard_checklist ORDER BY tipo DESC, tarefa_nome ASC")
    checklist_final = []
    
    for t in tarefas:
        item = dict(t)
        if item['tipo'] == 'AUTO':
            progresso = buscar_progresso_gestta_remoto(item['termo_gestta'], item['dia_vencimento'], month)
            item['concluidas'], item['total'] = progresso['concluidas'], progresso['total']
            item['status_manual'] = 1 if (progresso['total'] > 0 and progresso['concluidas'] == progresso['total']) else 0
        else:
            status_row = db.executar_query_dict("SELECT status_manual, usuario_conclusao, data_conclusao FROM checklist_mes WHERE id_tarefa = ? AND competencia = ?", (item['id'], month))
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
    db.executar_update("""
        INSERT INTO checklist_mes (id_tarefa, competencia, status_manual, usuario_conclusao, data_conclusao)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(id_tarefa, competencia) DO UPDATE SET status_manual = excluded.status_manual, usuario_conclusao = excluded.usuario_conclusao, data_conclusao = excluded.data_conclusao
    """, (item_id, req.month, req.status, usuario, data_atual))
    return {"mensagem": "Status atualizado"}

 
# ==========================================
# ROTAS DE TRATAMENTO DE ERROS E QUARENTENA
# ==========================================
@app.get("/api/quarentena/listar")
def listar_documentos_quarentena():
    query = """
        SELECT 
            dt.id, 
            d.id_ticket as os, 
            d.nome_emp as empresa, 
            dt.nome_original, 
            dt.categoria_ia, 
            dt.status, 
            dt.status_tomados,
            CASE
                WHEN dt.status_tomados = 'ERRO_EXTRACAO_IA' THEN 'Erro na extração dos dados da nota tomada'
                WHEN dt.status_tomados = 'ERRO_TOMADOS' THEN 'Erro no processamento de tomados'
                ELSE dt.motivo_erro
            END as motivo_erro,
            dt.pasta_destino
        FROM documentos_triados dt
        JOIN downloads d 
            ON dt.id_ticket = d.id_ticket
        WHERE 
            (
                dt.status IN ('ERRO', 'ATENCAO', 'PENDENTE_SENHA')
                AND dt.categoria_ia IN ('revisao_manual', 'documento_unificado', 'ERRO', 'DESCONHECIDO')
            )
            OR dt.status_tomados IN ('ERRO_EXTRACAO_IA', 'ERRO_TOMADOS')
        ORDER BY d.id_ticket DESC
    """
    return db.executar_query_dict(query)


@app.get("/api/quarentena/download/{doc_id}")
def baixar_documento_quarentena(doc_id: int):
    doc_info = db.executar_query_dict("""
        SELECT 
            dt.nome_final, 
            dt.nome_original, 
            dt.pasta_destino, 
            d.caminho_pasta
        FROM documentos_triados dt
        JOIN downloads d 
            ON dt.id_ticket = d.id_ticket
        WHERE dt.id = ?
    """, (doc_id,))

    if not doc_info:
        raise HTTPException(status_code=404, detail="Registro não encontrado no banco.")

    info = doc_info[0]

    caminho_pasta = info.get("caminho_pasta")
    pasta_destino = info.get("pasta_destino") or ""
    nome_final = info.get("nome_final") or ""
    nome_original = info.get("nome_original") or ""

    if not caminho_pasta:
        raise HTTPException(status_code=404, detail="Caminho da OS não encontrado no banco.")

    pasta_os = Path(caminho_pasta)

    if not pasta_os.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Pasta física da OS não encontrada: {pasta_os}"
        )

    candidatos = []

    if nome_final:
        candidatos.append(pasta_os / pasta_destino / nome_final)
        candidatos.append(pasta_os / nome_final)

    if nome_original:
        candidatos.append(pasta_os / pasta_destino / nome_original)
        candidatos.append(pasta_os / nome_original)

    for caminho in candidatos:
        try:
            if caminho.exists() and caminho.is_file():
                return FileResponse(
                    path=caminho,
                    filename=nome_original or caminho.name
                )
        except Exception:
            pass

    if nome_final:
        encontrados = list(pasta_os.rglob(nome_final))
        for encontrado in encontrados:
            if encontrado.is_file():
                return FileResponse(
                    path=encontrado,
                    filename=nome_original or encontrado.name
                )

    if nome_original:
        encontrados = list(pasta_os.rglob(nome_original))
        for encontrado in encontrados:
            if encontrado.is_file():
                return FileResponse(
                    path=encontrado,
                    filename=nome_original or encontrado.name
                )

    raise HTTPException(
        status_code=404,
        detail=(
            "Arquivo físico não encontrado. "
            f"OS={pasta_os}, pasta_destino={pasta_destino}, "
            f"nome_final={nome_final}, nome_original={nome_original}"
        )
    )


@app.post("/api/quarentena/upload-correcao/{os_id}")
async def upload_documentos_corrigidos(
    os_id: int, 
    id_doc_original: int = Form(...), 
    arquivos: List[UploadFile] = File(...)
):
    os_info = db.executar_query_dict("SELECT caminho_pasta FROM downloads WHERE id_ticket = ?", (os_id,))
    if not os_info or not os_info[0]['caminho_pasta']:
        raise HTTPException(status_code=404, detail="Pasta da OS não encontrada.")

    pasta_os = Path(os_info[0]['caminho_pasta'])

    for upload in arquivos:
        nome_seguro = Path(upload.filename).name
        caminho_novo = pasta_os / nome_seguro
        
        contador = 1
        while caminho_novo.exists():
            caminho_novo = pasta_os / f"parte_{contador}_{nome_seguro}"
            contador += 1
            
        with open(caminho_novo, "wb") as buffer:
            import shutil
            shutil.copyfileobj(upload.file, buffer)

    db.executar_update("""
        UPDATE documentos_triados 
        SET status = 'RESOLVIDO_UPLOAD',
            status_tomados = 'RESOLVIDO_UPLOAD',
            motivo_erro = 'Substituído por fatias'
        WHERE id = ?
    """, (id_doc_original,))

    db.executar_update(
        "DELETE FROM resultados_tomados WHERE id_documento = ?",
        (id_doc_original,)
    )

    db.executar_update(
        "DELETE FROM tickets_triados WHERE id_ticket = ?",
        (os_id,)
    )

    db.executar_update(
        "UPDATE downloads SET status = 'SUCESSO' WHERE id_ticket = ?",
        (os_id,)
    )
    return {"mensagem": f"{len(arquivos)} arquivo(s) processado(s) com sucesso!"}
