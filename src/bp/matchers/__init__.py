# Módulo: src.bp.matchers
"""Matching inteligente de contas (fuzzy + heurísticas + IA)"""

from .conta_matcher import (
    ContaMatcher,
    MatchCandidate,
    MatchDecision,
    MatchResult,
)
from .match_cache import MatchCache

__all__ = [
    "ContaMatcher",
    "MatchCache",
    "MatchCandidate",
    "MatchDecision",
    "MatchResult",
]
