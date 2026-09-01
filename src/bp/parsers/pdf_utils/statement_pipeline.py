"""
StatementTablePipeline — integração StatementDetector + TableExtractor (Fase 3.4)

Fornece uma interface simples para, dado o texto das páginas:
- classificar páginas por demonstração
- extrair tabelas estruturadas por demonstração
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pdfplumber
from pdf2image import convert_from_path

from .ocr_engine import OCREngine
from .preprocessor import ImagePreprocessor
from .statement_detector import StatementDetector, StatementType
from .table_extractor import TableExtractor


class StatementTablePipeline:
    def __init__(self) -> None:
        self.detector = StatementDetector()
        self.extractor = TableExtractor()

    def extract_structured_from_pages(self, pages_text: list[str]) -> dict[str, Any]:
        sep = self.detector.separate_statements(pages_text)

        result = {
            "balance_sheet": [],
            "income_statement": [],
            "notes": [],
            "metadata": {},
        }

        # Extrai BP
        for idx in sep.get(StatementType.BALANCE_SHEET, []):
            structured = self.extractor.extract_structured(pages_text[idx])
            result["balance_sheet"].append(structured)

        # Extrai DRE
        for idx in sep.get(StatementType.INCOME_STATEMENT, []):
            structured = self.extractor.extract_structured(pages_text[idx])
            result["income_statement"].append(structured)

        # Metadados simples da primeira página relevante
        for bucket in (StatementType.BALANCE_SHEET, StatementType.INCOME_STATEMENT):
            pages = sep.get(bucket, [])
            if pages:
                meta = self.detector.extract_metadata(pages_text[pages[0]])
                result["metadata"] = meta
                break

        return result

    @staticmethod
    def detect_entities_and_periods_from_table(
        table: list[list[str]],
    ) -> dict[str, list[str]]:
        """
        Detecta entidades (controladora|consolidado), períodos (datas dd/mm/yyyy)
        e janelas (9M|3M) a partir de linhas de cabeçalho de uma tabela.
        """
        entities = set()
        periods = set()
        windows = set()

        import re as _re

        date_pattern = _re.compile(r"\b\d{2}/\d{2}/\d{4}\b")

        def _is_header_row(row: list[str]) -> bool:
            joined = " ".join([str(c or "") for c in row]).lower()
            return any(
                k in joined
                for k in [
                    "controladora",
                    "consolidado",
                    "consolidadas",
                    "período",
                    "periodo",
                    "meses",
                    "findos",
                ]
            ) or bool(date_pattern.search(joined))

        for row in table[:5]:  # primeiras linhas tendem a conter cabeçalho
            cells = [str(c or "") for c in row]
            lower = [c.lower() for c in cells]
            joined = " ".join(lower)
            if not _is_header_row(row):
                continue

            if any("controladora" in c for c in lower):
                entities.add("controladora")
            if any("consolidado" in c or "consolidad" in c for c in lower):
                entities.add("consolidado")

            for m in date_pattern.findall(joined):
                periods.add(m)

            if "nove meses" in joined or "9 meses" in joined:
                windows.add("9M")
            if "três meses" in joined or "tres meses" in joined or "3 meses" in joined:
                windows.add("3M")

        return {
            "entities": sorted(entities),
            "periods": sorted(periods),
            "windows": sorted(windows),
        }

    # -----------------------------
    # Hybrid text extraction (native → OCR)
    # -----------------------------
    def get_pages_text_hybrid(self, pdf_path: str | Path) -> list[str]:
        pages_text: list[str] = []
        # 1) Try native text first
        with pdfplumber.open(str(pdf_path)) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                pages_text.append(text)

        # 2) OCR fallback for empty/very short pages
        need_ocr = [i for i, t in enumerate(pages_text) if len(t.strip()) < 20]
        if not need_ocr:
            return pages_text

        try:
            images = convert_from_path(str(pdf_path), dpi=300)
        except Exception:
            # If pdf2image not working, just return what we have
            return pages_text

        ocr = OCREngine(language=["por", "eng"], engine="tesseract")
        pre = ImagePreprocessor()
        for idx in need_ocr:
            if idx < len(images):
                img = images[idx]
                proc = pre.preprocess_for_ocr(img)
                text = ocr.extract_text(proc)
                pages_text[idx] = text or pages_text[idx]
        return pages_text

    # -----------------------------
    # Full PDF pipeline (classification + extraction with Camelot fallback)
    # -----------------------------
    def extract_structured_from_pdf(self, pdf_path: str | Path) -> dict[str, Any]:
        pages_text = self.get_pages_text_hybrid(pdf_path)
        sep = self.detector.separate_statements(pages_text)

        result = {
            "balance_sheet": [],
            "income_statement": [],
            "notes": [],
            "metadata": {},
        }

        # Helper to try camelot first then text
        def extract_page(page_idx: int) -> dict[str, Any]:
            # Try Camelot
            try:
                from pathlib import Path as _P

                structured = self.extractor.extract_with_camelot(_P(pdf_path), page_idx)
                if structured and structured.get("rows"):
                    return structured
            except Exception:
                pass
            # Fallback to text-based
            return self.extractor.extract_structured(pages_text[page_idx])

        # Extract BP
        for idx in sep.get(StatementType.BALANCE_SHEET, []):
            result["balance_sheet"].append(extract_page(idx))

        # Extract DRE
        for idx in sep.get(StatementType.INCOME_STATEMENT, []):
            result["income_statement"].append(extract_page(idx))

        # Metadata
        for bucket in (StatementType.BALANCE_SHEET, StatementType.INCOME_STATEMENT):
            pages = sep.get(bucket, [])
            if pages:
                meta = self.detector.extract_metadata(pages_text[pages[0]])
                result["metadata"] = meta
                break

        return result
