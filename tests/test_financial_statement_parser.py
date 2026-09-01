"""
Testes do FinancialStatementParser (Fase 3.5)
"""

from __future__ import annotations

from pathlib import Path
import json

import pytest

# PyMuPDF (`fitz`) vem do extra `ocr` (`uv sync --extra ocr`), não do núcleo.
# `pdf_utils/detector.py` o importa de forma ansiosa, então sem o extra este
# módulo nem coleta. Sem este guard, `uv sync && uv run pytest` — o fluxo que o
# README documenta — termina em erro de coleta em vez de skip.
pytest.importorskip("fitz", reason="requer o extra `ocr` (PyMuPDF)")

from src.bp.parsers.financial_statement_parser import FinancialStatementParser


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def pdf_dir() -> Path:
    """Diretório com PDFs de teste."""
    return Path(__file__).parent.parent / "auxil" / "BP_PDF_ex"


@pytest.fixture
def output_dir(tmp_path) -> Path:
    """Diretório temporário para saídas."""
    return tmp_path


# ============================================================================
# Testes de Análise
# ============================================================================


def test_analyze_simple_pdf(pdf_dir):
    """Testa análise rápida de PDF simples."""
    pdf_path = pdf_dir / "ABT - BP 03.2024.pdf"
    if not pdf_path.exists():
        pytest.skip(f"PDF de teste não encontrado: {pdf_path}")

    parser = FinancialStatementParser(pdf_path)
    analysis = parser.analyze()

    assert "type" in analysis
    assert "total_pages" in analysis
    assert "statements" in analysis
    assert analysis["total_pages"] > 0


def test_analyze_complex_pdf(pdf_dir):
    """Testa análise de PDF com múltiplas páginas."""
    pdf_path = pdf_dir / "Voll S.A_60_DF 2023.pdf"
    if not pdf_path.exists():
        pytest.skip(f"PDF de teste não encontrado: {pdf_path}")

    parser = FinancialStatementParser(pdf_path)
    analysis = parser.analyze()

    assert analysis["total_pages"] > 1
    assert len(analysis["statements"]["balance_sheet"]) > 0
    assert len(analysis["statements"]["income_statement"]) > 0


def test_analyze_nonexistent_pdf():
    """Testa erro quando PDF não existe."""
    with pytest.raises(FileNotFoundError):
        FinancialStatementParser("nao_existe.pdf")


# ============================================================================
# Testes de Extração Individual
# ============================================================================


def test_extract_balance_sheet(pdf_dir):
    """Testa extração apenas de BP."""
    pdf_path = pdf_dir / "ABT - BP 03.2024.pdf"
    if not pdf_path.exists():
        pytest.skip(f"PDF de teste não encontrado: {pdf_path}")

    parser = FinancialStatementParser(pdf_path)
    bp = parser.extract_balance_sheet()

    assert bp is not None
    assert bp.tipo == "BP"
    assert len(bp.contas) > 0
    assert "validation_status" in bp.__dict__


def test_extract_income_statement(pdf_dir):
    """Testa extração apenas de DRE."""
    pdf_path = pdf_dir / "Voll S.A_60_DF 2023.pdf"
    if not pdf_path.exists():
        pytest.skip(f"PDF de teste não encontrado: {pdf_path}")

    parser = FinancialStatementParser(pdf_path)
    dre = parser.extract_income_statement()

    assert dre is not None
    assert dre.tipo == "DRE"
    assert len(dre.contas) > 0


# ============================================================================
# Testes de Parsing Completo
# ============================================================================


def test_parse_complete_single_statement(pdf_dir):
    """Testa parsing completo de PDF com apenas BP."""
    pdf_path = pdf_dir / "ABT - BP 03.2024.pdf"
    if not pdf_path.exists():
        pytest.skip(f"PDF de teste não encontrado: {pdf_path}")

    parser = FinancialStatementParser(pdf_path)
    result = parser.parse_complete()

    assert result is not None
    assert result.metadata is not None
    assert result.balance_sheet is not None
    assert result.extraction_quality is not None


def test_parse_complete_full_statements(pdf_dir):
    """Testa parsing completo de PDF com BP e DRE."""
    pdf_path = pdf_dir / "Voll S.A_60_DF 2023.pdf"
    if not pdf_path.exists():
        pytest.skip(f"PDF de teste não encontrado: {pdf_path}")

    parser = FinancialStatementParser(pdf_path)
    result = parser.parse_complete()

    assert result.balance_sheet is not None
    assert result.income_statement is not None
    assert result.metadata.company is not None
    assert result.extraction_quality["bp_extracted"]
    assert result.extraction_quality["dre_extracted"]


# ============================================================================
# Testes de Mapeamento
# ============================================================================


def test_map_balance_sheet_structure(pdf_dir):
    """Testa mapeamento de estrutura do BP."""
    pdf_path = pdf_dir / "ABT - BP 03.2024.pdf"
    if not pdf_path.exists():
        pytest.skip(f"PDF de teste não encontrado: {pdf_path}")

    parser = FinancialStatementParser(pdf_path)
    bp = parser.extract_balance_sheet()
    mapped = parser.map_balance_sheet_structure(bp)

    assert "ativo" in mapped
    assert "passivo" in mapped
    assert "patrimonio_liquido" in mapped
    assert isinstance(mapped["ativo"], list)


def test_map_income_statement_structure(pdf_dir):
    """Testa mapeamento de estrutura da DRE."""
    pdf_path = pdf_dir / "Voll S.A_60_DF 2023.pdf"
    if not pdf_path.exists():
        pytest.skip(f"PDF de teste não encontrado: {pdf_path}")

    parser = FinancialStatementParser(pdf_path)
    dre = parser.extract_income_statement()
    mapped = parser.map_income_statement_structure(dre)

    assert "receita" in mapped or "custo" in mapped or "resultado" in mapped
    assert isinstance(mapped, dict)


# ============================================================================
# Testes de Exportação
# ============================================================================


def test_export_to_standard_format(pdf_dir):
    """Testa exportação para formato padrão."""
    pdf_path = pdf_dir / "ABT - BP 03.2024.pdf"
    if not pdf_path.exists():
        pytest.skip(f"PDF de teste não encontrado: {pdf_path}")

    parser = FinancialStatementParser(pdf_path)
    result = parser.parse_complete()
    standard = parser.export_to_standard_format(result)

    assert "metadata" in standard
    assert "balance_sheet" in standard
    assert "quality" in standard
    assert (
        standard["metadata"]["company"] is not None
        or standard["metadata"]["cnpj"] is not None
    )


def test_export_to_json(pdf_dir, output_dir):
    """Testa exportação para arquivo JSON."""
    pdf_path = pdf_dir / "ABT - BP 03.2024.pdf"
    if not pdf_path.exists():
        pytest.skip(f"PDF de teste não encontrado: {pdf_path}")

    parser = FinancialStatementParser(pdf_path)
    output_file = output_dir / "result.json"

    parser.export_to_json(output_file)

    assert output_file.exists()

    with open(output_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert "metadata" in data
    assert "balance_sheet" in data


def test_generate_report(pdf_dir):
    """Testa geração de relatório."""
    pdf_path = pdf_dir / "ABT - BP 03.2024.pdf"
    if not pdf_path.exists():
        pytest.skip(f"PDF de teste não encontrado: {pdf_path}")

    parser = FinancialStatementParser(pdf_path)
    report = parser.generate_report()

    assert isinstance(report, str)
    assert len(report) > 100
    assert "Relatório de Extração" in report
    assert "Metadados" in report
    assert "Qualidade" in report


# ============================================================================
# Testes de Qualidade
# ============================================================================


def test_extraction_quality_assessment(pdf_dir):
    """Testa avaliação de qualidade da extração."""
    pdf_path = pdf_dir / "Voll S.A_60_DF 2023.pdf"
    if not pdf_path.exists():
        pytest.skip(f"PDF de teste não encontrado: {pdf_path}")

    parser = FinancialStatementParser(pdf_path)
    result = parser.parse_complete()

    quality = result.extraction_quality

    assert "bp_extracted" in quality
    assert "dre_extracted" in quality
    assert "bp_accounts" in quality
    assert "dre_accounts" in quality
    assert quality["bp_accounts"] > 0
    assert quality["dre_accounts"] > 0


def test_validation_status(pdf_dir):
    """Testa status de validação das demonstrações."""
    pdf_path = pdf_dir / "ABT - BP 03.2024.pdf"
    if not pdf_path.exists():
        pytest.skip(f"PDF de teste não encontrado: {pdf_path}")

    parser = FinancialStatementParser(pdf_path)
    bp = parser.extract_balance_sheet()

    validation = bp.validation_status

    assert "totals_detected" in validation
    assert "totals_valid" in validation
    assert isinstance(validation["totals_detected"], int)


# ============================================================================
# Testes de Metadata
# ============================================================================


def test_metadata_extraction(pdf_dir):
    """Testa extração completa de metadados."""
    pdf_path = pdf_dir / "Voll S.A_60_DF 2023.pdf"
    if not pdf_path.exists():
        pytest.skip(f"PDF de teste não encontrado: {pdf_path}")

    parser = FinancialStatementParser(pdf_path)
    result = parser.parse_complete()

    meta = result.metadata

    assert meta.extraction_date is not None
    assert meta.pages_total > 0
    assert len(meta.pages_bp) > 0 or len(meta.pages_dre) > 0


# ============================================================================
# Testes de Performance
# ============================================================================


def test_caching_analysis(pdf_dir):
    """Testa cache de análise."""
    pdf_path = pdf_dir / "ABT - BP 03.2024.pdf"
    if not pdf_path.exists():
        pytest.skip(f"PDF de teste não encontrado: {pdf_path}")

    parser = FinancialStatementParser(pdf_path)

    # Primeira análise
    analysis1 = parser.analyze()

    # Segunda análise (deve usar cache)
    analysis2 = parser.analyze()

    assert analysis1 == analysis2
    assert parser._analyzed is True
