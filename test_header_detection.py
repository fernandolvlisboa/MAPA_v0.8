"""Test header detection on Real Life."""

import pandas as pd
from src.bp.parsers.common import detect_header_row_df

file_path = "src/bp/training/DFS_Exemple/Balancete Real Life.xlsx"

# Read raw
df_raw = pd.read_excel(file_path, engine="openpyxl", header=None, nrows=80)
df_raw_str = df_raw.astype(str)

print(f"Raw shape: {df_raw.shape}")
print(f"\nFirst 10 rows:")
print(df_raw.head(10).to_string())

# Test header detection
best_header = detect_header_row_df(df_raw_str)
print(f"\n{'=' * 60}")
print(f"detect_header_row_df() returned: {best_header}")

if best_header is not None:
    print(f"\nRow {best_header} (detected header):")
    print(df_raw.iloc[best_header].tolist())
