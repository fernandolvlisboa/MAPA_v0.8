"""
Contrato do registro de conta — o formato que TODO parser entrega.

Cada parser nasceu com o seu próprio vocabulário. O caminho tabular emite
``credito``/``debito``/``saldo``/``nivel``; o ``TXTParser`` emite
``creditos``/``debitos``/``classificacao`` e **nenhum** campo ``saldo``. Como
os consumidores a jusante (``xlsx_exporter``, ``build_gt_output``, o trainer)
leem ``saldo``, um balancete .TXT rendia contas com valor zero — mesmo depois
de o roteamento passar a funcionar.

O contrato não estava escrito em lugar nenhum; estava implícito no parser que
cada consumidor havia testado. Este módulo o torna explícito e o
``ParseyCaller`` o aplica na saída, de modo que **a fronteira do dispatcher
garante o formato** independentemente de qual parser produziu o registro.

Campos
------
=================  ==========  ==============================================
Campo              Obrigatório Significado
=================  ==========  ==============================================
``codigo``         sim         Código hierárquico ("1.1.01"). Cai para a
                               descrição quando a origem não traz código.
``descricao``      sim         Chave primária de matching (description-first).
``nivel``          sim         Profundidade derivada do código.
``saldo``          sim         Saldo principal. ``None`` = ilegível na origem
                               (distinto de ``0.0`` = conta zerada).
``saldo_anterior`` não         Estrutura de movimento, quando a origem tem.
``credito``        não
``debito``         não
``saldo_atual``    não
``codigo_interno`` não         Código próprio da origem, quando difere do
                               hierárquico (ex.: o "1001" dos .TXT).
=================  ==========  ==============================================
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from ..utils.codigo import (
    detectar_niveis_planos,
    nivel_from_codigo,
    normalizar_codigo,
    pontuar_codigo_plano,
)

#: Abaixo disso não há amostra para decidir o esquema do balancete.
_MINIMO_PARA_DECIDIR_ESQUEMA = 5

#: Fração dos códigos que precisa ter o mesmo número de segmentos para o
#: balancete ser considerado de largura fixa.
_FRACAO_LARGURA_FIXA = 0.80

__all__ = ["CAMPOS_MOVIMENTO", "normalizar_registros"]

#: Campos da estrutura de movimento, no vocabulário canônico.
CAMPOS_MOVIMENTO = ("saldo_anterior", "credito", "debito", "saldo_atual")

#: Sinônimos que os parsers usam para os mesmos campos.
_SINONIMOS = {
    "creditos": "credito",
    "debitos": "debito",
    "saldo_final": "saldo_atual",
}

#: Ordem de preferência para preencher ``saldo`` quando ausente.
_ORIGENS_DE_SALDO = ("saldo_atual", "saldo_anterior")

#: Código hierárquico: "1", "1.1", "1.1.01". A conta-raiz não tem ponto, então
#: a presença do separador não serve de teste.
_CODIGO_HIERARQUICO_RE = re.compile(r"^\d+(\.\d+)*$")


def normalizar_registros(registros: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Aplica o contrato a uma lista de registros vinda de qualquer parser.

    Idempotente: um registro já no contrato passa inalterado.
    """
    return _cortar_preenchimento(_pontuar_codigos_planos([_normalizar(r) for r in registros]))


def _pontuar_codigos_planos(registros: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Revela a hierarquia de um código **plano** de largura fixa.

    Muito sistema emite o código sem pontos, como número::

        1  ->  101  ->  10101  ->  10101001  ->  101010010001

    A árvore está lá — cada código é prefixo do filho —, mas invisível para
    quem procura ponto. Num balancete de cliente com sete exercícios, os cinco
    mais recentes caíam em "SEM HIERARQUIA" por isso, e eu cheguei a relatar
    que "não há código de conta na origem". Havia, e em 97,9% das contas o pai
    estava presente.

    A decisão é do balancete inteiro e exige prova (ver
    ``detectar_niveis_planos``): sem pai presente na esmagadora maioria, uma
    coluna de identificadores viraria árvore falsa. Aqui, como no corte de
    preenchimento, não converter devolve o comportamento anterior; converter
    errado inventa uma hierarquia que não existe.
    """
    codigos = [str(r.get("codigo", "")).strip() for r in registros]
    niveis = detectar_niveis_planos([c for c in codigos if c])
    if not niveis:
        return registros

    convertidos = {c: pontuar_codigo_plano(c, niveis) for c in set(codigos) if c}
    if len(set(convertidos.values())) != len(convertidos):
        return registros  # a conversão colidiria: dois códigos virariam um só

    for registro, codigo in zip(registros, codigos, strict=True):
        novo = convertidos.get(codigo)
        if novo and novo != codigo:
            registro.setdefault("codigo_original", codigo)
            registro["codigo"] = novo
            registro["nivel"] = nivel_from_codigo(novo)
    return registros


def _cortar_preenchimento(registros: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Corta o preenchimento de código de largura fixa — **se o balancete usar um**.

    Muito sistema emite o código com todos os níveis presentes e zeros onde o
    nível não se aplica (``1.01.00.00.00000000`` para "Ativo"). Lidos ao pé da
    letra, esses códigos formam raízes irmãs: todos têm o mesmo número de
    segmentos, nenhum é prefixo do outro, a árvore some. Três balancetes de
    clientes reais caíam em "SEM HIERARQUIA" exatamente assim.

    **A decisão é do balancete inteiro, não do registro.** Foi o erro da
    primeira versão: cortando registro a registro, em outro balancete
    ``1.5.00 CLIENTES`` virou ``1.5``, que já existia como "ATIVO NÃO
    CIRCULANTE" — duas contas distintas colapsaram num código só e o rollup,
    que estava íntegro, passou a divergir em 3,27 milhões. Ali o "00" é nível
    de verdade.

    Dois testes têm de passar, e são baratos:

    1. **Largura fixa** — a esmagadora maioria dos códigos tem o mesmo número
       de segmentos. É a assinatura do esquema; onde os níveis são de fato
       variáveis (``1``, ``1.5``, ``1.5.00``), não há preenchimento a cortar.
    2. **Sem colisão** — nenhum par de códigos distintos pode virar o mesmo
       código depois do corte.

    Falhando qualquer um, nada é cortado. Não cortar devolve o comportamento
    anterior; cortar errado inventa uma árvore que não existe.
    """
    codigos = [
        str(r.get("codigo", "")).strip()
        for r in registros
        if _CODIGO_HIERARQUICO_RE.fullmatch(str(r.get("codigo", "")).strip() or "x")
    ]
    hierarquicos = [c for c in codigos if "." in c]
    if len(hierarquicos) < _MINIMO_PARA_DECIDIR_ESQUEMA:
        return registros

    larguras = Counter(c.count(".") for c in hierarquicos)
    (_, mais_comum), = larguras.most_common(1)
    if mais_comum / len(hierarquicos) < _FRACAO_LARGURA_FIXA:
        return registros  # níveis variáveis: não há preenchimento

    cortados = {c: normalizar_codigo(c) for c in set(hierarquicos)}
    if not any(v != k for k, v in cortados.items()):
        return registros  # nada a cortar
    if len(set(cortados.values())) != len(cortados):
        return registros  # o corte colidiria: dois códigos virariam um só

    for r in registros:
        atual = str(r.get("codigo", "")).strip()
        novo = cortados.get(atual)
        if novo and novo != atual:
            r.setdefault("codigo_original", atual)
            r["codigo"] = novo
            r["nivel"] = nivel_from_codigo(novo)
    return registros


def _normalizar(registro: dict[str, Any]) -> dict[str, Any]:
    r = dict(registro)

    for origem, canonico in _SINONIMOS.items():
        if origem in r and canonico not in r:
            r[canonico] = r.pop(origem)
        else:
            r.pop(origem, None)

    # `classificacao` é o código hierárquico dos .TXT; o `codigo` deles é um
    # identificador interno plano ("1001"), inútil para derivar nível e classe
    # contábil. Promove-se o hierárquico e preserva-se o interno.
    classificacao = r.pop("classificacao", None)
    if classificacao and _CODIGO_HIERARQUICO_RE.match(str(classificacao).strip()):
        atual = r.get("codigo")
        if atual and str(atual) != str(classificacao):
            r["codigo_interno"] = atual
        r["codigo"] = str(classificacao)

    if not r.get("codigo"):
        r["codigo"] = r.get("descricao", "")


    if r.get("saldo") is None:
        for campo in _ORIGENS_DE_SALDO:
            if r.get(campo) is not None:
                r["saldo"] = r[campo]
                break
        else:
            r.setdefault("saldo", None)

    if "nivel" not in r:
        r["nivel"] = nivel_from_codigo(r.get("codigo"))

    return r
