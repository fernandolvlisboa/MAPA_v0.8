from __future__ import annotations

import re

import pandas as pd

BALANCE_KEYWORDS = [
    "conta",
    "código",
    "codigo",
    "classificação",
    "classificacao",
    "descrição",
    "descricao",
    "saldo",
    # Vocabulário que balancete real usa e a lista original não previa. Três
    # balancetes de clientes com estrutura impecável — "Conta Contábil |
    # Cod. R. | Nome da Conta | S. Anterior | Débito | Crédito | S. Atual" —
    # rendiam ZERO contas porque casavam só "conta": "Cod. R." não é "codigo"
    # e "S. Atual" não é "saldo". Ver REVISAO_QUALIDADE.md §17.
    "débito",
    "debito",
    "crédito",
    "credito",
    "cod.",
    "cod ",
    "cta",
    "histórico",
    "historico",
    "s. anterior",
    "s. atual",
    "anterior",
    "atual",
    "movimento",
    "nome da conta",
]

#: Um código de conta hierárquico: "1", "1.1.1", "1.00.00.00.00000000".
_CODIGO_CONTABIL_RE = re.compile(r"^\s*\d{1,8}(\.\d{1,9}){1,8}\s*$")

#: Fração mínima de uma coluna que precisa parecer código para a tabela ser
#: reconhecida pelo conteúdo. Baixa de propósito: balancete tem cabeçalho,
#: subtotais e linhas em branco no meio.
_LIMIAR_CODIGO_NA_COLUNA = 0.30


def has_balance_keywords(columns: list[str]) -> bool:
    col_str = " ".join(str(c).lower() for c in columns)
    return sum(1 for kw in BALANCE_KEYWORDS if kw in col_str) >= 2


def parece_balancete(df: pd.DataFrame) -> bool:
    """
    A tabela **parece** um balancete, julgando pelo conteúdo?

    Existe porque ``has_balance_keywords`` julga pelo **nome** das colunas, e
    nome é dica, não prova — a mesma lição do §12, onde uma coluna chamada
    "Conta contábil" não era reconhecida como código.

    O critério aqui é estrutural e não depende de vocabulário: existe alguma
    coluna em que boa parte dos valores é **código contábil hierárquico**
    (``1.01.01.00.00000000``), e existe alguma coluna **numérica**? Nenhuma
    planilha que não seja plano de contas ou balancete satisfaz isso por acaso.

    Serve de rede sob o filtro por palavra-chave: se o nome não convence mas o
    conteúdo é inequívoco, a tabela passa.
    """
    if df is None or df.empty or len(df.columns) < 2:
        return False

    tem_codigo = False
    tem_numero = False
    for coluna in df.columns:
        serie = df[coluna].dropna()
        if serie.empty:
            continue
        if not tem_codigo:
            texto = serie.astype(str)
            casam = texto.str.match(_CODIGO_CONTABIL_RE).sum()
            if casam / len(serie) >= _LIMIAR_CODIGO_NA_COLUNA:
                tem_codigo = True
        if not tem_numero:
            numericos = pd.to_numeric(serie, errors="coerce").notna().sum()
            if numericos / len(serie) >= 0.5:
                tem_numero = True
        if tem_codigo and tem_numero:
            return True
    return False


def split_code_description(text: str) -> tuple[str, str]:
    s = str(text)
    m = re.match(r"^(\d+(?:\.\d+)*)\s{2,}(.*)$", s)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    parts = s.split(maxsplit=1)
    if len(parts) >= 2:
        return parts[0].strip(), parts[1].strip()
    return s.strip(), s.strip()


def filter_sep_rows(df: pd.DataFrame) -> pd.DataFrame:
    def _is_sep_line(row) -> bool:
        joined = " ".join(str(v).strip() for v in row).strip()
        return (not joined) or set(joined) <= set("_=")

    mask_sep = df.apply(_is_sep_line, axis=1)
    if mask_sep.any():
        df = df[~mask_sep]
    return df


def unmerge_cells_forward_fill(df: pd.DataFrame) -> pd.DataFrame:
    for col in df.columns:
        col_str = str(col).lower()
        if (
            any(kw in col_str for kw in ["cod", "class", "conta"])
            and "desc" not in col_str
        ):
            df[col] = df[col].ffill()
    return df


def detect_header_row_df(df_raw: pd.DataFrame, max_rows: int = 30) -> int | None:
    best_header_row = None
    max_matches = 0
    for row_idx in range(min(max_rows, len(df_raw))):
        row_values = df_raw.iloc[row_idx].astype(str).str.lower()
        matches = sum(
            1
            for kw in BALANCE_KEYWORDS
            if any(kw in val for val in row_values if val and val != "nan")
        )
        if matches >= 2 and matches > max_matches:
            best_header_row = row_idx
            max_matches = matches
    return best_header_row
