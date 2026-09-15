from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from .common import (
    detect_header_row_df,
    filter_sep_rows,
    has_balance_keywords,
    parece_balancete,
    split_code_description,
    unmerge_cells_forward_fill,
)


class ExcelParser:
    def __init__(self, file_path: str | Path):
        self.file_path = Path(file_path)

    def read(self) -> pd.DataFrame | None:
        # Prefer engine per extension; try both for .xls to handle edge cases.
        engines = (
            ["openpyxl"]
            if self.file_path.suffix.lower() == ".xlsx"
            else ["xlrd", "openpyxl"]
        )

        for engine in engines:
            try:
                try:
                    xls = pd.ExcelFile(self.file_path, engine=engine)
                    sheet_names = xls.sheet_names
                except Exception:
                    sheet_names = [None]

                # Detect best header row using a raw sample read with larger window.
                try:
                    df_raw = pd.read_excel(
                        self.file_path, engine=engine, header=None, nrows=80
                    )
                    # Coerce all columns to string for better keyword detection
                    df_raw_str = df_raw.astype(str)
                    best_header = detect_header_row_df(df_raw_str)

                    # Secondary heuristic: find first non-empty row after a keyword-bearing row
                    if best_header is None:
                        keywords = [
                            "conta",
                            "código",
                            "codigo",
                            "class",
                            "desc",
                            "saldo",
                        ]
                        for idx in range(len(df_raw_str)):
                            row_text = " ".join(
                                df_raw_str.iloc[idx].astype(str)
                            ).lower()
                            if sum(1 for kw in keywords if kw in row_text) >= 2:
                                # Found keyword row, next non-empty row might be header
                                for next_idx in range(
                                    idx, min(idx + 5, len(df_raw_str))
                                ):
                                    if not df_raw_str.iloc[next_idx].isna().all():
                                        best_header = next_idx
                                        break
                                break
                except Exception:
                    best_header = None

                header_candidates = (
                    [best_header] if best_header is not None else []
                ) + list(range(0, 20))

                for sheet in sheet_names:
                    for hdr in header_candidates:
                        try:
                            df = pd.read_excel(
                                self.file_path,
                                engine=engine,
                                header=hdr,
                                sheet_name=sheet if sheet is not None else None,
                            )
                        except Exception as e:
                            msg = str(e).lower()
                            # Handle corrupted/legacy OLE2/BOF issues (e.g., VIVAE).
                            if "bof" in msg or "ole2" in msg or "expected bof" in msg:
                                return None
                            continue

                        if df is None or df.empty:
                            continue

                        # Try headerless read with manual column assignment if standard fails
                        if hdr is None or (
                            hdr == 0 and not has_balance_keywords(list(df.columns))
                        ):
                            try:
                                df_headerless = pd.read_excel(
                                    self.file_path,
                                    engine=engine,
                                    header=None,
                                    sheet_name=sheet if sheet is not None else None,
                                )
                                if (
                                    not df_headerless.empty
                                    and best_header is not None
                                    and best_header < len(df_headerless)
                                ):
                                    # Use detected header row as columns
                                    new_cols = (
                                        df_headerless.iloc[best_header]
                                        .astype(str)
                                        .str.strip()
                                    )
                                    df = df_headerless.iloc[
                                        best_header + 1 :
                                    ].reset_index(drop=True)
                                    df.columns = new_cols
                            except Exception:
                                pass

                        # Basic cleanup and normalization
                        # NO dropna here - compaction will handle empty columns
                        df = filter_sep_rows(df)

                        # COMPACTION: Remove blank cells and shift left (handles merged cells)
                        # MUST be done BEFORE unmerge to preserve column headers correctly
                        df = self._compact_merged_cells(df)

                        df = unmerge_cells_forward_fill(df)
                        df.columns = [str(c).strip() for c in df.columns]

                        # NOW remove completely empty columns AFTER compaction
                        df = df.dropna(axis=1, how="all")

                        # If columns look like a balance table, return directly.
                        if has_balance_keywords(list(df.columns)) or parece_balancete(df):
                            return df

                        # Reconstruct when "Conta" contains code + description combined
                        classificacao_nan_ratio = (
                            df["Classificação"].isna().mean()
                            if "Classificação" in df.columns
                            else 1.0
                        )
                        conta_looks_combined = False
                        if "Conta" in df.columns:
                            sample = df["Conta"].dropna().astype(str).head(20)
                            conta_looks_combined = any(
                                re.match(r"^\s*[A-Za-z]?\s*\d+(?:\.\d+)*\s{2,}.+", s)
                                for s in sample
                            )

                        if classificacao_nan_ratio > 0.7 and conta_looks_combined:
                            tmp = df[df["Conta"].notna()].copy()
                            tmp[["__codigo", "__descricao"]] = tmp["Conta"].apply(
                                lambda x: pd.Series(split_code_description(x))
                            )
                            saldo_col = None
                            for c in [
                                "Saldo",
                                "Saldo final",
                                "Saldo atual",
                                "Saldo Ant.",
                            ]:
                                if c in tmp.columns:
                                    saldo_col = c
                                    break

                            result = pd.DataFrame(
                                {
                                    "Conta": tmp["__codigo"],
                                    "Classificação": tmp["__descricao"],
                                }
                            )
                            if saldo_col:
                                result["Saldo"] = tmp[saldo_col]

                            if not result.empty and (
                                has_balance_keywords(list(result.columns))
                                or parece_balancete(result)
                            ):
                                return result
            except Exception as e:
                msg = str(e).lower()
                if (
                    "bof" in msg
                    or "ole2" in msg
                    or "expected bof" in msg
                    or "corrupt" in msg
                ):
                    # File is corrupted - log guidance and return None
                    import warnings

                    warnings.warn(
                        f"Excel file '{self.file_path.name}' is corrupted or has unsupported format. "
                        f"Try converting to .xlsx:\n"
                        f"  - Open in Excel and Save As .xlsx\n"
                        f"  - Use LibreOffice: soffice --headless --convert-to xlsx '{self.file_path}'\n"
                        f"Error: {str(e)[:200]}", stacklevel=2
                    )
                    return None
                # Try next engine/sheet/header candidate
                continue

        return None

    def _compact_merged_cells(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Compacta DataFrame removendo células vazias e deslocando para esquerda.

        Simula o processo manual Excel:
        1. Desmesclar células (já feito por unmerge_cells_forward_fill)
        2. Selecionar células em branco
        3. Deletar deslocando para esquerda

        Isso elimina colunas "Unnamed: X" vazias criadas por células mescladas,
        alinhando títulos e valores corretamente.

        IMPORTANTE: Compacta TODOS os dados (headers + rows) juntos para
        preservar o alinhamento correto entre headers e valores.

        Args:
            df: DataFrame com possíveis gaps de células mescladas

        Returns:
            DataFrame compactado com células e headers alinhados à esquerda
        """
        if df.empty:
            return df

        # Cria um DataFrame temporário incluindo headers como primeira linha
        temp_data = [list(df.columns), *df.values.tolist()]

        # Compacta cada linha (incluindo header row)
        compacted_data = []
        max_cols = 0

        for row in temp_data:
            # Remove valores NaN/vazios, mantendo apenas valores válidos
            non_null_values = []
            for val in row:
                val_str = str(val).strip()
                # Verifica se valor é não-nulo e não-vazio
                # Também ignora "Unnamed: X" que são colunas merged vazias
                if (
                    pd.notna(val)
                    and val_str not in ["", "nan", "None", "<NA>"]
                    and not val_str.startswith("Unnamed:")
                ):
                    non_null_values.append(val)

            compacted_data.append(non_null_values)
            max_cols = max(max_cols, len(non_null_values))

        # Preenche linhas curtas com NaN até max_cols
        for row in compacted_data:
            while len(row) < max_cols:
                row.append(pd.NA)

        # Separa headers (primeira linha) dos dados (restante)
        compacted_headers = compacted_data[0]
        compacted_rows = compacted_data[1:]

        # Reconstrói DataFrame
        df_compacted = pd.DataFrame(compacted_rows, columns=compacted_headers)

        # Remove colunas completamente vazias (se houver)
        df_compacted = df_compacted.dropna(axis=1, how="all")

        return df_compacted
