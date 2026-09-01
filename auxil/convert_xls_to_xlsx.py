"""
Batch XLS to XLSX Converter

Converts .xls files to .xlsx using Excel COM automation.
This is run ONCE as a preprocessing step to avoid COM deadlocks during parsing.

Usage:
    python convert_xls_to_xlsx.py <input_dir>

Example:
    python convert_xls_to_xlsx.py BP_teste/XLS
"""

import sys
from pathlib import Path
import win32com.client
import pythoncom
import time


def convert_xls_to_xlsx(xls_path: Path, output_dir: Path = None) -> bool:
    """
    Convert a single .xls file to .xlsx using Excel COM.

    Args:
        xls_path: Path to .xls file
        output_dir: Output directory (default: same as input)

    Returns:
        True if conversion succeeded
    """
    if output_dir is None:
        output_dir = xls_path.parent

    xlsx_path = output_dir / (xls_path.stem + ".xlsx")

    # Skip if already converted
    if xlsx_path.exists():
        print(f"  ⊙ SKIP: {xls_path.name} (already converted)")
        return True

    excel = None
    workbook = None
    com_initialized = False

    try:
        # Initialize COM
        try:
            pythoncom.CoInitialize()
            com_initialized = True
        except Exception:
            pass

        # Start Excel
        excel = win32com.client.DispatchEx("Excel.Application")
        excel.Visible = False
        excel.DisplayAlerts = False
        excel.ScreenUpdating = False
        excel.AskToUpdateLinks = False

        # Open workbook
        abs_path = str(xls_path.absolute())
        workbook = excel.Workbooks.Open(
            abs_path,
            ReadOnly=True,
            UpdateLinks=0,
            Password="",
            WriteResPassword="",
            IgnoreReadOnlyRecommended=True,
            Notify=False,
        )

        # Save as XLSX
        workbook.SaveAs(
            str(xlsx_path.absolute()),
            FileFormat=51,  # xlOpenXMLWorkbook
            ConflictResolution=2,  # Overwrite
        )

        # Close
        workbook.Close(SaveChanges=False)
        workbook = None

        excel.Quit()
        excel = None

        print(f"  ✓ SUCCESS: {xls_path.name} → {xlsx_path.name}")
        return True

    except Exception as e:
        print(f"  ✗ FAILED: {xls_path.name} - {e}")
        return False

    finally:
        # Cleanup
        try:
            if workbook:
                workbook.Close(SaveChanges=False)
        except:
            pass

        try:
            if excel:
                excel.Quit()
        except:
            pass

        if com_initialized:
            try:
                pythoncom.CoUninitialize()
            except:
                pass

        # Force GC
        import gc

        gc.collect()

        # Small delay to let Excel cleanup
        time.sleep(0.5)


def batch_convert(input_dir: Path):
    """Convert all .xls files in directory to .xlsx"""
    xls_files = sorted(list(input_dir.glob("*.xls")))

    print(f"\nFound {len(xls_files)} .xls files in {input_dir}")
    print("=" * 80)

    results = []
    for i, xls_file in enumerate(xls_files, 1):
        print(f"\n[{i}/{len(xls_files)}] {xls_file.name}")
        success = convert_xls_to_xlsx(xls_file)
        results.append((xls_file.name, success))

        # Extra delay between files to avoid COM issues
        time.sleep(1)

    # Summary
    print(f"\n\n{'=' * 80}")
    print("CONVERSION SUMMARY")
    print("=" * 80)

    successful = sum(1 for _, success in results if success)
    total = len(results)

    print(f"Success Rate: {successful}/{total} ({100 * successful / total:.1f}%)")
    print(f"\nResults:")
    for filename, success in results:
        status = "✓" if success else "✗"
        print(f"  {status} {filename}")

    return successful == total


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python convert_xls_to_xlsx.py <input_dir>")
        print("Example: python convert_xls_to_xlsx.py BP_teste/XLS")
        sys.exit(1)

    input_dir = Path(sys.argv[1])

    if not input_dir.exists():
        print(f"Error: Directory not found: {input_dir}")
        sys.exit(1)

    success = batch_convert(input_dir)
    sys.exit(0 if success else 1)
