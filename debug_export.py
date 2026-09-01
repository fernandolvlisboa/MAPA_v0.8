"""Debug do export para identificar onde está o problema"""

from pathlib import Path
from src.bp.parsers.dispatcher import ParseyCaller

# Teste 1: Parse direto
print("=" * 80)
print("TESTE 1: Parse direto do arquivo")
print("=" * 80)

file_path = Path("src/bp/training/DFS_Exemple/Balancete Real Life.xls")
print(f"Arquivo: {file_path}")
print(f"Existe: {file_path.exists()}")

try:
    caller = ParseyCaller(file_path)
    print(f"ParseyCaller criado: {caller}")

    accounts = caller.parse()
    print(f"\nTotal contas retornadas: {len(accounts)}")

    if accounts:
        print("\nPrimeiras 5 contas:")
        for i, acc in enumerate(accounts[:5], 1):
            print(
                f"{i}. Código: {acc.get('codigo', 'N/A')}, Descrição: {acc.get('descricao', 'N/A')}, Saldo: {acc.get('saldo', 0)}"
            )
    else:
        print("\n[ERRO] Nenhuma conta retornada!")

        # Tenta parse_with_result para ver mensagem de erro
        print("\n" + "=" * 80)
        print("TESTE 2: Parse com result para ver erro")
        print("=" * 80)
        result = caller.parse_with_result()
        print(f"Sucesso: {result.success}")
        print(f"Erro: {result.error}")
        print(f"Total contas: {len(result.contas)}")

except Exception as e:
    print(f"\n[ERRO CRÍTICO] {type(e).__name__}: {e}")
    import traceback

    traceback.print_exc()

# Teste 2: Verificar estrutura do arquivo
print("\n" + "=" * 80)
print("TESTE 3: Leitura direta do XLS")
print("=" * 80)

try:
    import pandas as pd

    df = pd.read_excel(file_path)
    print(f"Shape: {df.shape}")
    print(f"Colunas: {list(df.columns)}")
    print(f"\nPrimeiras 5 linhas:")
    print(df.head())
except Exception as e:
    print(f"[ERRO] {type(e).__name__}: {e}")
