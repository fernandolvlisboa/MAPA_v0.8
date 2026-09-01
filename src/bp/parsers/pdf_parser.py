"""
PDFParser — Parser para arquivos PDF

Extrai tabelas de balanços patrimoniais em PDFs.
Suporta PDFs nativos (pdfplumber) e escaneados (OCR).
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any

import pdfplumber

from .base_parser import BaseParser, ParseResult

# Importa utilitários OCR (opcionais)
try:
    from pdf2image import convert_from_path

    from .pdf_utils.detector import PDFTypeDetector
    from .pdf_utils.ocr_engine import OCREngine
    from .pdf_utils.preprocessor import ImagePreprocessor

    PDF_UTILS_AVAILABLE = True
except ImportError:
    PDF_UTILS_AVAILABLE = False
    warnings.warn(
        "PDF Utils não disponíveis. OCR desabilitado. "
        "Instale: pip install pytesseract pdf2image opencv-python", stacklevel=2
    )


class PDFParser(BaseParser):
    """Parser para arquivos PDF de balanços."""

    def __init__(
        self,
        file_path: Path,
        page_numbers: list[int] | None = None,
        use_ocr: bool = False,
        auto_detect: bool = True,
        debug: bool = False,
    ):
        """
        Args:
            file_path: Caminho do arquivo PDF
            page_numbers: Lista de páginas a processar (None = todas)
            use_ocr: Forçar uso de OCR mesmo se PDF for nativo
            auto_detect: Auto-detectar se PDF precisa OCR
        """
        super().__init__(file_path)
        self.page_numbers = page_numbers
        self.use_ocr = use_ocr
        self.auto_detect = auto_detect
        self._pdf_info = None
        self.debug = debug

    def validate(self) -> bool:
        """
        Valida se o arquivo é um PDF válido.

        Returns:
            True se válido, False caso contrário
        """
        try:
            with pdfplumber.open(self.file_path) as pdf:
                return len(pdf.pages) > 0
        except Exception:
            return False

    def parse(self) -> ParseResult:
        """
        Parseia o PDF e extrai tabelas de contas.

        Estratégia:
        1. Abre o PDF com pdfplumber
        2. Para cada página, extrai tabelas
        3. Converte tabelas para o formato de contas

        Returns:
            ParseResult com contas extraídas
        """
        if not self.validate():
            raise ValueError(f"PDF inválido: {self.file_path}")

        contas = []
        metadata = self._extract_metadata()

        with pdfplumber.open(self.file_path) as pdf:
            metadata["total_paginas"] = len(pdf.pages)

            # Determina quais páginas processar
            pages_to_process = (
                self.page_numbers if self.page_numbers else range(len(pdf.pages))
            )

            # Build pages_text for detector usage
            pages_text = []
            for i in range(len(pdf.pages)):
                try:
                    txt = pdf.pages[i].extract_text() or ""
                except Exception:
                    txt = ""
                pages_text.append(txt)

            # Use StatementDetector to separate BP/DRE pages for focused metadata scan
            try:
                from .pdf_utils.statement_detector import (
                    StatementDetector,
                    StatementType,
                )

                detector = StatementDetector(min_confidence=0.2)
                separated = detector.separate_statements(pages_text)
                bp_pages = separated.get(StatementType.BALANCE_SHEET, [])
                dre_pages = separated.get(StatementType.INCOME_STATEMENT, [])

                # Global aggregation of entities/periods/windows across detected pages
                import re as _re

                date_pattern = _re.compile(r"\b\d{2}/\d{2}/\d{4}\b")
                ent_set, per_set, win_set = set(), set(), set()

                # Helper to scan text for signals
                def _scan_text(txt: str, is_dre: bool = False):
                    low = txt.lower()
                    # Entities (accept plural and capitalization variants)
                    if "controladora" in low:
                        ent_set.add("controladora")
                    if (
                        ("consolidado" in low)
                        or ("consolidadas" in low)
                        or ("consolidada" in low)
                        or ("consolidad" in low)
                    ):
                        ent_set.add("consolidado")
                    # Periods
                    for m in date_pattern.findall(txt):
                        per_set.add(m)
                    # Windows (only meaningful on DRE pages)
                    if is_dre:
                        if ("nove meses" in low) or ("9 meses" in low):
                            win_set.add("9M")
                        if (
                            ("três meses" in low)
                            or ("tres meses" in low)
                            or ("3 meses" in low)
                        ):
                            win_set.add("3M")

                for idx in bp_pages:
                    if 0 <= idx < len(pages_text):
                        _scan_text(pages_text[idx], is_dre=False)
                for idx in dre_pages:
                    if 0 <= idx < len(pages_text):
                        _scan_text(pages_text[idx], is_dre=True)

                if ent_set:
                    metadata["entities"] = sorted(ent_set)
                if per_set:
                    metadata["periods"] = sorted(per_set)
                if win_set:
                    metadata["windows"] = sorted(win_set)

                if self.debug:
                    print(f"[PDFParser] BP pages: {bp_pages}")
                    print(f"[PDFParser] DRE pages: {dre_pages}")
                    print(f"[PDFParser] Entities: {metadata.get('entities')}")
                    print(f"[PDFParser] Periods: {metadata.get('periods')}")
                    print(f"[PDFParser] Windows: {metadata.get('windows')}")
            except Exception:
                bp_pages, dre_pages = [], []

            # Additional targeted scan: first 10 lines from BP/DRE pages
            try:

                def _first_lines(txt: str, n: int = 10) -> str:
                    lines = [
                        line.strip() for line in (txt or "").split("\n") if line.strip()
                    ]
                    return " \n ".join(lines[:n])

                import re as _re

                date_pattern = _re.compile(r"\b\d{2}/\d{2}/\d{4}\b")
                ent_set2, per_set2, win_set2 = set(), set(), set()

                for idx in bp_pages:
                    if 0 <= idx < len(pages_text):
                        tx = _first_lines(pages_text[idx])
                        low = tx.lower()
                        if "controladora" in low:
                            ent_set2.add("controladora")
                        if (
                            ("consolidado" in low)
                            or ("consolidadas" in low)
                            or ("consolidada" in low)
                            or ("consolidad" in low)
                        ):
                            ent_set2.add("consolidado")
                        for m in date_pattern.findall(tx):
                            per_set2.add(m)

                for idx in dre_pages:
                    if 0 <= idx < len(pages_text):
                        tx = _first_lines(pages_text[idx])
                        low = tx.lower()
                        if "controladora" in low:
                            ent_set2.add("controladora")
                        if (
                            ("consolidado" in low)
                            or ("consolidadas" in low)
                            or ("consolidada" in low)
                            or ("consolidad" in low)
                        ):
                            ent_set2.add("consolidado")
                        if ("nove meses" in low) or ("9 meses" in low):
                            win_set2.add("9M")
                        if (
                            ("três meses" in low)
                            or ("tres meses" in low)
                            or ("3 meses" in low)
                        ):
                            win_set2.add("3M")
                        for m in date_pattern.findall(tx):
                            per_set2.add(m)

                if ent_set2:
                    metadata.setdefault("entities", [])
                    metadata["entities"] = sorted(
                        set(metadata["entities"]) | ent_set2
                    )
                if per_set2:
                    metadata.setdefault("periods", [])
                    metadata["periods"] = sorted(
                        set(metadata["periods"]) | per_set2
                    )
                if win_set2:
                    metadata.setdefault("windows", [])
                    metadata["windows"] = sorted(
                        set(metadata["windows"]) | win_set2
                    )

                if self.debug:
                    print(f"[PDFParser] Top-lines Entities: {metadata.get('entities')}")
                    print(f"[PDFParser] Top-lines Periods: {metadata.get('periods')}")
                    print(f"[PDFParser] Top-lines Windows: {metadata.get('windows')}")
            except Exception:
                pass

            for page_num in pages_to_process:
                if page_num >= len(pdf.pages):
                    continue

                page = pdf.pages[page_num]
                tables = page.extract_tables()

                # Enrich metadata by detecting entities/periods/windows from tables and page text
                try:
                    from .pdf_utils.statement_pipeline import StatementTablePipeline

                    pipeline = StatementTablePipeline()
                except Exception:
                    pipeline = None

                if tables and pipeline is not None:
                    try:
                        for tbl in tables[:3]:
                            det = pipeline.detect_entities_and_periods_from_table(tbl)
                            if det.get("entities"):
                                metadata.setdefault("entities", [])
                                metadata["entities"] = sorted(
                                    set(metadata["entities"]) | set(det["entities"])
                                )
                            if det.get("periods"):
                                metadata.setdefault("periods", [])
                                metadata["periods"] = sorted(
                                    set(metadata["periods"]) | set(det["periods"])
                                )
                            if det.get("windows"):
                                metadata.setdefault("windows", [])
                                metadata["windows"] = sorted(
                                    set(metadata["windows"]) | set(det["windows"])
                                )
                    except Exception:
                        pass

                # Also scan page text for entities/periods/windows when tables miss headers
                try:
                    text = (
                        pages_text[page_num]
                        if page_num < len(pages_text)
                        else (page.extract_text() or "")
                    )
                    lower = text.lower()
                    import re as _re

                    date_pattern = _re.compile(r"\b\d{2}/\d{2}/\d{4}\b")
                    det_text_entities = []
                    det_text_periods = date_pattern.findall(text)
                    det_text_windows = []

                    if ("controladora" in lower) and (
                        page_num in bp_pages or page_num in dre_pages
                    ):
                        det_text_entities.append("controladora")
                    if ("consolidado" in lower or "consolidadas" in lower) and (
                        page_num in bp_pages or page_num in dre_pages
                    ):
                        det_text_entities.append("consolidado")
                    if (("nove meses" in lower) or ("9 meses" in lower)) and (
                        page_num in dre_pages
                    ):
                        det_text_windows.append("9M")
                    if (
                        ("três meses" in lower)
                        or ("tres meses" in lower)
                        or ("3 meses" in lower)
                    ) and (page_num in dre_pages):
                        det_text_windows.append("3M")

                    if det_text_entities:
                        metadata.setdefault("entities", [])
                        metadata["entities"] = sorted(
                            set(metadata.get("entities", []))
                                | set(det_text_entities)
                        )
                    if det_text_periods:
                        metadata.setdefault("periods", [])
                        metadata["periods"] = sorted(
                            set(metadata.get("periods", [])) | set(det_text_periods)
                        )
                    if det_text_windows:
                        metadata.setdefault("windows", [])
                        metadata["windows"] = sorted(
                            set(metadata.get("windows", [])) | set(det_text_windows)
                        )
                except Exception:
                    pass

                # Processa cada tabela da página
                for table_idx, table in enumerate(tables):
                    contas_da_tabela = self._extract_contas_from_table(
                        table, page_num=page_num, table_idx=table_idx
                    )
                    contas.extend(contas_da_tabela)

        metadata["total_contas"] = len(contas)
        return ParseResult(contas=contas, metadata=metadata)

    def _extract_contas_from_table(
        self, table: list[list[str]], page_num: int, table_idx: int
    ) -> list[dict[str, Any]]:
        """
        Extrai contas de uma tabela extraída do PDF.

        Args:
            table: Tabela como lista de listas (matriz)
            page_num: Número da página
            table_idx: Índice da tabela na página

        Returns:
            Lista de contas
        """
        if not table or len(table) < 2:  # Precisa de header + pelo menos 1 linha
            return []

        contas = []

        # Assume que a primeira linha é o cabeçalho
        header = [str(cell).lower().strip() if cell else "" for cell in table[0]]

        # Detecta colunas relevantes
        column_map = self._detect_columns_in_header(header)

        # Processa cada linha (pula o header)
        for row_idx, row in enumerate(table[1:], start=1):
            try:
                # Pula linhas vazias
                if not any(row):
                    continue

                # Garante que row tenha o mesmo tamanho que header
                if len(row) < len(header):
                    row = row + [None] * (len(header) - len(row))

                # Extrai descrição
                desc_idx = column_map.get("descricao", 0)
                descricao = str(row[desc_idx]).strip() if row[desc_idx] else ""

                if not descricao or descricao.lower() in ["none", "nan", ""]:
                    continue

                # Monta a conta
                conta = {
                    "descricao": descricao,
                    "fonte": f"{self.file_path.name} (pág {page_num + 1}, tabela {table_idx + 1})",
                }

                # Adiciona campos opcionais
                if "codigo" in column_map:
                    codigo = (
                        str(row[column_map["codigo"]]).strip()
                        if row[column_map["codigo"]]
                        else ""
                    )
                    if codigo and codigo.lower() not in ["none", "nan"]:
                        conta["codigo"] = codigo

                if "saldo" in column_map:
                    saldo_raw = row[column_map["saldo"]]
                    conta["saldo"] = self._normalize_saldo(saldo_raw)

                if "natureza" in column_map:
                    natureza = (
                        str(row[column_map["natureza"]]).strip()
                        if row[column_map["natureza"]]
                        else ""
                    )
                    if natureza and natureza.lower() not in ["none", "nan"]:
                        conta["natureza"] = natureza

                contas.append(conta)

            except Exception:
                # Se der erro em uma linha, continua
                continue

        return contas

    def _detect_columns_in_header(self, header: list[str]) -> dict[str, int]:
        """
        Detecta quais colunas contêm código, descrição, saldo baseado no header.

        Args:
            header: Lista com nomes das colunas (já em lowercase)

        Returns:
            Dict mapeando tipo -> índice da coluna
        """
        column_map = {}

        patterns = {
            "codigo": ["codigo", "código", "conta", "cod", "code"],
            "descricao": [
                "descricao",
                "descrição",
                "description",
                "nome",
                "name",
                "titulo",
            ],
            "saldo": ["saldo", "valor", "value", "montante", "total"],
            "natureza": ["natureza", "tipo", "d/c", "dc"],
        }

        for idx, col_name in enumerate(header):
            for tipo, keywords in patterns.items():
                if tipo not in column_map:
                    for keyword in keywords:
                        if keyword in col_name:
                            column_map[tipo] = idx
                            break

        return column_map

    def get_page_count(self) -> int:
        """
        Retorna o número total de páginas do PDF.

        Returns:
            Número de páginas
        """
        try:
            with pdfplumber.open(self.file_path) as pdf:
                return len(pdf.pages)
        except Exception:
            return 0

    def detect_pdf_type(self) -> dict[str, Any]:
        """
        Detecta o tipo do PDF (nativo vs escaneado).

        Requer PDF Utils instalados.

        Returns:
            Dict com informações do PDF ou None se utils não disponíveis
        """
        if not PDF_UTILS_AVAILABLE:
            warnings.warn("PDF Utils não disponíveis para detecção", stacklevel=2)
            return {"type": "unknown", "needs_ocr": False, "quality": "unknown"}

        if self._pdf_info is None:
            detector = PDFTypeDetector(self.file_path)
            self._pdf_info = detector.detect_type()

        return self._pdf_info

    def extract_text_with_ocr(self, page_num: int) -> str:
        """
        Extrai texto de uma página usando OCR.

        Requer PDF Utils instalados.

        Args:
            page_num: Número da página (0-indexed)

        Returns:
            Texto extraído ou string vazia
        """
        if not PDF_UTILS_AVAILABLE:
            warnings.warn("PDF Utils não disponíveis para OCR", stacklevel=2)
            return ""

        try:
            # Converte página para imagem
            images = convert_from_path(
                self.file_path, first_page=page_num + 1, last_page=page_num + 1, dpi=300
            )

            if not images:
                return ""

            image = images[0]

            # Pré-processa imagem
            preprocessor = ImagePreprocessor()
            processed = preprocessor.preprocess_for_ocr(image)

            # Extrai texto com OCR
            ocr = OCREngine(language="por")
            result = ocr.extract_with_confidence(processed)

            return result["text"]

        except Exception as e:
            warnings.warn(f"Erro ao extrair texto com OCR: {e}", stacklevel=2)
            return ""

    def should_use_ocr(self) -> bool:
        """
        Determina se deve usar OCR baseado no tipo de PDF.

        Returns:
            True se deve usar OCR, False caso contrário
        """
        if self.use_ocr:
            return True

        if not self.auto_detect:
            return False

        if not PDF_UTILS_AVAILABLE:
            return False

        info = self.detect_pdf_type()
        return info.get("needs_ocr", False)
