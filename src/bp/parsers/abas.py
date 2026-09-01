"""
Descoberta de abas: o que uma pasta de trabalho tem dentro.

Por que existe
--------------

Balancete de cliente nem sempre é um arquivo com um período. Vem também como
**pasta de trabalho**: ``Balancetes 2020`` … ``Balancetes 2026`` lado a lado,
ou ``Balancete Dez-2024``, ``Balancete mensal Jan-2026``, … — cada aba um
exercício, entre abas que não são balancete nenhum (``Output Modelo (BP)``,
``Plano de contas``, ``Comparativo``).

Escolher sozinho qual usar é palpite. Este módulo levanta os candidatos —
nome, quantas contas rendem, que exercício aparentam — para que **quem faz o
trabalho** marque os que quer, respeitando o teto de exercícios do template.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

#: Extensões que têm abas.
EXTENSOES_COM_ABAS = (".xlsx", ".xls", ".xlsm")

#: Abaixo disso a aba não parece um balancete — é resumo, capa ou legenda.
MIN_CONTAS = 20

#: Teto de abas inspecionadas. Pasta real chega a vinte; além disso a leitura
#: fica cara sem melhorar a escolha.
MAX_ABAS = 30

_ANO_RE = re.compile(r"(?<!\d)(19|20)(\d{2})(?!\d)")

#: Mês como aparece em nome de aba: abreviado ou por extenso.
#:
#: A fronteira ``(?![a-z])`` não é detalhe. Sem ela, "out" casa dentro de
#: "**Out**put Modelo (BP)" e a aba de modelo vira "outubro" — período
#: inventado numa aba que nem balancete é.
_MESES = {
    1: r"jan(?:eiro)?",
    2: r"fev(?:ereiro)?",
    3: r"mar(?:[çc]o)?",
    4: r"abr(?:il)?",
    5: r"mai(?:o)?",
    6: r"jun(?:ho)?",
    7: r"jul(?:ho)?",
    8: r"ago(?:sto)?",
    9: r"set(?:embro)?",
    10: r"out(?:ubro)?",
    11: r"nov(?:embro)?",
    12: r"dez(?:embro)?",
}
_MES_RE = {
    numero: re.compile(rf"(?<![a-z]){padrao}(?![a-z])")
    for numero, padrao in _MESES.items()
}


#: O que uma aba parece ser.
BALANCETE = "balancete"        #: código hierárquico e árvore conferível
DEMONSTRATIVO = "demonstrativo"  #: já padronizado — sem árvore, valores por período
OUTRA = "outra"                #: nem uma coisa nem outra


@dataclass(frozen=True)
class AbaCandidata:
    """Uma aba e o que ela promete."""

    nome: str
    contas: int
    ano: int | None
    mes: int | None = None
    #: A aba tem árvore de códigos conferível? É o que separa um balancete de
    #: um demonstrativo já montado.
    tem_hierarquia: bool = False

    @property
    def tipo(self) -> str:
        if self.tem_hierarquia:
            return BALANCETE
        if self.contas >= MIN_CONTAS:
            return DEMONSTRATIVO
        return OUTRA

    @property
    def rotulo_do_tipo(self) -> str:
        return {
            BALANCETE: "balancete",
            DEMONSTRATIVO: "já padronizado",
            OUTRA: "—",
        }[self.tipo]

    @property
    def periodo(self) -> str:
        """Rótulo legível do período, para a interface."""
        if self.ano and self.mes:
            return f"{self.mes:02d}/{self.ano}"
        if self.ano:
            return str(self.ano)
        return "—"


def periodo_do_nome(nome: str) -> tuple[int | None, int | None]:
    """
    ``(ano, mês)`` deduzidos do nome da aba, ou ``(None, None)``.

    "Balancetes 2023" -> (2023, None); "Balancete mensal Jan-2026" ->
    (2026, 1); "Balancete Dez-2025" -> (2025, 12).
    """
    texto = str(nome or "").lower()
    achado = _ANO_RE.search(texto)
    ano = int(achado.group(0)) if achado else None
    mes = next((numero for numero, rx in _MES_RE.items() if rx.search(texto)), None)
    return ano, mes


def listar_abas(
    caminho: str | Path,
    min_contas: int = MIN_CONTAS,
    todas: bool = False,
) -> list[AbaCandidata]:
    """
    As abas do arquivo, com quantas contas cada uma rende e o que aparenta ser.

    A contagem é medida, não estimada: cada aba passa pelo mesmo extrator que o
    pipeline usa. É o que distingue ``Balancete mensal Jun-2026`` (424 contas)
    de ``Output Modelo (BP)`` (28) sem depender do nome.

    ``todas=True`` inclui as abas que não parecem balancete. É o modo usado
    quando **nenhuma** aba é balancete puro: aí a pergunta ao analista deixa de
    ser "qual exercício?" e passa a ser "em qual aba está o balanço?", e a
    resposta pode ser uma aba de 36 linhas que o filtro normal descartaria —
    um demonstrativo consolidado, já pronto.

    Devolve lista vazia para arquivo de aba única ou de formato sem abas — aí
    não há escolha a fazer e a interface não deve perguntar nada.
    """
    import pandas as pd

    from .dispatcher import ParseyCaller

    caminho = Path(caminho)
    if caminho.suffix.lower() not in EXTENSOES_COM_ABAS:
        return []
    try:
        nomes = pd.ExcelFile(caminho).sheet_names
    except Exception:
        return []
    if len(nomes) < 2:
        return []

    leitor = ParseyCaller(caminho)
    candidatas: list[AbaCandidata] = []
    for nome in nomes[:MAX_ABAS]:
        try:
            bruto = pd.read_excel(caminho, sheet_name=nome, header=None)
        except Exception:
            continue
        if bruto.empty:
            continue
        # A mesma pontuação do dispatcher: árvore antes de contagem. Escolher
        # o recorte só pelo tamanho classificava anos da MESMA série de forma
        # diferente — dois como balancete, cinco como demonstrativo.
        arvore, contas = max(
            (leitor._pontuar(r) for r in leitor._recortes(bruto)), default=(0, 0)
        )
        if contas < (1 if todas else min_contas):
            continue
        ano, mes = periodo_do_nome(nome)
        candidatas.append(
            AbaCandidata(
                nome=nome, contas=contas, ano=ano, mes=mes,
                tem_hierarquia=bool(arvore),
            )
        )
    return candidatas


def _motivo_de_arquivo_unico(caminho: Path) -> str:
    """Vazio quando o arquivo é um balancete conferível; o motivo, quando não."""
    from ..validators.hierarquia import conferir_hierarquia
    from .dispatcher import ParseyCaller

    try:
        contas = ParseyCaller(caminho).parse()
    except Exception as exc:
        return f"não consegui ler o arquivo ({type(exc).__name__})"
    if not contas:
        return "não consegui extrair conta nenhuma do arquivo"
    if not conferir_hierarquia(contas).tem_hierarquia:
        return (
            "o arquivo não traz código de conta hierárquico — sem árvore, o "
            "rollup e os totais não podem ser conferidos contra a origem"
        )
    return ""


@dataclass(frozen=True)
class DiagnosticoArquivo:
    """O que o arquivo é, na leitura do programa."""

    caminho: Path
    abas: list[AbaCandidata]
    motivo: str = ""

    @property
    def e_balancete_puro(self) -> bool:
        """O arquivo rende uma árvore de contas conferível?

        Com abas, basta uma ser balancete. Sem abas, decide o próprio arquivo
        (``motivo`` vazio = é balancete).

        Quando não é, o programa **não sabe** onde está o balanço e não deve
        fingir que sabe: a extração até acontece, mas rollup e totais não podem
        ser conferidos contra a origem. Aí a pergunta vai para quem sabe.
        """
        if not self.abas:
            return not self.motivo
        return any(a.tipo == BALANCETE for a in self.abas)

    @property
    def precisa_perguntar(self) -> bool:
        return bool(self.abas) and not self.e_balancete_puro


def diagnosticar(caminho: str | Path) -> DiagnosticoArquivo:
    """
    Este arquivo é um balancete puro? Se não, por quê — e o que ele tem dentro.

    Nasceu de dois arquivos reais que chegaram como "balancete" e não são:
    a empresa já havia feito a consolidação, numa aba ``Consolidado`` (uma
    linha por conta do BP, uma coluna por empresa) e numa ``Output Modelo (BP)``
    (De-Para em inglês, períodos em colunas). O programa lia alguma aba, tirava
    centenas de contas e entregava — sem conseguir conferir nada contra a
    origem, porque origem hierárquica não havia.

    Dizer "não parece um balancete puro; em qual aba está o balanço?" é mais
    honesto e mais útil que escolher sozinho: o trabalho já está feito, o que
    falta é o template.
    """
    caminho = Path(caminho)
    abas = listar_abas(caminho, todas=True)
    if not abas:
        # Aba única (ou formato sem abas): não há o que escolher, mas o arquivo
        # ainda pode ser um balancete perfeito — e dizer que não é, por falta
        # de abas para listar, seria o pior tipo de erro: um "não" que não foi
        # medido. Aqui a resposta vem do próprio arquivo.
        return DiagnosticoArquivo(caminho, [], motivo=_motivo_de_arquivo_unico(caminho))
    if any(a.tipo == BALANCETE for a in abas):
        return DiagnosticoArquivo(caminho, abas)
    return DiagnosticoArquivo(
        caminho,
        abas,
        motivo=(
            "nenhuma aba traz código de conta hierárquico — o arquivo parece "
            "um demonstrativo já padronizado, não um balancete. Sem árvore, o "
            "rollup e os totais não podem ser conferidos contra a origem."
        ),
    )
