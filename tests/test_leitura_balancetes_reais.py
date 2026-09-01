"""
Os balancetes que chegaram de clientes, e os quatro defeitos que eles expuseram.

O contexto
----------

Seis balancetes reais e recentes — os casos para os quais o programa está
sendo feito — foram postos no corpus. **Os seis rendiam zero contas.** Um
derrubava o parser com exceção.

Nenhum teste da suíte podia ter pego isso: todos rodavam sobre o corpus
antigo, e um arquivo que o pipeline não consegue ler simplesmente não aparece
em métrica nenhuma. É o ponto cego do §15 outra vez, um nível antes: lá o
número final não era medido; aqui o arquivo nem chega a ser lido.

Os quatro defeitos
------------------

1. **Vocabulário fechado** (`has_balance_keywords`). Três balancetes com
   estrutura impecável — ``Conta Contábil | Cod. R. | Nome da Conta |
   S. Anterior | Débito | Crédito | S. Atual`` — eram recusados porque a lista
   tinha 8 palavras e exigia 2: casavam só "conta". "Cod. R." não é "codigo";
   "S. Atual" não é "saldo". Mesmo erro do §12, noutro lugar.

2. **Código de largura fixa** (``1.01.00.00.00000000``). Todos os níveis com o
   mesmo número de segmentos: nenhum é prefixo do outro, a árvore vira raízes
   irmãs, o rollup não é conferido e a seleção que evita dupla contagem nunca
   roda.

3. **Colunas duplicadas** derrubavam o parser: ``df[col]`` devolve um
   *DataFrame* quando o rótulo se repete, e a primeira operação de texto
   estoura com ``AttributeError``.

4. **Balancete em outra aba.** Planilha de trabalho tem dezenas de abas; a
   primeira costuma ser um modelo de saída. O leitor devolvia a primeira aba
   que passasse no portão — zero contas, com nove abas de balancete ao lado.

Referência: ``REVISAO_QUALIDADE.md`` §17.
"""

from __future__ import annotations

import pandas as pd
import pytest
from conftest import CORPUS_DIR

from src.bp.parsers.common import has_balance_keywords, parece_balancete
from src.bp.parsers.dispatcher import ParseyCaller
from src.bp.parsers.registro import normalizar_registros
from src.bp.utils.codigo import normalizar_codigo
from src.bp.validators.hierarquia import conferir_hierarquia

#: Balancetes reais recebidos de clientes, com a forma que cada um exercita.
#: Não há asserção sobre valor de conta específica — só sobre a INVARIANTE de
#: que o arquivo é lido e a árvore dele fecha (§10).
REAIS_COM_HIERARQUIA = (
    "IBH 18_Balancete_06.2026.xlsx",
    "Infraestrutura Brasil III_Balancete 06.2026.xlsx",
    "Infraestrutura Brasil III- A_Balancete 06.2026.xlsx",
)


# ============================================================================
# 1. Vocabulário: o nome da coluna é dica, o conteúdo é prova
# ============================================================================


def test_cabecalho_de_balancete_real_e_reconhecido():
    """O cabeçalho exato dos três arquivos que eram recusados."""
    colunas = [
        "Conta Contábil", "Cod. R.", "Unnamed: 2", "Nome da Conta",
        "S. Anterior", "Débito", "Crédito", "S. Atual",
    ]
    assert has_balance_keywords(colunas), (
        "cabeçalho de balancete real recusado pelo vocabulário — é o defeito "
        "que fazia três arquivos de cliente renderem zero contas"
    )


def test_conteudo_reconhece_o_que_o_nome_nao_diz():
    """
    A rede sob o filtro por palavra: colunas sem nome nenhum, mas com códigos
    contábeis e números, são um balancete.
    """
    df = pd.DataFrame({
        "a": ["1.01.01.00", "1.01.01.01", "1.01.02.00", "1.02.00.00"],
        "b": ["Caixa", "Caixa Geral", "Bancos", "Realizável"],
        "c": [100.0, 100.0, 250.5, 900.0],
    })
    assert not has_balance_keywords(list(df.columns)), "o teste seria vacuoso"
    assert parece_balancete(df)


def test_conteudo_nao_confunde_planilha_qualquer():
    """Não-vacuidade do lado oposto: a rede não pode aprovar qualquer tabela."""
    assert not parece_balancete(
        pd.DataFrame({"nome": ["ana", "bruno"], "idade": [30, 40]})
    )
    assert not parece_balancete(pd.DataFrame())
    assert not parece_balancete(pd.DataFrame({"só_uma": [1, 2, 3]}))


# ============================================================================
# 2. Código de largura fixa: zero à direita é preenchimento
# ============================================================================


@pytest.mark.parametrize(
    ("codigo", "esperado"),
    [
        ("1.00.00.00.00000000", "1"),
        ("1.01.00.00.00000000", "1.01"),
        ("1.01.01.02.00000000", "1.01.01.02"),
        ("1.01.01.01.00000001", "1.01.01.01.00000001"),  # último não é zero
        ("1.01.03.04.00000010", "1.01.03.04.00000010"),
        ("1.1.1.01.001", "1.1.1.01.001"),  # sem preenchimento: intacto
        ("2.1", "2.1"),  # menos de 3 segmentos: intacto
        ("1", "1"),
        ("ALUGUEIS", "ALUGUEIS"),  # não numérico: intacto
        ("", ""),
    ],
)
def test_normalizar_codigo(codigo, esperado):
    assert normalizar_codigo(codigo) == esperado


def test_corte_restaura_a_arvore_de_um_esquema_de_largura_fixa():
    registros = normalizar_registros([
        {"codigo": "1.00.00.00.00000000", "descricao": "Ativo", "saldo": 300.0},
        {"codigo": "1.01.00.00.00000000", "descricao": "Circulante", "saldo": 300.0},
        {"codigo": "1.01.01.00.00000000", "descricao": "Disponibilidades", "saldo": 300.0},
        {"codigo": "1.01.01.01.00000000", "descricao": "Caixa", "saldo": 100.0},
        {"codigo": "1.01.01.02.00000000", "descricao": "Bancos", "saldo": 200.0},
    ])
    codigos = [r["codigo"] for r in registros]
    assert codigos == ["1", "1.01", "1.01.01", "1.01.01.01", "1.01.01.02"]
    assert registros[0]["codigo_original"] == "1.00.00.00.00000000"

    relatorio = conferir_hierarquia(registros)
    assert relatorio.tem_hierarquia
    assert relatorio.rollup_integro
    assert relatorio.pais_conferidos == 3


def test_corte_nao_acontece_quando_colidiria():
    """
    A trava que a primeira versão não tinha, e por isso quebrou um balancete
    que estava correto.

    Cortando registro a registro, ``1.5.00 CLIENTES`` virou ``1.5``, que já
    existia como "ATIVO NÃO CIRCULANTE": duas contas distintas colapsaram num
    código só e o rollup, íntegro, passou a divergir em 3,27 milhões. Ali o
    "00" é nível de verdade, e a decisão tem de ser do balancete inteiro.
    """
    registros = normalizar_registros([
        {"codigo": "1.1.00", "descricao": "Ativo circulante", "saldo": 100.0},
        {"codigo": "1.5", "descricao": "ATIVO NÃO CIRCULANTE", "saldo": 50.0},
        {"codigo": "1.5.00", "descricao": "CLIENTES", "saldo": 20.0},
        {"codigo": "1.5.01", "descricao": "Clientes nacionais", "saldo": 20.0},
        {"codigo": "1.6.00", "descricao": "Estoques", "saldo": 30.0},
        {"codigo": "2.1.00", "descricao": "Passivo", "saldo": -150.0},
    ])
    assert [r["codigo"] for r in registros] == [
        "1.1.00", "1.5", "1.5.00", "1.5.01", "1.6.00", "2.1.00"
    ], (
        "cortou apesar da colisão: '1.5.00' viraria '1.5', que já existe como "
        "outra conta — as duas colapsariam num código só"
    )
    assert not any("codigo_original" in r for r in registros)


def test_corte_nao_acontece_com_niveis_variaveis():
    """Onde os códigos têm profundidades diferentes não há preenchimento."""
    registros = normalizar_registros([
        {"codigo": "1", "descricao": "Ativo", "saldo": 100.0},
        {"codigo": "1.1", "descricao": "Circulante", "saldo": 100.0},
        {"codigo": "1.1.1.00", "descricao": "Disponível", "saldo": 100.0},
        {"codigo": "1.1.1.01", "descricao": "Caixa", "saldo": 60.0},
        {"codigo": "1.1.1.02", "descricao": "Bancos", "saldo": 40.0},
        {"codigo": "2.1", "descricao": "Passivo", "saldo": -100.0},
    ])
    assert [r["codigo"] for r in registros][2] == "1.1.1.00"


# ============================================================================
# 3. Colunas duplicadas não podem derrubar o parser
# ============================================================================


def test_coluna_duplicada_nao_derruba_o_parser():
    """
    ``df[col]`` devolve DataFrame quando o rótulo se repete, e a primeira
    operação de texto estoura. Planilha de trabalho repete cabeçalho o tempo
    todo — não é caso de borda.
    """
    df = pd.DataFrame(
        [
            ["1.01.01", "Caixa", 100.0, 100.0],
            ["1.01.02", "Bancos", 200.0, 200.0],
            ["1.02.00", "Realizável", 50.0, 50.0],
        ],
        columns=["Conta", "Descrição", "Saldo", "Saldo"],
    )
    contas = ParseyCaller("qualquer.xlsx")._parse_accounts_from_df(df)
    assert contas, "nenhuma conta extraída de uma tabela válida"
    assert len(contas) == 3


def test_desduplicacao_preserva_a_primeira_ocorrencia():
    df = pd.DataFrame([[1, 2, 3]], columns=["Saldo", "Saldo", "Saldo"])
    resultado = ParseyCaller._desduplicar_colunas(df)
    assert list(resultado.columns) == ["Saldo", "Saldo.1", "Saldo.2"]
    # Sem duplicata, o DataFrame passa intacto (mesmo objeto, sem cópia).
    limpo = pd.DataFrame([[1, 2]], columns=["a", "b"])
    assert ParseyCaller._desduplicar_colunas(limpo) is limpo


# ============================================================================
# 4. Os arquivos reais, ponta a ponta
# ============================================================================


@pytest.mark.integration
@pytest.mark.parametrize("nome", REAIS_COM_HIERARQUIA)
def test_balancete_real_de_cliente_e_lido_e_fecha(nome):
    """
    O que se exige de um balancete de cliente: ser lido, ter a hierarquia
    reconhecida, e a árvore dele fechar.

    Nenhuma asserção sobre conta ou valor específico — a regra do §10. O que
    se trava é a invariante.
    """
    caminho = CORPUS_DIR / nome
    if not CORPUS_DIR.exists():
        pytest.skip(f"corpus ausente: {CORPUS_DIR}")
    if not caminho.exists():
        pytest.skip(f"balancete ausente neste workspace: {nome}")

    contas = ParseyCaller(caminho).parse()
    assert len(contas) > 50, f"{nome}: só {len(contas)} contas — o arquivo tem mais"

    relatorio = conferir_hierarquia(contas)
    assert relatorio.tem_hierarquia, (
        f"{nome}: hierarquia não reconhecida. O código é de largura fixa "
        "('1.01.00.00.00000000') e o preenchimento não foi cortado?"
    )
    assert relatorio.rollup_integro, (
        f"{nome}: a árvore não fecha na origem — "
        f"{relatorio.pais_divergentes} agrupador(es). Pior: "
        f"{relatorio.divergencias[0] if relatorio.divergencias else ''}"
    )
    print(f"[real] {nome}: {len(contas)} contas, {relatorio.pais_conferidos} pais conferem")


@pytest.mark.integration
def test_nenhum_balancete_do_corpus_derruba_o_parser():
    """
    Piso absoluto: ler um arquivo pode render zero contas — nem todo arquivo
    do corpus é balancete —, mas **nenhum pode levantar exceção**.
    """
    if not CORPUS_DIR.exists():
        pytest.skip(f"corpus ausente: {CORPUS_DIR}")
    extensoes = {".xls", ".xlsx", ".csv", ".txt"}
    arquivos = [p for p in sorted(CORPUS_DIR.iterdir()) if p.suffix.lower() in extensoes]
    assert len(arquivos) >= 10, "corpus pequeno demais — o teste seria fraco"

    explodiram: list[str] = []
    for caminho in arquivos:
        try:
            ParseyCaller(caminho).parse()
        except Exception as exc:
            explodiram.append(f"{caminho.name}: {type(exc).__name__}: {exc}")
    assert not explodiram, "o parser levantou exceção em:\n" + "\n".join(explodiram)


# ============================================================================
# 5. Código plano de largura fixa: a árvore está no prefixo, não no ponto
# ============================================================================
#
# Muito sistema emite o código sem pontos, como número:
#
#     1  ->  101  ->  10101  ->  10101001  ->  101010010001
#
# A hierarquia está lá — cada código é prefixo do filho —, mas invisível para
# quem procura ponto. Num balancete de cliente com sete exercícios, cinco
# caíam em "SEM HIERARQUIA" por isso, e eu cheguei a RELATAR que "não há
# código de conta na origem". Havia: em 97,9% das contas o pai estava lá.
#
# A trava que faltou na primeira versão é a que mais importa: inteiros
# CONSECUTIVOS formam prefixos naturalmente ("1" é prefixo de "12", que é de
# "123"), então uma coluna de numeração de linha 1..668 passava no teste e
# virava "hierarquia" — o rollup divergiu em 65 agrupadores com somas de
# bilhões.

from src.bp.utils.codigo import (  # noqa: E402
    detectar_niveis_planos,
    pontuar_codigo_plano,
)


def _plano_hierarquico() -> list[str]:
    """Um plano de contas plano realista: níveis 1, 3, 5, 8 e 12 dígitos."""
    codigos = ["1", "2"]
    for grupo in ("01", "02", "03"):
        codigos.append(f"1{grupo}")
        for conta in ("01", "02", "03"):
            codigos.append(f"1{grupo}{conta}")
            for sub in ("001", "002", "003"):
                codigos.append(f"1{grupo}{conta}{sub}")
                codigos.extend(
                    f"1{grupo}{conta}{sub}{folha}" for folha in ("0001", "0002")
                )
    return codigos


def test_detecta_os_niveis_de_um_codigo_plano():
    niveis = detectar_niveis_planos(_plano_hierarquico())
    assert niveis == (1, 3, 5, 8, 12)


def test_numeracao_de_linha_nao_vira_hierarquia():
    """
    A trava decisiva. Inteiros consecutivos formam prefixos por acidente, e uma
    coluna ``n`` de 1 a 668 foi promovida a código de conta — 65 agrupadores
    divergindo com somas de bilhões.

    Contador é denso e contíguo; código de conta tem buracos enormes.
    """
    assert detectar_niveis_planos([str(i) for i in range(1, 669)]) is None
    assert detectar_niveis_planos([str(i) for i in range(100, 400)]) is None


def test_coluna_de_identificadores_de_tamanho_unico_nao_vira_hierarquia():
    """Sem níveis distintos não há árvore — são só identificadores."""
    assert detectar_niveis_planos([str(10000 + i * 7) for i in range(80)]) is None


def test_codigos_sem_pai_presente_nao_viram_hierarquia():
    """
    A prova exigida é o prefixo: sem pai presente na esmagadora maioria,
    qualquer coluna de números de tamanhos variados viraria árvore falsa.
    """
    orfaos = [str(900000 + i * 37) for i in range(40)]
    orfaos += [str(1000 + i * 13) for i in range(40)]
    orfaos += [str(10 + i) for i in range(10)]
    assert detectar_niveis_planos(orfaos) is None


@pytest.mark.parametrize(
    ("codigo", "esperado"),
    [
        ("1", "1"),
        ("101", "1.01"),
        ("10101", "1.01.01"),
        ("10101001", "1.01.01.001"),
        ("101010010001", "1.01.01.001.0001"),
        ("101010029999", "1.01.01.002.9999"),
        ("ALUGUEIS", "ALUGUEIS"),
    ],
)
def test_pontuar_codigo_plano(codigo, esperado):
    assert pontuar_codigo_plano(codigo, (1, 3, 5, 8, 12)) == esperado


def test_conversao_restaura_a_arvore_no_contrato_de_registro():
    registros = normalizar_registros([
        {"codigo": c, "descricao": f"conta {c}", "saldo": 1.0}
        for c in _plano_hierarquico()
    ])
    codigos = {r["codigo"] for r in registros}
    assert "1.01.01.001.0001" in codigos, "o código plano não foi pontuado"
    assert conferir_hierarquia(registros).tem_hierarquia


def test_conversao_nao_acontece_sem_esquema_plano():
    """Balancete já pontuado passa intacto — não converter é o padrão seguro."""
    registros = normalizar_registros([
        {"codigo": "1.1.1", "descricao": "Disponível", "saldo": 100.0},
        {"codigo": "1.1.1.01", "descricao": "Caixa", "saldo": 60.0},
        {"codigo": "1.1.1.02", "descricao": "Bancos", "saldo": 40.0},
    ])
    assert [r["codigo"] for r in registros] == ["1.1.1", "1.1.1.01", "1.1.1.02"]
    assert not any("codigo_original" in r for r in registros)


@pytest.mark.integration
def test_exercicio_com_codigo_plano_e_lido_com_arvore():
    """
    Ponta a ponta no arquivo real. Antes desta correção o exercício rendia
    contas e caía em "SEM HIERARQUIA"; eu relatei isso como "não há código na
    origem", e estava errado.
    """
    caminho = CORPUS_DIR / "SmartRio Balancetes (2020 2026).xlsx"
    if not CORPUS_DIR.exists():
        pytest.skip(f"corpus ausente: {CORPUS_DIR}")
    if not caminho.exists():
        pytest.skip("arquivo ausente neste workspace")

    contas = ParseyCaller(caminho, aba="Balancetes 2023").parse()
    assert len(contas) > 300

    relatorio = conferir_hierarquia(contas)
    assert relatorio.tem_hierarquia, (
        "o código plano ('10101001') não foi reconhecido como hierárquico"
    )
    assert relatorio.pais_conferidos > 100, (
        f"só {relatorio.pais_conferidos} agrupadores conferem — a coluna "
        "escolhida provavelmente não é a de código de conta"
    )
