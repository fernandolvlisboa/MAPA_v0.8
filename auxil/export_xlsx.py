"""CLI para exportar balancete em XLSX estruturado (Fase 5).

Uso:
    powershell> python -m auxil.export_xlsx -i caminho\balancete.xlsx -o output\balancete_export.xlsx

Suporta: CSV, XLS, XLSX, PDF (dependendo do parser genérico).
"""

from __future__ import annotations

import argparse
from pathlib import Path
from src.bp.exporters.xlsx_exporter import export_balance_sheet_to_xlsx


def parse_args():
    p = argparse.ArgumentParser(description="Exporta balancete para XLSX estruturado")
    p.add_argument(
        "-i", "--input", required=True, help="Arquivo de origem (CSV/XLS/XLSX/PDF)"
    )
    p.add_argument("-o", "--output", required=True, help="Arquivo XLSX destino")
    p.add_argument(
        "--plano", help="Plano de contas JSON (default data/plano_contas.json)"
    )
    p.add_argument(
        "--training-dir", default="src/bp/training", help="Diretório de treinamento"
    )
    p.add_argument("--auto-th", type=float, default=0.85, help="Threshold auto-match")
    p.add_argument("--requery-th", type=float, default=0.60, help="Threshold requery")
    return p.parse_args()


def main():
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    plano_path = Path(args.plano) if args.plano else None
    training_dir = Path(args.training_dir)
    path = export_balance_sheet_to_xlsx(
        input_path=input_path,
        output_path=output_path,
        plano_path=plano_path,
        training_dir=training_dir,
        auto_match_threshold=args.auto_th,
        requery_threshold=args.requery_th,
    )
    print(f"Export concluído: {path}")


if __name__ == "__main__":  # pragma: no cover
    main()
