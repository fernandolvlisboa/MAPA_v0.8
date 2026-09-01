"""
Natureza de resultado: RECEITA ou DESPESA.

Por que isso existe
-------------------

``classe_from_codigo`` responde ATIVO / PASSIVO / RESULTADO. Para o Balanço
basta; para a DRE, **não**: receita e despesa são a mesma "classe" e têm
sinais opostos. Tratá-las como uma coisa só produziu o pior defeito visto até
aqui — uma receita de serviços de R$ 4.937.529,00 casou com
``(-) Custo dos Serviços Prestados`` com score 1.0 e entrou na entrega como
custo negativo. Erro duplo: a receita some **e** o custo infla pelo mesmo
valor. O resultado do exercício erra por duas vezes o valor da conta.

O Plano C (restrição por classe) não podia pegar isso: origem e destino eram
ambos RESULTADO. Este módulo é o refinamento que faltava — o "Plano C da DRE".

Como a natureza é determinada
-----------------------------

**No plano referencial**, pelo texto: a RFB marca deduções, custos e despesas
com o prefixo ``(-)``. Das 451 contas de resultado do referencial, 226 trazem
a marca.

**No balancete de origem**, pela árvore (:func:`mapear_natureza`). A conta
"Servicos prestados - mercado interno" não diz o que é; o ramo em que ela vive
diz — ela pende de ``4 RECEITAS``. É a declaração estrutural do próprio
balancete, e vale mais que qualquer heurística sobre o nome da folha.
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from collections.abc import Iterable
from typing import Any

RECEITA = "RECEITA"
DESPESA = "DESPESA"

#: Prefixo redutor da RFB. Domina qualquer outro sinal: "(-) Outras Receitas
#: Operacionais" é conta redutora, não receita.
_PREFIXO_REDUTOR_RE = re.compile(r"^\s*\(\s*-\s*\)")
_PREFIXO_ADITIVO_RE = re.compile(r"^\s*\(\s*\+\s*\)")

#: Palavras que declaram despesa. "custo" e "despesa" são inequívocas em
#: plano de contas brasileiro; "deducao" e "abatimento" idem.
_PALAVRAS_DESPESA = (
    "custo",
    "despesa",
    "deducao",
    "abatimento",
    "perda",
    "provisao para perda",
)

#: Palavras que declaram receita.
_PALAVRAS_RECEITA = (
    "receita",
    "faturamento",
    "venda",
    "rendimento",
    "ganho",
)


def _sem_acento(texto: Any) -> str:
    return "".join(
        c
        for c in unicodedata.normalize("NFD", str(texto or "").lower())
        if unicodedata.category(c) != "Mn"
    )


def natureza_de_texto(descricao: Any) -> str | None:
    """
    RECEITA, DESPESA ou ``None`` quando o texto não declara nada.

    ``None`` é resposta legítima e frequente ("ALUGUEIS", "SERVICOS
    PRESTADOS"): quem responde nesses casos é a árvore, não o nome da folha.
    Chutar aqui seria pior que não saber — um chute errado inverte o sinal de
    uma conta na DRE.
    """
    if descricao is None:
        return None
    bruto = str(descricao)
    if _PREFIXO_REDUTOR_RE.match(bruto):
        return DESPESA
    if _PREFIXO_ADITIVO_RE.match(bruto):
        return RECEITA
    texto = _sem_acento(bruto)
    if not texto.strip():
        return None
    # Despesa é testada primeiro: "custo das mercadorias vendidas" contém
    # "venda", e o que manda é o "custo".
    if any(p in texto for p in _PALAVRAS_DESPESA):
        return DESPESA
    if any(p in texto for p in _PALAVRAS_RECEITA):
        return RECEITA
    return None


def mapear_natureza(contas: Iterable[dict[str, Any]]) -> dict[str, str]:
    """
    ``{código: RECEITA|DESPESA}`` para as contas de resultado do balancete.

    A natureza vem do **ancestral mais próximo que a declara**, subindo a partir
    da própria conta. O ramo em que a conta vive é quem responde:

    - "Servicos prestados - mercado interno" nada declara sozinha, mas pende de
      ``4.1 RECEITAS OPERACIONAIS`` → RECEITA;
    - "Servicos prestados por terceiros" pende de ``3.2 DESPESAS OPERACIONAIS``
      → DESPESA.

    As duas existem no mesmo balancete, com nomes quase idênticos e sinais
    opostos. É esse par que o Plano C não separava.

    **Por que o mais próximo e não o mais alto.** A regra do "ancestral mais
    alto" parece mais estrutural, e quebra feio: a raiz ``3`` do Plano
    Referencial da RFB tem descrição "Redução do IPI na Venda de Bens de
    Informática..." — contém "venda", declara RECEITA, e classificaria as 451
    contas de resultado do plano inteiro como receita, deduções e custos
    inclusive. O ancestral mais próximo é local, e o mais específico é sempre o
    mais informativo: ``3.90.02 Despesas Administrativas e Gerais`` decide o que
    está sob ele, sem depender da raiz.

    A mesma função serve o balancete e o plano referencial — os dois são
    árvores de código com descrição, e a natureza se lê da mesma maneira nos
    dois. Ter duas regras seria ter duas verdades.

    Contas fora do resultado não entram no mapa: para elas a natureza não
    existe e devolver um valor seria convidar uso errado.
    """
    from .codigo import classe_from_codigo

    # Uma conta pode aparecer repetida (código duplicado é normal em balancete
    # real); a descrição do grupo é a da primeira ocorrência com texto.
    descricao_por_codigo: dict[str, str] = {}
    for conta in contas:
        codigo = str(conta.get("codigo", "")).strip()
        if not codigo or classe_from_codigo(codigo) != "RESULTADO":
            continue
        descricao = str(conta.get("descricao", "") or "").strip()
        if descricao and codigo not in descricao_por_codigo:
            descricao_por_codigo[codigo] = descricao
        descricao_por_codigo.setdefault(codigo, "")

    #: natureza declarada por cada nó, se declarar alguma
    declarada = {
        codigo: natureza_de_texto(descricao)
        for codigo, descricao in descricao_por_codigo.items()
    }

    resolvido: dict[str, str] = {}
    for codigo in descricao_por_codigo:
        partes = codigo.split(".")
        # Da folha para a raiz: o primeiro ancestral que declara é quem manda.
        for n in range(len(partes), 0, -1):
            natureza = declarada.get(".".join(partes[:n]))
            if natureza:
                resolvido[codigo] = natureza
                break
    return resolvido


def totais_por_natureza(
    contas: Iterable[dict[str, Any]], naturezas: dict[str, str]
) -> dict[str, float]:
    """
    Soma das **raízes** de cada natureza — o totalizador, não a soma de tudo.

    Somar todas as contas contaria o ramo várias vezes (pai e filhos). Aqui só
    entram os códigos sem ancestral dentro da mesma natureza.
    """
    por_codigo: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for conta in contas:
        codigo = str(conta.get("codigo", "")).strip()
        if codigo in naturezas:
            por_codigo[codigo].append(conta)

    totais: dict[str, float] = {}
    for codigo, grupo in por_codigo.items():
        partes = codigo.split(".")
        tem_ancestral = any(
            ".".join(partes[:n]) in por_codigo for n in range(1, len(partes))
        )
        if tem_ancestral:
            continue
        natureza = naturezas[codigo]
        total = sum(
            float(c.get("saldo") or 0.0)
            for c in grupo
            if isinstance(c.get("saldo"), (int, float))
        )
        totais[natureza] = totais.get(natureza, 0.0) + total
    return totais


def resultado_do_periodo(
    contas: Iterable[dict[str, Any]],
    total_classe_resultado: float,
    origem_com_sinal: bool,
) -> float:
    """
    O resultado do exercício **na origem** — a referência da conferência da DRE.

    Como é calculado depende da convenção do balancete, e usar a fórmula errada
    produz um "não bate" que é da régua, não do dado:

    - **origem com sinal** (receita credora negativa, despesa devedora
      positiva): ``-(total da classe RESULTADO)``. Não passa pelo mapa de
      naturezas, e é isso que a torna robusta — num balancete real, os ramos
      "3 RESULTADO LÍQUIDO ANTES DO IRPJ" e "4 IMPOSTOS SOBRE O LUCRO" não
      declaram natureza nenhuma, ficam fora do mapa, e uma referência baseada
      nele deixava 86,73 mil de IRPJ/CSLL de fora — acusando a entrega de um
      erro que era da comparação.
    - **natureza implícita** (receita e despesa ambas positivas):
      ``|receitas| - |despesas|``, porque aí o total da classe soma as duas com
      o mesmo sinal e não significa nada.

    ``origem_com_sinal`` vem de fora, e de propósito: quem decide é o sinal do
    **Passivo**, não o das naturezas. Deduzir pelo sinal das naturezas parecia
    natural e quebra — num balancete com lucro, o ramo de resultado classificado
    DESPESA soma negativo (o lucro está lá dentro), a dedução dizia "natureza
    implícita" e a referência saía com o sinal trocado. O Passivo não tem esse
    problema: ele não compensa receita com despesa.
    """
    if origem_com_sinal:
        return -total_classe_resultado
    contas = list(contas)
    totais = totais_por_natureza(contas, mapear_natureza(contas))
    return abs(totais.get(RECEITA, 0.0)) - abs(totais.get(DESPESA, 0.0))
