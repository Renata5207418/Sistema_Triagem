# 🚀 Sistema de Triagem RPA (Refatoração Cloud)

Este projeto é uma evolução de alto desempenho da arquitetura original [**Projeto_Claud**](https://github.com/Renata5207418/Projeto_Claud). O objetivo é automatizar a esteira completa de documentos fiscais, desde a captura no Onvio até o processamento final, utilizando uma estrutura robusta, resiliente e modernizada.

## 🏗️ Evolução e Robustez
Diferente da versão legacy, esta refatoração transforma os processos em módulos profissionais coordenados por um orquestrador central.

### 🛠️ O que mudou? (Upgrade Tecnológico)
| Recurso | Versão Anterior (Legacy) | Nova Versão (Refatorada) |
| :--- | :--- | :--- |
| **Motor Web** | Selenium + ChromeDriver | **Playwright (Interceptação de API)** |
| **Identificação** | Texto Exato / Manual | **Code Priority + Fuzzy Matching** |
| **Organização** | Pastas Simples | **Hierarquia Cronológica (MM.YYYY)** |
| **Resiliência** | Sensível a interrupções | **Banco SQLite de Persistência** |
| **Ambiente** | Pastas Isoladas | **Arquitetura Modular Unificada** |

---

## 📂 Estrutura do Projeto

```text
SISTEMA_TRIAGEM/
├── .venv/                  # Ambiente virtual Python
├── arquivos/               # (Rede) Destino dos arquivos (Empresa/Mês/Ticket)
├── .env                    # Configurações centralizadas (Senhas e Rotas)
├── banco_rpa.db            # Cérebro do sistema (Status, Logs e Descrições)
├── requirements.txt        # Bibliotecas necessárias
├── orquestrador.py         # Maestro: Coordena a execução de todos os robôs
│
├── download/               # 🤖 MÓDULO 1: Extrator Onvio (Cloud_1)
│   ├── main.py             # Login, Captura de Token e Loop de Ingestão
│   ├── db_dominio.py       # Conexão SQL Anywhere (Mapeamento Domínio)
│   ├── db_resiliencia.py   # Gestor de persistência e detecção de GAPs
│   └── __init__.py         # Definição de pacote
│
├── triagem/                # 🤖 MÓDULO 2: Classificador (Em desenvolvimento)
├── tomados/                # 🤖 MÓDULO 3: Lançador (Em desenvolvimento)
└── front/                  # 🖥️ Interface de monitoramento
```

---

## ⚙️ Destaques Técnicos (Módulo Download)
* **Performance:** Uso de Playwright para interceptar o `UDSLongToken`, permitindo downloads via chamadas diretas de API (muito mais rápido que cliques em tela).
* **Inteligência de Dados:** Prioriza o código de cliente do Onvio; em caso de ausência, utiliza o algoritmo `RapidFuzz` para cruzar dados com o banco Domínio, higienizando siglas (LTDA, S/A, etc).
* **Organização Automatizada:** Separação por período (`04.2026`) e auto-extração de arquivos ZIP/RAR com logs de erro em `.txt` para arquivos corrompidos.
* **Resiliência Local:** O banco `banco_rpa.db` armazena o status de cada ticket e a descrição enviada pelo cliente, evitando downloads duplicados e facilitando a auditoria.

---

## 🚀 Como Executar

### Pré-requisitos
1.  **Python 3.12+**
2.  **Driver SQL Anywhere 17** (para conexão com a Domínio).
3.  **Playwright** configurado no ambiente.

### Passo a Passo
```bash
# 1. Instalar dependências
pip install -r requirements.txt

# 2. Configurar Navegadores
playwright install chromium

# 3. Executar a esteira
python orquestrador.py
```

---

## 🛡️ Propriedade Intelectual e Licença
Este software foi desenvolvido por **Renata Boppré Scharf** para a **SCRYTA TECNOLOGIA LTDA.**

**Copyright (c) 2026 SCRYTA TECNOLOGIA LTDA. Todos os direitos reservados.**

A propriedade intelectual, código-fonte e binários associados pertencem exclusivamente à empresa, conforme a Lei do Software (Lei nº 9.609/98). É vedada a cópia ou distribuição não autorizada.
