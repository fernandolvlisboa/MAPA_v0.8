"""
Integridade do índice de busca do ``ContaMatcher``.

``_prepare_fuzzy_data`` montava o índice assim::

    self.fuzzy_map[normalize(descricao)] = {...}

Chaveado pela **descrição normalizada**. Num plano de contas, descrições se
repetem em ramos diferentes por natureza — "Outros" aparece em 56 códigos do
plano real, "(-) ICMS" em 3. A última conta lida sobrescrevia as anteriores e
**25,9% do plano ficava inalcançável** pelo matcher.

E era justamente o conjunto que o Plano C (restrição por classe contábil)
existe para desambiguar: ele recebia candidatos de um índice que já havia
colapsado os homônimos, então conseguia *rejeitar* a conta de classe errada,
mas nunca *achar* a certa — ela não estava lá. O cache, chaveado só pela
descrição, ainda anulava a restrição a partir da segunda chamada.

Hoje ``entradas_por_texto`` mapeia texto -> **lista** de contas e a chave do
cache inclui a classe. Este arquivo é a trava dessas duas correções.
Referência: ``REVISAO_QUALIDADE.md`` §4.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import pytest

from src.bp.generators.plano_contas import PlanodeContas
from src.bp.matchers.conta_matcher import ContaMatcher
from src.bp.utils.normalizer import normalize

pytestmark = pytest.mark.contrato

PROJECT_ROOT = Path(__file__).parent.parent
PLANO_CONTAS_JSON = PROJECT_ROOT / "data" / "plano_contas.json"


# ============================================================================
# Fixtures: plano sintético com homônimos em classes diferentes
# ============================================================================

CONTAS_HOMONIMAS = {
    "1.1.02.01": {
        "codigo": "1.1.02.01",
        "descricao": "Clientes",
        "tipo": "ATIVO",
        "natureza": "Devedora",
        "nivel": 4,
    },
    "2.1.05.01": {
        "codigo": "2.1.05.01",
        "descricao": "Clientes",
        "tipo": "PASSIVO",
        "natureza": "Credora",
        "nivel": 4,
    },
    "1.1.01.01": {
        "codigo": "1.1.01.01",
        "descricao": "Caixa Geral",
        "tipo": "ATIVO",
        "natureza": "Devedora",
        "nivel": 4,
    },
}


@pytest.fixture
def plano_homonimos(tmp_path) -> PlanodeContas:
    caminho = tmp_path / "plano.json"
    caminho.write_text(
        json.dumps(
            {
                "forms": {},
                "contas_flat": list(CONTAS_HOMONIMAS.values()),
                "contas_tree": [],
                "contas_index": CONTAS_HOMONIMAS,
            }
        ),
        encoding="utf-8",
    )
    return PlanodeContas(caminho)


@pytest.fixture
def matcher(plano_homonimos, tmp_path) -> ContaMatcher:
    """Matcher com cache isolado — nunca toca ``data/match_cache.json``."""
    return ContaMatcher(plano_homonimos, cache_path=tmp_path / "cache.json")


# ============================================================================
# 1. Isolamento — o matcher não pode escrever no estado versionado
# ============================================================================


def test_matcher_default_aponta_para_cache_versionado(plano_homonimos):
    """
    Documenta o acoplamento: sem ``cache_path``, o matcher grava em
    ``data/match_cache.json``, que está sob controle de versão. Todo teste
    que instancia ``ContaMatcher`` DEVE passar um cache temporário.
    """
    m = ContaMatcher(plano_homonimos, cache_path=None)
    assert m.cache.cache_path == PROJECT_ROOT / "data" / "match_cache.json"


# ============================================================================
# 2. Colisão de descrições no índice
# ============================================================================


def test_homonimas_convivem_no_indice(matcher):
    """Duas contas com a mesma descrição: um texto de busca, duas entradas."""
    assert len(matcher.plano.contas_flat) == 3
    assert len(matcher.fuzzy_choices) == 2, "esperados 2 textos distintos"
    assert len(matcher.entradas_por_texto["clientes"]) == 2, (
        "a homônima foi sobrescrita — o índice voltou a colapsar descrições"
    )


def test_indice_contem_todas_as_contas(matcher):
    indexados = {
        e["codigo"] for entradas in matcher.entradas_por_texto.values() for e in entradas
    }
    assert indexados == set(CONTAS_HOMONIMAS), (
        f"contas ausentes do índice: {set(CONTAS_HOMONIMAS) - indexados}"
    )


@pytest.mark.parametrize(
    "classe,esperado", [("ATIVO", "1.1.02.01"), ("PASSIVO", "2.1.05.01")]
)
def test_plano_c_acha_a_conta_da_classe_certa(matcher, classe, esperado):
    """
    O teste que resume a correção: a mesma descrição resolve para contas
    diferentes conforme a classe da conta de origem.
    """
    resultado = matcher.match("CLIENTES", classe=classe)
    assert resultado.decision is not None, f"nenhum candidato para {classe}"
    assert resultado.decision.codigo == esperado
    assert resultado.needs_review is False


def test_plano_c_rejeita_quando_so_ha_classe_errada(matcher):
    """
    Sem candidato da classe pedida, o Plano C derruba o score do que existe
    para longe do auto-accept, em vez de aceitá-lo.
    """
    resultado = matcher.match("CAIXA GERAL", classe="PASSIVO")
    assert resultado.needs_review is True, (
        "candidato de classe incompatível foi aceito automaticamente"
    )


# ============================================================================
# 3. Chave do cache — mais pobre que a chave da decisão
# ============================================================================


def test_chave_do_cache_carrega_a_classe(matcher):
    """A chave precisa ser tão específica quanto os dados da decisão."""
    matcher.match("CAIXA GERAL", classe="ATIVO")
    assert list(matcher.cache.cache) == ["caixa geral|ATIVO"]


def test_consulta_sem_classe_preserva_a_chave_antiga(matcher):
    """
    Compatibilidade: as decisões já gravadas em ``data/match_cache.json`` estão
    sob a chave sem classe e precisam continuar sendo encontradas.
    """
    matcher.match("CAIXA GERAL")
    assert list(matcher.cache.cache) == ["caixa geral"]


def test_cache_nao_atravessa_classes(matcher):
    primeira = matcher.match("CAIXA GERAL", classe="ATIVO")
    assert primeira.decision is not None, "pré-condição: a 1ª chamada deve casar"
    assert primeira.decision.codigo == "1.1.01.01"

    segunda = matcher.match("CAIXA GERAL", classe="PASSIVO")
    assert segunda.decision is None or segunda.decision.source != "cache", (
        "cache devolveu uma conta do ATIVO para uma consulta do PASSIVO "
        f"(codigo={segunda.decision.codigo}, source={segunda.decision.source})"
    )


# ============================================================================
# 4. Censo no plano real — dimensiona o impacto
# ============================================================================


def _censo_colisoes(caminho: Path) -> tuple[int, int]:
    """Devolve (total de contas, contas inalcançáveis por colisão)."""
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    flat = dados.get("contas_flat", [])
    grupos: dict[str, list[str]] = defaultdict(list)
    for conta in flat:
        grupos[normalize(conta.get("descricao", ""))].append(conta.get("codigo"))
    perdidas = sum(len(v) - 1 for v in grupos.values() if len(v) > 1)
    return len(flat), perdidas


@pytest.mark.skipif(
    not PLANO_CONTAS_JSON.exists(), reason="plano_contas.json ausente"
)
def test_plano_real_tem_muitos_homonimos():
    """
    O plano real tem homônimos de sobra — é o que tornava a colisão cara.
    Trava o pressuposto do teste seguinte: se um dia o plano deixar de ter
    descrições repetidas, aquele teste vira vacuoso.
    """
    total, colididas = _censo_colisoes(PLANO_CONTAS_JSON)
    assert total > 7000
    assert colididas / total > 0.25, (
        f"só {colididas}/{total} contas compartilham descrição — o teste de "
        f"alcançabilidade perdeu o pressuposto"
    )


@pytest.mark.integration
@pytest.mark.skipif(
    not PLANO_CONTAS_JSON.exists(), reason="plano_contas.json ausente"
)
def test_plano_real_e_integralmente_alcancavel(tmp_path):
    """
    A trava que importa: **toda** conta do plano real chega ao matcher.
    Eram 2.003 de 7.741 (25,9%) invisíveis.
    """
    matcher = ContaMatcher(
        PlanodeContas(PLANO_CONTAS_JSON), cache_path=tmp_path / "cache.json"
    )
    indexados = {
        e["codigo"] for entradas in matcher.entradas_por_texto.values() for e in entradas
    }
    do_plano = {c.get("codigo") for c in matcher.plano.contas_flat}
    ausentes = do_plano - indexados
    assert not ausentes, f"{len(ausentes)} contas inalcançáveis, ex.: {sorted(ausentes)[:5]}"
