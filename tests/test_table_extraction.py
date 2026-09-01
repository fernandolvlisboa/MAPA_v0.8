
import pytest

# PyMuPDF (`fitz`) vem do extra `ocr` (`uv sync --extra ocr`), não do núcleo.
# `pdf_utils/detector.py` o importa de forma ansiosa, então sem o extra este
# módulo nem coleta. Sem este guard, `uv sync && uv run pytest` — o fluxo que o
# README documenta — termina em erro de coleta em vez de skip.
pytest.importorskip("fitz", reason="requer o extra `ocr` (PyMuPDF)")

from src.bp.parsers.pdf_utils.table_extractor import TableExtractor
from src.bp.parsers.pdf_utils.table_validator import TableValidator


class TestTableExtractor:
    def test_create_extractor(self):
        ext = TableExtractor()
        assert ext is not None

    def test_parse_numeric_common_cases(self):
        ext = TableExtractor()

        # BR format with thousands + decimal
        assert ext.parse_numeric("1.234,56") == pytest.approx(1234.56)
        # BR/US integers
        assert ext.parse_numeric("1.234") == pytest.approx(1234.0)
        assert ext.parse_numeric("1,234") == pytest.approx(1234.0)
        # Currency and spaces
        assert ext.parse_numeric("R$ 1.000") == pytest.approx(1000.0)
        # Parentheses negative
        assert ext.parse_numeric("(1.234,56)") == pytest.approx(-1234.56)
        # Scale (thousands)
        assert ext.parse_numeric("1.5", scale_unit=1000) == pytest.approx(1500.0)
        # Missing
        assert ext.parse_numeric("-") is None
        assert ext.parse_numeric("") is None

    def test_extract_table_basic(self):
        sample_text = (
            "EMPRESA XYZ LTDA\n"
            "BALANÇO PATRIMONIAL\n"
            "ATIVO            2024      2023\n"
            "Caixa            1.234     1.100\n"
            "Bancos           500       420\n"
            "TOTAL DO ATIVO   6.234     5.900\n"
        )
        ext = TableExtractor()
        res = ext.extract_table(sample_text)
        assert res.rows  # should not be empty
        assert isinstance(res.metadata, dict)
        assert "currency" in res.metadata

    def test_extract_structured_and_validate(self):
        sample_text = (
            "EMPRESA XYZ LTDA\n"
            "BALANÇO PATRIMONIAL\n"
            "Descrição        2024      2023\n"
            "Caixa            1.000     900\n"
            "Bancos           500       400\n"
            "TOTAL DO ATIVO   1.500     1.300\n"
        )

        ext = TableExtractor()
        out = ext.extract_structured(sample_text)
        assert out["rows"], "Should produce structured rows"
        # Expect the last line to be total and current=1500
        last = out["rows"][-1]
        assert isinstance(last.get("current"), (int, float))

        val = TableValidator()
        assert val.is_total_line(last.get("descricao"))
        assert val.validate_block_sum(out["rows"]) is True
