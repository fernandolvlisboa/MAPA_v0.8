"""
Review Wizard — Fluxo interativo para revisar contas que precisam de classificação

Funcionalidades:
- Reprocessa balancetes (todos ou um arquivo) e lista contas "needs_review"
- Mostra candidatos por busca fuzzy no plano de contas
- Permite navegação hierárquica (Ativo → Circulante → Caixa ...)
- Salva decisões no cache de treinamento (manual=True)
- Opcionalmente, atualiza `account_variations.json` com a descrição normalizada

Uso rápido (PowerShell):
  python -m src.bp.training.review_wizard --file "data/samples/MeuBalancete.xlsx"
  python -m src.bp.training.review_wizard --all

Comandos durante a revisão:
  [1..N]    Seleciona opção listada
  s         Buscar (fuzzy) no plano de contas
  h         Navegar por hierarquia (drill-down)
  c         Escolher código diretamente (digitar código completo)
  k         Skip (pular esta conta)
  b         Voltar (quando em hierarquia)
  q         Sair do assistente
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from ..generators.plano_contas import PlanodeContas
from ..utils.normalizer import normalize
from .trainer import AccountTrainer


def _list_roots(plano: PlanodeContas) -> list[dict[str, Any]]:
    roots = []
    for conta in plano.contas_index.values():
        if not conta.get("parent_id"):
            roots.append(conta.copy())
    roots.sort(key=lambda x: x.get("codigo", ""))
    return roots


def _print_header(title: str):
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)


def _select_from_list(prompt: str, options: list[str]) -> int | None:
    for i, opt in enumerate(options, 1):
        print(f"  {i}. {opt}")
    choice = input(f"{prompt} [1-{len(options)} | q=cancelar]: ").strip().lower()
    if choice == "q":
        return None
    if not choice.isdigit():
        return -1
    idx = int(choice)
    return idx if 1 <= idx <= len(options) else -1


def _confirm(prompt: str) -> bool:
    ans = input(f"{prompt} [s/N]: ").strip().lower()
    return ans in ("s", "sim", "y", "yes")


def _format_conta_line(conta: dict[str, Any]) -> str:
    return f"{conta.get('codigo', '')} — {conta.get('descricao', '')}"


def _fuzzy_candidates(
    plano: PlanodeContas, query: str, limit: int = 7
) -> list[dict[str, Any]]:
    try:
        return plano.buscar_por_descricao(query, threshold=0.5, limit=limit)
    except Exception:
        return []


def _navigate_hierarchy(plano: PlanodeContas) -> dict[str, Any] | None:
    """Permite escolher uma conta navegando pela hierarquia."""
    # current_parent começa None (raiz); ao descer, empilha o pai anterior.
    stack: list[tuple[str | None, list[dict[str, Any]]]] = []
    current_list = _list_roots(plano)
    current_parent = None

    while True:
        print("\nNavegação hierárquica:")
        options = [
            f"{c.get('codigo', '')} — {c.get('descricao', '')}" for c in current_list
        ]

        for i, text in enumerate(options, 1):
            print(f"  {i}. {text}")

        nav = (
            input(
                "Escolha [número], 'b'=voltar, 'q'=cancelar, 'e'=escolher esta(s) folha(s): "
            )
            .strip()
            .lower()
        )

        if nav == "q":
            return None
        if nav == "b":
            if stack:
                current_parent, current_list = stack.pop()
                continue
            else:
                return None

        if nav == "e":
            # Permite escolher explicitamente digitando o índice (conta final/folha)
            idx_str = input("Índice da conta desejada: ").strip()
            if idx_str.isdigit():
                idx = int(idx_str)
                if 1 <= idx <= len(current_list):
                    return current_list[idx - 1]
            print("Índice inválido.")
            continue

        if not nav.isdigit():
            print("Entrada inválida.")
            continue

        idx = int(nav)
        if not (1 <= idx <= len(current_list)):
            print("Opção fora do intervalo.")
            continue

        chosen = current_list[idx - 1]
        filhos = plano.get_filhos(chosen.get("codigo", ""))
        if not filhos:
            # Folha atingida
            if _confirm(f"Selecionar '{_format_conta_line(chosen)}'? "):
                return chosen
            else:
                continue

        # Desce um nível
        stack.append((current_parent, current_list))
        current_parent = chosen.get("codigo")
        current_list = filhos


def _save_manual_decision(
    trainer: AccountTrainer,
    descricao_original: str,
    conta_escolhida: dict[str, Any],
):
    query_norm = normalize(descricao_original)
    codigo = conta_escolhida.get("codigo", "")
    desc = conta_escolhida.get("descricao", "")

    # Atualiza cache de treinamento
    trainer.matcher.cache.update(query_norm, codigo, desc, manual=True)

    # Atualiza variações (opcional, ajuda no boost futuro)
    normalized = query_norm
    variations = trainer.variations
    if codigo not in variations:
        variations[codigo] = {"variations": [], "frequency": 0}
    if normalized not in variations[codigo]["variations"]:
        variations[codigo]["variations"].append(normalized)
    variations[codigo]["frequency"] += 1

    # Persiste variações
    with open(trainer.variations_path, "w", encoding="utf-8") as f:
        json.dump(variations, f, ensure_ascii=False, indent=2)


def _review_one(trainer: AccountTrainer, item: dict[str, Any]) -> bool:
    """Revisa um único item e salva se houver decisão. Retorna True se decidido."""
    desc = item.get("descricao") or item.get("original") or ""
    codigo_src = item.get("codigo") or item.get("codigo_original") or ""
    print("\n" + "-" * 80)
    print(f"Conta: {desc}")
    if codigo_src:
        print(f"Código origem (arquivo): {codigo_src}")

    # Heurística de ruído (provável nome de software / empresa específico):
    noisy = _is_noisy_description(desc)
    if noisy:
        print(
            "\n⚠ Indicação: descrição parece ruído específico (empresa/software). Considere 'i'."
        )

    print("\nOpções:")
    print("  s  → Buscar por descrição (fuzzy)")
    print("  h  → Navegar por hierarquia")
    print("  c  → Informar código diretamente")
    print("  i  → Ignorar permanentemente (não treinar / não mostrar de novo)")
    print("  k  → Pular (apenas nesta sessão)")
    print("  q  → Sair")

    plano = trainer.plano

    while True:
        cmd = input("Escolha [s/h/c/i/k/q]: ").strip().lower()
        if cmd == "i":
            trainer.add_to_ignore(desc)
            print("✓ Adicionada à lista de ignorados permanentes")
            return True
        if cmd == "q":
            return False  # sinaliza interrupção da sessão
        if cmd == "k":
            return True  # sem decisão, mas segue adiante
        if cmd == "s":
            cands = _fuzzy_candidates(plano, desc, limit=7)
            if not cands:
                print("Sem candidatos relevantes.")
            else:
                print("Candidatos:")
                for i, c in enumerate(cands, 1):
                    print(f"  {i}. [{c['score']:.2f}] {c['codigo']} — {c['descricao']}")
                pick = input("Selecione [número] ou Enter p/ voltar: ").strip()
                if pick.isdigit():
                    idx = int(pick)
                    if 1 <= idx <= len(cands):
                        chosen = cands[idx - 1]["conta"]
                        if _confirm(f"Confirmar '{_format_conta_line(chosen)}'? "):
                            _save_manual_decision(trainer, desc, chosen)
                            print("✓ Mapeamento salvo (cache + variações)")
                            return True
            continue
        if cmd == "h":
            chosen = _navigate_hierarchy(plano)
            if chosen:
                if _confirm(f"Confirmar '{_format_conta_line(chosen)}'? "):
                    _save_manual_decision(trainer, desc, chosen)
                    print("✓ Mapeamento salvo (cache + variações)")
                    return True
            continue
        if cmd == "c":
            code = input("Digite o código completo (ex: 1.01.01.02.01): ").strip()
            conta = plano.buscar_por_codigo(code)
            if not conta:
                print("Código não encontrado no plano de contas.")
            else:
                if _confirm(f"Confirmar '{_format_conta_line(conta)}'? "):
                    _save_manual_decision(trainer, desc, conta)
                    print("✓ Mapeamento salvo (cache + variações)")
                    return True
            continue

        print("Comando inválido. Use s/h/c/i/k/q.")


def _is_noisy_description(text: str) -> bool:
    """Detecta se a descrição parece um nome muito específico que não deve treinar.

    Critérios:
    - Muitas palavras todas em maiúsculas (>=3)
    - Contém termos típicos de empresa/soft: SOLUCAO|SOLUÇÕES|SOFTWARE|SISTEMA|TECNOLOGIA|SERVICOS|DIGITAL
    - Não contém palavras típicas de contas contábeis (caixa, bancos, impostos, receita, despesa, ativo, passivo, clientes)
    - Possui números misturados com letras sem estrutura de código (ex.: 'TFS SOLUCOES EM SOFTWARE')
    """
    if not text:
        return False
    norm = text.strip()
    upper_tokens = [t for t in norm.split() if t.isupper()]
    empresa_terms = re.compile(
        r"(SOLUCA|SOLUÇÃO|SOLUÇÕES|SOFTWARE|SISTEMA|SISTEMAS|TECNOLOGIA|SERVICOS|SERVIÇOS|DIGITAL|PLATFORM|PLATAFORMA)",
        re.IGNORECASE,
    )
    conta_terms = {
        "CAIXA",
        "BANCOS",
        "BANCO",
        "IMPOSTO",
        "IMPOSTOS",
        "RECEITA",
        "RECEITAS",
        "DESPESA",
        "DESPESAS",
        "ATIVO",
        "PASSIVO",
        "CLIENTES",
        "FORNECEDORES",
        "PATRIMONIO",
        "PATRIMÔNIO",
        "ESTOQUES",
        "SALARIOS",
        "SALÁRIOS",
    }
    has_empresa = bool(empresa_terms.search(norm))
    has_conta = any(ct in norm.upper() for ct in conta_terms)
    many_upper = len(upper_tokens) >= 3
    longish = len(norm) > 18
    if has_empresa and not has_conta and (many_upper or longish):
        return True
    return False


def _collect_needs_review(
    trainer: AccountTrainer, only_file: Path | None
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    targets: list[Path]
    if only_file:
        targets = [only_file]
    else:
        # Todos os arquivos (já processados e novos)
        targets = sorted(
            list((trainer.dfs_dir).glob("*.csv"))
            + list((trainer.dfs_dir).glob("*.xlsx"))
            + list((trainer.dfs_dir).glob("*.xls"))
        )

    for fp in targets:
        try:
            result = trainer.process_file(fp)
        except Exception as e:
            print(f"Aviso: erro reprocessando {fp.name}: {e}")
            continue

        for r in result.get("results", []):
            if r.get("needs_review"):
                items.append(
                    {
                        "file": fp.name,
                        "original": r.get("original"),
                        "codigo_original": r.get("codigo_original"),
                        "descricao": r.get("original"),
                    }
                )

    # Dedup por descrição normalizada (evita repetir a mesma conta idêntica)
    seen = set()
    unique_items = []
    for it in items:
        key = (it["file"], normalize(it["descricao"]))
        if key in seen:
            continue
        seen.add(key)
        unique_items.append(it)

    return unique_items


def main():
    parser = argparse.ArgumentParser(description="Assistente interativo de revisão")
    parser.add_argument(
        "--file", type=str, default=None, help="Arquivo específico para revisar"
    )
    parser.add_argument(
        "--all", action="store_true", help="Revisar todos os arquivos em data/samples/ (MAPA_SAMPLES_DIR)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limite de itens a revisar (0 = sem limite)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Apenas listar itens pendentes e sair (modo não interativo)",
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Ignorar automaticamente descrições detectadas como ruído e não interagir",
    )
    args = parser.parse_args()

    trainer = AccountTrainer()

    only_file = None
    if args.file and not args.all:
        only_file = Path(args.file)
        if not only_file.exists():
            print(f"Arquivo não encontrado: {only_file}")
            return

    _print_header("Assistente de Revisão — Contas pendentes")
    items = _collect_needs_review(trainer, only_file)

    if not items:
        print("Não há itens pendentes de revisão (com base no reprocessamento atual).")
        return

    total = len(items)
    if args.limit and args.limit > 0:
        items = items[: args.limit]
    print(f"Itens pendentes encontrados: {total} | Selecionados: {len(items)}")

    if args.list or args.auto:
        print("\nLista (modo somente leitura):")
        auto_ignored = 0
        for i, it in enumerate(items, 1):
            noisy_flag = " [ruído]" if _is_noisy_description(it["descricao"]) else ""
            print(f"  {i}. [{it['file']}] {it['descricao']}{noisy_flag}")
            if args.auto and _is_noisy_description(it["descricao"]):
                trainer.add_to_ignore(it["descricao"])
                auto_ignored += 1
        if args.auto:
            print(f"\n✓ Ignorados automaticamente: {auto_ignored}")
        else:
            print("\nUse sem --list para revisar interativamente.")
        return

    decided = 0
    for i, it in enumerate(items, 1):
        print(f"\n[{i}/{len(items)}] Arquivo: {it['file']}")
        proceeded = _review_one(trainer, it)
        if proceeded is False:
            print("Saindo do assistente.")
            break
        # proceeded True: decisão tomada ou skip
        # Contabilizamos decisão apenas quando salvamos; detectamos pelo cache
        qn = normalize(it.get("descricao", ""))
        if trainer.matcher.cache.get(qn):
            decided += 1

    print("\n" + "-" * 80)
    print(f"Concluído. Decisões salvas: {decided}. Você pode reexecutar o treinamento.")


if __name__ == "__main__":
    main()
