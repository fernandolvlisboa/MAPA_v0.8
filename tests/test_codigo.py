"""Testes de utils/codigo (nivel/classe hierárquicos)."""

from src.bp.utils.codigo import classe_from_codigo, nivel_from_codigo


def test_nivel_from_codigo():
    assert nivel_from_codigo("1") == 1
    assert nivel_from_codigo("1.1") == 2
    assert nivel_from_codigo("1.1.01.03") == 4
    assert nivel_from_codigo("") == 0
    assert nivel_from_codigo(None) == 0


def test_classe_from_codigo_variantes():
    assert classe_from_codigo("1.1.01") == "ATIVO"
    assert classe_from_codigo("2.1.01") == "PASSIVO"
    assert classe_from_codigo("3.1") == "RESULTADO"
    assert classe_from_codigo("4.1.01") == "RESULTADO"
    assert classe_from_codigo("9.9") == "RESULTADO"
    # códigos redutores/formatação com prefixos
    assert classe_from_codigo("(-) 4.1") == "RESULTADO"
    assert classe_from_codigo("- 2.01") == "PASSIVO"
    # códigos textuais: sem restrição
    assert classe_from_codigo("ABC") is None
    assert classe_from_codigo("") is None
    assert classe_from_codigo(None) is None


def test_classe_import_from_conta_matcher_backward_compat():
    """Chamadores existentes importam de matchers.conta_matcher — deve funcionar."""
    from src.bp.matchers.conta_matcher import classe_from_codigo as cm_classe

    assert cm_classe("1.1.01") == "ATIVO"
    assert cm_classe is classe_from_codigo  # mesma função, um só código-fonte
