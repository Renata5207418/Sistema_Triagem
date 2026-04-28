import os
import time
import json
import logging
import re
from anthropic import Anthropic

def classificar_documento_claude(pdf_base64):
    api_key = os.getenv("CLAUDE_API_KEY")
    if not api_key:
        logging.error("Chave CLAUDE_API_KEY não encontrada no .env")
        return {"categoria": "ERRO_API", "cnpj_prestador": None, "cnpj_tomador": None}

    client = Anthropic(api_key=api_key)
    MODELO = "claude-haiku-4-5-20251001"

    prompt_sistema = """
Você é um classificador fiscal brasileiro. Analise o documento e responda APENAS com um JSON válido, sem texto adicional.

CATEGORIAS DISPONÍVEIS:
- "danfe": Documento Auxiliar da Nota Fiscal Eletrônica (NF-e). B2B.
- "fatura_consumo": Nota Fiscal de Consumidor (NFC-e), cupom fiscal, nota de balcão (gás, mercado).
- "nota_servico": Nota Fiscal de Serviços (NFS-e).
- "boleto": Boleto bancário, carnê, fatura de cartão de crédito.
- "guia": Guia de recolhimento de tributos (DARF, GPS, GNRE, DAS, DAM, IPTU etc).
- "comprovante_pagamento": Comprovante de PIX, TED, DOC ou recibo de pagamento.
- "extrato": Extrato bancário, extrato de conta corrente.
- "invoice_exterior": Fatura internacional, em inglês/espanhol.
- "fatura_locacao": Fatura ou contrato de aluguel.
- "nota_debito": Nota de débito, solicitação de reembolso, recibos simples ou cobranças que não sejam boletos nem notas fiscais.
- "revisao_manual": Use esta categoria se o documento for ilegível, não se encaixar em nenhuma das acima, ou se parecer conter vários tipos diferentes misturados.

FORMATO OBRIGATÓRIO:
{"categoria": "nome_da_categoria", "cnpj_prestador": null, "cnpj_tomador": null}

Regras:
1. Para "nota_servico", preencha os CNPJs apenas com números. Para as outras, use null.
2. NUNCA tente adivinhar. Na dúvida ou se estiver ilegível, retorne "revisao_manual".
"""

    for tentativa in range(3):
        try:
            response = client.messages.create(
                model=MODELO,
                max_tokens=200,
                temperature=0.0,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_base64}},
                        {"type": "text", "text": "Classifique este documento fiscal e responda APENAS com o JSON."}
                    ]
                }],
                system=prompt_sistema
            )

            resposta_ia = response.content[0].text.strip()
            
            try:
                dados = json.loads(resposta_ia)
            except json.JSONDecodeError:
                match = re.search(r"\{.*?\}", resposta_ia, re.DOTALL)
                if not match:
                    time.sleep(2)
                    continue
                dados = json.loads(match.group(0))

            categoria = dados.get("categoria", "").strip().lower()

            # Validação estrita (adicionado nota_debito)
            categorias_validas = {
                "guia", "boleto", "invoice_exterior", "fatura_consumo",
                "comprovante_pagamento", "danfe", "extrato", "nota_servico",
                "fatura_locacao", "revisao_manual", "planilhas", "xml", "nota_debito"
            }
            
            if categoria not in categorias_validas:
                categoria = "revisao_manual"

            return {
                "categoria": categoria,
                "cnpj_prestador": dados.get("cnpj_prestador"),
                "cnpj_tomador": dados.get("cnpj_tomador")
            }

        except Exception as e:
            logging.error(f"Erro na API Anthropic (tentativa {tentativa+1}): {e}")
            time.sleep(2 ** tentativa) 

    return {"categoria": "ERRO_API", "cnpj_prestador": None, "cnpj_tomador": None}
