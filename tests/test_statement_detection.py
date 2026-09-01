"""
Testes para detecção de demonstrações financeiras (Fase 3.3)
"""

import pytest

# PyMuPDF (`fitz`) vem do extra `ocr` (`uv sync --extra ocr`), não do núcleo.
# `pdf_utils/detector.py` o importa de forma ansiosa, então sem o extra este
# módulo nem coleta. Sem este guard, `uv sync && uv run pytest` — o fluxo que o
# README documenta — termina em erro de coleta em vez de skip.
pytest.importorskip("fitz", reason="requer o extra `ocr` (PyMuPDF)")

from src.bp.parsers.pdf_utils import (
    StatementDetector,
    StatementType,
    NoiseRemover,
    ColumnDetector,
    ColumnType,
)


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def sample_bp_text():
    """Texto de exemplo de um Balanço Patrimonial."""
    return """
    EMPRESA XYZ LTDA
    CNPJ: 12.345.678/0001-90
    
    BALANÇO PATRIMONIAL
    Em 31 de dezembro de 2024
    Valores em milhares de reais
    
    ATIVO                           2024        2023
    Ativo Circulante               1.234       1.100
    Caixa                            100          80
    Bancos                           500         420
    Aplicações Financeiras           634         600
    
    Ativo Não Circulante           5.000       4.800
    Imobilizado                    3.500       3.200
    Intangível                     1.500       1.600
    
    TOTAL DO ATIVO                 6.234       5.900
    
    PASSIVO
    Passivo Circulante               800         750
    Fornecedores                     500         450
    Empréstimos                      300         300
    
    Patrimônio Líquido             5.434       5.150
    Capital Social                 4.000       4.000
    Lucros Acumulados              1.434       1.150
    
    TOTAL DO PASSIVO E PL          6.234       5.900
    """


@pytest.fixture
def sample_dre_text():
    """Texto de exemplo de uma DRE."""
    return """
    EMPRESA ABC S.A.
    
    DEMONSTRAÇÃO DO RESULTADO DO EXERCÍCIO
    Período: 01/01/2024 a 31/12/2024
    Em milhares de reais
    
                                   2024        2023
    Receita Operacional Bruta    10.000       9.500
    (-) Deduções                 (1.000)       (950)
    
    Receita Operacional Líquida   9.000       8.550
    
    (-) Custo das Vendas         (5.000)     (4.700)
    
    Lucro Bruto                   4.000       3.850
    
    Despesas Operacionais        (2.500)     (2.400)
    Despesas Administrativas     (1.200)     (1.150)
    Despesas Comerciais          (1.300)     (1.250)
    
    Resultado Operacional         1.500       1.450
    
    Resultado Financeiro            100          50
    
    Lucro Líquido                 1.600       1.500
    """


@pytest.fixture
def sample_notes_text():
    """Texto de exemplo de notas explicativas."""
    return """
    NOTAS EXPLICATIVAS ÀS DEMONSTRAÇÕES FINANCEIRAS
    
    Nota 1 - Contexto Operacional
    
    A Empresa XYZ LTDA atua no segmento de tecnologia...
    
    Nota 2 - Políticas Contábeis
    
    As demonstrações financeiras foram elaboradas de acordo
    com as práticas contábeis adotadas no Brasil...
    """


@pytest.fixture
def sample_noise_text():
    """Texto de exemplo com ruído."""
    return """
    ____________________________________________
    
    Assinaturas:
    
    _______________________
    Diretor Financeiro
    
    _______________________
    Contador - CRC 12345/O-6
    
    De acordo,
    
    _______________________
    Auditor Independente
    KPMG Auditores
    """


# ============================================================================
# TESTES: StatementDetector
# ============================================================================


class TestStatementDetector:
    """Testes para StatementDetector."""

    def test_create_detector(self):
        """Testa criação do detector."""
        detector = StatementDetector()
        assert detector.min_confidence == 0.3
        assert detector.bp_weight == 1.0
        assert detector.dre_weight == 1.0

    def test_classify_bp_page(self, sample_bp_text):
        """Testa classificação de página de BP."""
        detector = StatementDetector()
        result = detector.classify_page(0, sample_bp_text)

        assert result.page_number == 0
        assert result.statement_type == StatementType.BALANCE_SHEET
        assert result.bp_score > 0.5
        assert result.confidence >= detector.min_confidence

    def test_classify_dre_page(self, sample_dre_text):
        """Testa classificação de página de DRE."""
        detector = StatementDetector()
        result = detector.classify_page(0, sample_dre_text)

        assert result.statement_type == StatementType.INCOME_STATEMENT
        assert result.dre_score > 0.5
        assert result.confidence >= detector.min_confidence

    def test_classify_notes_page(self, sample_notes_text):
        """Testa classificação de notas explicativas."""
        detector = StatementDetector()
        result = detector.classify_page(0, sample_notes_text)

        assert result.statement_type == StatementType.NOTES
        assert result.notes_score > 0.3

    def test_find_balance_sheet_pages(self, sample_bp_text, sample_dre_text):
        """Testa busca de páginas de BP."""
        detector = StatementDetector()
        pages = [sample_bp_text, sample_dre_text, sample_bp_text]

        bp_pages = detector.find_balance_sheet_pages(pages)
        assert 0 in bp_pages
        assert 2 in bp_pages
        assert len(bp_pages) == 2

    def test_find_income_statement_pages(self, sample_bp_text, sample_dre_text):
        """Testa busca de páginas de DRE."""
        detector = StatementDetector()
        pages = [sample_bp_text, sample_dre_text, sample_bp_text]

        dre_pages = detector.find_income_statement_pages(pages)
        assert 1 in dre_pages
        assert len(dre_pages) == 1

    def test_separate_statements(
        self, sample_bp_text, sample_dre_text, sample_notes_text
    ):
        """Testa separação de demonstrações."""
        detector = StatementDetector()
        pages = [sample_bp_text, sample_dre_text, sample_notes_text]

        separated = detector.separate_statements(pages)

        assert len(separated[StatementType.BALANCE_SHEET]) >= 1
        assert len(separated[StatementType.INCOME_STATEMENT]) >= 1
        assert len(separated[StatementType.NOTES]) >= 1

    def test_extract_metadata(self, sample_bp_text):
        """Testa extração de metadados."""
        detector = StatementDetector()
        metadata = detector.extract_metadata(sample_bp_text)

        assert metadata["cnpj"] == "12.345.678/0001-90"
        assert metadata["currency"]["currency"] == "BRL"
        assert metadata["currency"]["scale"] == "thousands"


# ============================================================================
# TESTES: NoiseRemover
# ============================================================================


class TestNoiseRemover:
    """Testes para NoiseRemover."""

    def test_create_remover(self):
        """Testa criação do remover."""
        remover = NoiseRemover()
        assert remover.min_line_length == 3
        assert remover.remove_duplicates is True

    def test_clean_text(self, sample_noise_text):
        """Testa limpeza de texto."""
        remover = NoiseRemover()
        result = remover.clean_text(sample_noise_text)

        assert result.removed_lines > 0
        assert result.noise_score > 0.0
        assert len(result.clean_text) < len(sample_noise_text)

    def test_remove_signature_areas(self, sample_noise_text):
        """Testa remoção de áreas de assinatura."""
        remover = NoiseRemover()
        clean = remover.remove_signature_areas(sample_noise_text)

        assert "assinaturas" not in clean.lower()
        assert len(clean) < len(sample_noise_text)

    def test_identify_repetitive_lines(self, sample_bp_text):
        """Testa identificação de linhas repetitivas."""
        remover = NoiseRemover()
        pages = [sample_bp_text, sample_bp_text]  # Mesma página 2x

        repetitive = remover.identify_repetitive_lines(pages, min_occurrences=2)
        assert len(repetitive) > 0

    def test_filter_page_numbers(self):
        """Testa remoção de números de página."""
        remover = NoiseRemover()
        text = "Linha 1\nPágina 5\nLinha 2\n5/10\nLinha 3"

        clean = remover.filter_page_numbers(text)
        assert "Página 5" not in clean
        assert "Linha 1" in clean
        assert "Linha 2" in clean

    def test_extract_relevant_sections(self, sample_bp_text):
        """Testa extração de seções relevantes."""
        remover = NoiseRemover()
        sections = remover.extract_relevant_sections(
            sample_bp_text,
            start_keywords=["ATIVO"],
            end_keywords=["TOTAL DO ATIVO"],
        )

        assert len(sections) > 0
        assert "ATIVO" in sections[0]


# ============================================================================
# TESTES: ColumnDetector
# ============================================================================


class TestColumnDetector:
    """Testes para ColumnDetector."""

    def test_create_detector(self):
        """Testa criação do detector."""
        detector = ColumnDetector()
        assert detector.min_confidence == 0.5

    def test_detect_columns_simple(self):
        """Testa detecção de colunas simples."""
        detector = ColumnDetector()
        header = ["Descrição", "2024", "2023"]

        layout = detector.detect_columns(header)

        assert len(layout.columns) == 3
        assert layout.description_column is not None
        assert layout.current_column is not None
        assert layout.has_comparative

    def test_detect_columns_with_periods(self):
        """Testa detecção de colunas com períodos."""
        detector = ColumnDetector()
        header = ["Conta", "12/2024", "12/2023"]

        layout = detector.detect_columns(header)

        assert layout.current_column is not None
        assert layout.previous_column is not None
        assert layout.has_comparative

    def test_identify_description_column(self):
        """Testa identificação de coluna de descrição."""
        detector = ColumnDetector()
        header = ["Descrição da Conta", "Saldo Atual", "Saldo Anterior"]

        desc_col = detector.identify_description_column(header)
        assert desc_col == 0

    def test_identify_value_columns(self):
        """Testa identificação de colunas de valores."""
        detector = ColumnDetector()
        header = ["Descrição", "R$ 2024", "R$ 2023"]

        value_cols = detector.identify_value_columns(header)
        assert 1 in value_cols
        assert 2 in value_cols

    def test_extract_comparative_values(self):
        """Testa extração de valores comparativos."""
        detector = ColumnDetector()
        header = ["Conta", "2024", "2023"]
        layout = detector.detect_columns(header)

        row = ["Caixa", "1.234,56", "1.100,00"]
        values = detector.extract_comparative_values(row, layout)

        assert values["current"] is not None
        assert values["previous"] is not None
        assert values["current"] > values["previous"]

    def test_detect_period_columns(self):
        """Testa detecção de colunas de período."""
        detector = ColumnDetector()
        header = ["Descrição", "12/2024", "12/2023", "Variação"]

        periods = detector.detect_period_columns(header)
        assert "12/2024" in periods
        assert "12/2023" in periods
        assert len(periods) == 2


# ============================================================================
# TESTES DE INTEGRAÇÃO
# ============================================================================


class TestStatementDetectionIntegration:
    """Testes de integração dos componentes."""

    def test_full_pipeline(self, sample_bp_text):
        """Testa pipeline completo de detecção."""
        # 1. Detecta tipo
        detector = StatementDetector()
        classification = detector.classify_page(0, sample_bp_text)
        assert classification.statement_type == StatementType.BALANCE_SHEET

        # 2. Remove ruído
        remover = NoiseRemover()
        cleaned = remover.clean_text(sample_bp_text)
        assert cleaned.cleaned_lines > 0

        # 3. Detecta colunas
        col_detector = ColumnDetector()
        header = ["ATIVO", "2024", "2023"]
        layout = col_detector.detect_columns(header)
        assert layout.has_comparative

    def test_metadata_extraction_integration(self, sample_bp_text):
        """Testa extração integrada de metadados."""
        detector = StatementDetector()
        metadata = detector.extract_metadata(sample_bp_text)

        # Verifica CNPJ
        assert metadata["cnpj"] is not None

        # Verifica moeda
        assert metadata["currency"]["currency"] == "BRL"
        assert metadata["currency"]["unit"] == 1000  # milhares
