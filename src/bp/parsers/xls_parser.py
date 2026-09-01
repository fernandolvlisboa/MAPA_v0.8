"""
XLS Parser with Multiple Strategies and Merged Cell Compaction

Features:
- Multi-strategy parsing (LibreOffice → Excel COM → openpyxl)
- Automatic header detection and inference
- **Automatic merged cell compaction** (simulates manual Excel cleanup)

Priority order:
1. LibreOffice headless conversion (safest, fastest, no COM issues)
2. Excel COM automation (fallback for files LibreOffice can't handle)
3. openpyxl direct read (for files that are actually xlsx with .xls extension)

Merged Cell Handling:
- Detects and processes merged cells that create blank/Unnamed columns
- Automatically compacts DataFrame by removing blanks and shifting left
- Simulates manual Excel process: unmerge → select blanks → delete → shift left
- Results in clean tabular structure ready for column detection

This ensures maximum reliability and handles complex real-world Excel files.
"""

import contextlib
import os
import re
import shutil
import subprocess
import tempfile
import warnings
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
from .excel_parser import ExcelParser

try:
    import pythoncom
    import win32com.client

    EXCEL_AVAILABLE = True
except ImportError:
    EXCEL_AVAILABLE = False
    win32com = None
    pythoncom = None


class XlsParser:
    """
    Parser for .xls files with multiple conversion strategies.

    Strategies (in priority order):
    1. LibreOffice headless: --convert-to xlsx (no COM, no deadlocks)
    2. Excel COM: win32com automation (fallback)
    3. openpyxl: direct read (for misnamed .xlsx files)
    """

    def __init__(self, file_path: str | Path):
        """
        Args:
            file_path: Absolute path to .xls file
        """
        self.file_path = Path(file_path)
        self.df: pd.DataFrame | None = None
        self.conversion_method: str | None = None  # Track which method worked

    def read(self) -> pd.DataFrame | None:
        """
        Read .xls file using best available strategy.

        Priority:
        1. Try LibreOffice headless conversion (if soffice available)
        2. Try Excel COM automation (if pywin32 available)
        3. Try openpyxl direct read (last resort)

        Returns:
            DataFrame with parsed data, or None if all strategies fail
        """
        if self.df is not None:
            return self.df

        if not self.file_path.exists():
            warnings.warn(f"File not found: {self.file_path}", stacklevel=2)
            return None

        # Prefer a pre-converted sibling .xlsx if present (fast path, used in tests/docs)
        sibling_xlsx = self.file_path.with_suffix(".xlsx")
        if sibling_xlsx.exists():
            try:
                df = ExcelParser(sibling_xlsx).read()
                if df is not None and not df.empty:
                    self.conversion_method = "sibling_xlsx"
                    self.df = df
                    return self.df
            except Exception:
                pass

        # Strategy 1: LibreOffice headless (PREFERRED)
        df = self._try_libreoffice_conversion()
        if df is not None:
            self.conversion_method = "libreoffice"
            self.df = df
            return self.df

        # Strategy 2: Excel COM automation (FALLBACK)
        df = self._try_excel_com()
        if df is not None:
            self.conversion_method = "excel_com"
            self.df = df
            return self.df

        # Strategy 3: Direct openpyxl (LAST RESORT - for misnamed xlsx)
        df = self._try_openpyxl_direct()
        if df is not None:
            self.conversion_method = "openpyxl"
            self.df = df
            return self.df

        warnings.warn(
            f"All conversion strategies failed for {self.file_path.name}. "
            f"Install LibreOffice or ensure Excel is available.", stacklevel=2
        )
        return None

    def _try_libreoffice_conversion(self) -> pd.DataFrame | None:
        """
        Try converting .xls to .xlsx using LibreOffice headless mode.

        This is the PREFERRED method because:
        - No COM issues (deadlocks, process leaks)
        - Faster than COM
        - More reliable for batch processing
        - Works on Windows/Linux/Mac

        Returns:
            DataFrame or None if conversion fails
        """
        # Check if soffice is available
        soffice_paths = [
            r"C:\Program Files\LibreOffice\program\soffice.exe",
            r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
            "soffice",  # In PATH
        ]

        soffice_exe = None
        for path in soffice_paths:
            if shutil.which(path) or (Path(path).exists() if "\\" in path else False):
                soffice_exe = path
                break

        if soffice_exe is None:
            return None  # LibreOffice not installed

        temp_dir = None

        try:
            # Create temp directory for conversion
            temp_dir = tempfile.mkdtemp()

            # Run LibreOffice headless conversion
            # --headless: no GUI
            # --convert-to xlsx: target format
            # --outdir: output directory
            cmd = [
                soffice_exe,
                "--headless",
                "--convert-to",
                "xlsx",
                "--outdir",
                temp_dir,
                str(self.file_path.absolute()),
            ]

            subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,  # 30s timeout
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )

            # Find the converted .xlsx file
            expected_xlsx = Path(temp_dir) / (self.file_path.stem + ".xlsx")
            if not expected_xlsx.exists():
                # Try finding any xlsx in temp dir
                xlsx_files = list(Path(temp_dir).glob("*.xlsx"))
                if xlsx_files:
                    expected_xlsx = xlsx_files[0]
                else:
                    return None

            # Read and process the xlsx
            df = self._read_and_process_xlsx(str(expected_xlsx))
            return df

        except subprocess.TimeoutExpired:
            warnings.warn(f"LibreOffice conversion timeout for {self.file_path.name}", stacklevel=2)
            return None
        except Exception:
            # Silent fail - will try next strategy
            return None
        finally:
            # Cleanup temp directory
            if temp_dir and os.path.exists(temp_dir):
                with contextlib.suppress(Exception):
                    shutil.rmtree(temp_dir)

    def _try_excel_com(self) -> pd.DataFrame | None:
        """
        Try reading .xls using Excel COM automation with improved safety.

        Improvements over original:
        - Timeout protection (kills Excel if stuck)
        - Better process cleanup
        - Single-use Excel instance per file

        Returns:
            DataFrame or None if COM fails
        """
        if not EXCEL_AVAILABLE:
            return None

        excel = None
        workbook = None
        temp_xlsx = None
        com_initialized = False

        try:
            # Initialize COM for this thread
            try:
                pythoncom.CoInitialize()
                com_initialized = True
            except Exception:
                # Already initialized
                pass

            # Start Excel COM - use DispatchEx to get isolated instance
            excel = win32com.client.DispatchEx("Excel.Application")
            excel.Visible = False
            excel.DisplayAlerts = False
            excel.ScreenUpdating = False  # Faster processing
            excel.AskToUpdateLinks = False  # Don't prompt for links

            # Open the .xls file with restrictions
            abs_path = str(self.file_path.absolute())
            workbook = excel.Workbooks.Open(
                abs_path,
                ReadOnly=True,
                UpdateLinks=0,  # Don't update any links
                Password="",  # Empty password
                WriteResPassword="",  # Empty write password
                IgnoreReadOnlyRecommended=True,
                Notify=False,  # Don't notify
            )

            # Create temp .xlsx file
            with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
                temp_xlsx = tmp.name

            # Save as .xlsx (51 = xlOpenXMLWorkbook format)
            workbook.SaveAs(
                temp_xlsx, FileFormat=51, ConflictResolution=2
            )  # Overwrite without asking

            # Close workbook BEFORE quitting Excel
            workbook.Close(SaveChanges=False)
            workbook = None

            # Quit Excel
            excel.Quit()
            excel = None

            # Read with pandas/openpyxl and apply header detection
            df = self._read_and_process_xlsx(temp_xlsx)

            return df

        except Exception:
            # Silent fail - will try next strategy
            return None

        finally:
            # Aggressive cleanup to prevent deadlocks
            try:
                if workbook is not None:
                    workbook.Close(SaveChanges=False)
                    workbook = None
            except Exception:
                pass

            try:
                if excel is not None:
                    excel.Quit()
                    excel = None
            except Exception:
                pass

            # Uninitialize COM if we initialized it
            if com_initialized:
                with contextlib.suppress(Exception):
                    pythoncom.CoUninitialize()

            # Delete temp file
            if temp_xlsx and os.path.exists(temp_xlsx):
                with contextlib.suppress(Exception):
                    os.unlink(temp_xlsx)

            # Force garbage collection to release COM objects
            import gc

            gc.collect()

    def _read_and_process_xlsx(self, xlsx_path: str) -> pd.DataFrame | None:
        """
        Read and process the temporary XLSX file with same logic as ExcelParser.

        Args:
            xlsx_path: Path to temporary XLSX file

        Returns:
            Processed DataFrame or None
        """
        try:
            # Detect best header row using a raw sample read
            df_raw = pd.read_excel(xlsx_path, engine="openpyxl", header=None, nrows=80)
            df_raw_str = df_raw.astype(str)
            best_header = detect_header_row_df(df_raw_str)

            # Secondary heuristic: find first non-empty row after a keyword-bearing row
            if best_header is None:
                keywords = ["conta", "código", "codigo", "class", "desc", "saldo"]
                for idx in range(len(df_raw_str)):
                    row_text = " ".join(df_raw_str.iloc[idx].astype(str)).lower()
                    if sum(1 for kw in keywords if kw in row_text) >= 2:
                        for next_idx in range(idx, min(idx + 5, len(df_raw_str))):
                            if not df_raw_str.iloc[next_idx].isna().all():
                                best_header = next_idx
                                break
                        break

            header_candidates = (
                [best_header] if best_header is not None else []
            ) + list(range(0, 20))

            for hdr in header_candidates:
                try:
                    df = pd.read_excel(xlsx_path, engine="openpyxl", header=hdr)
                except Exception:
                    continue

                if df is None or df.empty:
                    continue

                # Try headerless read with manual column assignment if needed
                if hdr is None or (
                    hdr == 0 and not has_balance_keywords(list(df.columns))
                ):
                    try:
                        df_headerless = pd.read_excel(
                            xlsx_path, engine="openpyxl", header=None
                        )
                        if (
                            not df_headerless.empty
                            and best_header is not None
                            and best_header < len(df_headerless)
                        ):
                            new_cols = (
                                df_headerless.iloc[best_header].astype(str).str.strip()
                            )
                            df = df_headerless.iloc[best_header + 1 :].reset_index(
                                drop=True
                            )
                            df.columns = new_cols
                    except Exception:
                        pass

                # Basic cleanup and normalization
                df = df.dropna(axis=1, how="all")
                df = filter_sep_rows(df)
                df = unmerge_cells_forward_fill(df)

                # COMPACTION: Use shared ExcelParser method for merged cells
                excel_parser = ExcelParser(self.file_path)
                df = excel_parser._compact_merged_cells(df)

                df.columns = [str(c).strip() for c in df.columns]

                # If columns look like a balance table, return directly
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
                    for c in ["Saldo", "Saldo final", "Saldo atual", "Saldo Ant."]:
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

        except Exception:
            return None

        return None

    def _try_openpyxl_direct(self) -> pd.DataFrame | None:
        """
        Try reading file directly with openpyxl.

        This only works if the file is actually a .xlsx misnamed as .xls.
        This is surprisingly common with files downloaded from web systems.

        Returns:
            DataFrame or None if direct read fails
        """
        try:
            # Try reading as xlsx directly
            df = pd.read_excel(self.file_path, engine="openpyxl")

            if df is not None and not df.empty:
                # Apply same processing as _read_and_process_xlsx
                df = df.dropna(axis=1, how="all")
                df = filter_sep_rows(df)
                df = unmerge_cells_forward_fill(df)
                df.columns = [str(c).strip() for c in df.columns]

                if has_balance_keywords(list(df.columns)) or parece_balancete(df):
                    return df

        except Exception:
            return None

        return None
