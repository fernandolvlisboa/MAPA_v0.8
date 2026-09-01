import json
from pathlib import Path
import pytest

# `pydantic` vem do extra `curation` — a geração do plano master é passo de
# curadoria, não faz parte do núcleo embarcado.
pytest.importorskip("pydantic", reason="requer o extra `curation` (pydantic)")

from src.bp.generators.plano_contas_generator import PlanoContasGenerator


def test_process_excel_sample():
    # This test assumes a small sample file under data/examples/sample_plano.xlsx
    sample = Path("data/examples/sample_plano.xlsx")
    if not sample.exists():
        # If sample not provided, mark test skipped
        import pytest

        pytest.skip("sample_plano.xlsx not found in data/examples/")

    gen = PlanoContasGenerator(sample)
    flat, forms = gen.process_excel()
    assert isinstance(flat, list)
    assert isinstance(forms, dict)
    # each flat entry must have a codigo
    assert all("codigo" in c for c in flat)


def test_build_tree_index_roundtrip():
    # Synthetic small data
    flat = [
        {"codigo": "1", "descricao": "ATIVO", "forms": ["S"]},
        {
            "codigo": "1.1",
            "descricao": "ATIVO CIRCULANTE",
            "parent_id": "1",
            "forms": ["S"],
        },
        {"codigo": "1.1.1", "descricao": "CAIXA", "parent_id": "1.1", "forms": ["S"]},
    ]
    gen = PlanoContasGenerator()
    tree, index = gen.build_tree_and_index(flat)
    assert isinstance(tree, list)
    assert isinstance(index, dict)
    assert "1" in index and "1.1.1" in index
