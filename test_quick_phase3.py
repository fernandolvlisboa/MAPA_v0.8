"""Quick test for Phase 3 description-first parsing."""

from src.bp.parsers.dispatcher import ParseyCaller
from pathlib import Path

file_path = "src/bp/training/DFS_Exemple/Balancete 072022 122022 - RBM.xlsx"
print(f"Testing: {Path(file_path).name}")

parser = ParseyCaller(file_path)

# Test 1: Read DataFrame
print("\nStep 1: Reading DataFrame...")
df = parser.read()
if df is not None:
    print(f"  ✓ DataFrame shape: {df.shape}")
    print(f"  ✓ Columns: {list(df.columns)}")
else:
    print("  ✗ Failed to read DataFrame")
    exit(1)

# Test 2: Find columns
print("\nStep 2: Finding columns with description-first strategy...")
descricao_col = parser._find_description_column(df)
print(f"  Description column: {descricao_col}")

saldo_col = parser._find_saldo_column(df)
print(f"  Saldo column: {saldo_col}")

codigo_col = parser._find_codigo_column(df)
print(f"  Codigo column: {codigo_col}")

# Test 3: Parse accounts
print("\nStep 3: Parsing accounts...")
accounts = parser._parse_accounts_from_df(df)
print(f"  ✓ Extracted {len(accounts)} accounts")

# Show first 3
print("\nFirst 3 accounts:")
for i, acc in enumerate(accounts[:3], 1):
    print(f"  {i}. Código: {acc.get('codigo', 'N/A')[:40]:40s}")
    print(f"     Descrição: {acc.get('descricao', 'N/A')[:60]:60s}")
    saldo_val = acc.get("saldo")
    saldo_str = f"{saldo_val:.2f}" if saldo_val is not None else "N/A"
    print(f"     Saldo: {saldo_str}")
    print()

print(f"\n{'=' * 60}")
if len(accounts) >= 500:
    print(f"✓ SUCCESS: {len(accounts)} accounts extracted (expected >= 500)")
else:
    print(f"✗ FAIL: {len(accounts)} accounts extracted (expected >= 500)")
