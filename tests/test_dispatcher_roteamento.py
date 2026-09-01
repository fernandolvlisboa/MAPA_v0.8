"""
Roteamento do ``ParseyCaller`` por extensão.

``ParseyCaller`` declara ``SUPPORTED_EXTENSIONS = (".csv", ".xlsx", ".xls",
".pdf", ".txt")`` e o trainer usa essa tupla para varrer o corpus. Toda
extensão declarada precisa ter um desvio correspondente em ``parse()``.

``.txt`` não tinha: caía no caminho genérico de DataFrame, que não acha coluna
de descrição e devolvia lista vazia. O ``TXTParser`` — 307 linhas, parser de
largura fixa que extrai 468 contas de um balancete real — **nunca era chamado
em produção**. O trainer descobria o arquivo, extraía zero contas e o marcava
como processado; nada distinguia "arquivo sem contas" de "arquivo que o
roteador não sabe abrir".

Este arquivo trava a equivalência: para toda extensão com parser
especializado, o dispatcher entrega o que o parser entrega.
Referência: ``REVISAO_QUALIDADE.md`` §3.
"""

from __future__ import annotations

import pytest

from src.bp.parsers.dispatcher import ParseyCaller
from src.bp.parsers.txt_parser import TXTParser

pytestmark = pytest.mark.contrato


@pytest.fixture(scope="module")
def contas_via_parser_direto(balancete_txt):
    """O que o parser especializado consegue extrair."""
    return TXTParser(balancete_txt).parse().contas


@pytest.fixture(scope="module")
def contas_via_dispatcher(balancete_txt):
    """O que o pipeline de produção realmente enxerga."""
    return ParseyCaller(balancete_txt).parse()


# ============================================================================
# 1. O parser especializado funciona
# ============================================================================


@pytest.mark.integration
def test_txt_parser_direto_extrai_contas(contas_via_parser_direto):
    assert len(contas_via_parser_direto) > 400, (
        f"TXTParser extraiu só {len(contas_via_parser_direto)} contas"
    )
    primeira = contas_via_parser_direto[0]
    assert primeira["descricao"], "conta sem descrição"
    assert "saldo_atual" in primeira, "TXTParser deveria trazer saldo_atual"


# ============================================================================
# 2. O dispatcher descarta o resultado
# ============================================================================


@pytest.mark.integration
def test_txt_esta_declarado_como_suportado():
    assert ".txt" in ParseyCaller.SUPPORTED_EXTENSIONS, (
        "se .txt saiu da tupla, o trainer parou de varrer .TXT — ajuste este "
        "arquivo de teste junto"
    )


@pytest.mark.integration
def test_dispatcher_roteia_txt_para_o_txt_parser(
    contas_via_dispatcher, contas_via_parser_direto
):
    assert len(contas_via_dispatcher) == len(contas_via_parser_direto), (
        f"dispatcher={len(contas_via_dispatcher)} contas vs "
        f"TXTParser={len(contas_via_parser_direto)} contas"
    )


@pytest.mark.integration
def test_txt_sai_no_contrato_do_registro(contas_via_dispatcher):
    """
    Rotear não basta: o ``TXTParser`` fala ``creditos``/``debitos``/
    ``classificacao`` e não emite ``saldo``. Sem a normalização na fronteira
    do dispatcher, as 468 contas chegavam ao exporter e à entrega com valor
    zero. Ver ``parsers/registro.py``.
    """
    raiz, filha = contas_via_dispatcher[0], contas_via_dispatcher[1]

    # `codigo` passa a ser o hierárquico ("1", "1.1"), não o interno ("1000").
    assert raiz["codigo"] == "1"
    assert filha["codigo"] == "1.1"
    assert filha["codigo_interno"] == "1001", "o código da origem foi perdido"
    assert (raiz["nivel"], filha["nivel"]) == (1, 2)

    for conta in (raiz, filha):
        assert conta["saldo"] is not None, "saldo não foi derivado de saldo_atual"
        assert conta["saldo"] == conta["saldo_atual"]
        for campo in ("creditos", "debitos", "classificacao"):
            assert campo not in conta, f"vocabulário do TXTParser vazou: {campo}"


# ============================================================================
# 3. CSV: mesma pergunta, resposta diferente — o desvio existe
# ============================================================================


@pytest.mark.integration
def test_csv_tem_desvio_dedicado_no_dispatcher(balancete_csv):
    """
    O ``.csv`` tem desvio (delega ao ``CSVParser``), então dispatcher e parser
    direto concordam — inclusive quando ambos devolvem zero. Trava a
    equivalência: é ela que falta ao ``.txt``.
    """
    from src.bp.parsers.csv_parser import CSVParser

    via_dispatcher = ParseyCaller(balancete_csv).parse()
    parser = CSVParser(balancete_csv)
    via_direto = parser.parse().contas if parser.validate() else []
    assert len(via_dispatcher) == len(via_direto)


@pytest.mark.integration
@pytest.mark.xfail(
    strict=True,
    reason="DEGRADAÇÃO 3c: o CSVParser devolve 0 contas para um balancete "
    "real de 61 KB com separador ';' e preâmbulo de cabeçalho. O desvio de "
    "roteamento existe, mas o parser não reconhece o layout. Cobertura do "
    "csv_parser é de 51% — nenhum teste exercita um CSV real. "
    "Ver REVISAO_QUALIDADE.md §3.",
)
def test_csv_real_deveria_render_contas(balancete_csv):
    contas = ParseyCaller(balancete_csv).parse()
    assert len(contas) > 50, f"CSV real rendeu {len(contas)} contas"


# ============================================================================
# 4. Sinal das contas redutoras no .TXT
# ============================================================================


@pytest.mark.integration
@pytest.mark.xfail(
    strict=True,
    reason="DEGRADAÇÃO 9a: o TXTParser perde o sinal das contas redutoras. "
    "Em 2019-01.TXT, '(-) DEPRECIACOES' vem +32.419.395,76; com o sinal certo "
    "a soma dos filhos de 1.2.03 IMOBILIZADO dá exatamente os 48.257.635,28 "
    "declarados pelo pai. São 17 agrupadores divergentes por essa causa. "
    "Achado pela conferência hierárquica. Ver REVISAO_QUALIDADE.md §9.",
)
def test_txt_preserva_o_sinal_das_contas_redutoras(balancete_txt):
    from src.bp.validators.hierarquia import conferir_hierarquia

    relatorio = conferir_hierarquia(ParseyCaller(balancete_txt).parse())
    assert relatorio.tem_hierarquia, "sem árvore, o teste seria vacuoso"
    assert relatorio.rollup_integro, (
        f"{relatorio.pais_divergentes} agrupadores divergem: "
        + "; ".join(str(d) for d in relatorio.divergencias[:2])
    )
