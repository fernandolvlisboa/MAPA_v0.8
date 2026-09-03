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
    "conferir_hierarquia",
    "mapear_filhos",
    "participa_da_arvore",
    "selecionar_para_projecao",
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


def participa_da_arvore(conta: dict[str, Any]) -> bool:
    """
    A conta é um nó da hierarquia?

    Exige código hierárquico **e** descrição que não seja lixo. As duas
    condições são necessárias: as linhas de totalização do balancete chegam com
    um número nos dois campos, e ``"4389425.29"`` casa o formato de código
    hierárquico tão bem quanto ``"1.1.01"``. Quem sabe distinguir é
    ``is_garbage_description`` — a definição de linha-lixo que o matcher já
    usa, reaproveitada aqui em vez de duplicada.
    """
    codigo = str(conta.get("codigo", "")).strip()
    if not _CODIGO_HIERARQUICO_RE.fullmatch(codigo):
        return False
    return not is_garbage_description(str(conta.get("descricao", "")))


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
        return min(self._residuos_possiveis(), key=abs, default=0.0)

    def _residuos_possiveis(self) -> list[float]:
        """
        O resíduo da equação sob cada atribuição de sinais às classes.

        Trabalha sobre ``totais_por_raiz`` — o dígito-raiz, não a classe — de
        propósito: ``classe_from_codigo`` funde 3..9 num só "RESULTADO", e é
        justamente separar Custos (3) de Receitas (4) que permite ver a
        subtração. Fundidas, as duas só podem ser somadas.

        Fixa o sinal da primeira classe em ``+1``: negar tudo dá o mesmo
        resíduo em módulo, então metade das combinações é redundante.
        """
        totais = list(self.totais_por_raiz.values()) or list(
            self.totais_por_classe.values()
        )
        if not totais:
            return []
        if len(totais) > self.MAX_CLASSES_PARA_BUSCA:
            return [sum(totais)]

        residuos = []
        for combinacao in _product((1, -1), repeat=len(totais) - 1):
            sinais = (1,) + combinacao
            residuos.append(sum(s * v for s, v in zip(sinais, totais)))
        return residuos

    #: Acima disso a busca por sinais deixa de ser conservadora: com muitas
    #: classes cresce a chance de uma combinação zerar por acaso, e aí o
    #: "fecha" não significa mais nada. Plano contábil real tem 3 ou 4.
    MAX_CLASSES_PARA_BUSCA = 5

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


def _saldo(conta: dict[str, Any]) -> float:
    return parse_saldo(conta.get("saldo")) or 0.0


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
