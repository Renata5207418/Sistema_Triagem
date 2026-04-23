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
Você é um classificador fiscal brasileiro. Analise o documento e responda APENAS com um JSON válido, sem texto adicional, sem explicações, sem markdown.

CATEGORIAS DISPONÍVEIS e seus critérios:

- "danfe": Documento Auxiliar da Nota Fiscal Eletrônica (NF-e). Contém "DANFE" ou "Documento Auxiliar da Nota Fiscal Eletrônica". Operações entre empresas (B2B).
- "fatura_consumo": Nota Fiscal de Consumidor Eletrônica (NFC-e) ou cupom fiscal. Contém "NFC-e", "Nota Fiscal de Consumidor", "Cupom Fiscal". Vendas no varejo para consumidor final. Inclui notas de gás, combustível, mercadorias para consumo.
- "nota_servico": Nota Fiscal de Serviços (NFS-e). Prestação de serviços. Contém CNPJ do prestador e tomador.
- "boleto": Boleto bancário, carnê, guia de pagamento bancário com código de barras para pagamento em banco.
- "guia": Guia de recolhimento de tributos (DARF, GPS, GNRE, DAS, DAE, ISS, IPTU, IPVA etc).
- "comprovante_pagamento": Comprovante de pagamento, recibo, transferência bancária (PIX, TED, DOC) já realizada.
- "extrato": Extrato bancário, extrato de conta corrente, OFX.
- "planilhas": Planilhas, tabelas, relatórios em formato tabular.
- "invoice_exterior": Invoice ou fatura internacional, documentos em inglês/espanhol de fornecedor estrangeiro.
- "fatura_locacao": Fatura ou contrato de aluguel, locação de imóvel.

FORMATO DE RESPOSTA OBRIGATÓRIO:
{"categoria": "nome_da_categoria", "cnpj_prestador": null, "cnpj_tomador": null}

Para nota_servico, preencha os CNPJs (apenas dígitos, sem pontuação). Para todas as outras categorias, mantenha null.
Se não conseguir classificar com certeza, use "fatura_consumo" para qualquer cupom/nota de varejo, ou "danfe" para notas fiscais entre empresas.
NUNCA retorne categoria vazia ou fora da lista acima.
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
                        {
                            "type": "document",
                            "source": {
                                "type": "base64",
                                "media_type": "application/pdf",
                                "data": pdf_base64
                            }
                        },
                        {
                            "type": "text",
                            "text": "Classifique este documento fiscal e responda APENAS com o JSON."
                        }
                    ]
                }],
                system=prompt_sistema
            )

            resposta_ia = response.content[0].text.strip()
            logging.info(f"Resposta IA [{tentativa+1}]: {resposta_ia}") 

            # Tenta parse direto primeiro
            try:
                dados = json.loads(resposta_ia)
            except json.JSONDecodeError:
                # Fallback: extrai JSON via regex
                match = re.search(r"\{.*?\}", resposta_ia, re.DOTALL)
                if not match:
                    logging.warning(f"JSON não encontrado na resposta (tentativa {tentativa+1}): {resposta_ia}")
                    time.sleep(2)
                    continue
                dados = json.loads(match.group(0))


            categoria = dados.get("categoria", "").strip().lower()

            # Valida se a categoria retornada é conhecida
            categorias_validas = {
                "guia", "boleto", "invoice_exterior", "fatura_consumo",
                "comprovante_pagamento", "danfe", "extrato", "planilhas",
                "xml", "fatura_locacao", "nota_servico"
            }
            if categoria not in categorias_validas:
                logging.warning(f"Categoria desconhecida '{categoria}', marcando como ignorar.")
                categoria = "ignorar"

            return {
                "categoria": categoria,
                "cnpj_prestador": dados.get("cnpj_prestador"),
                "cnpj_tomador": dados.get("cnpj_tomador")
            }

        except Exception as e:
            logging.error(f"Erro na API Anthropic (tentativa {tentativa+1}): {e}")
            time.sleep(2 ** tentativa)  # Backoff exponencial: 1s, 2s, 4s

    return {"categoria": "ERRO_API", "cnpj_prestador": None, "cnpj_tomador": None}
