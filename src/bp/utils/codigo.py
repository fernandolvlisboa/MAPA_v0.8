"""
Utilitários para códigos hierárquicos de conta contábil.

Fonte ÚNICA para operações sobre códigos ("1.1.01.03"): profundidade
hierárquica (`nivel`) e classe contábil (Ativo/Passivo/Resultado). Antes desta
extração, essas derivações viviam duplicadas em `conta_matcher.py` e
`plano_referencial.py` — divergências entre elas iam causar bugs sutis (Plano C
depende de derivação consistente da classe).
"""

from __future__ import annotations


def nivel_from_codigo(codigo: str | None) -> int:
    """
    Profundidade hierárquica derivada do código: número de segmentos separados
    por ponto. Ex.: ``"1"`` → 1, ``"1.1"`` → 2, ``"1.1.01.03"`` → 4.
    """
    if not codigo:
        return 0
    return len(str(codigo).split("."))


def classe_from_codigo(codigo: str | None) -> str | None:
    """
    Deriva a classe contábil a partir do dígito-raiz do código.

    Convenção (origem e Plano Referencial): 1=Ativo, 2=Passivo/PL, 3+=Resultado
    (DRE). No referencial a DRE é a raiz 3; em balancetes de origem o resultado
    pode usar 3, 4, 5... — todos mapeiam para RESULTADO.

    Retorna None quando o código não começa por dígito (ex.: códigos textuais
    de alguns balancetes), caso em que nenhuma restrição de classe é aplicada
    pelo Plano C (heurística segura por construção).
    """
    if not codigo:
        return None
    # Remove prefixos comuns de contas redutoras/formatação: "(", ")", "-", espaço.
    root = str(codigo).lstrip("()- ").strip()[:1]
    if root == "1":
        return "ATIVO"
    if root == "2":
        return "PASSIVO"
    if "3" <= root <= "9":
        return "RESULTADO"
    return None


#: Um segmento que é só zeros ("00", "00000000"). Em código de largura fixa
#: isso é preenchimento, não nível.
_SEGMENTO_ZERADO_RE = __import__("re").compile(r"^0+$")


def normalizar_codigo(codigo: str | None) -> str:
    """
    Remove os segmentos-zero à direita de um código de largura fixa.

    Muito sistema contábil emite o código com todos os níveis preenchidos e
    zeros onde o nível não se aplica::

        1.00.00.00.00000000   Ativo
        1.01.00.00.00000000   CIRCULANTE
        1.01.01.00.00000000   DISPONIBILIDADES
        1.01.01.01.00000001   Caixa Geral

    Lidos ao pé da letra, esses códigos formam quatro **raízes irmãs**: nenhum
    é prefixo do outro, porque todos têm cinco segmentos. A árvore some, o
    rollup não é conferido e a seleção que evita dupla contagem nunca roda —
    foi o que aconteceu com três balancetes de clientes reais, que rendiam
    contas e caíam em "SEM HIERARQUIA".

    Cortando o preenchimento, a filiação por prefixo volta a valer::

        1  ->  1.01  ->  1.01.01  ->  1.01.01.01  ->  1.01.01.01.00000001

    Conservador de propósito: só corta com 3+ segmentos e nunca devolve vazio.
    Código sem preenchimento passa intacto, então balancete que já funcionava
    não muda.
    """
    if not codigo:
        return ""
    texto = str(codigo).strip()
    if "." not in texto:
        return texto
    partes = texto.split(".")
    if len(partes) < 3 or not all(p.isdigit() for p in partes):
        return texto
    while len(partes) > 1 and _SEGMENTO_ZERADO_RE.match(partes[-1]):
        partes.pop()
    return ".".join(partes)


#: Um comprimento com uma ocorrência só é ruído — linha solta, não nível.
_MIN_OCORRENCIAS_DO_NIVEL = 2

#: Fração dos filhos que precisa encontrar o pai para um comprimento ser aceito
#: como nível. É a PROVA de que os números são uma árvore, e não uma coluna de
#: identificadores quaisquer.
_MIN_FRACAO_COM_PAI = 0.90

#: Mínimo de níveis. Com dois, qualquer coluna de identificadores de dois
#: tamanhos passaria.
_MIN_NIVEIS = 3


def detectar_niveis_planos(codigos: list[str]) -> tuple[int, ...] | None:
    """
    Os comprimentos que formam os níveis de um código **plano** de largura fixa.

    Muito sistema contábil emite o código sem pontos, como número::

        1              ATIVO
        101            ATIVO CIRCULANTE
        10101          CAIXA E EQUIVALENTES DE CAIXA
        10101001       CAIXA GERAL
        101010010001   GALPAO 1

    A hierarquia está lá — ``10101001`` é prefixo de ``101010010001`` —, mas
    invisível para quem procura ponto. Num balancete de cliente com sete
    exercícios, cinco caíam em "SEM HIERARQUIA" por isso, e eu cheguei a
    relatar que "não há código na origem". Havia: em 97,9% das contas o pai
    estava presente.

    Devolve os comprimentos acumulados — ``(1, 3, 5, 8, 12)`` — ou ``None``
    quando os números não formam árvore.

    Como os níveis são escolhidos
    -----------------------------

    De baixo para cima, e por **cobertura**, não por frequência. O critério
    natural — "comprimento com muitas ocorrências é nível" — descarta o topo
    do plano, que tem três ou quatro contas (Ativo, Passivo, Receitas,
    Despesas) contra centenas de folhas. O que define um nível é quantos
    **filhos encontram pai nele**.

    Duas travas contra árvore falsa, e ambas foram necessárias:

    - **contador** (:func:`_e_contador`) — inteiros consecutivos formam
      prefixos por acidente, e uma coluna de numeração de linha 1..668 virou
      "hierarquia", com o rollup divergindo em 65 agrupadores;
    - **cobertura** — sem 90% dos filhos achando pai, não é árvore.
    """
    planos = [c for c in codigos if c.isdigit()]
    if len(planos) < 10 or _e_contador(planos):
        return None

    from collections import Counter

    contagem = Counter(len(c) for c in planos)
    candidatos = sorted(
        L for L, n in contagem.items() if n >= _MIN_OCORRENCIAS_DO_NIVEL
    )
    if len(candidatos) < _MIN_NIVEIS:
        return None

    presentes = set(planos)
    por_comprimento: dict[int, list[str]] = {}
    for codigo in planos:
        por_comprimento.setdefault(len(codigo), []).append(codigo)

    def cobertura(filho: int, pai: int) -> float:
        """Fração dos códigos de comprimento ``filho`` cujo prefixo existe."""
        amostra = por_comprimento.get(filho, ())
        if not amostra:
            return 0.0
        return sum(1 for c in amostra if c[:pai] in presentes) / len(amostra)

    niveis = [candidatos[-1]]
    while True:
        atual = niveis[0]
        acima = [L for L in candidatos if atual > L]
        if not acima:
            break
        # O ancestral mais PRÓXIMO que cobre, não o mais bem coberto. A
        # cobertura é monótona — o prefixo mais curto de um código sempre
        # existe se o mais longo existe —, então escolher pelo máximo pula os
        # níveis intermediários e achata a árvore: de 162 agrupadores
        # conferindo para 6.
        validos = [L for L in acima if cobertura(atual, L) >= _MIN_FRACAO_COM_PAI]
        if not validos:
            break
        niveis.insert(0, max(validos))

    if len(niveis) < _MIN_NIVEIS:
        return None
    return tuple(niveis)


def _e_contador(planos: list[str]) -> bool:
    """
    Os números são uma **numeração de linha**, não um código de conta?

    A trava que faltava, e ela é decisiva. Inteiros consecutivos formam
    prefixos naturalmente — "1" é prefixo de "12", que é prefixo de "123" —,
    então uma coluna 1, 2, 3, …, 668 passa no teste de prefixo com folga e vira
    "hierarquia". Foi o que aconteceu: a coluna ``n`` de um balancete foi
    promovida a código de conta, e o rollup divergiu em 65 agrupadores com
    somas de bilhões.

    O que distingue: contador é **denso e contíguo**; código de conta tem
    buracos enormes (1, 101, 10101, 10101001). Basta comparar a quantidade de
    valores distintos com a amplitude.
    """
    numeros = {int(c) for c in planos}
    if len(numeros) < 10:
        return False
    amplitude = max(numeros) - min(numeros) + 1
    # Contador ocupa quase todo o intervalo; código de conta ocupa uma fração
    # ínfima (668 códigos espalhados até 999999999999).
    return len(numeros) / amplitude > 0.5


def pontuar_codigo_plano(codigo: str, niveis: tuple[int, ...]) -> str:
    """
    Quebra um código plano nos níveis detectados: ``10101001`` -> ``10.10.1001``?

    Não: ``niveis`` são comprimentos **acumulados**, então ``(1, 3, 5, 8, 12)``
    aplica cortes em 1, 3, 5 e 8 — ``101010010001`` vira ``1.01.01.001.0001``.

    Pontuar em vez de comparar prefixos direto é o que faz o resto do pipeline
    funcionar sem mudança: nível, classe contábil, mapeamento de filhos e
    seleção da projeção já falam a língua do código pontuado.
    """
    if not codigo.isdigit():
        return codigo
    partes: list[str] = []
    anterior = 0
    for corte in niveis:
        if corte >= len(codigo):
            break
        partes.append(codigo[anterior:corte])
        anterior = corte
    partes.append(codigo[anterior:])
    return ".".join(p for p in partes if p)
