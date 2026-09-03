"""
Gerador do Plano de Contas Referencial (alvo limpo de matching — 3 setores).

Contexto do problema
---------------------
O ``data/plano_contas.json`` foi gerado a partir de TODOS os blocos da ECF/SPED
(L100, L300, M300, M350, N670, P..., U..., etc.). Isso mistura vários "planos
referenciais" diferentes — cada um com seu PRÓPRIO esquema de código — no mesmo
saco de matching. Consequência: a mesma descrição casa em códigos incompatíveis
dependendo do arquivo (ex.: FGTS caindo ora em ``2.01.01.01.04``, ora em
``1.1.1.4.2.60.00``) e conceitos de balancete casam em blocos de apuração fiscal
(ex.: COFINS em ``3.01.01.01.01.04.10`` do e-Lalur).

Solução
-------
Extrair um ÚNICO plano-alvo consistente: o Plano de Contas Referencial da RFB
para **PJ em Geral**, composto pelos formulários:

- ``L100A`` — Balanço Patrimonial (Ativo / Passivo / PL) — raízes ``1`` e ``2``
- ``L300A`` — Demonstração do Resultado (DRE) — raiz ``3``

O vocabulário de L100B/C (Financeiras/Seguradoras) é incorporado como variações
de descrição dos códigos L100A/L300A equivalentes via ``account_variations.json``
— não misturados no plano referencial, pois seus esquemas de código são
incompatíveis com o template GT. É este arquivo que o matcher/treinador
devem usar como referência, no lugar do master heterogêneo.

Uso
---
    python -m src.bp.generators.plano_referencial

Gera ``data/plano_referencial.json`` na mesma estrutura de ``plano_contas.json``
(forms / contas_flat / contas_tree / contas_index), de modo que ``PlanodeContas``
consiga carregá-lo sem alterações.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..utils.codigo import nivel_from_codigo

# Formulários que compõem o plano referencial ALVO do matching.
# L100A = Balanço Patrimonial; L300A = DRE. Ambos usam o mesmo esquema de código.
# L100B/C e L300B/C (Financeiras/Seguradoras) NÃO entram aqui — seus códigos são
# incompatíveis com o template GT. O vocabulário deles é aprendido como variações
# dos códigos L100A/L300A equivalentes em account_variations.json.
TARGET_FORMS: set[str] = {"L100A", "L300A"}


def _repo_root() -> Path:
    # src/bp/generators/plano_referencial.py -> sobe 3 níveis até a raiz do repo
    return Path(__file__).resolve().parent.parent.parent.parent


ENRICHED_FORM = "ENRIQUECIDO"


def _merge_extras(
    selected: list[dict[str, Any]],
    selected_codes: set[str],
    extra_path: Path | None,
) -> int:
    """
    Mescla contas enriquecidas (arquivo separado) na lista selecionada.

    Cada conta extra recebe forms=['ENRIQUECIDO'], nivel derivado do código e
    os campos padrão. Ignora códigos que já existam (não sobrescreve a ECF).
    Retorna quantas foram efetivamente adicionadas.
    """
    root = _repo_root()
    extra_path = (
        Path(extra_path) if extra_path else root / "data" / "plano_referencial_extra.json"
    )
    if not extra_path.exists():
        return 0

    with open(extra_path, encoding="utf-8") as f:
        extras = json.load(f).get("contas", [])

    added = 0
    for c in extras:
        codigo = c.get("codigo")
        if not codigo or codigo in selected_codes:
            continue
        conta = {
            "codigo": codigo,
            "descricao": c.get("descricao", ""),
            "tipo": c.get("tipo", "A"),
            "natureza": c.get("natureza", ""),
            "nivel": nivel_from_codigo(codigo),
            "parent_id": c.get("parent_id", ""),
            "formula": "",
            "formato": "",
            "tipo_do_lancamento": "",
            "relacao": "",
            "forms": [ENRICHED_FORM],
        }
        selected.append(conta)
        selected_codes.add(codigo)
        added += 1
    return added


def build_referencial(
    master_path: str | Path | None = None,
    output_path: str | Path | None = None,
    target_forms: set[str] | None = None,
    extra_path: str | Path | None = None,
    verbose: bool = True,
) -> dict[str, Any]:
    """
    Extrai o plano referencial limpo do master heterogêneo.

    Args:
        master_path: Caminho para ``plano_contas.json`` (master ECF completo).
        output_path: Caminho de saída para ``plano_referencial.json``.
        target_forms: Conjunto de formulários a manter (default: L100A + L300A).
        verbose: Imprime resumo.

    Returns:
        Dicionário com estatísticas da geração.
    """
    root = _repo_root()
    master_path = Path(master_path) if master_path else root / "data" / "plano_contas.json"
    output_path = (
        Path(output_path) if output_path else root / "data" / "plano_referencial.json"
    )
    forms_keep = target_forms if target_forms is not None else TARGET_FORMS

    with open(master_path, encoding="utf-8") as f:
        master = json.load(f)

    flat_all: list[dict[str, Any]] = master.get("contas_flat", [])

    # 1. Seleciona contas cujos formulários intersectam o alvo.
    selected = [c for c in flat_all if set(c.get("forms") or []) & forms_keep]
    selected_codes: set[str] = {c["codigo"] for c in selected}

    # 2. Integridade da árvore: garante que todo parent_id referenciado exista.
    #    (Na base atual isso já é verdade, mas puxamos os pais faltantes por segurança.)
    by_code = {c["codigo"]: c for c in flat_all}
    added_parents = 0
    changed = True
    while changed:
        changed = False
        for c in list(selected):
            pid = c.get("parent_id")
            if pid and pid not in selected_codes and pid in by_code:
                parent = by_code[pid]
                selected.append(parent)
                selected_codes.add(pid)
                added_parents += 1
                changed = True

    # 2.5. Enriquecimento: adiciona linhas comuns de balancete ausentes na ECF
    #      (Clientes, Capital Social, Despesas com Pessoal, ...). Auditável e
    #      reversível — vêm de um arquivo separado e ficam marcadas em forms.
    extra_added = _merge_extras(selected, selected_codes, extra_path)

    # 3. Reconstrói as estruturas no mesmo formato do master.
    #    - contas_flat: lista achatada (restrita ao alvo)
    #    - contas_index: código -> conta
    #    - forms: apenas os formulários mantidos, com seus códigos
    #    - contas_tree: árvore aninhada reconstruída a partir de parent_id
    selected.sort(key=lambda c: _code_sort_key(c["codigo"]))
    contas_index = {c["codigo"]: c for c in selected}

    forms_out: dict[str, list[str]] = {}
    for fm in sorted(set(forms_keep) | {ENRICHED_FORM}):
        codes = [c["codigo"] for c in selected if fm in (c.get("forms") or [])]
        if codes:
            forms_out[fm] = codes

    contas_tree = _build_tree(selected)

    referencial = {
        "_meta": {
            "descricao": "Plano de Contas Referencial RFB — PJ em Geral (extraído da ECF)",
            "forms_incluidos": sorted(forms_keep),
            "origem": str(Path(master_path).name),
            "total_contas": len(selected),
        },
        "forms": forms_out,
        "contas_flat": selected,
        "contas_tree": contas_tree,
        "contas_index": contas_index,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(referencial, f, ensure_ascii=False, indent=2)

    stats = {
        "enriquecidas": extra_added,
        "total_contas": len(selected),
        "pais_adicionados": added_parents,
        "por_raiz": _count_by_root(selected),
        "por_tipo": _count_by(selected, "tipo"),
        "output": str(output_path),
    }

    if verbose:
        print("=" * 72)
        print("GERAÇÃO DO PLANO DE CONTAS REFERENCIAL (PJ em Geral)")
        print("=" * 72)
        print(f"Formulários alvo : {sorted(forms_keep)}")
        print(f"Master           : {master_path}")
        print(f"Contas extraídas : {stats['total_contas']}")
        print(f"Enriquecidas     : {stats['enriquecidas']}")
        print(f"Pais adicionados : {stats['pais_adicionados']}")
        print(f"Por raiz         : {stats['por_raiz']}")
        print(f"Por tipo         : {stats['por_tipo']}")
        print(f"Salvo em         : {output_path}")
        print("=" * 72)

    return stats


def _code_sort_key(codigo: str):
    """Ordena códigos hierárquicos numericamente por segmento quando possível."""
    parts = str(codigo).split(".")
    key = []
    for p in parts:
        try:
            key.append((0, int(p)))
        except ValueError:
            key.append((1, p))
    return key


def _build_tree(contas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Reconstrói árvore aninhada (com 'children') a partir de parent_id."""
    nodes: dict[str, dict[str, Any]] = {}
    for c in contas:
        node = dict(c)
        node["children"] = []
        nodes[c["codigo"]] = node

    roots: list[dict[str, Any]] = []
    for c in contas:
        node = nodes[c["codigo"]]
        pid = c.get("parent_id")
        if pid and pid in nodes:
            nodes[pid]["children"].append(node)
        else:
            roots.append(node)

    roots.sort(key=lambda n: _code_sort_key(n["codigo"]))
    return roots


def _count_by_root(contas: list[dict[str, Any]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for c in contas:
        r = str(c.get("codigo", ""))[:1]
        out[r] = out.get(r, 0) + 1
    return dict(sorted(out.items()))


def _count_by(contas: list[dict[str, Any]], field: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for c in contas:
        v = c.get(field) or "?"
        out[v] = out.get(v, 0) + 1
    return dict(sorted(out.items()))


if __name__ == "__main__":
    build_referencial()
