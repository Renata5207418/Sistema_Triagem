import os
import json
import logging
import time
from pathlib import Path
import sys
import re
import base64
import fitz  
from dotenv import load_dotenv
from anthropic import Anthropic

# Configuração de caminhos
raiz_projeto = Path(__file__).resolve().parent.parent.parent
if str(raiz_projeto) not in sys.path:
    sys.path.append(str(raiz_projeto))

load_dotenv(dotenv_path=raiz_projeto / ".env")

from utils.claude_limiter import aguardar_janela_claude, erro_rate_limit


def limpar_numero(texto):
    """Remove pontuações e deixa só números para o CNPJ."""
    return re.sub(r'[^0-9]', '', str(texto))


def tentar_extracao_regex(texto):
    """
    Tenta extrair os dados básicos por Regex para poupar a IA.
    Retorna um dict preenchido se encontrar tudo, senão retorna None.
    """
    dados = {
        "cpf_cnpj_prestador": "",
        "cpf_cnpj_tomador": "",
        "numero_documento": "",
        "serie": "",
        "data_emissao": "",
        "valor_servicos": "0,00",
        "valor_irrf": "0,00",
        "valor_pis": "0,00",
        "valor_cofins": "0,00",
        "valor_csll": "0,00",
        "valor_inss": "0,00"
    }
    
    # 1. Busca CNPJs/CPFs (Padrão com pontuação ou seguidos)
    documentos = re.findall(r'\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b|\b\d{3}\.\d{3}\.\d{3}-\d{2}\b', texto)
    if len(documentos) >= 1:
        dados["cpf_cnpj_prestador"] = limpar_numero(documentos[0])
    if len(documentos) >= 2:
        # Geralmente o 2º documento que aparece no texto da NFS-e é o do tomador
        dados["cpf_cnpj_tomador"] = limpar_numero(documentos[1])
        
    # 2. Busca Data de Emissão (DD/MM/AAAA)
    datas = re.findall(r'\b\d{2}/\d{2}/\d{4}\b', texto)
    if datas:
        dados["data_emissao"] = datas[0]
        
    # 3. Busca Número da Nota (Suporta Curitiba, BH e variações)
    match_numero = re.search(r'(?:Número da NFS-e|Número da Nota|Número do Documento|NFS-e N[oº]?|Nota Fiscal N[oº]?|Número|Nº|Numero)\s*[:\-]?\s*0*(\d{1,15})', texto, re.IGNORECASE)
    if match_numero:
        dados["numero_documento"] = match_numero.group(1)
        
    # 4. Busca Valor Total (Suporta Valores Líquidos e de Serviços)
    match_valor = re.search(r'(?:Valor Líquido da NFS-e|Valor Líquido da Nota|Valor Total da NFS-e|Valor Total da Nota|Valor Total dos Serviços|Valor do Serviço|Valor Líquido|Valor Total|Total)\s*[:\-]?\s*(?:R\$)?\s*([\d\.]+(?:,\d{2}))', texto, re.IGNORECASE)
    if match_valor:
        dados["valor_servicos"] = match_valor.group(1)
        
    # Validação do Bypass: Só aceita pular a IA se achou o "Quarteto de Ouro"
    if dados["cpf_cnpj_prestador"] and dados["numero_documento"] and dados["data_emissao"] and dados["valor_servicos"] != "0,00":
        return dados
        
    return None


def extrair_dados_nota_claude(texto_bruto, max_tentativas=5, caminho_pdf=None):
    """Lê o texto do banco ou usa IA Visual para notas escaneadas e retorna JSON."""
    
    # ========================================================
    # 1º TENTATIVA: BYPASS COM REGEX (Custo Zero)
    # Apenas tenta o regex se o texto for válido e não-escaneado
    # ========================================================
    if texto_bruto and len(texto_bruto.strip()) >= 50:
        bypass = tentar_extracao_regex(texto_bruto)
        if bypass:
            logging.info("Dados fiscais extraídos via REGEX com sucesso! (Bypass IA concluído)")
            return bypass

    # ========================================================
    # 2º TENTATIVA: INTELIGÊNCIA ARTIFICIAL (Fallback Híbrido)
    # ========================================================
    api_key = os.getenv("CLAUDE_API_KEY")

    if not api_key:
        logging.error("Chave CLAUDE_API_KEY não encontrada.")
        return None

    client = Anthropic(api_key=api_key)

    prompt_sistema = """Retorne APENAS um JSON válido. Extraia os dados da NFS-e.

    Regras:
    1. CNPJs: Extraia APENAS NÚMEROS do prestador e tomador. Se não achar, use "".
    2. Datas: Formato DD/MM/AAAA.
    3. Valores: Formato PT-BR (ex: "1500,50"). Nunca use R$. Na ausência de um imposto, omita a chave correspondente.

    JSON BASE:
    {
        "cpf_cnpj_prestador": "numero",
        "cpf_cnpj_tomador": "numero_ou_vazio",
        "numero_documento": "numero",
        "serie": "texto_ou_vazio",
        "data_emissao": "data",
        "valor_servicos": "valor"
    }"""

    conteudo_mensagem = []

    # ========================================================
    # 2º TENTATIVA: INTELIGÊNCIA ARTIFICIAL (Fallback Híbrido)
    # ========================================================
    tem_imagem = False

    # 1. Tenta carregar a imagem da nota (Prioridade para entender layouts complexos)
    if caminho_pdf and os.path.exists(caminho_pdf):
        try:
            doc_pdf = fitz.open(caminho_pdf)
            primeira_pag = fitz.open()
            primeira_pag.insert_pdf(doc_pdf, from_page=0, to_page=0)
            pdf_bytes = primeira_pag.tobytes()
            pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')
            
            doc_pdf.close()
            primeira_pag.close()
            
            conteudo_mensagem.append({
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": pdf_base64
                }
            })
            tem_imagem = True
            logging.info("Imagem carregada para análise visual no Claude (Modo Híbrido).")
        except Exception as e:
            logging.error(f"Erro ao preparar leitura visual do PDF: {e}")

    # 2. Adiciona o texto extraído (se houver). 
    # Se tem imagem, o texto serve de apoio para evitar alucinações.
    if texto_bruto and len(texto_bruto.strip()) >= 20:
        instrucao_texto = (
            "Utilize o texto extraído abaixo como apoio para os valores exatos, "
            "mas CONFIE NA IMAGEM E NO LAYOUT para entender a qual campo o valor pertence "
            "caso o texto pareça desconfigurado:\n\nTEXTO EXTRAÍDO:\n"
        ) if tem_imagem else "TEXTO DA NOTA:\n"
        
        conteudo_mensagem.append({
            "type": "text",
            "text": f"{instrucao_texto}{texto_bruto}"
        })

    # 3. Validação final do payload
    if not conteudo_mensagem:
        logging.warning("Sem texto válido e sem caminho de PDF físico. Abortando extração IA.")
        return None

    # Instrução final amarrando o que o modelo deve fazer
    conteudo_mensagem.append({
        "type": "text",
        "text": "Extraia os dados da nota fiscal de serviço e retorne APENAS o JSON solicitado."
    })

    # Chamada à API
    for tentativa in range(max_tentativas):
        try:
            aguardar_janela_claude()

            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1024,
                temperature=0.0,
                system=prompt_sistema,
                messages=[
                    {
                        "role": "user",
                        "content": conteudo_mensagem
                    }
                ]
            )

            texto_resposta = response.content[0].text.strip()
            
            # Limpeza cirúrgica e blindada do JSON
            try:
                # 1. Tenta limpar blocos markdown (```json ... ```)
                texto_limpo = texto_resposta.replace("```json", "").replace("```", "").strip()
                dados_ia = json.loads(texto_limpo)
            except json.JSONDecodeError:
                # 2. Fallback: Busca o bloco JSON inteiro (usando Regex Greedy, sem o '?')
                match = re.search(r"\{.*\}", texto_resposta, re.DOTALL)
                if match:
                    try:
                        dados_ia = json.loads(match.group(0))
                    except json.JSONDecodeError:
                        logging.warning("[CLAUDE] Falha na decodificação estrutural do JSON.")
                        return None
                else:
                    logging.warning("[CLAUDE] Nenhum bloco JSON detectado na resposta.")
                    return None
                    
            # ========================================================
            # INJEÇÃO DE RESILIÊNCIA 
            # Garante que nenhum campo de imposto fique de fora quebrando o sistema
            # ========================================================
            campos_impostos = ["valor_irrf", "valor_pis", "valor_cofins", "valor_csll", "valor_inss"]
            for imposto in campos_impostos:
                if imposto not in dados_ia or not dados_ia[imposto]:
                    dados_ia[imposto] = "0,00"
            
            return dados_ia

        except Exception as e:
            if erro_rate_limit(e):
                espera = min(90, 10 * (tentativa + 1))
                logging.warning(
                    f"[CLAUDE] Rate limit/sobrecarga no Tomados "
                    f"tentativa {tentativa + 1}/{max_tentativas}. "
                    f"Aguardando {espera}s..."
                )
                time.sleep(espera)
                continue

            logging.error(f"Erro na extração com Claude: {e}")
            return None

    logging.error("Falha na extração após múltiplas tentativas. A API do Claude está indisponível.")
    return None
