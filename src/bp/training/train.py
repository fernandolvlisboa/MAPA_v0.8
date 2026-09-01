"""
Script isolado de treinamento.

Uso:
    python src/bp/training/train.py

Adicione balancetes em: data/samples/
O sistema processa apenas arquivos novos automaticamente.

Arquivos gerados:
- processed_files.json: Lista de arquivos processados
- training_cache.json: Cache de matching para treino
- account_variations.json: Variações de descrição aprendidas
- learned_patterns.json: Padrões (sinônimos, abreviações)
- training_stats.json: Estatísticas acumuladas
"""

import sys
from pathlib import Path

# Adiciona raiz do projeto ao path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from src.bp.training.trainer import AccountTrainer


def main():
    """Executa treinamento incremental."""
    try:
        trainer = AccountTrainer()
        trainer.train(verbose=True)

        # Exporta relatório detalhado
        output_dir = Path("output")
        output_dir.mkdir(exist_ok=True)
        trainer.export_report(output_dir / "training_report.md")

    except Exception as e:
        print(f"\n❌ Erro durante treinamento: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
