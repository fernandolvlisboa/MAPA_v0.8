"""Deep inspection of specific XLS files."""

from pathlib import Path
import pandas as pd


def deep_inspect_xls(file_path: Path):
    """Deep inspection of XLS file structure."""
    print(f"\n{'=' * 80}")
    print(f"Deep Inspection: {file_path.name}")
    print("=" * 80)

    # Try reading with different configurations
    for engine in ["xlrd", "openpyxl"]:
        print(f"\n--- Engine: {engine} ---")
        for header_row in range(10):
            try:
                df = pd.read_excel(file_path, engine=engine, header=header_row)

                # Check if we have valid data
                if not df.empty and len(df.columns) >= 2:
                    df = df.dropna(axis=1, how="all")

                    print(
                        f"Header row {header_row}: {df.shape[0]} rows, {df.shape[1]} cols"
                    )
                    print(f"  Columns: {list(df.columns[:10])}")

                    # Look for account-like patterns
                    for col in df.columns:
                        col_str = str(col).lower()
                        if any(
                            p in col_str
                            for p in ["conta", "codigo", "classificacao", "descricao"]
                        ):
                            print(f"  >>> FOUND: {col}")
                            print(
                                f"      Sample values: {df[col].dropna().head(3).tolist()}"
                            )

                    # Show first row
                    if header_row <= 2:
                        print(
                            f"  First row: {df.iloc[0].tolist()[:5] if len(df) > 0 else 'empty'}"
                        )

                    # If this looks good, show more
                    if len(df.columns) >= 3 and len(df) > 5:
                        print(f"\n  >>> This looks promising! First 3 rows:")
                        print(df.head(3).to_string())
                        break

            except Exception as e:
                if header_row == 0:
                    print(f"  Error: {type(e).__name__}")


files = [
    Path("auxil/BP_teste/XLS/Balancete 042025 em excel.xls"),
    Path("auxil/BP_teste/XLS/Balancete ASP 2023.xls"),
    Path("auxil/BP_teste/XLS/Balancete Real Life.xls"),
]

for f in files:
    if f.exists():
        deep_inspect_xls(f)
