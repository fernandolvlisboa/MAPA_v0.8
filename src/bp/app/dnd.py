"""
Arrastar-e-soltar, com plano B.

O Tk que vem no Python **não** aceita arquivo arrastado de fora da janela; isso
é uma extensão (``tkdnd``). Este módulo tenta os backends conhecidos, na ordem,
e diz honestamente se conseguiu. Quando não consegue, a zona de soltar continua
existindo como um botão grande — o app nunca fica sem caminho para escolher
arquivo.

Sobre a dúvida que originou este módulo: **não é preciso pasta temporária**.
O sistema operacional entrega o *caminho completo* do arquivo arrastado; o BP
abre o original, onde ele estiver, e nunca o modifica. A única exceção real é
arrastar um anexo direto do Outlook — aí o que vem é um fluxo de bytes sem
caminho, o drop não traz nada e a tela pede que o anexo seja salvo antes
(:data:`AVISO_SEM_CAMINHO`).
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

#: Nenhum backend disponível — a zona vira só botão.
SEM_SUPORTE = ""

AVISO_SEM_CAMINHO = (
    "Esse item não chegou como arquivo do disco. Se veio de um e-mail ou de um "
    "arquivo .zip, salve-o numa pasta primeiro e arraste de lá."
)

#: Por que o arrastar-e-soltar não subiu, quando não subiu. Vazio = subiu.
#:
#: Existe porque a falha era **silenciosa**. No .exe da v0.8 o `tkdnd` não foi
#: empacotado, ``TkinterDnD.Tk()`` levantou ``RuntimeError('Unable to load
#: tkdnd library.')``, o ``except Exception: pass`` engoliu, e a janela abriu
#: com a zona virada em botão. Quem recebeu o executável só viu que arrastar
#: não trazia o arquivo — sem mensagem, sem log, sem pista. O motivo custa uma
#: string e transforma "não funciona" em "não achei a biblioteca tkdnd".
motivo_indisponivel: str = ""


def diagnostico() -> str:
    """
    Uma linha sobre o estado do arrastar-e-soltar. Vazia quando está ativo.

    A janela mostra isto embaixo da zona de soltar, e ``app.py --diagnostico``
    imprime no terminal — é o que se pede a quem relata "não traz o arquivo".
    """
    return motivo_indisponivel


def criar_root() -> tuple[Any, str]:
    """
    Devolve ``(root, backend)`` — a janela raiz e o nome do backend de drop.

    ``tkinterdnd2`` exige que a *raiz* seja dela, então a escolha do backend
    acontece antes de qualquer widget existir.

    ``BP_SEM_DND=1`` no ambiente força o caminho sem arrastar-e-soltar — é como
    os testes e a captura de tela rodam, e é a saída se o tkdnd brigar com
    alguma máquina.
    """
    global motivo_indisponivel
    motivo_indisponivel = ""

    if os.environ.get("BP_SEM_DND"):
        import tkinter as tk

        motivo_indisponivel = "desligado por BP_SEM_DND no ambiente"
        return tk.Tk(), SEM_SUPORTE

    try:
        from tkinterdnd2 import TkinterDnD

        return TkinterDnD.Tk(), "tkinterdnd2"
    except Exception as exc:
        falha_tkdnd = f"{type(exc).__name__}: {exc}"

    import tkinter as tk

    root = tk.Tk()
    try:  # Windows puro, sem dependência: aceita arquivo via ctypes.
        import windnd  # noqa: F401

        return root, "windnd"
    except Exception as exc:
        motivo_indisponivel = (
            f"tkinterdnd2 falhou ({falha_tkdnd}); windnd tambem nao ({exc})"
        )
        return root, SEM_SUPORTE


def registrar_alvo(
    widget: Any, backend: str, ao_soltar: Callable[[list[Path]], None]
) -> bool:
    """
    Faz ``widget`` aceitar arquivos arrastados. False quando não deu.

    ``ao_soltar`` recebe já a lista de :class:`~pathlib.Path` — a tela não vê
    o formato de string de cada backend.
    """
    global motivo_indisponivel

    if backend == "tkinterdnd2":
        try:
            from tkinterdnd2 import DND_FILES

            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>", lambda e: ao_soltar(caminhos_do_drop(e.data)))
            return True
        except Exception as exc:
            # Carregar a biblioteca e REGISTRAR o alvo são passos distintos, e
            # o segundo falhava calado: `criar_root` dizia "sem queixa" e o
            # arrastar continuava morto. O motivo tem de sobreviver aos dois.
            motivo_indisponivel = (
                f"tkdnd carregou, mas drop_target_register falhou em "
                f"{type(widget).__name__}: {type(exc).__name__}: {exc}"
            )
            return False

    if backend == "windnd":
        try:
            import windnd

            windnd.hook_dropfiles(
                widget,
                func=lambda arquivos: ao_soltar(
                    [Path(a.decode("mbcs", "ignore") if isinstance(a, bytes) else a)
                     for a in arquivos]
                ),
            )
            return True
        except Exception as exc:
            motivo_indisponivel = (
                f"windnd.hook_dropfiles falhou: {type(exc).__name__}: {exc}"
            )
            return False

    return False


def caminhos_do_drop(dados: str) -> list[Path]:
    """
    Converte a string do tkdnd em caminhos.

    O tkdnd entrega os itens separados por espaço e envolve em ``{}`` os que
    têm espaço no caminho — ``{C:\\Meus Balancetes\\jan 24.xlsx} C:\\outro.csv``.
    Alguns sistemas não põem as chaves; por isso, no fim, fragmentos vizinhos
    que só juntos formam um arquivo existente são reagrupados.
    """
    itens: list[str] = []
    atual: list[str] = []
    dentro = False

    for ch in dados:
        if ch == "{" and not dentro and not atual:
            dentro = True
        elif ch == "}" and dentro:
            dentro = False
            itens.append("".join(atual))
            atual = []
        elif ch.isspace() and not dentro:
            if atual:
                itens.append("".join(atual))
                atual = []
        else:
            atual.append(ch)
    if atual:
        itens.append("".join(atual))

    return [Path(p) for p in _reagrupar(itens) if p]


def _reagrupar(itens: list[str]) -> list[str]:
    """Junta fragmentos que só fazem sentido como um caminho com espaços."""
    saida: list[str] = []
    i = 0
    while i < len(itens):
        atual = itens[i]
        if Path(atual).exists():
            saida.append(atual)
            i += 1
            continue
        juntou = False
        acumulado = atual
        for j in range(i + 1, len(itens)):
            acumulado = f"{acumulado} {itens[j]}"
            if Path(acumulado).exists():
                saida.append(acumulado)
                i = j + 1
                juntou = True
                break
        if not juntou:
            # Não existe nem sozinho nem junto: devolve como veio e deixa a
            # camada de cima recusar com uma mensagem clara.
            saida.append(atual)
            i += 1
    return saida
