"""
Test Phase 3: Description-first parsing on corpus files (simplified output).
"""

from src.bp.parsers.dispatcher import ParseyCaller
from pathlib import Path


def test_file(file_path: str, expected_min_accounts: int = 10):
    """Test parsing a single file with description-first approach."""
    parser = ParseyCaller(file_path)
    result = parser.parse_with_result()

    success = len(result.extracted_records) >= expected_min_accounts
    status = "PASS" if success else "FAIL"

    print(
        f"[{status}] {Path(file_path).name:60s} {len(result.extracted_records):4d} accounts"
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

    print("=" * 80)
    print("PHASE 3: DESCRIPTION-FIRST PARSING TEST")
    print("=" * 80)

    results = []
    for file_path, min_accounts in test_cases:
        try:
            success, result = test_file(file_path, min_accounts)
            results.append(
                (Path(file_path).name, success, len(result.extracted_records))
            )
        except Exception as e:
            print(f"[FAIL] {Path(file_path).name:60s} EXCEPTION: {e}")
            results.append((Path(file_path).name, False, 0))

    print("=" * 80)
    total_pass = sum(1 for _, success, _ in results if success)
    print(f"RESULT: {total_pass}/{len(results)} files passed")
    print("=" * 80)


if __name__ == "__main__":
    main()
