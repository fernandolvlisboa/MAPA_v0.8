"""Testes da camada de sinônimos/abreviações e guarda anti-lixo (Plano B)."""

from src.bp.utils.synonyms import expand_synonyms, is_garbage_description


def test_expand_phrase_zero_overlap():
    # "bens numerarios" não compartilha token com "caixa..." — a expansão é o
    # que permite o fuzzy casar.
    assert "caixa" in expand_synonyms("BENS NUMERARIOS")


def test_expand_handles_glued_punctuation():
    # pontuação grudada não pode bloquear a frase
    assert expand_synonyms("FORNECEDORES/CREDORES") == "fornecedores"
    assert "receitas diferidas" in expand_synonyms("REC.RECEBIDAS ANTECIPADAMENTE")


def test_expand_symbolic_abbrev():
    assert expand_synonyms("BANCO C/APLICACOES").startswith("banco com")
    assert "sobre" in expand_synonyms("PIS S/ FATURAMENTO")


def test_expand_token_abbrev():
    assert "clientes" in expand_synonyms("Duplicatas a Receber")


def test_expand_idempotent_on_canonical():
    # termo já canônico não deve ser destruído
    assert expand_synonyms("Caixa") == "caixa"


def test_expand_english():
    assert expand_synonyms("Trade payables") == "fornecedores"
    assert "caixa" in expand_synonyms("Cash and cash equivalents")
    assert "estoques" in expand_synonyms("Inventories")
    assert "imobilizado" in expand_synonyms("Property, plant and equipment")


def test_expand_spanish():
    assert expand_synonyms("Proveedores") == "fornecedores"
    assert "caixa" in expand_synonyms("Efectivo y equivalentes de efectivo")
    assert "estoques" in expand_synonyms("Existencias")
    assert "imobilizado" in expand_synonyms("Inmovilizado")


def test_expand_chained_resolves_to_terminal():
    # cadeia EN -> intermediário PT -> canônico deve resolver por completo
    assert expand_synonyms("Cash and cash equivalents") == "caixa"


def test_garbage_numeric():
    assert is_garbage_description("199687591.84")
    assert is_garbage_description("-203123324.74")
    assert is_garbage_description("0.0")
    assert is_garbage_description("12,50")
    assert is_garbage_description("(-)")
    assert is_garbage_description("")
    assert is_garbage_description(None)


def test_garbage_keeps_real_accounts():
    assert not is_garbage_description("CAIXA")
    assert not is_garbage_description("Fornecedores Nacionais")
    assert not is_garbage_description("ICMS a Recolher")
