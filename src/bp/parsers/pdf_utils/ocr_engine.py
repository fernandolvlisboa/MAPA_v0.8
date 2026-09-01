"""
OCREngine — Engine de OCR para extração de texto de imagens

Suporta múltiplos engines: Tesseract e (opcionalmente) EasyOCR.
Otimizado para português brasileiro.
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Literal

import numpy as np
from PIL import Image

try:
    import pytesseract

    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False
    warnings.warn("pytesseract não instalado. OCR não disponível.", stacklevel=2)

# EasyOCR é opcional (mais pesado)
try:
    import easyocr

    EASYOCR_AVAILABLE = True
except ImportError:
    EASYOCR_AVAILABLE = False


class OCREngine:
    """Engine de OCR com suporte a Tesseract e EasyOCR."""

    def __init__(
        self,
        language: str | list[str] = "por",
        engine: Literal["tesseract", "easyocr", "auto"] = "tesseract",
    ):
        """
        Args:
            language: Idioma(s) para OCR
                - "por" para português
                - "eng" para inglês
                - ["por", "eng"] para múltiplos
            engine: Engine de OCR a usar
                - "tesseract": Tesseract OCR (rápido, preciso)
                - "easyocr": EasyOCR (mais lento, boa precisão)
                - "auto": Escolhe automaticamente
        """
        self.language = language if isinstance(language, list) else [language]
        self.engine = engine
        self._easyocr_reader = None

        # Verifica disponibilidade
        if engine == "tesseract" and not TESSERACT_AVAILABLE:
            raise RuntimeError(
                "Tesseract não está disponível. Instale: "
                "pip install pytesseract e baixe Tesseract: "
                "https://github.com/UB-Mannheim/tesseract/wiki"
            )

        if engine == "easyocr" and not EASYOCR_AVAILABLE:
            raise RuntimeError(
                "EasyOCR não está disponível. Instale: pip install easyocr"
            )

    def extract_text_tesseract(
        self, image: np.ndarray | Image.Image | Path | str, config: str = "--psm 6"
    ) -> str:
        """
        Extrai texto usando Tesseract OCR.

        Args:
            image: Imagem (array, PIL, ou caminho)
            config: Configuração do Tesseract
                - "--psm 6": Assume bloco uniforme de texto
                - "--psm 3": Modo automático (padrão)
                - "--psm 11": Texto esparso

        Returns:
            Texto extraído
        """
        if not TESSERACT_AVAILABLE:
            raise RuntimeError("Tesseract não disponível")

        # Carrega imagem se for caminho
        if isinstance(image, (Path, str)):
            image = Image.open(image)
        elif isinstance(image, np.ndarray):
            image = Image.fromarray(image)

        # Configura idioma
        lang = "+".join(self.language)

        # Extrai texto
        try:
            text = pytesseract.image_to_string(image, lang=lang, config=config)
            return text.strip()
        except Exception as e:
            warnings.warn(f"Erro no Tesseract OCR: {e}", stacklevel=2)
            return ""

    def extract_text_easyocr(
        self, image: np.ndarray | Image.Image | Path | str, detail: int = 0
    ) -> str:
        """
        Extrai texto usando EasyOCR.

        Args:
            image: Imagem (array, PIL, ou caminho)
            detail: Nível de detalhe
                - 0: Apenas texto
                - 1: Texto + coordenadas + confiança

        Returns:
            Texto extraído
        """
        if not EASYOCR_AVAILABLE:
            raise RuntimeError("EasyOCR não disponível")

        # Inicializa reader se necessário
        if self._easyocr_reader is None:
            # Mapeia códigos de idioma
            lang_map = {"por": "pt", "eng": "en"}
            langs = [lang_map.get(lang, lang) for lang in self.language]
            self._easyocr_reader = easyocr.Reader(langs, gpu=False)

        # Converte para array numpy se necessário
        if isinstance(image, (Path, str)):
            image = np.array(Image.open(image))
        elif isinstance(image, Image.Image):
            image = np.array(image)

        # Extrai texto
        try:
            results = self._easyocr_reader.readtext(image, detail=detail)

            if detail == 0:
                # Apenas texto
                text = " ".join(results)
            else:
                # Texto + informações
                text = " ".join([item[1] for item in results])

            return text.strip()
        except Exception as e:
            warnings.warn(f"Erro no EasyOCR: {e}", stacklevel=2)
            return ""

    def extract_text(
        self, image: np.ndarray | Image.Image | Path | str, **kwargs
    ) -> str:
        """
        Extrai texto usando o engine configurado.

        Args:
            image: Imagem (array, PIL, ou caminho)
            **kwargs: Argumentos específicos do engine

        Returns:
            Texto extraído
        """
        if self.engine == "tesseract":
            return self.extract_text_tesseract(image, **kwargs)
        elif self.engine == "easyocr":
            return self.extract_text_easyocr(image, **kwargs)
        else:  # auto
            # Tenta Tesseract primeiro (mais rápido)
            if TESSERACT_AVAILABLE:
                return self.extract_text_tesseract(image, **kwargs)
            elif EASYOCR_AVAILABLE:
                return self.extract_text_easyocr(image, **kwargs)
            else:
                raise RuntimeError("Nenhum engine OCR disponível")

    def extract_with_confidence(
        self, image: np.ndarray | Image.Image | Path | str
    ) -> dict[str, any]:
        """
        Extrai texto com informações de confiança.

        Args:
            image: Imagem (array, PIL, ou caminho)

        Returns:
            Dict com texto e metadados:
            {
                "text": str,
                "confidence": float (0.0 - 1.0),
                "engine": str,
                "word_count": int
            }
        """
        if isinstance(image, (Path, str)):
            image = Image.open(image)
        elif isinstance(image, np.ndarray):
            image = Image.fromarray(image)

        if self.engine == "tesseract" and TESSERACT_AVAILABLE:
            # Extrai com dados de confiança
            lang = "+".join(self.language)
            data = pytesseract.image_to_data(
                image, lang=lang, output_type=pytesseract.Output.DICT
            )

            # Filtra palavras com confiança > 0
            confidences = [
                int(conf) for conf in data["conf"] if conf != "-1" and int(conf) > 0
            ]

            avg_confidence = (
                sum(confidences) / len(confidences) / 100.0 if confidences else 0.0
            )

            text = self.extract_text_tesseract(image)

            return {
                "text": text,
                "confidence": round(avg_confidence, 2),
                "engine": "tesseract",
                "word_count": len(text.split()),
            }

        else:
            # Sem informações de confiança
            text = self.extract_text(image)
            return {
                "text": text,
                "confidence": 0.0,  # Desconhecida
                "engine": self.engine,
                "word_count": len(text.split()),
            }

    @staticmethod
    def is_tesseract_installed() -> bool:
        """
        Verifica se Tesseract está instalado e acessível.

        Returns:
            True se instalado, False caso contrário
        """
        if not TESSERACT_AVAILABLE:
            return False

        try:
            pytesseract.get_tesseract_version()
            return True
        except Exception:
            return False

    @staticmethod
    def get_available_languages() -> list[str]:
        """
        Lista idiomas disponíveis no Tesseract.

        Returns:
            Lista de códigos de idioma
        """
        if not TESSERACT_AVAILABLE:
            return []

        try:
            langs = pytesseract.get_languages()
            return langs
        except Exception:
            return []
