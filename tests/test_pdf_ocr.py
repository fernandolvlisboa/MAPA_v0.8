"""
Testes para funcionalidades OCR do PDFParser.
"""

import pytest
from pathlib import Path

# O guard anterior era `try/import ... except ImportError` + `pytestmark =
# skipif(...)`. Não funciona: `pytestmark` pula os TESTES, mas os decoradores
# `@pytest.mark.skipif(not OCREngine.is_tesseract_installed())` mais abaixo são
# avaliados na COLETA, quando `OCREngine` não existe — o módulo morria com
# NameError em vez de pular. `importorskip` interrompe o módulo na hora certa.
pytest.importorskip("numpy", reason="requer o extra `ocr`")
pytest.importorskip("PIL", reason="requer o extra `ocr` (pillow)")
pytest.importorskip("fitz", reason="requer o extra `ocr` (PyMuPDF)")
pytest.importorskip("cv2", reason="requer o extra `ocr` (opencv-python)")

import numpy as np
from PIL import Image

from src.bp.parsers.pdf_utils.detector import PDFTypeDetector
from src.bp.parsers.pdf_utils.ocr_engine import OCREngine
from src.bp.parsers.pdf_utils.preprocessor import ImagePreprocessor


# Fixtures
@pytest.fixture
def sample_pdf_native():
    """Retorna caminho para PDF nativo se existir."""
    pdf_path = (
        Path(__file__).parent.parent / "auxil" / "BP_PDF_ex" / "ABT - BP 03.2024.pdf"
    )
    if pdf_path.exists():
        return pdf_path
    return None


@pytest.fixture
def sample_image():
    """Cria uma imagem de teste simples."""
    # Cria imagem branca 200x100 com texto preto
    img = Image.new("RGB", (200, 100), color="white")
    return np.array(img)


# Testes do PDFTypeDetector
class TestPDFTypeDetector:
    """Testes do detector de tipo de PDF."""

    def test_create_detector(self, tmp_path):
        """Testa criação do detector."""
        # Cria PDF temporário vazio
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4\n%EOF")

        detector = PDFTypeDetector(pdf_file)
        assert detector.file_path == pdf_file

    def test_detect_type_structure(self, sample_pdf_native):
        """Testa estrutura do resultado de detect_type."""
        if sample_pdf_native is None:
            pytest.skip("PDF de exemplo não encontrado")

        detector = PDFTypeDetector(sample_pdf_native)
        info = detector.detect_type()

        # Verifica campos obrigatórios
        assert "type" in info
        assert "has_text" in info
        assert "text_ratio" in info
        assert "quality" in info
        assert "needs_ocr" in info
        assert "total_pages" in info

        # Verifica tipos
        assert info["type"] in ["native", "scanned", "hybrid"]
        assert isinstance(info["has_text"], bool)
        assert isinstance(info["text_ratio"], float)
        assert info["quality"] in ["high", "medium", "low"]

    def test_is_native_pdf(self, sample_pdf_native):
        """Testa detecção de PDF nativo."""
        if sample_pdf_native is None:
            pytest.skip("PDF de exemplo não encontrado")

        detector = PDFTypeDetector(sample_pdf_native)
        # Maioria dos PDFs de exemplo devem ser nativos
        assert isinstance(detector.is_native_pdf(), bool)

    def test_has_extractable_text(self, sample_pdf_native):
        """Testa verificação de texto extraível."""
        if sample_pdf_native is None:
            pytest.skip("PDF de exemplo não encontrado")

        detector = PDFTypeDetector(sample_pdf_native)
        assert isinstance(detector.has_extractable_text(), bool)


# Testes do ImagePreprocessor
class TestImagePreprocessor:
    """Testes do pré-processador de imagens."""

    def test_binarize(self, sample_image):
        """Testa binarização de imagem."""
        preprocessor = ImagePreprocessor()

        # Testa métodos diferentes
        binary_otsu = preprocessor.binarize(sample_image, method="otsu")
        binary_adaptive = preprocessor.binarize(sample_image, method="adaptive")
        binary_simple = preprocessor.binarize(sample_image, method="simple")

        # Verifica que retorna array numpy
        assert isinstance(binary_otsu, np.ndarray)
        assert isinstance(binary_adaptive, np.ndarray)
        assert isinstance(binary_simple, np.ndarray)

        # Verifica dimensões
        assert binary_otsu.shape == sample_image.shape[:2]

    def test_denoise(self, sample_image):
        """Testa remoção de ruído."""
        preprocessor = ImagePreprocessor()

        denoised = preprocessor.denoise(sample_image, method="median")

        assert isinstance(denoised, np.ndarray)
        assert denoised.shape == sample_image.shape

    def test_adjust_contrast(self, sample_image):
        """Testa ajuste de contraste."""
        preprocessor = ImagePreprocessor()

        enhanced = preprocessor.adjust_contrast(sample_image, method="clahe")

        assert isinstance(enhanced, np.ndarray)
        # Deve ter 2D após conversão para grayscale
        assert len(enhanced.shape) == 2

    def test_deskew(self, sample_image):
        """Testa correção de rotação."""
        preprocessor = ImagePreprocessor()

        deskewed = preprocessor.deskew(sample_image)

        assert isinstance(deskewed, np.ndarray)
        assert deskewed.shape == sample_image.shape

    def test_resize_for_ocr(self, sample_image):
        """Testa redimensionamento para OCR."""
        preprocessor = ImagePreprocessor()

        resized = preprocessor.resize_for_ocr(
            sample_image, target_dpi=300, current_dpi=72
        )

        assert isinstance(resized, np.ndarray)
        # Deve ser maior que original (300/72 = 4.17x)
        assert resized.shape[0] > sample_image.shape[0]

    def test_preprocess_for_ocr(self, sample_image):
        """Testa pipeline completo."""
        preprocessor = ImagePreprocessor()

        processed = preprocessor.preprocess_for_ocr(sample_image)

        assert isinstance(processed, np.ndarray)
        # Deve ser binarizado (2D)
        assert len(processed.shape) == 2


# Testes do OCREngine
class TestOCREngine:
    """Testes do engine OCR."""

    def test_create_engine(self):
        """Testa criação do engine."""
        engine = OCREngine(language="por", engine="tesseract")

        assert engine.language == ["por"]
        assert engine.engine == "tesseract"

    def test_create_engine_multiple_languages(self):
        """Testa criação com múltiplos idiomas."""
        engine = OCREngine(language=["por", "eng"])

        assert engine.language == ["por", "eng"]

    def test_is_tesseract_installed(self):
        """Testa verificação de instalação do Tesseract."""
        result = OCREngine.is_tesseract_installed()

        # Deve retornar bool
        assert isinstance(result, bool)

    def test_get_available_languages(self):
        """Testa listagem de idiomas disponíveis."""
        langs = OCREngine.get_available_languages()

        # Deve retornar lista
        assert isinstance(langs, list)

    @pytest.mark.skipif(
        not OCREngine.is_tesseract_installed(), reason="Tesseract não instalado"
    )
    def test_extract_text_simple_image(self):
        """Testa extração de texto de imagem simples."""
        # Cria imagem simples com texto
        from PIL import ImageDraw, ImageFont

        img = Image.new("RGB", (200, 50), color="white")
        draw = ImageDraw.Draw(img)

        # Desenha texto simples (sem fonte específica, usa default)
        draw.text((10, 10), "TESTE", fill="black")

        engine = OCREngine(language="por")
        text = engine.extract_text(img)

        # OCR pode não ser perfeito, mas deve extrair algo
        assert isinstance(text, str)

    @pytest.mark.skipif(
        not OCREngine.is_tesseract_installed(), reason="Tesseract não instalado"
    )
    def test_extract_with_confidence(self):
        """Testa extração com informações de confiança."""
        from PIL import ImageDraw

        img = Image.new("RGB", (200, 50), color="white")
        draw = ImageDraw.Draw(img)
        draw.text((10, 10), "TESTE", fill="black")

        engine = OCREngine(language="por")
        result = engine.extract_with_confidence(img)

        # Verifica estrutura do resultado
        assert "text" in result
        assert "confidence" in result
        assert "engine" in result
        assert "word_count" in result

        assert isinstance(result["text"], str)
        assert isinstance(result["confidence"], float)
        assert 0.0 <= result["confidence"] <= 1.0


# Testes de Integração
class TestPDFOCRIntegration:
    """Testes de integração entre componentes."""

    def test_full_pipeline_on_image(self, sample_image):
        """Testa pipeline completo: preprocessamento + OCR."""
        # Pré-processa
        preprocessor = ImagePreprocessor()
        processed = preprocessor.preprocess_for_ocr(sample_image)

        # Verifica que processou
        assert isinstance(processed, np.ndarray)

        # OCR (só se Tesseract estiver instalado)
        if OCREngine.is_tesseract_installed():
            engine = OCREngine(language="por")
            text = engine.extract_text(processed)

            assert isinstance(text, str)
