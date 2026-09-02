# 🧾 Parsers — os leitores de balancete

> **Reuso natural:** qualquer automação que precise ler documento financeiro de cliente que vem em formato variado. Você não precisa de nada do resto do MAPA para usar só esta camada.

Todo parser recebe um caminho de arquivo e devolve **uma lista de dicionários uniforme**, independente do formato de origem:

```python
[
    {"codigo": "1.1.01", "descricao": "CAIXA", "saldo": 12345.67},
    {"codigo": "1.1.02", "descricao": "BANCOS", "saldo": 98765.43},
    ...
]
```

É esse contrato que faz o resto do sistema não se importar se o arquivo veio como `.xlsx`, `.pdf` ou `.txt` de largura fixa. E é ele que torna esta camada útil fora do MAPA.

---

## O caminho comum: `ParseyCaller`

O jeito fácil de usar é o **dispatcher**: você entrega o caminho, ele descobre o parser certo, chama, e devolve o resultado.

```python
from src.bp.parsers.dispatcher import ParseyCaller

contas = ParseyCaller("balancete_qualquer_formato.xlsx").parse()
for c in contas:
    print(c["codigo"], c["descricao"], c["saldo"])
```

O dispatcher olha a extensão e o conteúdo, escolhe entre os parsers concretos e ainda faz normalização numérica (vírgula-BR, negativos entre parênteses, milhares com ponto).

---

## Os parsers concretos

Cada um lida com um formato específico. Todos herdam de `BaseParser` e implementam `.parse() -> ParseResult`.

| Formato | Classe | Quando usa direto |
|---|---|---|
| `.xlsx` moderno | `ExcelParser` | quando você já sabe que é xlsx e quer controle da aba |
| `.xls` legado | `XlsParser` | Excel 97-2003; usa COM no Windows quando disponível |
| `.csv` | `CSVParser` | separador `;` ou `,`, com/sem preâmbulo |
| `.txt` (largura fixa) | `TXTParser` | balancete "listagem" — colunas por coluna de caractere |
| `.pdf` nativo | `PDFBalanceParser` | PDF com texto (não escaneado). Duas colunas ou coluna única. |

Uso direto (quando você não quer o dispatcher):

```python
from src.bp.parsers import ExcelParser

r = ExcelParser("balancete.xlsx", aba="Balancete").parse()
print(r.contas)      # lista de dicts
print(r.metadata)    # {"origem": "...", "linhas_lidas": N, ...}
```

---

## O contrato: `BaseParser` + `ParseResult`

```python
class BaseParser(ABC):
    def __init__(self, file_path: Path): ...

    @abstractmethod
    def parse(self) -> ParseResult:
        """Devolve ParseResult(contas=[...], metadata={...})"""
```

**Cada conta** no `ParseResult.contas` tem estas chaves:

| Chave | Tipo | Sempre presente? |
|---|---|---|
| `codigo` | `str` — hierárquico (`"1.1.01"`) ou flat (`"CAIXA"` quando o arquivo não traz código) | sim |
| `descricao` | `str` — descrição da conta, como o cliente escreveu | sim |
| `saldo` | `float` ou `None` — valor numérico normalizado; `None` quando o parser não conseguiu ler | sim |
| `natureza`, `tipo`, `nivel` | opcionais — quando o formato de origem traz | não |

`saldo=None` é **diferente** de saldo zero. É o sinal para camadas de cima ("o parser viu a linha, mas não decifrou o número") — o exporter e a janela usam isso para avisar em vez de silenciar.

---

## Estenda para um formato novo

Escrever um parser novo (`OFXParser`, `SAPExtratoParser`, o que for) é um exercício pequeno — e o dispatcher passa a aceitar o formato sozinho depois que ele é registrado.

```python
# src/bp/parsers/meu_parser.py
from .base_parser import BaseParser, ParseResult

class MeuParser(BaseParser):
    def parse(self) -> ParseResult:
        contas = []
        for linha in _abrir(self.file_path):   # sua leitura aqui
            contas.append({
                "codigo": linha.codigo,
                "descricao": linha.descricao.strip(),
                "saldo": _para_float(linha.valor),  # aceite None se não deu
            })
        return ParseResult(contas, metadata={"origem": self.file_path.name})
```

Depois é só ligar no dispatcher (`dispatcher.py` → `read()`/`parse()`) escolhendo pela extensão.

---

## Como reaproveitar fora do MAPA

Esta camada **não depende do resto do projeto**. Para levar para outra automação:

1. Copie `src/bp/parsers/` inteiro (mais `src/bp/utils/numero.py`, que os parsers usam para normalizar valores).
2. Instale as libs: `pandas`, `openpyxl`, `xlrd`, `pdfplumber`.
3. Importe e use — a API de cima permanece a mesma.

Alguns casos onde essa camada vale sozinha:

- **Accounting Advisory** — ler razão auxiliar em qualquer formato que o cliente mandar.
- **Capital Markets** — extrair tabelas de laudos e DFPs de PDF nativo.
- **Due Diligence** — normalizar planilhas de fluxo de caixa que vêm em mil layouts.
- **Any-shape ingestion** — quando o "de-para" para um formato interno é o trabalho.

---

## Arquivos-chave

| Arquivo | Papel |
|---|---|
| `base_parser.py` | Contrato — `BaseParser`, `ParseResult` |
| `dispatcher.py` | `ParseyCaller` — escolhe o parser certo por extensão/conteúdo |
| `excel_parser.py`, `xls_parser.py` | Excel moderno e legado |
| `csv_parser.py`, `txt_parser.py` | Delimitados e largura fixa |
| `pdf_balance_parser.py`, `pdf_utils/` | PDF nativo (extração por texto) + utilitários OCR (opcional) |
| `financial_statement_parser.py` | DFs completas (BP + DRE) em PDF/xlsx |
| `registro.py` | Modelo intermediário compartilhado |

Testes: [`tests/test_parsers.py`](../../../tests/test_parsers.py), [`tests/test_dispatcher_roteamento.py`](../../../tests/test_dispatcher_roteamento.py), [`tests/test_pdf_balance.py`](../../../tests/test_pdf_balance.py).
