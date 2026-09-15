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
    canonicalizar_contas,
    chave_hierarquica,
    conferir_hierarquia,
    detectar_largura_fixa,
    e_linha_de_total,
    mapear_filhos,
    participa_da_arvore,
    raizes,
    selecionar_para_projecao,
    valor_do_grupo,
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
# 4. Plano de largura fixa com padding (COSIF): a árvore não pode colapsar
# ============================================================================
#
# Códigos como ``1.1.2.30.02.00007`` põem a hierarquia em posições fixas,
# preenchem os níveis não usados com zero e reservam o último segmento para um
# id sequencial. O pai (``1.1.2.30.00.00003``) não é prefixo-de-ponto do filho,
# então ``mapear_filhos`` não montava a árvore: num balancete de banco real,
# 342 de 414 contas viravam raiz e o total do Ativo somava pai + filho + neto,
# inflando de R$ 30,9 mi para R$ 181 mi. Ver REVISAO_QUALIDADE.md.


#: Recorte mínimo de um balancete COSIF: dois ramos do Ativo, cada um descendo
#: até a folha, com o padding e o id sequencial reais. A raiz "1" (1000) é a
#: soma dos dois ramos (400 + 600).
COSIF = [
    conta("1.0.0.00.00.00007", "CIRCULANTE E REALIZAVEL A LONGO PRAZO", 1000.0),
    conta("1.1.0.00.00.00006", "DISPONIBILIDADES", 400.0),
    conta("1.1.2.00.00.00002", "DEPOSITOS BANCARIOS", 400.0),
    conta("1.1.2.30.00.00003", "DEP BANC DE INST S/CTA RESERVA", 400.0),
    conta("1.1.2.30.02.00007", "BRADESCO - AG 1002", 400.0),
    conta("1.2.0.00.00.00005", "APLICACOES INTERFINANCEIRAS DE LIQUIDEZ", 600.0),
    conta("1.2.2.00.00.00001", "APLIC. EM DEPOSITOS INTERFINANCEIROS", 600.0),
    conta("1.2.2.10.00.00008", "APLIC. EM DEPOSITOS INTERFINANCEIROS", 600.0),
    conta("1.2.2.10.20.00035", "BRADESCO - CDI - D+1", 250.0),
    conta("1.2.2.10.20.00042", "VOTORANTIM - CDI - LONGA", 350.0),
]


def test_detecta_largura_fixa_so_em_plano_com_padding():
    assert detectar_largura_fixa([c["codigo"] for c in COSIF]) == 6
    # O corpus de PJ usa código variável, sem zero interior: não dispara.
    variavel = ["1", "1.1", "1.1.01", "2.1.1.01.0010", "2.1.1.02"] * 3
    assert detectar_largura_fixa(variavel) is None


def test_chave_hierarquica_distingue_no_agregado_de_folha():
    # Nó-agregado (tem zero de padding nos níveis): descarta o id e apara zeros.
    assert chave_hierarquica("1.0.0.00.00.00007", 6) == "1"
    assert chave_hierarquica("1.1.2.30.00.00003", 6) == "1.1.2.30"
    # Folha totalmente especificada: mantém o código inteiro — duas contas
    # irmãs (00035, 00042) NÃO podem colapsar na mesma chave e ser somadas.
    assert chave_hierarquica("1.2.2.10.20.00035", 6) == "1.2.2.10.20.00035"
    assert chave_hierarquica("1.2.2.10.20.00042", 6) == "1.2.2.10.20.00042"
    # Sem plano fixo: identidade (o estilo de código variável do corpus).
    assert chave_hierarquica("2.1.1.01.0010", None) == "2.1.1.01.0010"


def test_canonicalizar_e_identidade_em_plano_variavel():
    """No corpus de PJ nada muda — a canonicalização é no-op."""
    assert canonicalizar_contas(BANCOS) == BANCOS


def test_canonicalizar_preserva_contagem_e_guarda_original():
    canon = canonicalizar_contas(COSIF)
    assert len(canon) == len(COSIF)  # 1:1, a fusão de nós vem depois
    por_original = {c["codigo_original"]: c["codigo"] for c in canon}
    assert por_original["1.0.0.00.00.00007"] == "1"
    assert por_original["1.1.2.30.00.00003"] == "1.1.2.30"
    assert por_original["1.2.2.10.20.00035"] == "1.2.2.10.20.00035"


def test_cosif_nao_colapsa_a_arvore():
    """
    O defeito central: sem canonicalização a árvore some (quase toda conta vira
    raiz). Depois dela há UMA raiz ("1") e cada nó confere com a soma dos filhos.
    """
    canon = canonicalizar_contas(COSIF)
    grupos = agrupar_por_codigo(canon)
    filhos = mapear_filhos(grupos)
    assert raizes(grupos, filhos) == ["1"]

    rel = conferir_hierarquia(canon)
    assert rel.tem_hierarquia
    assert rel.pais_divergentes == 0, [str(d) for d in rel.divergencias]
    assert rel.totais_por_classe["ATIVO"] == pytest.approx(1000.0)


def test_cosif_selecao_nao_conta_duas_vezes():
    """Emitido + não coberto reproduz a origem, como no estilo variável."""
    canon = canonicalizar_contas(COSIF)
    grupos = agrupar_por_codigo(canon)
    mapeados = {"1.1.2.30", "1.2.2.10"}  # dois agrupadores mapeados
    selecao = selecionar_para_projecao(canon, lambda c: c in mapeados)
    soma = sum(
        c["saldo"]
        for cod in selecao.codigos + selecao.nao_cobertos
        for c in grupos[cod]
    )
    assert soma == pytest.approx(1000.0)
    for a in selecao.codigos:
        for b in selecao.codigos:
            assert a == b or not b.startswith(a + "."), f"{a} ancestral de {b}"


def test_valor_do_grupo_trata_subtotal_que_convive_com_detalhe():
    # COSIF: dentro de 8.1.7.33 a linha PROVENTOS (849.558,97) já é a soma de
    # FÉRIAS + SALÁRIO + 13º… que valem os mesmos 849.558,97. Somar tudo conta
    # em dobro; a regra devolve só o subtotal.
    proventos = 849558.97
    detalhe = [84982.61, 417704.5, 62550.8, 3731.62, 231789.85, 48799.59]
    assert sum(detalhe) == pytest.approx(proventos)
    assert valor_do_grupo([proventos, *detalhe]) == pytest.approx(proventos)


def test_valor_do_grupo_soma_contas_homonimas_distintas():
    # RBM: 2.1.1.01.0010 cobre EMPRÉSTIMO SANTANDER e JUROS A APROPRIAR; nenhuma
    # é a soma da outra, então a resposta é a soma (comportamento de sempre).
    assert valor_do_grupo([-200.0, -100.0]) == pytest.approx(-300.0)
    assert valor_do_grupo([42.0]) == pytest.approx(42.0)  # um só elemento
    assert valor_do_grupo([]) == pytest.approx(0.0)


def test_linha_de_total_geral_fica_fora_da_arvore():
    """
    "TOTAL DO ATIVO"/"TOTAL DO PASSIVO" são somas que o template recalcula, não
    contas. Num plano COSIF elas vêm codificadas dentro de um grupo
    (``3.9.9.99.99.09999``) e viravam um valor gigante no lugar errado.
    """
    assert e_linha_de_total("TOTAL DO ATIVO")
    assert e_linha_de_total("Total do Passivo")
    assert e_linha_de_total("TOTAL GERAL")
    assert e_linha_de_total("TOTAL DO PASSIVO E PATRIMONIO LIQUIDO")
    # Subtotal de bloco: a hierarquia trata pela soma dos filhos, não exclui.
    assert not e_linha_de_total("Total do Ativo Circulante")
    assert not e_linha_de_total("CAIXA GERAL")
    # E some da árvore, mesmo com código hierárquico válido.
    assert not participa_da_arvore(
        conta("3.9.9.99.99.09999", "TOTAL DO ATIVO", 66.0)
    )
    assert participa_da_arvore(conta("1.1", "ATIVO CIRCULANTE", 10.0))
