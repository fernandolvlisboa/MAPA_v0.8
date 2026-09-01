"""
Script de demonstração completo: PDF → Parsing → Matching

Demonstra o workflow end-to-end:
1. Parse de PDF (Fase 3.5)
2. Matching inteligente (Fase 4)
3. Exportação de resultados
"""

from pathlib import Path
from src.bp.parsers.financial_statement_parser import FinancialStatementParser
from src.bp.matchers import ContaMatcher
from src.bp.generators.plano_contas import PlanodeContas


def main():
    print("=" * 80)
    print("DEMO: Workflow Completo — PDF → Parsing → Matching → Export")
    print("=" * 80)

    # 1. Configuração
    print("\n[1/5] Carregando configurações...")
    plano_path = Path("data/plano_contas.json")
    cache_path = Path("data/match_cache.json")

    if not plano_path.exists():
        print(f"❌ Erro: {plano_path} não encontrado")
        print("Execute: python auxil/generate_plano_contas.py")
        return

    plano = PlanodeContas(plano_path)
    matcher = ContaMatcher(
        plano_contas=plano,
        cache_path=str(cache_path),
        auto_accept_threshold=0.85,
        requery_threshold=0.60,
        use_ai=False,
    )
    print(f"✓ Plano de contas: {len(plano.contas_flat)} contas")
    print(f"✓ Matcher configurado (threshold: 0.85)")

    # 2. Seleção de PDF
    print("\n[2/5] Selecionando PDF de exemplo...")

    # Procura PDFs de exemplo
    pdf_examples = list(Path("auxil/BP_PDF_ex/DF_completa").glob("*.pdf"))

    if not pdf_examples:
        print("❌ Nenhum PDF encontrado em auxil/BP_PDF_ex/DF_completa/")
        print("Adicione arquivos PDF de demonstração neste diretório")
        return

    pdf_path = pdf_examples[0]
    print(f"✓ Usando: {pdf_path.name}")

    # 3. Parse do PDF
    print("\n[3/5] Processando PDF...")
    parser = FinancialStatementParser(str(pdf_path))

    try:
        result = parser.parse_complete()
        print(f"✓ PDF processado com sucesso")
        print(f"  Tipo: {result.metadata.pdf_type}")
        print(f"  Empresa: {result.metadata.company or 'Não identificada'}")
        print(f"  BP: {len(result.balanco.accounts) if result.balanco else 0} contas")
        print(f"  DRE: {len(result.dre.accounts) if result.dre else 0} contas")
    except Exception as e:
        print(f"❌ Erro ao processar PDF: {e}")
        return

    # 4. Matching de contas
    print("\n[4/5] Realizando matching...")

    # Prepara contas para matching
    bp_contas = []
    if result.balanco:
        for conta in result.balanco.accounts:
            descricao = conta["descricao"]

            # Tenta inferir tipo baseado em descrição
            tipo = None
            if any(
                k in descricao.upper()
                for k in ["ATIVO", "CIRCULANTE", "REALIZÁVEL", "IMOBILIZADO"]
            ):
                tipo = "ATIVO"
            elif any(
                k in descricao.upper() for k in ["PASSIVO", "EXIGÍVEL", "OBRIGAÇÕES"]
            ):
                tipo = "PASSIVO"
            elif any(k in descricao.upper() for k in ["PATRIMÔNIO", "CAPITAL"]):
                tipo = "PATRIMÔNIO LÍQUIDO"

            bp_contas.append(
                {
                    "descricao": descricao,
                    "tipo": tipo,
                    "saldo": conta.get("current", 0),
                }
            )

    if not bp_contas:
        print("⚠ Nenhuma conta encontrada no BP para matching")
        return

    # Processa matching
    match_results = matcher.match_batch(bp_contas)

    # Separa resultados
    matched_accounts = []
    review_needed = []

    for i, match_result in enumerate(match_results):
        original = bp_contas[i]

        if match_result.decision and not match_result.needs_review:
            matched_accounts.append(
                {
                    "original": original["descricao"],
                    "mapped_codigo": match_result.decision.codigo,
                    "mapped_descricao": match_result.decision.descricao,
                    "score": match_result.decision.score,
                    "source": match_result.decision.source,
                    "saldo": original["saldo"],
                }
            )
        else:
            review_needed.append(
                {
                    "original": original["descricao"],
                    "candidates": [
                        {"codigo": c.codigo, "descricao": c.descricao, "score": c.score}
                        for c in match_result.candidates[:3]
                    ],
                }
            )

    # Estatísticas
    stats = matcher.get_stats(match_results)

    print(f"✓ Matching concluído")
    print(f"  Total: {stats['total']} contas")
    print(f"  Auto-matched: {stats['auto_matched']} ({stats['auto_matched_pct']:.1f}%)")
    print(
        f"  Precisam revisão: {stats['needs_review']} ({stats['needs_review_pct']:.1f}%)"
    )
    print(f"  Cache hits: {stats['cache_hits']} ({stats['cache_hit_rate']:.1f}%)")
    print(f"  Confiança média: {stats['avg_confidence']:.2f}")

    # 5. Exportação
    print("\n[5/5] Exportando resultados...")

    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)

    # Exporta matched accounts
    matched_md = output_dir / "matched_accounts.md"
    with open(matched_md, "w", encoding="utf-8") as f:
        f.write("# Contas Mapeadas\n\n")
        f.write(f"**PDF:** {pdf_path.name}\n")
        f.write(f"**Total:** {len(matched_accounts)} contas\n\n")
        f.write("| Original | Código | Descrição Mapeada | Score | Source | Saldo |\n")
        f.write("|----------|--------|-------------------|-------|--------|-------|\n")

        for acc in matched_accounts:
            f.write(
                f"| {acc['original'][:40]} | {acc['mapped_codigo']} | "
                f"{acc['mapped_descricao'][:40]} | {acc['score']:.2f} | "
                f"{acc['source']} | {acc['saldo']:,.2f} |\n"
            )

    print(f"✓ Contas mapeadas: {matched_md}")

    # Exporta review needed
    if review_needed:
        review_md = output_dir / "review_needed.md"
        with open(review_md, "w", encoding="utf-8") as f:
            f.write("# Contas que Precisam Revisão\n\n")
            f.write(f"**Total:** {len(review_needed)} contas\n\n")

            for item in review_needed:
                f.write(f"## {item['original']}\n\n")
                f.write("**Candidatos:**\n\n")
                for i, cand in enumerate(item["candidates"], 1):
                    f.write(
                        f"{i}. `{cand['codigo']}` — {cand['descricao']} "
                        f"(score: {cand['score']:.2f})\n"
                    )
                f.write("\n")

        print(f"✓ Revisão necessária: {review_md}")

    # Exporta cache para auditoria
    cache_audit = output_dir / "match_cache_audit.md"
    matcher.cache.export_for_review(str(cache_audit))
    print(f"✓ Auditoria do cache: {cache_audit}")

    # Relatório final
    print("\n" + "=" * 80)
    print("RESUMO FINAL")
    print("=" * 80)
    print(f"✓ PDF processado: {pdf_path.name}")
    print(
        f"✓ Contas extraídas: {len(result.balanco.accounts) if result.balanco else 0}"
    )
    print(f"✓ Contas mapeadas: {len(matched_accounts)}")
    print(f"⚠ Precisam revisão: {len(review_needed)}")
    print(f"✓ Taxa de sucesso: {stats['auto_matched_pct']:.1f}%")
    print(f"\n✓ Resultados salvos em: {output_dir}/")
    print("=" * 80)


if __name__ == "__main__":
    main()
