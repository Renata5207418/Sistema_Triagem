import sqlite3
import logging
from pathlib import Path
import re

DB_PATH = Path(__file__).parent.parent.parent / "banco_rpa.db"

def limpar_campo(valor):
    """Remove quebras de linha e ponto-e-vírgulas impostores que quebram o layout do CSV/TXT."""
    if valor is None:
        return ''
    v_str = str(valor)
    v_str = v_str.replace('\n', ' ').replace('\r', ' ').replace('\t', ' ')
    v_str = v_str.replace(';', ',')
    return ' '.join(v_str.split()).strip()

def formatar_moeda(valor):
    """Trator da Domínio: Aniquila qualquer formatação louca da IA e devolve PT-BR puro."""
    if not valor:
        return ''
    
    # 1. Tira R$, espaços e deixa só número, ponto e vírgula
    v_str = str(valor).replace('R$', '').strip()
    v_str = re.sub(r'[^\d\,\.]', '', v_str)
    
    if not v_str:
        return ''

    # 2. Se a IA mandou um número inteiro cravado (ex: "15000")
    if ',' not in v_str and '.' not in v_str:
        return v_str + ',00'

    # 3. Acha onde está o ÚLTIMO separador (sempre será a casa dos centavos)
    ultimo_separador = max(v_str.rfind(','), v_str.rfind('.'))
    
    # 4. Divide o número no meio
    parte_inteira = v_str[:ultimo_separador]
    parte_decimal = v_str[ultimo_separador+1:]
    
    # 5. Remove QUALQUER outro ponto ou vírgula da parte inteira (resolve o 15,190,37 -> 15190)
    parte_inteira = parte_inteira.replace('.', '').replace(',', '')
    
    # 6. Garante que os centavos tenham 2 dígitos (se IA mandar "5", vira "50")
    if len(parte_decimal) == 1:
        parte_decimal += '0'
        
    return f"{parte_inteira},{parte_decimal}"

def gerar_arquivos_dominio(id_ticket, pasta_destino_local):
    """Busca os resultados no banco e gera os arquivos GERAL.txt e TOMADOS*.txt."""
    pasta = Path(pasta_destino_local)
    pasta.mkdir(parents=True, exist_ok=True)
    
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        registros = conn.execute("SELECT * FROM resultados_tomados WHERE id_ticket = ?", (id_ticket,)).fetchall()

    if not registros:
        return

    cabecalho = [
        "CPF/CNPJ", "Razão Social", "UF", "Município", "Endereço", "Número Documento", 
        "Série", "Data", "Situação (0- Regular / 2- Cancelada)", "Acumulador", "CFOP", 
        "Valor Serviços", "Valor Descontos", "Valor Contábil", "Base de Calculo", 
        "Alíquota ISS", "Valor ISS Normal", "Valor ISS Retido", "Valor IRRF", 
        "Valor PIS", "Valor COFINS", "Valor CSLL", "Valo CRF", "Valor INSS", 
        "Código do Item", "Quantidade", "Valor Unitário", "tomador"
    ]
    
    header_csv = ";".join(cabecalho)
    todas_linhas = [header_csv]
    tomadores = {}

    for row_raw in registros:
        row = dict(row_raw)
        
        tomador_cnpj = limpar_campo(row.get('tomador', ''))
        if tomador_cnpj not in tomadores:
            tomadores[tomador_cnpj] = [header_csv]
            
        linha_bruta = [
            limpar_campo(row.get('cpf_cnpj', '')), 
            limpar_campo(row.get('razao_social', '')), 
            limpar_campo(row.get('uf', '')), 
            limpar_campo(row.get('municipio', '')), 
            '', 
            limpar_campo(row.get('numero_documento', '')), 
            limpar_campo(row.get('serie', '')),
            limpar_campo(row.get('data_emissao', '')), 
            '0', 
            limpar_campo(row.get('acumulador', '')), 
            limpar_campo(row.get('cfop', '')), 
            
            formatar_moeda(row.get('valor_servicos', '')), 
            '', 
            formatar_moeda(row.get('valor_contabil', '')), 
            formatar_moeda(row.get('base_calculo', '')), 
            '', '', '', 
            formatar_moeda(row.get('valor_irrf', '')), 
            formatar_moeda(row.get('valor_pis', '')),    
            formatar_moeda(row.get('valor_cofins', '')), 
            formatar_moeda(row.get('valor_csll', '')),   
            formatar_moeda(row.get('valor_crf', '')), 
            formatar_moeda(row.get('valor_inss', '')), 
            
            '', '', '', 
            limpar_campo(row.get('tomador', ''))
        ]
        
        linha_csv = ";".join(linha_bruta)
        todas_linhas.append(linha_csv)
        tomadores[tomador_cnpj].append(linha_csv)

    with open(pasta / "GERAL.txt", 'w', encoding='latin-1', errors='replace') as f:
        f.write("\n".join(todas_linhas) + "\n")

    for tomador, linhas in tomadores.items():
        razao = registros[0]['razao_social']
        nome_tomador = re.sub(r'[^0-9]', '', str(tomador))
        razao_limpa = re.sub(r'[^a-zA-Z0-9 ]', '', str(razao)).strip()
        filename = f"TOMADOS {razao_limpa} - {nome_tomador}.txt"
        
        with open(pasta / filename, 'w', encoding='latin-1', errors='replace') as f:
            f.write("\n".join(linhas) + "\n")
            
    logging.info(f"Arquivos TXT gerados na pasta: {pasta.name}")
    