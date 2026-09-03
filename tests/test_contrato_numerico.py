"""
Contrato de conversão numérica — uma fonte, cinco consumidores.

O projeto convertia "texto de saldo → float" em **cinco lugares independentes**
que divergiam em entradas contábeis corriqueiras. Hoje todos delegam a
``utils.numero.parse_saldo``:

======================================  =====================================
Consumidor                              Como usa
======================================  =====================================
``BaseParser._normalize_saldo``         ``parse_saldo_ou(v, 0.0)`` (shim)
``ParseyCaller._parse_accounts_from_df````parse_saldo`` — único caminho tabular
``PDFBalanceParser._to_float``          herda o mesmo algoritmo
``_primary_saldo`` (exporter)           ``parse_saldo``
``validate_parsed_accounts``            ``parse_saldo``
======================================  =====================================

Este arquivo é a trava dessa unificação: exercita cada consumidor pela sua
porta pública e exige que concordem. Se alguém reintroduzir uma conversão
própria, a divergência aparece aqui antes de chegar ao balancete.

Referência: ``REVISAO_QUALIDADE.md`` §1.
"""

from __future__ import annotations

import math

import pandas as pd
import pytest

from src.bp.exporters.xlsx_exporter import _primary_saldo
from src.bp.parsers.base_parser import BaseParser, ParseResult
from src.bp.parsers.dispatcher import ParseyCaller
from src.bp.parsers.pdf_balance_parser import PDFBalanceParser
from src.bp.utils.numero import parse_saldo, parse_saldo_ou

pytestmark = pytest.mark.contrato


# ============================================================================
# Adaptadores: cada implementação exposta pela sua porta pública real
# ============================================================================


class _ParserConcreto(BaseParser):
    """Subclasse mínima só para alcançar ``_normalize_saldo``."""

    def parse(self) -> ParseResult:  # pragma: no cover - não usado
        return ParseResult([])

    def validate(self) -> bool:  # pragma: no cover - não usado
        return True


@pytest.fixture(scope="module")
def base_parser(tmp_path_factory) -> _ParserConcreto:
    arquivo = tmp_path_factory.mktemp("num") / "vazio.txt"
    arquivo.write_text("", encoding="utf-8")
    return _ParserConcreto(arquivo)


def via_base_parser(parser: _ParserConcreto, valor):
    return parser._normalize_saldo(valor)


def _caller_com(valor) -> ParseyCaller:
    """
    Exercita o caminho de produção do dispatcher (DataFrame injetado), não uma
    reimplementação da closure — o teste continua válido se a closure for
    extraída para uma função nomeada.
    """
    caller = ParseyCaller("injetado.xlsx")
    caller.df = pd.DataFrame({"Descricao": ["CAIXA GERAL"], "Saldo": [valor]})
    return caller


def via_dispatcher_trainer(valor):
    """``ParseyCaller.parse()`` — o caminho que o **trainer** usa."""
    contas = _caller_com(valor).parse()
    return contas[0].get("saldo") if contas else None


def via_dispatcher_exporter(valor):
    """``parse_with_original()`` — o caminho que o **xlsx_exporter** usa."""
    contas, _ = _caller_com(valor).parse_with_original()
    return contas[0].get("saldo") if contas else None


def via_pdf_balance(valor):
    return PDFBalanceParser._to_float(str(valor))


def via_exporter(valor):
    return _primary_saldo({"saldo": valor})



@pytest.fixture(scope="module")
def conversores():
    """Mapa nome → conversor, para parametrizar sobre as implementações."""

    def _mapa(parser: _ParserConcreto):
        return {
            "base_parser": lambda v: via_base_parser(parser, v),
            "dispatcher_trainer": via_dispatcher_trainer,
            "dispatcher_exporter": via_dispatcher_exporter,
            "pdf_balance": via_pdf_balance,
            "exporter": via_exporter,
        }

    return _mapa


# ============================================================================
# 1. O que todas acertam — trava de não-regressão
# ============================================================================


@pytest.mark.parametrize(
    "texto,esperado",
    [
        ("1.234,56", 1234.56),  # BR canônico
        ("1.234", 1234.0),  # milhar sem decimais
        ("0,00", 0.0),
        ("R$ 1.234,56", 1234.56),  # com símbolo de moeda
    ],
)
def test_formato_br_canonico_concorda_em_todas(base_parser, texto, esperado):
    """Formato BR bem-comportado: as cinco implementações devem concordar."""
    assert via_base_parser(base_parser, texto) == pytest.approx(esperado)
    assert via_dispatcher_trainer(texto) == pytest.approx(esperado)
    assert via_dispatcher_exporter(texto) == pytest.approx(esperado)
    assert via_pdf_balance(texto) == pytest.approx(esperado)
    assert via_exporter(texto) == pytest.approx(esperado)


# ============================================================================
# 2. Os dois caminhos do dispatcher entregam o mesmo
# ============================================================================


@pytest.mark.parametrize("entrada", ["(1.234,56)", "1.234,56 C", "abc", "-", ""])
def test_dispatcher_dois_caminhos_concordam(entrada):
    """
    ``parse()`` (trainer) e ``parse_with_original()`` (exporter) tinham
    conversores próprios: o trainer via 0.0 onde o exporter via None, para o
    mesmo arquivo. Hoje ``parse()`` delega ao mesmo extrator.
    """
    assert repr(via_dispatcher_trainer(entrada)) == repr(
        via_dispatcher_exporter(entrada)
    ), (
        f"parse()={via_dispatcher_trainer(entrada)!r} vs "
        f"parse_with_original()={via_dispatcher_exporter(entrada)!r}"
    )


def test_dispatcher_dois_caminhos_concordam_no_caso_feliz():
    """Trava o que já funciona: em BR canônico os dois caminhos coincidem."""
    for entrada in ["1.234,56", "1.234", "0,00", "R$ 1.234,56"]:
        assert via_dispatcher_trainer(entrada) == pytest.approx(
            via_dispatcher_exporter(entrada)
        ), f"divergência inesperada em {entrada!r}"


# ============================================================================
# 3. Negativo entre parênteses — convenção contábil padrão
# ============================================================================


def test_pdf_balance_entende_negativo_entre_parenteses():
    """A única das cinco que acerta. É a candidata natural a fonte única."""
    assert via_pdf_balance("(1.234,56)") == pytest.approx(-1234.56)


@pytest.mark.parametrize(
    "conversor",
    ["base_parser", "dispatcher_trainer", "dispatcher_exporter", "exporter"],
)
def test_negativo_entre_parenteses(base_parser, conversor, conversores):
    assert conversores(base_parser)[conversor]("(1.234,56)") == pytest.approx(-1234.56)


# ============================================================================
# 4. Sufixo D/C (Devedor/Credor) — presente em quase todo balancete brasileiro
# ============================================================================


@pytest.mark.parametrize("texto", ["1.234,56 C", "1.234,56D", "1.234,56 d"])
def test_base_parser_e_pdf_toleram_sufixo_dc(base_parser, texto):
    """Estas duas removem o marcador D/C corretamente."""
    assert via_base_parser(base_parser, texto) == pytest.approx(1234.56)
    assert via_pdf_balance(texto) == pytest.approx(1234.56)


@pytest.mark.parametrize(
    "conversor", ["dispatcher_trainer", "dispatcher_exporter", "exporter"]
)
def test_sufixo_dc(base_parser, conversor, conversores):
    assert conversores(base_parser)[conversor]("1.234,56 C") == pytest.approx(1234.56)


# ============================================================================
# 5. Decimal com ponto — o erro de 100x mais provável em produção
# ============================================================================


def test_pdf_balance_entende_decimal_com_ponto():
    """
    Detecta o separador pelo formato (``1.234`` = milhar, ``1234.56`` =
    decimal). É a implementação a ser promovida a fonte única.
    """
    assert via_pdf_balance("1234.56") == pytest.approx(1234.56)


@pytest.mark.parametrize(
    "conversor",
    ["base_parser", "dispatcher_trainer", "dispatcher_exporter", "exporter"],
)
def test_decimal_com_ponto_nao_deve_inflar(base_parser, conversor, conversores):
    assert conversores(base_parser)[conversor]("1234.56") == pytest.approx(1234.56)


# ============================================================================
# 6. NaN — a entrada que envenena o rollup (ver test_integridade_rollup.py)
# ============================================================================


@pytest.mark.parametrize(
    "conversor",
    ["base_parser", "dispatcher_trainer", "dispatcher_exporter", "pdf_balance", "exporter"],
)
def test_nenhum_conversor_propaga_nan(base_parser, conversor, conversores):
    """
    NaN não é saldo. Nenhum dos cinco pode devolvê-lo: um único NaN numa folha
    contaminava todo o ramo do rollup, que ainda por cima o aprovava.
    """
    resultado = conversores(base_parser)[conversor](float("nan"))
    assert resultado is None or not math.isnan(resultado)


# ============================================================================
# 7. Entrada inválida: zero legítimo vs. falha de conversão
# ============================================================================


@pytest.mark.parametrize("lixo", ["abc", "", "-"])
def test_pdf_e_exporter_path_distinguem_lixo_de_zero(lixo):
    """``None`` diz "não consegui ler". ``0.0`` diz "a conta vale zero"."""
    assert via_pdf_balance(lixo) is None
    assert via_dispatcher_exporter(lixo) is None


@pytest.mark.parametrize("lixo", ["abc", "R$ ---", "saldo"])
def test_dispatcher_nao_mascara_lixo_como_zero(lixo, conversores, base_parser):
    """
    No caminho de produção, entrada ilegível vira ``None``, não ``0.0``. É essa
    distinção que permite ao validador acusar dado corrompido em vez de
    reportar uma conta zerada plausível.
    """
    assert conversores(base_parser)["dispatcher_trainer"](lixo) is None


@pytest.mark.parametrize("lixo", ["abc", "R$ ---", "saldo"])
def test_normalize_saldo_e_um_shim_de_fallback_explicito(base_parser, lixo):
    """
    ``BaseParser._normalize_saldo`` mantém o contrato antigo (``float``, 0.0
    quando ilegível) para não quebrar csv/txt/pdf_parser — mas o 0.0 agora vem
    de ``parse_saldo_ou``, uma decisão nomeada, não de um ``except`` escondido.
    A fonte devolve ``None``; o shim é que escolhe o default.
    """
    assert parse_saldo(lixo) is None
    assert via_base_parser(base_parser, lixo) == 0.0
    assert parse_saldo_ou(lixo, 0.0) == 0.0
