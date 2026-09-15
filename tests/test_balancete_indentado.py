"""
Balancete indentado: a hierarquia mora na coluna da descrição (§27).

O formato é comum no Brasil — muito sistema exporta o balancete sem código
hierárquico, mostrando a árvore pela indentação: a descrição fica numa coluna
mais à direita conforme a profundidade. Antes, esses arquivos caíam em "SEM
HIERARQUIA" e a entrega saía sem ser conferida (§26).

A reconstrução numera a árvore por outline e SÓ é aceita se o rollup fechar —
a mesma régua do resto da suíte: rollup fechando é prova de extração correta.
"""

from __future__ import annotations

import pandas as pd
import pytest
from conftest import require_corpus_file

from src.bp.parsers.dispatcher import ParseyCaller
from src.bp.parsers.indentado import _e_valor, reconstruir_de_grade
from src.bp.validators.hierarquia import conferir_hierarquia

# ============================================================================
# 1. O defeito exato: nome com dígito NÃO é valor
# ============================================================================


@pytest.mark.parametrize(
    ("celula", "e_valor"),
    [
        ("BS2 EMPRESAS", False),   # sumia inteira: parse_saldo extraía o "2"
        ("C6 BANK", False),
        ("B2W", False),
        ("ITAÚ", False),
        ("3 CORAÇÕES", False),
        ("1.234,56", True),
        ("-191,72", True),
        ("0", True),
        ("1000", True),
        (1820.20, True),
        ("", False),
    ],
)
def test_valor_nao_tem_letra(celula, e_valor):
    """
    A distinção descrição-valor tem de ser rígida.

    ``parse_saldo`` é frouxo de propósito para ler "R$ 1.820,20"; mas isso faz
    ``parse_saldo("BS2 EMPRESAS")`` devolver ``2.0``. Usá-lo para decidir "é
    valor?" apagava a conta "BS2 EMPRESAS" (1.820,20) do Real Life, e o rollup
    do pai deixava de fechar por esse exato valor. Valor não tem letra.
    """
    assert _e_valor(celula) is e_valor


# ============================================================================
# 2. A reconstrução, sobre uma grade sintética
# ============================================================================


def _grade_indentada() -> pd.DataFrame:
    """
    Uma grade no formato Real Life: código-numeração na col 0, descrição
    migrando pelas colunas por profundidade, valores em colunas fixas à direita.
    O pai vale a soma dos filhos — para o rollup poder fechar.
    """
    # Colunas: 0 numeração | 2..6 descrição por profundidade | 8 Débito |
    # 9 Crédito | 10 Saldo Atual. O cabeçalho precisa de saldo E movimento.
    linhas = [
        [None, None, None, "Código", None, "Descrição", None, None, "Débito", "Crédito", "Saldo Atual"],
        [1, None, "ATIVO", None, None, None, None, None, 0, 0, 300.0],          # nível 0 (col 2)
        [2, None, None, "CIRCULANTE", None, None, None, None, 0, 0, 300.0],     # nível 1 (col 3)
        [3, None, None, None, "DISPONÍVEL", None, None, None, 0, 0, 300.0],     # nível 2 (col 4)
        [4, None, None, None, None, "CAIXA", None, None, 0, 0, 100.0],          # nível 3 (col 5)
        [5, None, None, None, None, "C6 BANK", None, None, 0, 0, 200.0],        # nível 3, nome com dígito
        [6, None, "PASSIVO", None, None, None, None, None, 0, 0, -300.0],       # nível 0
        [7, None, None, "CIRCULANTE PASSIVO", None, None, None, None, 0, 0, -300.0],
        [8, None, None, None, "FORNECEDORES", None, None, None, 0, 0, -300.0],
    ]
    return pd.DataFrame(linhas)


def test_reconstroi_e_o_rollup_fecha():
    registros = reconstruir_de_grade(_grade_indentada())
    assert registros is not None
    codigos = [r["codigo"] for r in registros]
    assert codigos[:4] == ["1", "1.1", "1.1.1", "1.1.1.1"]

    # C6 BANK (nome com dígito) tem de estar presente, como irmão de CAIXA.
    descr = {r["descricao"]: r["codigo"] for r in registros}
    assert "C6 BANK" in descr, "conta com dígito no nome foi descartada de novo"
    assert descr["C6 BANK"] == "1.1.1.2"

    relatorio = conferir_hierarquia(registros)
    assert relatorio.rollup_integro, relatorio.resumo()


def test_grade_sem_indentacao_nao_e_reconstruida():
    """
    Não-vacuidade: uma grade comum (descrição numa coluna só) não vira árvore
    indentada — a banda tem um nível só, abaixo do mínimo.
    """
    df = pd.DataFrame([
        [None, "Conta", "Descrição", "Saldo Atual", "Débito", "Crédito"],
        ["1.01", "Caixa", "Caixa", 100.0, 0, 0],
        ["1.02", "Bancos", "Bancos", 200.0, 0, 0],
    ])
    assert reconstruir_de_grade(df) is None


# ============================================================================
# 3. Ponta a ponta, sobre o arquivo real
# ============================================================================


@pytest.mark.parametrize("nome", ["Balancete Real Life.xlsx", "Balancete Real Life.xls"])
def test_real_life_passa_a_conferir(nome):
    """
    O balancete que saía com 96 linhas e ZERO conferência agora fecha.

    A invariante, sem cravar conta nenhuma: o arquivo é lido COM árvore e o
    rollup fecha. É a diferença entre entregar sem garantia e entregar conferido.
    """
    caminho = require_corpus_file(nome)
    contas = ParseyCaller(str(caminho)).parse()
    relatorio = conferir_hierarquia(contas)
    assert relatorio.tem_hierarquia, (
        f"{nome}: continuou SEM HIERARQUIA — a reconstrução por indentação não "
        "disparou"
    )
    assert relatorio.rollup_integro, relatorio.resumo()


def test_fallback_nao_altera_balancete_ja_hierarquico():
    """
    A trava que impede a heurística de estragar o que já funciona.

    Um balancete com código hierárquico de verdade (SPEZZIA) NÃO pode passar
    pela reconstrução por indentação — ela só roda quando não há árvore.
    """
    caminho = require_corpus_file("Balancete SPEZZIA TUBOS 01012024-31122024.xls")
    contas = ParseyCaller(str(caminho)).parse()
    # Códigos hierárquicos reais têm ponto; a reconstrução geraria "1.1.1" a
    # partir do zero, mas o SPEZZIA tem códigos como "1.1.01.02" — os originais.
    assert any("." in str(c["codigo"]) for c in contas)
    relatorio = conferir_hierarquia(contas)
    assert relatorio.tem_hierarquia and relatorio.pais_conferidos > 50
