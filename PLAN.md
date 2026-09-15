# 📋 PLANO DO PROJETO BP — Conversão de Balanços

## 🎯 Objetivo Principal

Criar um sistema automatizado que leia balanços de diversos formatos (PDF, Excel, CSV, TXT) de múltiplas empresas e setores, e converta-os para um modelo padrão utilizando a base de dados de plano de contas brasileiras como referência, com suporte a matching inteligente (fuzzy + IA).

---

## 📊 Estrutura de Dados

O projeto utiliza **4 estruturas complementares** no `data/plano_contas.json`:

```
{
  "forms": {},              # Mapa de abas do Excel → lista de códigos de contas
  "contas_flat": [],        # Lista achatada de todas as contas (busca direta por código)
  "contas_tree": [],        # Árvore hierárquica aninhada (com children)
  "contas_index": {}        # Índice mapa código → metadados (leve, sem children)
}
```

**Exemplos de campos por conta:**
- `codigo`: "1.1.1.2.1.10.03"
- `descricao`: "Descrição da conta"
- `tipo`: "ATIVO" | "PASSIVO" | "RECEITA" | etc.
- `natureza`: "Devedora" | "Credora"
- `nivel`: 1–8 (profundidade hierárquica)
- `parent_id`: "1.1.1.2.1.10" (conta pai)
- `forms`: ["L100A", "L100B"] (abas de origem)
- `formula`: "" (cálculo opcional)
- `tipo_do_lancamento`: "" (tipo de movimento contábil)

---

## 🗓️ Fases e Timeline

### ✅ **FASE 1: Organização e Documentação (Semana 1)**

**Objetivo:** Documentar o projeto, validar base de dados, estruturar pastas.

#### Tarefas
1. ✏️ **Documentar PLAN.md** com objetivos, pipeline, estrutura de dados, timeline.
2. 📖 **Criar README.md** com instruções de uso, estrutura de pastas, exemplos.
3. 🧪 **Validar JSON gerado** rodando `acctree_generate_json.py` com `plano_master.xlsx`.
4. 🔧 **Criar .env.example** com variáveis padrão (INPUT_EXCEL, OUTPUT_JSON, LOG_LEVEL).
5. 📁 **Criar estrutura src/bp/** com pastas: models/, generators/, parsers/, matchers/, utils/, validators/, exporters/.

#### Saídas esperadas
- [x] PLAN.md (este arquivo) preenchido
- [ ] README.md finalizado
- [ ] data/plano_contas.json validado com 4 estruturas
- [ ] .env.example criado
- [ ] Pastas em src/bp/ criadas

---

### 📦 **FASE 2: Refatoração do Core (Semana 2–3)**

**Objetivo:** Transformar scripts auxiliares em módulos reutilizáveis com testes.

#### Tarefas
1. 🏗️ **Mover lógica de geradores** para `src/bp/generators/plano_contas_generator.py` (classe + funções).
2. 🧮 **Criar modelos Pydantic** em `src/bp/models/conta.py`: ContaModel, BalanceteModel, validação.
3. 🔧 **Implementar PlanodeContas** em `src/bp/generators/plano_contas.py`:
   - Carrega tree + index + flat + forms do JSON
   - Métodos: `buscar_por_codigo()`, `buscar_por_descricao()`, `obter_hierarquia()`, `listar_contas_por_form()`
   - Cache em memória
4. 📝 **Criar utilitários** em `src/bp/utils/`: normalização, logging, config, .env.
5. 🧪 **Implementar testes** em `tests/`:
   - test_generators.py (geração de árvore/índice)
   - test_plano_contas.py (buscas, hierarquia)
   - test_models.py (validação Pydantic)

#### Saídas esperadas
- [ ] Módulo `src/bp/generators/` funcional e testado
- [ ] Classe `PlanodeContas` reutilizável
- [ ] Modelos Pydantic em `src/bp/models/`
- [ ] Utilitários em `src/bp/utils/`
- [ ] Testes em `tests/` (pytest)

---

### ✅ **FASE 3: Parsers de Balanços (Semana 3–4)** — PARCIALMENTE CONCLUÍDA ✅

**Objetivo:** Desenvolver parsers para cada formato de entrada (Excel, PDF, CSV, TXT).

#### FASE 3.0: Parsers Básicos ✅ CONCLUÍDA
1. ✅ **Criar BaseParser** em `src/bp/parsers/base_parser.py` (interface abstrata).
2. ✅ **Implementar parsers específicos**:
   - ExcelParser (`src/bp/parsers/excel_parser.py`) — lê .xlsx com detecção automática de abas
   - PDFParser (`src/bp/parsers/pdf_parser.py`) — extrai tabelas BÁSICAS (pdfplumber)
   - CSVParser (`src/bp/parsers/csv_parser.py`) — processa .csv com auto-detecção de delimitador
   - TXTParser (`src/bp/parsers/txt_parser.py`) — trata .txt estruturados (tab, espaços, pipe)
3. ✅ **Formato intermediário**: cada parser retorna `ParseResult` com contas padronizadas
4. ✅ **Criar exemplos** em `data/examples/`: balanco_exemplo.xlsx, .csv, .txt
5. ✅ **Testes** em `tests/test_parsers.py`: 15 testes para validar todos os parsers
6. ✅ **Demonstração** em `auxil/demo_parsers.py`: script mostrando uso de cada parser

#### Saídas Fase 3.0
- [x] Interface BaseParser em place com métodos validate(), parse(), _normalize_saldo()
- [x] 4 parsers implementados e testados (ExcelParser, CSVParser, PDFParser, TXTParser)
- [x] Exemplos em data/examples/ (3 arquivos criados automaticamente)
- [x] README.md em src/bp/parsers/ com documentação completa
- [x] 15 testes passando (28 testes totais no projeto)

#### FASE 3.2: PDFParser Avançado - OCR e PDFs Escaneados 🔄 PRÓXIMA
**Objetivo:** Suportar PDFs escaneados e imagens com OCR robusto.

**Ver detalhes completos em:** [`PLANO_PDF_AVANCADO.md`](PLANO_PDF_AVANCADO.md)

**Tarefas:**
1. ⏳ **Detector de tipo de PDF**
   - `PDFTypeDetector` - identifica nativo vs escaneado
   - `has_extractable_text()` - verifica texto selecionável
   - `estimate_ocr_quality()` - avalia necessidade de OCR

2. ⏳ **Pipeline de OCR**
   - `convert_pdf_to_images()` - PDF → imagens (pdf2image)
   - `ImagePreprocessor` - melhora qualidade (binarização, denoising, deskew)
   - `OCREngine` - extrai texto (pytesseract/easyocr)
   - Suporte para português brasileiro

3. ⏳ **Extração Híbrida**
   - Tenta extração nativa primeiro
   - Fallback para OCR se necessário
   - Sistema de confiança

**Saídas esperadas:**
- [ ] `src/bp/parsers/pdf_utils/detector.py` - PDFTypeDetector
- [ ] `src/bp/parsers/pdf_utils/ocr_engine.py` - OCREngine
- [ ] `src/bp/parsers/pdf_utils/preprocessor.py` - ImagePreprocessor
- [ ] Testes em `tests/test_pdf_ocr.py`
- [ ] Dependências: pytesseract, easyocr, pdf2image, opencv-python

#### FASE 3.3: Detecção Inteligente de Demonstrações 🔄
**Objetivo:** Identificar e extrair BP e DRE de DFs completas com ruído.

**Tarefas:**
1. ⏳ **Identificação de BP e DRE**
   - `StatementDetector` - detecta tipo de demonstração
   - Busca por keywords ("BALANÇO", "DRE", "ATIVO", "RECEITA")
   - Classifica páginas (BP, DRE, Notas)

2. ⏳ **Remoção de Ruído**
   - Remove assinaturas digitais
   - Filtra cabeçalhos/rodapés repetitivos
   - Separa notas explicativas
   - Remove elementos gráficos

3. ⏳ **Separação de Colunas**
   - Detecta layout de colunas
   - Extrai dados comparativos (Atual vs Anterior)
   - Identifica Consolidado vs Individual

**Saídas esperadas:**
- [ ] `src/bp/parsers/pdf_utils/statement_detector.py`
- [ ] `src/bp/parsers/pdf_utils/patterns.py` - keywords e padrões
- [ ] `src/bp/parsers/pdf_utils/noise_remover.py`
- [ ] Testes em `tests/test_pdf_detection.py`

#### FASE 3.4: Extração Avançada de Tabelas 🔄
**Objetivo:** Extrair tabelas complexas, multi-página e sem bordas.

**Tarefas:**
1. ⏳ **Múltiplos métodos de extração**
   - Camelot (lattice + stream)
   - Tabula
   - pdfplumber
   - Escolha automática do melhor método

2. ⏳ **Reconstrução de tabelas**
   - Une linhas quebradas entre páginas
   - Alinha colunas desalinhadas
   - Trata células mescladas

3. ⏳ **Validação**
   - Valida estrutura de tabelas
   - Detecta hierarquia de contas
   - Verifica totais e subtotais

**Saídas esperadas:**
- [ ] `src/bp/parsers/pdf_utils/table_extractor.py`
- [ ] `src/bp/parsers/pdf_utils/table_validator.py`
- [ ] Testes em `tests/test_pdf_tables.py`
- [ ] Dependências: camelot-py, tabula-py, PyMuPDF

#### FASE 3.5: Parser Completo de Demonstrações Financeiras 🔄
**Objetivo:** Orquestrar todo o pipeline para processar DFs completas.

**Tarefas:**
1. ⏳ **FinancialStatementParser**
   - Orquestra detecção, OCR, extração e validação
   - Processa múltiplas demonstrações no mesmo PDF
   - Extrai metadados (empresa, período, moeda)

2. ⏳ **Testes com PDFs reais**
   - `auxil/BP_PDF_ex/ABT - BP 03.2024.pdf`
   - `auxil/BP_PDF_ex/BALANÇO-DRE 2024 - ADA.pdf`
   - `auxil/BP_PDF_ex/Voll S.A_60_DF 2023.pdf`
   - `auxil/BP_PDF_ex/DF_completa/2023 Q4 - Agger Report.pdf`

3. ⏳ **Otimização e Performance**
   - Cache de resultados
   - Processamento paralelo
   - Métricas de qualidade

**Saídas esperadas:**
- [ ] `src/bp/parsers/financial_statement_parser.py`
- [ ] Testes em `tests/test_pdf_real_cases.py`
- [ ] Documentação em `src/bp/parsers/PDF_PARSER.md`
- [ ] Performance: <10s PDFs nativos, <30s PDFs escaneados

**Dependências Totais para PDF Avançado:**
```toml
pytesseract>=0.3.10      # OCR
easyocr>=1.7.0           # OCR moderno
pdf2image>=1.16.3        # PDF → Imagem
opencv-python>=4.8.0     # Processamento de imagem
PyMuPDF>=1.23.0          # PDF rápido
camelot-py[cv]>=0.11.0   # Tabelas avançadas
tabula-py>=2.9.0         # Extração de tabelas
pdfminer.six>=20221105   # Análise de layout
```

**Métricas de Sucesso:**
- Precisão >95% para PDFs nativos
- Precisão >85% para PDFs escaneados de alta qualidade
- Precisão >70% para PDFs escaneados de baixa qualidade
- Detectar BP/DRE em >90% dos casos
- [ ] Testes em tests/test_parsers.py

---

### 🤖 **FASE 4: Matching e IA (Semana 4–5)**

**Objetivo:** Implementar matching fuzzy + fallback para IA; cache de decisões.

#### Tarefas
1. 🤖 **Implementar ContaMatcher** em `src/bp/matchers/conta_matcher.py`:
   - Thresholds: auto_accept_threshold (0.85), requery_threshold (0.60)
   - Método `match()`: fuzzy → heurísticas → IA
   - Retorna: `{"source": "fuzzy|ai|cache", "decision": {...}, "candidates": [...]}`
2. 💾 **Criar cache** em `src/bp/matchers/match_cache.py`:
   - Armazena decisões em `data/match_cache.json`
   - Evita re-processamento
3. 🤖 **Integrar IA** (stub inicialmente):
   - Função `_classify_with_ai()` em `ContaMatcher`
   - Placeholder para LLM local ou API (OpenAI/Claude)
   - Prompt engineering com contexto de contas
4. 🧪 **Testes** em `tests/test_matchers.py`: fuzzy, heurísticas, IA.

#### Saídas esperadas
- [ ] Classe ContaMatcher funcional
- [ ] Cache implementado
- [ ] IA (stub) integrada
- [ ] Testes em tests/test_matchers.py

---

### 📊 **FASE 5: Aplicação e Output (Semana 5–6)**

**Objetivo:** CLI robusto, exportadores, validação e UI (opcional).

#### Tarefas
1. 🖥️ **Criar CLI** em `src/main.py` com argparse:
   ```bash
   python src/main.py convert --input balancete.xlsx --output saida.json [--force-ai]
   python src/main.py validate --file saida.json
   python src/main.py consolidate --file saida.json --by form
   ```
2. 📤 **Implementar exportadores** em `src/bp/exporters/`:
   - ExcelExporter — balanço em .xlsx padrão
   - JsonExporter — estrutura normalizada
   - ReportExporter — relatório HTML/PDF
3. ✅ **Validadores** em `src/bp/validators/balance_validator.py`:
   - Verificar débito = crédito
   - Validar hierarquia (soma filhos = pai)
   - Alertas sobre contas faltantes
4. 🧪 **Testes de integração** em `tests/test_integration.py`: ponta-a-ponta.
5. 🎨 **UI (opcional)**: GUI com PyQt6 se tempo permitir.

#### Saídas esperadas
- [ ] CLI funcional em src/main.py
- [ ] Exportadores em src/bp/exporters/
- [ ] Validadores em src/bp/validators/
- [ ] Testes de integração
- [ ] UI (PyQt6) ou CLI completa

---

## 📈 Fluxo de Processamento

```
Entrada (PDF/Excel/CSV/TXT)
         ↓
    [Parser específico]
         ↓
Formato intermediário: [{descricao, saldo, natureza, ...}]
         ↓
    [ContaMatcher + PlanodeContas]
         ↓
Decisão: {codigo, match_score, source (fuzzy/ai/cache), candidates}
         ↓
[Validador de Balanço]
         ↓
Saída normalizada (JSON/Excel/PDF)
         ↓
data/output/
```

---

## 🛠️ Dependências Principais

- **pandas** (2.3.3) — processamento de dados
- **pydantic** (2.12.5) — validação de dados
- **rapidfuzz** / **fuzzywuzzy** — matching fuzzy
- **pdfplumber** (0.11.8) — extração de PDFs
- **pyqt6** (6.10.0) — UI (opcional)
- **pytest** (9.0.1) — testes
- **python-dotenv** (1.2.1) — variáveis de ambiente

---

## 📁 Estrutura de Pastas

```
BP/
├── src/
│   ├── __init__.py
│   ├── main.py                    # CLI principal
│   └── bp/
│       ├── __init__.py
│       ├── models/                # Pydantic models
│       │   ├── __init__.py
│       │   ├── conta.py
│       │   └── balancete.py
│       ├── generators/            # Geradores de dados
│       │   ├── __init__.py
│       │   ├── plano_contas_generator.py
│       │   └── plano_contas.py
│       ├── parsers/               # Parseadores de entrada
│       │   ├── __init__.py
│       │   ├── base_parser.py
│       │   ├── excel_parser.py
│       │   ├── pdf_parser.py
│       │   ├── csv_parser.py
│       │   └── txt_parser.py
│       ├── matchers/              # Matching contábil
│       │   ├── __init__.py
│       │   ├── conta_matcher.py
│       │   └── match_cache.py
│       ├── exporters/             # Exportadores
│       │   ├── __init__.py
│       │   ├── excel_exporter.py
│       │   ├── json_exporter.py
│       │   └── report_exporter.py
│       ├── validators/            # Validadores
│       │   ├── __init__.py
│       │   └── balance_validator.py
│       └── utils/                 # Utilitários
│           ├── __init__.py
│           ├── logger.py
│           ├── config.py
│           └── normalizer.py
├── tests/
│   ├── __init__.py
│   ├── test_generators.py
│   ├── test_plano_contas.py
│   ├── test_models.py
│   ├── test_parsers.py
│   ├── test_matchers.py
│   ├── test_validators.py
│   ├── test_integration.py
│   └── fixtures/
├── auxil/                         # Scripts auxiliares descartáveis
│   ├── acctree_generate_json.py  # Gerador (pode virar src/bp/generators/)
│   └── csv_to_json.py            # Conversores auxiliares
├── data/
│   ├── plano_contas.json         # Base de contas (tree + index + flat + forms)
│   ├── match_cache.json          # Cache de decisões de matching
│   ├── plano_master.xlsx         # Fonte Excel (42 abas)
│   ├── templates/                # Templates de saída
│   ├── examples/                 # Exemplos de entrada
│   └── [formularios padrão].json # Templates por formulário (L100A, L100B, etc)
├── output/                       # Saída gerada (ignorar no git)
├── .gitignore
├── .env.example                  # Variáveis padrão
├── README.md
├── PLAN.md                       # Este arquivo
├── pyproject.toml
└── uv.lock
```

---

## 🎯 Decisões de Design

1. **JSON único vs. múltiplos arquivos**: Usar único `plano_contas.json` com 4 estruturas (melhor performance, simplicidade).
2. **Cache de matching**: Armazenar em `data/match_cache.json` para evitar re-processamento e permitir auditoria.
3. **IA opcional**: Começar com fuzzy matching puro; IA é fallback (stub → LLM local/API depois).
4. **LLM local vs. API**: Preferir local (Ollama + Llama2) se dados sensíveis; API (OpenAI/Claude) se velocidade for prioridade.
5. **Output priorizado**: Excel (padrão financeiro) + JSON (integração).
6. **Async**: Sync inicial; refatorar para async (asyncio) se bottleneck com +100 balanços/dia.

---

## 📝 Próximas Ações

**Semana 1 (Esta semana):**
- [ ] ✏️ Preencher PLAN.md (este arquivo) ← FEITO
- [ ] 📖 Criar README.md
- [ ] 🧪 Validar JSON com `acctree_generate_json.py`
- [ ] 🔧 Criar .env.example
- [ ] 📁 Estruturar src/bp/

**Semana 2–3:**
- [ ] 🏗️ Refatorar geradores
- [ ] 🧮 Modelos Pydantic
- [ ] 🧪 Testes unitários

**Semana 3–4:**
- [ ] 🔍 Parsers de balanços
- [ ] 📁 Exemplos em data/examples/

**Semana 4–5:**
- [ ] 🤖 ContaMatcher + IA
- [ ] 💾 Cache de decisões

**Semana 5–6:**
- [ ] 🖥️ CLI em src/main.py
- [ ] 📤 Exportadores
- [ ] ✅ Validadores

---

## 📞 Contato / Notas

- Projeto: **BP — Conversão Automática de Balanços**
- Linguagem: **Python 3.13+**
- Gerenciador: **uv**
- Status: **Em desenvolvimento (Fase 1)**
- Última atualização: **28 de Novembro de 2025**

---

## 🆕 Requisitos Adicionais e Estratégia de Evolução

Com base no seu pedido e nas necessidades reais de uso (muitos balanços, ambientes corporativos, múltiplos idiomas), adicionamos as seguintes atividades ao plano principal. Essas tarefas tornarão o `plano_contas` mais completo com o tempo, permitirão distribuição em Windows como `.exe` e suportarão arquivos em português, inglês e espanhol.

### 1) Enriquecimento contínuo do `plano_contas`
- Objetivo: permitir que o plano padrão (base) seja incrementalmente enriquecido por exemplos reais (balanços históricos e amostras), de forma controlada e auditável.
- Como: criar pipeline de ingestão que processa arquivos em `data/examples/`, extrai contas, sugere novas entradas e atualiza `data/plano_contas.json` via merge (com revisão humana e logs).

### 2) Exemplos de balanços (seed data)
- Objetivo: já entregar um conjunto inicial de exemplos (Excel, PDF, CSV) dentro de `data/examples/` para "alimentar" o gerador e treinar heurísticas.
- Como: adicionar amostras reais (ou anônimas) e scripts de importação automatizados; registrar origem (formulário/empresa).

### 3) Mecanismo de merge + auditoria
- Objetivo: quando uma nova conta for adicionada a partir de exemplos, manter um histórico e permitir reversão e aprovação humana.
- Como: criar `data/plano_versions/` e `data/plano_audit.log` com entradas que descrevem: operação (add/update), timestamp, origem (arquivo), usuário/aprovador.

### 4) Empacotamento em .exe
- Objetivo: permitir distribuição interna (Windows) sem exigir que cada usuário instale Python ou dependências.
- Como: usar `PyInstaller` ou `Nuitka` para gerar um executável. Criar script `build_exe.ps1` ou `build_exe.bat` com instruções e testes.

### 5) Suporte multilíngue (PT/EN/ES)
- Objetivo: permitir que o parser e o matcher trabalhem com descrições em Português, Inglês e Espanhol.
- Como: construir camadas de normalização multilíngue (stopwords, mapeamentos, tradução mínima de tokens contábeis), detectar idioma automaticamente (langdetect) e aplicar dicionários apropriados.

### 6) Documentação e testes de uso corporativo
- Objetivo: instruções de ingestão em lote, auditoria, políticas de aprovação e empacotamento para TI.
- Como: atualizar `README.md` e criar `docs/` com guias passo-a-passo.

---

## 🔁 Atualização do Roadmap (curto prazo)

Adicionamos as tarefas listadas acima ao backlog principal e priorizaremos como segue:

1. Adicionar amostras em `data/examples/` e script de ingestão (low-effort) — priorizar agora.
2. Implementar ingestão incremental com merge e log (próxima sprint).
3. Criar processo de revisão humana e interface simples para aprovar/recusar inclusões.
4. Entregar empacotamento `.exe` (script + documentação) para ambiente Windows.
5. Implementar normalizadores multilíngues e testes com exemplos em EN/ES.

---

## Próximas ações propostas

Se está de acordo, eu posso executar uma das opções iniciais abaixo (escolha uma):

- (A) Criar a pasta `data/examples/` e adicionar um pequeno `README` com o formato esperado para exemplos (Excel/PDF/CSV).
- (B) Implementar o script inicial `src/bp/generators/ingest_examples.py` que processa `data/examples/` e gera um relatório de novas contas encontradas (sem alterar o JSON automaticamente — apenas relatório para revisão).
- (C) Esboçar um `build_exe` com PyInstaller e adicionar instruções em `README.md`.

Qual das opções prefere que eu inicie agora? (A) Criar `data/examples/` e README; (B) Implementar script de ingestão inicial; (C) Esboçar o empacotamento `.exe`.
