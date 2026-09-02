"""
Balancete indentado: a hierarquia está na COLUNA da descrição, não num código.

O formato
---------

Muito sistema contábil brasileiro exporta o balancete sem coluna de código
hierárquico. A árvore aparece pela **indentação**: a descrição de cada conta
fica numa coluna mais à direita conforme a profundidade. No balancete "Real
Life"::

    col 5   ATIVO
    col 7     ATIVO CIRCULANTE
    col 9       DISPONÍVEL
    col 10        CAIXA
    col 11          CAIXA GERAL
    col 10        BANCOS CONTA MOVIMENTO
    col 11          BS2 EMPRESAS

O "Código" que existe é numeração de linha (1, 2, 3, 646, 9…), inútil como
árvore. Para o resto do programa, que precisa de código hierárquico para
conferir o rollup e evitar dupla contagem, o arquivo era ilegível: caía em
"SEM HIERARQUIA" e a entrega saía **sem ser conferida**.

A reconstrução
--------------

Este módulo lê a grade crua, descobre a **banda de indentação** (o conjunto de
colunas onde as descrições aparecem) e numera a árvore por outline: cada nível
mais fundo vira um segmento a mais no código. ``CAIXA GERAL`` acima vira
``1.1.1.1.1``. O código sintético é hierárquico de verdade — o pai é prefixo do
filho — então o pipeline inteiro (nível, classe, rollup, seleção) funciona sem
mudança.

A prova de que a leitura está certa
-----------------------------------

Não se aceita a reconstrução por parecer bonita: aceita-se **se o rollup
fechar**. Um balancete indentado real tem o pai valendo a soma dos filhos, e a
numeração por outline preserva isso. Se a árvore reconstruída não fecha, não é
um balancete indentado — é outra coisa, e a função devolve ``None`` para o
caminho normal seguir. É a mesma régua do resto da suíte: o rollup fechando é a
evidência de extração correta, não um detalhe estético.

Por isso o módulo é um **fallback puro**: o dispatcher só o chama quando o
caminho normal não achou árvore, e só usa o resultado quando ele fecha. Nunca
sobrepõe uma leitura que já funciona.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from ..utils.numero import parse_saldo

#: Mínimo de colunas distintas na banda de indentação. Um balancete NORMAL tem
#: a descrição numa coluna só; exigir três n[íveis distintos separa "indentado"
#: de "coluna de descrição comum" antes mesmo de tentar reconstruir.
_MIN_NIVEIS = 3

#: Palavras que marcam a coluna de saldo no cabeçalho, da mais específica para
#: a mais genérica. "Saldo Atual" é o saldo de fechamento; é ele que vale.
_ROTULOS_DE_SALDO = ("saldo atual", "saldo final", "saldo", "valor")


def _linha_de_cabecalho(bruto: pd.DataFrame) -> int | None:
    """A linha que traz os rótulos de valor. Sem ela, não há o que ancorar."""
    for i in range(min(len(bruto), 30)):
        celulas = [str(v).strip().lower() for v in bruto.iloc[i] if pd.notna(v)]
        tem_saldo = any(any(r in c for r in _ROTULOS_DE_SALDO) for c in celulas)
        tem_mov = any("débito" in c or "debito" in c or "crédito" in c or "credito" in c
                      for c in celulas)
        if tem_saldo and tem_mov:
            return i
    return None


def _coluna_de_saldo(cabecalho: pd.Series) -> int | None:
    """Índice da coluna de saldo, pelo rótulo mais específico presente."""
    for rotulo in _ROTULOS_DE_SALDO:
        for j, v in enumerate(cabecalho):
            if pd.notna(v) and rotulo in str(v).strip().lower():
                return j
    return None


def _e_valor(celula: Any) -> bool:
    """
    A célula é um VALOR monetário — não uma descrição?

    A distinção tem de ser rígida, e a primeira versão errou por ser frouxa:
    ``parse_saldo`` extrai o dígito de dentro do texto, então
    ``parse_saldo("BS2 EMPRESAS")`` devolve ``2.0``, ``"C6 BANK"`` vira ``6``,
    ``"B2W"`` vira ``2``. Nomes de banco e de empresa com número no meio são
    comuns, e cada um deles fazia a conta inteira DESAPARECER — a linha era
    tomada por coluna de valor e descartada. No Real Life sumia "BS2 EMPRESAS"
    (1.820,20), e o rollup do pai deixava de fechar por esse exato valor.

    Regra rígida: valor não tem letra. Se sobrou qualquer caractere alfabético
    depois de tirar dígitos, sinais e separadores, é descrição.
    """
    if pd.isna(celula):
        return False
    if isinstance(celula, (int, float)):
        return True
    texto = str(celula).strip()
    if not texto:
        return False
    if any(c.isalpha() for c in texto):
        return False
    return parse_saldo(texto) is not None


def _coluna_da_descricao(linha: list[Any]) -> int | None:
    """
    Onde começa a descrição numa linha: a primeira célula de TEXTO depois da
    coluna 0 (que costuma ser o número da linha). Célula de VALOR encerra a
    busca — dali em diante são as colunas de saldo.
    """
    for j in range(1, len(linha)):
        v = linha[j]
        if pd.isna(v):
            continue
        s = str(v).strip()
        if not s:
            continue
        if _e_valor(v):
            return None
        return j
    return None


def reconstruir_de_grade(bruto: pd.DataFrame) -> list[dict[str, Any]] | None:
    """
    Reconstrói registros ``{codigo, descricao, saldo}`` de uma grade indentada.

    Devolve ``None`` quando a grade não tem cara de balancete indentado — sem
    cabeçalho de valor, sem banda de indentação com profundidade suficiente, ou
    sem coluna de saldo. **Não** confere o rollup aqui: isso é responsabilidade
    de quem chama (o dispatcher só aceita se fechar), para o módulo poder ser
    testado nos dois passos separadamente.
    """
    if bruto is None or bruto.empty:
        return None

    cab = _linha_de_cabecalho(bruto)
    if cab is None:
        return None
    col_saldo = _coluna_de_saldo(bruto.iloc[cab])
    if col_saldo is None:
        return None

    dados = bruto.iloc[cab + 1 :].reset_index(drop=True)

    # Descobre a banda: as colunas de descrição de linhas que TÊM saldo. As
    # linhas sem saldo (banners de seção, assinatura no rodapé) ficam de fora —
    # não têm valor e não entram na árvore.
    linhas: list[tuple[int, str, float | None]] = []
    banda: set[int] = set()
    for _, row in dados.iterrows():
        r = row.tolist()
        j = _coluna_da_descricao(r)
        if j is None:
            continue
        saldo = parse_saldo(r[col_saldo]) if col_saldo < len(r) else None
        linhas.append((j, str(r[j]).strip(), saldo))
        if saldo is not None:
            banda.add(j)

    banda_ordenada = sorted(banda)
    if len(banda_ordenada) < _MIN_NIVEIS:
        return None

    nivel = {coluna: i for i, coluna in enumerate(banda_ordenada)}

    # Numeração por outline: um contador por nível, reiniciado ao subir.
    caminho: list[int] = []
    registros: list[dict[str, Any]] = []
    for coluna, descricao, saldo in linhas:
        if coluna not in nivel:
            continue  # banner de seção fora da banda
        profundidade = nivel[coluna]
        if profundidade < len(caminho):
            caminho = caminho[: profundidade + 1]
            caminho[profundidade] += 1
        elif profundidade == len(caminho):
            caminho.append(1)
        else:
            while len(caminho) < profundidade:
                caminho.append(1)
            caminho.append(1)
        registros.append(
            {
                "codigo": ".".join(str(c) for c in caminho),
                "descricao": descricao,
                "saldo": saldo,
            }
        )

    return registros or None
