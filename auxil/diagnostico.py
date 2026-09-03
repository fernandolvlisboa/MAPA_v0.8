"""
Diagnóstico de um balancete que não fecha — de ONDE vem o desequilíbrio.

Por que este script existe
--------------------------

Quando a janela diz *"O BALANCETE DE ORIGEM não fecha: Ativo + Passivo +
Resultado = 11.666.761,48"*, o número sozinho não diz o que fazer. Ele pode
significar coisas muito diferentes, e cada uma pede uma ação diferente:

- **o dado do cliente está errado mesmo** — nada a fazer no BP, avise o cliente;
- **o parser leu a coluna errada** (pegou Débito/Crédito em vez de Saldo) — os
  totais explodem e nenhuma conta bate;
- **a árvore quebrou** — o balancete tem detalhe (``1.01.01``) mas não tem o
  agrupador (``1.01``), então cada folha vira raiz e a soma conta o mesmo valor
  várias vezes;
- **códigos em formatos misturados** — parte com ponto (``1.01.01``), parte
  sem (``10101``). Os sem ponto viram raízes próprias e entram na conta de novo;
- **dois exercícios empilhados na mesma aba** — cada código aparece duas vezes
  e ``agrupar_por_codigo`` soma os dois.

Este script mede qual é o caso. Ele não conserta nada: só responde a pergunta
que precisa ser respondida antes de consertar qualquer coisa.

Uso
---
    uv run python -m auxil.diagnostico "caminho/do/balancete.xlsx"

    # se a planilha tem várias abas e você quer uma específica
    uv run python -m auxil.diagnostico "balancete.xlsx" --aba "Balancete 2025"
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

from src.bp.parsers.dispatcher import ParseyCaller
from src.bp.utils.numero import parse_saldo
from src.bp.utils.codigo import classe_from_codigo
from src.bp.validators.hierarquia import (
    agrupar_por_codigo,
    conferir_hierarquia,
    mapear_filhos,
    participa_da_arvore,
    raizes,
)

#: Quantos itens listar em cada seção. O suficiente para reconhecer o padrão
#: sem despejar 200 linhas no terminal.
TOPO = 15


def _linha(titulo: str) -> None:
    print(f"\n{'=' * 72}\n{titulo}\n{'=' * 72}")


def _ler(caminho: Path, aba: str | None) -> list[dict]:
    chamador = ParseyCaller(str(caminho), sheet_name=aba) if aba else ParseyCaller(str(caminho))
    contas = chamador.parse()
    if not contas:
        print(f"ERRO: o parser não devolveu nenhuma conta de {caminho}")
        print("Sem isso não há o que diagnosticar. Verifique se a aba está certa.")
        sys.exit(1)
    return contas


def _secao_leitura(contas: list[dict]) -> None:
    """O parser leu o quê? Antes de conferir soma, conferir que houve leitura."""
    _linha("1. O QUE O PARSER LEU")
    print(f"Contas devolvidas: {len(contas)}")

    com_saldo = sum(1 for c in contas if parse_saldo(c.get("saldo")) is not None)
    print(f"Com saldo legível: {com_saldo}")
    if com_saldo < len(contas) * 0.5:
        print("  !! Menos da metade trouxe valor — a coluna de saldo pode estar errada.")

    campos = Counter(k for c in contas for k in c.keys())
    print(f"Campos presentes: {', '.join(sorted(campos))}")

    print("\nPrimeiras 5 contas, como o parser as viu:")
    for c in contas[:5]:
        print(f"  codigo={c.get('codigo')!r:24} saldo={c.get('saldo')!r:>18} "
              f"desc={str(c.get('descricao'))[:34]!r}")


def _secao_arvore(contas: list[dict]) -> None:
    """
    As raízes são o coração do problema.

    A equação contábil soma AS RAÍZES. Numa árvore sã há três (``1``, ``2``,
    ``3``). Se houver dezenas, a soma está contando ramos inteiros mais de uma
    vez, e o desequilíbrio é artefato do medidor — não defeito do dado.
    """
    _linha("2. A ÁRVORE — é aqui que o desequilíbrio costuma nascer")

    grupos = agrupar_por_codigo(contas)
    filhos = mapear_filhos(grupos)
    rs = raizes(grupos, filhos)

    fora = len(contas) - sum(len(v) for v in grupos.values())
    print(f"Códigos distintos na árvore: {len(grupos)}")
    print(f"Contas fora da árvore (código não hierárquico ou descrição-lixo): {fora}")
    print(f"RAÍZES (códigos sem pai dentro do balancete): {len(rs)}")

    if len(rs) <= 5:
        print("  OK — poucas raízes, a árvore está inteira.")
    else:
        print(f"  !! {len(rs)} raízes é MUITO. Numa árvore sã são 3 ('1','2','3').")
        print("     Cada raiz entra inteira na equação contábil. Se um ramo tem")
        print("     raiz própria porque o agrupador dele falta no arquivo, o")
        print("     valor dele é contado junto com o de quem deveria contê-lo.")

    print(f"\nAs {min(TOPO, len(rs))} maiores raízes, por valor absoluto:")
    por_valor = sorted(
        ((r, sum(parse_saldo(c.get("saldo")) or 0.0 for c in grupos[r])) for r in rs),
        key=lambda t: abs(t[1]), reverse=True,
    )
    for codigo, total in por_valor[:TOPO]:
        desc = str(grupos[codigo][0].get("descricao", ""))[:36]
        classe = classe_from_codigo(codigo) or "?"
        print(f"  {codigo:<20} classe={classe:<3} {total:>18,.2f}  {desc}")


def _secao_formato(contas: list[dict]) -> None:
    """Formatos de código misturados — a causa silenciosa de dupla contagem."""
    _linha("3. FORMATO DOS CÓDIGOS — misturar formatos duplica valor")

    grupos = agrupar_por_codigo(contas)
    por_niveis = Counter(c.count(".") + 1 for c in grupos)
    print("Distribuição por profundidade (níveis no código):")
    for niveis in sorted(por_niveis):
        marca = "  <-- sem ponto" if niveis == 1 else ""
        print(f"  {niveis} nível(is): {por_niveis[niveis]:>4} código(s){marca}")

    sem_ponto = [c for c in grupos if "." not in c]
    if len(sem_ponto) > 3:
        print(f"\n  !! {len(sem_ponto)} códigos SEM PONTO convivendo com códigos com ponto.")
        print("     Se o plano do cliente é '1.01.01' e alguns vieram '10101', os")
        print("     sem ponto não encaixam na árvore e viram raízes próprias.")
        print(f"     Exemplos: {', '.join(sorted(sem_ponto)[:10])}")

    duplicados = {c: len(l) for c, l in grupos.items() if len(l) > 1}
    if duplicados:
        repetidas = sum(n - 1 for n in duplicados.values())
        print(f"\nCódigos repetidos: {len(duplicados)} ({repetidas} conta(s) a mais)")
        print("  Normal em balancete real (duas contas com o mesmo código), MAS")
        print("  se forem muitos pode ser DOIS EXERCÍCIOS empilhados na mesma aba —")
        print("  e aí cada código é somado duas vezes.")
        piores = sorted(duplicados.items(), key=lambda t: -t[1])[:TOPO]
        for codigo, n in piores:
            desc = str(grupos[codigo][0].get("descricao", ""))[:34]
            print(f"    {codigo:<20} x{n}  {desc}")


def _secao_equacao(contas: list[dict]) -> None:
    """O veredito: a equação fecha? E se não, por quanto e por causa de quem?"""
    _linha("4. A EQUAÇÃO CONTÁBIL")

    rel = conferir_hierarquia(contas)
    print(rel.resumo())

    if rel.totais_por_classe:
        print("\nTotal por classe (soma das raízes de cada classe):")
        nomes = {"1": "ATIVO", "2": "PASSIVO+PL", "3": "RESULTADO"}
        for classe, total in sorted(rel.totais_por_classe.items()):
            print(f"  {nomes.get(classe, classe):<12} {total:>20,.2f}")
        print(f"  {'DESEQUILÍBRIO':<12} {rel.desequilibrio:>20,.2f}")

    if rel.divergencias:
        print(f"\nAgrupadores cuja soma dos filhos NÃO bate ({len(rel.divergencias)}):")
        print("Ordenados pela maior diferença — o primeiro costuma explicar o resto.")
        for d in rel.divergencias[:TOPO]:
            print(f"  {d}")
    else:
        print("\nTodos os agrupadores conferem: a soma dos filhos bate com o pai.")
        if not rel.equacao_fecha:
            print("  !! Rollup íntegro MAS equação não fecha. Isso aponta para")
            print("     raízes a mais (seção 2) ou classe faltando — não para")
            print("     erro de leitura de valor.")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Diz de onde vem o desequilíbrio de um balancete.",
    )
    p.add_argument("balancete", type=Path, help="caminho do arquivo")
    p.add_argument("--aba", default=None, help="nome da aba, se houver várias")
    args = p.parse_args(argv)

    if not args.balancete.exists():
        print(f"ERRO: não achei {args.balancete}")
        return 1

    print(f"Diagnóstico de: {args.balancete.name}")
    contas = _ler(args.balancete, args.aba)

    _secao_leitura(contas)
    _secao_arvore(contas)
    _secao_formato(contas)
    _secao_equacao(contas)

    _linha("COMO LER ISTO")
    print("Muitas raízes (secao 2)   -> a arvore quebrou; o desequilibrio e do medidor")
    print("Codigos sem ponto (3)     -> formatos misturados; o parser leu duas convencoes")
    print("Muitos duplicados (3)     -> talvez dois exercicios na mesma aba")
    print("Poucas contas com saldo(1)-> a coluna de valor esta errada")
    print("Divergencias grandes (4)  -> o dado do cliente e que nao fecha")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
