"""
TableExtractor — extração avançada de tabelas de BP/DRE a partir de texto.

Nesta fase 3.4, o foco é preparar a estrutura para:
- segmentação de linhas
- junção de quebras
- normalização de valores numéricos
- (futuro) mapeamento por colunas usando ColumnDetector

As funções aqui visam ser puras e reusáveis na pipeline do PDF parser.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .column_detector import ColumnDetector
from .patterns import SETTINGS, extract_currency_info


@dataclass
class TableRow:
    raw: str
    parts: list[str]


@dataclass
class TableExtractionResult:
    rows: list[TableRow]
    metadata: dict[str, Any]


class TableExtractor:
    """
    Extrai uma estrutura tabular básica a partir de texto já extraído do PDF.
    Não depende de bibliotecas externas de detecção de tabela, apenas heurística de texto.
    """

    def __init__(self, trailing_numbers_order: str | None = None) -> None:
        self.column_detector = ColumnDetector()
        default_order = SETTINGS.get("trailing_numbers_order", "current_previous")
        self.trailing_numbers_order = (
            trailing_numbers_order if trailing_numbers_order else default_order
        )

    # -----------------------------
    # Linhas e segmentação básica
    # -----------------------------
    def split_lines(self, text: str) -> list[str]:
        lines = [ln.rstrip() for ln in text.splitlines()]
        return [ln for ln in lines if ln.strip()]

    def merge_wrapped_lines(self, lines: list[str]) -> list[str]:
        """
        Heurística simples: se a linha não contém nenhum dígito e a próxima contém,
        tenta fazer a junção considerando quebra de descrição.
        """
        if not lines:
            return []
        merged: list[str] = []
        buffer = lines[0]
        for nxt in lines[1:]:
            has_num_buf = bool(re.search(r"\d", buffer))
            has_num_nxt = bool(re.search(r"\d", nxt))
            if not has_num_buf and not buffer.endswith(":") and not has_num_nxt:
                buffer = f"{buffer} {nxt.strip()}"
            else:
                merged.append(buffer)
                buffer = nxt
        merged.append(buffer)
        return merged

    def tokenize_row(self, line: str) -> list[str]:
        # divide por múltiplos espaços ou tabs
        parts = re.split(r"\s{2,}|\t+", line.strip())
        parts = [p for p in parts if p != ""]

        # Fallback: se não houve divisão (PDFs que colapsam espaços),
        # tenta separar descrição e números finais separados por 1 espaço
        if len(parts) <= 1:
            desc, nums = self._split_desc_and_trailing_numbers(line)
            if desc or nums:
                parts = [desc, *nums] if desc else nums
        return parts

    # -----------------------------
    # Números
    # -----------------------------
    def parse_numeric(
        self, value: str, scale_unit: int | None = None
    ) -> float | None:
        if value is None:
            return None
        s = str(value).strip()
        if s == "" or s in {"-", "–", "—"}:
            return None

        neg = False
        # parênteses indicam negativo
        if s.startswith("(") and s.endswith(")"):
            neg = True
            s = s[1:-1].strip()

        # remove símbolos de moeda e espaços
        s = re.sub(r"[Rr]\$|\$|€|£", "", s)
        s = s.replace(" ", "")

        # se ainda houver letras, provavelmente não é número (ex.: "dez/24")
        if re.search(r"[A-Za-z]", s):
            return None

        # separar papéis de vírgula e ponto
        if "," in s:
            left, right = s.rsplit(",", 1)
            if right.isdigit() and len(right) in (1, 2):
                # vírgula decimal (BR): remove pontos de milhar, troca vírgula por ponto
                s = left.replace(".", "") + "." + right
            elif (
                right.isdigit()
                and len(right) == 3
                and left.replace("-", "").replace(".", "").isdigit()
            ):
                # vírgula de milhar (EN): remove vírgulas
                s = left.replace(",", "") + right
            else:
                # fallback: remove todas vírgulas
                s = s.replace(",", "")
        # tratar ponto
        if "." in s and "," not in s:
            left, right = s.rsplit(".", 1)
            if right.isdigit() and len(right) == 3 and left.replace("-", "").isdigit():
                # ponto de milhar (BR)
                s = left + right

        # remove qualquer caractere não numérico final (ex: notas)
        s = re.sub(r"[^0-9\.\-]", "", s)

        if s in {"", ".", "-", "--"}:
            return None

        try:
            num = float(s)
            if neg:
                num = -num
            if scale_unit:
                num *= scale_unit
            return num
        except ValueError:
            return None

    # -----------------------------
    # Extração principal
    # -----------------------------
    def extract_table(self, text: str) -> TableExtractionResult:
        lines = self.split_lines(text)
        lines = self.merge_wrapped_lines(lines)

        rows: list[TableRow] = []
        for ln in lines:
            parts = self.tokenize_row(ln)
            rows.append(TableRow(raw=ln, parts=parts))

        meta = {
            "line_count": len(lines),
            "currency": extract_currency_info(text),
        }
        return TableExtractionResult(rows=rows, metadata=meta)

    # -----------------------------
    # Header detection and structured mapping
    # -----------------------------
    def _find_header_index(self, rows: list[TableRow]) -> int:
        """
        Heurística: primeira linha contendo possível período (YYYY ou MM/YYYY)
        e múltiplas colunas.
        """
        # aceita: YYYY, MM/YYYY, DD/MM/YYYY, e meses pt-br abreviados como "mar/24"
        period_re = re.compile(
            r"(\b20\d{2}\b|\b\d{2}/\d{4}\b|\b\d{2}/\d{2}/\d{4}\b|\b(jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)[\-/]?\d{2,4}\b)",
            re.IGNORECASE,
        )
        for i, tr in enumerate(rows):
            if len(tr.parts) >= 2 and any(period_re.search(p or "") for p in tr.parts):
                return i
        # fallback: primeira linha com >= 3 partes
        for i, tr in enumerate(rows):
            if len(tr.parts) >= 3:
                return i
        return 0

    def _build_layout(self, header_parts: list[str]) -> Any:
        return self.column_detector.detect_columns(header_parts)

    def extract_structured(self, text: str) -> dict[str, Any]:
        """
        Extrai uma estrutura tabular com mapeamento de colunas (current/previous)
        e valores numéricos já normalizados.
        """
        base = self.extract_table(text)
        if not base.rows:
            return {"rows": [], "layout": None, "metadata": base.metadata}

        header_idx = self._find_header_index(base.rows)
        header = (
            base.rows[header_idx].parts
            if base.rows[header_idx].parts
            else [base.rows[header_idx].raw]
        )
        layout = self._build_layout(header)

        scale = None
        if base.metadata.get("currency"):
            scale = base.metadata["currency"].get("unit")
            # garantir int/float
            if isinstance(scale, str):
                try:
                    scale = float(scale)
                except Exception:
                    scale = None

        structured: list[dict[str, Any]] = []
        for tr in base.rows[header_idx + 1 :]:
            parts = tr.parts or [tr.raw]
            if not parts:
                continue

            desc = (
                parts[layout.description_column]
                if layout.description_column is not None
                and layout.description_column < len(parts)
                else parts[0]
            )
            current_val = None
            previous_val = None

            if layout.current_column is not None and layout.current_column < len(parts):
                current_val = self.parse_numeric(parts[layout.current_column], scale)
            if layout.previous_column is not None and layout.previous_column < len(
                parts
            ):
                previous_val = self.parse_numeric(parts[layout.previous_column], scale)

            # Fallback: se não conseguimos mapear colunas ou valores ficaram None,
            # tenta extrair números finais da linha crua (ex.: "... 5.176 922")
            if current_val is None and previous_val is None:
                d2, nums = self._split_desc_and_trailing_numbers(tr.raw)
                if d2:
                    desc = d2
                if nums:
                    # Ordem configurável: "current_previous" (padrão) ou "previous_current"
                    if self.trailing_numbers_order == "previous_current":
                        if len(nums) >= 1:
                            previous_val = self.parse_numeric(nums[0], scale)
                        if len(nums) >= 2:
                            current_val = self.parse_numeric(nums[1], scale)
                    else:
                        if len(nums) >= 1:
                            current_val = self.parse_numeric(nums[0], scale)
                        if len(nums) >= 2:
                            previous_val = self.parse_numeric(nums[1], scale)

            structured.append(
                {
                    "descricao": desc,
                    "current": current_val,
                    "previous": previous_val,
                    "raw": tr.raw,
                }
            )

        return {"rows": structured, "layout": layout, "metadata": base.metadata}

    # -----------------------------
    # Camelot-based extraction (optional)
    # -----------------------------
    def extract_with_camelot(
        self, pdf_path: str | Path, page_index: int
    ) -> dict[str, Any] | None:
        try:
            import camelot  # type: ignore
        except Exception:
            return None

        # Camelot uses 1-based page indexing
        page_str = str(page_index + 1)

        # Try stream first (no borders), then lattice (with borders)
        tables = None
        for flavor in ("stream", "lattice"):
            try:
                tables = camelot.read_pdf(str(pdf_path), pages=page_str, flavor=flavor)
                if tables and tables.n > 0:
                    break
            except Exception:
                tables = None
        if not tables or tables.n == 0:
            return None

        df = tables[0].df  # type: ignore[attr-defined]
        if df is None or df.empty:
            return None

        # Use first row as header if looks like header
        header = [str(x) for x in list(df.iloc[0].values)]
        layout = self.column_detector.detect_columns(header)

        structured: list[dict[str, Any]] = []
        scale = None
        for i in range(1, len(df)):
            row_vals = [
                str(x) if x is not None else "" for x in list(df.iloc[i].values)
            ]
            desc = (
                row_vals[layout.description_column]
                if layout.description_column is not None
                and layout.description_column < len(row_vals)
                else row_vals[0]
                if row_vals
                else ""
            )
            current_val = None
            previous_val = None
            if layout.current_column is not None and layout.current_column < len(
                row_vals
            ):
                current_val = self.parse_numeric(row_vals[layout.current_column], scale)
            if layout.previous_column is not None and layout.previous_column < len(
                row_vals
            ):
                previous_val = self.parse_numeric(
                    row_vals[layout.previous_column], scale
                )

            # Fallback semelhante ao texto: se não mapeou, tenta números finais
            if current_val is None and previous_val is None:
                raw_join = " ".join(row_vals)
                d2, nums = self._split_desc_and_trailing_numbers(raw_join)
                if d2:
                    desc = d2
                if nums:
                    if self.trailing_numbers_order == "previous_current":
                        if len(nums) >= 1:
                            previous_val = self.parse_numeric(nums[0], scale)
                        if len(nums) >= 2:
                            current_val = self.parse_numeric(nums[1], scale)
                    else:
                        if len(nums) >= 1:
                            current_val = self.parse_numeric(nums[0], scale)
                        if len(nums) >= 2:
                            previous_val = self.parse_numeric(nums[1], scale)

            structured.append(
                {
                    "descricao": desc,
                    "current": current_val,
                    "previous": previous_val,
                    "raw": " ".join(row_vals),
                }
            )

        return {"rows": structured, "layout": layout, "metadata": {}}

    # -----------------------------
    # Helpers internos
    # -----------------------------
    def _split_desc_and_trailing_numbers(self, line: str) -> tuple[str, list[str]]:
        """
        Separa a descrição e um bloco final de 1-3 números no fim da linha.
        Ex.: "Caixa e equivalentes 5.176 922" -> ("Caixa e equivalentes", ["5.176", "922"])
        """
        if not line:
            return "", []

        text = line.strip()
        # Captura qualquer sequência final composta por números com separadores e espaços
        m = re.search(
            r"^(.*?)(-?\(?[0-9\.\,]+\)?(?:\s+-?\(?[0-9\.\,]+\)?){0,3})\s*$", text
        )
        if not m:
            return text, []

        desc = m.group(1).strip()
        tail = m.group(2).strip()
        # Normaliza espaços antes de separadores decimais/de milhar (ex.: "2 .533.136,00" → "2.533.136,00")
        tail = re.sub(r"\s+(?=[\.,])", "", tail)
        # Divide por espaço e filtra tokens com cara de número
        tokens = [t for t in re.split(r"\s+", tail) if re.search(r"[0-9]", t)]
        # Merge defensivo de fragmentos numéricos ainda separados
        tokens = self._merge_numeric_fragments(tokens)
        # Prioriza tokens claramente numéricos (com separadores ou >=2 dígitos)
        prioritized = [
            t
            for t in tokens
            if re.search(r"[\.,]", t) or len(re.sub(r"[^0-9]", "", t)) >= 2
        ]
        if len(prioritized) >= 1:
            tokens = prioritized
        # Evita casos onde a "cauda" é parte da descrição (muito pequena)
        if not tokens:
            return text, []
        return desc, tokens

    def _merge_numeric_fragments(self, tokens: list[str]) -> list[str]:
        merged: list[str] = []
        i = 0
        while i < len(tokens):
            t = tokens[i]
            if i + 1 < len(tokens):
                nxt = tokens[i + 1]
                # Caso típico: "2" + ".533.136,00" → "2.533.136,00"
                if re.fullmatch(r"\(?-?\d{1,3}\)?", t) and re.match(r"^[\.,]", nxt):
                    merged.append(f"{t}{nxt}")
                    i += 2
                    continue
                # Caso: separador sozinho (raro) "." + "533.136,00"
                if re.fullmatch(r"[\.,]", t) and re.match(r"^\d", nxt) and merged:
                    merged[-1] = f"{merged[-1]}{t}{nxt}"
                    i += 2
                    continue
            merged.append(t)
            i += 1
        return merged
