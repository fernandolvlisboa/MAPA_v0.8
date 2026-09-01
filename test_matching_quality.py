"""
Teste de qualidade do matching com contas parseadas
Verifica se as contas extraídas pelos parsers conseguem ser matched
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.bp.parsers.dispatcher import ParseyCaller
from src.bp.matchers.conta_matcher import ContaMatcher
from src.bp.generators.plano_contas import PlanodeContas


def test_matching():
    """Testa matching em arquivo exemplo"""

    # Parsear arquivo
    file_path = Path("src/bp/training/DFS_Exemple/Balancete 072022 122022 - RBM.xlsx")
    print(f"[PARSING] {file_path}")

    parser = ParseyCaller(file_path)
    result = parser.parse_with_result()

    print(f"[OK] Parseado: {len(result.extracted_records)} contas")
    if not result.extracted_records:
        print(f"[ERRO] Nenhuma conta parseada!")
        print(f"   Errors: {result.errors}")
        print(f"   Warnings: {result.warnings}")
        return

    accounts = result.extracted_records

    # Mostrar sample
    print("\n[SAMPLE] Contas parseadas:")
    for i, acc in enumerate(accounts[:10], 1):
        codigo = acc.get("codigo", "N/A")
        descricao = acc.get("descricao", "")[:50]
        saldo = acc.get("saldo_final", 0)
        print(f"  {i:2d}. {codigo:15s} | {descricao:50s} | {saldo:>15,.2f}")
    print()

    # Carregar plano de contas e criar matcher
    print("[LOADING] Carregando plano de contas...")
    plano = PlanodeContas()

    print(f"[OK] Plano carregado: {len(plano.contas_flat)} contas padrao")
    print()

    # Criar matcher
    print("[MATCHING] Criando matcher...")
    matcher = ContaMatcher(plano_contas=plano)
    print(
        f"[OK] Matcher criado com {len(matcher.learned_variations)} variacoes aprendidas"
    )
    print()

    # Testar matching em sample
    print("[TEST] Testando matching em 20 contas:")
    print()

    matched = 0
    unmatched = 0
    review = 0

    for acc in accounts[:20]:
        descricao = acc.get("descricao", "")
        codigo = acc.get("codigo", "N/A")

        match_result = matcher.match(descricao)

        # Extract match info
        decision = match_result.decision
        needs_review = match_result.needs_review

        if decision:
            matched_code = decision.codigo
            score = decision.score * 100  # Convert to percentage
            match_type = decision.source
            status = "✓"
            matched += 1
        elif needs_review:
            matched_code = "REVIEW"
            score = 0
            match_type = "review"
            status = "?"
            review += 1
        else:
            matched_code = "N/A"
            score = 0
            match_type = "none"
            status = "✗"
            unmatched += 1

        print(
            f"{status} {codigo:15s} | {descricao[:40]:40s} → {matched_code:15s} ({match_type}, {score:.0f}%)"
        )

    print()
    print(f"[RESULTADOS]")
    print(f"   Matched: {matched}/20 ({matched / 20 * 100:.0f}%)")
    print(f"   Review:  {review}/20 ({review / 20 * 100:.0f}%)")
    print(f"   Unmatched: {unmatched}/20 ({unmatched / 20 * 100:.0f}%)")


if __name__ == "__main__":
    test_matching()
