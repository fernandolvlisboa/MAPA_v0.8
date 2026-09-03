"""
O carimbo de versão e a impressão digital dos dados.

Por que estes testes existem
----------------------------

O mesmo balancete — mesmo SHA-256 na aba "Balancete Original" — foi
processado duas vezes e deu **100%** de aproveitamento numa e **38%** na
outra. Não havia como responder "o que mudou?", porque nenhuma das duas
saídas dizia sobre qual versão nem sobre quais dados tinha rodado.

O carimbo não é enfeite: é o que transforma "está errado" em "está errado
*porque* o plano tem 1.109 contas em vez de 1.226". Estes testes garantem que
ele existe, que mede o que precisa medir e que chega à planilha.
"""

from __future__ import annotations

from pathlib import Path

import openpyxl
import pytest

from src.bp import versao

pytestmark = pytest.mark.contrato


def test_versao_tem_formato_de_tag():
    """
    ``VERSAO`` vira a tag do git (`v0.8.2`), então precisa ser x.y.z.

    O workflow de release dispara por `tags: ["v*"]`; um valor solto aqui
    quebra a correspondência entre o que a janela mostra e o que foi
    publicado — que é justamente o vínculo que este módulo existe para criar.
    """
    partes = versao.VERSAO.split(".")
    assert len(partes) == 3, f"VERSAO={versao.VERSAO!r} não é x.y.z"
    assert all(p.isdigit() for p in partes), f"VERSAO={versao.VERSAO!r} não é numérica"


def test_impressao_digital_cobre_os_tres_dados_que_mudam_o_resultado():
    """
    Versão sozinha não explica nada: duas máquinas na mesma versão divergem se
    os dados divergirem. São exatamente três os arquivos capazes disso.
    """
    d = versao.impressao_digital()
    assert "Versão" in d
    for rotulo in ("Plano referencial", "Vocabulário aprendido", "Mapa do template"):
        assert rotulo in d, f"a impressão digital não carimba {rotulo!r}"
        assert d[rotulo] not in ("AUSENTE", "ILEGIVEL"), (
            f"{rotulo} não foi lido — neste estado o programa entrega errado "
            f"em silêncio, que é o defeito que este carimbo denuncia"
        )


def test_impressao_digital_traz_contagem_e_hash():
    """
    Contagem responde "está completo?"; hash responde "é o mesmo?".

    Só a contagem não bastaria: dois planos de 1.226 contas podem diferir, e
    foi uma troca silenciosa de conteúdo que motivou o módulo.
    """
    valor = versao.impressao_digital()["Plano referencial"]
    contagem, _, digest = valor.partition(" / ")
    assert contagem.isdigit() and int(contagem) > 1000, (
        f"plano referencial com {contagem!r} contas — muito pouco"
    )
    assert len(digest) == 8, f"hash {digest!r} fora do formato"


def test_impressao_digital_muda_quando_o_dado_muda(tmp_path, monkeypatch):
    """
    Não-vacuidade: um carimbo que nunca muda não denuncia nada.

    Aponta o resolvedor para um plano diferente e exige que o hash mude.
    """
    antes = versao.impressao_digital()["Plano referencial"]

    falso = tmp_path / "plano_referencial.json"
    falso.write_text('{"contas_index": {"1": {"descricao": "ATIVO"}}}', encoding="utf-8")
    monkeypatch.setattr(
        versao, "_resolver", lambda rel: falso if "plano_referencial" in rel else tmp_path / rel
    )
    depois = versao.impressao_digital()["Plano referencial"]

    assert depois != antes, "o carimbo não reagiu à troca do plano"
    assert depois.startswith("1 / ")


def test_a_versao_chega_ao_sumario_da_entrega(tmp_path, balancete_xls):
    """
    O carimbo só serve se estiver NA PLANILHA.

    É comparando dois Sumários que se descobre, em segundos, se a diferença
    entre duas entregas é de código ou de dado. Se ele ficar só na janela, a
    pergunta volta a não ter resposta no dia seguinte.
    """
    from src.bp.output.build_gt_output import FonteBalancete, build_gt_output

    destino = tmp_path / "com_versao.xlsx"
    build_gt_output(
        [FonteBalancete(balancete_xls, 2024, 1000.0)], destino, nome_cliente="Teste"
    )

    ws = openpyxl.load_workbook(destino, data_only=True)["Sumário"]
    textos = [
        str(v)
        for row in ws.iter_rows(values_only=True)
        for v in row
        if v is not None
    ]

    assert any("VERSÃO E DADOS USADOS" in t for t in textos), (
        "o Sumário não traz a seção de versão"
    )
    assert versao.VERSAO in textos, f"a versão {versao.VERSAO} não está no Sumário"
    assert any("Plano referencial" in t for t in textos), (
        "o Sumário não carimba qual plano foi usado"
    )


# ============================================================================
# O balancete que expos dois defeitos — trava permanente
# ============================================================================


def test_trindade_e_lido_inteiro_pelo_caminho_do_app():
    """
    O caso Trindade, medido ponta a ponta pelo caminho que a JANELA usa.

    Este balancete rendeu dois defeitos reais:

    1. plano de QUATRO classes (1 Ativo, 2 Passivo, 3 Custos, 4 Receitas) com
       tudo positivo — a equacao contabil somava Custos e Receitas em vez de
       subtrair e acusava 11.666.761,48 de desequilibrio num arquivo que
       fecha exatamente;
    2. codigos em duas convencoes na mesma coluna — sinteticas pontuadas
       (`1.1.1.01.001`) e analiticas planas alinhadas a direita (`11111`).

    Vale como trava de nao-regressao do APROVEITAMENTO: a medicao passou de
    38% para 100% e nao pode voltar. Chamar por `service.gerar` e proposital —
    e o caminho da janela, com selecao de arquivo e escala, nao so o motor.

    Pula quando o corpus nao esta no workspace (o arquivo e dado de cliente e
    nao e versionado).
    """
    from src.bp.app import service
    from tests.conftest import require_corpus_file

    entrada = require_corpus_file("Balancete_Trindade_052025.xlsx")

    aceitos, _ = service.selecionar([entrada])
    assert aceitos, "o seletor recusou o balancete"

    import tempfile

    with tempfile.TemporaryDirectory() as pasta:
        r = service.gerar(aceitos, cliente="Trindade", pasta_saida=Path(pasta))

        assert r.ok, r.erro
        assert r.contas_lidas == 193, (
            f"lidas {r.contas_lidas}, esperado 193 — o parser perdeu linhas"
        )
        assert r.contas_nao_identificadas == 0, (
            f"{r.contas_nao_identificadas} conta(s) sem classificacao; este "
            f"balancete casa 100% desde a correcao do plano de 4 classes"
        )
        assert r.match_rate == 1.0, f"aproveitamento caiu para {r.match_rate:.0%}"
        assert f"_v{versao.VERSAO}" in r.saida.name, (
            f"a versao sumiu do nome da entrega: {r.saida.name}"
        )
