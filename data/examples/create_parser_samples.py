"""
Cria arquivos de exemplo para testar os parsers.
"""

import pandas as pd
from pathlib import Path


def create_sample_excel():
    """Cria um arquivo Excel de exemplo com balanço."""
    data = {
        "Código": ["1", "1.1", "1.1.1", "1.1.2", "1.2", "2", "2.1"],
        "Descrição": [
            "ATIVO",
            "ATIVO CIRCULANTE",
            "CAIXA",
            "BANCOS",
            "ESTOQUES",
            "PASSIVO",
            "FORNECEDORES",
        ],
        "Saldo": [
            "100.000,00",
            "60.000,00",
            "10.000,00",
            "50.000,00",
            "40.000,00",
            "100.000,00",
            "30.000,00",
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
    }

    df = pd.DataFrame(data)
    output_path = Path(__file__).parent / "balanco_exemplo.xlsx"
    df.to_excel(output_path, index=False)
    print(f"✓ Criado: {output_path}")
    return output_path


def create_sample_csv():
    """Cria um arquivo CSV de exemplo."""
    data = {
        "Codigo": ["1", "1.1", "1.1.1", "2", "2.1"],
        "Descricao": ["ATIVO", "ATIVO CIRCULANTE", "CAIXA", "PASSIVO", "FORNECEDORES"],
        "Saldo": ["100000.00", "60000.00", "10000.00", "100000.00", "30000.00"],
        "Natureza": ["Devedora", "Devedora", "Devedora", "Credora", "Credora"],
    }

    df = pd.DataFrame(data)
    output_path = Path(__file__).parent / "balanco_exemplo.csv"
    df.to_csv(output_path, index=False, sep=";")
    print(f"✓ Criado: {output_path}")
    return output_path


def create_sample_txt():
    """Cria um arquivo TXT de exemplo com colunas separadas por tabs."""
    lines = [
        "Codigo\tDescricao\tSaldo\tNatureza",
        "1\tATIVO\t100000.00\tDevedora",
        "1.1\tATIVO CIRCULANTE\t60000.00\tDevedora",
        "1.1.1\tCAIXA\t10000.00\tDevedora",
        "1.1.2\tBANCOS\t50000.00\tDevedora",
        "2\tPASSIVO\t100000.00\tCredora",
        "2.1\tFORNECEDORES\t30000.00\tCredora",
    ]

    output_path = Path(__file__).parent / "balanco_exemplo.txt"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"✓ Criado: {output_path}")
    return output_path


if __name__ == "__main__":
    print("Criando arquivos de exemplo para testes...")
    create_sample_excel()
    create_sample_csv()
    create_sample_txt()
    print("\n✓ Todos os arquivos criados com sucesso!")
