import logging
from pathlib import Path
import sys

pasta_atual = str(Path(__file__).parent.parent)
if pasta_atual not in sys.path:
    sys.path.append(pasta_atual)

from db.db_resiliencia import db
from tomados.utils.acumuladores import acumuladores
from tomados.utils.consulta_for import dados_fornecedor
from tomados.utils.motor_extracao import extrair_dados_nota_claude
from tomados.utils.gerador_txt import gerar_arquivos_dominio

def soma_csrf(pis, cofins, csll):
    """Soma PIS, COFINS e CSLL (ex: '10,50' + '5,00' -> '15,50')."""
    try:
        p = float(pis.replace(",", ".")) if pis else 0.0
        c = float(cofins.replace(",", ".")) if cofins else 0.0
        s = float(csll.replace(",", ".")) if csll else 0.0
        return str(round(p + c + s, 2)).replace(".", ",")
    except:
        return "0,00"

def executar_tomados():
    # 1. Usa o método seguro do banco (com a trava do ticket CONCLUÍDO)
    pendentes = db.get_documentos_pendentes_tomados(limite=50)
    
    if not pendentes: return 0

    tickets_processados = set()

    for doc in pendentes:
        id_doc = doc['id_documento']
        id_ticket = doc['id_ticket']
        texto = doc['texto_extraido']
        pasta_destino = doc['pasta_destino'] 
        pasta_raiz = doc['pasta_raiz_ticket']

        # IGNORA se a Triagem jogou para EMITIDAS ou TERCEIROS
        if pasta_destino != 'NOTAS_DE_SERVICO/TOMADAS':
            db.atualizar_status_tomados(id_doc, 'IGNORADO_NAO_E_TOMADO')
            continue

        try:
            # 1. Extração com IA
            dados_ia = extrair_dados_nota_claude(texto)
            if not dados_ia: continue

            # 2. Consulta API/Cache para o PRESTADOR (Quem emitiu a nota)
            forn = dados_fornecedor(dados_ia['cpf_cnpj_prestador'])
            acumulador = acumuladores.get(forn['cnae'], '8') 
            
            # 3. Consulta API/Cache para o TOMADOR (O seu cliente)
            cliente = dados_fornecedor(dados_ia['cpf_cnpj_tomador'])
            uf_cliente = cliente.get('uf', 'PR') # Fallback de segurança caso a API falhe
            
            # 4. Lógica Dinâmica do CFOP
            cfop = "1933" if forn['uf'] == uf_cliente else "2933"
            
            # 5. Soma CRF
            crf = soma_csrf(dados_ia['valor_pis'], dados_ia['valor_cofins'], dados_ia['valor_csll'])

            # 6. Salva no Banco de Resultados
            db.executar_update("""
                INSERT INTO resultados_tomados (
                    id_ticket, id_documento, cpf_cnpj, razao_social, uf, municipio,
                    numero_documento, serie, data_emissao, acumulador, cfop,
                    valor_servicos, valor_contabil, base_calculo, valor_irrf,
                    valor_pis, valor_cofins, valor_csll, valor_crf, valor_inss, tomador
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                id_ticket, id_doc, dados_ia['cpf_cnpj_prestador'], forn['razao_social'], forn['uf'], forn['municipio'],
                dados_ia['numero_documento'], dados_ia['serie'], dados_ia['data_emissao'], acumulador, cfop,
                dados_ia['valor_servicos'], dados_ia['valor_servicos'], dados_ia['valor_servicos'], dados_ia['valor_irrf'],
                dados_ia['valor_pis'], dados_ia['valor_cofins'], dados_ia['valor_csll'], crf, dados_ia['valor_inss'], dados_ia['cpf_cnpj_tomador']
            ))

            db.atualizar_status_tomados(id_doc, 'PROCESSADO')
            tickets_processados.add((id_ticket, pasta_raiz, pasta_destino))
            logging.info(f"Doc {id_doc} processado no BD.")
            
        except Exception as e:
            logging.error(f"Erro no Doc {id_doc}: {e}")

    # 7. Gera os arquivos físicos na pasta correta
    for id_ticket, pasta_raiz, pasta_destino in tickets_processados:
        pasta_final_txt = Path(pasta_raiz) / pasta_destino # Salva direto em TOMADAS
        gerar_arquivos_dominio(id_ticket, pasta_final_txt)

    return len(pendentes)

if __name__ == "__main__":
    executar_tomados()