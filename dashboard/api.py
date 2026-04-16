import os
import io
import sys
import sqlite3
import zipfile
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
    """Gera um ZIP contendo apenas os TXTs convertidos para CSV e envia direto, sem salvar no disco."""
    
    query = "SELECT caminho_pasta FROM downloads WHERE id_ticket = ?"
    resultado = executar_query_dict(query, (os_id,))
    
    if not resultado or not resultado[0]['caminho_pasta']:
        raise HTTPException(status_code=404, detail="Pasta da OS não encontrada.")
    
    caminho_raiz = Path(resultado[0]['caminho_pasta'])
    pasta_tomadas = caminho_raiz / "NOTAS_DE_SERVICO" / "TOMADAS"
    
    if not pasta_tomadas.exists():
        raise HTTPException(status_code=404, detail="Pasta TOMADAS não encontrada.")

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for arquivo in pasta_tomadas.iterdir():
            if arquivo.is_file() and arquivo.suffix.lower() == '.txt':
                nome_excel = arquivo.stem + ".csv"
                zipf.write(arquivo, arcname=nome_excel)

    zip_buffer.seek(0)

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=OS{os_id}_Planilhas_Dominio.zip"}
    )

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
# ROTAS DA MALHA FISCAL
# ==========================================
@app.get("/api/malha-fiscal/resumo/{competencia}")
def get_resumo_malha(competencia: str):
    """Retorna os clientes, a contagem REAL do TriaBot e os erros após o Sync."""
    query = """
        WITH clientes_com_tomadas AS (
            -- 1. Clientes e a CONTAGEM REAL do TriaBot
            SELECT 
                d.cod_emp, 
                d.nome_emp,
                COUNT(dt.id) as total_triabot_real
            FROM downloads d
            INNER JOIN documentos_triados dt ON d.id_ticket = dt.id_ticket
            -- A CORREÇÃO ESTÁ AQUI: Usa LIKE em vez de igualdade exata
            WHERE strftime('%Y-%m', d.ultima_tentativa) = ?
              AND dt.categoria_ia LIKE '%nota%servico%'
            GROUP BY d.cod_emp, d.nome_emp
        ),
        resumo_malha AS (
            -- 2. Dados apenas da AWS/Cruzamento
            SELECT 
                cod_empresa,
                MAX(data_atualizacao) as ultima_sincronizacao,
                COUNT(CASE WHEN origem IN ('AWS', 'AMBOS') THEN 1 END) as total_aws,
                SUM(CASE WHEN status_conciliacao = 'FALTA_NO_TRIABOT' THEN 1 ELSE 0 END) as qtd_faltantes,
                SUM(CASE WHEN status_conciliacao = 'DIVERGENCIA_VALOR' THEN 1 ELSE 0 END) as qtd_divergentes,
                SUM(CASE WHEN status_conciliacao = 'NOTA_FANTASMA_TRIABOT' THEN 1 ELSE 0 END) as qtd_fantasmas
            FROM malha_fiscal_tomadas
            WHERE competencia = ?
            GROUP BY cod_empresa
        )
        -- 3. Junta tudo para o Frontend
        SELECT 
            c.cod_emp as cod_empresa,
            c.nome_emp as nome_empresa,
            COALESCE(r.ultima_sincronizacao, NULL) as ultima_sincronizacao,
            COALESCE(r.total_aws, 0) as total_aws,
            c.total_triabot_real as total_triabot,
            COALESCE(r.qtd_faltantes, 0) as qtd_faltantes,
            COALESCE(r.qtd_divergentes, 0) as qtd_divergentes,
            COALESCE(r.qtd_fantasmas, 0) as qtd_fantasmas
        FROM clientes_com_tomadas c
        LEFT JOIN resumo_malha r ON c.cod_emp = r.cod_empresa
        ORDER BY c.nome_emp ASC
    """
    try:
        return executar_query_dict(query, (competencia, competencia))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    
@app.post("/api/malha-fiscal/sincronizar/{cod_empresa}/{competencia}")
def sincronizar_malha_cliente(cod_empresa: str, competencia: str):
    """Busca na AWS, cruza com o TriaBot e salva na tabela malha_fiscal_tomadas."""
    try:
        # Busca CNPJ diretamente no banco da Domínio
        db_dom = DatabaseConnection()
        if not db_dom.connect():
            raise Exception("Falha ao conectar no banco da Domínio.")
        
        cnpjs_grupo = db_dom.obter_cnpjs_do_grupo(cod_empresa)
        db_dom.close()
        
        if not cnpjs_grupo:
            raise Exception(f"CNPJ não encontrado na Domínio para o código {cod_empresa}.")
            
        cnpj_cliente = cnpjs_grupo[0]         
        #  Busca notas na AWS
        notas_aws = buscar_xmls_aws(cnpj_cliente, competencia)
        
        #  Limpa a base antiga deste cliente/mês
        executar_update("DELETE FROM malha_fiscal_tomadas WHERE cod_empresa = ? AND competencia = ?", (cod_empresa, competencia))
        
        # Cruzamento: Varre as notas da AWS
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
                    valor_txt = triabot_match[0]['valor_contabil'].replace('.', '').replace(',', '.')
                    valor_triabot = float(valor_txt)
                except: pass

                if abs(valor_triabot - nota['valor']) <= 0.01:
                    status = "BATEU"
                else:
                    status = "DIVERGENCIA_VALOR"
            
            executar_update("""
                INSERT INTO malha_fiscal_tomadas 
                (cod_empresa, competencia, numero_nota, cnpj_prestador, valor_nota, status_conciliacao, origem)
                VALUES (?, ?, ?, ?, ?, ?, 'AWS')
            """, (cod_empresa, competencia, nota['numero'], nota['cnpj'], nota['valor'], status))


        notas_triabot = executar_query_dict("""
            SELECT numero_documento, cpf_cnpj, valor_contabil 
            FROM resultados_tomados 
            WHERE id_ticket IN (
                SELECT id_ticket FROM downloads 
                WHERE cod_emp = ? AND strftime('%Y-%m', ultima_tentativa) = ?
            )
        """, (cod_empresa, competencia))

        for nota_tb in notas_triabot:
            ja_existe = executar_query_dict("""
                SELECT id FROM malha_fiscal_tomadas 
                WHERE cod_empresa = ? AND competencia = ? AND numero_nota = ? AND cnpj_prestador = ?
            """, (cod_empresa, competencia, nota_tb['numero_documento'], nota_tb['cpf_cnpj']))

            if not ja_existe:
                try:
                    valor_tb_float = float(nota_tb['valor_contabil'].replace('.', '').replace(',', '.'))
                except: valor_tb_float = 0.0

                executar_update("""
                    INSERT INTO malha_fiscal_tomadas 
                    (cod_empresa, competencia, numero_nota, cnpj_prestador, valor_nota, status_conciliacao, origem)
                    VALUES (?, ?, ?, ?, ?, 'NOTA_FANTASMA_TRIABOT', 'TRIABOT')
                """, (cod_empresa, competencia, nota_tb['numero_documento'], nota_tb['cpf_cnpj'], valor_tb_float))

        return {"mensagem": f"Auditoria concluída: {len(notas_aws)} notas da AWS e {len(notas_triabot)} notas do TriaBot cruzadas."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    

@app.get("/api/malha-fiscal/detalhes/{cod_empresa}/{competencia}")
def get_detalhes_malha(cod_empresa: str, competencia: str):
    """Puxa as notas específicas para abrir a sub-tabela."""
    query = "SELECT * FROM malha_fiscal_tomadas WHERE cod_empresa = ? AND competencia = ? ORDER BY status_conciliacao DESC"
    return executar_query_dict(query, (cod_empresa, competencia))

