"""
Conferência hierárquica — a aritmética que valida a extração.

Um balancete é uma árvore em que cada agrupador declara um saldo igual à soma
dos filhos. Essa identidade não estava sendo verificada em lugar nenhum, e a
ausência dela é a causa direta de o balanço da entrega não fechar:

- contas com nome próprio ("SICOOB - UNISUDESTE - RBM 62540-0") não casam com
  plano de contas nenhum, e o valor delas simplesmente sumia;
- quando o agrupador **e** os filhos casavam, o ramo era somado duas vezes.

Os dois erros são opostos, coexistiam, e nenhum teste os pegava.

Este arquivo cobre o motor (``validators/hierarquia.py``) em árvores
sintéticas. A trava sobre o corpus real está em
``test_integridade_entrega_gt.py::test_cobertura_completa_no_corpus_real``.

Referência: ``REVISAO_QUALIDADE.md`` §9.
"""

from __future__ import annotations

import pytest

from src.bp.validators.hierarquia import (
    agrupar_por_codigo,
    conferir_hierarquia,
    mapear_filhos,
    participa_da_arvore,
    selecionar_para_projecao,
)

pytestmark = pytest.mark.contrato


def conta(codigo: str, descricao: str, saldo: float | None) -> dict:
    return {"codigo": codigo, "descricao": descricao, "saldo": saldo}


#: Árvore mínima com a forma do caso real: um agrupador de bancos cujas folhas
#: têm nome próprio e cuja soma bate com o total declarado.
BANCOS = [
    conta("1", "ATIVO", 1000.0),
    conta("1.1", "ATIVO CIRCULANTE", 1000.0),
    conta("1.1.1", "DISPONÍVEL", 1000.0),
    conta("1.1.1.02", "BANCOS CONTA MOVIMENTO", 1000.0),
    conta("1.1.1.02.0005", "SICOOB - UNISUDESTE - RBM 62540-0", 600.0),
    conta("1.1.1.02.0006", "BANCO DO BRASIL S.A - RBM", 250.0),
    conta("1.1.1.02.0007", "SICREDI RBM - 92688-4", 150.0),
]


# ============================================================================
# 1. A identidade do rollup
# ============================================================================


def test_rollup_confere_quando_filhos_somam_o_pai():
    r = conferir_hierarquia(BANCOS)
    assert r.rollup_integro
    assert r.pais_conferidos == 4
    assert r.pais_divergentes == 0


def test_rollup_acusa_quando_falta_uma_folha():
    """
    O teste que o usuário pediu: some uma conta com nome próprio e a soma
    deixa de bater com o agrupador. É a checagem mais barata e mais forte que
    existe sobre a extração.
    """
    sem_uma = [c for c in BANCOS if c["codigo"] != "1.1.1.02.0006"]
    r = conferir_hierarquia(sem_uma)

    assert not r.rollup_integro
    divergencia = next(d for d in r.divergencias if d.codigo == "1.1.1.02")
    assert divergencia.declarado == pytest.approx(1000.0)
    assert divergencia.somado == pytest.approx(750.0)
    assert divergencia.diferenca == pytest.approx(250.0)
    assert "1.1.1.02" in str(divergencia)


def test_sem_arvore_nao_e_sucesso():
    """
    Um balancete sem código hierárquico não tem pai nenhum. ``rollup_integro``
    tem de ser Falso — um dicionário vazio de divergências não é aprovação.
    """
    sem_codigo = [conta("CAIXA GERAL", "CAIXA GERAL", 10.0)]
    r = conferir_hierarquia(sem_codigo)
    assert not r.tem_hierarquia
    assert not r.rollup_integro
    assert "SEM HIERARQUIA" in r.resumo()


def test_equacao_contabil():
    completo = [
        conta("1", "ATIVO", 1000.0),
        conta("2", "PASSIVO", -800.0),
        conta("3", "RESULTADO", -200.0),
        conta("1.1", "CIRCULANTE", 1000.0),
    ]
    assert conferir_hierarquia(completo).equacao_fecha

    torto = [*completo[:3], conta("1.1", "CIRCULANTE", 1000.0)]
    torto[1] = conta("2", "PASSIVO", -500.0)
    assert not conferir_hierarquia(torto).equacao_fecha


# ============================================================================
# 2. Código repetido é normal em balancete real
# ============================================================================


def test_codigo_repetido_nao_perde_conta():
    """
    No balancete RBM, ``2.1.1.01.0010`` cobre duas contas distintas. Um
    ``dict[codigo] = conta`` descartaria uma delas em silêncio — foi o que fez
    4 dos 80 rollups "falharem" numa primeira medição.
    """
    contas = [
        conta("2.1.1.01", "EMPRÉSTIMOS", -300.0),
        conta("2.1.1.01.0010", "EMPRESTIMO SANTANDER", -200.0),
        conta("2.1.1.01.0010", "JUROS A APROPRIAR", -100.0),
    ]
    grupos = agrupar_por_codigo(contas)
    assert len(grupos["2.1.1.01.0010"]) == 2

    r = conferir_hierarquia(contas)
    assert r.codigos_duplicados == {"2.1.1.01.0010": 2}
    assert r.rollup_integro, "a soma das duas homônimas bate com o pai"


def test_linha_de_totalizacao_fica_fora_da_arvore():
    """
    O parser emite linhas de totalização com um NÚMERO nos dois campos. Elas
    casam o formato de código hierárquico e viravam raízes-fantasma: oito
    delas somavam 20,7 milhões de totais inexistentes no balancete RBM.
    """
    assert participa_da_arvore(conta("1.1", "CIRCULANTE", 1.0))
    assert not participa_da_arvore(conta("2187555.9", "4389425.29", 1.0))
    assert not participa_da_arvore(conta("CAIXA GERAL", "CAIXA GERAL", 1.0))


def test_pai_e_o_ancestral_mais_proximo_existente():
    """Nível intermediário ausente não pode sumir com a subárvore."""
    contas = [
        conta("1", "ATIVO", 50.0),
        conta("1.1.1.02", "BANCOS", 50.0),  # 1.1 e 1.1.1 não existem
    ]
    filhos = mapear_filhos(agrupar_por_codigo(contas))
    assert filhos == {"1": ["1.1.1.02"]}


# ============================================================================
# 3. A seleção: nem dupla contagem, nem valor perdido
# ============================================================================


def _selecionar(contas, mapeados: set[str]):
    return selecionar_para_projecao(contas, lambda c: c in mapeados)


def test_agrupador_absorve_contas_com_nome_proprio():
    """
    O caso que motivou tudo: as três contas bancárias não casam com plano de
    contas nenhum, mas o agrupador casa e já vale a soma delas. Uma linha
    entrega o valor certo em vez de perder três.
    """
    selecao = _selecionar(BANCOS, {"1.1.1.02"})

    assert selecao.codigos == ["1.1.1.02"]
    assert selecao.nao_cobertos == []
    assert selecao.total_absorvidos == 3
    assert set(selecao.absorvidos_por["1.1.1.02"]) == {
        "1.1.1.02.0005",
        "1.1.1.02.0006",
        "1.1.1.02.0007",
    }


def test_nunca_emite_pai_e_filho_juntos():
    """
    Dupla contagem: o total do agrupador JÁ contém os filhos. Emitir os dois
    soma o ramo duas vezes. Nenhum código selecionado pode ser prefixo de
    outro.
    """
    selecao = _selecionar(
        BANCOS, {"1", "1.1", "1.1.1", "1.1.1.02", "1.1.1.02.0005"}
    )
    for a in selecao.codigos:
        for b in selecao.codigos:
            assert a == b or not b.startswith(a + "."), (
                f"{a} é ancestral de {b} — o ramo seria contado duas vezes"
            )


def test_prefere_o_detalhe_quando_ele_cobre_tudo():
    """
    Parar no nível mapeado mais alto seria "ATIVO" — o balanço inteiro em uma
    linha. Quando todas as folhas casam, desce até elas.
    """
    todas = {c["codigo"] for c in BANCOS}
    selecao = _selecionar(BANCOS, todas)
    assert selecao.codigos == [
        "1.1.1.02.0005",
        "1.1.1.02.0006",
        "1.1.1.02.0007",
    ]
    assert selecao.nao_cobertos == []


def test_sobe_ao_agrupador_quando_uma_folha_nao_casa():
    """Detalhe parcial não serve: uma folha de fora obriga a subir."""
    selecao = _selecionar(
        BANCOS,
        {"1.1.1.02", "1.1.1.02.0005", "1.1.1.02.0006"},  # falta a .0007
    )
    assert selecao.codigos == ["1.1.1.02"]
    assert selecao.nao_cobertos == []


def test_folha_sem_agrupador_mapeado_e_reportada_como_perda():
    """
    Quando nem a folha nem nenhum ancestral tem destino, o valor não pode
    sumir calado: ele aparece em ``nao_cobertos`` para virar aviso com o
    montante exato.
    """
    selecao = _selecionar(BANCOS, set())
    assert selecao.codigos == []
    assert selecao.nao_cobertos == [
        "1.1.1.02.0005",
        "1.1.1.02.0006",
        "1.1.1.02.0007",
    ]


def test_selecao_reproduz_o_total_da_origem():
    """
    A invariante que vale sempre: **emitido + não coberto == origem**. Se ela
    quebra, há conta contada duas vezes ou perdida, e nenhum total a jusante
    é confiável.
    """
    grupos = agrupar_por_codigo(BANCOS)
    total_origem = 1000.0  # a raiz "1"

    for mapeados in [
        {"1"},
        {"1.1.1.02"},
        {"1.1.1.02.0005", "1.1.1.02.0006", "1.1.1.02.0007"},
        {"1.1.1.02", "1.1.1.02.0005"},
        {"1.1.1.02.0005"},
        set(),
    ]:
        selecao = _selecionar(BANCOS, mapeados)
        soma = sum(
            c["saldo"]
            for cod in selecao.codigos + selecao.nao_cobertos
            for c in grupos[cod]
        )
        assert soma == pytest.approx(total_origem), (
            f"mapeados={sorted(mapeados)} reproduziu {soma}, esperado {total_origem}"
        )


# ============================================================================
# Plano de QUATRO classes — a equação que o BP declarava quebrada
# ============================================================================


def _quatro_classes(ativo, passivo, custos, receitas):
    """
    Balancete de natureza implícita: tudo positivo, a classe é que diz o lado.

    Estrutura mínima com pai e filho em cada classe, porque a conferência só
    vale quando há árvore (``tem_hierarquia``).
    """
    return [
        {"codigo": "1", "descricao": "ATIVO", "saldo": ativo},
        {"codigo": "1.1", "descricao": "CIRCULANTE", "saldo": ativo},
        {"codigo": "2", "descricao": "PASSIVO", "saldo": passivo},
        {"codigo": "2.1", "descricao": "CIRCULANTE", "saldo": passivo},
        {"codigo": "3", "descricao": "CUSTOS E DESPESAS", "saldo": custos},
        {"codigo": "3.1", "descricao": "CUSTOS", "saldo": custos},
        {"codigo": "4", "descricao": "RECEITAS", "saldo": receitas},
        {"codigo": "4.1", "descricao": "VENDAS", "saldo": receitas},
    ]


def test_quatro_classes_com_natureza_implicita_fecha():
    """
    O caso Trindade, com os números do arquivo real.

    Ativo 2.361.053,53 = Passivo 891.480,90 + Lucro 1.469.572,63, onde o lucro
    é Receitas 4.941.899,84 - Custos 3.472.327,21. Fecha exatamente.

    A soma ingênua das classes dava 11.666.761,48 porque ``classe_from_codigo``
    funde 3 e 4 em "RESULTADO" e as duas entravam SOMADAS — quando a DRE
    subtrai. O programa mandava não entregar uma planilha correta.
    """
    r = conferir_hierarquia(
        _quatro_classes(2_361_053.53, 891_480.90, 3_472_327.21, 4_941_899.84)
    )
    assert r.equacao_fecha, (
        f"balancete que fecha foi reprovado: desequilíbrio {r.desequilibrio:,.2f}"
    )
    assert r.desequilibrio == pytest.approx(0.0, abs=0.01)

    # Não-vacuidade: as quatro raízes têm de estar separadas, senão a
    # subtração da DRE seria impossível de enxergar.
    assert set(r.totais_por_raiz) == {"1", "2", "3", "4"}
    assert r.totais_por_classe["RESULTADO"] == pytest.approx(8_414_227.05)


def test_quatro_classes_com_prejuizo_tambem_fecha():
    """Receitas < Custos: o Passivo supera o Ativo pelo prejuízo."""
    # Ativo 800 = Passivo 1000 + Lucro (-200); Receitas 300 - Custos 500.
    r = conferir_hierarquia(_quatro_classes(800.0, 1000.0, 500.0, 300.0))
    assert r.equacao_fecha, f"prejuízo reprovado: {r.desequilibrio:,.2f}"


def test_quatro_classes_realmente_torto_continua_reprovado():
    """
    A trava do lado oposto — sem ela a correção viraria "aprova tudo".

    Se qualquer atribuição de sinais fechasse, o teste acima não provaria
    nada. Aqui o Ativo não bate com Passivo + lucro por 500, e nenhuma
    combinação de sinais zera.
    """
    r = conferir_hierarquia(_quatro_classes(1_300.0, 1_000.0, 500.0, 300.0))
    assert not r.equacao_fecha, (
        "balancete torto passou — a busca por sinais está aprovando qualquer coisa"
    )


def test_convencao_de_sinal_explicito_continua_fechando():
    """
    Não-regressão: o plano referencial (passivo e receita negativos) fechava
    pela soma simples e tem de continuar fechando.
    """
    contas = [
        {"codigo": "1", "descricao": "ATIVO", "saldo": 1_000.0},
        {"codigo": "1.1", "descricao": "CIRCULANTE", "saldo": 1_000.0},
        {"codigo": "2", "descricao": "PASSIVO", "saldo": -600.0},
        {"codigo": "2.1", "descricao": "CIRCULANTE", "saldo": -600.0},
        {"codigo": "3", "descricao": "RESULTADO", "saldo": -400.0},
        {"codigo": "3.1", "descricao": "RECEITAS", "saldo": -400.0},
    ]
    r = conferir_hierarquia(contas)
    assert r.equacao_fecha
    assert r.desequilibrio == pytest.approx(0.0, abs=0.01)


def test_residuo_da_equacao_e_a_fonte_unica():
    """
    Uma implementacao so — a duplicacao foi o que gerou o segundo defeito.

    A conferencia da ORIGEM ja procurava os sinais certos, mas a reconciliacao
    da ENTREGA continuava somando `emitido_por_classe` cru. Resultado: a tela
    mostrava "Balanco fecha: sim" no cartao e "o balanco nao fechou, nao
    entregue esta planilha" no aviso, sobre o mesmo arquivo. Duas respostas
    para a mesma pergunta porque eram duas contas diferentes.
    """
    from src.bp.validators.hierarquia import residuo_da_equacao

    # Trindade: 4 classes, natureza implicita. Ativo = Passivo + (Rec - Cust).
    assert residuo_da_equacao(
        [2_361_053.53, 891_480.90, 3_472_327.21, 4_941_899.84]
    ) == pytest.approx(0.0, abs=0.01)

    # Sinal explicito (ECF): a soma simples ja zerava e tem de continuar zerando.
    assert residuo_da_equacao([1_000.0, -600.0, -400.0]) == pytest.approx(0.0)

    # Torto de verdade: nenhuma combinacao de sinais salva. Os valores sao
    # escolhidos para nao se cancelarem em nenhuma delas — o melhor caso ainda
    # deixa 619 de residuo sobre um total de 1.381.
    assert abs(residuo_da_equacao([1_000.0, 300.0, 70.0, 11.0])) == pytest.approx(619.0)

    # Sem totais nao ha o que conferir — nao pode explodir.
    assert residuo_da_equacao([]) == 0.0
