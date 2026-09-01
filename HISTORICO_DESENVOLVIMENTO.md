# Histórico de Desenvolvimento — Projeto BP

Este documento consolida o histórico de desenvolvimento do sistema BP, desde a implementação dos parsers até o matching inteligente.

---

## 📅 Fase 3 — Parsers de Balanços (Concluída)

**Objetivo:** Criar parsers especializados para extrair contas de diferentes formatos de arquivo.

### Implementações

#### 1. BaseParser — Interface Abstrata
- **Arquivo:** `src/bp/parsers/base_parser.py`
- **Funcionalidades:**
  - Classe abstrata com métodos `parse()` e `validate()`
  - Utilitários: `_normalize_saldo()`, `_extract_metadata()`
  - Classe `ParseResult` para padronizar retorno

#### 2. ExcelParser — Parser Excel/XLS
- **Arquivo:** `src/bp/parsers/excel_parser.py`
- **Funcionalidades:**
  - Leitura de arquivos .xlsx e .xls
  - Detecção automática de abas
  - Mapeamento inteligente de colunas
  - Método `get_available_sheets()`

#### 3. CSVParser — Parser CSV
- **Arquivo:** `src/bp/parsers/csv_parser.py`
- **Funcionalidades:**
  - Auto-detecção de delimitador (`,`, `;`, `|`, tab)
  - Suporte para múltiplas codificações
  - Método `_detect_delimiter()` com csv.Sniffer

#### 4. PDFParser — Parser PDF
- **Arquivo:** `src/bp/parsers/pdf_parser.py`
- **Funcionalidades:**
  - Extração de tabelas com pdfplumber
  - Processamento de múltiplas páginas
  - Seleção de páginas específicas
  - Método `get_page_count()`

#### 5. TXTParser — Parser Texto
- **Arquivo:** `src/bp/parsers/txt_parser.py`
- **Funcionalidades:**
  - Auto-detecção de separador (tab, espaços, pipe, etc)
  - Suporte para colunas de largura fixa
  - Detecção automática de cabeçalhos
  - Método `_detect_separator()`

---

## 📅 Fase 3.2 — OCR e PDFs Escaneados (Concluída)

**Objetivo:** Adicionar suporte completo para OCR e processamento de PDFs escaneados.

### Implementações

#### 1. PDFTypeDetector
- **Arquivo:** `src/bp/parsers/pdf_utils/detector.py`
- **Funcionalidades:**
  - Detecta tipo de PDF (nativo, escaneado, híbrido)
  - Calcula razão de texto extraível
  - Avalia qualidade do PDF
  - Determina necessidade de OCR automaticamente

#### 2. ImagePreprocessor
- **Arquivo:** `src/bp/parsers/pdf_utils/preprocessor.py`
- **Funcionalidades:**
  - Binarização (Otsu, Adaptive, Simple)
  - Remoção de ruído (Gaussian, Median, Bilateral)
  - Ajuste de contraste (CLAHE, Normalize, Gamma)
  - Correção de rotação (deskew automático)
  - Redimensionamento para DPI ideal (300 DPI)

#### 3. OCREngine
- **Arquivo:** `src/bp/parsers/pdf_utils/ocr_engine.py`
- **Funcionalidades:**
  - Integração com Tesseract OCR
  - Suporte multi-idioma (por, eng)
  - Extração com scores de confiança
  - Configurações personalizáveis

#### 4. StatementDetector
- **Arquivo:** `src/bp/parsers/pdf_utils/statement_detector.py`
- **Funcionalidades:**
  - Detecção de tipo de demonstrativo (BP, DRE, Notas)
  - Classificação por página
  - Separação de demonstrativos em PDFs multi-statement
  - Extração de metadados (período, empresa)

---

## 📅 Fase 3.3 — Parser Dispatcher e Estratégia Description-First (Concluída)

**Objetivo:** Criar dispatcher central e implementar estratégia description-first parsing.

### Implementações

#### 1. ParseyCaller (Dispatcher)
- **Arquivo:** `src/bp/parsers/dispatcher.py`
- **Funcionalidades:**
  - Interface pública única para todos os parsers
  - Detecção automática de tipo de arquivo
  - Estratégia description-first (universal > code > saldo)
  - Helpers: `_find_description_column()`, `_find_saldo_column()`, `_find_codigo_column()`
  - Validação de códigos hierárquicos vs numeração sequencial

#### 2. ExcelParser — Compactação de Células Mescladas
- **Arquivo:** `src/bp/parsers/excel_parser.py`
- **Funcionalidades:**
  - Método `_compact_merged_cells()` unificado
  - Processa headers E dados juntos
  - Remove colunas "Unnamed:" automaticamente
  - Simula processo manual: unmerge → delete blanks → shift left

### Resultados
- ✅ 7/7 arquivos do corpus passando (2,334 contas extraídas)
- ✅ Suporte para estruturas hierárquicas e flat
- ✅ Código genérico funciona com qualquer formato

---

## 📅 Fase 4 — Matching Inteligente (Concluída)

**Objetivo:** Implementar sistema de matching inteligente para mapear contas ao plano padrão.

### Arquitetura

#### Pipeline Multi-estágio
```
Query → Normalização → Cache? ──yes──> Retorna
                          │
                          no
                          ↓
                    Fuzzy Match (RapidFuzz)
                          │
                    Score ≥ 0.85? ──yes──> Auto-aceita + Cache
                          │
                          no
                          ↓
                    Heurísticas Contábeis
                          │
                    Score ≥ 0.85? ──yes──> Auto-aceita + Cache
                          │
                          no
                          ↓
                    Precisa Revisão Manual
```

### Implementações

#### 1. ContaMatcher
- **Arquivo:** `src/bp/matchers/conta_matcher.py`
- **Funcionalidades:**
  - Fuzzy matching com RapidFuzz
  - Heurísticas contábeis (keywords, tipo, natureza)
  - Auto-accept threshold: 0.85
  - Requery threshold: 0.60
  - Retorna `MatchResult` com decision/needs_review

#### 2. MatchCache
- **Arquivo:** `src/bp/matchers/match_cache.py`
- **Funcionalidades:**
  - Cache JSON persistente de decisões
  - Métodos: `get()`, `save()`, `update()`, `delete()`, `stats()`
  - Exportação para JSON e Markdown

#### 3. PlanodeContas
- **Arquivo:** `src/bp/generators/plano_contas.py`
- **Funcionalidades:**
  - Carrega plano de contas master (7,741 contas padrão)
  - Busca por código ou descrição
  - Suporte fuzzy matching
  - Métodos de hierarquia e estatísticas

### Resultados
- ✅ 58.9% auto-match rate (conservador, seguro)
- ✅ 0% data loss
- ✅ Real Life file: 83.3% matched (mostra sistema funciona bem com dados limpos)

---

## 📅 Fase 5 — Treinamento e Review Wizard (Em Produção)

**Objetivo:** Sistema de aprendizado incremental e revisão interativa.

### Implementações

#### 1. AccountTrainer
- **Arquivo:** `src/bp/training/trainer.py`
- **Funcionalidades:**
  - Processa balancetes e aprende padrões
  - Filtra contas analíticas automaticamente
  - Atualiza `account_variations.json`
  - Tracking de arquivos processados
  - Geração de relatórios

#### 2. Review Wizard
- **Arquivo:** `src/bp/training/review_wizard.py`
- **Funcionalidades:**
  - Interface interativa para revisão manual
  - Comandos: search, hierarchy, code, ignore, skip, quit
  - Salva decisões em cache + variations
  - Preview com `--list`, limite com `--limit N`

### Dados de Treinamento
- **Localização:** `src/bp/training/DFS_Exemple/`
- **Arquivos:** 31 balancetes (CSV, XLS, XLSX, PDF, TXT)
- **Aprendizado Atual:**
  - 194 códigos únicos
  - 378 variações aprendidas
  - 756 ocorrências processadas

---

## 📅 Limpeza e Modernização (Dez 2025)

**Objetivo:** Remover código obsoleto e modernizar infraestrutura.

### Remoções
- ✅ `generic_parser.py` (substituído por `ParseyCaller`)
- ✅ Backups obsoletos: `generic_parser_backup.py`, `excel_parser_backup.py`
- ✅ 11 scripts debug da root
- ✅ 62 scripts ad-hoc de `auxil/`
- ✅ Diretório `auxil/BP_teste/` duplicado
- ✅ 7 arquivos CSV/TXT intermediários

### Migração UV
- ✅ Migrado de pip para uv (10-100x mais rápido)
- ✅ 20/20 dependências principais instaladas
- ✅ 1/1 dependência dev instalada
- ✅ Tempo de instalação: 8.5s (vs ~60s com pip)

### Validação PDF
- ✅ pdfplumber: OK (1,585 chars, 4 tables)
- ✅ pdfminer.six: OK (1,665 chars com layout)
- ✅ PyMuPDF/fitz: OK (1,777 chars, 2 images)
- 🟡 tabula-py: Instalado mas precisa Java (opcional)

### Testes
- ✅ **119 testes passando**
- ✅ 8 skipped (esperado: PDFs ausentes, Tesseract opcional)
- ✅ 5 warnings (apenas referências a arquivos removidos)

---

## 🎯 Estado Atual (Dez 2025)

### Sistemas Operacionais
- ✅ Parsing: 7/7 arquivos corpus, 2,334 contas
- ✅ Matching: 58.9% auto-match, 0% loss
- ✅ Training: 194 codes, 378 variations
- ✅ Dependencies: 100% instaladas via uv
- ✅ PDF: 3 parsers robustos disponíveis

### Próximos Passos
1. Executar review wizard para refinar matching
2. Processar corpus completo (2,334 contas)
3. Atualizar documentação com arquitetura atual
4. Opcional: Configurar tabula-py com Java

### Documentação Ativa
- `Full_Workflow.md` — Workflow completo atual
- `README.md` — Instruções gerais
- `SETUP_UV.md` — Guia do uv
- Este documento — Histórico de desenvolvimento
