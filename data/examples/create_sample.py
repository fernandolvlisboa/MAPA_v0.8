"""
Script para gerar um arquivo Excel sample (sintético) para testes.
Executa uma vez para criar data/examples/sample_plano.xlsx
"""

import pandas as pd
from pathlib import Path


def create_sample_excel():
    """Cria um arquivo Excel sample com estrutura simples para testes."""

    # Dados de exemplo simples
    data = {
        "Código": ["1", "1.1", "1.1.1", "1.1.2", "1.2", "2", "2.1"],
        "Descrição": [
            "ATIVO",
            "ATIVO CIRCULANTE",
            "CAIXA",
            "BANCOS",
            "ATIVO NÃO CIRCULANTE",
            "PASSIVO",
            "PASSIVO CIRCULANTE",
        ],
        "Saldo": [
            100000.00,
            50000.00,
            5000.00,
            45000.00,
            50000.00,
            100000.00,
            60000.00,
        ],
        "Natureza": [
            "Devedora",
            "Devedora",
            "Devedora",
            "Devedora",
            "Devedora",
            "Credora",
            "Credora",
        ],
        "Tipo": ["ATIVO", "ATIVO", "ATIVO", "ATIVO", "ATIVO", "PASSIVO", "PASSIVO"],
    }

    df = pd.DataFrame(data)

    # Cria arquivo Excel com duas abas para testar merge
    output_path = Path(__file__).parent.parent / "examples" / "sample_plano.xlsx"

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Balanço", index=False)
        # Adiciona uma segunda aba com dados ligeiramente diferentes (para testar merge)
        df2 = df.copy()
        df2.loc[0, "Saldo"] = 105000.00  # saldo diferente
        df2.to_excel(writer, sheet_name="L100A", index=False)

    print(f"✅ Arquivo sample criado em: {output_path}")
    return output_path


if __name__ == "__main__":
    create_sample_excel()
