"""
Teste completo de matching em 3 arquivos do corpus
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.bp.parsers.dispatcher import ParseyCaller
from src.bp.matchers.conta_matcher import ContaMatcher
from src.bp.generators.plano_contas import PlanodeContas


def test_file_matching(file_path: Path, max_accounts: int = 50):
    """Testa matching em um arquivo"""
    print(f"\n{'=' * 80}")
    print(f"Arquivo: {file_path.name}")
    print(f"{'=' * 80}")

    # Parse
    parser = ParseyCaller(file_path)
    result = parser.parse_with_result()

    if not result.extracted_records:
        print(f"[ERRO] Nenhuma conta parseada")
        return None

    accounts = result.extracted_records
    print(f"[OK] Parseado: {len(accounts)} contas")

    # Setup matcher
    plano = PlanodeContas()
    matcher = ContaMatcher(plano_contas=plano)

    # Test matching
    matched = 0
    review = 0
    unmatched = 0

    sample_size = min(max_accounts, len(accounts))

    for acc in accounts[:sample_size]:
        match_result = matcher.match(acc.get("descricao", ""))

        if match_result.decision:
            matched += 1
        elif match_result.needs_review:
            review += 1
        else:
            unmatched += 1

    # Stats
    total = sample_size
    match_rate = (matched / total * 100) if total > 0 else 0
    review_rate = (review / total * 100) if total > 0 else 0

    print(f"\n[RESULTADOS] Sample: {sample_size}/{len(accounts)} contas")
    print(f"  Matched:   {matched:4d} ({match_rate:5.1f}%)")
    print(f"  Review:    {review:4d} ({review_rate:5.1f}%)")
    print(f"  Unmatched: {unmatched:4d} ({(unmatched / total * 100):5.1f}%)")

    return {
        "file": file_path.name,
        "total": len(accounts),
        "sample": sample_size,
        "matched": matched,
        "review": review,
        "unmatched": unmatched,
        "match_rate": match_rate,
    }


def main():
    """Testa matching em múltiplos arquivos"""

    test_files = [
        Path("src/bp/training/DFS_Exemple/Balancete 072022 122022 - RBM.xlsx"),
        Path("src/bp/training/DFS_Exemple/Balancete Real Life.xlsx"),
        Path("src/bp/training/DFS_Exemple/202404_2024 - Balancete.xlsx"),
    ]

    results = []
    for file_path in test_files:
        try:
            result = test_file_matching(file_path, max_accounts=30)
            if result:
                results.append(result)
        except Exception as e:
            print(f"[ERRO] {file_path.name}: {e}")

    # Summary
    if results:
        print(f"\n{'=' * 80}")
        print("RESUMO GERAL")
        print(f"{'=' * 80}")

        for r in results:
            print(
                f"{r['file']:60s} {r['matched']:4d}/{r['sample']:4d} ({r['match_rate']:5.1f}%)"
            )

        total_matched = sum(r["matched"] for r in results)
        total_sample = sum(r["sample"] for r in results)
        overall_rate = (total_matched / total_sample * 100) if total_sample > 0 else 0

        print(f"{'─' * 80}")
        print(
            f"{'TOTAL':60s} {total_matched:4d}/{total_sample:4d} ({overall_rate:5.1f}%)"
        )


if __name__ == "__main__":
    main()
