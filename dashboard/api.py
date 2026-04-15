import os
import sqlite3
import zipfile
from pathlib import Path
from fastapi.responses import FileResponse
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional

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

RAIZ_PROJETO = Path(__file__).parent.parent
DB_PATH = RAIZ_PROJETO / "banco_rpa.db"

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
    """Gera um ZIP contendo apenas os TXTs convertidos para CSV (Excel)."""
    
    query = "SELECT caminho_pasta FROM downloads WHERE id_ticket = ?"
    resultado = executar_query_dict(query, (os_id,))
    
    if not resultado or not resultado[0]['caminho_pasta']:
        raise HTTPException(status_code=404, detail="Pasta da OS não encontrada.")
    
    caminho_raiz = Path(resultado[0]['caminho_pasta'])
    pasta_tomadas = caminho_raiz / "NOTAS_DE_SERVICO" / "TOMADAS"
    
    if not pasta_tomadas.exists():
        raise HTTPException(status_code=404, detail="Pasta TOMADAS não encontrada.")

    zip_path = caminho_raiz / f"Dados_Dominio_OS{os_id}.zip"

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for arquivo in pasta_tomadas.iterdir():
            if arquivo.is_file() and arquivo.suffix.lower() == '.txt':
                nome_excel = arquivo.stem + ".csv"
                zipf.write(arquivo, arcname=nome_excel)

    return FileResponse(
        path=zip_path, 
        media_type="application/zip", 
        filename=f"OS{os_id}_Planilhas_Dominio.zip"
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



@app.get("/api/triagem/auditoria")
def get_auditoria_triagem():
    """Retorna a lista unificada puxando os dados REAIS da tabela de downloads e do status da IA."""
    query = """
        SELECT 
            dt.id,
            dt.id_ticket as os, 
            dt.nome_original as arquivo,
            dt.categoria_ia, 
            dt.status as status_triagem,
            dt.status_tomados, -- <-- AQUI ESTÁ A MÁGICA! Puxando o status real do banco.
            
            d.status as status_download,
            d.cod_emp as cod_empresa,
            d.nome_emp as nome_empresa,
            d.descricao as mensagem

        FROM documentos_triados dt
        LEFT JOIN downloads d ON dt.id_ticket = d.id_ticket
        ORDER BY dt.id_ticket DESC
    """
    try:
        return executar_query_dict(query)
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