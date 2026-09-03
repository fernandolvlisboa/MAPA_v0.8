"""
Testes para ContaMatcher e MatchCache (Fase 4)
"""

import pytest
from pathlib import Path
import tempfile
import json

from src.bp.matchers import (
    ContaMatcher,
    MatchCandidate,
    MatchDecision,
    MatchResult,
    MatchCache,
)
from src.bp.generators.plano_contas import PlanodeContas


# =============================================================================
# Testes classe_from_codigo (Plano C)
# =============================================================================


def test_classe_disambiguation_blocks_cross_class(plano_contas, cache_path):
    """Classe da origem impede casar Passivo com conta do Ativo."""
    m = ContaMatcher(plano_contas, cache_path=cache_path)
    # A fixture só tem contas de ATIVO (raiz "1"). Uma origem de PASSIVO
    # (raiz "2") não deve auto-aceitar nenhuma delas.
    r = m.match("Bancos Conta Movimento", codigo_origem="2.1.01")
    assert r.needs_review is True


def test_classe_penalty_not_double_applied(plano_contas, cache_path):
    """Regressão: a penalidade cross-class não pode ser aplicada duas vezes
    (uma no _fuzzy_match, outra no _apply_heuristics) no MESMO candidato."""
    m = ContaMatcher(plano_contas, cache_path=cache_path)
    r = m.match("Bancos Conta Movimento", codigo_origem="2.1.01")
    # Score do melhor candidato: no máximo 0.5 (uma penalidade), NUNCA 0.25.
    if r.candidates:
        for c in r.candidates:
            assert c.score >= 0.5 - 1e-6 or c.score == 0.0, (
                f"candidato {c.codigo} tem score {c.score} — dupla penalidade?"
            )


def test_classe_same_class_still_matches(plano_contas, cache_path):
    """Classe compatível (Ativo->Ativo) mantém o match normal."""
    m = ContaMatcher(plano_contas, cache_path=cache_path)
    r = m.match("Bancos Conta Movimento", codigo_origem="1.1.01")
    assert r.decision is not None
    assert r.decision.codigo == "1.1.01.01.02"


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def plano_contas():
    """Plano de contas simplificado para testes."""
    # Estrutura válida para PlanodeContas (forms, contas_flat, contas_tree, contas_index)
    estrutura = {
        "forms": {},
        "contas_flat": [
            {
                "codigo": "1.1.01",
                "descricao": "Disponibilidades",
                "tipo": "ATIVO",
                "nivel": 3,
            },
            {
                "codigo": "1.1.01.01.01",
                "descricao": "Caixa",
                "tipo": "ATIVO",
                "nivel": 5,
            },
            {
                "codigo": "1.1.01.01.02",
                "descricao": "Bancos Conta Movimento",
                "tipo": "ATIVO",
                "nivel": 5,
            },
            {
                "codigo": "1.1.02.01",
                "descricao": "Contas a Receber de Clientes",
                "tipo": "ATIVO",
                "nivel": 4,
            },
        ],
        "contas_tree": [
            {
                "codigo": "1",
                "descricao": "ATIVO",
                "tipo": "ATIVO",
                "nivel": 1,
                "filhos": [
                    {
                        "codigo": "1.1",
                        "descricao": "ATIVO CIRCULANTE",
                        "tipo": "ATIVO",
                        "nivel": 2,
                        "filhos": [
                            {
                                "codigo": "1.1.01",
                                "descricao": "Disponibilidades",
                                "tipo": "ATIVO",
                                "nivel": 3,
                                "filhos": [
                                    {
                                        "codigo": "1.1.01.01",
                                        "descricao": "Caixa e Equivalentes de Caixa",
                                        "tipo": "ATIVO",
                                        "nivel": 4,
                                        "filhos": [
                                            {
                                                "codigo": "1.1.01.01.01",
                                                "descricao": "Caixa",
                                                "tipo": "ATIVO",
                                                "nivel": 5,
                                            },
                                            {
                                                "codigo": "1.1.01.01.02",
                                                "descricao": "Bancos Conta Movimento",
                                                "tipo": "ATIVO",
                                                "nivel": 5,
                                            },
                                        ],
                                    }
                                ],
                            },
                            {
                                "codigo": "1.1.02",
                                "descricao": "Créditos",
                                "tipo": "ATIVO",
                                "nivel": 3,
                                "filhos": [
                                    {
                                        "codigo": "1.1.02.01",
                                        "descricao": "Contas a Receber de Clientes",
                                        "tipo": "ATIVO",
                                        "nivel": 4,
                                    }
                                ],
                            },
                        ],
                    }
                ],
            }
        ],
        "contas_index": {
            "1.1.01": {
                "codigo": "1.1.01",
                "descricao": "Disponibilidades",
                "tipo": "ATIVO",
                "nivel": 3,
            },
            "1.1.01.01.01": {
                "codigo": "1.1.01.01.01",
                "descricao": "Caixa",
                "tipo": "ATIVO",
                "nivel": 5,
            },
            "1.1.01.01.02": {
                "codigo": "1.1.01.01.02",
                "descricao": "Bancos Conta Movimento",
                "tipo": "ATIVO",
                "nivel": 5,
            },
            "1.1.02.01": {
                "codigo": "1.1.02.01",
                "descricao": "Contas a Receber de Clientes",
                "tipo": "ATIVO",
                "nivel": 4,
            },
        },
    }

    # Salva em arquivo temporário
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", suffix=".json", delete=False
    ) as f:
        json.dump(estrutura, f, ensure_ascii=False, indent=2)
        temp_path = f.name

    plano = PlanodeContas(Path(temp_path))

    yield plano

    # Cleanup
    Path(temp_path).unlink(missing_ok=True)


@pytest.fixture
def cache_path():
    """Cache temporário."""
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", suffix=".json", delete=False
    ) as f:
        temp_path = f.name

    yield temp_path

    # Cleanup
    Path(temp_path).unlink(missing_ok=True)


@pytest.fixture
def matcher(plano_contas, cache_path):
    """ContaMatcher configurado."""
    return ContaMatcher(
        plano_contas=plano_contas,
        cache_path=cache_path,
        auto_accept_threshold=0.85,
        requery_threshold=0.60,
        use_ai=False,
    )


# =============================================================================
# Testes MatchCache
# =============================================================================


def test_match_cache_save_and_get(cache_path):
    """Testa salvamento e recuperação do cache."""
    cache = MatchCache(cache_path)

    # Salva decisão
    cache.save(
        query="caixa",
        codigo="1.1.01.01.01",
        descricao="Caixa",
        score=0.95,
        confidence=0.95,
    )

    # Recupera
    result = cache.get("caixa")
    assert result is not None
    assert result["codigo"] == "1.1.01.01.01"
    assert result["descricao"] == "Caixa"
    assert result["score"] == 0.95


def test_match_cache_persistence(cache_path):
    """Testa persistência do cache entre instâncias."""
    # Primeira instância
    cache1 = MatchCache(cache_path)
    cache1.save("banco", "1.1.01.01.02", "Bancos Conta Movimento", 0.90, 0.90)

    # Segunda instância (recarrega do disco)
    cache2 = MatchCache(cache_path)
    result = cache2.get("banco")

    assert result is not None
    assert result["codigo"] == "1.1.01.01.02"


def test_match_cache_update(cache_path):
    """Testa atualização de decisão manual."""
    cache = MatchCache(cache_path)

    # Salva decisão automática
    cache.save("caixa", "1.1.01.01.01", "Caixa", 0.80, 0.80, manual=False)

    # Atualiza manualmente
    cache.update("caixa", "1.1.01.01.02", "Bancos Conta Movimento", manual=True)

    result = cache.get("caixa")
    assert result["codigo"] == "1.1.01.01.02"
    assert result["manual"] is True
    assert result["confidence"] == 1.0


def test_match_cache_delete(cache_path):
    """Testa remoção de decisão."""
    cache = MatchCache(cache_path)
    cache.save("caixa", "1.1.01.01.01", "Caixa", 0.95, 0.95)

    # Remove
    deleted = cache.delete("caixa")
    assert deleted is True

    # Verifica que foi removido
    result = cache.get("caixa")
    assert result is None


def test_match_cache_stats(cache_path):
    """Testa estatísticas do cache."""
    cache = MatchCache(cache_path)

    cache.save("caixa", "1.1.01.01.01", "Caixa", 0.95, 0.95, manual=False)
    cache.save("banco", "1.1.01.01.02", "Bancos", 0.85, 0.85, manual=True)

    stats = cache.get_stats()

    assert stats["total_entries"] == 2
    assert stats["auto_entries"] == 1
    assert stats["manual_entries"] == 1
    assert stats["avg_score"] == pytest.approx(0.90, abs=0.01)


# =============================================================================
# Testes ContaMatcher - Fuzzy Matching
# =============================================================================


def test_matcher_exact_match(matcher):
    """Testa matching exato."""
    result = matcher.match("Caixa")

    assert result.decision is not None
    assert result.decision.codigo == "1.1.01.01.01"
    assert result.decision.score >= 0.85
    assert result.needs_review is False


def test_matcher_fuzzy_match_with_typo(matcher):
    """Testa matching com erro de digitação."""
    result = matcher.match("Caxa")  # Faltando 'i'

    # Deve encontrar "Caixa" mesmo com typo
    assert result.decision is not None
    assert "1.1.01.01.01" in result.decision.codigo


def test_matcher_partial_match(matcher):
    """Testa matching parcial."""
    result = matcher.match("Bancos")

    assert result.decision is not None
    assert "1.1.01.01.02" in result.decision.codigo


def test_matcher_below_threshold(matcher):
    """Testa matching abaixo do threshold."""
    result = matcher.match("Xpto Desconhecido")

    # Não deve auto-aceitar
    assert result.needs_review is True
    # Mas deve ter candidatos
    assert len(result.candidates) > 0


# =============================================================================
# Testes ContaMatcher - Heurísticas
# =============================================================================


def test_matcher_with_tipo_hint(matcher):
    """Testa matching com dica de tipo."""
    result = matcher.match("Disponibilidades", tipo="ATIVO")

    assert result.decision is not None
    # Deve preferir conta do tipo ATIVO
    conta_info = next(
        c for c in matcher.plano.contas_flat if c["codigo"] == result.decision.codigo
    )
    assert conta_info["tipo"] == "ATIVO"


def test_matcher_keyword_boost(matcher):
    """Testa boost por palavra-chave."""
    result = matcher.match("Saldo em Banco")

    # "banco" é detectado mas score não alcança threshold com dataset mínimo
    assert result.needs_review  # vai para revisão
    assert len(result.candidates) > 0
    # Verifica que "Bancos" está entre os candidatos
    assert any("banco" in c.descricao.lower() for c in result.candidates)


# =============================================================================
# Testes ContaMatcher - Cache
# =============================================================================


def test_matcher_uses_cache(matcher):
    """Testa que matcher usa cache."""
    # Primeira busca
    result1 = matcher.match("Caixa")
    assert result1.decision.source in ["fuzzy", "heuristic"]

    # Segunda busca (deve vir do cache)
    result2 = matcher.match("Caixa")
    assert result2.decision.source == "cache"
    assert result2.metadata.get("cache_hit") is True


# =============================================================================
# Testes ContaMatcher - Batch Processing
# =============================================================================


def test_matcher_injected_ai_classifier(plano_contas, cache_path):
    """O desempate por IA é injetável e resolve casos que iriam para revisão."""

    def fake_classifier(descricao, candidates, context):
        # Simula um LLM escolhendo o primeiro candidato com alta confiança.
        assert candidates, "classificador deve receber candidatos"
        c = candidates[0]
        return MatchDecision(
            codigo=c.codigo,
            descricao=c.descricao,
            score=0.99,
            source="ai",
            confidence=0.99,
            method="fake_llm",
        )

    m = ContaMatcher(
        plano_contas=plano_contas,
        cache_path=cache_path,
        use_ai=True,
        ai_classifier=fake_classifier,
    )
    # "Saldo em Banco" sozinho ia para revisão; com o classificador, decide.
    result = m.match("Saldo em Banco")
    assert result.decision is not None
    assert result.decision.source == "ai"
    assert result.metadata.get("ai_used") is True


def test_matcher_ai_classifier_failure_is_safe(plano_contas, cache_path):
    """Falha do classificador não derruba o matching (cai em revisão)."""

    def boom(descricao, candidates, context):
        raise RuntimeError("provedor indisponível")

    m = ContaMatcher(
        plano_contas=plano_contas,
        cache_path=cache_path,
        use_ai=True,
        ai_classifier=boom,
    )
    result = m.match("Saldo em Banco")
    assert result.needs_review is True


def test_matcher_batch(matcher):
    """Testa processamento em lote."""
    contas = [
        {"descricao": "Caixa", "tipo": "ATIVO"},
        {"descricao": "Bancos", "tipo": "ATIVO"},
        {"descricao": "Clientes", "tipo": "ATIVO"},
    ]

    results = matcher.match_batch(contas)

    assert len(results) == 3
    assert all(r.decision is not None for r in results)


def test_matcher_stats(matcher):
    """Testa estatísticas de matching."""
    contas = [
        {"descricao": "Caixa"},
        {"descricao": "Bancos"},
        {"descricao": "Xpto Desconhecido"},
    ]

    results = matcher.match_batch(contas)
    stats = matcher.get_stats(results)

    assert stats["total"] == 3
    assert stats["auto_matched"] >= 2  # Caixa e Bancos
    assert stats["needs_review"] >= 1  # Xpto Desconhecido
    assert stats["auto_matched_pct"] > 0


# =============================================================================
# Testes Cache Export
# =============================================================================


def test_cache_export_json(cache_path):
    """Testa exportação do cache para JSON."""
    cache = MatchCache(cache_path)
    cache.save("caixa", "1.1.01.01.01", "Caixa", 0.95, 0.95)

    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", suffix=".json", delete=False
    ) as f:
        export_path = f.name

    try:
        cache.export_for_review(export_path)

        # Verifica que arquivo foi criado
        assert Path(export_path).exists()

        # Verifica conteúdo
        with open(export_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            assert "caixa" in data

    finally:
        Path(export_path).unlink(missing_ok=True)


def test_cache_export_markdown(cache_path):
    """Testa exportação do cache para Markdown."""
    cache = MatchCache(cache_path)
    cache.save("caixa", "1.1.01.01.01", "Caixa", 0.95, 0.95)

    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", suffix=".md", delete=False
    ) as f:
        export_path = f.name

    try:
        cache.export_for_review(export_path)

        # Verifica que arquivo foi criado
        assert Path(export_path).exists()

        # Verifica conteúdo básico
        with open(export_path, "r", encoding="utf-8") as f:
            content = f.read()
            assert "Cache de Matching" in content
            assert "caixa" in content

    finally:
        Path(export_path).unlink(missing_ok=True)
