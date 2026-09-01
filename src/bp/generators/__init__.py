# Módulo: src.bp.generators
"""Geradores de estruturas de dados (plano de contas, hierarquias)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .plano_contas import PlanodeContas

if TYPE_CHECKING:  # pragma: no cover
    from .plano_contas_generator import PlanoContasGenerator

__all__ = ["PlanoContasGenerator", "PlanodeContas"]


def __getattr__(name: str) -> Any:
    """
    Import tardio de ``PlanoContasGenerator`` (PEP 562).

    O gerador depende de ``pydantic``, que é um extra de CURADORIA
    (``pip install bp[curation]``) e não faz parte do núcleo embarcado no
    executável do colaborador. Importá-lo aqui de forma ansiosa obrigaria
    todo consumidor de ``PlanodeContas`` a ter pydantic instalado.
    """
    if name == "PlanoContasGenerator":
        from .plano_contas_generator import PlanoContasGenerator

        return PlanoContasGenerator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
