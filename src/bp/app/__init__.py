"""
Interface do usuário final do BP.

Este pacote é a **casca**: janela, campos, mensagens. Ele não sabe padronizar
balancete nenhum — quem faz isso é ``src/bp/output/build_gt_output.py``, o mesmo
código que o ``main.py`` e os testes usam. A regra é dura de propósito: se a
interface precisar decidir alguma coisa sobre contabilidade, a decisão está no
lugar errado.

    src/bp/app/
    ├── paths.py     onde ler / onde escrever (a diferença que o .exe impõe)
    ├── service.py   ponte GUI -> núcleo: palpites, validação, execução
    ├── dnd.py       arrastar-e-soltar, com degradação quando não há suporte
    └── ui.py        a janela

Ver ``PLANO_J_INTERFACE.md`` para o desenho e o porquê de cada escolha.
"""

from __future__ import annotations

__all__ = ["main"]


def main() -> int:
    """Abre a janela. Ponto de entrada do executável."""
    from .ui import main as _main

    return _main()
