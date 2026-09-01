#!/usr/bin/env python
"""
BP — o programa do usuário final.

É este arquivo que vira o executável. Ele não faz nada além de abrir a janela:
toda a lógica está em ``src/bp/app/`` (interface) e no núcleo do projeto
(padronização). Ver ``PLANO_J_INTERFACE.md``.

    uv run python app.py        # da fonte
    BP.exe                      # empacotado (PyInstaller)

Para a bancada de trabalho do analista — treinar, revisar pendências — use
``main.py``, o menu de terminal. São públicos diferentes de propósito.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Permite rodar `python app.py` da raiz sem instalar o pacote.
RAIZ = Path(__file__).resolve().parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from src.bp.app import main  # noqa: E402  (precisa do sys.path acima)

if __name__ == "__main__":
    raise SystemExit(main())
