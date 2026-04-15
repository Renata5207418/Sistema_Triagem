import requests
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / "banco_rpa.db"

def dados_fornecedor(cnpj: str):
    cnpj_limpo = re.sub(r'[^0-9]', '', cnpj).zfill(14)
    
    # 1. Tenta buscar no cache local primeiro
    dados_locais = buscar_no_cache(cnpj_limpo)
    
    if dados_locais:
        # Verifica se a consulta tem menos de 30 dias
        data_consulta = datetime.strptime(dados_locais['data_ultima_consulta'], '%Y-%m-%d %H:%M:%S')
        if datetime.now() - data_consulta < timedelta(days=30):
            return {
                'razao_social': dados_locais['razao_social'],
                'uf': dados_locais['uf'],
                'municipio': dados_locais['municipio'],
                'cnae': dados_locais['cnae']
            }

    # 2. Se não tem no cache ou está vencido, vai para a API
    try:
        response = requests.get(url=f'https://receitaws.com.br/v1/cnpj/{cnpj_limpo}', timeout=20)
        
        if response.status_code == 200:
            response_json = response.json()
            if 'nome' in response_json:
                resultado = {
                    'razao_social': re.sub(r'[^0-9a-zA-Z ]', '', response_json.get('nome', '')),
                    'uf': response_json.get('uf', ''),
                    'municipio': response_json.get('municipio', ''),
                    'cnae': re.sub(r'[^0-9]', '', response_json.get('atividade_principal', [{}])[0].get('code', ''))
                }
                
                # 3. Salva/Atualiza o cache com a nova data
                salvar_no_cache(cnpj_limpo, resultado)
                return resultado
            
    except Exception as e:
        print(f"Erro na API para o CNPJ {cnpj_limpo}: {e}")
        
    return {'razao_social': '', 'uf': '', 'municipio': '', 'cnae': ''}

def buscar_no_cache(cnpj):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute("SELECT * FROM cache_fornecedores WHERE cnpj = ?", (cnpj,)).fetchone()

def salvar_no_cache(cnpj, dados):
    agora = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            INSERT OR REPLACE INTO cache_fornecedores 
            (cnpj, razao_social, uf, municipio, cnae, data_ultima_consulta)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (cnpj, dados['razao_social'], dados['uf'], dados['municipio'], dados['cnae'], agora))
