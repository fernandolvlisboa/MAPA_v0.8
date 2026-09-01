"""
Teste dos parsers avançados de PDF
Testa: pdfplumber, tabula-py, pdfminer.six, PyMuPDF
"""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))


def test_pdfplumber():
    """Testa extração com pdfplumber"""
    import pdfplumber

    pdf_path = Path("src/bp/training/DFS_Exemple/ABT - BP 03.2024.pdf")

    if not pdf_path.exists():
        print(f"[SKIP] {pdf_path.name} nao encontrado")
        return

    print("\n" + "=" * 80)
    print("TESTE 1: pdfplumber (extração de texto nativo)")
    print("=" * 80)
    print(f"Arquivo: {pdf_path.name}")

    try:
        with pdfplumber.open(pdf_path) as pdf:
            print(f"  Paginas: {len(pdf.pages)}")
            print(f"  Metadados: {pdf.metadata}")

            # Primeira página
            page = pdf.pages[0]
            text = page.extract_text()

            print(f"\n  Texto extraido (primeiras 500 chars):")
            print(f"  {text[:500]}")

            # Tentar extrair tabelas
            tables = page.extract_tables()
            print(f"\n  Tabelas encontradas: {len(tables)}")

            if tables:
                print(f"  Primeira tabela (primeiras 3 linhas):")
                for row in tables[0][:3]:
                    print(f"    {row}")

        print("\n  [OK] pdfplumber funcionando!")

    except Exception as e:
        print(f"\n  [ERRO] {e}")


def test_tabula():
    """Testa extração tabular com tabula-py"""
    try:
        import tabula.io as tabula
    except ImportError:
        print("\n[SKIP] tabula-py nao disponivel")
        return

    pdf_path = Path("src/bp/training/DFS_Exemple/ABT - BP 03.2024.pdf")

    if not pdf_path.exists():
        print(f"[SKIP] {pdf_path.name} nao encontrado")
        return

    print("\n" + "=" * 80)
    print("TESTE 2: tabula-py (extração de tabelas)")
    print("=" * 80)
    print(f"Arquivo: {pdf_path.name}")

    try:
        # Extrair todas as tabelas da primeira página
        tables = tabula.read_pdf(
            str(pdf_path),
            pages=1,
            multiple_tables=True,
            pandas_options={"header": None},
        )

        print(f"  Tabelas encontradas: {len(tables)}")

        if tables:
            print(f"\n  Primeira tabela:")
            print(f"  Shape: {tables[0].shape}")
            print(f"  Head:")
            print(tables[0].head())

        print("\n  [OK] tabula-py funcionando!")

    except Exception as e:
        print(f"\n  [ERRO] {e}")


def test_pdfminer():
    """Testa extração com pdfminer.six"""
    try:
        from pdfminer.high_level import extract_text
    except ImportError:
        print("\n[SKIP] pdfminer.six nao disponivel")
        return

    pdf_path = Path("src/bp/training/DFS_Exemple/ABT - BP 03.2024.pdf")

    if not pdf_path.exists():
        print(f"[SKIP] {pdf_path.name} nao encontrado")
        return

    print("\n" + "=" * 80)
    print("TESTE 3: pdfminer.six (extração de texto estruturado)")
    print("=" * 80)
    print(f"Arquivo: {pdf_path.name}")

    try:
        text = extract_text(str(pdf_path), page_numbers=[0])

        print(f"  Texto extraido (primeiras 500 chars):")
        print(f"  {text[:500]}")

        # Contar linhas
        lines = [l for l in text.split("\n") if l.strip()]
        print(f"\n  Linhas nao vazias: {len(lines)}")

        print("\n  [OK] pdfminer.six funcionando!")

    except Exception as e:
        print(f"\n  [ERRO] {e}")


def test_pymupdf():
    """Testa extração com PyMuPDF (fitz)"""
    try:
        import fitz
    except ImportError:
        print("\n[SKIP] PyMuPDF nao disponivel")
        return

    pdf_path = Path("src/bp/training/DFS_Exemple/ABT - BP 03.2024.pdf")

    if not pdf_path.exists():
        print(f"[SKIP] {pdf_path.name} nao encontrado")
        return

    print("\n" + "=" * 80)
    print("TESTE 4: PyMuPDF/fitz (extração rápida)")
    print("=" * 80)
    print(f"Arquivo: {pdf_path.name}")

    try:
        doc = fitz.open(str(pdf_path))

        print(f"  Paginas: {doc.page_count}")
        print(f"  Metadados: {doc.metadata}")

        # Primeira página
        page = doc[0]
        text = page.get_text()

        print(f"\n  Texto extraido (primeiras 500 chars):")
        print(f"  {text[:500]}")

        # Extrair imagens
        images = page.get_images()
        print(f"\n  Imagens na pagina: {len(images)}")

        doc.close()

        print("\n  [OK] PyMuPDF funcionando!")

    except Exception as e:
        print(f"\n  [ERRO] {e}")


def test_financial_statement_parser():
    """Testa o parser de demonstrações financeiras"""
    try:
        from src.bp.parsers.financial_statement_parser import FinancialStatementParser
    except ImportError as e:
        print(f"\n[SKIP] FinancialStatementParser nao disponivel: {e}")
        return

    pdf_path = Path("src/bp/training/DFS_Exemple/ABT - BP 03.2024.pdf")

    if not pdf_path.exists():
        print(f"[SKIP] {pdf_path.name} nao encontrado")
        return

    print("\n" + "=" * 80)
    print("TESTE 5: FinancialStatementParser (parser integrado)")
    print("=" * 80)
    print(f"Arquivo: {pdf_path.name}")

    try:
        parser = FinancialStatementParser(str(pdf_path))
        result = parser.parse()

        print(f"  Sucesso: {result.success}")
        print(f"  Tipo de demonstracao: {result.statement_type}")
        print(f"  Contas extraidas: {len(result.accounts)}")
        print(f"  Metadados: {result.metadata}")

        if result.accounts:
            print(f"\n  Primeiras 5 contas:")
            for acc in result.accounts[:5]:
                codigo = acc.get("codigo", "N/A")
                desc = acc.get("descricao", "")[:40]
                valor = acc.get("valor_atual", 0)
                print(f"    {codigo:15s} | {desc:40s} | {valor:>15,.2f}")

        if result.warnings:
            print(f"\n  Avisos: {result.warnings}")

        if result.errors:
            print(f"\n  Erros: {result.errors}")

        print("\n  [OK] FinancialStatementParser funcionando!")

    except Exception as e:
        print(f"\n  [ERRO] {e}")
        import traceback

        traceback.print_exc()


def main():
    """Executa todos os testes"""
    print("=" * 80)
    print("TESTE DE PARSERS AVANCADOS DE PDF")
    print("=" * 80)

    test_pdfplumber()
    test_tabula()
    test_pdfminer()
    test_pymupdf()
    test_financial_statement_parser()

    print("\n" + "=" * 80)
    print("TESTES CONCLUIDOS")
    print("=" * 80)


if __name__ == "__main__":
    main()
