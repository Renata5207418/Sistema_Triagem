import os
import sys
import logging
import mimetypes
import shutil
import fitz
from datetime import datetime
import io
import base64
from pathlib import Path
from dotenv import load_dotenv
import unicodedata

pasta_atual = str(Path(__file__).parent)
if pasta_atual not in sys.path:
    sys.path.append(pasta_atual)

from motor_ia import classificar_documento_claude
from db.db_resiliencia import db
from db.db_dominio import DatabaseConnection

# --- CONFIGURAÇÃO DE LOGS ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [TRIAGEM] %(message)s",
    datefmt="%H:%M:%S"
)

RAIZ_PROJETO = Path(__file__).parent.parent
load_dotenv(dotenv_path=RAIZ_PROJETO / ".env")

BASE_CLIENTES = Path(os.getenv("CLIENTES_DIR", RAIZ_PROJETO / "CLIENTES_REDE"))

MAPA_PASTAS = {    
    'invoice_exterior': 'DOCUMENTOS GERAIS',
    'fatura_consumo': 'DOCUMENTOS GERAIS',
    'comprovante_pagamento': 'DOCUMENTOS GERAIS',
    'danfe': 'DANFE',
    'extrato': 'EXTRATO',
    'planilhas': 'PLANILHAS',
    'xml': 'XML',
    'fatura_locacao': 'DOCUMENTOS GERAIS',
    'revisao_manual': 'LOW_CONFIDENCE',    
    'rh': 'RH',
    'guia': 'DOCUMENTOS GERAIS',
    'boleto': 'DOCUMENTOS GERAIS',
    'nota_debito': 'DOCUMENTOS GERAIS',
    'dacte': 'DOCUMENTOS GERAIS',
    'cte': 'DOCUMENTOS GERAIS',
    'documentos_gerais': 'DOCUMENTOS GERAIS' 
}


# ==========================================
# CAMADA PRÉ-IA / UTILITÁRIOS
# ==========================================
def normalizar_texto(texto: str) -> str:
    texto = texto.lower().strip()
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("utf-8")


def fechar_doc_seguro(doc):
    try:
        if doc is not None:
            doc.close()
    except Exception:
        pass


def mover_arquivo_seguro(origem: Path, destino: Path) -> bool:
    try:
        if origem.exists():
            shutil.move(str(origem), str(destino))
            return True

        logging.warning(f"Arquivo não encontrado para mover: {origem}")
        return False

    except Exception as e:
        logging.error(f"Erro ao mover arquivo {origem} para {destino}: {e}")
        return False

def copiar_recursivo_robusto(origem: Path, destino: Path):
    """Copia arquivos tratando caminhos longos (locais e rede UNC)."""
    try:
        def preparar_caminho(p: Path) -> str:
            path_str = str(p.resolve())
            if os.name != 'nt': return path_str
            if path_str.startswith("\\\\?\\"): return path_str
            
            if path_str.startswith("\\\\"):
                return "\\\\?\\UNC\\" + path_str[2:]
            
            return "\\\\?\\" + path_str

        origem_longa = preparar_caminho(origem)
        destino_longo = preparar_caminho(destino)

        os.makedirs(destino_longo, exist_ok=True)

        for item in origem.iterdir():
            dest_item = destino / item.name
            
            if item.is_dir():
                copiar_recursivo_robusto(item, dest_item)
            else:
                src = preparar_caminho(item)
                dst = preparar_caminho(dest_item)
                try:
                    shutil.copy2(src, dst)
                except Exception as e:
                    logging.error(f"Falha ao copiar arquivo {item.name}: {e}")
                    
    except Exception as e:
        logging.error(f"Erro na cópia robusta: {e}")


def pre_classificar_por_texto(texto: str) -> str:
    t = normalizar_texto(texto)

    rh_keywords = [
        "folha individual de ponto", "programacao de ferias", "aviso de ferias",
        "recibo de ferias", "holerite", "recibo de pagamento de salario",
        "quadro de horario de trabalho", "controle de ponto", "guia de recolhimento rescisorio"
    ]
    for kw in rh_keywords:
        if kw in t:
            return "rh"

    gerais_keywords = [
        "solicitacao de reembolso", "comprovante de deposito", 
        "aplicacao financeira", "nota de debito", "demonstrativo de investimento",
        "recibo de reembolso", "aviso de lancamento"
    ]
    for kw in gerais_keywords:
        if kw in t:
            return "documentos_gerais"

    return ""


def detectar_tipo_pagina(texto: str) -> str:
    t = normalizar_texto(texto)

    if "extrato consolidado" in t or "extrato de conta" in t or "saldo anterior" in t or "lancamentos do periodo" in t:
        return "extrato"
    if "nfs-e" in t or "nota fiscal de servico" in t:
        return "nota_servico"
    if "documento de arrecadacao" in t or "gnre" in t or "simples nacional" in t or ("dam" in t and "prefeitura" in t):
        return "guia"
    if "linha digitavel" in t or (("codigo de barras" in t or "ficha de compensacao" in t) and "banco" in t):
        return "boleto"
    if "comprovante de pagamento" in t or "comprovante pix" in t or "recibo" in t:
        return "comprovante"
    if "darf" in t and "lancamentos do periodo" not in t:
        return "guia"
    if "nota fiscal eletronica de repasse" in t or "nf-r" in t or "valor do repasse" in t:
        return "nota_repasse"

    return "desconhecido"


def analisar_documento_misto(doc) -> str:
    try:
        if len(doc) <= 2:
            return "OK"

        tipos = []
        paginas_com_texto = 0

        for i in range(min(len(doc), 6)):
            texto = doc[i].get_text("text")

            if not texto or len(texto.strip()) < 80:
                continue

            paginas_com_texto += 1
            tipos.append(detectar_tipo_pagina(texto))

        tipos_unicos = set(tipos)

        if "desconhecido" in tipos_unicos and len(tipos_unicos) > 1:
            tipos_unicos.remove("desconhecido")

        if "extrato" in tipos_unicos:
            for falso_positivo in ["boleto", "guia"]:
                if falso_positivo in tipos_unicos:
                    tipos_unicos.remove(falso_positivo)

        if len(tipos_unicos) > 1:
            logging.info(f"Pré-IA: Frankenstein real detectado. Tipos={tipos_unicos}")
            return "DOCUMENTOS_UNIFICADOS"

        return "OK"

    except Exception:
        return "OK"


# ==========================================
# 1. FUNÇÕES DE ARQUIVO E REDE
# ==========================================
def obter_nome_unico(caminho_destino: Path, nome_arquivo: str) -> Path:
    caminho_completo = caminho_destino / nome_arquivo
    if not caminho_completo.exists(): return caminho_completo
    nome_base = caminho_completo.stem
    extensao = caminho_completo.suffix
    contador = 1
    while True:
        novo_caminho = caminho_destino / f"{nome_base}_{contador}{extensao}"
        if not novo_caminho.exists(): return novo_caminho
        contador += 1


def limpar_pastas_vazias(pasta_raiz: Path):
    pastas_seguras = list(MAPA_PASTAS.values()) + [
        'LIMITE_PAGINAS', 'ERRO_PROCESSAMENTO', 'LOW_CONFIDENCE',
        'IMAGEM_PRINT', 'NOTAS_DE_SERVICO', 'DOCUMENTOS_UNIFICADOS',
        'COMPACTADOS_JA_EXTRAIDOS'
    ]
    for root, dirs, files in os.walk(pasta_raiz, topdown=False):
        for d in dirs:
            dir_path = Path(root) / d
            if dir_path.name not in pastas_seguras and not any(dir_path.iterdir()):
                try: dir_path.rmdir()
                except OSError: pass


def detectar_tipo_real(caminho_arquivo: Path):
    SIGNATURES = {
        b'%PDF': ('.pdf', 'PDF'),
        b'PK\x03\x04': ('.zip', 'COMPACTADOS'),
        b'Rar!\x1a\x07': ('.rar', 'COMPACTADOS'),
        b'\xff\xd8\xff': ('.jpg', 'IMAGEM_PRINT'),
        b'\x89PNG': ('.png', 'IMAGEM_PRINT'),
        b'\xd0\xcf\x11\xe0': ('.xls', 'PLANILHAS')
    }
    try:
        with open(caminho_arquivo, 'rb') as f:
            header = f.read(100)
        ext_original = caminho_arquivo.suffix.lower()
        for sig, (ext, cat) in SIGNATURES.items():
            if header.startswith(sig):
                if sig == b'PK\x03\x04' and ext_original in ['.docx', '.xlsx', '.pptx']: return None, None
                return ext, cat
        if b'<?xml' in header or b'<nfeProc' in header or b'<cteProc' in header or b'<resNFe' in header:
            return '.xml', 'XML'
        
        header_lower = header.lower()
        if b'<!doctype html' in header_lower or b'<html' in header_lower:
            return '.html', 'IGNORADOS'
        
    except Exception:
        pass
    return None, None


def separar_nao_pdfs(pasta_ticket: Path, id_ticket: int):
    regras_extensao = {
        '.csv': 'PLANILHAS', '.xls': 'PLANILHAS', '.xlsx': 'PLANILHAS',
        '.ofx': 'EXTRATO', '.doc': 'DOCUMENTOS GERAIS', '.docx': 'DOCUMENTOS GERAIS',
        '.xml': 'XML', '.txt': 'DOCUMENTOS GERAIS', '.png': 'IMAGEM_PRINT',        
        '.jpg': 'IMAGEM_PRINT', '.jpeg': 'IMAGEM_PRINT', '.heic': 'IMAGEM_PRINT',     
        '.zip': 'COMPACTADOS', '.rar': 'COMPACTADOS', '.vcf': 'DOCUMENTOS GERAIS',
        '.ret': 'EXTRATO', '.ini': 'IGNORADOS', '.db': 'IGNORADOS'
    }

    pastas_seguranca = list(MAPA_PASTAS.values()) + [
        'NOTAS_DE_SERVICO', 'DOCUMENTOS_UNIFICADOS', 'ERRO_PROCESSAMENTO',
        'LIMITE_PAGINAS', 'COMPACTADOS', 'IMAGEM_PRINT', 'COMPACTADOS_JA_EXTRAIDOS'
    ]

    for arquivo in list(pasta_ticket.rglob('*')):
        if not arquivo.is_file() or arquivo.name.startswith('.') or arquivo.stat().st_size == 0: continue
        if any(p in arquivo.parts for p in pastas_seguranca): continue

        ext_original = arquivo.suffix.lower()
        ext_dna, categoria_dna = detectar_tipo_real(arquivo)

        if ext_dna == '.pdf':
            if ext_original != '.pdf':
                novo_nome = arquivo.with_suffix('.pdf')
                arquivo.rename(novo_nome)
                logging.info(f"Resgatado PDF: {arquivo.name} -> {novo_nome.name}")
            continue

        if categoria_dna:
            destino = pasta_ticket / categoria_dna
            destino.mkdir(exist_ok=True)
            nome_final = arquivo.name if ext_original == ext_dna else arquivo.name + ext_dna
            caminho_final = obter_nome_unico(destino, nome_final)
            mover_arquivo_seguro(arquivo, caminho_final)
            db.registrar_documento_triado(id_ticket, arquivo.name, caminho_final.name, ext_dna.replace('.', '').upper(), categoria_dna, "SUCESSO")
            continue

        if ext_original in regras_extensao:
            nome_pasta = regras_extensao[ext_original]
            destino = pasta_ticket / nome_pasta
            destino.mkdir(exist_ok=True)
            caminho_final = obter_nome_unico(destino, arquivo.name)
            mover_arquivo_seguro(arquivo, caminho_final)
            categoria_label = nome_pasta if nome_pasta != 'IGNORADOS' else "Lixo de Sistema"
            db.registrar_documento_triado(id_ticket, arquivo.name, caminho_final.name, ext_original.replace('.', '').upper(), categoria_label, "SUCESSO")
            continue

        if ext_original == '.pdf': continue

        nome_pasta = 'ERRO_PROCESSAMENTO'
        destino = pasta_ticket / nome_pasta
        destino.mkdir(exist_ok=True)
        caminho_final = obter_nome_unico(destino, arquivo.name)
        mover_arquivo_seguro(arquivo, caminho_final)
        
        db.registrar_documento_triado(
            id_ticket, 
            arquivo.name, 
            caminho_final.name, 
            "lixo_digital", 
            nome_pasta, 
            "IGNORADO",
            f"Extensão não reconhecida ou lixo digital: {ext_original}"
        )


def mover_cliente_rede(id_ticket: int, pasta_ticket: Path, cod_emp: str):
    if not cod_emp or cod_emp == "0": return
    
    db_dom = DatabaseConnection()
    cod_final_rede = cod_emp
    
    try:
        if db_dom.connect():
            cod_final_rede = db_dom.descobrir_codigo_matriz(cod_emp)
            db_dom.close()

        mes_ano = pasta_ticket.parent.name
        ano = mes_ano.split(".")[1]
        cliente_dir = None

        if BASE_CLIENTES.exists():
            for d in BASE_CLIENTES.iterdir():
                if d.is_dir() and (d.name.startswith(f"{cod_final_rede}-") or d.name.startswith(f"{cod_final_rede} -")):
                    cliente_dir = d
                    break

        if not cliente_dir: 
            logging.warning(f"Ticket {id_ticket}: Pasta da matriz {cod_final_rede} não encontrada na rede.")
            return

        pasta_contabil_nome = next((d.name for d in cliente_dir.iterdir() if d.name.upper() in ["CONTÁBIL", "CONTABIL"]), "CONTÁBIL")
        nome_pasta_os = pasta_ticket.name
        
        destino_contabil = cliente_dir / pasta_contabil_nome / "MOVIMENTO" / ano / mes_ano / "TRIAGEM_ROBO" / nome_pasta_os
        destino_fiscal = cliente_dir / "FISCAL" / "IMPOSTOS" / ano / mes_ano / "MCALC" / "TRIAGEM_ROBO" / nome_pasta_os

        logging.info(f"Ticket {id_ticket}: Espelhando arquivos na rede (Modo Robusto)...")
        copiar_recursivo_robusto(pasta_ticket, destino_contabil)
        copiar_recursivo_robusto(pasta_ticket, destino_fiscal)
        
        logging.info(f"Ticket {id_ticket}: Arquivos espelhados com sucesso.")
        
    except Exception as e:
        logging.error(f"Ticket {id_ticket}: Erro rede ao processar matriz/filial: {e}")


# ==========================================
# 2. MOTOR PRINCIPAL
# ==========================================
def processar_ticket(id_ticket: int, caminho_pasta: str, qtd_esperada: int, cod_emp: str):
    pasta_ticket = Path(caminho_pasta)

    if not pasta_ticket.exists():
        db.marcar_ticket_triado(id_ticket, "ERRO_PASTA", "Pasta física não encontrada.")
        return

    logging.info(f"--- Ticket {id_ticket} (Cód: {cod_emp}) ---")

    # === FAXINA DE LIXO DA APPLE (MAC) ANTES DE QUALQUER COISA ===
    for pasta_mac in pasta_ticket.rglob('__MACOSX'):
        shutil.rmtree(pasta_mac, ignore_errors=True)

    for lixo_arquivo in pasta_ticket.rglob('._*'):
        try: lixo_arquivo.unlink(missing_ok=True)
        except: pass    

    cnpjs_cliente = []
    if cod_emp and cod_emp != "0":
        db_dom = DatabaseConnection()
        try:
            if db_dom.connect(): cnpjs_cliente = db_dom.obter_cnpjs_do_grupo(cod_emp)
        except Exception as e: logging.error(f"Ticket {id_ticket}: erro BD Domínio: {e}")
        finally:
            try: db_dom.close()
            except: pass

    arquivos_encontrados = len([f for f in pasta_ticket.rglob('*') if f.is_file()])
    separar_nao_pdfs(pasta_ticket, id_ticket)

    pastas_seguranca = list(MAPA_PASTAS.values()) + [
        'LIMITE_PAGINAS', 'ERRO_PROCESSAMENTO', 'LOW_CONFIDENCE',
        'IMAGEM_PRINT', 'NOTAS_DE_SERVICO', 'DOCUMENTOS_UNIFICADOS', 
        'COMPACTADOS', 'COMPACTADOS_JA_EXTRAIDOS'
    ]

    pdfs = [f for f in pasta_ticket.rglob('*') if f.is_file() and f.suffix.lower() == '.pdf']

    for arquivo in pdfs:
        if arquivo.name.startswith('.') or arquivo.stat().st_size == 0: continue
        if any(p in arquivo.parts for p in pastas_seguranca): continue

        nome_minusculo = arquivo.name.lower()
        
        # =============================================================
        # 1. BYPASS POR NOME (AGORA NO TOPO - IGNORA SENHA)
        # =============================================================
        categoria_bypass = None
        PREFIXOS_SEGUROS = [
            'guia', 'boleto', 'invoice_exterior', 'fatura_consumo',
            'comprovante_pagamento', 'danfe', 'extrato', 'planilhas',
            'xml', 'fatura_locacao', 'nota_debito', 'rh', 'documentos_gerais',
            'dacte', 'cte', 'tomadas', 'emitidas', 'terceiros' 
        ]
        
        for prefixo in PREFIXOS_SEGUROS:
            if nome_minusculo.startswith(f"{prefixo}_") or nome_minusculo.startswith(f"{prefixo}-"):
                categoria_bypass = prefixo
                break

        if not categoria_bypass:
            if "extrato" in nome_minusculo: categoria_bypass = "extrato"
            elif "sindicato" in nome_minusculo: categoria_bypass = "rh"
            elif any(k in nome_minusculo for k in ["reembolso", "deposito", "aplicacao", "recibo", "debito"]):
                categoria_bypass = "documentos_gerais"

        if categoria_bypass:
            if categoria_bypass in ['tomadas', 'emitidas', 'terceiros']:
                categoria_ia = "nota_servico"
                nome_pasta_final = f"NOTAS_DE_SERVICO/{categoria_bypass.upper()}"
            else:
                categoria_ia = categoria_bypass
                nome_pasta_final = MAPA_PASTAS.get(categoria_ia, 'DOCUMENTOS GERAIS')
            
            destino = Path(os.path.normpath(str(pasta_ticket / nome_pasta_final)))
            destino.mkdir(parents=True, exist_ok=True)
            nome_limpo = arquivo.stem.replace(' ', '_')[:80]
            novo_nome = f"{categoria_bypass.upper()}_{nome_limpo}{arquivo.suffix}"
            caminho_final = obter_nome_unico(destino, novo_nome)
            
            mover_arquivo_seguro(arquivo, caminho_final)
            db.registrar_documento_triado(id_ticket, arquivo.name, caminho_final.name, categoria_ia, str(nome_pasta_final), "SUCESSO", texto_extraido="Bypass NOME.")
            continue

        # =============================================================
        # 2. SE NÃO FOR BYPASS, TENTA ABRIR E CHECAR SENHA
        # =============================================================
        doc = None
        primeira_pag = None

        try:
            doc = fitz.open(str(arquivo))

            if doc.needs_pass:
                fechar_doc_seguro(doc)
                doc = None
                raise ValueError("Protegido por Senha")

            if len(doc) > 250:
                fechar_doc_seguro(doc)
                doc = None
                destino = pasta_ticket / 'LIMITE_PAGINAS'
                destino.mkdir(exist_ok=True)
                caminho_final = obter_nome_unico(destino, arquivo.name)
                mover_arquivo_seguro(arquivo, caminho_final)
                db.registrar_documento_triado(id_ticket, arquivo.name, caminho_final.name, "ignorar_tamanho", "LIMITE_PAGINAS", "SUCESSO")
                continue            

            # Extração e Decisão
            texto_completo = ""
            for pagina in doc: texto_completo += pagina.get_text()

            if analisar_documento_misto(doc) == "DOCUMENTOS_UNIFICADOS":
                destino = pasta_ticket / 'DOCUMENTOS_UNIFICADOS'
                destino.mkdir(exist_ok=True)
                caminho_final = obter_nome_unico(destino, f"DOCUMENTO_UNIFICADO_{arquivo.stem.replace(' ', '_')[:80]}{arquivo.suffix}")
                fechar_doc_seguro(doc)
                doc = None
                mover_arquivo_seguro(arquivo, caminho_final)
                db.registrar_documento_triado(id_ticket, arquivo.name, caminho_final.name, "documento_unificado", "DOCUMENTOS_UNIFICADOS", "ERRO", "Múltiplos tipos.")
                continue

            categoria_texto = pre_classificar_por_texto(texto_completo)
            if categoria_texto:
                categoria_ia = categoria_texto
                status_banco = "SUCESSO"
                nome_pasta_final = MAPA_PASTAS.get(categoria_ia, 'DOCUMENTOS GERAIS')
                fechar_doc_seguro(doc)
                doc = None
            else:
                # IA
                primeira_pag = fitz.open()
                primeira_pag.insert_pdf(doc, from_page=0, to_page=0)
                pdf_bytes = primeira_pag.tobytes()
                fechar_doc_seguro(primeira_pag)
                fechar_doc_seguro(doc)
                doc = None
                pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')
                resultado_ia = classificar_documento_claude(pdf_base64)
                categoria_ia = resultado_ia.get("categoria", "documentos_gerais")
                status_banco = "SUCESSO"

                if categoria_ia == 'ERRO_API':
                    status_banco = "ERRO"
                    nome_pasta_final = "ERRO_PROCESSAMENTO"
                    categoria_ia = "ERRO"
                elif categoria_ia == 'revisao_manual':
                    status_banco = "ATENCAO"
                    nome_pasta_final = "LOW_CONFIDENCE"
                
                elif categoria_ia == 'nota_servico':
                    if "repasse" in texto_completo.lower():
                        nome_pasta_final = "NOTAS_DE_SERVICO/TERCEIROS"
                    else:
                        cnpj_p = resultado_ia.get("cnpj_prestador")
                        cnpj_t = resultado_ia.get("cnpj_tomador")
                        
                        if cnpj_p in cnpjs_cliente: 
                            nome_pasta_final = "NOTAS_DE_SERVICO/EMITIDAS"
                        elif cnpj_t in cnpjs_cliente: 
                            nome_pasta_final = "NOTAS_DE_SERVICO/TOMADAS"
                        else: 
                            nome_pasta_final = "NOTAS_DE_SERVICO/TERCEIROS"
                else:
                    nome_pasta_final = MAPA_PASTAS.get(categoria_ia, 'DOCUMENTOS GERAIS')
                    if nome_pasta_final == 'LOW_CONFIDENCE': status_banco = "ATENCAO"

            # Finalização
            destino = Path(os.path.normpath(str(pasta_ticket / nome_pasta_final)))
            destino.mkdir(parents=True, exist_ok=True)
            novo_nome = f"{categoria_ia.upper()}_{arquivo.stem.replace(' ', '_')[:80]}{arquivo.suffix}"
            caminho_final = obter_nome_unico(destino, novo_nome)
            mover_arquivo_seguro(arquivo, caminho_final)
            db.registrar_documento_triado(id_ticket, arquivo.name, caminho_final.name, categoria_ia, str(nome_pasta_final), status_banco, texto_extraido=texto_completo)

        except Exception as e:
            fechar_doc_seguro(doc)
            fechar_doc_seguro(primeira_pag)
            logging.error(f"Erro PDF {arquivo.name}: {e}")
            erro_dir = pasta_ticket / 'ERRO_PROCESSAMENTO'
            erro_dir.mkdir(exist_ok=True)
            caminho_final = obter_nome_unico(erro_dir, arquivo.name)
            mover_arquivo_seguro(arquivo, caminho_final)
            
            erro_str = str(e).lower()
            status_erro = "PENDENTE_SENHA" if "pass" in erro_str or "protegido" in erro_str else "ERRO"
            
            if "failed to open file" in erro_str or "cannot open" in erro_str:
                mensagem_erro = "Arquivo corrompido ou atalho inválido"
            elif status_erro == "PENDENTE_SENHA":
                mensagem_erro = "Protegido por senha"
            else:
                mensagem_erro = f"Erro de leitura: {str(e)[:60]}" 

            db.registrar_documento_triado(id_ticket, arquivo.name, caminho_final.name, "ERRO", "ERRO_PROCESSAMENTO", status_erro, mensagem_erro)

    limpar_pastas_vazias(pasta_ticket)
    db.marcar_ticket_triado(id_ticket, "CONCLUIDO" if arquivos_encontrados == qtd_esperada else "CONCLUIDO_COM_DIVERGENCIA")
    mover_cliente_rede(id_ticket, pasta_ticket, cod_emp)


def executar_triagem():
    logging.info("Iniciando Módulo de Triagem IA...")
    db._criar_tabelas()
    pendentes = db.get_tickets_pendentes_triagem()
    if not pendentes: return 0

    processados = 0
    for p in pendentes:
        id_ticket = p["id_ticket"]
        
        agora_db = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db.executar_update("UPDATE downloads SET ultima_tentativa = ? WHERE id_ticket = ?", (agora_db, id_ticket))
        
        if not p["caminho_pasta"]:
            db.marcar_ticket_triado(id_ticket, "SEM_ANEXOS")
            processados += 1
            continue

        try:
            processar_ticket(id_ticket, p["caminho_pasta"], p["qtd_anexos_esperados"], p["cod_emp"])
            processados += 1
        except Exception as e:
            logging.exception(f"[TRIAGEM] Erro crítico no ticket {id_ticket}: {e}")
            db.marcar_ticket_triado(id_ticket, "ERRO_TRIAGEM", str(e)[:500])
            processados += 1

    return processados

if __name__ == "__main__":
    executar_triagem()
    