import pytest

# PyMuPDF (`fitz`) vem do extra `ocr` (`uv sync --extra ocr`), não do núcleo.
# `pdf_utils/detector.py` o importa de forma ansiosa, então sem o extra este
# módulo nem coleta. Sem este guard, `uv sync && uv run pytest` — o fluxo que o
# README documenta — termina em erro de coleta em vez de skip.
pytest.importorskip("fitz", reason="requer o extra `ocr` (PyMuPDF)")

from src.bp.parsers.pdf_utils import StatementTablePipeline


def test_pipeline_balance_sheet_basic():
    pages = [
        (
            "EMPRESA XYZ LTDA\n"
            "BALANÇO PATRIMONIAL\n"
            "Descrição        2024      2023\n"
            "Caixa            1.000     900\n"
            "Bancos           500       400\n"
            "TOTAL DO ATIVO   1.500     1.300\n"
        ),
        (
            "DEMONSTRAÇÃO DO RESULTADO DO EXERCÍCIO\n"
            "Descrição        2024      2023\n"
            "Receita Líquida  9.000     8.500\n"
            "Lucro Líquido    1.600     1.500\n"
        ),
    ]

    pipe = StatementTablePipeline()
    out = pipe.extract_structured_from_pages(pages)

    assert out["balance_sheet"], "Should detect and extract BP"
    assert out["income_statement"], "Should detect and extract DRE"
    # metadata presence
    assert isinstance(out["metadata"], dict)
