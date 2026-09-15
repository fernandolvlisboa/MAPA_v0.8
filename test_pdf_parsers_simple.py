"""
Teste simplificado dos parsers avançados de PDF
Foca em: pdfplumber, tabula-py, pdfminer.six, PyMuPDF
"""

from pathlib import Path


def test_pdfplumber():
    """Testa extração com pdfplumber"""
    try:
        import pdfplumber
    except ImportError:
        return {
            "lib": "pdfplumber",
            "status": "NOT_INSTALLED",
            "error": "Module not found",
        }

    pdf_path = Path("src/bp/training/DFS_Exemple/ABT - BP 03.2024.pdf")

    if not pdf_path.exists():
        return {"lib": "pdfplumber", "status": "SKIP", "error": "PDF not found"}

    try:
        with pdfplumber.open(pdf_path) as pdf:
            page = pdf.pages[0]
            text = page.extract_text()
            tables = page.extract_tables()

            return {
                "lib": "pdfplumber",
                "status": "OK",
                "pages": len(pdf.pages),
                "text_length": len(text),
                "tables_found": len(tables),
                "sample": text[:200],
            }
    except Exception as e:
        return {"lib": "pdfplumber", "status": "ERROR", "error": str(e)}


def test_tabula():
    """Testa extração tabular com tabula-py"""
    try:
        import tabula.io as tabula
    except ImportError:
        return {
            "lib": "tabula-py",
            "status": "NOT_INSTALLED",
            "error": "Module not found",
        }

    pdf_path = Path("src/bp/training/DFS_Exemple/ABT - BP 03.2024.pdf")

    if not pdf_path.exists():
        return {"lib": "tabula-py", "status": "SKIP", "error": "PDF not found"}

    try:
        tables = tabula.read_pdf(
            str(pdf_path),
            pages=1,
            multiple_tables=True,
            pandas_options={"header": None},
            silent=True,
        )

        return {
            "lib": "tabula-py",
            "status": "OK",
            "tables_found": len(tables),
            "first_table_shape": tables[0].shape if tables else None,
        }
    except Exception as e:
        return {"lib": "tabula-py", "status": "ERROR", "error": str(e)}


def test_pdfminer():
    """Testa extração com pdfminer.six"""
    try:
        from pdfminer.high_level import extract_text
    except ImportError:
        return {
            "lib": "pdfminer.six",
            "status": "NOT_INSTALLED",
            "error": "Module not found",
        }

    pdf_path = Path("src/bp/training/DFS_Exemple/ABT - BP 03.2024.pdf")

    if not pdf_path.exists():
        return {"lib": "pdfminer.six", "status": "SKIP", "error": "PDF not found"}

    try:
        text = extract_text(str(pdf_path), page_numbers=[0])
        lines = [l for l in text.split("\n") if l.strip()]

        return {
            "lib": "pdfminer.six",
            "status": "OK",
            "text_length": len(text),
            "non_empty_lines": len(lines),
            "sample": text[:200],
        }
    except Exception as e:
        return {"lib": "pdfminer.six", "status": "ERROR", "error": str(e)}


def test_pymupdf():
    """Testa extração com PyMuPDF (fitz)"""
    try:
        import fitz
    except ImportError:
        return {
            "lib": "PyMuPDF",
            "status": "NOT_INSTALLED",
            "error": "Module not found",
        }

    pdf_path = Path("src/bp/training/DFS_Exemple/ABT - BP 03.2024.pdf")

    if not pdf_path.exists():
        return {"lib": "PyMuPDF", "status": "SKIP", "error": "PDF not found"}

    try:
        doc = fitz.open(str(pdf_path))
        page = doc[0]
        text = page.get_text()
        images = page.get_images()

        result = {
            "lib": "PyMuPDF",
            "status": "OK",
            "pages": doc.page_count,
            "text_length": len(text),
            "images": len(images),
            "sample": text[:200],
        }

        doc.close()
        return result
    except Exception as e:
        return {"lib": "PyMuPDF", "status": "ERROR", "error": str(e)}


def main():
    """Executa todos os testes"""
    print("=" * 80)
    print("TESTE DE PARSERS AVANCADOS DE PDF")
    print("=" * 80)
    print()

    tests = [test_pdfplumber, test_tabula, test_pdfminer, test_pymupdf]

    results = []
    for test_func in tests:
        result = test_func()
        results.append(result)

        lib = result["lib"]
        status = result["status"]

        print(f"[{status:15s}] {lib:20s}", end="")

        if status == "OK":
            # Mostrar detalhes
            details = []
            if "pages" in result:
                details.append(f"{result['pages']} pages")
            if "text_length" in result:
                details.append(f"{result['text_length']} chars")
            if "tables_found" in result:
                details.append(f"{result['tables_found']} tables")
            if "images" in result:
                details.append(f"{result['images']} imgs")

            print(f" - {', '.join(details)}")

            if "sample" in result:
                sample = result["sample"].replace("\n", " ")[:80]
                print(f"    Sample: {sample}...")

        elif status == "ERROR":
            print(f" - {result['error']}")

        elif status == "NOT_INSTALLED":
            print(f" - Module not available")

        elif status == "SKIP":
            print(f" - {result['error']}")

        print()

    # Resumo
    print("=" * 80)
    print("RESUMO")
    print("=" * 80)

    ok_count = sum(1 for r in results if r["status"] == "OK")
    total = len(results)

    print(f"Funcionando: {ok_count}/{total}")

    for r in results:
        symbol = "OK" if r["status"] == "OK" else "  "
        print(f"  [{symbol}] {r['lib']}")


if __name__ == "__main__":
    main()
