"""
Integridade do rollup hierárquico e da validação de saída.

O rollup é a única checagem aritmética do sistema: soma os filhos diretos e
compara com o saldo declarado do pai. É o que a aba ``Validation`` e a métrica
``Rollup Discrepancies`` do ``Summary`` reportam ao usuário final.

Por isso a falha mais cara possível não é o rollup errar — é ele **dizer que
está certo quando os dados estão corrompidos**. Era o que acontecia com ``NaN``:

- ``_primary_saldo`` devolvia ``NaN`` (``float(nan)`` não levanta);
- ``soma += NaN`` propagava ``NaN`` para o pai e todos os ancestrais;
- ``abs(NaN) > TOLERANCIA`` é ``False`` em Python, logo
  ``rollup_ok = not (False and ...) = True``.

Hoje ``parse_saldo`` recusa não-finitos na entrada e ``_saldo_ilegivel``
marca a conta — própria ou de qualquer filho — cujo campo de saldo existe mas
não pôde ser lido. Esse ramo sai com ``rollup_ok=False`` e ``rollup_motivo``.

Este arquivo é a trava dessa blindagem.
Referência: ``REVISAO_QUALIDADE.md`` §2.
"""

from __future__ import annotations

import math

import pytest

from src.bp.exporters.xlsx_exporter import _compute_rollups, _primary_saldo
from src.bp.validators.export_schema import (
    validate_parsed_accounts,
    validate_matched_accounts,
)

pytestmark = pytest.mark.contrato

NAN = float("nan")


def _arvore(saldo_bancos):
    """
    Árvore mínima de 4 contas:

        1        ATIVO
        └ 1.1    CIRCULANTE   (pai dos dois abaixo)
          ├ 1.1.01  CAIXA   = 100
          └ 1.1.02  BANCOS  = <parâmetro>
    """
    return {
        "1": {"codigo": "1", "descricao": "ATIVO", "saldo": 0.0, "parent_id": None},
        "1.1": {
            "codigo": "1.1",
            "descricao": "CIRCULANTE",
            "saldo": 0.0,
            "parent_id": "1",
        },
        "1.1.01": {
            "codigo": "1.1.01",
            "descricao": "CAIXA",
            "saldo": 100.0,
            "parent_id": "1.1",
        },
        "1.1.02": {
            "codigo": "1.1.02",
            "descricao": "BANCOS",
            "saldo": saldo_bancos,
            "parent_id": "1.1",
        },
    }


# ============================================================================
# 1. O rollup funciona nos dados bem-comportados — trava de não-regressão
# ============================================================================


def test_rollup_soma_filhos_diretos():
    index = _arvore(250.0)
    _compute_rollups(index)
    assert index["1.1"]["saldo_calculado"] == pytest.approx(350.0)
    assert index["1.1.01"]["saldo_calculado"] == pytest.approx(100.0), (
        "conta-folha deve reportar o próprio saldo"
    )


def test_rollup_sinaliza_discrepancia_real():
    """Pai declara 999 mas os filhos somam 350: tem de acusar."""
    index = _arvore(250.0)
    index["1.1"]["saldo"] = 999.0
    _compute_rollups(index)
    assert index["1.1"]["rollup_ok"] is False
    assert index["1.1"]["rollup_diff"] == pytest.approx(999.0 - 350.0)


def test_rollup_aceita_diferenca_dentro_da_tolerancia():
    index = _arvore(250.0)
    index["1.1"]["saldo"] = 350.001
    _compute_rollups(index)
    assert index["1.1"]["rollup_ok"] is True


# ============================================================================
# 2. NaN — o furo que faz a validação mentir
# ============================================================================


def test_nan_nao_contamina_os_ancestrais():
    """Um NaN numa folha não pode virar NaN no total do pai."""
    index = _arvore(NAN)
    _compute_rollups(index)
    assert not math.isnan(index["1.1"]["saldo_calculado"])
    assert not math.isnan(index["1.1"]["rollup_diff"])


def test_rollup_reprova_pai_de_conta_com_nan():
    index = _arvore(NAN)
    _compute_rollups(index)
    assert index["1.1"]["rollup_ok"] is False, (
        "pai com filho de saldo ilegível foi aprovado pela validação"
    )
    assert "ilegível" in index["1.1"]["rollup_motivo"]


def test_rollup_reprova_a_propria_conta_com_nan():
    index = _arvore(NAN)
    _compute_rollups(index)
    assert index["1.1.02"]["rollup_ok"] is False


def test_primary_saldo_nao_devolve_nan():
    resultado = _primary_saldo({"saldo": NAN})
    assert not math.isnan(resultado)


# ============================================================================
# 3. O validador de schema também deixa NaN passar
# ============================================================================


def test_validador_rejeita_saldo_nao_numerico():
    """Trava o que já funciona: uma lista como saldo é recusada."""
    resultado = validate_parsed_accounts(
        [{"codigo": "1.1.01", "descricao": "CAIXA", "saldo": [1, 2], "nivel": 3}]
    )
    assert resultado.valid is False
    assert any("invalid saldo" in e for e in resultado.errors)


@pytest.mark.parametrize("valor", [NAN, float("inf"), "nan", "Infinity"])
def test_validador_rejeita_nan_e_infinito(valor):
    resultado = validate_parsed_accounts(
        [{"codigo": "1.1.01", "descricao": "CAIXA", "saldo": valor, "nivel": 3}]
    )
    assert resultado.valid is False, f"{valor!r} passou como saldo válido"


def test_metrica_avg_saldo_nao_vira_nan():
    resultado = validate_parsed_accounts(
        [
            {"codigo": "1.1.01", "descricao": "CAIXA", "saldo": 100.0, "nivel": 3},
            {"codigo": "1.1.02", "descricao": "BANCOS", "saldo": NAN, "nivel": 3},
        ]
    )
    assert not math.isnan(resultado.metrics["avg_saldo"])


# ============================================================================
# 4. O índice do exporter não pode perder conta homônima
# ============================================================================


def test_exporter_funde_codigos_homonimos_em_vez_de_descartar():
    """
    ``index[codigo] = conta`` era last-write-wins. Código repetido é normal em
    balancete real — no RBM, ``2.1.1.01.0010`` cobre duas contas distintas e
    nove códigos se repetem, o que descartava onze contas em silêncio.
    """
    from src.bp.exporters.xlsx_exporter import _build_hierarchy

    index = _build_hierarchy(
        [
            {"codigo": "2.1.1.01", "descricao": "EMPRÉSTIMOS", "saldo": -300.0},
            {"codigo": "2.1.1.01.0010", "descricao": "SANTANDER", "saldo": -200.0},
            {"codigo": "2.1.1.01.0010", "descricao": "JUROS", "saldo": -100.0},
        ]
    )
    assert index["2.1.1.01.0010"]["saldo"] == pytest.approx(-300.0), (
        "a homônima foi descartada em vez de somada"
    )
    assert index["2.1.1.01.0010"]["codigos_homonimos"] == 2

    _compute_rollups(index)
    assert index["2.1.1.01"]["rollup_ok"] is True


def test_exporter_liga_ao_ancestral_mais_proximo():
    """
    O pai era só o prefixo imediato. Faltando o nível intermediário, a
    subárvore inteira ficava órfã e fora da conferência.
    """
    from src.bp.exporters.xlsx_exporter import _build_hierarchy

    index = _build_hierarchy(
        [
            {"codigo": "1", "descricao": "ATIVO", "saldo": 50.0},
            {"codigo": "1.1.1.02", "descricao": "BANCOS", "saldo": 50.0},
        ]
    )
    assert index["1.1.1.02"]["parent_id"] == "1"
    assert index["1"]["parent_id"] is None

    _compute_rollups(index)
    assert index["1"]["rollup_ok"] is True


# ============================================================================
# 5. Validadores de schema (consolidados de test_export_validators.py)
# ============================================================================


def test_validador_rejeita_lista_vazia():
    result = validate_parsed_accounts([])
    assert not result.valid
    assert "empty list" in result.errors[0].lower()


def test_validador_aceita_contas_validas():
    accounts = [
        {"descricao": "Ativo", "saldo": 1000.0, "nivel": 1, "codigo": "1"},
        {"descricao": "Passivo", "saldo": -500.5, "nivel": 1, "codigo": "2"},
    ]
    result = validate_parsed_accounts(accounts)
    assert result.valid
    assert result.metrics["total_accounts"] == 2
    assert result.metrics["valid_saldo"] == 2


def test_validador_rejeita_descricao_vazia():
    accounts = [
        {"descricao": "", "saldo": 100, "nivel": 1},
        {"descricao": "Valid", "saldo": 200, "nivel": 1},
    ]
    result = validate_parsed_accounts(accounts)
    assert not result.valid
    assert any("empty description" in e.lower() for e in result.errors)


def test_validador_avisa_nivel_invalido():
    accounts = [
        {"descricao": "Test1", "saldo": 100, "nivel": 0},
        {"descricao": "Test2", "saldo": 200, "nivel": "abc"},
        {"descricao": "Test3", "saldo": 300, "nivel": 1},
    ]
    result = validate_parsed_accounts(accounts)
    assert result.valid
    assert any("invalid nivel" in w.lower() for w in result.warnings)


def test_validador_avisa_codigo_nao_hierarquico():
    accounts = [
        {"descricao": "Test1", "saldo": 100, "nivel": 1, "codigo": "1.2.3"},
        {"descricao": "Test2", "saldo": 200, "nivel": 1, "codigo": "ABC"},
        {"descricao": "Test3", "saldo": 300, "nivel": 1},
    ]
    result = validate_parsed_accounts(accounts)
    assert result.valid
    assert any("non-hierarchical codigo" in w.lower() for w in result.warnings)


# -- validate_matched_accounts -----------------------------------------------


def test_matched_rejeita_lista_vazia():
    result = validate_matched_accounts([])
    assert not result.valid


def test_matched_aceita_contas_validas():
    accounts = [
        {
            "descricao": "Ativo",
            "saldo": 1000,
            "match_score": 0.95,
            "match_codigo": "1",
            "match_descricao": "ATIVO",
            "is_analytical": False,
        },
        {
            "descricao": "Passivo",
            "saldo": -500,
            "match_score": 0.80,
            "match_codigo": "2",
            "match_descricao": "PASSIVO",
            "is_analytical": False,
        },
    ]
    result = validate_matched_accounts(accounts)
    assert result.valid
    assert result.metrics["matched"] == 2
    assert result.metrics["match_rate_%"] == 100.0


def test_matched_rejeita_score_fora_do_intervalo():
    accounts = [
        {"descricao": "Test", "saldo": 100, "match_score": 1.5},
        {"descricao": "Test2", "saldo": 200, "match_score": -0.1},
    ]
    result = validate_matched_accounts(accounts)
    assert not result.valid
    assert any("invalid match_score" in e.lower() for e in result.errors)


def test_matched_rejeita_dados_inconsistentes():
    accounts = [
        {
            "descricao": "Test",
            "saldo": 100,
            "match_score": 0.8,
            "match_codigo": "1",
            "match_descricao": None,
        }
    ]
    result = validate_matched_accounts(accounts)
    assert not result.valid
    assert any("inconsistent match" in e.lower() for e in result.errors)


def test_matched_calcula_taxa_excluindo_analiticas():
    accounts = [
        {
            "descricao": "S1",
            "saldo": 100,
            "match_codigo": "1",
            "match_descricao": "ATIVO",
            "is_analytical": False,
        },
        {
            "descricao": "S2",
            "saldo": 200,
            "match_codigo": None,
            "match_descricao": None,
            "is_analytical": False,
        },
        {
            "descricao": "A1",
            "saldo": 50,
            "match_codigo": None,
            "match_descricao": None,
            "is_analytical": True,
        },
    ]
    result = validate_matched_accounts(accounts)
    assert result.valid
    assert result.metrics["synthetic"] == 2
    assert result.metrics["analytical"] == 1
    assert result.metrics["match_rate_%"] == 50.0
