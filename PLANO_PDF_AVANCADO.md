# 📄 PLANO AVANÇADO: Parser de PDF para Demonstrações Financeiras

## 🎯 Objetivo

Criar um parser de PDF robusto capaz de extrair dados de Balanço Patrimonial (BP) e Demonstração de Resultados (DRE) de PDFs complexos, incluindo documentos escaneados, assinados, com ruído e demonstrações financeiras completas.

---

## 🚧 Desafios Identificados

### 1. **PDFs Nativos vs Escaneados**
- PDFs com texto selecionável (nativos)
- PDFs escaneados (apenas imagens)
- PDFs híbridos (texto + imagens)

### 2. **Ruído e Elementos Extras**
- Assinaturas digitais e carimbos
- Cabeçalhos e rodapés repetitivos
- Logotipos e elementos gráficos
- Notas explicativas extensas
- Dados de auditoria

### 3. **Estrutura Complexa**
- Múltiplas demonstrações no mesmo PDF
- Tabelas complexas com múltiplas colunas
- Valores comparativos (ano atual vs anterior)
- Consolidado vs Individual
- Diferentes layouts entre empresas

### 4. **Formatos Variados**
- PDF padrão CVM (mais estruturado)
- PDF corporativo (layouts personalizados)
- PDF escaneado de baixa qualidade
- PDF multilíngue

---

## 🛠️ Tecnologias e Bibliotecas

### Extração de Texto
- **pdfplumber** - PDFs nativos, extração de tabelas
- **PyMuPDF (fitz)** - Rápido, múltiplos formatos
- **tabula-py** - Extração avançada de tabelas

### OCR (Optical Character Recognition)
- **pytesseract** - OCR open source (Tesseract)
- **easyocr** - OCR moderno com deep learning
- **pdf2image** - Conversão PDF → Imagem para OCR

### Pré-processamento de Imagem
- **Pillow (PIL)** - Manipulação de imagens
- **OpenCV (cv2)** - Filtros, binarização, denoising
- **numpy** - Operações em arrays de imagens

### Detecção de Layout
- **pdfminer.six** - Análise de layout PDF
- **camelot-py** - Detecção de tabelas (lattice/stream)

---

## 📋 Arquitetura do PDFParser Avançado

```
PDFParser (versão avançada)
├── 1. Detecção de Tipo
│   ├── is_native_pdf() → True/False
│   ├── is_scanned_pdf() → True/False
│   └── detect_quality() → 'high'|'medium'|'low'
│
├── 2. Pré-processamento
│   ├── remove_signatures() → PDF limpo
│   ├── remove_headers_footers() → PDF sem cabeçalhos
│   ├── extract_relevant_pages() → Páginas com BP/DRE
│   └── improve_image_quality() → Para OCR
│
├── 3. Extração de Texto
│   ├── extract_native_text() → pdfplumber/PyMuPDF
│   ├── extract_ocr_text() → pytesseract/easyocr
│   └── hybrid_extraction() → Combina ambos
│
├── 4. Detecção de Demonstrações
│   ├── find_balance_sheet() → Páginas com BP
│   ├── find_income_statement() → Páginas com DRE
│   └── separate_statements() → Separa BP e DRE
│
├── 5. Extração de Tabelas
│   ├── detect_table_structure() → Layout da tabela
│   ├── extract_tables_lattice() → Tabelas com bordas
│   ├── extract_tables_stream() → Tabelas sem bordas
│   └── merge_split_tables() → Une tabelas quebradas
│
├── 6. Limpeza de Dados
│   ├── remove_noise() → Remove elementos extras
│   ├── filter_notes() → Remove notas explicativas
│   ├── identify_account_lines() → Detecta linhas de contas
│   └── normalize_values() → Padroniza números
│
└── 7. Parsing Final
    ├── map_columns() → Identifica colunas
    ├── extract_accounts() → Extrai contas
    └── validate_structure() → Valida BP/DRE
```

---

## 🔧 Implementação em Fases

### **FASE 3.1: PDFParser Básico (já implementado)** ✅
- Extração simples com pdfplumber
- Processamento de tabelas nativas
- Detecção básica de colunas

### **FASE 3.2: OCR e PDFs Escaneados** (NOVA)

#### Tarefas
1. **Detector de tipo de PDF**
   - `detect_pdf_type()` - Identifica se é nativo ou escaneado
   - `has_extractable_text()` - Verifica texto selecionável
   - `estimate_ocr_quality()` - Avalia necessidade de OCR

2. **Pipeline de OCR**
   - `convert_pdf_to_images()` - PDF → imagens (pdf2image)
   - `preprocess_image()` - Melhora qualidade para OCR
     - Binarização (threshold)
     - Remoção de ruído (denoising)
     - Ajuste de contraste
     - Rotação automática (deskew)
   - `ocr_image()` - Extrai texto com pytesseract/easyocr
   - `combine_ocr_results()` - Mescla resultados

3. **Extração Híbrida**
   - `hybrid_text_extraction()` - Tenta nativo primeiro, OCR depois
   - `confidence_score()` - Avalia qualidade da extração

#### Saídas esperadas
- [ ] Classe `PDFTypeDetector` em `src/bp/parsers/pdf_utils/detector.py`
- [ ] Classe `OCREngine` em `src/bp/parsers/pdf_utils/ocr_engine.py`
- [ ] Classe `ImagePreprocessor` em `src/bp/parsers/pdf_utils/preprocessor.py`
- [ ] Testes em `tests/test_pdf_ocr.py`

---

### **FASE 3.3: Detecção Inteligente de Demonstrações** (NOVA)

#### Tarefas
1. **Identificação de BP e DRE**
   - `find_keywords()` - Busca palavras-chave ("BALANÇO", "DRE", "ATIVO", "RECEITA")
   - `classify_page()` - Classifica página como BP, DRE ou Notas
   - `extract_statement_pages()` - Extrai apenas páginas relevantes

2. **Separação de Colunas**
   - `detect_column_layout()` - Identifica estrutura de colunas
   - `extract_comparative_data()` - Separa "Atual" vs "Anterior"
   - `identify_consolidated()` - Detecta "Consolidado" vs "Individual"

3. **Filtro de Ruído**
   - `remove_signatures_areas()` - Remove áreas de assinatura
   - `filter_header_footer()` - Remove cabeçalhos/rodapés
   - `clean_notes_section()` - Separa notas explicativas

#### Saídas esperadas
- [ ] Classe `StatementDetector` em `src/bp/parsers/pdf_utils/statement_detector.py`
- [ ] Padrões de keywords em `src/bp/parsers/pdf_utils/patterns.py`
- [ ] Testes em `tests/test_pdf_detection.py`

---

### **FASE 3.4: Extração Avançada de Tabelas** (NOVA)

#### Tarefas
1. **Múltiplos métodos de extração**
   - `extract_with_camelot()` - Método lattice (tabelas com bordas)
   - `extract_with_stream()` - Método stream (sem bordas)
   - `extract_with_pdfplumber()` - Método atual
   - `best_extraction_method()` - Escolhe melhor método

2. **Reconstrução de tabelas**
   - `merge_split_rows()` - Une linhas quebradas
   - `align_columns()` - Alinha colunas desalinhadas
   - `fix_merged_cells()` - Trata células mescladas

3. **Validação**
   - `validate_table_structure()` - Verifica estrutura
   - `detect_account_hierarchy()` - Identifica hierarquia de contas
   - `check_sum_totals()` - Valida totais

#### Saídas esperadas
- [ ] Classe `TableExtractor` em `src/bp/parsers/pdf_utils/table_extractor.py`
- [ ] Classe `TableValidator` em `src/bp/parsers/pdf_utils/table_validator.py`
- [ ] Testes em `tests/test_pdf_tables.py`

---

### **FASE 3.5: Parser Completo de DF** (NOVA)

#### Tarefas
1. **FinancialStatementParser**
   - Orquestra todo o pipeline
   - Processa DF completa
   - Extrai BP + DRE do mesmo PDF

2. **Mapeamento Inteligente**
   - `map_balance_sheet_structure()` - Estrutura do BP
   - `map_income_statement_structure()` - Estrutura da DRE
   - `extract_metadata()` - Empresa, período, moeda

3. **Exportação**
   - `export_to_standard_format()` - Formato padronizado
   - `generate_report()` - Relatório de extração

#### Saídas esperadas
- [ ] Classe `FinancialStatementParser` em `src/bp/parsers/financial_statement_parser.py`
- [ ] Testes com PDFs reais em `tests/test_pdf_real_cases.py`
- [ ] Documentação em `src/bp/parsers/PDF_PARSER.md`

---

## 📦 Dependências Adicionais

Adicionar ao `pyproject.toml`:

```toml
[project]
dependencies = [
    # ... dependências existentes ...
    
    # OCR e Processamento de Imagem
    "pytesseract>=0.3.10",      # OCR com Tesseract
    "easyocr>=1.7.0",           # OCR moderno
    "pdf2image>=1.16.3",        # PDF → Imagem
    "Pillow>=10.0.0",           # Manipulação de imagens
    "opencv-python>=4.8.0",     # Processamento de imagem
    
    # Extração PDF Avançada
    "PyMuPDF>=1.23.0",          # fitz - PDF rápido
    "camelot-py[cv]>=0.11.0",   # Detecção avançada de tabelas
    "tabula-py>=2.9.0",         # Extração de tabelas
    "pdfminer.six>=20221105",   # Análise de layout
    
    # Utilitários
    "numpy>=1.24.0",            # Arrays numéricos
]
```

**NOTA:** Tesseract OCR precisa ser instalado separadamente:
- Windows: `choco install tesseract`
- Linux: `sudo apt-get install tesseract-ocr tesseract-ocr-por`
- Mac: `brew install tesseract tesseract-lang`

---

## 🎯 Estrutura de Pastas

```
src/bp/parsers/
├── pdf_parser.py                    # Parser básico (atual)
├── financial_statement_parser.py    # Parser completo de DF
└── pdf_utils/                       # Utilitários PDF
    ├── __init__.py
    ├── detector.py                  # Detecta tipo de PDF
    ├── ocr_engine.py                # Engine OCR
    ├── preprocessor.py              # Pré-processamento de imagens
    ├── statement_detector.py        # Detecta BP/DRE
    ├── table_extractor.py           # Extração avançada de tabelas
    ├── table_validator.py           # Validação de tabelas
    ├── patterns.py                  # Padrões e keywords
    └── noise_remover.py             # Remoção de ruído

tests/
├── test_pdf_ocr.py                  # Testes OCR
├── test_pdf_detection.py            # Testes detecção
├── test_pdf_tables.py               # Testes tabelas
└── test_pdf_real_cases.py           # Testes com PDFs reais

auxil/BP_PDF_ex/                     # PDFs de exemplo
├── ABT - BP 03.2024.pdf
├── BALANÇO-DRE 2024 - ADA.pdf
├── Voll S.A_60_DF 2023.pdf
└── DF_completa/
    └── 2023 Q4 - Agger Report.pdf
```

---

## 🧪 Casos de Teste

### 1. PDFs Nativos Simples
- [x] Tabelas com bordas claras
- [x] Texto selecionável
- [x] Layout padrão

### 2. PDFs Nativos Complexos
- [ ] Múltiplas colunas (Atual, Anterior, Consolidado)
- [ ] Tabelas sem bordas
- [ ] Notas explicativas intercaladas

### 3. PDFs Escaneados
- [ ] Baixa resolução
- [ ] Texto rotacionado
- [ ] Ruído de digitalização

### 4. PDFs com Ruído
- [ ] Assinaturas digitais
- [ ] Carimbos e marcas d'água
- [ ] Elementos gráficos sobrepostos

### 5. DFs Completas
- [ ] BP + DRE + Notas no mesmo PDF
- [ ] Múltiplas páginas por demonstração
- [ ] Tabelas quebradas entre páginas

---

## 📊 Pipeline Completo de Processamento

```
1. ENTRADA
   └─> PDF de DF completa

2. ANÁLISE INICIAL
   ├─> Detecta tipo (nativo/escaneado)
   ├─> Avalia qualidade
   └─> Conta páginas

3. PRÉ-PROCESSAMENTO
   ├─> Remove assinaturas
   ├─> Limpa cabeçalhos/rodapés
   └─> Melhora imagem (se OCR)

4. DETECÇÃO DE DEMONSTRAÇÕES
   ├─> Identifica páginas de BP
   ├─> Identifica páginas de DRE
   └─> Separa notas explicativas

5. EXTRAÇÃO DE DADOS
   ├─> Extrai texto (nativo ou OCR)
   ├─> Detecta tabelas
   └─> Extrai valores

6. LIMPEZA E VALIDAÇÃO
   ├─> Remove ruído
   ├─> Valida estrutura
   └─> Normaliza valores

7. PARSING FINAL
   ├─> Mapeia contas
   ├─> Cria hierarquia
   └─> Valida totais

8. SAÍDA
   └─> ParseResult padronizado
```

---

## 🎯 Métricas de Sucesso

### Precisão de Extração
- **Meta:** >95% para PDFs nativos
- **Meta:** >85% para PDFs escaneados de alta qualidade
- **Meta:** >70% para PDFs escaneados de baixa qualidade

### Cobertura
- **Meta:** Detectar BP e DRE em >90% dos casos
- **Meta:** Extrair hierarquia correta em >85% dos casos

### Performance
- **Meta:** <10s para PDF nativo (10 páginas)
- **Meta:** <30s para PDF escaneado com OCR (10 páginas)

---

## 📝 Próximos Passos Imediatos

### Semana 1 (FASE 3.2)
1. Instalar e configurar Tesseract
2. Implementar `PDFTypeDetector`
3. Implementar `OCREngine` básico
4. Criar `ImagePreprocessor`
5. Testes com PDFs escaneados

### Semana 2 (FASE 3.3)
1. Implementar `StatementDetector`
2. Criar biblioteca de keywords/patterns
3. Implementar filtros de ruído
4. Testes de detecção com DFs reais

### Semana 3 (FASE 3.4)
1. Integrar camelot-py
2. Implementar `TableExtractor`
3. Criar `TableValidator`
4. Testes com tabelas complexas

### Semana 4 (FASE 3.5)
1. Implementar `FinancialStatementParser`
2. Testes end-to-end com DFs completas
3. Documentação completa
4. Otimização de performance

---

## 🔍 Exemplos de Uso (Futuro)

```python
from src.bp.parsers import FinancialStatementParser

# Parser de DF completa
parser = FinancialStatementParser("DF_completa.pdf")

# Detecta tipo automaticamente
info = parser.analyze()
print(f"Tipo: {info['type']}")  # 'native' ou 'scanned'
print(f"Qualidade: {info['quality']}")  # 'high', 'medium', 'low'
print(f"Demonstrações encontradas: {info['statements']}")  # ['BP', 'DRE']

# Extrai BP
bp_result = parser.extract_balance_sheet()
print(f"BP: {len(bp_result.contas)} contas extraídas")

# Extrai DRE
dre_result = parser.extract_income_statement()
print(f"DRE: {len(dre_result.contas)} contas extraídas")

# Ou extrai tudo de uma vez
full_result = parser.parse_complete()
print(f"BP: {len(full_result.balance_sheet)} contas")
print(f"DRE: {len(full_result.income_statement)} contas")
print(f"Metadados: {full_result.metadata}")
```

---

## ⚠️ Desafios Técnicos

### 1. OCR em Português
- Configurar idioma PT-BR no Tesseract
- Tratar caracteres especiais (ç, ã, õ)
- Lidar com números formatados (1.234.567,89)

### 2. Layout Variável
- Cada empresa tem layout diferente
- Precisa ser robusto a variações
- Machine Learning pode ajudar no futuro

### 3. Performance
- OCR é lento
- Processar em paralelo quando possível
- Cache de resultados intermediários

### 4. Tabelas Quebradas
- Tabelas que continuam em outra página
- Cabeçalhos repetidos
- Totais intermediários

---

## 🚀 Futuro (Fase 4+)

### Machine Learning
- Modelo para detectar layout de tabelas
- Classificação automática de contas
- Extração de relacionamentos entre contas

### API de Processamento
- Endpoint para upload de PDF
- Processamento assíncrono
- Retorno em formato JSON

### Interface Gráfica
- Upload de PDF
- Visualização de extração
- Correção manual de erros
- Exportação de resultados

---

## 📋 Checklist de Implementação

### FASE 3.2: OCR e PDFs Escaneados
- [ ] Instalar Tesseract OCR
- [ ] Criar `PDFTypeDetector`
- [ ] Criar `OCREngine`
- [ ] Criar `ImagePreprocessor`
- [ ] Testes básicos de OCR
- [ ] Documentação

### FASE 3.3: Detecção de Demonstrações
- [ ] Criar `StatementDetector`
- [ ] Biblioteca de keywords
- [ ] Filtros de ruído
- [ ] Testes de detecção
- [ ] Documentação

### FASE 3.4: Extração Avançada
- [ ] Integrar camelot-py
- [ ] Criar `TableExtractor`
- [ ] Criar `TableValidator`
- [ ] Testes de tabelas complexas
- [ ] Documentação

### FASE 3.5: Parser Completo
- [ ] Criar `FinancialStatementParser`
- [ ] Pipeline completo
- [ ] Testes end-to-end
- [ ] Otimização
- [ ] Documentação final

---

**Estimativa Total:** 4-6 semanas para implementação completa
**Complexidade:** Alta
**Prioridade:** Crítica (PDF é o formato mais comum e desafiador)

---

## ⚙️ Configuração adicionada (Fase 3.4.x)

- `data/patterns.json > settings.trailing_numbers_order`
   - Controla a ordem de mapeamento dos números finais detectados em linhas quando o cabeçalho não permite mapear colunas com confiança.
   - Valores:
      - `"current_previous"` (padrão): primeiro número → `current`, segundo → `previous`.
      - `"previous_current"`: primeiro número → `previous`, segundo → `current`.
   - Exemplo:

```json
{
   "settings": {
      "trailing_numbers_order": "current_previous"
   }
}
```

Essa configuração é lida pelo `TableExtractor` automaticamente.
