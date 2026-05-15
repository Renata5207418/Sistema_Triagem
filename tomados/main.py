import logging
from pathlib import Path
import sys
import sqlite3 # ADICIONADO PARA BUSCAR O CAMINHO DO ARQUIVO

pasta_atual = str(Path(__file__).parent.parent)
if pasta_atual not in sys.path:
    sys.path.append(pasta_atual)

from db.db_resiliencia import db
from tomados.utils.acumuladores import acumuladores
from tomados.utils.consulta_for import dados_fornecedor
from tomados.utils.motor_extracao import extrair_dados_nota_claude
from tomados.utils.gerador_txt import gerar_arquivos_dominio

# Importa a função que faz a sincronização AWS x Tomados.
# Mantendo como está hoje no projeto.
from dashboard.api import sincronizar_aws_internamente


def soma_csrf(pis, cofins, csll):
    """Soma PIS, COFINS e CSLL (ex: '10,50' + '5,00' -> '15,50')."""
    try:
        p = float(str(pis).replace(",", ".")) if pis else 0.0
        c = float(str(cofins).replace(",", ".")) if cofins else 0.0
        s = float(str(csll).replace(",", ".")) if csll else 0.0
        return str(round(p + c + s, 2)).replace(".", ",")
    except:
        return "0,00"


def obter_valor(dados, chave, padrao=""):
    """
    Busca valor no JSON da IA sem quebrar o processamento.
    """
    valor = dados.get(chave, padrao)

    if valor is None:
        return padrao

    return valor


def validar_dados_minimos(dados_ia):
    """
    Valida o mínimo necessário para salvar uma nota tomada.
    O Tomador (cpf_cnpj_tomador) FOI REMOVIDO da lista restrita, pois muitas 
    notas legítimas (ao consumidor final) não possuem CNPJ do tomador na folha.
    """
    if not isinstance(dados_ia, dict):
        return False, "Retorno da IA não é um JSON/dict."

    # Apenas o essencial que define que o documento existe
    campos_obrigatorios = [
        "cpf_cnpj_prestador",
        "numero_documento",
        "data_emissao",
        "valor_servicos"
    ]

    ausentes = []

    for campo in campos_obrigatorios:
        valor = str(dados_ia.get(campo, "") or "").strip()
        # Se for o valor serviços, não pode ser vazio (mas pode ser "0,00")
        if not valor:
            ausentes.append(campo)

    if ausentes:
        return False, f"Campos obrigatórios ausentes: {', '.join(ausentes)}"

    return True, ""


def tentar_sincronizar_malha_uma_vez(cod_empresa, competencia):
    """
    Faz a primeira sincronização AWS da empresa/competência.

    Como a função sincronizar_aws_internamente será chamada com forcar=False,
    ela só consulta AWS se ainda não existir dado salvo na malha.
    """
    if not cod_empresa or not competencia:
        logging.warning(
            f"Malha AWS ignorada: cod_empresa ou competencia ausente. "
            f"cod_empresa={cod_empresa}, competencia={competencia}"
        )
        return

    try:
        resultado = sincronizar_aws_internamente(
            cod_empresa=str(cod_empresa).strip(),
            competencia=competencia,
            forcar=False
        )

        if resultado.get("sincronizou"):
            logging.info(
                f"Malha AWS sincronizada: empresa {cod_empresa}, competência {competencia}."
            )
        else:
            logging.info(
                f"Malha AWS já existia: empresa {cod_empresa}, competência {competencia}. "
                f"Última atualização: {resultado.get('ultima_atualizacao')}"
            )

    except Exception as e:
        logging.error(
            f"Erro ao sincronizar malha AWS inicial "
            f"empresa {cod_empresa}, competência {competencia}: {e}"
        )


def processar_documento_tomado(doc, tickets_processados, empresas_para_sincronizar):
    """
    Processa um único documento tomado.

    Importante:
    - erro definitivo tira o documento da fila;
    - erro temporário de API mantém pendente;
    - sucesso marca PROCESSADO.
    """
    id_doc = doc["id_documento"]
    id_ticket = doc["id_ticket"]
    texto = doc["texto_extraido"]
    pasta_destino = doc["pasta_destino"]
    pasta_raiz = doc["pasta_raiz_ticket"]

    cod_empresa = doc.get("cod_empresa")
    competencia = doc.get("competencia")

    # Segurança extra. Idealmente o filtro já vem do banco.
    if pasta_destino != "NOTAS_DE_SERVICO/TOMADAS":
        db.atualizar_status_tomados(id_doc, "IGNORADO_NAO_E_TOMADO")
        return

    try:
        # =========================================================
        # BUSCA O CAMINHO FÍSICO DO ARQUIVO DIRETO NO BANCO
        # Isso garante que a IA Visual encontre o PDF escaneado
        # =========================================================
        caminho_pdf = None
        try:
            db_path = Path(__file__).parent.parent / "banco_rpa.db"
            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute("""
                    SELECT d.caminho_pasta, dt.pasta_destino, dt.nome_final 
                    FROM documentos_triados dt
                    JOIN downloads d ON dt.id_ticket = d.id_ticket
                    WHERE dt.id = ?
                """, (id_doc,)).fetchone()
                
                if row and row['caminho_pasta'] and row['nome_final']:
                    caminho_pdf = str(Path(row['caminho_pasta']) / row['pasta_destino'] / row['nome_final'])
        except Exception as e:
            logging.error(f"Erro ao montar caminho do PDF para visão: {e}")

        # AGORA ENVIAMOS O TEXTO E O CAMINHO
        dados_ia = extrair_dados_nota_claude(texto, caminho_pdf=caminho_pdf)

        # Compatível com ajuste futuro no motor_extracao.py:
        # quando Claude estiver fora/rate limit geral, ele pode retornar esse marcador.
        if isinstance(dados_ia, dict) and dados_ia.get("_erro_temporario_api"):
            logging.warning(
                f"Doc {id_doc}: erro temporário da API Claude. "
                f"Mantendo PENDENTE para próxima execução."
            )
            return

        if not dados_ia:
            logging.warning(f"Doc {id_doc} sem retorno da IA. Enviando para revisão.")
            db.atualizar_status_tomados(id_doc, "ERRO_EXTRACAO_IA")
            return

        valido, motivo = validar_dados_minimos(dados_ia)

        if not valido:
            logging.warning(f"Doc {id_doc} com dados insuficientes: {motivo}")
            db.atualizar_status_tomados(id_doc, "ERRO_EXTRACAO_IA")
            return

        cpf_cnpj_prestador = obter_valor(dados_ia, "cpf_cnpj_prestador")
        cpf_cnpj_tomador = obter_valor(dados_ia, "cpf_cnpj_tomador")

        # Consulta API/Cache para o PRESTADOR, quem emitiu a nota.
        forn = dados_fornecedor(cpf_cnpj_prestador) or {}

        # Se o fornecedor não vier bem, evita quebrar o documento.
        cnae = forn.get("cnae", "")
        acumulador = acumuladores.get(cnae, "8")

        razao_social = forn.get("razao_social", "")
        uf_fornecedor = forn.get("uf", "")
        municipio = forn.get("municipio", "")

        # Consulta API/Cache para o TOMADOR, que é o cliente.
        cliente = dados_fornecedor(cpf_cnpj_tomador) or {}
        uf_cliente = cliente.get("uf", "PR")

        # Lógica dinâmica do CFOP.
        cfop = "1933" if uf_fornecedor == uf_cliente else "2933"

        # Soma CRF.
        crf = soma_csrf(
            obter_valor(dados_ia, "valor_pis", "0,00"),
            obter_valor(dados_ia, "valor_cofins", "0,00"),
            obter_valor(dados_ia, "valor_csll", "0,00")
        )

        valor_servicos = obter_valor(dados_ia, "valor_servicos", "0,00")

        # Evita duplicar resultado caso o documento tenha sido reprocessado por algum motivo.
        db.executar_update(
            "DELETE FROM resultados_tomados WHERE id_documento = ?",
            (id_doc,)
        )

        db.executar_update("""
            INSERT INTO resultados_tomados (
                id_ticket, 
                id_documento, 
                cpf_cnpj, 
                razao_social, 
                uf, 
                municipio,
                numero_documento, 
                serie, 
                data_emissao, 
                acumulador, 
                cfop,
                valor_servicos, 
                valor_contabil, 
                base_calculo, 
                valor_irrf,
                valor_pis, 
                valor_cofins, 
                valor_csll, 
                valor_crf, 
                valor_inss, 
                tomador
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            id_ticket,
            id_doc,
            cpf_cnpj_prestador,
            razao_social,
            uf_fornecedor,
            municipio,
            obter_valor(dados_ia, "numero_documento"),
            obter_valor(dados_ia, "serie"),
            obter_valor(dados_ia, "data_emissao"),
            acumulador,
            cfop,
            valor_servicos,
            valor_servicos,
            valor_servicos,
            obter_valor(dados_ia, "valor_irrf", "0,00"),
            obter_valor(dados_ia, "valor_pis", "0,00"),
            obter_valor(dados_ia, "valor_cofins", "0,00"),
            obter_valor(dados_ia, "valor_csll", "0,00"),
            crf,
            obter_valor(dados_ia, "valor_inss", "0,00"),
            cpf_cnpj_tomador
        ))

        db.atualizar_status_tomados(id_doc, "PROCESSADO")

        tickets_processados.add((id_ticket, pasta_raiz, pasta_destino))

        if cod_empresa and competencia:
            empresas_para_sincronizar.add((str(cod_empresa).strip(), competencia))

        logging.info(f"Doc {id_doc} processado no BD.")

    except Exception as e:
        logging.exception(f"Erro no Doc {id_doc}: {e}")
        db.atualizar_status_tomados(id_doc, "ERRO_TOMADOS")
        return


def executar_tomados():
    """
    Executa o módulo Tomados.

    Regra importante:
    - documentos com erro definitivo saem da fila;
    - documentos com erro temporário de API permanecem pendentes;
    - documentos corrigidos manualmente entram novamente pela triagem,
      porque a rota de upload apaga tickets_triados e volta downloads para SUCESSO.
    """
    pendentes = db.get_documentos_pendentes_tomados(limite=50)

    if not pendentes:
        return 0

    tickets_processados = set()
    empresas_para_sincronizar = set()

    for doc in pendentes:
        processar_documento_tomado(
            doc=doc,
            tickets_processados=tickets_processados,
            empresas_para_sincronizar=empresas_para_sincronizar
        )

    # Gera os arquivos físicos na pasta correta.
    for id_ticket, pasta_raiz, pasta_destino in tickets_processados:
        try:
            pasta_final_txt = Path(pasta_raiz) / pasta_destino
            gerar_arquivos_dominio(id_ticket, pasta_final_txt)
            logging.info(f"Arquivos Domínio gerados para OS {id_ticket}.")
        except Exception as e:
            logging.exception(f"Erro ao gerar arquivos Domínio para OS {id_ticket}: {e}")

    # Depois que os tomados foram salvos no banco,
    # faz a primeira sincronização AWS uma vez por empresa/competência.
    for cod_empresa, competencia in empresas_para_sincronizar:
        tentar_sincronizar_malha_uma_vez(cod_empresa, competencia)

    return len(pendentes)


if __name__ == "__main__":
    logging.info("Iniciando varredura contínua da fila de Tomados...")
    lote = 1
    while True:
        qtd_processada = executar_tomados()
        if qtd_processada == 0:
            logging.info("Fila de Tomados vazia! Todas as OS foram concluídas.")
            break
        
        logging.info(f"Lote {lote} concluído ({qtd_processada} documentos). Buscando mais na fila...")
        lote += 1  
