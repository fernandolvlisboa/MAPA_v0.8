"""
Testes dos utilitários de infraestrutura extraídos no passe de arquitetura.

``utils/json_store.py`` e ``parsers/registro.py`` nasceram de duplicações que
escondiam inconsistências reais — o tipo de código que só é seguro de
centralizar se o comportamento centralizado estiver travado.

Referência: ``REVISAO_QUALIDADE.md`` §8.
"""

from __future__ import annotations

import json

import pytest

from src.bp.parsers.registro import normalizar_registros
from src.bp.utils.json_store import load_json, save_json

pytestmark = pytest.mark.contrato


# ============================================================================
# json_store — o padrão load/save que estava em 6 lugares
# ============================================================================


def test_load_json_devolve_default_quando_ausente(tmp_path):
    assert load_json(tmp_path / "nao_existe.json", {"a": 1}) == {"a": 1}
    assert load_json(tmp_path / "nao_existe.json", set()) == set()


def test_load_json_degrada_em_arquivo_corrompido(tmp_path, capsys):
    """
    Cinco das seis cópias originais não tratavam ``JSONDecodeError``: um
    arquivo de estado truncado derrubava a rodada de treino inteira. Agora o
    estado recomeça do default — sempre recuperável — e o aviso sai no log.
    """
    alvo = tmp_path / "truncado.json"
    alvo.write_text('{"variacoes": {"caixa"', encoding="utf-8")

    assert load_json(alvo, {}) == {}
    assert "ilegível" in capsys.readouterr().out


def test_save_e_load_fazem_roundtrip(tmp_path):
    alvo = tmp_path / "estado.json"
    dados = {"contas": ["1.1", "1.2"], "acentuação": "preservada", "n": 3}
    save_json(alvo, dados)
    assert load_json(alvo, {}) == dados
    assert "acentuação" in alvo.read_text(encoding="utf-8"), "ensure_ascii vazou"


def test_save_json_cria_o_diretorio(tmp_path):
    alvo = tmp_path / "novo" / "sub" / "estado.json"
    save_json(alvo, {"ok": True})
    assert json.loads(alvo.read_text(encoding="utf-8")) == {"ok": True}


def test_save_json_nao_deixa_o_arquivo_pela_metade(tmp_path):
    """
    A gravação é atômica: se ela falhar, o conteúdo anterior continua íntegro.
    Estado de treino acumulado em várias sessões é caro de perder.
    """
    alvo = tmp_path / "estado.json"
    save_json(alvo, {"versao": 1})

    class NaoSerializavel:
        pass

    with pytest.raises(TypeError):
        save_json(alvo, {"versao": 2, "quebra": NaoSerializavel()})

    assert json.loads(alvo.read_text(encoding="utf-8")) == {"versao": 1}
    restos = [p.name for p in tmp_path.iterdir() if p.name.endswith(".tmp")]
    assert not restos, f"arquivo temporário deixado para trás: {restos}"


# ============================================================================
# registro — o contrato que o dispatcher garante
# ============================================================================


def test_traduz_o_vocabulario_do_txt_parser():
    [r] = normalizar_registros(
        [
            {
                "classificacao": "1.1.01",
                "codigo": "1002",
                "descricao": "DISPONIBILIDADES",
                "creditos": 10.0,
                "debitos": 5.0,
                "saldo_atual": 100.0,
            }
        ]
    )
    assert r["codigo"] == "1.1.01", "código hierárquico não foi promovido"
    assert r["codigo_interno"] == "1002", "código da origem foi perdido"
    assert (r["credito"], r["debito"]) == (10.0, 5.0)
    assert r["saldo"] == 100.0, "saldo não foi derivado de saldo_atual"
    assert r["nivel"] == 3
    for antigo in ("creditos", "debitos", "classificacao"):
        assert antigo not in r


def test_conta_raiz_sem_ponto_tambem_e_promovida():
    """A raiz do plano é ``"1"`` — a presença do ponto não serve de teste."""
    [r] = normalizar_registros(
        [{"classificacao": "1", "codigo": "1000", "descricao": "ATIVO"}]
    )
    assert r["codigo"] == "1"
    assert r["nivel"] == 1


def test_classificacao_nao_hierarquica_e_ignorada():
    """Se `classificacao` não parece código, o `codigo` da origem prevalece."""
    [r] = normalizar_registros(
        [{"classificacao": "Ativo Circulante", "codigo": "1.1", "descricao": "X"}]
    )
    assert r["codigo"] == "1.1"
    assert "codigo_interno" not in r


def test_e_idempotente():
    """Um registro já no contrato passa inalterado — o dispatcher pode
    normalizar em qualquer ponto sem medo de aplicar duas vezes."""
    original = {
        "codigo": "1.1.01",
        "descricao": "CAIXA",
        "saldo": 100.0,
        "nivel": 3,
        "credito": 1.0,
    }
    [uma] = normalizar_registros([original])
    [duas] = normalizar_registros([uma])
    assert uma == duas == original


def test_descricao_e_o_codigo_de_ultimo_recurso():
    """Estratégia description-first: sem código na origem, a descrição serve."""
    [r] = normalizar_registros([{"descricao": "CAIXA GERAL", "saldo": 1.0}])
    assert r["codigo"] == "CAIXA GERAL"
    assert r["nivel"] == 1


def test_saldo_ausente_cai_para_saldo_anterior():
    [r] = normalizar_registros(
        [{"codigo": "1.1", "descricao": "X", "saldo_anterior": 50.0}]
    )
    assert r["saldo"] == 50.0


def test_saldo_ilegivel_permanece_none():
    """``None`` atravessa o contrato: é o sinal que o validador precisa ver."""
    [r] = normalizar_registros([{"codigo": "1.1", "descricao": "X", "saldo": None}])
    assert r["saldo"] is None
