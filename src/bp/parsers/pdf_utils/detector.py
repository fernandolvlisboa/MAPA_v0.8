"""
PDFTypeDetector — Detecta tipo e qualidade de PDFs

Identifica se um PDF é nativo (com texto selecionável) ou escaneado (imagem).
Avalia a qualidade e necessidade de OCR.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import fitz  # PyMuPDF


class PDFTypeDetector:
    """Detector de tipo e qualidade de PDFs."""

    def __init__(self, file_path: Path | str):
        """
        Args:
            file_path: Caminho do arquivo PDF
        """
        self.file_path = Path(file_path)
        self._doc = None

    def __enter__(self):
        """Context manager: abre o PDF."""
        self._doc = fitz.open(self.file_path)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager: fecha o PDF."""
        if self._doc:
            self._doc.close()

    def detect_type(self) -> dict[str, any]:
        """
        Detecta o tipo do PDF e retorna informações completas.

        Returns:
            Dict com informações:
            {
                "type": "native" | "scanned" | "hybrid",
                "has_text": bool,
                "text_ratio": float (0.0 - 1.0),
                "quality": "high" | "medium" | "low",
                "needs_ocr": bool,
                "total_pages": int,
                "pages_with_text": int,
                "pages_with_images": int
            }
        """
        with fitz.open(self.file_path) as doc:
            total_pages = len(doc)
            pages_with_text = 0
            pages_with_images = 0
            total_text_length = 0

            for page in doc:
                # Verifica texto
                text = page.get_text().strip()
                if len(text) > 50:  # Threshold mínimo
                    pages_with_text += 1
                    total_text_length += len(text)

                # Verifica imagens
                images = page.get_images()
                if images:
                    pages_with_images += 1

            # Calcula razão de texto
            text_ratio = pages_with_text / total_pages if total_pages > 0 else 0.0

            # Determina tipo
            if text_ratio > 0.8:
                pdf_type = "native"
                needs_ocr = False
            elif text_ratio < 0.2:
                pdf_type = "scanned"
                needs_ocr = True
            else:
                pdf_type = "hybrid"
                needs_ocr = text_ratio < 0.5

            # Avalia qualidade baseado em texto extraído
            avg_text_per_page = (
                total_text_length / total_pages if total_pages > 0 else 0
            )
            if avg_text_per_page > 1000:
                quality = "high"
            elif avg_text_per_page > 300:
                quality = "medium"
            else:
                quality = "low"

            return {
                "type": pdf_type,
                "has_text": pages_with_text > 0,
                "text_ratio": round(text_ratio, 2),
                "quality": quality,
                "needs_ocr": needs_ocr,
                "total_pages": total_pages,
                "pages_with_text": pages_with_text,
                "pages_with_images": pages_with_images,
            }

    def is_native_pdf(self) -> bool:
        """
        Verifica se o PDF é nativo (texto selecionável).

        Returns:
            True se nativo, False se escaneado
        """
        info = self.detect_type()
        return info["type"] == "native"

    def is_scanned_pdf(self) -> bool:
        """
        Verifica se o PDF é escaneado (apenas imagens).

        Returns:
            True se escaneado, False se nativo
        """
        info = self.detect_type()
        return info["type"] == "scanned"

    def needs_ocr(self) -> bool:
        """
        Verifica se o PDF precisa de OCR.

        Returns:
            True se precisa OCR, False caso contrário
        """
        info = self.detect_type()
        return info["needs_ocr"]

    def estimate_quality(self) -> Literal["high", "medium", "low"]:
        """
        Estima a qualidade do PDF para extração.

        Returns:
            "high", "medium" ou "low"
        """
        info = self.detect_type()
        return info["quality"]

    def has_extractable_text(self, min_pages: int = 1) -> bool:
        """
        Verifica se o PDF tem texto extraível em número mínimo de páginas.

        Args:
            min_pages: Número mínimo de páginas com texto

        Returns:
            True se tem texto suficiente, False caso contrário
        """
        info = self.detect_type()
        return info["pages_with_text"] >= min_pages

    def get_page_info(self, page_num: int) -> dict[str, any]:
        """
        Retorna informações sobre uma página específica.

        Args:
            page_num: Número da página (0-indexed)

        Returns:
            Dict com informações da página
        """
        with fitz.open(self.file_path) as doc:
            if page_num >= len(doc):
                raise ValueError(f"Página {page_num} não existe (total: {len(doc)})")

            page = doc[page_num]
            text = page.get_text().strip()
            images = page.get_images()

            return {
                "page_number": page_num,
                "has_text": len(text) > 50,
                "text_length": len(text),
                "image_count": len(images),
                "width": page.rect.width,
                "height": page.rect.height,
            }
