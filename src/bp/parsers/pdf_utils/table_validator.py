"""
TableValidator — validações básicas para tabelas BP/DRE

Nesta fase, fornecemos checagens essenciais:
- detecção de linhas de total
- verificação simples de somas por bloco
"""

from __future__ import annotations

import re
from typing import Any


class TableValidator:
    TOTAL_PATTERNS = [
        r"^total\b",
        r"^total do ativo",
        r"^total do passivo",
        r"^total do passivo e pl",
        r"^total geral",
    ]

    def is_total_line(self, description: str) -> bool:
        if not description:
            return False
        s = str(description).strip().lower()
        return any(re.search(pat, s) for pat in self.TOTAL_PATTERNS)

    def check_sum_totals(
        self,
        values: list[float | None],
        total: float | None,
        tolerance: float = 1e-2,
    ) -> bool:
        nums = [v for v in values if isinstance(v, (int, float))]
        if total is None or not nums:
            return False
        return abs(sum(nums) - float(total)) <= tolerance

    def validate_block_sum(self, rows: list[dict[str, Any]]) -> bool:
        """
        Valida se o último item com 'total' bate com a soma anterior (current apenas).
        """
        total_value = None
        items: list[float] = []
        for r in rows:
            desc = (r.get("descricao") or "").lower()
            if self.is_total_line(desc):
                total_value = r.get("current")
            else:
                v = r.get("current")
                if isinstance(v, (int, float)):
                    items.append(float(v))
        if total_value is None:
            return False
        return self.check_sum_totals(items, total_value)
