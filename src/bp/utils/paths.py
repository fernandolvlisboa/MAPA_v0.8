"""
Caminhos do projeto — resolvidos uma vez, sem hardcode.

O corpus de treinamento (balancetes de clientes) vive fora do repositório
público. Este módulo dá a **única** resposta para "onde estão os balancetes?"
— procurado em duas fontes, nesta ordem:

1. Variável de ambiente ``MAPA_SAMPLES_DIR``. Útil para quem mantém os
   arquivos num pen drive, Dropbox, ou pasta compartilhada.
2. ``<raiz-do-repo>/data/samples/`` — o padrão. Gitignored (ver
   ``docs/DADOS_PRIVADOS.md``).

Se nenhuma tiver arquivo, os testes que dependem do corpus **pulam** com
mensagem explicativa; o código de produção também não quebra — só devolve
lista vazia.
"""

from __future__ import annotations

import os
from pathlib import Path

__all__ = ["SAMPLES_DIR", "raiz_do_repo", "samples_dir"]

_ENV_VAR = "MAPA_SAMPLES_DIR"


def raiz_do_repo() -> Path:
    """Raiz do repositório (ancorada neste arquivo)."""
    return Path(__file__).resolve().parent.parent.parent.parent


def samples_dir() -> Path:
    """Onde estão os balancetes de treinamento nesta máquina."""
    override = os.environ.get(_ENV_VAR)
    if override:
        return Path(override).expanduser().resolve()
    return raiz_do_repo() / "data" / "samples"


#: Constante para quem só quer importar e usar.
SAMPLES_DIR = samples_dir()
