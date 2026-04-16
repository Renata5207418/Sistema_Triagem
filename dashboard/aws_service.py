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
    """Extrai Número, CNPJ do Prestador e Valor suportando Padrão Nacional e ABRASF."""
    try:
        # Tenta achar a tag do Padrão Nacional (<nNFSe>) ou do ABRASF (<Numero>)
        numero = re.search(r'<nNFSe>(\d+)</nNFSe>', xml_content, re.IGNORECASE) or \
                 re.search(r'<Numero>(\d+)</Numero>', xml_content, re.IGNORECASE)
                 
        # O CNPJ continua usando a tag <Cnpj> ou <CNPJ>. O primeiro a aparecer é o do emitente/prestador.
        cnpj = re.search(r'<Cnpj>(\d+)</Cnpj>', xml_content, re.IGNORECASE)
        
        # Tenta achar a tag do Padrão Nacional (<vServ>) ou do ABRASF (<ValorServicos>)
        valor = re.search(r'<vServ>([\d\.]+)</vServ>', xml_content, re.IGNORECASE) or \
                re.search(r'<ValorServicos>([\d\.]+)</ValorServicos>', xml_content, re.IGNORECASE)
        
        # Se não achou o número da nota em nenhum dos dois formatos, aborta
        if not numero: 
            return None
        
        return {
            "numero": numero.group(1),
            "cnpj": cnpj.group(1) if cnpj else "00000000000000",
            "valor": float(valor.group(1)) if valor else 0.00
        }
    except Exception as e:
        print(f"Erro ao extrair XML: {e}")
        return None
    

def buscar_xmls_aws(cnpj_cliente: str, competencia: str) -> list:
    """
    Busca na AWS com LOGS para debug.
    """
    prefix = f"{cnpj_cliente}/TOMADAS/{competencia}/"
    print(f"\n[DEBUG AWS] Iniciando busca no Bucket: {BUCKET_NAME}")
    print(f"[DEBUG AWS] Procurando na pasta: {prefix}")
    
    paginator = s3.get_paginator("list_objects_v2")
    notas_aws = []
    arquivos_encontrados = 0

    try:
        for page in paginator.paginate(Bucket=BUCKET_NAME, Prefix=prefix):
            for item in page.get("Contents", []):
                arquivos_encontrados += 1
                if item["Key"].lower().endswith(".xml"):
                    print(f"  -> Lendo arquivo: {item['Key']}")
                    obj = s3.get_object(Bucket=BUCKET_NAME, Key=item["Key"])
                    xml_str = obj["Body"].read().decode("utf-8", errors="ignore")
                    
                    dados = extrair_dados_xml(xml_str)
                    if dados:
                        print(f"     [SUCESSO] Dados extraídos: NF={dados['numero']}, CNPJ={dados['cnpj']}, Valor={dados['valor']}")
                        notas_aws.append(dados)
                    else:
                        print(f"     [FALHA] O Regex não conseguiu extrair os dados deste XML. Mostrando o início do arquivo para inspeção:")
                        print(f"     {xml_str[:150]}...")
        
        print(f"\n[RESUMO AWS] Arquivos encontrados na pasta: {arquivos_encontrados}")
        print(f"[RESUMO AWS] Notas processadas com sucesso: {len(notas_aws)}")
        return notas_aws
    except Exception as e:
        print(f"Erro AWS: {e}")
        return []
    