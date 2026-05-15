import os
import time
import json
import logging
import re
from anthropic import Anthropic
from utils.claude_limiter import aguardar_janela_claude, erro_rate_limit

def classificar_documento_claude(pdf_base64):
    api_key = os.getenv("CLAUDE_API_KEY")
    if not api_key:
        logging.error("Chave CLAUDE_API_KEY não encontrada no .env")
        return {"categoria": "ERRO_API", "cnpj_prestador": None, "cnpj_tomador": None}

    client = Anthropic(api_key=api_key)
    MODELO = "claude-haiku-4-5-20251001"

    # Prompt levemente melhorado para clareza e separação Produto x Serviço
    prompt_sistema = """Você é um classificador de documentos contábeis. Retorne ESTRITAMENTE um JSON no formato: {"categoria": "...", "cnpj_prestador": "so numeros", "cnpj_tomador": "so numeros"}. NÃO use marcação markdown (```).

REGRAS DE EXTRAÇÃO DE CNPJ:
- Extraia os CNPJs APENAS se a categoria for 'nota_servico'. Para as demais categorias, retorne null nos campos de CNPJ.
- PRESTADOR (Quem prestou o serviço): Procurar por Prestador, Emitente, Fornecedor.
- TOMADOR (Quem comprou o serviço): Procurar por Tomador, Destinatário, Cliente, Receptor, Contratante.

CATEGORIAS PERMITIDAS (Escolha apenas uma):
- nota_servico: Nota Fiscal de Serviço (NFS-e), retenção de ISS, Recibo de prestação de serviço.
- danfe: Nota Fiscal Eletrônica de Produtos/Mercadorias (NF-e, DANFE).
- fatura_consumo: Conta de água, luz, telefone, internet, NFC-e (cupom fiscal de varejo).
- boleto: Boleto bancário, cobrança.
- guia: Guias de impostos e tributos (DAS, DARF, GPS, DAE, GRRF).
- comprovante_pagamento: Comprovante de transferência, PIX, pagamento de título.
- extrato: Extrato bancário, movimentação de conta corrente.
- fatura_locacao: Recibo de aluguel, fatura de locação de equipamentos/imóveis.
- invoice_exterior: Invoice, nota fiscal internacional.
- rh: Folha de ponto, holerite, recibo de férias, termo de rescisão.
- revisao_manual: Documento totalmente em branco, ilegível ou página preta.
- documentos_gerais: Contratos, recibos simples, notificações ou qualquer outro documento na dúvida."""

    for tentativa in range(5):
        try:
            aguardar_janela_claude()

            response = client.messages.create(
                model=MODELO,
                max_tokens=200,
                temperature=0.0,
                messages=[
                    {
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
                                "text": "Classifique o documento e extraia os CNPJs conforme as regras."
                            }
                        ]
                    }
                ],
                system=prompt_sistema
            )

            resposta_ia = response.content[0].text.strip()

            try:
                dados = json.loads(resposta_ia)
            except json.JSONDecodeError:
                match = re.search(r"\{.*?\}", resposta_ia, re.DOTALL)
                if not match:
                    logging.warning("[CLAUDE] Resposta sem JSON válido na Triagem. Tentando novamente...")
                    time.sleep(2)
                    continue
                dados = json.loads(match.group(0))

            categoria = dados.get("categoria", "").strip().lower()

            categorias_validas = {
                "guia", "boleto", "invoice_exterior", "fatura_consumo",
                "comprovante_pagamento", "danfe", "extrato", "nota_servico",
                "fatura_locacao", "revisao_manual", "planilhas", "xml",
                "nota_debito", "documentos_gerais", "rh"
            }

            if categoria not in categorias_validas:
                categoria = "documentos_gerais"

            # Limpeza extra para garantir apenas números nos CNPJs retornados
            def limpar_cnpj(val):
                if val and isinstance(val, str):
                    nums = re.sub(r"\D", "", val)
                    return nums if nums else None
                return None

            return {
                "categoria": categoria,
                "cnpj_prestador": limpar_cnpj(dados.get("cnpj_prestador")),
                "cnpj_tomador": limpar_cnpj(dados.get("cnpj_tomador"))
            }

        except Exception as e:
            if erro_rate_limit(e):
                espera = min(90, 10 * (tentativa + 1))
                logging.warning(f"[CLAUDE] Rate limit na Triagem. Aguardando {espera}s...")
                time.sleep(espera)
                continue

            logging.error(f"Erro na API Anthropic na Triagem: {e}")
            time.sleep(2 ** tentativa)

    return {"categoria": "ERRO_API", "cnpj_prestador": None, "cnpj_tomador": None}
