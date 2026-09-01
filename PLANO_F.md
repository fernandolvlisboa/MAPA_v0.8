# Plano F — Suporte a Balancetes em PDF

Responde ao pedido: **usar os balancetes/DFs em PDF** que estavam na pasta de
treino e não eram aproveitados.

## Problema

O `ParseyCaller` (dispatcher) só lia CSV/XLSX/XLS/TXT — **PDF não era tratado**
(`read()` devolvia `None`, extração = 0 contas). O trainer nem procurava
`*.pdf`. Os 10 PDFs da pasta (8 nativos + 2 escaneados) eram invisíveis.

## Solução

Novo parser `src/bp/parsers/pdf_balance_parser.py` (`PDFBalanceParser`),
plugado no dispatcher e na descoberta de arquivos do trainer.

Estratégia por **linha de texto com posição (x) das palavras** (pdfplumber),
robusta a dois layouts comuns de balancete:

- **Coluna única** — uma conta por linha (`Caixa .... 1.234,56`).
- **Lado-a-lado** — Ativo à esquerda e Passivo à direita na MESMA linha
  (`Caixa 0 Fornecedores 14.766`); separado pela coordenada x da página.

Detalhes que garantem descrições limpas (o que o matcher usa):
- **Descrição = texto até o primeiro VALOR real**; valores intermediários de
  colunas comparativas (2024 vs 2023) não grudam na descrição.
- **Referências de nota** (dígitos soltos após o texto) são removidas.
- **Parsing numérico** PT-BR e US (`1.234,56`, `1,234.56`, `(218.813,56)`).
- **Ruído filtrado**: assinaturas, CNPJ/CRC, rodapés, datas por extenso.

PDFs **escaneados** (sem texto) retornam vazio de forma segura — precisam de
OCR (Tesseract), não instalado neste ambiente.

## Extração medida (via dispatcher)

| PDF | Tipo | Contas |
|-----|------|-------:|
| ABT - BP 03.2024 | balanço nativo 2-col | 35 |
| BALANÇO-DRE 2024 - ADA | balanço+DRE nativo | 106 |
| Voll S.A DF 2023 | DF nativo | 36 |
| 3T25 DFS MGLU3 | DF 59 pg | 382 |
| DFP / DF 4T24 / DF 2021 / DF Internacional | DFs 100+ pg | ~500–600 cada |
| BP_Image / dre_image | **escaneado** | 0 (requer OCR) |

Antes: **0 contas** em todos.

## Impacto no treino

Re-treino cold sobre o corpus completo (23 planilhas/CSV + 8 PDFs nativos):

| | Sem PDFs (Plano E) | Com PDFs (Plano F) |
|--|------------------:|-------------------:|
| Arquivos processados | 21 | 31 |
| Contas sintéticas | 4.610 | 7.376 |
| Matched (absoluto) | 1.726 | **2.474** |
| Taxa | 37,4% | 33,5% |
| Variações aprendidas | 155 | **252** |
| Variações fora do referencial | 0 | **0** |

A **taxa** cai (os DFs de 100+ páginas trazem muitas linhas de notas
explicativas que não casam), mas o **aprendizado absoluto cresce** (+748
matches, +97 variações) e permanece **100% limpo** (0 códigos fora do
referencial). As salvaguardas seguram o ruído: filtro sintético, guarda
anti-lixo, restrição de classe (Plano C) e threshold — só matches ≥0.85 e na
classe certa entram no dicionário; o resto vai para revisão.

## Limites / próximos passos

- **OCR**: os 2 PDFs escaneados precisam de Tesseract (`por`) + poppler. O
  pipeline `pdf_utils/ocr_engine.py` existe; falta ligar como fallback quando o
  PDF não tem texto.
- **DFs consolidadas** (IFRS, 100+ pg) são material ruidoso para treino de
  balancete; os balancetes limpos (ABT, ADA, Voll) são os mais valiosos.

## Arquivos

- novo: `src/bp/parsers/pdf_balance_parser.py`
- novo: `tests/test_pdf_balance.py`
- alterado: `src/bp/parsers/dispatcher.py` — roteia `.pdf`
- alterado: `src/bp/training/trainer.py` — descobre `*.pdf`
