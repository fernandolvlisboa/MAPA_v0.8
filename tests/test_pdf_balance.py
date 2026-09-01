"""Testes do PDFBalanceParser (extração de balancetes em PDF nativo)."""

from pathlib import Path

import pytest

from src.bp.parsers.pdf_balance_parser import PDFBalanceParser
from src.bp.parsers.dispatcher import ParseyCaller

ABT = Path("data/samples/ABT - BP 03.2024.pdf")


def test_to_float_formats():
    f = PDFBalanceParser._to_float
    assert f("1.234,56") == pytest.approx(1234.56)
    assert f("45.000") == pytest.approx(45000)
    assert f("(218.813,56)") == pytest.approx(-218813.56)
    assert f("0") == 0.0
    assert f("1,234.56") == pytest.approx(1234.56)


def test_parse_line_strips_note_refs_and_values():
    p = PDFBalanceParser("x.pdf")
    # valor real após referência de nota "1"
    assert p._parse_line("Disponibilidades 1 81.984,34") == ("Disponibilidades", pytest.approx(81984.34))
    # linha de ruído (assinatura) é descartada
    assert p._parse_line("CNPJ: 46.680.728/0001-02") is None
    # sem valor -> None
    assert p._parse_line("Ativo Circulante") is None


def test_parse_line_preserves_short_name_with_number():
    """Regressão: 'Loja 2' e 'CD 3' são nomes válidos — o dígito NÃO deve ser
    stripado por parecer nota de rodapé."""
    p = PDFBalanceParser("x.pdf")
    assert p._parse_line("Loja 2 500") == ("Loja 2", pytest.approx(500))
    assert p._parse_line("CD 3 45.000,00") == ("CD 3", pytest.approx(45000))


@pytest.mark.skipif(not ABT.exists(), reason="PDF de exemplo ausente")
def test_parses_real_balance_pdf():
    accounts = PDFBalanceParser(ABT).parse()
    descs = {a["descricao"].lower() for a in accounts}
    assert len(accounts) >= 20
    assert any("caixa" in d for d in descs)
    assert any("fornecedores" in d for d in descs)


@pytest.mark.skipif(not ABT.exists(), reason="PDF de exemplo ausente")
def test_dispatcher_routes_pdf():
    # O dispatcher passa a extrair contas de PDF (antes retornava []).
    accounts = ParseyCaller(ABT).parse()
    assert len(accounts) >= 20
