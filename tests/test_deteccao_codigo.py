"""
Detecção da coluna de código — o defeito que o harness de corpus não pegou.

A lição
-------
O harness (``test_corpus_regressao.py``) media *quantos arquivos TÊM
hierarquia*. Nunca mediu *quantos PERDEM a hierarquia que têm*. Um balancete
cuja coluna de código não é reconhecida passa como "sem hierarquia" —
**indistinguível** de um que genuinamente não tem código. Verde, e errado.

Foi assim que um balancete real com a coluna chamada ``"Conta contábil"``
atravessou tudo. A lista de nomes candidatos era
``["código", "codigo", "cod", "class"]``; "conta" não estava lá.

A cascata que isso provocou:

1. sem código, ``codigo = descricao`` (fallback description-first);
2. ``classe_from_codigo("ALUGUEIS")`` devolve ``None`` → **Plano C desligado**;
3. ``conferir_hierarquia`` reporta "SEM HIERARQUIA" → **nenhuma conferência**;
4. ``selecionar_para_projecao`` não roda → **pai e filhos emitidos juntos**;
5. matching vira texto puro → "Aluguel e Condominio **a pagar**" (passivo)
   casa com "Condomínio" (despesa), com score 1.0.

Conta de resultado no balanço, valor duplicado, e nenhum aviso.

A correção
----------
Nome de coluna virou dica, não prova. Quem decide é o **conteúdo**: a
proporção de códigos com 3+ segmentos (``1.1.1``), forma que nenhuma coluna
de saldo tem. Medido: no arquivo que expôs o defeito, a coluna certa marcou
29,4% e todas as outras 0,0%.

Referência: ``REVISAO_QUALIDADE.md`` §12.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.bp.parsers.dispatcher import ParseyCaller
from src.bp.utils.paths import samples_dir
from src.bp.validators.hierarquia import conferir_hierarquia

pytestmark = pytest.mark.contrato

CORPUS = samples_dir()


def _caller_com(df: pd.DataFrame) -> ParseyCaller:
    caller = ParseyCaller("injetado.xlsx")
    caller.df = df
    return caller


# ============================================================================
# 1. O nome da coluna não pode ser o que decide
# ============================================================================


@pytest.mark.parametrize(
    "nome_da_coluna",
    [
        "Conta contábil",  # o que expôs o defeito
        "Classificação",  # o que já funcionava
        "Código",
        "Cta",
        "Nº da conta",
        "conta_contabil",
        "Coluna Sem Nome Útil",  # nome que não ajuda em nada
    ],
)
def test_acha_a_coluna_de_codigo_seja_qual_for_o_nome(nome_da_coluna):
    """
    Sete nomes diferentes, o mesmo conteúdo. Todos têm de ser reconhecidos —
    é o conteúdo que prova, não o rótulo.
    """
    df = pd.DataFrame(
        {
            nome_da_coluna: ["1", "1.1", "1.1.01", "1.1.01.001", "1.1.02"],
            "Descrição da Conta": ["ATIVO", "CIRC", "CAIXA", "Caixa Geral", "BANCOS"],
            "Saldo Atual": [100.0, 100.0, 40.0, 40.0, 60.0],
        }
    )
    caller = _caller_com(df)
    assert caller._find_codigo_column(df) == nome_da_coluna


def test_nao_confunde_coluna_de_saldo_com_codigo():
    """
    Valores decimais (``364.58``) parecem código de 2 segmentos. O
    discriminante são os 3+ segmentos, que decimal nunca tem.
    """
    df = pd.DataFrame(
        {
            "Classificação": ["1.1.01", "1.1.02", "1.1.03"],
            "Descrição": ["CAIXA", "BANCOS", "CLIENTES"],
            "Saldo anterior": ["364.58", "1234.56", "99.01"],
            "Saldo Atual": ["72.86", "560.49", "12.30"],
        }
    )
    assert _caller_com(df)._find_codigo_column(df) == "Classificação"


def test_sem_coluna_de_codigo_devolve_none():
    """Description-first continua valendo quando não HÁ código."""
    df = pd.DataFrame(
        {
            "Descrição": ["CAIXA GERAL", "BANCOS"],
            "Saldo": [10.0, 20.0],
        }
    )
    assert _caller_com(df)._find_codigo_column(df) is None


# ============================================================================
# 2. Esquema misto: sintética pontilhada + analítica plana indentada
# ============================================================================


def test_folha_indentada_pendura_na_sintetica_acima():
    """
    Balancete real alterna dois esquemas na mesma coluna: sintéticas com
    código hierárquico alinhado à esquerda, analíticas com código interno
    plano **indentado à direita**. A filiação está na posição.

    Sem isso, cada analítica virava uma raiz — e como os sintéticos também
    eram raízes, todo valor entrava duas vezes.
    """
    df = pd.DataFrame(
        {
            "Conta contábil": [
                "1                 ",
                "1.1               ",
                "1.1.1.01.001      ",
                "             11111",
                "1.1.1.02.002      ",
                "             11121",
            ],
            "Descrição da Conta": [
                "ATIVO",
                "CIRCULANTE",
                "CAIXA",
                "Caixa Geral",
                "BANCOS CONTA MOVIMENTO",
                "Banco Bradesco",
            ],
            "Saldo Atual": [100.0, 100.0, 40.0, 40.0, 60.0, 60.0],
        }
    )
    contas = _caller_com(df).parse()
    por_desc = {c["descricao"]: c for c in contas}

    assert por_desc["Caixa Geral"]["codigo"] == "1.1.1.01.001.11111"
    assert por_desc["Caixa Geral"]["codigo_interno"] == "11111"
    assert por_desc["Banco Bradesco"]["codigo"] == "1.1.1.02.002.11121"


def test_folha_sintetizada_nao_vira_mae_da_seguinte():
    """
    Só um código que veio hierárquico DA ORIGEM pode ser pai. Um código
    sintetizado não — senão cada folha vira mãe da próxima e a árvore
    degenera numa lista encadeada (medido: 102 divergências onde deveria
    haver zero).
    """
    df = pd.DataFrame(
        {
            "Conta contábil": [
                "1.1.2.01.007      ",
                "             11271",
                "             11273",
                "             11276",
            ],
            "Descrição da Conta": [
                "ADIANTAMENTOS",
                "Adiantamento de Salarios",
                "Adiantamento de Ferias",
                "Adiantamento a Socios",
            ],
            "Saldo Atual": [100.0, 0.0, 0.0, 100.0],
        }
    )
    contas = _caller_com(df).parse()
    codigos = {c["descricao"]: c["codigo"] for c in contas}

    # Todas as três folhas penduram no MESMO pai.
    assert codigos["Adiantamento de Salarios"] == "1.1.2.01.007.11271"
    assert codigos["Adiantamento de Ferias"] == "1.1.2.01.007.11273"
    assert codigos["Adiantamento a Socios"] == "1.1.2.01.007.11276"


# ============================================================================
# 3. A trava que faltava: perder hierarquia que existe é DEFEITO
# ============================================================================


def _tem_coluna_de_codigo_na_origem(caminho) -> bool:
    """A planilha traz uma coluna com códigos hierárquicos de 3+ segmentos?"""
    df = ParseyCaller(caminho).read()
    if df is None or df.empty:
        return False
    for col in df.columns:
        amostra = df[col].dropna().astype(str).str.strip()
        if len(amostra) == 0:
            continue
        casam = sum(
            1 for v in amostra if ParseyCaller._TRES_SEGMENTOS_RE.match(v)
        )
        if casam / len(amostra) >= 0.10:
            return True
    return False


@pytest.mark.integration
def test_nenhum_balancete_perde_a_hierarquia_que_tem():
    """
    **O teste que faltava.** Para todo arquivo do corpus que TEM código
    hierárquico na origem, o pipeline precisa reconhecê-lo.

    O harness antigo media "quantos têm hierarquia" — um arquivo cuja coluna
    não fosse reconhecida caía silenciosamente na categoria "sem hierarquia",
    indistinguível de um que genuinamente não tem. Verde, e errado.
    """
    if not CORPUS.exists():
        pytest.skip(f"corpus ausente: {CORPUS}")

    perdidos = []
    for caminho in sorted(CORPUS.iterdir()):
        if caminho.suffix.lower() not in {".xls", ".xlsx", ".csv"}:
            continue
        try:
            if not _tem_coluna_de_codigo_na_origem(caminho):
                continue  # genuinamente sem código: não é defeito
            relatorio = conferir_hierarquia(ParseyCaller(caminho).parse())
            if not relatorio.tem_hierarquia:
                perdidos.append(caminho.name)
        except Exception:
            continue

    assert not perdidos, (
        "estes balancetes TÊM código hierárquico na origem e o pipeline não "
        f"reconheceu — Plano C desligado, rollup inerte: {perdidos}"
    )
