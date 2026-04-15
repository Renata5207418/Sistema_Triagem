import os
import time
import json
import logging
import re
from anthropic import Anthropic

def classificar_documento_claude(texto_pdf):
    """
    Envia o texto para a API do Claude e retorna um dicionário com a categoria 
    e os CNPJs (se for nota_servico).
    """
    
    api_key = os.getenv("CLAUDE_API_KEY")
    if not api_key:
        logging.error("Chave CLAUDE_API_KEY não encontrada no .env")
        return {"categoria": "LOW_CONFIDENCE", "cnpj_prestador": None, "cnpj_tomador": None}

    client = Anthropic(api_key=api_key)
    
    prompt_sistema = """
    Você é um extrator de dados fiscais brasileiros.
    Sua tarefa é classificar o documento e, SE for uma nota fiscal de serviço, extrair os CNPJs.
    
    Categorias permitidas: guia, boleto, invoice_exterior, fatura_consumo, comprovante_pagamento, danfe, nota_servico, extrato.
    Se não souber, use: ignorar.
    
    Responda ÚNICA E EXCLUSIVAMENTE com um JSON válido neste formato:
    {
        "categoria": "nome_da_categoria",
        "cnpj_prestador": "apenas_numeros_ou_null",
        "cnpj_tomador": "apenas_numeros_ou_null"
    }
    
    Regras:
    1. Nunca explique sua resposta.
    2. Se a categoria NÃO for 'nota_servico', os campos de CNPJ devem ser null.
    3. Remova toda a pontuação dos CNPJs (devolva apenas os 14 números).
    4. Se for nota de serviço mas o tomador for pessoa física ou não identificado, devolva null no cnpj_tomador.
    """

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001", 
            max_tokens=100, 
            temperature=0.0, 
            system=prompt_sistema,
            messages=[
                {"role": "user", "content": f"TEXTO EXTRAÍDO DO DOCUMENTO:\n{texto_pdf}"}
            ]
        )
        
        resposta_ia = response.content[0].text.strip()
        time.sleep(1)  
        
        # Tenta converter a resposta da IA para um dicionário Python
        try:
            resposta_limpa = re.sub(r"```json\n|\n```", "", resposta_ia).strip()
            dados = json.loads(resposta_limpa)
            return {
                "categoria": dados.get("categoria", "LOW_CONFIDENCE"),
                "cnpj_prestador": dados.get("cnpj_prestador"),
                "cnpj_tomador": dados.get("cnpj_tomador")
            }
        except json.JSONDecodeError:
            logging.error(f"Falha ao decodificar JSON da IA. Resposta bruta: {resposta_ia}")
            return {"categoria": "LOW_CONFIDENCE", "cnpj_prestador": None, "cnpj_tomador": None}
            
    except Exception as e:
        logging.error(f"Erro ao consultar a API do Claude: {e}")
        return {"categoria": "ERRO_API", "cnpj_prestador": None, "cnpj_tomador": None}