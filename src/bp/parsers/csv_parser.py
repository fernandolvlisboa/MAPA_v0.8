from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from .base_parser import BaseParser, ParseResult


class CSVParser(BaseParser):
    """
    Parser avançado de arquivos CSV de balancetes.

    Features:
    - Streaming support para arquivos grandes
    - BOM detection (UTF-8, UTF-16)
    - Header inference (auto-detecção de linha de cabeçalho)
    - Invalid line reporting com números de linha
    - Schema validation
    - Advanced delimiter detection
    """

    def __init__(self, file_path: Path, chunk_size: int = 10000):
        super().__init__(file_path)
        self._detected_encoding: str | None = None
        self._detected_delimiter: str | None = None
        self._detected_header_row: int = 0
        self._bom_encoding: str | None = None
        self.chunk_size = chunk_size
        self.invalid_rows: list[dict[str, Any]] = []

    def _detect_bom(self) -> str | None:
        """
        Detecta BOM (Byte Order Mark) no arquivo.

        Returns:
            Encoding específico se BOM detectado, None caso contrário
        """
        try:
            with open(self.file_path, "rb") as f:
                bom = f.read(4)

                # UTF-16 LE
                if bom.startswith(b"\xff\xfe"):
                    self._bom_encoding = "utf-16-le"
                    return "utf-16-le"

                # UTF-16 BE
                if bom.startswith(b"\xfe\xff"):
                    self._bom_encoding = "utf-16-be"
                    return "utf-16-be"

                # UTF-8 with BOM
                if bom.startswith(b"\xef\xbb\xbf"):
                    self._bom_encoding = "utf-8-sig"
                    return "utf-8-sig"

                # UTF-32 LE
                if bom.startswith(b"\xff\xfe\x00\x00"):
                    self._bom_encoding = "utf-32-le"
                    return "utf-32-le"

                # UTF-32 BE
                if bom.startswith(b"\x00\x00\xfe\xff"):
                    self._bom_encoding = "utf-32-be"
                    return "utf-32-be"
        except Exception:
            pass

        return None

    def validate(self) -> bool:
        """
        Valida arquivo CSV com BOM detection e encoding detection.

        Returns:
            True se arquivo é legível, False caso contrário
        """
        # Primeiro tenta BOM
        bom_encoding = self._detect_bom()
        if bom_encoding:
            try:
                _ = self.file_path.read_text(encoding=bom_encoding)
                self._detected_encoding = bom_encoding
                return True
            except Exception:
                pass

        # Tenta ler conteúdo com múltiplos encodings
        encodings = ["latin-1", "cp1252", "iso-8859-1", "windows-1252", "utf-8"]
        for enc in encodings:
            try:
                _ = self.file_path.read_text(encoding=enc)
                self._detected_encoding = enc
                return True
            except Exception:
                continue
        return False

    def _detect_header_row(self, text: str) -> int:
        """
        Detecta linha de cabeçalho baseado em keywords.

        Args:
            text: Conteúdo do arquivo

        Returns:
            Índice da linha de cabeçalho (0-based)
        """
        keywords = [
            "conta",
            "codigo",
            "código",
            "class",
            "desc",
            "descricao",
            "descrição",
            "saldo",
            "debito",
            "débito",
            "credito",
            "crédito",
            "nome",
        ]

        lines = text.splitlines()
        for i, line in enumerate(lines[:30]):  # Scan first 30 lines
            line_lower = line.lower()
            # Se tem 3+ keywords, provavelmente é header
            if sum(1 for kw in keywords if kw in line_lower) >= 3:
                self._detected_header_row = i
                return i

        # Default: primeira linha
        self._detected_header_row = 0
        return 0

    def _advanced_delimiter_detection(self, text: str) -> str:
        """
        Detecção avançada de delimitador com análise de consistência.

        Args:
            text: Conteúdo do arquivo

        Returns:
            Delimitador mais provável
        """
        lines = text.splitlines()[:50]
        if not lines:
            return ","

        delimiters = [",", ";", "\t", "|"]
        scores = dict.fromkeys(delimiters, 0)

        for delim in delimiters:
            # Conta colunas por linha
            column_counts = []
            for line in lines:
                if not line.strip():
                    continue
                # Ignora delimitadores dentro de aspas
                parts = line.split(delim)
                column_counts.append(len(parts))

            if not column_counts:
                continue

            # Consistência: desvio padrão baixo = bom
            if len(set(column_counts)) == 1:
                # Todas as linhas têm mesmo número de colunas
                scores[delim] += 100
            else:
                # Penaliza variação
                unique_counts = len(set(column_counts))
                scores[delim] += max(0, 50 - unique_counts * 5)

            # Frequência total
            total_count = sum(line.count(delim) for line in lines)
            scores[delim] += total_count

        # Retorna delimitador com maior score
        best_delim = max(scores, key=scores.get)
        self._detected_delimiter = best_delim
        return best_delim

    def _detect_delimiter(self) -> str:
        """
        Detecção de delimitador (usa versão avançada).

        Returns:
            Delimitador detectado
        """
        text = self.file_path.read_text(
            encoding=self._detected_encoding or "utf-8", errors="replace"
        )
        return self._advanced_delimiter_detection(text)

    def validate_schema(self, required_cols: list[str]) -> bool:
        """
        Valida se o CSV contém as colunas requeridas.

        Args:
            required_cols: Lista de padrões de colunas requeridas

        Returns:
            True se todas as colunas requeridas existem
        """
        try:
            delimiter = self._detect_delimiter()
            encoding = self._detected_encoding or "utf-8"

            # Lê apenas header
            df = pd.read_csv(
                self.file_path,
                sep=delimiter,
                encoding=encoding,
                nrows=1,
                engine="python",
            )

            # Verifica se cada coluna requerida existe
            return all(
                self._find_column(df.columns, [col]) is not None
                for col in required_cols
            )
        except Exception:
            return False

    def parse(self) -> ParseResult:
        """
        Parse completo do CSV com header inference e error tracking.

        Returns:
            ParseResult com contas e metadata detalhado
        """
        if not self.validate():
            raise ValueError(f"CSV inválido: {self.file_path}")

        # Detect parameters
        text = self.file_path.read_text(
            encoding=self._detected_encoding or "utf-8", errors="replace"
        )
        header_row = self._detect_header_row(text)
        delimiter = self._detect_delimiter()
        encoding = self._detected_encoding or "utf-8"

        # Reset invalid rows tracker
        self.invalid_rows = []

        # Lê DataFrame com header/skiprows conforme header_row detectado
        try:
            # Parâmetros especiais para CSVs brasileiros com ponto-e-vírgula e aspas
            read_kwargs = {
                "sep": delimiter,
                "encoding": encoding,
                "on_bad_lines": "warn",
                "engine": "python",
            }
            if delimiter == ";":
                read_kwargs.update(
                    {
                        "quotechar": '"',
                        "decimal": ",",
                        "thousands": ".",
                    }
                )
            if header_row > 0:
                read_kwargs["header"] = header_row
            df = pd.read_csv(self.file_path, **read_kwargs)
        except Exception as e:
            # Fallback: tenta sem skiprows
            try:
                df = pd.read_csv(
                    self.file_path,
                    sep=delimiter,
                    encoding=encoding,
                    on_bad_lines="skip",
                    engine="python",
                )
            except Exception:
                return ParseResult(
                    contas=[],
                    metadata={
                        **self._extract_metadata(),
                        "error": str(e),
                        "delimiter": delimiter,
                        "encoding": encoding,
                        "header_row": header_row,
                    },
                )

        if df is None or df.empty:
            # Fallback robusto: tentar encoding/delimitadores e header por densidade
            sep_candidates = [";", ",", "\t", "|"]
            enc_candidates = [encoding, "latin-1", "cp1252", "utf-8"]
            text_lines = text.splitlines()
            best_header = 0
            best_cols = 0
            best_sep = delimiter
            for sep in sep_candidates:
                for i in range(min(50, len(text_lines))):
                    cols = [c.strip() for c in text_lines[i].split(sep)]
                    non_empty = sum(1 for c in cols if c)
                    if non_empty > best_cols:
                        best_cols = non_empty
                        best_header = i
                        best_sep = sep
            df = None
            for enc_try in enc_candidates:
                try:
                    df = pd.read_csv(
                        self.file_path,
                        sep=best_sep,
                        encoding=enc_try,
                        header=best_header,
                        on_bad_lines="skip",
                        engine="python",
                    )
                    if df is not None and not df.empty:
                        delimiter = best_sep
                        encoding = enc_try
                        header_row = best_header
                        break
                except Exception:
                    continue
            if df is None or df.empty:
                return ParseResult(contas=[], metadata=self._extract_metadata())

        # Identifica colunas relevantes
        codigo_col = self._find_column(
            df.columns, ["codigo", "código", "conta", "classificacao", "classificação"]
        )
        descricao_col = self._find_column(
            df.columns, ["descricao", "descrição", "nome", "conta contábil", "conta"]
        )
        saldo_col = self._find_column(df.columns, ["saldo", "valor", "saldo atual"])

        contas: list[dict[str, Any]] = []
        for idx, row in df.iterrows():
            try:
                conta: dict[str, Any] = {"fonte": self.file_path.name}
                if codigo_col and pd.notna(row.get(codigo_col)):
                    conta["codigo"] = str(row.get(codigo_col)).strip()
                if descricao_col and pd.notna(row.get(descricao_col)):
                    conta["descricao"] = str(row.get(descricao_col)).strip()
                if saldo_col and pd.notna(row.get(saldo_col)):
                    conta["saldo"] = self._normalize_saldo(row.get(saldo_col))

                if "descricao" in conta or "codigo" in conta:
                    if "descricao" not in conta and "codigo" in conta:
                        conta["descricao"] = conta["codigo"]
                    contas.append(conta)
            except Exception as e:
                # Track invalid row
                self.invalid_rows.append(
                    {
                        "line": int(idx) + header_row + 2,  # +2 for 1-based and header
                        "reason": str(e),
                        "data": str(row.to_dict())
                        if hasattr(row, "to_dict")
                        else str(row),
                    }
                )

        metadata = self._extract_metadata()
        metadata["delimiter"] = delimiter
        metadata["encoding"] = encoding
        metadata["header_row"] = header_row
        metadata["total_contas"] = len(contas)
        metadata["bom_detected"] = self._bom_encoding is not None
        metadata["bom_encoding"] = self._bom_encoding
        metadata["invalid_rows_count"] = len(self.invalid_rows)
        if self.invalid_rows:
            metadata["invalid_rows"] = self.invalid_rows[:10]  # Limit to first 10

        return ParseResult(contas=contas, metadata=metadata)

    def parse_chunked(self, chunk_size: int | None = None):
        """
        Parse em chunks para arquivos grandes (streaming).

        Args:
            chunk_size: Tamanho do chunk (usa self.chunk_size se None)

        Yields:
            ParseResult para cada chunk processado
        """
        if not self.validate():
            raise ValueError(f"CSV inválido: {self.file_path}")

        chunk_size = chunk_size or self.chunk_size
        text = self.file_path.read_text(
            encoding=self._detected_encoding or "utf-8", errors="replace"
        )
        header_row = self._detect_header_row(text)
        delimiter = self._detect_delimiter()
        encoding = self._detected_encoding or "utf-8"

        # Iterator de chunks
        chunks = pd.read_csv(
            self.file_path,
            sep=delimiter,
            encoding=encoding,
            skiprows=range(header_row) if header_row > 0 else None,
            chunksize=chunk_size,
            on_bad_lines="skip",
            engine="python",
        )

        chunk_num = 0
        for chunk_df in chunks:
            chunk_num += 1

            # Processa chunk
            codigo_col = self._find_column(
                chunk_df.columns,
                ["codigo", "código", "conta", "classificacao", "classificação"],
            )
            descricao_col = self._find_column(
                chunk_df.columns,
                ["descricao", "descrição", "nome", "conta contábil", "conta"],
            )
            saldo_col = self._find_column(
                chunk_df.columns, ["saldo", "valor", "saldo atual"]
            )

            contas: list[dict[str, Any]] = []
            for _, row in chunk_df.iterrows():
                conta: dict[str, Any] = {"fonte": self.file_path.name}
                if codigo_col and pd.notna(row.get(codigo_col)):
                    conta["codigo"] = str(row.get(codigo_col)).strip()
                if descricao_col and pd.notna(row.get(descricao_col)):
                    conta["descricao"] = str(row.get(descricao_col)).strip()
                if saldo_col and pd.notna(row.get(saldo_col)):
                    conta["saldo"] = self._normalize_saldo(row.get(saldo_col))

                if "descricao" in conta or "codigo" in conta:
                    if "descricao" not in conta and "codigo" in conta:
                        conta["descricao"] = conta["codigo"]
                    contas.append(conta)

            metadata = {
                "chunk_number": chunk_num,
                "chunk_size": len(chunk_df),
                "delimiter": delimiter,
                "encoding": encoding,
                "header_row": header_row,
                "total_contas": len(contas),
            }

            yield ParseResult(contas=contas, metadata=metadata)

    def _find_column(self, columns: list[str], candidates: list[str]) -> str | None:
        cols_lower = {c.lower(): c for c in columns}
        for cand in candidates:
            if cand in cols_lower:
                return cols_lower[cand]
        for cand in candidates:
            for c in columns:
                if cand in c.lower():
                    return c
        return None


# Compatibilidade: manter o nome antigo usado em algumas partes do código
class CsvParser(CSVParser):
    pass
