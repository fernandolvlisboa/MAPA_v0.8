"""
Testes para a classe PlanodeContas
"""

import pytest
from pathlib import Path
from src.bp.generators.plano_contas import PlanodeContas


@pytest.fixture
def plano():
    """Fixture que carrega o plano de contas padrão."""
    json_path = Path("data/plano_contas.json")
    if not json_path.exists():
        pytest.skip("plano_contas.json não encontrado em data/")
    return PlanodeContas(json_path)


def test_load_plano_contas(plano):
    """Testa se o plano de contas carrega corretamente."""
    assert len(plano.contas_index) > 0
    assert len(plano.forms) > 0
    assert isinstance(plano.contas_flat, list)
    assert isinstance(plano.contas_tree, list)


def test_buscar_por_codigo(plano):
    """Testa busca por código."""
    # Busca conta raiz "1" (ATIVO)
    conta = plano.buscar_por_codigo("1")
    assert conta is not None
    assert conta["codigo"] == "1"
    assert "descricao" in conta

    # Busca conta inexistente
    conta_inexistente = plano.buscar_por_codigo("9999.9999.9999")
    assert conta_inexistente is None


def test_buscar_por_descricao(plano):
    """Testa busca fuzzy por descrição."""
    # Busca por "ATIVO"
    results = plano.buscar_por_descricao("ativo", threshold=0.7, limit=5)
    assert len(results) > 0
    assert all("codigo" in r for r in results)
    assert all("score" in r for r in results)
    assert all(r["score"] >= 0.7 for r in results)

    # Scores devem estar ordenados (decrescente)
    scores = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True)


def test_obter_hierarquia(plano):
    """Testa obter hierarquia completa de uma conta."""
    # Pega qualquer conta que tenha parent_id
    conta_com_pai = None
    for codigo, conta in plano.contas_index.items():
        if conta.get("parent_id"):
            conta_com_pai = codigo
            break

    if not conta_com_pai:
        pytest.skip("Nenhuma conta com parent_id encontrada")

    hierarquia = plano.obter_hierarquia(conta_com_pai)
    assert len(hierarquia) > 0

    # Última conta da hierarquia deve ser a conta buscada
    assert hierarquia[-1]["codigo"] == conta_com_pai

    # Hierarquia deve estar ordenada (raiz → folha)
    for i in range(len(hierarquia) - 1):
        # Cada conta deve ser parent da próxima
        assert hierarquia[i]["codigo"] == hierarquia[i + 1].get("parent_id")


def test_obter_hierarquia_conta_raiz(plano):
    """Testa hierarquia de uma conta raiz (sem pai)."""
    conta_raiz = plano.buscar_por_codigo("1")
    if not conta_raiz:
        pytest.skip("Conta '1' não encontrada")

    hierarquia = plano.obter_hierarquia("1")
    # Conta raiz tem hierarquia de tamanho 1 (ela mesma)
    assert len(hierarquia) == 1
    assert hierarquia[0]["codigo"] == "1"


def test_listar_contas_por_form(plano):
    """Testa listagem de contas por formulário."""
    forms = plano.listar_forms()
    if not forms:
        pytest.skip("Nenhum formulário encontrado")

    # Pega primeiro form
    form_name = forms[0]
    contas = plano.listar_contas_por_form(form_name)

    assert isinstance(contas, list)
    assert len(contas) > 0
    assert all("codigo" in c for c in contas)


def test_listar_forms(plano):
    """Testa listagem de formulários."""
    forms = plano.listar_forms()
    assert isinstance(forms, list)
    assert len(forms) > 0
    # Deve estar ordenado
    assert forms == sorted(forms)


def test_get_filhos(plano):
    """Testa obter contas filhas diretas."""
    # Busca conta "1" (ATIVO) que provavelmente tem filhos
    filhos = plano.get_filhos("1")

    if len(filhos) == 0:
        pytest.skip("Conta '1' não tem filhos")

    # Todos os filhos devem ter parent_id = "1"
    assert all(f.get("parent_id") == "1" for f in filhos)

    # Deve estar ordenado por código
    codigos = [f["codigo"] for f in filhos]
    assert codigos == sorted(codigos)


def test_estatisticas(plano):
    """Testa geração de estatísticas."""
    stats = plano.estatisticas()

    assert "total_contas" in stats
    assert "total_forms" in stats
    assert "contas_por_nivel" in stats
    assert "contas_por_tipo" in stats
    assert "contas_por_natureza" in stats
    assert "nivel_maximo" in stats

    assert stats["total_contas"] > 0
    assert stats["total_forms"] >= 0
    assert stats["nivel_maximo"] >= 1


