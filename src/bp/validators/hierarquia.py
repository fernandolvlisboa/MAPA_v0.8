"""
Conferência hierárquica do balancete — a aritmética que valida a extração.

Um balancete não é uma lista de contas: é uma **árvore** em que cada conta
sintética declara um saldo que deve ser igual à soma dos seus filhos diretos.

    2.1.1.01        EMPRÉSTIMOS                       -194.622,59
    ├ ...0002       EMPRÉSTIMO BANCÁRIO SICOOB         -42.708,96
    ├ ...0004       CONTA GARANTIDA - SICREDI RBM      -50.000,00
    ├ ...0010       EMPRESTIMO SANTANDER              -136.811,42
    ├ ...0010       JUROS A APROPRIAR - CURTO PRAZO     73.254,70
    └ ...009        EMPRESTIMO CREDIMATA - 624703      -38.356,91
                                                     ─────────────
                                                     -194.622,59  ✓

Essa identidade é a checagem mais barata e mais forte que existe sobre a
extração: se a soma bate em todos os pais, o parser leu tudo, leu certo e não
perdeu nem inventou linha.

Medido no corpus (31 arquivos, ver ``tests/test_corpus_regressao.py``): 17
expõem hierarquia e **14 fecham em todos os agrupadores**. Os 3 que não fecham
são os ``.TXT``, todos pela mesma causa — o parser de largura fixa perde o
sinal das contas redutoras. O exemplo acima vem do balancete RBM, que é o
**pior caso** do corpus em cobertura de valor (88,6%, contra 100% em quatro
dos sete medidos); usá-lo como ilustração é proposital, usá-lo como referência
única seria sobreajuste.

Duas armadilhas que este módulo trata e que custaram caro
--------------------------------------------------------
1. **Código repetido é normal.** No RBM, ``2.1.1.01.0010`` aparece duas vezes
   (EMPRESTIMO SANTANDER e JUROS A APROPRIAR). Nove códigos se repetem, o que
   representa 12 contas. Qualquer estrutura ``dict[codigo] = conta`` **descarta
   as repetidas em silêncio** — e foi exatamente o que fez 4 dos 80 rollups
   "falharem" numa primeira medição: o defeito estava no medidor, não no dado.
   Aqui tudo é agrupado em ``dict[codigo] -> list[conta]``.

2. **Contas com nome próprio não devem ser mapeadas uma a uma.**
   "SICOOB - UNISUDESTE - RBM 62540-0" não existe em plano de contas nenhum, e
   nem precisa: o agrupador dela ("BANCOS CONTA MOVIMENTO") existe e já carrega
   o total. ``selecionar_para_projecao`` desce a árvore e **para no nível
   mapeado mais alto**, o que resolve de uma vez os dois erros opostos:
   projetar pai *e* filhos (dupla contagem) ou deixar a folha não mapeada cair
   fora (valor perdido — a causa de o balanço não fechar).
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from collections.abc import Callable, Iterable
from itertools import product as _product
from dataclasses import dataclass, field
from typing import Any

from ..utils.codigo import classe_from_codigo
from ..utils.numero import parse_saldo
from ..utils.synonyms import is_garbage_description

__all__ = [
    "TOLERANCIA",
    "Divergencia",
    "RelatorioHierarquia",
    "agrupar_por_codigo",
    "canonicalizar_contas",
    "chave_hierarquica",
    "conferir_hierarquia",
    "detectar_largura_fixa",
    "e_linha_de_total",
    "mapear_filhos",
    "participa_da_arvore",
    "selecionar_para_projecao",
    "valor_do_grupo",
]

#: Tolerância absoluta em reais. Balancete fecha ao centavo; a folga existe só
#: para o erro de ponto flutuante acumulado na soma.
TOLERANCIA = 0.01

#: Código hierárquico de verdade: "1", "1.1", "2.1.1.01.0010".
#: A estratégia description-first do dispatcher preenche ``codigo`` com a
#: descrição quando a origem não tem coluna de código, e linhas de totalização
#: do balancete chegam com um NÚMERO nos dois campos (ex.: código
#: ``"-2647871.8"``, descrição ``"3166245.14"``). Oito dessas linhas-fantasma
#: no balancete RBM somavam 20,7 milhões de totais inexistentes e faziam a
#: equação contábil "não fechar" — o defeito estava no medidor, não no dado.
_CODIGO_HIERARQUICO_RE = re.compile(r"^\d+(\.\d+)*$")

#: Descrição de uma linha de **totalização geral** da demonstração: o grande
#: total do Ativo, do Passivo, o total geral. Não é conta — é uma soma que o
#: template recalcula sozinho —, e num plano em que esse total é codificado
#: dentro de um grupo (COSIF: ``3.9.9.99.99 TOTAL DO ATIVO``, ``9.9.9.99.99
#: TOTAL DO PASSIVO``) ela entrava na árvore como se fosse conta e virava um
#: valor gigante no lugar errado. É distinta de "Total do Ativo Circulante",
#: que é subtotal de um bloco e a hierarquia já trata pela soma dos filhos —
#: por isso o padrão casa só o total do Ativo/Passivo/Geral INTEIRO: nada
#: depois da palavra, salvo o "e Patrimônio Líquido" que fecha o Passivo.
_LINHA_DE_TOTAL_RE = re.compile(
    r"^total\s+(?:d[oae]s?\s+)?"
    r"(?:ativo|passivo(?:\s*[e+]\s*patrimonio\s+liquido)?|geral|"
    r"exercicio|balanco|patrimonio\s+liquido)"
    r"\s*$",
)


def _sem_acento(texto: Any) -> str:
    return "".join(
        c
        for c in unicodedata.normalize("NFD", str(texto or "").strip().lower())
        if unicodedata.category(c) != "Mn"
    )


def e_linha_de_total(descricao: Any) -> bool:
    """A descrição é a de uma linha de totalização geral da demonstração?"""
    return bool(_LINHA_DE_TOTAL_RE.match(_sem_acento(descricao)))


#: Fração mínima de códigos com "zero interior" (um segmento zero seguido de
#: outro não-zero) para reconhecer um plano de **largura fixa com padding** —
#: COSIF e vários ERPs. Nos balancetes de PJ do corpus a fração é 0,0%; no
#: balancete de banco medido é 37,8%. O limite folgado separa os dois sem
#: ambiguidade.
_FRACAO_PADDING_FIXO = 0.15


def _tem_zero_interior(codigo: str) -> bool:
    """``1.1.2.30.00.00003`` tem — o ``00`` no meio, seguido do id ``00003``."""
    try:
        vals = [int(s) for s in codigo.split(".")]
    except ValueError:
        return False
    return any(
        vals[i] == 0 and any(v != 0 for v in vals[i + 1 :])
        for i in range(len(vals) - 1)
    )


def detectar_largura_fixa(codigos: Iterable[str]) -> int | None:
    """
    Largura ``W`` de um plano de código **fixo com padding**, ou ``None``.

    Planos como o COSIF escrevem a hierarquia em posições fixas, preenchendo
    com zero os níveis não usados e reservando o último segmento para um id
    sequencial da subconta: ``1.1.2.30.00.00003`` é o nó ``1.1.2.30``, não uma
    conta seis níveis abaixo. Nesses planos o pai não é prefixo-de-ponto do
    filho (``1.1.2.30.00.00003`` não é prefixo de ``1.1.2.30.02.00007``), então
    ``mapear_filhos`` não montava a árvore: **342 de 414 contas viravam raiz** e
    o total de cada classe somava pai + filho + neto, inflando o Ativo de
    R$ 30,9 mi para R$ 181 mi.

    Reconhece o estilo pela presença de "zero interior" em fração relevante dos
    códigos. Os balancetes de PJ do corpus têm 0,0% (nenhum efeito — o código
    volta intacto); um balancete de banco tem 37,8%.
    """
    hier = [
        c
        for c in (str(x).strip() for x in codigos)
        if _CODIGO_HIERARQUICO_RE.fullmatch(c)
    ]
    if len(hier) < 10:
        return None
    fracao = sum(1 for c in hier if _tem_zero_interior(c)) / len(hier)
    if fracao < _FRACAO_PADDING_FIXO:
        return None
    largura = max(len(c.split(".")) for c in hier)
    return largura if largura >= 5 else None


def _e_padding(segmento: str) -> bool:
    """Segmento só de zeros — nível não usado (``0``, ``00``, ``000``)."""
    s = segmento.strip()
    return s != "" and set(s) == {"0"}


def chave_hierarquica(codigo: str, largura: int | None) -> str:
    """
    Chave canônica de um código, para que a árvore aninhe por prefixo de ponto.

    Sem plano fixo (``largura is None``) devolve o código intacto — é o estilo
    de código variável (``1``, ``1.1``, ``2.1.1.01.0010``) do corpus, em que o
    prefixo de ponto já é a hierarquia.

    Com plano fixo, distingue **nó-agregado** de **folha analítica** pelo
    padding, e é essa distinção que evita fundir contas distintas:

    - **Nó-agregado** — tem um segmento-zero nos níveis (``1.1.2.30.00.00003``,
      o ``00`` no 5º nível): o último segmento é só o id da linha totalizadora.
      Descarta-se o id e aparam-se os zeros → ``1.1.2.30``. ``1.0.0.00.00.00007``
      (o grupo inteiro) vira ``1``.
    - **Folha analítica** — todos os níveis preenchidos (``1.2.2.10.20.00004``,
      ``1.2.2.10.20.00035``): o último segmento é a própria folha e **fica**.
      As duas continuam chaves distintas — não se pode somá-las como se fossem
      a mesma conta —, e ambas aninham sob o nó ``1.2.2.10`` por prefixo.

    O aninhamento por prefixo de ponto faz o resto: ``1.1.2.30.02.00007`` (folha)
    é filho de ``1.1.2.30`` (nó). Fundir só acontece entre linhas que já eram o
    mesmo código — código repetido é normal em balancete real e o motor soma,
    como no RBM.
    """
    if largura is None:
        return codigo
    segs = codigo.split(".")
    if len(segs) >= largura and largura >= 5:
        niveis = segs[:-1]  # último = id sequencial da subconta
        if any(_e_padding(s) for s in niveis):
            # Nó-agregado: apara os níveis-zero à direita.
            while len(niveis) > 1 and _e_padding(niveis[-1]):
                niveis = niveis[:-1]
            return ".".join(niveis)
        # Folha totalmente especificada: mantém o código inteiro (o id é a folha).
        return codigo
    # Forma curta (menos segmentos que a largura cheia): já é o próprio nível.
    while len(segs) > 1 and _e_padding(segs[-1]):
        segs = segs[:-1]
    return ".".join(segs)


def canonicalizar_contas(contas: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Normaliza os códigos de origem para que a hierarquia aninhe corretamente.

    Detecta o estilo do plano uma vez (largura fixa com padding vs. código
    variável). Se for variável — o caso de todo o corpus de PJ — devolve as
    contas **sem mudança nenhuma**. Se for fixo, reescreve ``codigo`` para a
    chave canônica e guarda o original em ``codigo_original`` para
    rastreabilidade. É idempotente: rodar de novo sobre contas já canônicas não
    reencontra padding e devolve tudo igual.

    Preserva a contagem de linhas (1:1); a fusão de nós repetidos é feita
    depois, pela agregação por código, exatamente como já era.
    """
    contas = list(contas)
    codigos = [str(c.get("codigo", "")).strip() for c in contas]
    largura = detectar_largura_fixa(codigos)
    if largura is None:
        return contas
    novas: list[dict[str, Any]] = []
    for conta, codigo in zip(contas, codigos):
        chave = (
            chave_hierarquica(codigo, largura)
            if _CODIGO_HIERARQUICO_RE.fullmatch(codigo)
            else codigo
        )
        nova = dict(conta)
        nova["codigo"] = chave
        nova.setdefault("codigo_original", codigo)
        novas.append(nova)
    return novas


def participa_da_arvore(conta: dict[str, Any]) -> bool:
    """
    A conta é um nó da hierarquia?

    Exige código hierárquico **e** descrição que não seja lixo nem linha de
    totalização geral. As condições são necessárias: as linhas de totalização
    numéricas do balancete chegam com um número nos dois campos, e
    ``"4389425.29"`` casa o formato de código hierárquico tão bem quanto
    ``"1.1.01"`` — quem sabe distinguir é ``is_garbage_description``; e a linha
    de "TOTAL DO ATIVO/PASSIVO" tem descrição legítima mas é soma, não conta,
    e o template recalcula os totais sozinho.
    """
    codigo = str(conta.get("codigo", "")).strip()
    if not _CODIGO_HIERARQUICO_RE.fullmatch(codigo):
        return False
    descricao = str(conta.get("descricao", ""))
    if is_garbage_description(descricao):
        return False
    return not e_linha_de_total(descricao)


@dataclass(frozen=True)
class Divergencia:
    """Um pai cuja soma dos filhos não bate com o saldo declarado."""

    codigo: str
    descricao: str
    declarado: float
    somado: float
    n_filhos: int

    @property
    def diferenca(self) -> float:
        return self.declarado - self.somado

    def __str__(self) -> str:
        return (
            f"{self.codigo} ({self.descricao}): declarado {self.declarado:,.2f} "
            f"!= soma de {self.n_filhos} filho(s) {self.somado:,.2f} "
            f"[diferença {self.diferenca:,.2f}]"
        )


@dataclass
class RelatorioHierarquia:
    """Resultado da conferência aritmética de um balancete."""

    total_contas: int = 0
    #: Contas sem código hierárquico — não participam da árvore. Inclui as
    #: linhas de totalização que o parser emite com descrição numérica.
    fora_da_arvore: int = 0
    pais_conferidos: int = 0
    divergencias: list[Divergencia] = field(default_factory=list)
    #: código -> quantas vezes aparece (só os repetidos)
    codigos_duplicados: dict[str, int] = field(default_factory=dict)
    #: classe contábil -> soma das raízes daquela classe
    totais_por_classe: dict[str, float] = field(default_factory=dict)
    #: dígito-raiz -> soma das raízes com aquele dígito. Mais fino que
    #: ``totais_por_classe``, que funde 3..9 em "RESULTADO": é o que permite
    #: distinguir Custos (3) de Receitas (4) num plano de quatro classes e
    #: reconhecer que a DRE **subtrai**. Ver ``desequilibrio``.
    totais_por_raiz: dict[str, float] = field(default_factory=dict)
    #: Quantas contas chegaram com saldo legível. ``0`` significa que a coluna
    #: de valor não foi lida — e então **nada** aqui vale como conferência.
    contas_com_saldo: int = 0

    @property
    def pais_divergentes(self) -> int:
        return len(self.divergencias)

    @property
    def saldos_legiveis(self) -> bool:
        """
        Metade das contas trouxe saldo?

        Sem esta guarda a conferência é vácuo puro: ``_saldo`` devolve ``0.0``
        para saldo ilegível, então um balancete em que **nenhum** valor foi lido
        tem todo pai batendo com a soma dos filhos (0 == 0) e a equação contábil
        fechando (0 == 0). Foi o que aconteceu com as abas "Balancetes 2024" e
        "Balancetes 2025" do SmartRio: 773 de 774 e 821 de 824 contas com
        ``saldo=None``, e o relatório dizia "184 pais conferem, equação fecha".

        Meio a meio é folgado de propósito — balancete real tem conta zerada e
        conta sem saldo —, mas separa "quase tudo lido" de "quase nada lido".
        """
        return self.total_contas > 0 and self.contas_com_saldo * 2 >= self.total_contas

    @property
    def tem_hierarquia(self) -> bool:
        """
        Existe árvore para conferir?

        Um balancete sem coluna de código (o dispatcher cai para
        description-first e usa a descrição como código) não tem pai nenhum.
        Sem esta guarda, ``rollup_integro`` devolveria ``True`` por vacuidade —
        exatamente o tipo de "verde que não valida nada" que esta suíte existe
        para impedir.
        """
        return self.pais_conferidos + self.pais_divergentes > 0

    @property
    def rollup_integro(self) -> bool:
        """
        Todo pai confere com a soma dos filhos.

        Falso se não há árvore **ou** se não há saldo — os dois modos de um
        relatório ficar verde sem ter conferido coisa alguma.
        """
        return self.tem_hierarquia and self.saldos_legiveis and not self.divergencias

    @property
    def desequilibrio(self) -> float:
        """
        O quanto sobra da equação contábil, sob a convenção que o arquivo usa.

        Deve ser ~0. **Qual soma zera depende da convenção de sinais**, e há
        duas no mundo real — daí este método não ser um ``sum()``:

        - **sinal explícito** (ECF, plano referencial): o passivo e a receita
          já vêm negativos, então ``Ativo + Passivo + Resultado`` é que zera;
        - **natureza implícita** (muito balancete de sistema brasileiro): tudo
          vem positivo e a classe é que diz o lado. Aí a equação é
          ``Ativo - Passivo - (Receitas - Custos) = 0``.

        Somar tudo sob a segunda convenção acusa um desequilíbrio que não
        existe. Foi o que aconteceu com o balancete Trindade, um plano de
        **quatro** classes (1 Ativo, 2 Passivo, 3 Custos, 4 Receitas), todas
        positivas::

            Ativo    2.361.053,53      soma ingênua:
            Passivo    891.480,90        2.361.053,53
            Custos   3.472.327,21      + 891.480,90
            Receitas 4.941.899,84      + 8.414.227,05  (3 e 4 juntas)
                                       = 11.666.761,48   "não fecha"

        Mas 891.480,90 + (4.941.899,84 - 3.472.327,21) = 2.361.053,53 = Ativo.
        **Fechava exatamente**, e o programa mandava não entregar a planilha.

        Como se resolve sem adivinhar a convenção: procura-se a atribuição de
        sinais às classes que zera a soma. A atribuição toda-``+1`` é a
        convenção de sinal explícito, então tudo que fechava antes continua
        fechando — este método só acrescenta leituras, nunca remove. Com no
        máximo cinco classes são 16 combinações; o custo é irrelevante e a
        chance de dois totais de balancete real se cancelarem por acaso, nula.

        Devolve o menor resíduo entre as leituras possíveis: se alguma zera, é
        ela que vale.
        """
        return residuo_da_equacao(
            self.totais_por_raiz.values() or self.totais_por_classe.values()
        )

    @property
    def equacao_fecha(self) -> bool:
        if not self.saldos_legiveis:
            return False
        base = max(
            (abs(v) for v in self.totais_por_classe.values()), default=1.0
        )
        return abs(self.desequilibrio) <= max(TOLERANCIA, base * 1e-6)

    def resumo(self) -> str:
        if not self.saldos_legiveis:
            return (
                f"{self.total_contas} contas | SEM SALDO LEGÍVEL — só "
                f"{self.contas_com_saldo} conta(s) trouxeram valor; a coluna de "
                f"saldo não foi lida e nenhuma conferência vale"
            )
        if not self.tem_hierarquia:
            return (
                f"{self.total_contas} contas | SEM HIERARQUIA — o balancete não "
                f"traz código hierárquico, nenhuma conferência é possível"
            )
        linhas = [
            f"{self.total_contas} contas | "
            f"{self.pais_conferidos} pais conferem, {self.pais_divergentes} divergem"
        ]
        if self.fora_da_arvore:
            linhas.append(f"{self.fora_da_arvore} fora da árvore")
        if self.codigos_duplicados:
            repetidas = sum(n - 1 for n in self.codigos_duplicados.values())
            linhas.append(
                f"{len(self.codigos_duplicados)} código(s) repetido(s) "
                f"({repetidas} conta(s) a mais) — normal em balancete real"
            )
        linhas.append(
            "equação contábil "
            + ("fecha" if self.equacao_fecha else f"NÃO fecha ({self.desequilibrio:,.2f})")
        )
        return " | ".join(linhas)


#: Acima disso a busca por sinais deixa de ser conservadora: com muitas
#: classes cresce a chance de uma combinação zerar por acaso, e aí o "fecha"
#: não significa mais nada. Plano contábil real tem 3 ou 4.
MAX_CLASSES_PARA_BUSCA = 5


def residuo_da_equacao(totais: Iterable[float]) -> float:
    """
    O que sobra da equação contábil, sob a convenção de sinais que o arquivo usa.

    Existem duas convenções no mundo real, e nenhuma é detectável olhando um
    total isolado:

    - **sinal explícito** (ECF, plano referencial): passivo e receita já vêm
      negativos, então ``Ativo + Passivo + Resultado`` é que zera;
    - **natureza implícita** (muito sistema brasileiro): tudo vem positivo e a
      classe é que diz o lado — ``Ativo - Passivo - (Receitas - Custos) = 0``.

    Em vez de adivinhar, procura-se a atribuição de sinais que zera a soma. A
    atribuição toda-``+1`` é a convenção de sinal explícito, então tudo que
    fechava pela soma simples continua fechando: este método só acrescenta
    leituras, nunca remove.

    O sinal do primeiro total fica fixo em ``+1`` — negar tudo dá o mesmo
    resíduo em módulo, então metade das combinações é redundante.

    **Passe os totais o mais desagregado possível.** Com Custos e Receitas já
    somados num "RESULTADO" único, a subtração da DRE é invisível e nenhuma
    combinação de sinais a recupera. Foi exatamente esse o defeito: a mesma
    conta aparecia certa na conferência da origem e errada na reconciliação da
    entrega, porque as duas somavam agregações diferentes. Esta função existe
    para que haja **uma** implementação, e não duas que divergem.
    """
    valores = list(totais)
    if not valores:
        return 0.0
    if len(valores) > MAX_CLASSES_PARA_BUSCA:
        return sum(valores)
    return min(
        (
            sum(s * v for s, v in zip((1, *combinacao), valores))
            for combinacao in _product((1, -1), repeat=len(valores) - 1)
        ),
        key=abs,
    )


def _saldo(conta: dict[str, Any]) -> float:
    return parse_saldo(conta.get("saldo")) or 0.0


def valor_do_grupo(saldos: list[float]) -> float:
    """
    Valor de um nó cujos lançamentos caíram na mesma chave (código repetido).

    Duas realidades caem aqui, e a regra separa as duas pela **identidade do
    rollup**:

    - **Subtotal + detalhe** (COSIF): dentro de ``8.1.7.33`` a linha
      ``…00004 PROVENTOS`` (849.558,97) já é a soma de FÉRIAS, SALÁRIO, 13º…
      que valem os mesmos 849.558,97. Somar tudo conta em dobro. Se UM
      lançamento é igual à soma dos demais, ele é o subtotal — devolve só ele.
    - **Contas homônimas distintas** (RBM: ``2.1.1.01.0010`` cobre EMPRÉSTIMO
      SANTANDER e JUROS A APROPRIAR, -200 e -100): nenhuma é a soma da outra, e
      a resposta é a soma — o comportamento de sempre.
    """
    total = sum(saldos)
    if len(saldos) > 1:
        for s in saldos:
            if abs(s - (total - s)) <= TOLERANCIA:
                return s
    return total


def agrupar_por_codigo(contas: Iterable[dict[str, Any]]) -> dict[str, list[dict]]:
    """
    Agrupa contas por código, **preservando as repetidas**.

    Um ``dict[codigo] = conta`` perderia 12 das 537 contas do balancete RBM.
    """
    grupos: dict[str, list[dict]] = defaultdict(list)
    for conta in contas:
        if participa_da_arvore(conta):
            grupos[str(conta["codigo"]).strip()].append(conta)
    return dict(grupos)


def mapear_filhos(grupos: dict[str, list[dict]]) -> dict[str, list[str]]:
    """
    Pai -> filhos diretos, derivado do prefixo do código.

    "Direto" é o ancestral **mais próximo que existe no balancete**: se o
    balancete traz ``1.1`` e ``1.1.1.02`` mas não ``1.1.1``, o pai de
    ``1.1.1.02`` é ``1.1``. Sem isso, um nível intermediário ausente faria a
    subárvore inteira desaparecer da conferência.
    """
    filhos: dict[str, list[str]] = defaultdict(list)
    for codigo in grupos:
        partes = codigo.split(".")
        for n in range(len(partes) - 1, 0, -1):
            candidato = ".".join(partes[:n])
            if candidato in grupos:
                filhos[candidato].append(codigo)
                break
    return dict(filhos)


def raizes(grupos: dict[str, list[dict]], filhos: dict[str, list[str]]) -> list[str]:
    """Códigos sem pai dentro do balancete."""
    com_pai = {f for lista in filhos.values() for f in lista}
    return sorted(c for c in grupos if c not in com_pai)


def conferir_hierarquia(contas: Iterable[dict[str, Any]]) -> RelatorioHierarquia:
    """
    Confere, para cada pai, se o saldo declarado bate com a soma dos filhos.

    É a validação que faltava: um balancete cujo rollup fecha em todos os
    níveis está, com altíssima probabilidade, extraído corretamente. Um que
    não fecha tem problema **antes** de qualquer matching ou exportação.
    """
    contas = list(contas)
    grupos = agrupar_por_codigo(contas)
    filhos = mapear_filhos(grupos)

    relatorio = RelatorioHierarquia(total_contas=len(contas))
    relatorio.contas_com_saldo = sum(
        1 for c in contas if parse_saldo(c.get("saldo")) is not None
    )
    relatorio.fora_da_arvore = len(contas) - sum(len(v) for v in grupos.values())
    relatorio.codigos_duplicados = {
        codigo: len(lista) for codigo, lista in grupos.items() if len(lista) > 1
    }

    for pai, codigos_filhos in filhos.items():
        declarado = sum(_saldo(c) for c in grupos[pai])
        somado = sum(_saldo(c) for f in codigos_filhos for c in grupos[f])
        if abs(declarado - somado) <= TOLERANCIA:
            relatorio.pais_conferidos += 1
        else:
            relatorio.divergencias.append(
                Divergencia(
                    codigo=pai,
                    descricao=str(grupos[pai][0].get("descricao", "")),
                    declarado=declarado,
                    somado=somado,
                    n_filhos=len(codigos_filhos),
                )
            )

    for codigo in raizes(grupos, filhos):
        classe = classe_from_codigo(codigo)
        if classe:
            total = sum(_saldo(c) for c in grupos[codigo])
            relatorio.totais_por_classe[classe] = (
                relatorio.totais_por_classe.get(classe, 0.0) + total
            )
            # O dígito-raiz separado, para que Custos (3) e Receitas (4) não
            # cheguem à equação já somados. Ver RelatorioHierarquia.desequilibrio.
            raiz = str(codigo).lstrip("()- ").strip()[:1]
            relatorio.totais_por_raiz[raiz] = (
                relatorio.totais_por_raiz.get(raiz, 0.0) + total
            )

    relatorio.divergencias.sort(key=lambda d: abs(d.diferenca), reverse=True)
    return relatorio


@dataclass
class Selecao:
    """O corte da árvore que vai para a projeção."""

    #: Códigos cujo valor deve ser projetado (nenhum é ancestral de outro).
    codigos: list[str] = field(default_factory=list)
    #: Folhas não mapeadas: o valor delas se perde se nada for feito.
    nao_cobertos: list[str] = field(default_factory=list)
    #: Códigos que subiram para um agrupador mapeado, por agrupador.
    absorvidos_por: dict[str, list[str]] = field(default_factory=dict)

    @property
    def total_absorvidos(self) -> int:
        return sum(len(v) for v in self.absorvidos_por.values())


def _e_raiz_de_classe(codigo: str) -> bool:
    """
    ``"1"``, ``"2"``, ``"3"`` — a raiz de uma classe contábil.

    Um só segmento significa "o Ativo inteiro", "o Passivo inteiro". Nenhuma
    linha de detalhe do template representa isso, e deixar o corte parar aí
    põe o balanço inteiro numa linha só.
    """
    return "." not in str(codigo).strip()


def selecionar_para_projecao(
    contas: Iterable[dict[str, Any]],
    esta_mapeado: Callable[[str], bool],
) -> Selecao:
    """
    Escolhe **um corte** da árvore: o nível mais detalhado que não perde valor.

    Nenhum código selecionado é ancestral de outro, então não há dupla
    contagem; e todo ramo cujo detalhe seja mapeável é levado no detalhe.

    A regra, por nó, é:

    1. Se **todos** os ramos abaixo dele são cobertos sem perda, desce — mais
       detalhe é melhor, e o total é o mesmo.
    2. Senão, se o próprio nó é mapeado, para nele. Os filhos são *absorvidos*:
       o valor deles está no total do nó, pela identidade do rollup.
    3. Senão, desce assim mesmo e aceita a perda das folhas não mapeadas.

    É a regra 2 que resolve o caso que motivou este módulo: as seis contas
    bancárias com nome próprio não casam com plano de contas nenhum, mas
    "BANCOS CONTA MOVIMENTO" casa e já vale a soma delas. Parar no agrupador
    entrega o valor certo com uma linha em vez de perder seis.

    Sem a regra 1, o corte pararia na primeira conta mapeada de cima para
    baixo — em geral a raiz ("ATIVO") — e o template receberia o balanço
    inteiro em quatro linhas.

    **A raiz de classe nunca para o corte.** A regra 2 é boa para um agrupador
    de verdade ("BANCOS CONTA MOVIMENTO"), e desastrosa para "ATIVO": num
    balancete real, o Ativo inteiro — R$ 197.840.840 — foi emitido numa linha
    só, casada com "Outros ativos circulantes". O total do Balanço até fechava;
    a leitura era ficção. Raiz de classe é totalizador, e o template calcula os
    totais sozinho — o que ela absorveria é sempre melhor descer e declarar
    perdido, porque aí a perda aparece na reconciliação em vez de virar um
    número plausível no lugar errado.
    """
    grupos = agrupar_por_codigo(contas)
    filhos = mapear_filhos(grupos)
    selecao = Selecao()

    def escolher(codigo: str) -> tuple[list[str], list[str]]:
        """Devolve (códigos a emitir, folhas perdidas) para a subárvore."""
        descendentes_diretos = filhos.get(codigo, [])

        if descendentes_diretos:
            emitidos: list[str] = []
            perdidos: list[str] = []
            for filho in descendentes_diretos:
                e, p = escolher(filho)
                emitidos.extend(e)
                perdidos.extend(p)
            if not perdidos:
                return emitidos, []  # (1) detalhe completo, sem perda

        if esta_mapeado(codigo) and not _e_raiz_de_classe(codigo):
            absorvidos = _descendentes(codigo, filhos)
            if absorvidos:
                selecao.absorvidos_por[codigo] = absorvidos
            return [codigo], []  # (2) para no agrupador

        if descendentes_diretos:
            return emitidos, perdidos  # (3) desce e assume a perda
        return [], [codigo]  # folha não mapeada

    for raiz in raizes(grupos, filhos):
        emitidos, perdidos = escolher(raiz)
        selecao.codigos.extend(emitidos)
        selecao.nao_cobertos.extend(perdidos)

    selecao.codigos.sort()
    selecao.nao_cobertos.sort()
    return selecao


def _descendentes(codigo: str, filhos: dict[str, list[str]]) -> list[str]:
    """Todos os descendentes de um nó, em largura."""
    saida: list[str] = []
    fila = list(filhos.get(codigo, ()))
    while fila:
        atual = fila.pop(0)
        saida.append(atual)
        fila.extend(filhos.get(atual, ()))
    return saida
