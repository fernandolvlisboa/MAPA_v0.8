from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ParserResult:
    file_type: str
    success: bool
    rows_count: int = 0
    pages_count: int = 0
    extracted_records: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    raw_text: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    timing: dict[str, Any] = field(default_factory=dict)
    checksum: str | None = None

    @staticmethod
    def start_timer() -> float:
        return time.perf_counter()

    def stop_timer(self, start: float) -> None:
        self.timing["duration_sec"] = round(time.perf_counter() - start, 4)

    @staticmethod
    def compute_checksum(path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
