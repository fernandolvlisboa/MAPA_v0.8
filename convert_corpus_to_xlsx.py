"""Convert all corpus XLS files to XLSX."""

from pathlib import Path
from auxil.convert_xls_to_xlsx import convert_xls_to_xlsx

corpus_dir = Path("src/bp/training/DFS_Exemple")
xls_files = list(corpus_dir.glob("*.xls"))

print(f"Found {len(xls_files)} XLS files to convert\n")

for xls_file in xls_files:
    print(f"Converting: {xls_file.name}")
    try:
        convert_xls_to_xlsx(xls_file)
    except Exception as e:
        print(f"  ✗ Error: {e}")

print(f"\n{'=' * 60}")
print("Conversion complete!")

# List all XLSX files
xlsx_files = list(corpus_dir.glob("*.xlsx"))
print(f"\nTotal XLSX files: {len(xlsx_files)}")
for xlsx in sorted(xlsx_files):
    print(f"  - {xlsx.name}")
