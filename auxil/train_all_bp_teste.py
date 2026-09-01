"""
Script de treinamento completo usando todos os arquivos de auxil/BP_teste

Processa:
- CSVs (raiz + CSV/)
- PDFs (PDF/)
- TXTs (TXT/)
- XLS/XLSX (raiz + XLS/)

Usa o sistema de treinamento incremental do AccountTrainer.
"""

from pathlib import Path
import shutil
from src.bp.training.trainer import AccountTrainer


def prepare_training_data():
    """
    Copia todos os arquivos de BP_teste para DFS_Exemple/ (diretório de treinamento).
    """
    bp_teste = Path("auxil/BP_teste")
    training_dir = Path("src/bp/training/DFS_Exemple")

    # Limpa diretório de treinamento (opcional - comente se quiser manter arquivos antigos)
    if training_dir.exists():
        print(f"Limpando diretório de treinamento: {training_dir}")
        shutil.rmtree(training_dir)

    training_dir.mkdir(parents=True, exist_ok=True)

    # Arquivos na raiz
    print("\n[Copiando arquivos da raiz]")
    for file in bp_teste.glob("*"):
        if file.is_file() and file.suffix.lower() in [
            ".csv",
            ".xls",
            ".xlsx",
            ".pdf",
            ".txt",
        ]:
            dest = training_dir / file.name
            shutil.copy2(file, dest)
            print(f"  ✓ {file.name}")

    # CSV/
    csv_dir = bp_teste / "CSV"
    if csv_dir.exists():
        print("\n[Copiando CSVs]")
        for file in csv_dir.glob("*.csv"):
            dest = training_dir / file.name
            shutil.copy2(file, dest)
            print(f"  ✓ {file.name}")

    # PDF/
    pdf_dir = bp_teste / "PDF"
    if pdf_dir.exists():
        print("\n[Copiando PDFs]")
        for file in pdf_dir.glob("*.pdf"):
            dest = training_dir / file.name
            shutil.copy2(file, dest)
            print(f"  ✓ {file.name}")

    # TXT/
    txt_dir = bp_teste / "TXT"
    if txt_dir.exists():
        print("\n[Copiando TXTs]")
        for file in txt_dir.glob("*.TXT"):
            dest = training_dir / file.name
            shutil.copy2(file, dest)
            print(f"  ✓ {file.name}")

    # XLS/
    xls_dir = bp_teste / "XLS"
    if xls_dir.exists():
        print("\n[Copiando XLS/XLSX]")
        for file in xls_dir.glob("*"):
            if file.suffix.lower() in [".xls", ".xlsx"]:
                dest = training_dir / file.name
                shutil.copy2(file, dest)
                print(f"  ✓ {file.name}")

    total_files = len(list(training_dir.glob("*")))
    print(f"\n✓ Total de arquivos preparados: {total_files}")
    return total_files


def main():
    print("=" * 80)
    print("TREINAMENTO COMPLETO - BP_teste")
    print("=" * 80)

    # Prepara dados
    total_files = prepare_training_data()

    if total_files == 0:
        print("\n❌ Nenhum arquivo encontrado em BP_teste/")
        return

    # Inicializa trainer
    print("\n" + "=" * 80)
    print("INICIANDO TREINAMENTO")
    print("=" * 80)

    trainer = AccountTrainer(
        training_dir="src/bp/training", plano_path="data/plano_contas.json"
    )

    # Executa treinamento
    results = trainer.train(verbose=True)

    # Relatório final
    print("\n" + "=" * 80)
    print("RELATÓRIO FINAL")
    print("=" * 80)

    if results:
        print(f"\n✓ Arquivos processados: {results.get('processed', 0)}")
        print(f"✓ Contas totais: {results.get('total_accounts', 0)}")
        print(f"✓ Contas sintéticas: {results.get('synthetic_accounts', 0)}")
        print(f"✓ Contas analíticas filtradas: {results.get('analytical_filtered', 0)}")
        print(f"✓ Contas matched: {results.get('matched', 0)}")
        print(f"✓ Contas para revisão: {results.get('needs_review', 0)}")

        if results.get("needs_review", 0) > 0:
            print(
                f"\n⚠️  Execute 'python -m src.bp.training.review_tool' para revisar pendências"
            )

    # Estatísticas gerais
    stats = trainer.get_stats_summary()
    print("\n📊 ESTATÍSTICAS ACUMULADAS")
    print(f"   Total de arquivos processados: {stats.get('total_files', 0)}")
    print(f"   Total de contas processadas: {stats.get('total_accounts', 0)}")
    print(f"   Total de padrões aprendidos: {len(trainer.learned_patterns)}")
    print(f"   Total de variações conhecidas: {len(trainer.variations)}")

    print("\n✓ Treinamento concluído!")


if __name__ == "__main__":
    main()
