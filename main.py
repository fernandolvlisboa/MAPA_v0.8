#!/usr/bin/env python
"""
BP — ponto de entrada único.

    uv run python main.py            # abre a janela (o que o cliente vê)
    uv run python main.py --menu     # menu de terminal (bancada do analista)

Rodar sem argumento abre a **interface do usuário final** (o mesmo alvo do
``app.py``, que vai virar o executável). É a apresentação: você chama e o
programa aparece, sem passo intermediário — a fonte fica exatamente igual ao
que vai ser distribuído.

``--menu`` guarda a bancada do analista — treinar com balancetes novos, revisar
pendências — que não faz sentido na janela do colaborador. Nenhum arquivo além
deste conhece a bandeira; o resto do projeto continua chamando as mesmas
funções (``AccountTrainer``, ``build_gt_output``, ``review_wizard``).

Ver ``PLANO_J_INTERFACE.md`` para o desenho da janela.
"""

from __future__ import annotations

import contextlib
import sys
from pathlib import Path

# Permite `python main.py` da raiz sem instalar o pacote.
RAIZ = Path(__file__).resolve().parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))


def _saida_nunca_derruba_o_programa() -> None:
    """
    Impede que um símbolo fora da tabela do console mate o processo.

    O console clássico do Windows usa cp1252, que não tem ``→``, ``✓`` nem
    ``✗``. Cada um deles é um ``UnicodeEncodeError`` **fatal**: o processo
    morre com código 1 no meio de um ``print`` e o usuário vê um traceback em
    vez do menu. Aconteceu duas vezes seguidas, com dois caracteres
    diferentes — trocar o caractere culpado conserta um caso e deixa a
    armadilha armada para o próximo.

    Só ``errors="replace"``, mantendo a codificação do console. Forçar UTF-8
    aqui foi a minha primeira tentativa e estava errada: o processo parava de
    cair, mas o console decodificava os bytes pela tabela dele e o menu saía
    ``BP â€” PadronizaÃ§Ã£o``. Trocar queda por texto ilegível não é conserto.

    Mantendo a tabela do console, tudo que cabe nela sai correto — acentos e
    travessão incluídos, que são cp1252 — e só o símbolo impossível vira
    ``?``. Degradar o enfeite, nunca a execução nem o resto do texto.

    Silencioso quando não dá para reconfigurar (saída redirecionada, stream
    substituído por um teste): aí vale o comportamento de antes.
    """
    for fluxo in (sys.stdout, sys.stderr):
        with contextlib.suppress(AttributeError, ValueError, OSError):
            fluxo.reconfigure(errors="replace")


_saida_nunca_derruba_o_programa()

PASTA_TREINO = RAIZ / "src" / "bp" / "training" / "DFS_Exemple"
PASTA_SAIDA = RAIZ / "output" / "gt"


# ---------------------------------------------------------------------------
# Utilidades de terminal
# ---------------------------------------------------------------------------


def _titulo(texto: str) -> None:
    print("\n" + "=" * 68)
    print(texto)
    print("=" * 68)


def _perguntar(rotulo: str, default: str | None = None) -> str:
    sufixo = f" [{default}]" if default else ""
    resposta = input(f"{rotulo}{sufixo}: ").strip()
    return resposta or (default or "")


def _pedir_arquivo(rotulo: str) -> Path | None:
    """Pede um caminho e insiste até existir (ou o usuário cancelar com vazio)."""
    while True:
        bruto = _perguntar(f"{rotulo} (Enter p/ cancelar)")
        if not bruto:
            return None
        # Aceita caminho com aspas coladas por copiar/colar.
        caminho = Path(bruto.strip().strip('"').strip("'")).expanduser()
        if caminho.exists():
            return caminho
        print(f"  ✗ não encontrei: {caminho}")


def _pedir_ano(rotulo: str, default: int | None = None) -> int:
    while True:
        bruto = _perguntar(rotulo, str(default) if default else None)
        if bruto.isdigit() and 1900 <= int(bruto) <= 2100:
            return int(bruto)
        print("  ✗ informe um ano com 4 dígitos (ex.: 2024)")


# ---------------------------------------------------------------------------
# Ações
# ---------------------------------------------------------------------------


def acao_treinar() -> None:
    """Processa os balancetes novos em DFS_Exemple/ e aprende com eles."""
    _titulo("TREINAMENTO — aprender com balancetes")
    print(f"Lê os arquivos NOVOS em: {PASTA_TREINO}")
    print("(coloque balancetes .xlsx/.xls/.csv/.pdf nessa pasta antes de treinar)")
    if _perguntar("Rodar o treinamento agora? (s/N)").lower() not in ("s", "sim"):
        print("  cancelado.")
        return

    from src.bp.training.trainer import AccountTrainer

    trainer = AccountTrainer()
    resultado = trainer.train(verbose=True)

    saida = RAIZ / "output" / "training_report.md"
    trainer.export_report(saida)
    if resultado.get("processed"):
        print(f"\n✓ Relatório atualizado em: {saida}")
    else:
        print("\n(nenhum arquivo novo — nada a aprender desta vez)")


def acao_padronizar() -> None:
    """Lê um balancete e entrega o Template GT povoado."""
    _titulo("PADRONIZAR -- balancete -> Template GT")
    entrada = _pedir_arquivo("Caminho do balancete")
    if not entrada:
        print("  cancelado.")
        return

    ano = _pedir_ano("Ano/exercício do balancete", default=2024)
    cliente = _perguntar("Nome do cliente", default=entrada.stem)

    escala_txt = _perguntar(
        "Valores já estão em milhares? (s = não dividir / N = dividir por 1000)",
        default="N",
    )
    escala = 1.0 if escala_txt.lower() in ("s", "sim") else 1000.0

    PASTA_SAIDA.mkdir(parents=True, exist_ok=True)
    saida = PASTA_SAIDA / f"{_slug(cliente)}_{ano}.xlsx"

    print("\nProcessando... (parse -> matching -> projecao -> template)")
    from src.bp.output.build_gt_output import build_gt_output

    try:
        r = build_gt_output(
            entrada,
            saida,
            ano_base=ano,
            nome_cliente=cliente,
            escala=escala,
        )
    except Exception as exc:  # erro na vitrine vira mensagem amigável, não stacktrace
        print(f"\n✗ Falhou: {exc}")
        return

    print("\n" + "-" * 68)
    print(f"✓ Arquivo gerado: {r.output_path}")
    print(f"  Contas lidas ......... {r.contas_lidas}")
    print(f"  Com match ............ {r.contas_tratadas}")
    print(f"  Sem match (revisão) .. {r.contas_nao_identificadas}")
    print(f"  Match rate ........... {r.match_rate:.1%}")
    print(f"  Balanço confere ...... {'OK' if r.balanco_confere else 'NOK'}")
    for aviso in r.avisos:
        print(f"  ⚠ {aviso}")
    print("\nAbra o arquivo no Excel: BP_GT e DRE_GT são a entrega ao cliente;")
    print("Sumário e Contas Não Identificadas são para você revisar.")


def acao_revisar() -> None:
    """Abre o assistente interativo de revisão das contas pendentes."""
    _titulo("REVISAR — classificar contas pendentes")
    print("O assistente lista o que ficou sem match e ensina o sistema.")
    print("Dentro dele: s=buscar  h=hierarquia  c=código  i=ignorar  k=pular  q=sair")
    if _perguntar("Abrir o assistente? (s/N)").lower() not in ("s", "sim"):
        print("  cancelado.")
        return

    from src.bp.training import review_wizard

    # Reaproveita o main() do wizard como se fosse chamado com --all.
    argv = sys.argv
    try:
        sys.argv = ["review_wizard", "--all"]
        review_wizard.main()
    finally:
        sys.argv = argv


# ---------------------------------------------------------------------------
# Menu
# ---------------------------------------------------------------------------

_OPCOES = {
    "1": ("Treinar (aprender com balancetes novos)", acao_treinar),
    "2": ("Padronizar um balancete -> Template GT", acao_padronizar),
    "3": ("Revisar contas pendentes (assistente)", acao_revisar),
    "0": ("Sair", None),
}


def _slug(texto: str) -> str:
    limpo = "".join(c if c.isalnum() else "_" for c in texto.strip())
    return "_".join(filter(None, limpo.split("_"))) or "cliente"


def _menu() -> str:
    _titulo("BP — Padronização de Balancetes")
    print("O que você quer fazer?\n")
    for chave, (rotulo, _) in _OPCOES.items():
        print(f"  [{chave}] {rotulo}")
    return _perguntar("\nEscolha").strip()


def _loop_menu() -> int:
    """O menu de terminal — bancada do analista, atrás de ``--menu``."""
    while True:
        try:
            escolha = _menu()
        except (EOFError, KeyboardInterrupt):
            print("\nAté logo.")
            return 0

        if escolha not in _OPCOES:
            print("  ✗ opção inválida.")
            continue
        if escolha == "0":
            print("Até logo.")
            return 0

        _, acao = _OPCOES[escolha]
        try:
            acao()
        except KeyboardInterrupt:
            print("\n(interrompido — voltando ao menu)")
        except Exception as exc:  # nunca derruba a vitrine
            print(f"\n✗ Erro inesperado: {exc}")


def main(argv: list[str] | None = None) -> int:
    """Ponto de entrada. Sem argumento abre a janela; ``--menu`` abre o menu."""
    args = list(sys.argv[1:] if argv is None else argv)
    if any(a in ("--menu", "-m") for a in args):
        return _loop_menu()
    if any(a in ("--help", "-h") for a in args):
        print(__doc__)
        return 0

    # Vitrine visual: abre a mesma janela que o executável vai abrir.
    try:
        from src.bp.app import main as abrir_janela
    except Exception as exc:
        # Só cai aqui se `tkinter` faltar — em Linux, `apt install python3-tk`.
        print(f"Não consegui abrir a janela: {exc}")
        print("Use `uv run python main.py --menu` para o menu de terminal.")
        return 1
    return abrir_janela()


if __name__ == "__main__":
    raise SystemExit(main())
