"""
A conferência que faltava: **o total entregue bate com o total da origem?**

Por que este módulo existe
--------------------------

O revisor colocou a pergunta no lugar certo:

    "Qual é o ativo desses balancetes? Se o ativo desses balancetes soma dois
    milhões de reais, o ativo do resultado que você vai encontrar deve somar
    dois milhões de reais."

Havia centenas de testes e nenhum respondia isso. Todos mediam **proxies**:
quantas contas casaram, se a árvore da origem é consistente, se cada linha
escrita é capturada por uma linha do template. Um proxy pode ficar verde com o
número final errado — e ficou. O Ativo de um balancete real saiu 2.683.506,57
contra 2.361.053,53 declarados na origem, com toda a suíte verde.

O motivo do ponto cego é estrutural: **escrever em ``_dados_padronizados`` não
põe número na entrega**. Quem soma são as fórmulas do template, e nada em
Python as executava. Entre o último teste e o número que o cliente lê havia uma
camada inteira que ninguém avaliava.

Este módulo executa essa camada.

O que ele faz
-------------

1. :func:`avaliar_demonstrativo` interpreta as fórmulas de BP_GT/DRE_GT
   exatamente como o Excel as interpretaria — inclusive o curinga ``*`` do
   SUMIFS, que é o ponto onde a dupla contagem apareceria.
2. :func:`conferir_totais` compara o resultado com os **totalizadores da
   origem**. O balancete quase sempre traz "ATIVO" como linha de totalização;
   é o número mais fácil de achar e o único que interessa conferir.
3. :func:`conferir_dre` faz o mesmo do outro lado: o lucro líquido entregue
   tem de ser ``Receitas - Despesas`` do balancete. O Balanço pode fechar com
   a DRE inteira errada — aconteceu, quando uma receita de R$ 4,9 milhões
   entrou como custo negativo e o Ativo continuou correto.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

#: Tolerância absoluta, na moeda da entrega (milhares por default). Um centavo
#: de milhar = R$ 0,01 ao cliente.
TOLERANCIA = 0.01

_ABA_DADOS = "_dados_padronizados"

#: ``SUMIFS(_dados_padronizados!C:C, _dados_padronizados!$A:$A, <critério>)``
#: onde o critério é um literal ``"1.01*"`` ou a forma ``$C9&"*"``.
_SUMIFS_RE = re.compile(
    r"SUMIFS\(\s*" + _ABA_DADOS + r"!([A-Z]+):[A-Z]+\s*,\s*"
    r"" + _ABA_DADOS + r"!\$A:\$A\s*,\s*"
    r'(?:"([^"]*)"|\$?C(\d+)\s*&\s*"([^"]*)")\s*\)'
)
_SUM_RE = re.compile(r"SUM\(([A-Z]+)(\d+):([A-Z]+)(\d+)\)")
_IFERROR_RE = re.compile(r"IFERROR\((.*),\s*0\)\s*$")
_CELULA_RE = re.compile(r"\b([A-Z]+)(\d+)\b")
_SEGURO_RE = re.compile(r"^[\d\s.+\-*/()e]*$")

_COL_ROTULO = 2
_COL_CODIGO = 3


def _curinga_para_regex(padrao: str) -> re.Pattern[str]:
    """Traduz o curinga do Excel. ``*`` casa qualquer sequência, ``?`` um char."""
    return re.compile(
        re.escape(padrao).replace(r"\*", ".*").replace(r"\?", ".") + r"\Z"
    )


@dataclass
class Conferencia:
    """Um total da entrega contra o mesmo total na origem."""

    nome: str
    origem: float
    entrega: float

    @property
    def diferenca(self) -> float:
        return self.entrega - self.origem

    @property
    def confere(self) -> bool:
        return abs(self.diferenca) <= TOLERANCIA

    def __str__(self) -> str:
        marca = "OK" if self.confere else "NÃO"
        return (
            f"{self.nome}: origem {self.origem:,.2f} / entrega "
            f"{self.entrega:,.2f} / diferença {self.diferenca:+,.2f} [{marca}]"
        )


@dataclass
class RelatorioEntrega:
    """Resultado da conferência ponta a ponta."""

    conferencias: list[Conferencia] = field(default_factory=list)
    #: Rótulo -> valor, de todas as linhas avaliadas. Para diagnóstico.
    linhas: dict[str, float] = field(default_factory=dict)
    motivo_nao_conferido: str = ""

    @property
    def conferivel(self) -> bool:
        return bool(self.conferencias)

    @property
    def confere(self) -> bool:
        return self.conferivel and all(c.confere for c in self.conferencias)

    @property
    def divergentes(self) -> list[Conferencia]:
        return [c for c in self.conferencias if not c.confere]

    def mensagem(self) -> str:
        if not self.conferivel:
            return f"não foi possível conferir: {self.motivo_nao_conferido}"
        if self.confere:
            return "os totais da entrega batem com os da origem"
        return "; ".join(str(c) for c in self.divergentes)


def avaliar_demonstrativo(wb, aba: str, coluna: str = "D") -> dict[str, float]:
    """
    Avalia uma coluna de BP_GT/DRE_GT como o Excel avaliaria.

    Interpreta as formas que o template usa — ``IFERROR``, ``SUMIFS`` (com o
    curinga), ``SUM(intervalo)`` e aritmética entre células da mesma coluna.
    ``IF``/``ROUND`` (a linha de *check*) não são avaliadas: são apresentação,
    não valor.

    Devolve ``{rótulo da linha: valor}``.
    """
    if aba not in wb.sheetnames or _ABA_DADOS not in wb.sheetnames:
        return {}

    registros = _ler_dados(wb[_ABA_DADOS])
    ws = wb[aba]
    letra_para_indice = {chr(ord("A") + i): i + 1 for i in range(26)}
    col_idx = letra_para_indice.get(coluna.upper(), 4)
    memo: dict[int, float] = {}

    def valor_da_linha(linha: int) -> float:
        if linha in memo:
            return memo[linha]
        memo[linha] = 0.0  # corta ciclo antes de recorrer
        bruto = ws.cell(row=linha, column=col_idx).value
        if isinstance(bruto, (int, float)):
            memo[linha] = float(bruto)
            return memo[linha]
        if not isinstance(bruto, str) or not bruto.startswith("="):
            return 0.0

        expr = bruto[1:]
        if expr.upper().startswith("IF("):
            return 0.0  # linha de check: apresentação, não valor

        def resolver_sumifs(m: re.Match[str]) -> str:
            coluna_valor, literal, referencia, sufixo = m.groups()
            if literal is not None:
                padrao = literal
            else:
                base = ws.cell(row=int(referencia), column=_COL_CODIGO).value
                padrao = f"{str(base or '').strip()}{sufixo}"
            regex = _curinga_para_regex(padrao)
            return repr(
                sum(
                    valores.get(coluna_valor, 0.0)
                    for codigo, valores in registros
                    if regex.match(codigo)
                )
            )

        expr = _SUMIFS_RE.sub(resolver_sumifs, expr)
        expr = _IFERROR_RE.sub(r"(\1)", expr)
        expr = _SUM_RE.sub(
            lambda m: repr(
                sum(valor_da_linha(x) for x in range(int(m.group(2)), int(m.group(4)) + 1))
            ),
            expr,
        )
        expr = _CELULA_RE.sub(lambda m: repr(valor_da_linha(int(m.group(2)))), expr)

        # Depois das substituições só pode restar aritmética. Se sobrou nome de
        # função ou referência, a fórmula usa algo que este avaliador não
        # modela — devolver 0 calado seria fabricar um "confere".
        if not _SEGURO_RE.match(expr):
            raise ValueError(
                f"{aba}!{coluna}{linha}: fórmula não modelada por este "
                f"avaliador, sobrou {expr!r}"
            )
        memo[linha] = float(eval(expr))
        return memo[linha]

    resultado: dict[str, float] = {}
    for linha in range(1, ws.max_row + 1):
        rotulo = ws.cell(row=linha, column=_COL_ROTULO).value
        if rotulo and str(rotulo).strip():
            resultado[str(rotulo).strip()] = valor_da_linha(linha)
    return resultado


def _ler_dados(ws) -> list[tuple[str, dict[str, float]]]:
    """``_dados_padronizados`` como ``(código, {coluna: valor})``."""
    letras = {i + 1: chr(ord("A") + i) for i in range(26)}
    registros: list[tuple[str, dict[str, float]]] = []
    for linha in range(2, ws.max_row + 1):
        codigo = ws.cell(row=linha, column=1).value
        if not codigo:
            continue
        valores = {}
        for indice, letra in letras.items():
            bruto = ws.cell(row=linha, column=indice).value
            if isinstance(bruto, (int, float)) and not isinstance(bruto, bool):
                valores[letra] = float(bruto)
        registros.append((str(codigo).strip(), valores))
    return registros


#: Rótulos que carregam o total de cada lado do Balanço, e a classe da origem
#: com que cada um tem de bater.
TOTAIS_DO_BALANCO = (
    ("ATIVO TOTAL", "ATIVO"),
    ("PASSIVO + PATRIMÔNIO LÍQUIDO", "PASSIVO"),
)

#: Rótulo do resultado final na DRE do template.
ROTULO_LUCRO_LIQUIDO = "(=) LUCRO LÍQUIDO DO EXERCÍCIO"


def conferir_dre(
    wb,
    resultado_da_origem: float,
    coluna: str = "D",
    nao_coberto: float = 0.0,
) -> RelatorioEntrega:
    """
    O lucro líquido entregue é ``Receitas - Despesas`` do balancete?

    Por que separado do Balanço
    ---------------------------

    O Balanço pode fechar com a DRE inteira errada, e foi o que aconteceu: uma
    receita de serviços de R$ 4.937.529,00 entrou como **custo negativo**
    (``(-) Custo dos Serviços Prestados``, score 1.0 vindo do cache). O Ativo
    continuou certo — ele não depende da DRE —, e a receita simplesmente não
    aparecia em lugar nenhum enquanto o custo inflava pelo mesmo valor.

    Nenhuma conferência do lado do Balanço pega isso. Esta pega: o lucro
    líquido da entrega tem de ser, ao centavo, a diferença entre os
    totalizadores de receita e de despesa do balancete.

    A identidade
    ------------

    Como no Balanço, não basta ``entrega == origem``: uma conta de resultado
    pode legitimamente não ter linha no template, e o valor dela fica de fora
    por decisão reportada. O que se exige é::

        entrega + não coberto == resultado da origem

    ``resultado_da_origem`` vem de :func:`bp.utils.natureza.resultado_do_periodo`,
    que escolhe a fórmula pela convenção do balancete — usar a errada produz um
    "não bate" que é da régua, não do dado.
    """
    relatorio = RelatorioEntrega()
    if not resultado_da_origem:
        relatorio.motivo_nao_conferido = (
            "o balancete não traz contas de resultado com totalizador"
        )
        return relatorio

    relatorio.linhas = avaliar_demonstrativo(wb, "DRE_GT", coluna)
    if not relatorio.linhas:
        relatorio.motivo_nao_conferido = "DRE_GT ou _dados_padronizados ausente"
        return relatorio
    if ROTULO_LUCRO_LIQUIDO not in relatorio.linhas:
        relatorio.motivo_nao_conferido = (
            f"a DRE do template não traz a linha {ROTULO_LUCRO_LIQUIDO!r}"
        )
        return relatorio

    relatorio.conferencias.append(
        Conferencia(
            nome="LUCRO LÍQUIDO DO EXERCÍCIO",
            origem=resultado_da_origem,
            entrega=relatorio.linhas[ROTULO_LUCRO_LIQUIDO] + nao_coberto,
        )
    )
    return relatorio


def conferir_totais(
    wb,
    totais_da_origem: dict[str, float],
    coluna: str = "D",
    resultado_transferido: float = 0.0,
) -> RelatorioEntrega:
    """
    O Ativo entregue é o Ativo da origem? E o Passivo + PL?

    ``totais_da_origem`` vem de ``RelatorioHierarquia.totais_por_classe`` — a
    soma das raízes de cada classe, que num balancete é a própria linha
    "ATIVO". Como o template exige os dois lados positivos e a origem pode
    trazer o Passivo negativo, a comparação é feita em módulo.

    ``resultado_transferido`` entra na expectativa do lado do Passivo: num
    balancete **aberto** o lucro do período ainda não foi levado ao PL, e a
    entrega o lança lá para o Balanço fechar. Sem somá-lo aqui, a conferência
    acusaria como erro justamente a correção — e no corpus a maioria dos
    balancetes é aberta, então o teste ficaria vermelho por estar certo.

    Sem totalizador na origem não há o que conferir, e o relatório diz isso em
    vez de devolver um "confere" vazio.
    """
    relatorio = RelatorioEntrega()
    if not totais_da_origem:
        relatorio.motivo_nao_conferido = (
            "o balancete não traz totalizador de classe (sem hierarquia)"
        )
        return relatorio

    relatorio.linhas = avaliar_demonstrativo(wb, "BP_GT", coluna)
    if not relatorio.linhas:
        relatorio.motivo_nao_conferido = "BP_GT ou _dados_padronizados ausente"
        return relatorio

    for rotulo, classe in TOTAIS_DO_BALANCO:
        if rotulo not in relatorio.linhas or classe not in totais_da_origem:
            continue
        esperado = abs(totais_da_origem[classe])
        if classe == "PASSIVO":
            esperado += resultado_transferido
        relatorio.conferencias.append(
            Conferencia(
                nome=rotulo,
                origem=esperado,
                entrega=abs(relatorio.linhas[rotulo]),
            )
        )
    if not relatorio.conferencias:
        relatorio.motivo_nao_conferido = (
            "nenhum total do Balanço pôde ser pareado com a origem"
        )
    return relatorio
