# Full Workflow — BP System

Este documento descreve o fluxo completo do sistema BP, do intake de arquivos até exportações e revisão. Foca no passo a passo, comandos práticos e na intercomunicação entre módulos Python.

> **📚 Histórico de Desenvolvimento:** Para entender a evolução do projeto (Fases 3-5, decisões arquiteturais, melhorias), consulte `HISTORICO_DESENVOLVIMENTO.md`

## Visão Geral
- Entrada: Arquivos de balancetes (CSV, XLS, XLSX, TXT, PDF)
- Parsing: Parsers especializados via dispatcher
- Treinamento: Aprendizado incremental de padrões de contas
- Matching: Mapeamento de descrições para plano de contas
- Exportação: Geração de relatórios e planilhas
- Revisão: Consolidação e revisão de pendências

## 1) Preparação do Ambiente
- Requisitos: Python 3.11+, `pandas`, etc. (via `pyproject.toml`)
- Comando de teste:
```powershell
pytest tests/ -v
```

Arquivos relevantes:
- `pyproject.toml` — dependências e config
- `README.md` — instruções gerais

## 2) Extração de Contas Master (Plano de Contas)
Objetivo: Carregar e manter o plano de contas master.

Arquivos:
- `data/plano_contas.json` — base do plano
- `src/bp/generators/plano_contas.py` — classe `PlanodeContas`

Intercomunicação:
- `PlanodeContas` é usado por `ContaMatcher` e pelo `trainer`.

Uso básico:
```python
from src.bp.generators.plano_contas import PlanodeContas
plano = PlanodeContas("data/plano_contas.json")
conta = plano.find_by_codigo("1.1.01")
```

## 3) Parsers (Ingestion)
Objetivo: Converter arquivos brutos em contas normalizadas.

Módulos principais atualizados:
- `src/bp/parsers/dispatcher.py` — `ParseyCaller` (interface pública única, detecção inteligente de colunas)
- `src/bp/parsers/xls_parser.py` — Parser avançado .xls/.xlsx (header inference, multi-strategy, compactação automática de células mescladas)
- `src/bp/parsers/csv_parser.py` — CSV v2.0 (streaming, BOM, header, schema, erros)


- `src/bp/parsers/txt_parser.py` — TXT baseado em padrões

- `src/bp/parsers/pdf_parser.py` — PDF (OCR/parsing estrutural)

- `src/bp/parsers/base_parser.py` — Contratos comuns
- `data/plano_contas.json` — Plano de contas master
- `data/patterns.json` — Padrões de mapeamento
- `pyproject.toml` — Dependências e configuração do ambiente


- `src/bp/parsers/dispatcher.py` — Dispatcher central (`ParseyCaller`) com detecção inteligente:
  - Detecta numeração sequencial em coluna "Código" (linhas vs códigos contábeis)
  - Busca códigos hierárquicos em colunas Unnamed (padrão X.X.X)
  - Prioriza "Classificação" como descrição quando código está em Unnamed
  - Auto-detecta coluna de saldo se não encontrada por nome
- `src/bp/parsers/csv_parser.py` — Parser CSV v2.0 (streaming, BOM, header inference)
- `src/bp/parsers/xls_parser.py` — Parser XLS/XLSX com:
  - Multi-strategy: LibreOffice → Excel COM → openpyxl
  - Header inference automático
  - **Compactação automática de células mescladas** (`_compact_merged_columns`)
    - Simula processo manual Excel: unmerge → delete blanks → shift left
    - Remove colunas Unnamed vazias criadas por merged cells
    - Reorganiza dados compactando para estrutura tabular limpa
- `src/bp/parsers/txt_parser.py` — Parser TXT baseado em padrões
- `src/bp/parsers/pdf_parser.py` — Parser PDF (OCR/parsing estrutural)
- `src/bp/parsers/base_parser.py` — Contratos comuns
- `src/bp/parsers/generic_parser.py` — DEPRECATED (mantido para compatibilidade)
- `src/bp/parsers/result.py` — Estrutura de resultado (`ParserResult`)

Obsoleto / Compatibilidade:
- `src/bp/training/trainer.py` — Orquestrador de treinamento (`AccountTrainer`)
- `src/bp/training/train.py` — Script de treino
- `src/bp/training/review_tool.py` — Ferramenta CLI de revisão
- `src/bp/training/processed_files.json` — Tracking de arquivos processados
- `src/bp/training/training_cache.json` — Cache de matching
- `src/bp/training/learned_patterns.json` — Padrões aprendidos
- `src/bp/training/account_variations.json` — Variações de contas
- `src/bp/training/training_stats.json` — Estatísticas de treino
- `src/bp/matchers/__init__.py` — Matching de contas
- `src/bp/matchers/match_cache.py` — Cache de matching
- `src/bp/utils/normalizer.py` — Normalização de descrições

- `src/bp/parsers/generic_parser.py` — DEPRECATED (mantido apenas para scripts antigos)
- `src/bp/exporters/xlsx_exporter.py` — Exportação para Excel
- `auxil/export_xlsx.py` — Script de exportação


- `auxil/train_all_bp_teste.py` — Treinamento com BP_teste
- `auxil/demo_complete_workflow.py` — Demonstração end-to-end
- `auxil/convert_xls_to_xlsx.py` — Conversão de arquivos
- `auxil/deep_inspect_xls.py` — Diagnóstico de XLS
- `auxil/test_csv_advanced_features.py` — Testes avançados de CSV
- `auxil/robust_parser_test.py` — Stress de parsers
- `auxil/debug_csv1544_v2.py` — Diagnóstico de CSV problemático
- `auxil/test_all_files.py` — Testes em todos os arquivos

Intercomunicação:
- `tests/test_trainer.py` — Testes do trainer
- `tests/test_xlsx_exporter.py` — Testes do exporter
- `tests/test_parsers.py` — Testes dos parsers
- `tests/test_matchers.py` — Testes de matching
- `tests/test_generators.py` — Testes de geradores
- `tests/test_financial_statement_parser.py` — Testes de parser financeiro
- `tests/test_pdf_ocr.py` — Testes de PDF/OCR
- `tests/test_table_extraction.py` — Testes de extração de tabelas
- `tests/test_table_pipeline.py` — Testes de pipeline de tabelas
- `tests/test_plano_contas.py` — Testes do plano de contas
- `tests/test_statement_detection.py` — Testes de detecção de demonstrações

- `ParseyCaller` analisa extensão e delega para parser especializado retornando `List[Dict]`
- `output/training_report.md` — Relatório de treino
- `output/phase34_report.md` — Relatório de fase
- `output/*.xlsx` — Planilhas exportadas

- Fluxos legados que esperam `ParseResult` convertem manualmente (`accounts = ParseyCaller(p).parse()`).
- `README.md` — Instruções gerais
- `src/bp/parsers/csv_PLAN.md` — Documentação do CSVParser
- `src/bp/parsers/xls_PLAN.md` — Documentação do XlsParser

Uso (estado da arte):
```python
from pathlib import Path
from src.bp.parsers.dispatcher import ParseyCaller

accounts = ParseyCaller(Path("auxil/BP_teste/Balancete Real Life.xls")).parse()
print(len(accounts), accounts[0])
```

## 4) Treinamento (Aprendizado de Padrões)
Objetivo: Aprender variações e consolidar mapeamentos.

Módulos:
- `src/bp/training/trainer.py` — `AccountTrainer`
- `src/bp/matchers/__init__.py` — `ContaMatcher`
- `src/bp/utils/normalizer.py` — normalização de descrições

Intercomunicação:
- `AccountTrainer` usa dispatcher/parsers para extrair contas
- `ContaMatcher` usa `PlanodeContas` para sugerir mapeamentos
- Resultados persistidos em `src/bp/training/*.json`

Execução completa com dados de exemplo:
```powershell
python auxil/train_all_bp_teste.py
```

Estrutura de treino:
- `src/bp/training/DFS_Exemple/` — arquivos de treino
- `src/bp/training/processed_files.json` — tracking
- `src/bp/training/training_cache.json` — cache matcher
- `src/bp/training/learned_patterns.json` — padrões aprendidos
- `src/bp/training/account_variations.json` — variações
- `src/bp/training/training_stats.json` — estatísticas

## 5) Matching & Revisão
Objetivo: Consolidar e revisar contas não mapeadas.

Módulos:
- `src/bp/matchers/` — regras de matching
- `src/bp/training/review_wizard.py` — ferramenta de revisão interativa (CLI)

Comando sugerido:
```powershell
python -m src.bp.training.review_wizard
```

Opções disponíveis:
- `--file ARQUIVO` — Revisar arquivo específico
- `--list` — Listar itens que precisam revisão sem executar
- `--limit N` — Limitar número de itens a revisar

## 6) Exportação
Objetivo: Gerar saídas em XLSX/Markdown.

Módulos:
- `src/bp/exporters/xlsx_exporter.py` — exportação para Excel
- `auxil/export_xlsx.py` — helper/driver

Exemplo:
```powershell
python auxil/export_xlsx.py
```

## 7) Relatórios e Documentação
- `output/training_report.md` — relatório de treino
- `output/phase34_report.md` — relatório de fase
- `src/bp/parsers/xls_PLAN.md` — docs do XlsParser
- `src/bp/parsers/csv_PLAN.md` — docs do CSVParser v2.0

## 8) Workflows Auxiliares (auxil/)
Scripts que orquestram tarefas específicas:
- `auxil/demo_complete_workflow.py` — demonstração end-to-end
- `auxil/train_all_bp_teste.py` — treinamento com dados de exemplo
- `auxil/convert_xls_to_xlsx.py` — conversões de formato
- `auxil/deep_inspect_xls.py` — diagnóstico de XLS
- `auxil/BP_PDF_ex/` — exemplos de PDFs para testes

## 9) Passo a Passo (Receita)
1. Copie seus balancetes para `src/bp/training/DFS_Exemple/`
2. Rode o treinamento:
```powershell
python auxil/train_all_bp_teste.py
```
3. Revise pendências (opcional):
```powershell
python -m src.bp.training.review_wizard
```
4. Exporte resultados:
```powershell
python auxil/export_xlsx.py
```
5. Verifique relatórios em `output/`

**Nota:** Dados de treinamento estão em `src/bp/training/DFS_Exemple/` (31 arquivos)

## 10) Comunicação entre Módulos (Mapa)
- `ParseyCaller` → chama `XlsParser`/`CSVParser`/`TXTParser`/`PDFParser`
- `AccountTrainer` → usa `ParseyCaller` para contas + `ContaMatcher` para mapeamento
- `ContaMatcher` → consulta `PlanodeContas`
- `xlsx_exporter` → consome `ParseResult.contas` para gerar planilhas
- `review_tool` → consome resultados do trainer para revisão

## Troubleshooting
- XLS/XLSX com cabeçalhos em linhas superiores: use `XlsParser` — ele infere o header automaticamente
- CSV com BOM/encodings: use `CSVParser v2.0`
- TXT irregular: ajuste padrões no `TXTParser`

## Comandos Rápidos
```powershell
# Rodar testes
python -m pytest tests/ -v

# Treinar com dados de exemplo
python auxil/train_all_bp_teste.py

# Exportar XLSX
python auxil/export_xlsx.py

# Revisar pendências
python -m src.bp.training.review_wizard

# Verificar dependências
python check_dependencies.py

# Instalar pacotes via uv (recomendado)
uv pip install <pacote>
```

Para mais informações sobre UV, consulte `SETUP_UV.md`
