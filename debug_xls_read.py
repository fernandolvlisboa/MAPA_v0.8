"""Debug do XlsParser para identificar travamento"""

from pathlib import Path
import sys
import signal


# Timeout handler
def timeout_handler(signum, frame):
    print("\n[TIMEOUT] Operação travou por mais de 10 segundos!")
    sys.exit(1)


# Set timeout (Windows não suporta SIGALRM, então vamos fazer manual)
file_path = Path("src/bp/training/DFS_Exemple/Balancete Real Life.xls")

print("=" * 80)
print("TESTE: Leitura direta do arquivo XLS")
print("=" * 80)
print(f"Arquivo: {file_path}")
print(f"Existe: {file_path.exists()}\n")

try:
    # Teste 1: pandas direto
    print("1. Tentando pd.read_excel()...")
    import pandas as pd
    import time

    start = time.time()
    df = pd.read_excel(file_path)
    elapsed = time.time() - start

    print(f"   [OK] Lido em {elapsed:.2f}s")
    print(f"   Shape: {df.shape}")
    print(f"   Colunas: {list(df.columns)}")
    print(f"\n   Primeiras 3 linhas:")
    print(df.head(3))

except Exception as e:
    print(f"   [ERRO] {type(e).__name__}: {e}")

print("\n" + "=" * 80)
print("TESTE: XlsParser.read()")
print("=" * 80)

try:
    from src.bp.parsers.xls_parser import XlsParser

    print("2. Criando XlsParser...")
    parser = XlsParser(file_path)
    print(f"   [OK] Parser criado: {parser}")

    print("\n3. Chamando parser.read()...")
    start = time.time()
    df2 = parser.read()
    elapsed = time.time() - start

    if df2 is None:
        print(f"   [ERRO] Retornou None!")
    else:
        print(f"   [OK] Lido em {elapsed:.2f}s")
        print(f"   Shape: {df2.shape}")
        print(f"   Colunas: {list(df2.columns)}")

except Exception as e:
    print(f"   [ERRO] {type(e).__name__}: {e}")
    import traceback

    traceback.print_exc()
