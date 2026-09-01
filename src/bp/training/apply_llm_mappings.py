"""
Aplica decisões manuais do classificador LLM (data/llm_mappings.json) ao
dicionário aprendido (account_variations.json) e ao cache de matching
(training_cache.json), com validação e trilha de auditoria.

Regras:
- Só aceita mapeamento cujo código exista no plano referencial.
- Só aceita se a classe do código respeitar a classe declarada (Plano C).
- Descrição é armazenada normalizada (mesma normalização usada no matcher).
- Marcações no cache: manual=True, source="llm".

Uso:
    python -m src.bp.training.apply_llm_mappings
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..generators.plano_contas import PlanodeContas
from ..matchers.conta_matcher import classe_from_codigo
from ..utils.normalizer import normalize


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent.parent


def apply_mappings(
    mappings_path: str | Path | None = None,
    variations_path: str | Path | None = None,
    cache_path: str | Path | None = None,
    plano_path: str | Path | None = None,
    verbose: bool = True,
) -> dict[str, int]:
    root = _repo_root()
    mp = Path(mappings_path) if mappings_path else root / "data" / "llm_mappings.json"
    vp = (
        Path(variations_path)
        if variations_path
        else root / "src" / "bp" / "training" / "account_variations.json"
    )
    cp = (
        Path(cache_path)
        if cache_path
        else root / "src" / "bp" / "training" / "training_cache.json"
    )
    plp = Path(plano_path) if plano_path else root / "data" / "plano_referencial.json"

    plano = PlanodeContas(plp)
    codes = set(plano.contas_index.keys())

    if not mp.exists():
        if verbose:
            print(f"Nada a aplicar: {mp} não existe.")
        return {"total": 0, "aplicados": 0, "rejeitados_codigo": 0, "rejeitados_classe": 0}

    with open(mp, encoding="utf-8") as f:
        data = json.load(f)
    mappings: list[dict[str, Any]] = data.get("mappings", [])

    variations = {}
    if vp.exists():
        with open(vp, encoding="utf-8") as f:
            variations = json.load(f)

    cache = {}
    if cp.exists():
        with open(cp, encoding="utf-8") as f:
            cache = json.load(f)

    stats = {"total": 0, "aplicados": 0, "rejeitados_codigo": 0, "rejeitados_classe": 0}

    for m in mappings:
        stats["total"] += 1
        codigo = m.get("codigo")
        desc = m.get("descricao", "")
        classe_esperada = m.get("classe")  # opcional

        if not codigo or codigo not in codes:
            stats["rejeitados_codigo"] += 1
            if verbose:
                print(f"  [reject:codigo] {desc!r} -> {codigo!r}")
            continue

        if classe_esperada:
            cc = classe_from_codigo(codigo)
            if cc and cc != classe_esperada:
                stats["rejeitados_classe"] += 1
                if verbose:
                    print(
                        f"  [reject:classe] {desc!r} classe={classe_esperada} vs código={cc}"
                    )
                continue

        norm = normalize(desc)
        conta = plano.contas_index[codigo]
        conta_desc = conta.get("descricao", "")

        # Variations: dicionário aprendido usado pelo matcher.
        entry = variations.setdefault(codigo, {"variations": [], "frequency": 0})
        if norm not in entry["variations"]:
            entry["variations"].append(norm)
        entry["frequency"] = entry.get("frequency", 0) + 1

        # Cache: torna a próxima consulta com essa descrição um HIT direto.
        cache[norm] = {
            "codigo": codigo,
            "descricao": conta_desc,
            "score": 1.0,
            "confidence": 1.0,
            "manual": True,
            "source": "llm",
        }

        stats["aplicados"] += 1

    vp.parent.mkdir(parents=True, exist_ok=True)
    with open(vp, "w", encoding="utf-8") as f:
        json.dump(variations, f, ensure_ascii=False, indent=2)
    with open(cp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

    if verbose:
        print("=" * 60)
        print(f"total mapeamentos    : {stats['total']}")
        print(f"aplicados            : {stats['aplicados']}")
        print(f"rejeitados (código)  : {stats['rejeitados_codigo']}")
        print(f"rejeitados (classe)  : {stats['rejeitados_classe']}")
        print("=" * 60)

    return stats


if __name__ == "__main__":
    apply_mappings()
