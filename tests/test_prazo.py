"""
Circulante × Não Circulante — o terceiro eixo de desambiguação.

O defeito
---------

Conferindo um arquivo que o revisor mandou, o ATIVO TOTAL batia ao centavo com
a origem e a **repartição** estava errada::

    Ativo Circulante      origem 652,56 mil   entrega 20,77 mil
    Ativo Não Circulante  origem 282.048,64   entrega 282.680,44
    ATIVO TOTAL           origem 282.701,21   entrega 282.701,21  (certo)

O total esconde: 631,79 mil de circulante entregues como não circulante. Num
outro arquivo do corpus o deslocamento era de **R$ 28,7 milhões**.

Medido antes da correção: **9 de 18** balancetes entregavam o Circulante
errado — e nenhum teste pegava, porque a conferência do §15 só olha os totais
de topo. Liquidez é metade da leitura de um balanço.

Os três eixos
-------------

===================  ======================================================
Plano C (classe)     ATIVO / PASSIVO / RESULTADO
``utils.natureza``   RECEITA / DESPESA, dentro de RESULTADO
``utils.prazo``      CIRCULANTE / NÃO CIRCULANTE, dentro de ATIVO e PASSIVO
===================  ======================================================

Referência: ``REVISAO_QUALIDADE.md`` §18.9.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from conftest import CORPUS_DIR, corpus_disponivel
from openpyxl import load_workbook

from src.bp.parsers.dispatcher import ParseyCaller
from src.bp.utils.prazo import (
    CIRCULANTE,
    NAO_CIRCULANTE,
    mapear_prazo,
    prazo_de_texto,
    prazo_do_codigo_referencial,
)
from src.bp.validators.entrega import avaliar_demonstrativo

# ============================================================================
# 1. Leitura do prazo
# ============================================================================


@pytest.mark.parametrize(
    ("descricao", "esperado"),
    [
        ("CIRCULANTE", CIRCULANTE),
        ("ATIVO CIRCULANTE", CIRCULANTE),
        ("PASSIVO CIRCULANTE", CIRCULANTE),
        # "não circulante" contém "circulante": a ordem do teste importa, e
        # inverter dá exatamente o oposto do que a conta é.
        ("NÃO CIRCULANTE", NAO_CIRCULANTE),
        ("ATIVO NÃO CIRCULANTE", NAO_CIRCULANTE),
        ("NAO CIRCULANTE", NAO_CIRCULANTE),
        ("REALIZÁVEL A LONGO PRAZO", NAO_CIRCULANTE),
        ("EXIGÍVEL A LONGO PRAZO", NAO_CIRCULANTE),
        ("ATIVO PERMANENTE", NAO_CIRCULANTE),
        ("IMOBILIZADO", NAO_CIRCULANTE),
        ("Caixa Geral", None),
        ("Aplicação Financeira - CDB", None),
        ("", None),
        (None, None),
    ],
)
def test_prazo_de_texto(descricao, esperado):
    assert prazo_de_texto(descricao) == esperado


@pytest.mark.parametrize(
    ("codigo", "esperado"),
    [
        ("1.01", CIRCULANTE),
        ("1.01.01.02", CIRCULANTE),
        ("1.02", NAO_CIRCULANTE),
        ("1.02.03.01", NAO_CIRCULANTE),
        ("2.01.01.03", CIRCULANTE),
        ("2.02.01.01", NAO_CIRCULANTE),
        # Patrimônio Líquido não tem prazo. Restringi-lo excluiria os alvos
        # certos — devolver None é o que mantém o PL alcançável.
        ("2.03.01", None),
        ("2.03.04.01", None),
        ("3.01.01.03", None),
        ("", None),
    ],
)
def test_prazo_do_codigo_referencial(codigo, esperado):
    assert prazo_do_codigo_referencial(codigo) == esperado


def test_o_ramo_decide_o_prazo_que_a_folha_nao_diz():
    """
    "Aplicação Financeira - CDB" não diz nada sozinha; o ramo diz. Foi essa
    conta que casou com Imobilizado.
    """
    contas = [
        {"codigo": "1", "descricao": "Ativo"},
        {"codigo": "1.01", "descricao": "CIRCULANTE"},
        {"codigo": "1.01.01.03", "descricao": "APLICAÇÕES FINANCEIRAS"},
        {"codigo": "1.01.01.03.01", "descricao": "Aplicação Financeira - CDB"},
        {"codigo": "1.02", "descricao": "NÃO CIRCULANTE"},
        {"codigo": "1.02.03", "descricao": "IMOBILIZADO"},
    ]
    prazos = mapear_prazo(contas)
    assert prazos["1.01.01.03.01"] == CIRCULANTE
    assert prazos["1.02.03"] == NAO_CIRCULANTE


def test_contas_de_resultado_nao_entram_no_mapa():
    """Prazo não se aplica à DRE; devolvê-lo convidaria uso errado."""
    contas = [
        {"codigo": "1.01", "descricao": "CIRCULANTE"},
        {"codigo": "3.01", "descricao": "RECEITAS"},
    ]
    assert set(mapear_prazo(contas)) == {"1.01"}


# ============================================================================
# 2. A trava, e a não-vacuidade dela
# ============================================================================


def test_trava_recusa_circulante_indo_para_nao_circulante():
    """
    Sem isto, o teste do corpus também passaria com a trava desligada — que é
    o estado em que o defeito chegou à entrega.
    """
    from src.bp.output.build_gt_output import _resolver
    from src.bp.output.template_map import ProjectionResult

    class _Decisao:
        codigo = "1.02.03.01"  # Imobilizado
        descricao = "Máquinas e equipamentos"
        score = 1.0

    class _MatcherFalso:
        natureza_referencial: dict[str, str] = {}

        def match(self, descricao, codigo_origem="", natureza_resultado=None, prazo=None):
            return type("R", (), {"decision": _Decisao(), "needs_review": False})()

    class _ProjectorFalso:
        def project(self, codigo):
            return ProjectionResult(codigo, "1.02.03.01", "direto")

    resolucao = _resolver(
        {"codigo": "1.01.01.03.01", "descricao": "Aplicação Financeira - CDB"},
        _MatcherFalso(),
        _ProjectorFalso(),
        None,
        {"1.01.01.03.01": CIRCULANTE},
    )
    assert resolucao.codigo_template is None, "circulante aceito em conta de imobilizado"
    assert "prazo incompatível" in resolucao.motivo


def test_trava_nao_recusa_projecao_de_mesmo_prazo():
    """A trava não pode virar bloqueio geral."""
    from src.bp.output.build_gt_output import _resolver
    from src.bp.output.template_map import ProjectionResult

    class _Decisao:
        codigo = "1.01.01.02"
        descricao = "Bancos conta movimento"
        score = 1.0

    class _MatcherFalso:
        natureza_referencial: dict[str, str] = {}

        def match(self, descricao, codigo_origem="", natureza_resultado=None, prazo=None):
            return type("R", (), {"decision": _Decisao(), "needs_review": False})()

    class _ProjectorFalso:
        def project(self, codigo):
            return ProjectionResult(codigo, "1.01.01.02.01", "direto")

    resolucao = _resolver(
        {"codigo": "1.01.01.02", "descricao": "BANCOS CONTA MOVIMENTO"},
        _MatcherFalso(),
        _ProjectorFalso(),
        None,
        {"1.01.01.02": CIRCULANTE},
    )
    assert resolucao.codigo_template == "1.01.01.02.01"
    assert not resolucao.motivo


# ============================================================================
# 3. A raiz de classe não pode parar o corte
# ============================================================================


def test_raiz_de_classe_nao_absorve_o_balanco_inteiro():
    """
    Um balancete real emitiu o Ativo INTEIRO — R$ 197.840.840 — numa linha só,
    casada com "Outros ativos circulantes". O total do Balanço até fechava; a
    leitura era ficção.

    Raiz de classe é totalizador, e o template calcula os totais sozinho.
    """
    from src.bp.validators.hierarquia import selecionar_para_projecao

    contas = [
        {"codigo": "1", "descricao": "ATIVO", "saldo": 300.0},
        {"codigo": "1.1", "descricao": "ATIVO CIRCULANTE", "saldo": 100.0},
        {"codigo": "1.1.01", "descricao": "CAIXA", "saldo": 100.0},
        {"codigo": "1.5", "descricao": "ATIVO NÃO CIRCULANTE", "saldo": 200.0},
        {"codigo": "1.5.01", "descricao": "IMOBILIZADO", "saldo": 200.0},
    ]
    # Só a raiz casa: antes, o corte parava nela e levava tudo numa linha.
    selecao = selecionar_para_projecao(contas, lambda c: c == "1")
    assert "1" not in selecao.codigos, (
        "o corte parou na raiz de classe — o Balanço inteiro vai para uma "
        "linha de detalhe"
    )

    # E um agrupador de verdade continua absorvendo, que é a regra certa.
    selecao = selecionar_para_projecao(contas, lambda c: c == "1.1")
    assert "1.1" in selecao.codigos


# ============================================================================
# 4. O subtotal na entrega — o teste que faltava
# ============================================================================

#: Balancetes do controle com subtotal de circulante identificável na origem.
CONTROLE = (
    "IBH 18_Balancete_06.2026.xlsx",
    "Infraestrutura Brasil III_Balancete 06.2026.xlsx",
    "Balancete_Trindade_052025.xlsx",
    "Balancete 072022 122022 - RBM.xls",
    "202404_2024 - Balancete.xls",
)


def _circulante_da_origem(contas) -> float | None:
    """O subtotal de circulante declarado pelo próprio balancete."""
    por: dict[str, tuple[str, float]] = {}
    for conta in contas:
        codigo = str(conta.get("codigo", "")).strip()
        if codigo:
            por[codigo] = (str(conta.get("descricao", "")), conta.get("saldo") or 0.0)

    total, achou = 0.0, False
    for codigo, (descricao, saldo) in por.items():
        partes = codigo.split(".")
        pai = next(
            (".".join(partes[:n]) for n in range(len(partes) - 1, 0, -1)
             if ".".join(partes[:n]) in por),
            None,
        )
        if pai == "1" and prazo_de_texto(descricao) == CIRCULANTE:
            total += saldo
            achou = True
    return total if achou else None


@pytest.mark.integration
@pytest.mark.parametrize("nome", CONTROLE)
def test_o_ativo_circulante_entregue_e_o_do_balancete(nome):
    """
    O teste do core um nível abaixo.

    O ATIVO TOTAL pode estar certo com a repartição inteira errada — ele é a
    soma. Liquidez é metade da leitura de um balanço, e era exatamente o que
    saía errado em 9 dos 18 balancetes do corpus.
    """
    from src.bp.output.build_gt_output import build_gt_output

    if not corpus_disponivel():
        pytest.skip(f"corpus ausente: {CORPUS_DIR}")
    caminho = CORPUS_DIR / nome
    if not caminho.exists():
        pytest.fail(f"controle ausente do corpus: {caminho}")

    contas = ParseyCaller(caminho).parse()
    origem = _circulante_da_origem(contas)
    if origem is None:
        pytest.skip(f"{nome}: a origem não declara subtotal de circulante")

    tmp = Path(tempfile.mkdtemp())
    resultado = build_gt_output(
        caminho, tmp / "s.xlsx", ano_base=2024, cache_path=tmp / "c.json"
    )
    if not (resultado.hierarquia and resultado.hierarquia.rollup_integro):
        pytest.skip(f"{nome}: a origem já não fecha")

    entregue = avaliar_demonstrativo(
        load_workbook(resultado.output_path), "BP_GT", "D"
    ).get("Total do Ativo Circulante", 0.0)

    esperado = abs(origem) / 1000.0
    assert abs(abs(entregue) - esperado) <= max(0.01, esperado * 0.01), (
        f"{nome}: Ativo Circulante entregue {abs(entregue):,.2f} contra "
        f"{esperado:,.2f} no balancete. O ATIVO TOTAL pode estar certo — ele é "
        f"a soma; o que está errado é a repartição."
    )
