"""
Onde o programa lê e onde ele escreve.

Rodando da fonte, "a pasta do projeto" serve para as duas coisas. Dentro de um
executável, **não**: o PyInstaller descompacta o programa numa pasta temporária
que o sistema apaga quando o app fecha e que o usuário nunca enxerga. Tudo que o
programa *lê* (plano de contas, template GT) vem de lá; tudo que ele *escreve*
(configuração, log, planilha entregue) tem de ir para uma pasta do usuário — ou
some, ou esbarra em permissão de escrita em ``C:\\Program Files``.

Este módulo é a **única** fonte dessa distinção. Nenhuma outra parte do app
monta caminho de gravação na mão.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

#: Nome da pasta do app dentro dos diretórios do sistema.
APP_NAME = "BP"

#: CSIDL_PERSONAL — "Documentos" do usuário no Windows. Usar a API do sistema
#: (e não ``~/Documents``) é o que faz o app achar a pasta certa quando ela está
#: em português, redirecionada para o OneDrive ou para um drive de rede — os
#: três casos comuns em máquina corporativa.
_CSIDL_PERSONAL = 5


def is_frozen() -> bool:
    """True quando rodando dentro do executável (PyInstaller/Nuitka)."""
    return bool(getattr(sys, "frozen", False))


def resource_dir() -> Path:
    """
    Raiz do que **vem junto** com o programa — somente leitura.

    Da fonte é a raiz do repositório; congelado é a pasta temporária que o
    PyInstaller descompactou (``sys._MEIPASS``).
    """
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    # src/bp/app/paths.py -> src/bp/app -> src/bp -> src -> raiz
    return Path(__file__).resolve().parents[3]


def user_data_dir() -> Path:
    """Pasta gravável do app para este usuário (config, log, cache)."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / APP_NAME


def documents_dir() -> Path:
    """"Documentos" do usuário, perguntando ao sistema quando dá."""
    if sys.platform == "win32":
        caminho = _documentos_windows()
        if caminho:
            return caminho
    for nome in ("Documents", "Documentos"):
        candidato = Path.home() / nome
        if candidato.is_dir():
            return candidato
    return Path.home()


def _documentos_windows() -> Path | None:
    """Pergunta ao Windows onde fica "Documentos". None se não der."""
    try:
        import ctypes

        buffer = ctypes.create_unicode_buffer(1024)
        # SHGetFolderPathW(hwnd, csidl, token, flags, out) -> 0 em caso de sucesso
        if ctypes.windll.shell32.SHGetFolderPathW(  # type: ignore[attr-defined]
            None, _CSIDL_PERSONAL, None, 0, buffer
        ) == 0 and buffer.value:
            return Path(buffer.value)
    except Exception:
        # Sem shell32, sem permissão, sem Windows de verdade: o chamador tem
        # fallback. Isto nunca pode derrubar a abertura do app.
        return None
    return None


def default_output_dir() -> Path:
    """Onde as planilhas geradas caem por padrão: ``Documentos/BP``."""
    return documents_dir() / APP_NAME


def settings_path() -> Path:
    """Preferências entre sessões (última pasta de saída, último cliente)."""
    return user_data_dir() / "config.json"


def log_path() -> Path:
    """Log técnico — o que o usuário manda para você quando algo falha."""
    return user_data_dir() / "bp.log"


def ensure_dir(caminho: Path) -> Path:
    """Cria a pasta (e as intermediárias) e devolve ela. Idempotente."""
    caminho.mkdir(parents=True, exist_ok=True)
    return caminho
