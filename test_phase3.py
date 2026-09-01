"""
Test Phase 3: Description-first parsing on corpus files.
Validates universal approach works for all Excel structures.
"""

from src.bp.parsers.dispatcher import ParseyCaller
from pathlib import Path


def test_file(file_path: str, expected_min_accounts: int = 10):
    """Test parsing a single file with description-first approach."""
    print(f"\n{'=' * 80}")
    print(f"Testing: {Path(file_path).name}")
    print(f"{'=' * 80}")

    parser = ParseyCaller(file_path)
    result = parser.parse_with_result()

    print(f"✓ Success: {result.success}")
    print(f"✓ Rows: {result.rows_count}")
    print(f"✓ Accounts extracted: {len(result.extracted_records)}")

    if result.errors:
        print(f"✗ Errors: {result.errors}")
    if result.warnings:
        print(f"⚠ Warnings: {result.warnings}")

    # Show first 5 accounts
    print(f"\nFirst 5 accounts:")
    for i, acc in enumerate(result.extracted_records[:5], 1):
        print(
            f"  {i}. Código: {acc.get('codigo', 'N/A')[:30]:30s} | "
            f"Descrição: {acc.get('descricao', 'N/A')[:50]:50s} | "
            f"Saldo: {acc.get('saldo', 'N/A')}"
        )

    # Validation
    success = len(result.extracted_records) >= expected_min_accounts
    print(
        f"\n{'✓ PASS' if success else '✗ FAIL'}: Expected >= {expected_min_accounts} accounts, got {len(result.extracted_records)}"
    )

    return success, result


def main():
    """Test all corpus files."""

    test_cases = [
        ("src/bp/training/DFS_Exemple/Balancete 072022 122022 - RBM.xlsx", 500),
        ("src/bp/training/DFS_Exemple/Balancete Real Life.xlsx", 100),
        ("src/bp/training/DFS_Exemple/202404_2024 - Balancete.xlsx", 400),
        ("src/bp/training/DFS_Exemple/Balancete 042025 em excel.xlsx", 50),
        ("src/bp/training/DFS_Exemple/Balancete ASP 2023.xlsx", 50),
        (
            "src/bp/training/DFS_Exemple/Balancete SPEZZIA TUBOS 01012024-31122024.xlsx",
            50,
        ),
        ("src/bp/training/DFS_Exemple/Balancete-2025-06.xlsx", 50),
    ]

    results = []
    for file_path, min_accounts in test_cases:
        try:
            success, result = test_file(file_path, min_accounts)
            results.append(
                (Path(file_path).name, success, len(result.extracted_records))
            )
        except Exception as e:
            print(f"\n✗ EXCEPTION: {e}")
            results.append((Path(file_path).name, False, 0))

    # Summary
    print(f"\n{'=' * 80}")
    print("SUMMARY")
    print(f"{'=' * 80}")
    for name, success, count in results:
        status = "✓ PASS" if success else "✗ FAIL"
        print(f"{status} {name:60s} {count:4d} accounts")

    total_pass = sum(1 for _, success, _ in results if success)
    print(f"\nTotal: {total_pass}/{len(results)} files passed")


if __name__ == "__main__":
    main()
