"""
Análise do treinamento de contas
"""

import json
from pathlib import Path

# Carregar dados
with open("src/bp/training/account_variations.json", encoding="utf-8") as f:
    variations = json.load(f)

with open("src/bp/training/processed_files.json", encoding="utf-8") as f:
    processed = json.load(f)

# Estatísticas gerais
print("=" * 80)
print("RESUMO DO TREINAMENTO DE CONTAS")
print("=" * 80)
print()

print(f"Arquivos processados: {processed['total_processed']}")
print(f"Última atualização: {processed['last_update']}")
print()

total_codes = len(variations)
total_variations = sum(len(v["variations"]) for v in variations.values())
total_frequency = sum(v["frequency"] for v in variations.values())

print(f"Códigos únicos aprendidos: {total_codes}")
print(f"Variações de descrições: {total_variations}")
print(f"Ocorrências totais: {total_frequency}")
print()

# Top 15 códigos com mais variações
print("=" * 80)
print("TOP 15 CÓDIGOS COM MAIS VARIAÇÕES APRENDIDAS")
print("=" * 80)

top15 = sorted(variations.items(), key=lambda x: len(x[1]["variations"]), reverse=True)[
    :15
]

for i, (code, data) in enumerate(top15, 1):
    num_vars = len(data["variations"])
    freq = data["frequency"]
    print(f"{i:2d}. {code:20s} - {num_vars:3d} variações (freq: {freq:3d})")

    # Mostrar algumas variações como exemplo
    if num_vars <= 3:
        for var in data["variations"]:
            print(f"    • {var}")
    else:
        for var in data["variations"][:3]:
            print(f"    • {var}")
        print(f"    ... e mais {num_vars - 3} variações")
    print()

# Arquivos processados
print("=" * 80)
print(f"ARQUIVOS PROCESSADOS ({len(processed['files'])})")
print("=" * 80)

for i, file in enumerate(sorted(processed["files"]), 1):
    print(f"{i:2d}. {file}")
