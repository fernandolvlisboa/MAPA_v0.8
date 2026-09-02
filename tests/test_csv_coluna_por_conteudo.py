"""
CSV com CONTA (numeração) e CLASSIFICAÇÃO (código): qual é o código? (§28)

O ``CSVParser`` escolhe as colunas pelo NOME do cabeçalho. Quando o balancete
traz uma coluna "CONTA" (numeração de linha: 1, 2, 3, 778…) E uma coluna
"CLASSIFICAÇÃO" (o código hierárquico de verdade: 1, 1.1, 01.1.1…), o casamento
por nome pega "conta" e toma a numeração por código E por descrição, com saldo
vazio. O arquivo lia 335 contas e a entrega saía com 4 linhas.

O fallback relê pelo CONTEÚDO — a coluna cujos valores PARECEM código é o
código — e só substitui quando acha árvore onde o CSVParser não achou.
"""

from __future__ import annotations

from conftest import require_corpus_file

from src.bp.parsers.dispatcher import ParseyCaller
from src.bp.validators.hierarquia import conferir_hierarquia


def _csv(tmp_path, texto: str, nome: str = "b.csv"):
    caminho = tmp_path / nome
    caminho.write_text(texto, encoding="latin-1")
    return caminho


def test_classificacao_vence_conta_por_conteudo(tmp_path):
    """
    Reproduz o defeito exato: duas colunas candidatas a código, e a de
    numeração de linha não pode vencer a de código hierárquico.
    """
    texto = (
        "CONTA,CLASSIFICAÇÃO,NOME DA CONTA CONTÁBIL,SALDO ANTERIOR\n"
        "1,1,ATIVO,300\n"
        "2,1.1,ATIVO CIRCULANTE,300\n"
        "3,1.1.01,DISPONÍVEL,300\n"
        "778,1.1.01.001,CAIXA,100\n"
        "957,1.1.01.002,BANCOS,200\n"
        "9,2,PASSIVO,-300\n"
        "10,2.1,PASSIVO CIRCULANTE,-300\n"
        "11,2.1.01,FORNECEDORES,-300\n"
    )
    contas = ParseyCaller(str(_csv(tmp_path, texto))).parse()
    relatorio = conferir_hierarquia(contas)
    assert relatorio.tem_hierarquia, (
        "o código foi tomado da coluna CONTA (numeração) — sem árvore"
    )
    # O código tem de ser o da CLASSIFICAÇÃO (tem ponto), não a numeração.
    codigos = {str(c["codigo"]) for c in contas}
    assert "1.1.01" in codigos, f"não usou a CLASSIFICAÇÃO como código: {sorted(codigos)[:6]}"
    assert relatorio.rollup_integro, relatorio.resumo()


def test_csv_normal_de_uma_coluna_de_codigo_nao_muda(tmp_path):
    """
    Não-vacuidade: um CSV comum, com uma coluna de código só, continua sendo
    lido pelo CSVParser — o fallback não se intromete.
    """
    texto = (
        "Codigo,Descricao,Saldo\n"
        "1,ATIVO,300\n"
        "1.1,CIRCULANTE,300\n"
        "1.1.01,CAIXA,300\n"
        "1.1.01.001,Caixa geral,300\n"
    )
    contas = ParseyCaller(str(_csv(tmp_path, texto))).parse()
    relatorio = conferir_hierarquia(contas)
    assert relatorio.tem_hierarquia
    assert relatorio.rollup_integro


def test_corpus_2024_ultimo_passa_a_ler_a_arvore():
    """
    O arquivo real: de 4 linhas para a árvore inteira lida.

    NÃO se afirma que ele confere — o formato de número desse arquivo é
    ambíguo (pais e folhas em escalas diferentes) e o programa avisa alto que
    não fecha (§26). O que se trava aqui é o passo anterior: as colunas certas
    e a árvore lida, em vez das 4 linhas que a numeração de linha rendia.
    """
    caminho = require_corpus_file("Balancete 2024 -Ultimo.csv")
    contas = ParseyCaller(str(caminho)).parse()
    relatorio = conferir_hierarquia(contas)
    assert relatorio.tem_hierarquia, "continuou sem árvore — o fallback não disparou"
    assert relatorio.total_contas > 300
    # O código veio da CLASSIFICAÇÃO (com ponto), não da coluna CONTA.
    assert sum(1 for c in contas if "." in str(c["codigo"])) > 100
