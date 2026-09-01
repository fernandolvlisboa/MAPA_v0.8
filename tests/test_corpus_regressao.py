"""
Regressão sobre o corpus inteiro — controle fixo **e** amostra aleatória.

Por que este arquivo existe
---------------------------
Toda a rodada anterior de correções foi verificada contra o balancete RBM. Isso
é sobreajuste: se o RBM passa e os outros trinta quebram, não consertamos nada —
quebramos o modelo, e o teste verde esconde isso. Um defeito só é geral quando
mais de um arquivo o exibe, e uma correção só é geral quando **nenhum outro
arquivo piora**.

A regra desta suíte, em duas partes:

1. **Controle fixo** — os mesmos arquivos em toda execução, cobrindo formas
   diferentes (com e sem hierarquia, .xls/.xlsx/.csv/.txt, com e sem código
   repetido). É a linha de base determinística: se ela muda, a mudança foi
   deliberada e o número no teste é atualizado no mesmo commit.

2. **Amostra aleatória** — arquivos sorteados a cada execução, com a semente
   impressa. Um defeito que só aparece num arquivo que ninguém testa é achado
   por acaso hoje e por acidente com o cliente amanhã. A amostra transforma
   "por acaso" em "eventualmente, e com a semente para reproduzir".

Para repetir uma execução que falhou::

    BP_SEED=<semente do log> uv run pytest tests/test_corpus_regressao.py

O que NÃO pertence aqui
-----------------------
Asserções sobre contas específicas de um balancete específico. "PARCELAMENTOS
não tem destino no template" é uma **particularidade esperada** — vai acontecer
num percentual alto dos clientes. Testar por ela é fixar o modelo no RBM. O que
se testa é a invariante: *seja lá o que ficar de fora, o valor tem de ser
reconciliado e nada pode evaporar.*

Referência: ``REVISAO_QUALIDADE.md`` §10.
"""

from __future__ import annotations

import os
import random
from dataclasses import dataclass
from pathlib import Path

import pytest

from src.bp.parsers.dispatcher import ParseyCaller
from src.bp.utils.paths import samples_dir
from src.bp.validators.hierarquia import conferir_hierarquia

pytestmark = [pytest.mark.contrato, pytest.mark.integration]

CORPUS = samples_dir()
EXTENSOES = {".xls", ".xlsx", ".csv", ".txt"}

#: Controle: escolhidos por **forma**, não por conveniência.
#: - RBM: hierarquia profunda, 8 códigos repetidos, folhas com nome próprio
#: - SPEZZIA: hierarquia limpa, sem repetição
#: - 202404: outro emissor, outra profundidade
#: - Real Life: SEM hierarquia (description-first) — o caso que não pode ser
#:   confundido com sucesso
#: - 2019-01.TXT: largura fixa, e o único do controle com rollup divergente
CONTROLE = (
    "Balancete 072022 122022 - RBM.xls",
    "Balancete SPEZZIA TUBOS 01012024-31122024.xls",
    "202404_2024 - Balancete.xls",
    "Balancete Real Life.xlsx",
    "2019-01.TXT",
)

#: Quantos arquivos sortear além do controle, por execução.
TAMANHO_AMOSTRA = 3


# ============================================================================
# Linha de base agregada — medida sobre os 31 arquivos do corpus
# ============================================================================


@dataclass(frozen=True)
class LinhaDeBase:
    """
    Piso que o corpus não pode furar.

    São mínimos, não igualdades: melhorar é livre, piorar quebra o teste. Se
    um número for atualizado para baixo, foi decisão deliberada e precisa de
    justificativa no commit.
    """

    arquivos_totais: int = 31
    #: Arquivos de que o dispatcher extrai ao menos uma conta.
    parse_com_contas: int = 22
    #: Dos que parseiam, quantos expõem hierarquia de códigos.
    com_hierarquia: int = 17
    #: Dos que têm hierarquia, quantos fecham em TODOS os agrupadores.
    rollup_integro: int = 14
    #: Dos que têm hierarquia, quantos fecham Ativo+Passivo+Resultado.
    equacao_fecha: int = 14


BASE = LinhaDeBase()


@dataclass
class Medida:
    nome: str
    contas: int
    tem_hierarquia: bool
    pais_conferidos: int
    pais_divergentes: int
    equacao_fecha: bool

    @property
    def rollup_integro(self) -> bool:
        return self.tem_hierarquia and self.pais_divergentes == 0


def _medir(caminho: Path) -> Medida:
    contas = ParseyCaller(caminho).parse()
    relatorio = conferir_hierarquia(contas)
    return Medida(
        nome=caminho.name,
        contas=len(contas),
        tem_hierarquia=relatorio.tem_hierarquia,
        pais_conferidos=relatorio.pais_conferidos,
        pais_divergentes=relatorio.pais_divergentes,
        equacao_fecha=relatorio.equacao_fecha,
    )


def _arquivos_do_corpus() -> list[Path]:
    if not CORPUS.exists():
        return []
    return sorted(p for p in CORPUS.iterdir() if p.suffix.lower() in EXTENSOES)


@pytest.fixture(scope="session")
def semente() -> int:
    """
    Semente da amostra. Fixa via ``BP_SEED`` para reproduzir uma falha.

    É impressa no log de toda execução: sem isso, um teste aleatório que falha
    é um teste que não se consegue depurar.
    """
    bruta = os.environ.get("BP_SEED")
    valor = int(bruta) if bruta and bruta.isdigit() else random.randrange(1_000_000)
    print(f"\n[corpus] semente da amostra = {valor}  (BP_SEED={valor} para repetir)")
    return valor


@pytest.fixture(scope="session")
def corpus_medido() -> list[Medida]:
    """Mede o corpus inteiro uma vez por sessão."""
    arquivos = _arquivos_do_corpus()
    if not arquivos:
        pytest.skip(f"corpus ausente: {CORPUS}")
    return [_medir(p) for p in arquivos]


# ============================================================================
# 1. A linha de base agregada não pode piorar
# ============================================================================


def test_corpus_tem_o_tamanho_esperado(corpus_medido):
    """Guarda de não-vacuidade: sem arquivos, todo teste abaixo passa vazio."""
    assert len(corpus_medido) >= BASE.arquivos_totais, (
        f"o corpus encolheu para {len(corpus_medido)} arquivos — os testes "
        f"abaixo perdem representatividade"
    )


def test_quantidade_de_arquivos_parseados_nao_regride(corpus_medido):
    com_contas = [m for m in corpus_medido if m.contas > 0]
    vazios = sorted(m.nome for m in corpus_medido if m.contas == 0)
    assert len(com_contas) >= BASE.parse_com_contas, (
        f"só {len(com_contas)} arquivos renderam contas (base: "
        f"{BASE.parse_com_contas}). Vazios: {vazios}"
    )


def test_quantidade_com_hierarquia_nao_regride(corpus_medido):
    com_arvore = [m for m in corpus_medido if m.tem_hierarquia]
    assert len(com_arvore) >= BASE.com_hierarquia, (
        f"só {len(com_arvore)} arquivos expõem hierarquia (base: "
        f"{BASE.com_hierarquia}) — o roteamento ou a detecção de código piorou"
    )


def test_integridade_do_rollup_nao_regride(corpus_medido):
    """
    A métrica que mais importa: em quantos balancetes a soma dos filhos bate
    com o pai em **todos** os agrupadores.
    """
    integros = [m for m in corpus_medido if m.rollup_integro]
    divergentes = sorted(
        (m.nome, m.pais_divergentes)
        for m in corpus_medido
        if m.tem_hierarquia and m.pais_divergentes
    )
    assert len(integros) >= BASE.rollup_integro, (
        f"só {len(integros)} balancetes têm rollup íntegro (base: "
        f"{BASE.rollup_integro}). Divergentes: {divergentes}"
    )


def test_equacao_contabil_nao_regride(corpus_medido):
    fecham = [m for m in corpus_medido if m.tem_hierarquia and m.equacao_fecha]
    nao_fecham = sorted(
        m.nome for m in corpus_medido if m.tem_hierarquia and not m.equacao_fecha
    )
    assert len(fecham) >= BASE.equacao_fecha, (
        f"só {len(fecham)} balancetes fecham a equação (base: "
        f"{BASE.equacao_fecha}). Não fecham: {nao_fecham}"
    )


# ============================================================================
# 2. Controle fixo — os mesmos arquivos, toda execução
# ============================================================================


@pytest.mark.parametrize("nome", CONTROLE)
def test_controle_parseia(nome):
    caminho = CORPUS / nome
    if not caminho.exists():
        pytest.skip(f"ausente: {caminho}")
    medida = _medir(caminho)
    assert medida.contas > 0, f"{nome} deixou de render contas"


@pytest.mark.parametrize(
    "nome",
    [n for n in CONTROLE if n != "Balancete Real Life.xlsx" and not n.endswith(".TXT")],
)
def test_controle_com_hierarquia_e_integro(nome):
    """
    Os arquivos do controle que têm hierarquia precisam fechar em todos os
    agrupadores. ``Real Life`` (sem código) e os ``.TXT`` (sinal das redutoras,
    ver ``test_dispatcher_roteamento.py``) estão fora por razão conhecida.
    """
    caminho = CORPUS / nome
    if not caminho.exists():
        pytest.skip(f"ausente: {caminho}")
    relatorio = conferir_hierarquia(ParseyCaller(caminho).parse())
    assert relatorio.tem_hierarquia
    assert relatorio.rollup_integro, (
        f"{nome}: {relatorio.pais_divergentes} agrupadores divergem — "
        + "; ".join(str(d) for d in relatorio.divergencias[:2])
    )
    assert relatorio.equacao_fecha


def test_controle_sem_hierarquia_nao_finge_sucesso():
    """
    ``Real Life`` não traz código hierárquico. O relatório tem de dizer isso,
    não devolver "0 divergências" como se estivesse tudo bem.
    """
    caminho = CORPUS / "Balancete Real Life.xlsx"
    if not caminho.exists():
        pytest.skip(f"ausente: {caminho}")
    relatorio = conferir_hierarquia(ParseyCaller(caminho).parse())
    assert relatorio.total_contas > 0
    assert not relatorio.tem_hierarquia
    assert not relatorio.rollup_integro


# ============================================================================
# 3. Amostra aleatória — o que ninguém testa é onde o defeito mora
# ============================================================================


@pytest.fixture(scope="session")
def amostra(semente) -> list[Path]:
    """Sorteia arquivos fora do controle. A semente vai no log."""
    candidatos = [p for p in _arquivos_do_corpus() if p.name not in CONTROLE]
    if not candidatos:
        pytest.skip("corpus sem arquivos além do controle")
    sorteio = random.Random(semente)
    return sorteio.sample(candidatos, min(TAMANHO_AMOSTRA, len(candidatos)))


@pytest.mark.parametrize("indice", range(TAMANHO_AMOSTRA))
def test_amostra_nao_quebra_o_pipeline(amostra, indice):
    """
    Um arquivo sorteado tem de atravessar o parse sem exceção. É o piso: nem
    todo balancete do corpus rende contas (nove não rendem, e isso está
    travado na linha de base), mas **nenhum pode explodir**.
    """
    if indice >= len(amostra):
        pytest.skip("amostra menor que o índice")
    caminho = amostra[indice]
    medida = _medir(caminho)  # levanta se o pipeline quebrar
    assert medida.contas >= 0
    print(f"[amostra] {caminho.name}: {medida.contas} contas, hierarquia={medida.tem_hierarquia}")


@pytest.mark.parametrize("indice", range(TAMANHO_AMOSTRA))
def test_amostra_com_hierarquia_respeita_as_invariantes(amostra, indice):
    """
    Se o arquivo sorteado tem hierarquia, as invariantes valem para ele como
    valem para o controle. Sem asserção sobre conta específica: o que se exige
    é coerência interna, não um valor decorado de um balancete conhecido.
    """
    if indice >= len(amostra):
        pytest.skip("amostra menor que o índice")

    caminho = amostra[indice]
    contas = ParseyCaller(caminho).parse()
    relatorio = conferir_hierarquia(contas)
    if not relatorio.tem_hierarquia:
        pytest.skip(f"{caminho.name} não traz hierarquia")

    # Toda divergência precisa ser descritível — um relatório que acusa sem
    # dizer o quê é tão inútil quanto não acusar.
    for divergencia in relatorio.divergencias:
        assert divergencia.codigo and divergencia.descricao
        assert divergencia.diferenca != 0
        assert divergencia.codigo in str(divergencia)

    # Códigos repetidos são normais; o que não pode é a contagem mentir.
    for codigo, vezes in relatorio.codigos_duplicados.items():
        assert vezes > 1, f"{codigo} listado como repetido aparecendo {vezes}x"

    assert relatorio.total_contas == len(contas)
    assert relatorio.fora_da_arvore >= 0


# ============================================================================
# 4. Cobertura de valor — a métrica que interessa ao negócio
# ============================================================================


@pytest.mark.parametrize("nome", [n for n in CONTROLE if not n.endswith(".TXT")])
def test_cobertura_de_valor_do_controle(nome):
    """
    Quanto do dinheiro da origem chega à entrega, por balancete do controle.

    Contar contas não mede nada: um código emitido cobre várias homônimas, e
    uma folha absorvida pelo agrupador não é conta perdida. Mede-se valor.

    Distribuição medida em 7 balancetes: quatro a 100%, dois acima de 99%, e o
    RBM a 88,6%. **O RBM é o pior caso, não o representativo** — foi contra ele
    que a rodada anterior de correções foi calibrada, e é por isso que este
    arquivo existe.
    """
    import tempfile

    from src.bp.output.build_gt_output import build_gt_output

    template = Path("templates/Template_GT_BP_Padrao_v3.xlsx")
    caminho = CORPUS / nome
    if not caminho.exists() or not template.exists():
        pytest.skip("corpus ou template ausente")

    tmp = Path(tempfile.mkdtemp())
    resultado = build_gt_output(
        caminho, tmp / "o.xlsx", ano_base=2022, cache_path=tmp / "c.json"
    )
    if not resultado.hierarquia.tem_hierarquia:
        pytest.skip(f"{nome} não traz hierarquia")

    assert resultado.reconciliacao.residuo == pytest.approx(0.0, abs=0.01), (
        f"{nome}: resíduo inexplicado de {resultado.reconciliacao.residuo:,.2f}"
    )
    assert resultado.cobertura_de_valor >= 0.85, (
        f"{nome}: só {resultado.cobertura_de_valor:.2%} do valor chegou"
    )
