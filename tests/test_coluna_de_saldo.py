"""
A coluna de saldo: escolher a errada é ficar sem balancete — e sem aviso.

O achado
--------

A pasta de trabalho de um cliente (SmartRio, sete exercícios em sete abas)
expôs dois modos de a escolha da coluna de valor dar errado, e um terceiro
defeito que fazia os dois passarem despercebidos.

1. **Coluna quase vazia.** A aba ``Balancetes 2025`` termina em duas colunas
   de sobra à direita do último mês: uma vazia e outra com **3 valores em 825
   linhas**. O critério era "a última coluna numérica" — e era essa. Resultado:
   821 das 824 contas chegavam com ``saldo=None``.

2. **Coluna constante.** A aba ``Balancetes 2021`` traz uma coluna auxiliar com
   ``100`` em todas as linhas. Sendo a última numérica, virava o saldo de
   **todas** as 513 contas.

3. **O verde vazio.** Nenhum dos dois aparecia em métrica alguma, porque
   ``_saldo`` devolve ``0.0`` para saldo ilegível: com tudo ``None``, todo pai
   bate com a soma dos filhos (0 == 0) e a equação contábil fecha (0 == 0). O
   relatório de 2025 dizia, literalmente, "184 pais conferem, equação contábil
   fecha" sobre um balancete em que **nada** tinha sido lido.

Medido depois da correção, na mesma aba de 2021: de 62 pais conferindo e 74
divergindo para 136 conferindo, 0 divergindo, equação fechando.

Referência: ``REVISAO_QUALIDADE.md`` §21.
"""

from __future__ import annotations

import pandas as pd
import pytest
from conftest import require_corpus_file

from src.bp.parsers.abas import listar_abas
from src.bp.parsers.dispatcher import ParseyCaller
from src.bp.validators.hierarquia import conferir_hierarquia


def _df(**colunas: list) -> pd.DataFrame:
    return pd.DataFrame(colunas)


def _escolher(df: pd.DataFrame) -> str | None:
    return ParseyCaller.__new__(ParseyCaller)._find_saldo_column(df)


# ============================================================================
# 1. A coluna de sobra não é o saldo
# ============================================================================


def test_coluna_quase_vazia_nao_e_saldo():
    """
    Três valores em oitenta linhas não é uma coluna de saldo.

    É a forma exata da aba ``Balancetes 2025``: colunas-fantasma à direita do
    último mês, com um resto de conteúdo que o critério "última coluna
    numérica" tomava por valor.
    """
    n = 80
    df = _df(
        codigo=[f"1.01.{i:03d}" for i in range(n)],
        descricao=[f"Conta {i}" for i in range(n)],
        dezembro=[float(i * 1000 + 7) for i in range(n)],
        sobra=[123.0, 456.0, 789.0] + [None] * (n - 3),
    )
    assert _escolher(df) == "dezembro", (
        "escolheu a coluna de sobra: é o defeito que deixava 821 de 824 contas "
        "com saldo=None"
    )


def test_coluna_constante_nao_e_saldo():
    """
    Nenhum balancete real tem o mesmo saldo repetido em centenas de contas.

    A aba ``Balancetes 2021`` traz uma coluna auxiliar com ``100`` em todas as
    linhas — e era ela que virava o saldo de todas as 513 contas.
    """
    n = 60
    df = _df(
        codigo=[f"1.01.{i:03d}" for i in range(n)],
        descricao=[f"Conta {i}" for i in range(n)],
        dezembro=[float(i * 1000 + 7) for i in range(n)],
        auxiliar=[100.0] * n,
    )
    assert _escolher(df) == "dezembro", (
        "escolheu a coluna constante: todas as contas ficariam com o mesmo saldo"
    )


def test_coluna_de_valor_legitima_continua_sendo_escolhida():
    """
    Não-vacuidade: a guarda recusa coluna degenerada, não coluna com zeros.

    Balancete real tem conta zerada às pencas; o que ele não tem é coluna com
    **um único** valor distinto. Aqui há dois — 0 e o resto —, e a coluna vale.
    """
    n = 40
    df = _df(
        codigo=[f"2.01.{i:03d}" for i in range(n)],
        descricao=[f"Conta {i}" for i in range(n)],
        saldo_final=[0.0] * (n - 4) + [10.0, 20.0, 30.0, 40.0],
    )
    assert _escolher(df) == "saldo_final"


def test_sem_coluna_util_devolve_a_ultima_numerica():
    """
    A guarda estreita a escolha; não pode zerá-la.

    Se **nenhuma** coluna numérica passa no filtro, o comportamento anterior
    volta — melhor um saldo duvidoso que nenhum, e a não-vacuidade do relatório
    (abaixo) é que denuncia o caso.
    """
    df = _df(
        codigo=["1.01", "1.02", "1.03"],
        descricao=["a", "b", "c"],
        unica=[5.0, 5.0, 5.0],
    )
    assert _escolher(df) == "unica"


# ============================================================================
# 2. Sem saldo lido, nada aqui é conferência
# ============================================================================


def _arvore(saldos: list[float | None]) -> list[dict]:
    contas = [
        ("1", "ATIVO"),
        ("1.01", "ATIVO CIRCULANTE"),
        ("1.01.01", "Caixa geral"),
        ("1.01.02", "Bancos conta movimento"),
        ("1.01.03", "Aplicações financeiras"),
    ]
    return [
        {"codigo": c, "descricao": d, "saldo": s}
        for (c, d), s in zip(contas, saldos, strict=True)
    ]


def test_relatorio_nao_fica_verde_sem_saldo_nenhum():
    """
    O verde vazio, na sua forma pura.

    Com todo saldo ilegível, ``_saldo`` devolve ``0.0`` e **todo** pai confere
    com a soma dos filhos. Era o que o relatório da aba ``Balancetes 2024``
    dizia sobre 773 contas de 774 sem valor: "184 pais conferem, 2 divergem,
    equação contábil fecha".
    """
    r = conferir_hierarquia(_arvore([None] * 5))
    assert r.pais_conferidos > 0, "o teste seria vacuoso: não há pai conferindo"
    assert not r.saldos_legiveis
    assert not r.rollup_integro, "rollup íntegro sobre balancete sem saldo"
    assert not r.equacao_fecha, "equação fechando sobre balancete sem saldo"
    assert "SEM SALDO LEGÍVEL" in r.resumo()


def test_relatorio_continua_verde_quando_ha_saldo():
    """Não-vacuidade: a guarda não pode reprovar balancete legítimo."""
    r = conferir_hierarquia(_arvore([60.0, 60.0, 10.0, 20.0, 30.0]))
    assert r.saldos_legiveis
    assert r.rollup_integro
    assert r.pais_conferidos == 2


def test_saldo_zero_e_saldo_lido():
    """
    Zero é valor; ``None`` é ausência.

    A distinção importa: um balancete de abertura tem contas zeradas, e ele não
    pode cair na guarda de não-vacuidade.
    """
    r = conferir_hierarquia(_arvore([0.0] * 5))
    assert r.saldos_legiveis
    assert r.rollup_integro


def test_metade_lida_ainda_vale():
    """
    A fronteira é folgada de propósito: separa "quase tudo lido" de "quase nada
    lido", não persegue conta faltante.
    """
    r = conferir_hierarquia(_arvore([60.0, 60.0, 60.0, None, None]))
    assert r.saldos_legiveis
    r_pouco = conferir_hierarquia(_arvore([60.0, 60.0, None, None, None]))
    assert not r_pouco.saldos_legiveis


# ============================================================================
# 3. O arquivo que expôs os três defeitos
# ============================================================================


#: A pasta de trabalho com sete exercícios em sete abas. Cada aba é um
#: balancete completo, e as três de baixo eram as que caíam nos defeitos.
_SMARTRIO = "SmartRio Balancetes (2020 2026).xlsx"


@pytest.mark.parametrize("aba", ["Balancetes 2021", "Balancetes 2024", "Balancetes 2025"])
def test_abas_do_smartrio_chegam_com_saldo(aba):
    """
    A invariante, sem asserção sobre conta nenhuma: o balancete tem valor.

    Antes: 2021 com um único saldo distinto (``100``) em 513 contas; 2024 com
    773 de 774 em ``None``; 2025 com 821 de 824. Nenhum dos três aparecia em
    métrica alguma — todos os relatórios estavam verdes.
    """
    caminho = require_corpus_file(_SMARTRIO)
    contas = ParseyCaller(str(caminho), aba=aba).parse()
    assert len(contas) > 200, "a aba nem foi lida — o teste seria vacuoso"

    relatorio = conferir_hierarquia(contas)
    assert relatorio.saldos_legiveis, (
        f"{aba}: só {relatorio.contas_com_saldo} de {relatorio.total_contas} "
        f"contas trouxeram saldo — a coluna de valor escolhida não é a certa"
    )
    distintos = {c["saldo"] for c in contas if c["saldo"] is not None}
    assert len(distintos) > 50, (
        f"{aba}: {len(distintos)} saldo(s) distinto(s) em {len(contas)} contas "
        f"— sinal de coluna constante ou quase vazia"
    )


def test_aba_de_2021_fecha_o_rollup():
    """
    O caso que o cliente mandou olhar, com o número medido.

    Com a coluna auxiliar de ``100`` no lugar do saldo: 62 pais conferindo, 74
    divergindo. Com a coluna de dezembro: 136 conferindo, 0 divergindo, e a
    equação contábil fechando.
    """
    caminho = require_corpus_file(_SMARTRIO)
    contas = ParseyCaller(str(caminho), aba="Balancetes 2021").parse()
    relatorio = conferir_hierarquia(contas)
    assert relatorio.tem_hierarquia
    assert relatorio.rollup_integro, relatorio.resumo()
    assert relatorio.equacao_fecha, relatorio.resumo()


def test_todas_as_abas_de_balancete_do_smartrio_tem_saldo():
    """
    A varredura, para o defeito não voltar por uma aba que ninguém olhou.

    Só as abas que o próprio programa reconhece como balancete — o critério é o
    da seleção de abas, não uma lista escrita à mão que envelhece.
    """
    caminho = require_corpus_file(_SMARTRIO)
    candidatas = [a for a in listar_abas(str(caminho)) if a.tem_hierarquia]
    assert len(candidatas) >= 5, (
        "a varredura achou menos de cinco balancetes — ou o arquivo mudou, ou a "
        f"rotulagem das abas regrediu: {[(a.nome, a.rotulo_do_tipo) for a in listar_abas(str(caminho))]}"
    )
    for aba in candidatas:
        relatorio = conferir_hierarquia(
            ParseyCaller(str(caminho), aba=aba.nome).parse()
        )
        assert relatorio.saldos_legiveis, (
            f"{aba.nome}: {relatorio.contas_com_saldo} de "
            f"{relatorio.total_contas} contas com saldo"
        )
