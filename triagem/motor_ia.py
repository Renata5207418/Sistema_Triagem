import os
import time
import logging
from anthropic import Anthropic


def classificar_documento_claude(texto_pdf):
    """Envia o texto para a API do Claude e retorna apenas a categoria."""
    
    api_key = os.getenv("CLAUDE_API_KEY")
    if not api_key:
        logging.error("Chave CLAUDE_API_KEY não encontrada no .env")
        return "LOW_CONFIDENCE"

    client = Anthropic(api_key=api_key)
    
    prompt_sistema = """
    Você é um classificador de documentos fiscais e contábeis brasileiros.
    Sua única tarefa é analisar o texto de um documento e responder APENAS com UMA das seguintes categorias exatas:
    - guia
    - boleto
    - invoice_exterior
    - fatura_consumo
    - comprovante_pagamento
    - danfe
    - nota_servico
    - extrato
    
    Regras:
    1. Nunca explique sua resposta.
    2. Responda apenas a palavra da categoria.
    3. Se não conseguir identificar com clareza, responda exatamente: ignorar
    """

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",  
            max_tokens=15, 
            temperature=0.0, 
            system=prompt_sistema,
            messages=[
                {"role": "user", "content": f"TEXTO EXTRAÍDO DO DOCUMENTO:\n{texto_pdf}"}
            ]
        )
        
        resposta_ia = response.content[0].text.strip().lower()        
        time.sleep(1)  
        
        return resposta_ia
        
    except Exception as e:
        logging.error(f"Erro ao consultar a API do Claude: {e}")
        return "ERRO_API"
    