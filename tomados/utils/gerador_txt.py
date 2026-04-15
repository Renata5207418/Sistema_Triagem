import sqlite3
import logging
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / "banco_rpa.db"

def gerar_arquivos_dominio(id_ticket, pasta_destino_local):
    """Busca os resultados no banco e gera os arquivos GERAL.txt e TOMADOS*.txt."""
    pasta = Path(pasta_destino_local)
    pasta.mkdir(parents=True, exist_ok=True)
    
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        registros = conn.execute("SELECT * FROM resultados_tomados WHERE id_ticket = ?", (id_ticket,)).fetchall()

    if not registros:
        return

    todas_linhas = []
    tomadores = {}

    for row in registros:
        tomador_cnpj = row['tomador']
        if tomador_cnpj not in tomadores:
            tomadores[tomador_cnpj] = []
            
        # Layout da Domínio Sistemas (28 colunas)
        linha = [
            row['cpf_cnpj'], row['razao_social'], row['uf'], row['municipio'], '',
            row['numero_documento'], '', row['data_emissao'], '0', row['acumulador'], '',
            row['valor_servicos'], '', row['valor_contabil'], row['base_calculo'], '',
            row['valor_iss_normal'], '', row['valor_irrf'], '', '', '', row['valor_crf'], 
            row['valor_inss'], '', '', '', row['tomador']
        ]
        
        linha_csv = ";".join([str(v) if v is not None else '' for v in linha])
        todas_linhas.append(linha_csv)
        tomadores[tomador_cnpj].append(linha_csv)

    # 1. Gera o GERAL.txt
    with open(pasta / "GERAL.txt", 'w', encoding='latin-1') as f:
        f.write("\n".join(todas_linhas) + "\n")

    # 2. Gera os TOMADOS individuais
    for tomador, linhas in tomadores.items():
        razao = registros[0]['razao_social'] # Pega a primeira razão como base
        filename = f"TOMADOS {razao} - {tomador}.txt"
        with open(pasta / filename, 'w', encoding='latin-1') as f:
            f.write("\n".join(linhas) + "\n")
            
    logging.info(f"Arquivos TXT gerados na pasta: {pasta.name}")
    