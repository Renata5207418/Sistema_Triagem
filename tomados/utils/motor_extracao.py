import os
import json
import logging
import time
from pathlib import Path
import sys
from dotenv import load_dotenv

# Configuração de caminhos
pasta_atual = str(Path(__file__).parent.parent)
if pasta_atual not in sys.path:
    sys.path.append(pasta_atual)

# Volta 3 casas para chegar na raiz do projeto
raiz_projeto = Path(__file__).parent.parent.parent
load_dotenv(dotenv_path=raiz_projeto / ".env")

import re
from anthropic import Anthropic

def extrair_dados_nota_claude(texto_bruto, max_tentativas=3):
    """Lê o texto do banco e retorna os valores fiscais em JSON, com retentativas."""
    api_key = os.getenv("CLAUDE_API_KEY")
    if not api_key:
        logging.error("Chave CLAUDE_API_KEY não encontrada.")
        return None

    client = Anthropic(api_key=api_key)
    
    prompt_sistema = """
    Você é um extrator de dados de Notas Fiscais de Serviço (NFS-e).
    Retorne APENAS um objeto JSON. Sem markdown, sem explicações.
    
    Regras:
    - CNPJ/CPF: Apenas números (ex: 12345678000199)
    - Valores: Formato brasileiro com vírgula e sem R$ (ex: "1500,50", "0,00")
    - Datas: Formato DD/MM/AAAA
    - Se não existir, retorne "0,00" ou "".
    
    Chaves OBRIGATÓRIAS:
    {
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
    """

    for tentativa in range(max_tentativas):
        try:
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",  
                max_tokens=1024, 
                temperature=0.0,
                system=prompt_sistema,
                messages=[{"role": "user", "content": f"TEXTO DA NOTA:\n{texto_bruto}"}]
            )
            
            texto_resposta = response.content[0].text.strip()
            texto_resposta = re.sub(r'^```json\s*', '', texto_resposta)
            texto_resposta = re.sub(r'\s*```$', '', texto_resposta)
            
            return json.loads(texto_resposta)
            
        except Exception as e:
            erro_str = str(e)
            # Se for erro de sobrecarga ou limite (429, 529, Overloaded)
            if "529" in erro_str or "429" in erro_str or "overloaded" in erro_str.lower():
                espera = (tentativa + 1) * 5  # Espera 5s, depois 10s, depois 15s...
                logging.warning(f"API do Claude sobrecarregada (Tentativa {tentativa + 1}/{max_tentativas}). Aguardando {espera}s...")
                time.sleep(espera)
            else:
                # Se for outro tipo de erro (ex: credencial inválida), para na hora
                logging.error(f"Erro na extração com Claude: {e}")
                return None
                
    logging.error("Falha na extração após múltiplas tentativas. A API do Claude está indisponível no momento.")
    return None
