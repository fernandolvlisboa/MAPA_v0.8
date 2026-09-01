"""
Módulo de treinamento — Sistema isolado de aprendizado incremental

Processa balancetes de forma incremental, filtra contas analíticas,
e aprende padrões de descrição para melhorar matching futuro.
"""

from .trainer import AccountTrainer

__all__ = ["AccountTrainer"]
