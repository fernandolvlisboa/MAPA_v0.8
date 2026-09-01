# Auditoria de Dependências — enxugando o executável

Responde ao requisito: **o app precisa rodar offline, sem grandes instalações,
na máquina de qualquer colaborador.** O pacote estava em ~825 MB.

## Resultado

| | Antes | Depois |
|--|------:|-------:|
| Ambiente completo | 825 MB | 554 MB |
| **Núcleo (o que o .exe embarca)** | 825 MB | **166 MB** |

**Redução de 80%** no que vai para a máquina do colaborador — verificado
instalando só o núcleo num venv limpo e rodando o pipeline inteiro
(XLSX + XLS + CSV + PDF nativo → matching → export .xlsx).

## Método

Auditei o que o código **realmente importa** (`grep` de imports em `src/bp/`)
contra o que estava declarado, e medi cada pacote no disco.

## 1. Removidas — declaradas mas nunca importadas

| Pacote | Peso | Situação |
|--------|-----:|----------|
| **PyQt6** | **256 MB** | Zero imports. Era a UI opcional que nunca saiu do papel. |
| tabula-py | 13 MB | Zero imports. Ainda exigiria **Java** instalado. |
| pypdf | 2 MB | Zero imports (pdfplumber já cobre). |
| python-levenshtein | 1 MB | Zero imports (rapidfuzz tem implementação própria em C++). |
| python-dotenv | <1 MB | Zero imports. |
| python-json-logger | <1 MB | Zero imports. |

**~272 MB eliminados** sem tocar em uma linha de lógica.

## 2. Movidas para extras opcionais

O código **já degrada** quando elas faltam (`try/except ImportError` →
`PDF_UTILS_AVAILABLE = False`), então isolá-las não quebrou nada.

### `[ocr]` — ~145 MB — só na estação de curadoria

```bash
uv sync --extra ocr     # ou: pip install bp[ocr]
```

| Pacote | Peso | Usado em |
|--------|-----:|----------|
| opencv-python | 79 MB | `pdf_utils/preprocessor.py` (binarização, deskew) |
| pymupdf | 60 MB | `pdf_utils/detector.py` (nativo vs escaneado) |
| pillow | 6 MB | `pdf_utils/ocr_engine.py`, preprocessor |
| pytesseract | <1 MB | wrapper do binário Tesseract |
| pdf2image | <1 MB | wrapper do poppler |

Requer também os **binários** Tesseract (idioma `por`) e poppler — outro
motivo para não ir no app do colaborador.

### `[curation]` — 9 MB — geração do plano master

`pydantic`, usado só em `plano_contas_generator.py` (Passo 1 do README, roda
uma vez). `generators/__init__.py` passou a importar o gerador de forma
**lazy** (PEP 562 `__getattr__`), para que `from bp.generators import
PlanodeContas` não puxe pydantic.

### `[windows-xls]` — conversão .xls via COM

`pywin32` era **importado sem estar declarado** (`win32com`, `pythoncom` em
`xls_parser.py`) — dependência fantasma, corrigida. Só Windows, já guardada
por `EXCEL_AVAILABLE`.

## 3. Núcleo — 166 MB

Só o indispensável para o runtime do colaborador:

| Pacote | Peso | Por quê |
|--------|-----:|---------|
| pandas | 53 MB | leitura tabular (XLSX/XLS/CSV/TXT) |
| numpy | 33 MB | dependência do pandas |
| rapidfuzz | 12 MB | matching fuzzy |
| pdfminer.six | 9 MB | (via pdfplumber) |
| openpyxl | 3 MB | ler/escrever .xlsx |
| xlrd | 1 MB | .xls legado |
| pdfplumber | 1 MB | PDF nativo |

`pytest` também saiu do runtime para `dev` (estava listado como dependência
de produção).

## 4. Verificação

Instalei **só o núcleo** num venv limpo e rodei o pipeline completo:

```
plano : 1226 contas
match : 2.01.01.03  (Fornecedores → sintético correto)
xlsx  : 126 contas
pdf   : 35 contas
csv   : 584 contas
export: core_export.xlsx  59.513 bytes
```

Também simulei a **ausência** das libs pesadas (bloqueando `cv2`, `fitz`,
`PIL`, `pdf2image`, `PyQt6` no `sys.meta_path`) com o ambiente completo: o
núcleo importa e funciona igual.

`165 testes passando` depois da reestruturação.

## 5. Como instalar

```bash
# Colaborador / runtime mínimo (o que vira .exe)
uv sync

# Estação de curadoria (você): OCR + geração do master
uv sync --extra ocr --extra curation

# Windows, para converter .xls legado via Excel
uv sync --extra windows-xls

# Desenvolvimento
uv sync --group dev
```

## 6. Próximo passo para o .exe

Com 166 MB de dependências, o PyInstaller deve produzir algo na faixa de
**80–120 MB** (ele não empacota o que não é importado). Para reduzir mais:

- `--exclude-module` para submódulos do pandas não usados (`pandas.plotting`,
  `pandas.io.sql`).
- Avaliar trocar pandas por leitura direta via `openpyxl` + `csv` no runtime —
  economizaria ~86 MB (pandas + numpy), mas exige reescrever os parsers
  tabulares. Só vale se o tamanho ainda incomodar.
