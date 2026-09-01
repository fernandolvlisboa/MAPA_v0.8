"""
Testes para AccountTrainer (sistema de treinamento)
"""

import shutil
import tempfile
from pathlib import Path

import pytest

from src.bp.training.trainer import AccountTrainer

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_training_dir():
    """Diretório temporário para treinamento."""
    temp_dir = Path(tempfile.mkdtemp())

    yield temp_dir

    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def sample_csv(temp_training_dir):
    """CSV de exemplo para testes."""
    dfs_dir = temp_training_dir / "DFS_Exemple"
    dfs_dir.mkdir(parents=True, exist_ok=True)

    csv_path = dfs_dir / "test_balancete.csv"

    # CSV com contas sintéticas e analíticas
    content = """codigo,descricao,saldo
1.1.01,Disponibilidades,100000
1.1.01.01,Caixa e Bancos,100000
1.1.01.01.01,Caixa,10000
1.1.01.01.02,Bancos Conta Movimento,90000
1.1.01.01.02.001,Banco Itaú - Ag 1234 C/C 56789,45000
1.1.01.01.02.002,Banco Bradesco - Ag 5678 C/C 12345,45000
1.1.02,Clientes,50000
1.1.02.01,Clientes Nacionais,50000
1.1.02.01.001,ACME CORP LTDA (CNPJ: 12.345.678/0001-90),50000
"""

    with open(csv_path, "w", encoding="utf-8") as f:
        f.write(content)

    return csv_path


@pytest.fixture
def trainer(temp_training_dir):
    """Trainer configurado com diretório temporário — samples também em tmp,
    para não depender do corpus local do desenvolvedor."""
    return AccountTrainer(
        training_dir=str(temp_training_dir),
        plano_path="data/plano_contas.json",
        samples_dir=temp_training_dir / "DFS_Exemple",
    )


# =============================================================================
# Testes de Tracking de Arquivos
# =============================================================================


def test_get_new_files_empty(trainer):
    """Testa que retorna vazio quando não há arquivos."""
    new_files = trainer.get_new_files()
    assert len(new_files) == 0


def test_get_new_files_with_sample(trainer, sample_csv):
    """Testa identificação de arquivo novo."""
    new_files = trainer.get_new_files()
    assert len(new_files) == 1
    assert new_files[0].name == "test_balancete.csv"


def test_processed_files_tracking(trainer, sample_csv):
    """Testa que arquivos processados não aparecem como novos."""
    # Primeira vez
    new_files = trainer.get_new_files()
    assert len(new_files) == 1

    # Marca como processado
    trainer.processed_files.add(sample_csv.name)
    trainer._save_processed_files()

    # Segunda vez
    new_files = trainer.get_new_files()
    assert len(new_files) == 0


def test_list_processed_files(trainer, sample_csv):
    """Testa listagem de arquivos processados."""
    trainer.processed_files.add(sample_csv.name)
    processed = trainer.list_processed_files()

    assert sample_csv.name in processed


# =============================================================================
# Testes de Detecção Analítico vs Sintético
# =============================================================================


def test_is_analytical_cnpj():
    """Testa detecção de conta com CNPJ (analítica)."""
    trainer = AccountTrainer()

    conta = {
        "codigo": "2.1.01.01.001",
        "descricao": "ACME CORP LTDA (CNPJ: 12.345.678/0001-90)",
    }

    assert trainer.is_analytical_level(conta, []) is True


def test_is_analytical_conta_corrente():
    """Testa detecção de conta corrente (analítica)."""
    trainer = AccountTrainer()

    conta = {
        "codigo": "1.1.01.01.001",
        "descricao": "Banco Itaú - Ag 1234 C/C 56789",
    }

    assert trainer.is_analytical_level(conta, []) is True


def test_is_analytical_deep_level():
    """Testa detecção por nível profundo (>5)."""
    trainer = AccountTrainer()

    conta = {
        "codigo": "1.1.01.01.01.001.001",
        "descricao": "Conta Profunda",
        "nivel": 7,
    }

    assert trainer.is_analytical_level(conta, []) is True


def test_is_synthetic_with_children():
    """Testa que conta com filhos é sintética."""
    trainer = AccountTrainer()

    all_accounts = [
        {"codigo": "1.1.01", "descricao": "Disponibilidades"},
        {"codigo": "1.1.01.01", "descricao": "Caixa"},
    ]

    assert trainer.is_analytical_level(all_accounts[0], all_accounts) is False


def test_get_synthetic_accounts_filters_analytical(trainer):
    """Testa que filtra contas analíticas corretamente."""
    all_accounts = [
        {"codigo": "1.1.01", "descricao": "Disponibilidades"},  # Sintética
        {"codigo": "1.1.01.01", "descricao": "Caixa"},  # Sintética
        {
            "codigo": "1.1.01.01.001",
            "descricao": "Banco Itaú - C/C 123",
        },  # Analítica
        {
            "codigo": "2.1.01.001",
            "descricao": "ACME LTDA (CNPJ: 12.345.678/0001-90)",
        },  # Analítica
    ]

    synthetic = trainer.get_synthetic_accounts(all_accounts)

    assert len(synthetic) == 2
    assert all("C/C" not in c["descricao"] for c in synthetic)
    assert all("CNPJ" not in c["descricao"] for c in synthetic)


# =============================================================================
# Testes de Processamento
# =============================================================================


def test_process_file_success(trainer, sample_csv):
    """Testa processamento bem-sucedido de arquivo."""
    result = trainer.process_file(sample_csv)

    assert "error" not in result
    assert result["file"] == sample_csv.name
    assert result["total_accounts"] > 0
    assert result["synthetic_accounts"] > 0
    assert result["analytical_filtered"] > 0


def test_process_file_filters_analytical(trainer, sample_csv):
    """Testa que filtra contas analíticas."""
    result = trainer.process_file(sample_csv)

    # CSV tem 9 contas, mas 3 são analíticas (com CNPJ, C/C)
    assert result["analytical_filtered"] >= 3


# =============================================================================
# Testes de Aprendizado
# =============================================================================


def test_learn_from_results(trainer):
    """Testa aprendizado de variações."""
    results = [
        {
            "original": "Caixa",
            "match_codigo": "1.1.01.01.01",
            "match_descricao": "Caixa",
            "needs_review": False,
        },
        {
            "original": "Bancos",
            "match_codigo": "1.1.01.01.02",
            "match_descricao": "Bancos Conta Movimento",
            "needs_review": False,
        },
    ]

    trainer.learn_from_results(results)

    # Verifica que variações foram registradas
    assert "1.1.01.01.01" in trainer.variations
    assert trainer.variations["1.1.01.01.01"]["frequency"] == 1


def test_learn_ignores_needs_review(trainer):
    """Testa que não aprende de resultados que precisam revisão."""
    results = [
        {
            "original": "Conta Desconhecida",
            "match_codigo": None,
            "match_descricao": None,
            "needs_review": True,
        }
    ]

    trainer.learn_from_results(results)

    # Não deve ter aprendido nada
    assert len(trainer.variations) == 0


# =============================================================================
# Testes de Treinamento Completo
# =============================================================================


def test_train_no_new_files(trainer):
    """Testa treinamento sem arquivos novos."""
    result = trainer.train(verbose=False)

    assert result["new_files"] == 0
    assert result["processed"] == 0


def test_train_with_sample_file(trainer, sample_csv):
    """Testa treinamento completo com arquivo de exemplo."""
    result = trainer.train(verbose=False)

    assert result["new_files"] == 1
    assert result["processed"] == 1
    assert result["total_accounts"] > 0
    assert result["synthetic_accounts"] > 0
    assert result["analytical_filtered"] > 0

    # Verifica que arquivo foi marcado como processado
    assert sample_csv.name in trainer.processed_files


def test_train_incremental(trainer, sample_csv):
    """Testa que treinamento é incremental."""
    # Primeira execução
    result1 = trainer.train(verbose=False)
    assert result1["processed"] == 1

    # Segunda execução (sem novos arquivos)
    result2 = trainer.train(verbose=False)
    assert result2["processed"] == 0  # Não reprocessa


def test_stats_accumulate(trainer, sample_csv):
    """Testa que estatísticas acumulam."""
    # Primeira execução
    trainer.train(verbose=False)
    stats1 = trainer.get_stats_summary()

    # Adiciona outro arquivo
    dfs_dir = trainer.dfs_dir
    csv2 = dfs_dir / "test_balancete2.csv"
    shutil.copy(sample_csv, csv2)

    # Segunda execução
    trainer.train(verbose=False)
    stats2 = trainer.get_stats_summary()

    # Estatísticas devem ter aumentado
    assert stats2["total_files"] > stats1["total_files"]
    assert stats2["total_accounts"] > stats1["total_accounts"]


# =============================================================================
# Testes de Exportação
# =============================================================================


def test_export_report(trainer, sample_csv, temp_training_dir):
    """Testa exportação de relatório."""
    # Treina
    trainer.train(verbose=False)

    # Exporta
    report_path = temp_training_dir / "report.md"
    trainer.export_report(report_path)

    # Verifica que arquivo existe
    assert report_path.exists()

    # Verifica conteúdo básico
    content = report_path.read_text(encoding="utf-8")
    assert "Relatório de Treinamento" in content
    assert "Estatísticas Gerais" in content


# =============================================================================
# Testes de Reset
# =============================================================================


def test_reset_clears_all_data(trainer, sample_csv):
    """Testa que reset limpa todos os dados."""
    # Treina
    trainer.train(verbose=False)

    # Verifica que tem dados
    assert len(trainer.processed_files) > 0
    assert len(trainer.stats["sessions"]) > 0

    # Reset
    trainer.reset()

    # Verifica que limpou
    assert len(trainer.processed_files) == 0
    assert len(trainer.variations) == 0
    assert trainer.stats["total_files"] == 0
    assert len(trainer.stats["sessions"]) == 0
