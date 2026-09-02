#!/usr/bin/env python
"""
BP — o programa do usuário final.

É este arquivo que vira o executável. Ele não faz nada além de abrir a janela:
toda a lógica está em ``src/bp/app/`` (interface) e no núcleo do projeto
(padronização). Ver ``PLANO_J_INTERFACE.md``.

    uv run python app.py        # da fonte
    MAPA.exe                    # empacotado (PyInstaller)

    MAPA.exe --diagnostico      # escreve MAPA_diagnostico.txt ao lado do .exe
    MAPA.exe --autoteste        # roda o pipeline inteiro; sai 0 se passou

``--diagnostico`` existe porque o executável é ``console=False``: quando algo
falha nele não há terminal, não há log, não há traceback. Foi assim que o .exe
da v0.8 circulou sem arrastar-e-soltar. A bandeira grava um relatório de texto
ao lado do binário e abre para a pessoa — é o que se pede a quem relata "não
funciona". Ver ``src/bp/app/diagnostico.py``.

Para a bancada de trabalho do analista — treinar, revisar pendências — use
``main.py``, o menu de terminal. São públicos diferentes de propósito.
"""

from __future__ import annotations

import contextlib
import os
import sys
from pathlib import Path

# Permite rodar `python app.py` da raiz sem instalar o pacote.
RAIZ = Path(__file__).resolve().parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))


def _abrir_janela() -> int:
    """
    Importa a interface só quando ela vai ser usada.

    ``ui.py`` importa ``tkinter`` no topo. Deixar isso no nível do módulo faria
    ``--diagnostico`` e ``--autoteste`` morrerem antes de rodar numa máquina
    sem Tk — justamente as duas bandeiras que existem para dizer o que está
    faltando. O autoteste do build também roda sem janela nenhuma.
    """
    from src.bp.app import main

    return main()


def _diagnosticar() -> int:
    """Grava o relatório e mostra o caminho — sem depender de terminal."""
    from src.bp.app import diagnostico

    destino = diagnostico.escrever()
    texto = destino.read_text(encoding="utf-8")
    print(texto)  # serve quando rodado da fonte, com terminal

    # No .exe não há terminal: a janelinha é a única forma de a pessoa saber
    # que o arquivo foi gerado e onde.
    try:
        import tkinter as tk
        from tkinter import messagebox

        raiz = tk.Tk()
        raiz.withdraw()
        messagebox.showinfo(
            "MAPA — diagnóstico",
            f"Relatório gravado em:\n\n{destino}\n\nMande esse arquivo para "
            f"quem for analisar. Só há caminhos e versões, nenhum dado de cliente.",
        )
        raiz.destroy()
    except Exception:
        pass

    with contextlib.suppress(Exception):  # abre no editor padrão do sistema
        os.startfile(destino)  # type: ignore[attr-defined]  # Windows
    return 0


def _autotestar() -> int:
    """
    Roda o pipeline completo dentro do próprio binário. 0 = passou.

    É o portão do `build.py`: um `.exe` que não se prova não é entregue. Grava
    o relatório ao lado do executável porque, em build ``console=False``, o
    print não vai a lugar nenhum.
    """
    from src.bp.app import autoteste

    passou, relatorio = autoteste.executar()
    print(relatorio)
    destino = (
        Path(sys.executable).resolve().parent
        if getattr(sys, "frozen", False)
        else Path.cwd()
    ) / "MAPA_autoteste.txt"
    with contextlib.suppress(Exception):
        destino.write_text(relatorio, encoding="utf-8")
    return 0 if passou else 1


if __name__ == "__main__":
    if "--diagnostico" in sys.argv[1:]:
        raise SystemExit(_diagnosticar())
    if "--autoteste" in sys.argv[1:]:
        raise SystemExit(_autotestar())
    raise SystemExit(_abrir_janela())
