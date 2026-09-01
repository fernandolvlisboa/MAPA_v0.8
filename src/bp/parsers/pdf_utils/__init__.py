"""
PDF Utils — Utilitários para processamento avançado de PDFs

Módulo com ferramentas para OCR, detecção de tipo, pré-processamento e mais.
"""

from .column_detector import ColumnDetector, ColumnInfo, ColumnLayout, ColumnType
from .detector import PDFTypeDetector
from .noise_remover import CleanedText, NoiseRemover
from .ocr_engine import OCREngine
from .preprocessor import ImagePreprocessor
from .statement_detector import PageClassification, StatementDetector, StatementType
from .statement_pipeline import StatementTablePipeline
from .table_extractor import TableExtractor
from .table_validator import TableValidator

__all__ = [
    "CleanedText",
    "ColumnDetector",
    "ColumnInfo",
    "ColumnLayout",
    "ColumnType",
    "ImagePreprocessor",
    "NoiseRemover",
    "OCREngine",
    # OCR e detecção de tipo (Fase 3.2)
    "PDFTypeDetector",
    "PageClassification",
    # Detecção de demonstrações (Fase 3.3)
    "StatementDetector",
    "StatementTablePipeline",
    "StatementType",
    "TableExtractor",
    "TableValidator",
]
