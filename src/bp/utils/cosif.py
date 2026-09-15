"""
Reconhecimento de plano COSIF — o plano contábil das instituições financeiras.

Por que isto existe
-------------------

O plano-alvo do MAPA é o Referencial da RFB para **PJ em geral**. Um banco não
usa esse plano: usa o **COSIF** (Plano Contábil das Instituições do Sistema
Financeiro Nacional, do Banco Central), que tem uma estrutura de grupos própria
e incompatível com a convenção ``1=Ativo, 2=Passivo, 3+=Resultado`` que
``classe_from_codigo`` assume::

    grupo 1  Circulante e Realizável a Longo Prazo   (ATIVO)
    grupo 2  Permanente                              (ATIVO)   <- não é Passivo!
    grupo 3  COMPENSAÇÃO (ativo)                      (fora do balanço)
    grupo 4  Circulante e Exigível a Longo Prazo     (PASSIVO)
    grupo 5  Resultados de Exercícios Futuros        (PASSIVO)
    grupo 6  Patrimônio Líquido                       (PASSIVO/PL)
    grupo 7  Contas de Resultado CREDORAS             (RECEITA)
    grupo 8  Contas de Resultado DEVEDORAS            (DESPESA)
    grupo 9  COMPENSAÇÃO (passivo)                    (fora do balanço)

Sem reconhecer isso, o Permanente do banco caía em Passivo, receita e despesa
se fundiam num "RESULTADO" só (com o sinal errado na DRE), e a compensação —
contas de ordem que se anulam — inflava o balanço em dezenas de milhões.

Este módulo NÃO tenta mapear conta a conta o COSIF para o plano PJ (isso é
vocabulário, não estrutura). Ele responde duas coisas estruturais: **isto é um
balancete COSIF?** e **qual o papel contábil de cada grupo?**
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable
from typing import Any

ATIVO = "ATIVO"
PASSIVO = "PASSIVO"
RECEITA = "RECEITA"
DESPESA = "DESPESA"
COMPENSACAO = "COMPENSACAO"

#: Papel contábil de cada grupo-raiz do COSIF. É a tabela do Bacen, não uma
#: heurística: o dígito-raiz do código COSIF determina o grupo.
_PAPEL_POR_GRUPO = {
    "1": ATIVO,
    "2": ATIVO,
    "3": COMPENSACAO,
    "4": PASSIVO,
    "5": PASSIVO,
    "6": PASSIVO,
    "7": RECEITA,
    "8": DESPESA,
    "9": COMPENSACAO,
}


def _sem_acento(texto: Any) -> str:
    return "".join(
        c
        for c in unicodedata.normalize("NFD", str(texto or "").strip().lower())
        if unicodedata.category(c) != "Mn"
    )


def papel_cosif(codigo: str | None) -> str | None:
    """Papel contábil (ATIVO/PASSIVO/RECEITA/DESPESA/COMPENSACAO) do grupo-raiz."""
    if not codigo:
        return None
    raiz = str(codigo).lstrip("()- ").strip()[:1]
    return _PAPEL_POR_GRUPO.get(raiz)


def e_compensacao(codigo: str | None) -> bool:
    """Conta de compensação (grupo 3 ou 9) — fora do balanço patrimonial."""
    return papel_cosif(codigo) == COMPENSACAO


#: De-para COSIF -> Template GT, revisado com o usuário (Opção B: despesas
#: abertas em pessoal, depreciação e administrativas). A chave é um PREFIXO de
#: código COSIF; o casamento é por prefixo MAIS LONGO, então ``8.1.7.27``
#: (pessoal) vence ``8.1`` (administrativas). O valor é ``(codigo_alvo, rótulo)``
#: — código que a fórmula SUMIFS do Template GT captura.
#:
#: NÃO é uma tabela fechada: é o ponto de partida acordado para balancete de
#: banco. Contas fora dela caem em "Contas Não Identificadas" para revisão, sem
#: sumir do total.
DE_PARA_COSIF: dict[str, tuple[str, str]] = {
    # ---- ATIVO ----
    "1.1": ("1.01.01", "Caixa e equivalentes de caixa"),
    "1.2": ("1.01.01", "Caixa e equivalentes de caixa"),  # aplic. interfin. de liquidez
    "1.6": ("1.01.02.02", "Contas a receber de clientes"),  # carteira de crédito
    "1.8": ("1.01.02.09", "Outros ativos circulantes"),
    "1.9": ("1.01.02.09", "Outros ativos circulantes"),
    "2.2": ("1.02.03", "Imobilizado"),
    # ---- PASSIVO + PL ----
    "4.9.4": ("2.01.01.09", "Obrigações tributárias"),
    "4.9.9": ("2.01.01.05", "Contas a pagar e outras obrigações"),
    "6.1.1": ("2.03.01", "Capital social"),
    "6.1.5": ("2.03.02.03", "Reservas de lucros"),
    # ---- DRE ----
    "7.1": ("3.01.01.05.01.01", "(+) Receitas financeiras"),
    "7.3": ("3.01.01.05.01.10", "(+) Outras receitas operacionais"),
    "8.1.7.27": ("3.01.01.07.01.01", "(-) Despesas com pessoal"),
    "8.1.7.30": ("3.01.01.07.01.01", "(-) Despesas com pessoal"),
    "8.1.7.33": ("3.01.01.07.01.01", "(-) Despesas com pessoal"),
    "8.1.8": ("3.01.01.07.01.23", "(-) Depreciação e amortização"),
    "8.1": ("3.01.01.07.01.04", "(-) Despesas gerais e administrativas"),
    "8.3": ("3.01.01.07.01.14", "(-) Outras despesas operacionais"),
    "8.9.4": ("3.02.01.01", "(-) IRPJ e CSLL correntes"),
}


def mapear_cosif(codigo: str | None) -> tuple[str, str] | None:
    """
    Casa um código COSIF no Template GT pela de-para, por prefixo MAIS LONGO.

    ``8.1.7.27.00.00003`` casa ``8.1.7.27`` (pessoal), não ``8.1`` (adm.).
    Devolve ``(codigo_alvo, rótulo)`` ou ``None`` se nada na de-para cobre.
    """
    if not codigo:
        return None
    segs = str(codigo).strip().split(".")
    for n in range(len(segs), 0, -1):
        prefixo = ".".join(segs[:n])
        if prefixo in DE_PARA_COSIF:
            return DE_PARA_COSIF[prefixo]
    return None


def _descricoes_de_raiz(contas: Iterable[dict[str, Any]]) -> dict[str, str]:
    """Descrição do nó-raiz de cada grupo (código de um só dígito)."""
    out: dict[str, str] = {}
    for conta in contas:
        codigo = str(conta.get("codigo", "")).strip()
        if len(codigo) == 1 and codigo.isdigit() and codigo not in out:
            out[codigo] = _sem_acento(conta.get("descricao", ""))
    return out


def detectar_cosif(contas: Iterable[dict[str, Any]]) -> bool:
    """
    O balancete é COSIF (instituição financeira)?

    A assinatura mais distintiva do COSIF é a nomenclatura dos grupos de
    resultado — nenhum plano de PJ chama o grupo 7 de "Contas de Resultado
    Credoras" e o 8 de "Devedoras". Reconhecer por aí é estrutural e específico:
    não dispara em balancete de PJ, que não tem grupos 7/8 assim.

    Requer os DOIS grupos de resultado (7 credoras E 8 devedoras) ou a
    combinação de compensação (grupo 3 ou 9 chamado "Compensação") com o grupo
    de resultado credor — o par que só o COSIF tem.

    Espera receber contas já canonicalizadas (raiz = um dígito). Ver
    ``validators/hierarquia.canonicalizar_contas``.
    """
    raizes = _descricoes_de_raiz(contas)
    g7 = raizes.get("7", "")
    g8 = raizes.get("8", "")
    tem_credoras = "resultado" in g7 and "cred" in g7
    tem_devedoras = "resultado" in g8 and "deved" in g8
    tem_compensacao = any(
        "compensacao" in raizes.get(g, "") for g in ("3", "9")
    )
    return (tem_credoras and tem_devedoras) or (tem_credoras and tem_compensacao)
