import os
import boto3
import re
from botocore.config import Config
from dotenv import load_dotenv

load_dotenv()

config = Config(connect_timeout=10, read_timeout=60, retries={"max_attempts": 5, "mode": "standard"})

s3 = boto3.client(
    "s3",
    region_name=os.getenv("AWS_REGION"),
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    config=config
)
BUCKET_NAME = os.getenv("AWS_BUCKET_NAME")

def extrair_dados_xml(xml_content: str) -> dict:
    """Extrai Número, CNPJ do Prestador e Valor suportando XMLs com espaços e namespaces."""
    try:
        # Busca Número: \s* ignora espaços e quebras de linha entre a tag e o número!
        numero_match = re.search(r'<[^>]*?(?:Numero|nNFSe)[^>]*?>\s*(\d+)\s*</', xml_content, re.IGNORECASE)
        
        # Busca CNPJ do Prestador
        cnpj_match = re.search(r'<[^>]*?Cnpj[^>]*?>\s*(\d+)\s*</', xml_content, re.IGNORECASE)
        
        # Busca Valor do Serviço (Aceita ponto ou vírgula no XML)
        valor_match = re.search(r'<[^>]*?(?:vServ|ValorServicos)[^>]*?>\s*([\d\.,]+)\s*</', xml_content, re.IGNORECASE)
        
        # Se não achou o número da nota, aborta (não é uma NFS-e válida ou layout desconhecido)
        if not numero_match: 
            return None
            
        valor_str = "0.00"
        if valor_match:
            # Troca vírgula por ponto caso a prefeitura gere o XML no formato PT-BR
            valor_str = valor_match.group(1).replace(',', '.')
        
        return {
            "numero": numero_match.group(1),
            "cnpj": cnpj_match.group(1) if cnpj_match else "00000000000000",
            "valor": float(valor_str)
        }
    except Exception as e:
        print(f"Erro ao extrair XML: {e}")
        return None
    

def buscar_xmls_aws(cnpj_cliente: str, competencia: str) -> list:
    """
    Busca na AWS direto na pasta YYYY-MM.
    """
    # Garante que o CNPJ seja apenas numérico
    cnpj_limpo = re.sub(r'[^0-9]', '', str(cnpj_cliente))
    
    # Monta o caminho exato do seu S3
    prefix = f"{cnpj_limpo}/TOMADAS/{competencia}/"
    
    print(f"\n[DEBUG AWS] Iniciando busca no Bucket: {BUCKET_NAME}")
    print(f"[DEBUG AWS] Procurando na pasta exata: {prefix}")
    
    paginator = s3.get_paginator("list_objects_v2")
    notas_aws = []
    arquivos_encontrados = 0

    try:
        for page in paginator.paginate(Bucket=BUCKET_NAME, Prefix=prefix):
            for item in page.get("Contents", []):
                arquivos_encontrados += 1
                if item["Key"].lower().endswith(".xml"):
                    obj = s3.get_object(Bucket=BUCKET_NAME, Key=item["Key"])
                    xml_str = obj["Body"].read().decode("utf-8", errors="ignore")
                    
                    dados = extrair_dados_xml(xml_str)
                    if dados:
                        notas_aws.append(dados)
                    else:
                        print(f"     [FALHA REGEX] Não foi possível ler o arquivo: {item['Key']}")
        
        print(f"\n[RESUMO AWS] Arquivos XMLs encontrados na pasta: {arquivos_encontrados}")
        print(f"[RESUMO AWS] Notas extraídas com sucesso: {len(notas_aws)}")
        
        return notas_aws
    except Exception as e:
        print(f"Erro AWS: {e}")
        return []
    