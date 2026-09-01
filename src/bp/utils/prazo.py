"""
Prazo: CIRCULANTE ou NÃO CIRCULANTE.

Por que isso existe
-------------------

É o terceiro eixo de desambiguação, e o último que faltava:

===================  ======================================================
Plano C (classe)     ATIVO / PASSIVO / RESULTADO
:mod:`utils.natureza`  RECEITA / DESPESA, dentro de RESULTADO
**este módulo**      CIRCULANTE / NÃO CIRCULANTE, dentro de ATIVO e PASSIVO
===================  ======================================================

Sem ele, "Aplicação Financeira - CDB" — conta do **circulante** — casou com
``1.02.03.01`` (Imobilizado), e "OUTROS CRÉDITOS" do circulante foi para
``1.02.01.15`` (ativo não circulante). O ATIVO TOTAL continua certo, porque é
a soma; o que quebra é a **repartição**, e ela é metade da leitura de um
balanço: liquidez.

Medido no corpus: **9 de 18** balancetes entregavam o Circulante errado, um
deles deslocando R$ 28,7 milhões.

Como o prazo é determinado
--------------------------

**No plano referencial**, pelo código — a RFB é explícita: ``1.01`` é Ativo
Circulante, ``1.02`` é Ativo Não Circulante, ``2.01`` Passivo Circulante,
``2.02`` Passivo Não Circulante. ``2.03`` (Patrimônio Líquido) não tem prazo, e
devolver ``None`` para ele é o certo: restringir o PL por prazo excluiria os
alvos corretos.

**No balancete de origem**, pela árvore (:func:`mapear_prazo`), do mesmo jeito
que a natureza: a conta não diz o que é, o ramo em que ela vive diz.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

CIRCULANTE = "CIRCULANTE"
NAO_CIRCULANTE = "NAO_CIRCULANTE"

#: "Não circulante", "realizável a longo prazo", "exigível a longo prazo",
#: "permanente". Testado ANTES de "circulante", senão "não circulante" casa a
#: palavra "circulante" e vira o oposto do que é.
_NAO_CIRCULANTE_RE = re.compile(
    r"n[ãa]o[\s-]*circulante|longo\s*prazo|permanente|imobilizado|intang[íi]vel",
    re.I,
)
_CIRCULANTE_RE = re.compile(r"circulante|curto\s*prazo", re.I)

#: Prefixos do Plano Referencial da RFB. O plano é fixo e publicado; ler o
#: prazo dele é olhar o código, não adivinhar pelo nome.
_PREFIXOS = (
    ("1.01", CIRCULANTE),
    ("1.02", NAO_CIRCULANTE),
    ("2.01", CIRCULANTE),
    ("2.02", NAO_CIRCULANTE),
)


def prazo_de_texto(descricao: Any) -> str | None:
    """CIRCULANTE, NAO_CIRCULANTE ou ``None`` quando o texto nada declara."""
    texto = str(descricao or "")
    if not texto.strip():
        return None
    if _NAO_CIRCULANTE_RE.search(texto):
        return NAO_CIRCULANTE
    if _CIRCULANTE_RE.search(texto):
        return CIRCULANTE
    return None


def prazo_do_codigo_referencial(codigo: Any) -> str | None:
    """
    O prazo de uma conta do Plano Referencial, lido do código.

    ``None`` para o Patrimônio Líquido (``2.03``) e para o resultado: prazo não
    se aplica, e restringir por ele excluiria os alvos certos.
    """
    texto = str(codigo or "").strip()
    for prefixo, prazo in _PREFIXOS:
        if texto == prefixo or texto.startswith(prefixo + "."):
            return prazo
    return None


def mapear_prazo(contas: Iterable[dict[str, Any]]) -> dict[str, str]:
    """
    ``{código: CIRCULANTE|NAO_CIRCULANTE}`` para as contas de Ativo e Passivo.

    O prazo vem do **ancestral mais próximo que o declara**, subindo a partir
    da própria conta — a mesma regra da natureza, pelo mesmo motivo: "Aplicação
    Financeira - CDB" não diz nada sozinha, mas pende de ``1.01 CIRCULANTE``.

    Contas de resultado não entram: prazo não se aplica a elas.
    """
    from .codigo import classe_from_codigo

    descricoes: dict[str, str] = {}
    for conta in contas:
        codigo = str(conta.get("codigo", "")).strip()
        if not codigo or classe_from_codigo(codigo) not in ("ATIVO", "PASSIVO"):
            continue
        descricao = str(conta.get("descricao", "") or "").strip()
        if descricao and codigo not in descricoes:
            descricoes[codigo] = descricao
        descricoes.setdefault(codigo, "")

    declarado = {c: prazo_de_texto(d) for c, d in descricoes.items()}
    resolvido: dict[str, str] = {}
    for codigo in descricoes:
        partes = codigo.split(".")
        for n in range(len(partes), 0, -1):
            prazo = declarado.get(".".join(partes[:n]))
            if prazo:
                resolvido[codigo] = prazo
                break
    return resolvido
