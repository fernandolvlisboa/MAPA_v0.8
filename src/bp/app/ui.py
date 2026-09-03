"""
A janela do BP.

Uma janela só, três estados: **escolher**, **processando**, **resultado**. Sem
menu, sem abas, sem assistente de vários passos — a tarefa é uma só (virar
balancete em entrega no Template GT) e ela cabe numa tela.

Regras que este arquivo segue:

- **Nada de contabilidade aqui.** Toda decisão é de ``service.py``, que chama o
  núcleo. Esta camada desenha e coleta.
- **A janela nunca congela.** A geração roda em thread; a tela conversa com ela
  por fila e ``after()``. Widget só é tocado pela thread principal.
- **Erro vira frase.** O usuário final não deve ver stacktrace nenhum.

Paleta tirada do próprio ``templates/Template_GT_BP_Padrao_v3.xlsx`` (roxo do
cabeçalho, teal dos destaques, cinza das linhas): o app parece a mesma coisa que
a planilha que ele entrega.
"""

from __future__ import annotations

import contextlib
import functools
import queue
import sys
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, ttk
from tkinter import font as tkfont

from .. import versao
from . import dnd, paths, service
from .service import Entrada

# ---------------------------------------------------------------------------
# Identidade visual
# ---------------------------------------------------------------------------

ROXO = "#4F2D7F"        # cabeçalho do BP_GT
ROXO_ESCURO = "#3C2161"  # estado pressionado
TEAL = "#00A7B5"        # destaques do template
FUNDO = "#F2F0EE"       # a mesma faixa clara do template
CARTAO = "#FFFFFF"
BORDA = "#D8D4D0"
TEXTO = "#1F1F1F"
TEXTO_FRACO = "#595959"
SUCESSO = "#1E7B34"
ATENCAO = "#8A5A00"
ATENCAO_FUNDO = "#FFF6E5"
ERRO = "#B3261E"

TITULO_JANELA = "MAPA — Mapeamento de Plano de Contas"


def _fonte_base() -> str:
    disponiveis = set(tkfont.families())
    for nome in ("Segoe UI", "Inter", "Helvetica Neue", "DejaVu Sans", "Arial",
                 "Liberation Sans", "helvetica"):
        if nome in disponiveis:
            return nome
    return "TkDefaultFont"


def _encurtar(texto: str, limite: int = 46) -> str:
    """Nome de arquivo longo não pode empurrar a coluna do exercício."""
    if len(texto) <= limite:
        return texto
    corte = limite - 3
    return texto[: corte // 2] + "..." + texto[-(corte - corte // 2) :]


def _moeda(valor: float | None) -> str:
    if valor is None:
        return "—"
    inteiro = f"{abs(valor):,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")
    return f"{'-' if valor < 0 else ''}{inteiro}"


# ---------------------------------------------------------------------------
# Aplicação
# ---------------------------------------------------------------------------


class AplicacaoBP:
    """Janela única do BP. Instanciar e chamar :meth:`rodar`."""

    def __init__(self) -> None:
        self.root, self.backend_dnd = dnd.criar_root()
        self.root.report_callback_exception = self._erro_em_callback
        self.fonte = _fonte_base()

        self.entradas: list[Entrada] = []
        self.pasta_saida: Path = self._pasta_saida_inicial()
        self.fila: queue.Queue = queue.Queue()
        self.resultado: service.Resultado | None = None

        self.var_cliente = tk.StringVar()
        self.var_milhares = tk.BooleanVar(value=False)
        self.var_saida = tk.StringVar(value=str(self.pasta_saida))
        self.var_recado = tk.StringVar()
        self.var_passo = tk.StringVar(value="Preparando...")
        self.var_alvo = tk.StringVar()

        self._montar_janela()
        self._montar_estilos()
        self._montar_telas()
        self._mostrar("entrada")
        self._atualizar_lista()

    # -- infraestrutura da janela -------------------------------------------

    def _montar_janela(self) -> None:
        self.root.title(TITULO_JANELA)
        self.root.configure(bg=FUNDO)
        self.root.minsize(760, 600)
        largura, altura = 860, 680
        x = max(0, (self.root.winfo_screenwidth() - largura) // 2)
        y = max(0, (self.root.winfo_screenheight() - altura) // 3)
        self.root.geometry(f"{largura}x{altura}+{x}+{y}")

    def _montar_estilos(self) -> None:
        estilo = ttk.Style(self.root)
        if "clam" in estilo.theme_names():
            estilo.theme_use("clam")  # o único tema com cor previsível nos 3 SOs

        estilo.configure("TFrame", background=FUNDO)
        estilo.configure("Cartao.TFrame", background=CARTAO)
        estilo.configure("Barra.TFrame", background=ROXO)

        estilo.configure("TLabel", background=FUNDO, foreground=TEXTO,
                         font=(self.fonte, 10))
        estilo.configure("Cartao.TLabel", background=CARTAO, foreground=TEXTO,
                         font=(self.fonte, 10))
        estilo.configure("Fraco.TLabel", background=FUNDO, foreground=TEXTO_FRACO,
                         font=(self.fonte, 9))
        estilo.configure("CartaoFraco.TLabel", background=CARTAO,
                         foreground=TEXTO_FRACO, font=(self.fonte, 9))
        estilo.configure("Secao.TLabel", background=FUNDO, foreground=TEXTO,
                         font=(self.fonte, 11, "bold"))
        estilo.configure("Titulo.TLabel", background=ROXO, foreground="#FFFFFF",
                         font=(self.fonte, 15, "bold"))
        estilo.configure("Subtitulo.TLabel", background=ROXO, foreground="#D9CFE8",
                         font=(self.fonte, 10))
        estilo.configure("Erro.TLabel", background=FUNDO, foreground=ERRO,
                         font=(self.fonte, 9))

        estilo.configure(
            "Acao.TButton", font=(self.fonte, 11, "bold"), foreground="#FFFFFF",
            background=ROXO, borderwidth=0, focusthickness=0, padding=(22, 11),
        )
        estilo.map(
            "Acao.TButton",
            background=[("disabled", "#B9AECB"), ("pressed", ROXO_ESCURO),
                        ("active", ROXO_ESCURO)],
            foreground=[("disabled", "#F0ECF5")],
        )
        estilo.configure(
            "Secundaria.TButton", font=(self.fonte, 10), foreground=ROXO,
            background=CARTAO, borderwidth=1, padding=(14, 8),
        )
        estilo.map("Secundaria.TButton",
                   background=[("active", "#EFEAF5")],
                   bordercolor=[("!disabled", BORDA)])
        estilo.configure("Linha.TButton", font=(self.fonte, 10), padding=(6, 2),
                         borderwidth=0, background=CARTAO, foreground=TEXTO_FRACO)
        estilo.map("Linha.TButton", background=[("active", "#F3EFEA")],
                   foreground=[("active", ERRO)])

        estilo.configure("TEntry", fieldbackground=CARTAO, bordercolor=BORDA,
                         padding=7)
        estilo.configure("TRadiobutton", background=FUNDO, foreground=TEXTO,
                         font=(self.fonte, 10))
        estilo.map("TRadiobutton", background=[("active", FUNDO)])
        estilo.configure("TSpinbox", fieldbackground=CARTAO, arrowsize=11)
        # Marcação das abas na tela de escolha de exercícios.
        estilo.configure("Cartao.TCheckbutton", background=CARTAO,
                         foreground=TEXTO, font=(self.fonte, 10))
        estilo.map("Cartao.TCheckbutton", background=[("active", CARTAO)])
        estilo.configure("Andamento.Horizontal.TProgressbar",
                         background=TEAL, troughcolor="#E4E0DC", borderwidth=0)

    def _montar_telas(self) -> None:
        cabecalho = ttk.Frame(self.root, style="Barra.TFrame", padding=(22, 14))
        cabecalho.pack(fill="x")
        ttk.Label(cabecalho, text="MAPA", style="Titulo.TLabel").pack(side="left")
        ttk.Label(cabecalho, text="   Mapeamento de Plano de Contas",
                  style="Subtitulo.TLabel").pack(side="left", padx=(4, 0))
        # A versão à direita do cabeçalho, sempre visível. É a primeira coisa
        # a perguntar quando "ontem saiu certo e hoje não" — e antes dela não
        # havia como responder sem abrir a planilha.
        ttk.Label(cabecalho, text=versao.VERSAO,
                  style="Subtitulo.TLabel").pack(side="right")

        self.container = ttk.Frame(self.root, padding=0)
        self.container.pack(fill="both", expand=True)

        self.telas: dict[str, ttk.Frame] = {}
        for nome, construtor in (
            ("entrada", self._construir_entrada),
            ("processando", self._construir_processando),
            ("resultado", self._construir_resultado),
        ):
            quadro = ttk.Frame(self.container, padding=(24, 20))
            quadro.place(relx=0, rely=0, relwidth=1, relheight=1)
            self.telas[nome] = quadro
            construtor(quadro)

    def _mostrar(self, nome: str) -> None:
        self.telas[nome].tkraise()

    # -- tela 1: escolher ---------------------------------------------------

    def _construir_entrada(self, pai: ttk.Frame) -> None:
        self.zona = tk.Canvas(pai, height=132, bg=FUNDO, highlightthickness=0,
                              cursor="hand2")
        self.zona.pack(fill="x")
        self.zona.bind("<Configure>", lambda _e: self._desenhar_zona())
        self.zona.bind("<Button-1>", lambda _e: self._escolher_arquivos())

        aceitou = dnd.registrar_alvo(self.zona, self.backend_dnd, self._receber_drop)
        self.dnd_ativo = aceitou
        if aceitou:
            # A janela inteira também aceita: soltar dois centímetros fora da
            # zona tracejada é o erro mais comum de quem usa pela primeira vez.
            dnd.registrar_alvo(self.root, self.backend_dnd, self._receber_drop)

        lista_cartao = ttk.Frame(pai, style="Cartao.TFrame", padding=(2, 2))
        lista_cartao.pack(fill="both", expand=True, pady=(14, 0))
        self.lista = ttk.Frame(lista_cartao, style="Cartao.TFrame", padding=(14, 10))
        self.lista.pack(fill="both", expand=True)

        dados = ttk.Frame(pai)
        dados.pack(fill="x", pady=(16, 0))

        ttk.Label(dados, text="Cliente", style="Secao.TLabel").grid(
            row=0, column=0, sticky="w")
        entrada_cliente = ttk.Entry(dados, textvariable=self.var_cliente,
                                    font=(self.fonte, 11), width=34)
        entrada_cliente.grid(row=1, column=0, sticky="we", pady=(4, 0))
        ttk.Label(dados, text="vai impresso na capa de BP_GT e DRE_GT",
                  style="Fraco.TLabel").grid(row=2, column=0, sticky="w", pady=(3, 0))

        ttk.Label(dados, text="Valores no balancete", style="Secao.TLabel").grid(
            row=0, column=1, sticky="w", padx=(28, 0))
        ttk.Radiobutton(dados, text="Em reais (o BP converte para milhares)",
                        variable=self.var_milhares, value=False).grid(
            row=1, column=1, sticky="w", padx=(28, 0), pady=(4, 0))
        ttk.Radiobutton(dados, text="Já estão em milhares",
                        variable=self.var_milhares, value=True).grid(
            row=2, column=1, sticky="w", padx=(28, 0))
        dados.columnconfigure(0, weight=1)
        dados.columnconfigure(1, weight=1)

        destino = ttk.Frame(pai)
        destino.pack(fill="x", pady=(16, 0))
        ttk.Label(destino, text="Salvar em", style="Secao.TLabel").pack(anchor="w")
        linha = ttk.Frame(destino)
        linha.pack(fill="x", pady=(4, 0))
        # Botão empacotado PRIMEIRO, à direita: um caminho de rede longo
        # (OneDrive corporativo, share cheio de projeto/cliente) empurrava
        # "Alterar..." para fora da janela. Assim ele fica ancorado e o
        # rótulo trunca pelo meio para caber no que sobrou.
        ttk.Button(linha, text="Alterar...", style="Secundaria.TButton",
                   command=self._escolher_pasta).pack(side="right", padx=(8, 0))
        self.rotulo_saida = ttk.Label(linha, text="", style="Fraco.TLabel",
                                      anchor="w")
        self.rotulo_saida.pack(side="left", fill="x", expand=True)
        self.rotulo_saida.bind("<Configure>", lambda _e: self._redesenhar_saida())
        self.var_saida.trace_add("write", lambda *_a: self._redesenhar_saida())
        self._redesenhar_saida()

        rodape = ttk.Frame(pai)
        rodape.pack(fill="x", side="bottom", pady=(18, 0))
        self.recado = ttk.Label(rodape, textvariable=self.var_recado,
                                style="Erro.TLabel", wraplength=470, justify="left")
        self.recado.pack(side="left", fill="x", expand=True)
        self.botao_gerar = ttk.Button(rodape, text="Gerar planilha GT",
                                      style="Acao.TButton", command=self._gerar)
        self.botao_gerar.pack(side="right")

    def _desenhar_zona(self, realce: bool = False) -> None:
        """Redesenha a área tracejada de soltar arquivos."""
        c = self.zona
        c.delete("all")
        largura = c.winfo_width() or 800
        altura = int(c["height"])
        cor_borda = TEAL if realce else "#B9B3AC"
        c.configure(bg="#EAF7F8" if realce else FUNDO)
        c.create_rectangle(2, 2, largura - 3, altura - 3, outline=cor_borda,
                           dash=(6, 4), width=2)

        if self.dnd_ativo:
            titulo = "Arraste os balancetes para cá"
            apoio = "ou clique para procurar no computador"
        else:
            titulo = "Clique para escolher os balancetes"
            # Dizer que arrastar está DESLIGADO, e não só oferecer o clique.
            # Sem isto, quem recebeu o .exe da v0.8 arrastou sobre uma zona que
            # dizia "clique", nada aconteceu, e a conclusão possível era "o
            # programa não funciona". A causa era o tkdnd fora do bundle.
            apoio = "arrastar-e-soltar indisponível nesta máquina · até 5 arquivos"

        # Ícone desenhado, não tipográfico: glifo bonito é loteria de fonte, e
        # uma seta que vira caixinha na máquina do colega é pior que nenhuma.
        self._icone_soltar(largura / 2, altura / 2 - 26, cor_borda)
        c.create_text(largura / 2, altura / 2 + 6, text=titulo, fill=TEXTO,
                      font=(self.fonte, 13, "bold"))
        c.create_text(largura / 2, altura / 2 + 28, text=apoio, fill=TEXTO_FRACO,
                      font=(self.fonte, 9))
        rodape = "xlsx  ·  xls  ·  csv  ·  txt  ·  pdf"
        if not self.dnd_ativo and dnd.diagnostico():
            # O motivo técnico, curto, para quem for reportar o problema.
            rodape = dnd.diagnostico()[:110]
        c.create_text(largura / 2, altura - 18, text=rodape,
                      fill=TEXTO_FRACO, font=(self.fonte, 8))

    def _icone_soltar(self, cx: float, cy: float, cor: str) -> None:
        """Folha com uma seta para baixo, em linhas — independe de fonte."""
        c = self.zona
        c.create_rectangle(cx - 13, cy - 15, cx + 13, cy + 13, outline=ROXO, width=2)
        c.create_line(cx, cy - 8, cx, cy + 6, fill=ROXO, width=2)
        c.create_line(cx - 6, cy, cx, cy + 6, fill=ROXO, width=2)
        c.create_line(cx + 6, cy, cx, cy + 6, fill=ROXO, width=2)

    def _atualizar_lista(self) -> None:
        for filho in self.lista.winfo_children():
            filho.destroy()

        if not self.entradas:
            ttk.Label(self.lista,
                      text="Nenhum balancete escolhido ainda.",
                      style="CartaoFraco.TLabel").pack(anchor="w", pady=18, padx=6)
            self._avaliar()
            return

        topo = ttk.Frame(self.lista, style="Cartao.TFrame")
        topo.pack(fill="x", pady=(0, 6))
        ttk.Label(topo, text=f"{len(self.entradas)} arquivo(s)",
                  style="Cartao.TLabel", font=(self.fonte, 10, "bold")).pack(side="left")
        ttk.Label(topo, text="Exercício", style="CartaoFraco.TLabel").pack(
            side="right", padx=(0, 56))

        for indice, item in enumerate(self.entradas):
            linha = ttk.Frame(self.lista, style="Cartao.TFrame")
            linha.pack(fill="x", pady=2)

            ttk.Label(linha, text=_encurtar(item.nome), style="Cartao.TLabel").pack(
                side="left")
            # O botão de remover usa o sinal de multiplicação, que é o glifo
            # de fechar; a letra "x" fica torta ao lado do texto. O ruff avisa
            # da ambiguidade entre os dois — aqui ela é intencional.
            ttk.Button(linha, text="×", style="Linha.TButton", width=3,  # noqa: RUF001
                       command=functools.partial(self._remover, indice)).pack(side="right")

            var = tk.StringVar(value=str(item.ano) if item.ano else "")
            caixa = ttk.Spinbox(linha, from_=service.ANO_MIN, to=service.ano_maximo(),
                                width=6, textvariable=var, justify="center",
                                font=(self.fonte, 10))
            caixa.pack(side="right", padx=(10, 12))
            var.trace_add("write", lambda *_a, i=indice, v=var: self._mudar_ano(i, v))
            if not item.ano:
                caixa.configure(foreground=ERRO)

        self._avaliar()

    def _mudar_ano(self, indice: int, var: tk.StringVar) -> None:
        bruto = var.get().strip()
        self.entradas[indice].ano = int(bruto) if bruto.isdigit() else None
        self._avaliar()

    def _remover(self, indice: int) -> None:
        del self.entradas[indice]
        self._atualizar_lista()

    def _avaliar(self) -> None:
        """Liga/desliga o botão principal e explica o que falta."""
        problemas = service.validar(self.entradas, self.var_cliente.get())
        if not self.entradas:
            self.var_recado.set("")
        else:
            self.var_recado.set(problemas[0] if problemas else "")
        estado = "disabled" if problemas else "normal"
        if hasattr(self, "botao_gerar"):
            self.botao_gerar.configure(state=estado)

    # -- entrada de arquivos ------------------------------------------------

    def _escolher_arquivos(self) -> None:
        escolhidos = filedialog.askopenfilenames(
            parent=self.root,
            title="Escolha os balancetes",
            filetypes=[
                ("Balancetes", "*.xlsx *.xls *.csv *.txt *.pdf"),
                ("Excel", "*.xlsx *.xls"),
                ("PDF", "*.pdf"),
                ("Texto", "*.csv *.txt"),
                ("Todos os arquivos", "*.*"),
            ],
        )
        if escolhidos:
            self._adicionar([Path(p) for p in escolhidos])

    def _receber_drop(self, caminhos: list[Path]) -> None:
        """
        Devolve **imediatamente** e faz o trabalho no próximo ciclo do Tk.

        Não é otimização, é correção. O ``<<Drop>>`` roda dentro da operação
        OLE do Windows: enquanto o callback não retorna, o Explorer — a origem
        do arrasto — fica bloqueado esperando. E o que este handler chamava
        direto era ``_adicionar``, que lê o arquivo inteiro para diagnosticar
        as abas e pode abrir um ``Toplevel`` com ``grab_set()``. Modal dentro
        do drop, com a origem travada, é receita de janela que não aparece e
        arquivo que não entra — sem erro nenhum, porque o build é
        ``console=False``.

        ``after(1, ...)`` encerra o drop primeiro; o resto acontece com a
        janela já livre.
        """
        self._desenhar_zona(realce=False)
        self._anotar(f"drop: {len(caminhos)} item(ns) -> {[str(c) for c in caminhos]}")
        if not caminhos:
            self.var_recado.set(dnd.AVISO_SEM_CAMINHO)
            return
        self.var_recado.set(f"Lendo {len(caminhos)} arquivo(s)...")
        self.root.after(1, lambda: self._adicionar(caminhos))

    def _adicionar(self, caminhos: list[Path]) -> None:
        aceitos, recusados = service.selecionar(caminhos)
        self._anotar(
            f"selecionar: {len(aceitos)} aceito(s), {len(recusados)} recusado(s)"
        )
        ja_tem = {(e.path, e.aba) for e in self.entradas}

        novos: list[service.Entrada] = []
        for aceito in aceitos:
            # Pasta de trabalho traz vários exercícios em abas — ou já vem
            # consolidada pela empresa, com o balanço numa aba qualquer.
            # Escolher por conta própria seria palpite: quem decide é o analista.
            try:
                diagnostico = service.diagnosticar_arquivo(aceito.path)
            except Exception as exc:
                # Inspecionar abas é conveniência: falhar aqui não pode custar
                # o arquivo. Sem o diagnóstico, segue como planilha de aba
                # única — que é o caso da esmagadora maioria dos balancetes.
                self.var_recado.set(
                    f"Não consegui inspecionar as abas de {aceito.path.name} "
                    f"({type(exc).__name__}); seguindo com a primeira."
                )
                diagnostico = None
            if diagnostico is not None and diagnostico.abas:
                escolhidas = self._perguntar_abas(aceito.path, diagnostico)
            else:
                escolhidas = [None]
            for aba in escolhidas:
                candidata = service.Entrada(aceito.path, aba=aba)
                if (candidata.path, candidata.aba) not in ja_tem:
                    ja_tem.add((candidata.path, candidata.aba))
                    novos.append(candidata)
        self.entradas.extend(novos)
        self._anotar(f"adicionadas {len(novos)} entrada(s); total {len(self.entradas)}")

        if not self.var_cliente.get().strip():
            palpite = service.cliente_do_nome([e.path for e in self.entradas])
            if palpite:
                self.var_cliente.set(palpite)

        self._atualizar_lista()
        if recusados:
            nomes = ", ".join(p.name for p in recusados[:3])
            self.var_recado.set(
                f"Não sei ler {nomes} — aceito xlsx, xls, csv, txt e pdf."
            )
        elif not novos and aceitos:
            self.var_recado.set("Esse arquivo já está na lista.")

#--------- Estrutura de validação de abas------------------------
    def _perguntar_abas(self, caminho: Path, diagnostico) -> list[str | None]:
        """
        Tabela de marcação das abas, com o teto de exercícios do template.

        A mesma tela responde a duas perguntas diferentes, e o diagnóstico
        decide qual:

        - **balancete com vários exercícios** → "quais exercícios usar?";
        - **arquivo já consolidado pela empresa** → "em qual aba está o
          balanço?", com o motivo dito na cara, e listando **todas** as abas.

        Devolve os nomes marcados. Fechar sem marcar nada devolve lista vazia —
        o arquivo simplesmente não entra, que é o desfecho certo para quem
        desistiu.

        As abas vêm com a contagem de contas **medida** (não estimada), porque
        é ela que distingue um balancete de verdade de uma aba de resumo com o
        nome parecido.
        """
        abas = diagnostico.abas
        perguntando_onde = diagnostico.precisa_perguntar
        janela = tk.Toplevel(self.root)
        janela.title(f"Exercícios de {caminho.name}")
        janela.configure(bg=FUNDO)
        janela.transient(self.root)
        janela.grab_set()

        moldura = ttk.Frame(janela, style="Cartao.TFrame", padding=18)
        moldura.pack(fill="both", expand=True)

        titulo = (
            f"{caminho.name} não parece um balancete puro."
            if perguntando_onde
            else f"{caminho.name} traz {len(abas)} balancetes."
        )
        ttk.Label(moldura, text=titulo, style="Cartao.TLabel",
                  font=(self.fonte, 11, "bold")).pack(anchor="w")

        if perguntando_onde:
            ttk.Label(
                moldura, text=diagnostico.motivo, style="CartaoFraco.TLabel",
                wraplength=520, justify="left",
            ).pack(anchor="w", pady=(2, 6))
            recado = (
                f"Em qual aba está o balanço? Marque até "
                f"{service.MAX_EXERCICIOS} — o template é preenchido do mesmo "
                "jeito, mas os totais não poderão ser conferidos contra a origem."
            )
        else:
            recado = (
                f"Marque até {service.MAX_EXERCICIOS} exercícios — é o que o "
                "template comporta."
            )
        ttk.Label(moldura, text=recado, style="CartaoFraco.TLabel",
                  wraplength=520, justify="left").pack(anchor="w", pady=(0, 12))

        vars_por_aba: dict[str, tk.BooleanVar] = {}
        var_recado = tk.StringVar(value="")

        def marcadas() -> list[str]:
            return [nome for nome, var in vars_por_aba.items() if var.get()]

        def ao_marcar() -> None:
            escolhidas = marcadas()
            excesso = len(escolhidas) - service.MAX_EXERCICIOS
            if excesso > 0:
                var_recado.set(
                    f"{len(escolhidas)} marcados. Desmarque {excesso} — o "
                    f"template comporta {service.MAX_EXERCICIOS}."
                )
            else:
                var_recado.set("")
            botao.configure(
                state="normal" if escolhidas and excesso <= 0 else "disabled"
            )

        cabecalho = ttk.Frame(moldura, style="Cartao.TFrame")
        cabecalho.pack(fill="x")
        ttk.Label(cabecalho, text="Aba", style="CartaoFraco.TLabel",
                  width=34).pack(side="left")
        ttk.Label(cabecalho, text="Contas", style="CartaoFraco.TLabel",
                  width=9, anchor="e").pack(side="left")
        ttk.Label(cabecalho, text="Período", style="CartaoFraco.TLabel",
                  width=10, anchor="e").pack(side="left")
        ttk.Label(cabecalho, text="Tipo", style="CartaoFraco.TLabel",
                  width=15, anchor="e").pack(side="left")

        if perguntando_onde:
            # Nada é sugerido: se o programa soubesse qual aba tem o balanço,
            # não estaria perguntando. Marcar por conta própria aqui seria dar
            # um palpite com cara de resposta.
            sugeridas: set[str] = set()
        else:
            # Marca os mais recentes, até o teto: é o que o analista quer na
            # esmagadora maioria das vezes, e ele pode mudar.
            recentes = sorted(
                abas, key=lambda a: (a.ano or 0, a.mes or 0), reverse=True
            )[: service.MAX_EXERCICIOS]
            sugeridas = {a.nome for a in recentes if a.ano}

        for aba in abas:
            linha = ttk.Frame(moldura, style="Cartao.TFrame")
            linha.pack(fill="x", pady=1)
            var = tk.BooleanVar(value=aba.nome in sugeridas)
            vars_por_aba[aba.nome] = var
            ttk.Checkbutton(
                linha, text=_encurtar(aba.nome, 32), variable=var,
                style="Cartao.TCheckbutton", command=ao_marcar, width=32,
            ).pack(side="left")
            ttk.Label(linha, text=str(aba.contas), style="Cartao.TLabel",
                      width=9, anchor="e").pack(side="left")
            ttk.Label(linha, text=aba.periodo, style="Cartao.TLabel",
                      width=10, anchor="e").pack(side="left")
            ttk.Label(linha, text=aba.rotulo_do_tipo, style="CartaoFraco.TLabel",
                      width=15, anchor="e").pack(side="left")

        ttk.Label(moldura, textvariable=var_recado, style="CartaoFraco.TLabel",
                  foreground=ERRO).pack(anchor="w", pady=(10, 0))

        rodape = ttk.Frame(moldura, style="Cartao.TFrame")
        rodape.pack(fill="x", pady=(14, 0))
        resultado: list[str] = []

        def confirmar() -> None:
            resultado.extend(marcadas())
            janela.destroy()

        botao = ttk.Button(
            rodape,
            text="Usar esta aba" if perguntando_onde else "Usar os marcados",
            style="Acao.TButton", command=confirmar,
        )
        botao.pack(side="right")
        ttk.Button(rodape, text="Cancelar", style="Linha.TButton",
                   command=janela.destroy).pack(side="right", padx=(0, 8))

        ao_marcar()
        janela.update_idletasks()
        janela.geometry(
            f"+{self.root.winfo_rootx() + 60}+{self.root.winfo_rooty() + 50}"
        )
        self.root.wait_window(janela)
        return list(resultado)
#=======Manutenção da funcionalidade de saída==================
    def _redesenhar_saida(self) -> None:
        """Escreve o caminho de saída, truncando pelo meio se não couber."""
        widget = getattr(self, "rotulo_saida", None)
        if widget is None:
            return
        texto_bruto = self.var_saida.get()
        largura = max(widget.winfo_width() - 8, 40)
        fonte = tkfont.nametofont(str(widget.cget("font")) or "TkDefaultFont")
        if fonte.measure(texto_bruto) <= largura:
            widget.configure(text=texto_bruto)
            return
        elipse = "\u2026"
        largura_alvo = largura - fonte.measure(elipse)
        meio = len(texto_bruto) // 2
        esquerda, direita = meio, meio
        while esquerda > 0 and direita < len(texto_bruto):
            candidato = texto_bruto[:esquerda] + elipse + texto_bruto[direita:]
            if fonte.measure(candidato) <= largura:
                widget.configure(text=candidato)
                return
            esquerda -= 1
            direita += 1
        widget.configure(text=elipse + texto_bruto[-max(1, largura_alvo // 8):])

    def _escolher_pasta(self) -> None:
        escolhida = filedialog.askdirectory(
            parent=self.root, title="Onde salvar as planilhas",
            initialdir=str(self.pasta_saida),
        )
        if escolhida:
            self.pasta_saida = Path(escolhida)
            self.var_saida.set(escolhida)
            self._salvar_preferencias()

    # -- tela 2: processando ------------------------------------------------

    def _construir_processando(self, pai: ttk.Frame) -> None:
        centro = ttk.Frame(pai)
        centro.place(relx=0.5, rely=0.42, anchor="center")

        ttk.Label(centro, text="Gerando a planilha", style="Secao.TLabel",
                  font=(self.fonte, 16, "bold")).pack()
        ttk.Label(centro, textvariable=self.var_alvo, style="TLabel").pack(pady=(8, 2))
        ttk.Label(centro, textvariable=self.var_passo, style="Fraco.TLabel").pack(
            pady=(2, 18))
        self.barra = ttk.Progressbar(centro, mode="indeterminate", length=380,
                                     style="Andamento.Horizontal.TProgressbar")
        self.barra.pack()
        ttk.Label(centro,
                  text="Costuma levar de 10 segundos a 1 minuto, conforme o tamanho\n"
                       "do balancete. Pode deixar a janela aberta.",
                  style="Fraco.TLabel", justify="center").pack(pady=(18, 0))

    # -- tela 3: resultado --------------------------------------------------

    def _construir_resultado(self, pai: ttk.Frame) -> None:
        self.res_topo = ttk.Frame(pai)
        self.res_topo.pack(fill="x")
        # O rodapé é empacotado ANTES do corpo de propósito. `pack` atende na
        # ordem das chamadas: se o corpo (expand=True) vier primeiro, ele
        # reivindica todo o espaço restante e os botões — que são a ação — são
        # empurrados para fora da janela quando a lista de avisos cresce.
        # Reservando o rodapé primeiro, ele nunca some; quem cede é o corpo.
        self.res_rodape = ttk.Frame(pai)
        self.res_rodape.pack(fill="x", side="bottom", pady=(16, 0))
        self.res_corpo = ttk.Frame(pai)
        self.res_corpo.pack(fill="both", expand=True, pady=(14, 0))

    def _pintar_resultado(self, r: service.Resultado) -> None:
        for area in (self.res_topo, self.res_corpo, self.res_rodape):
            for filho in area.winfo_children():
                filho.destroy()

        if not r.ok:
            ttk.Label(self.res_topo, text="Não deu para gerar",
                      style="Secao.TLabel", font=(self.fonte, 17, "bold"),
                      foreground=ERRO).pack(anchor="w")
            ttk.Label(self.res_corpo, text=r.erro or "Erro desconhecido.",
                      style="TLabel", wraplength=700, justify="left").pack(anchor="w")
            ttk.Label(self.res_corpo,
                      text=f"Detalhes técnicos ficam em {paths.log_path()}",
                      style="Fraco.TLabel").pack(anchor="w", pady=(14, 0))
            ttk.Button(self.res_rodape, text="Voltar", style="Acao.TButton",
                       command=lambda: self._mostrar("entrada")).pack(side="right")
            return

        titulo = ("Planilha gerada" if not r.precisa_atencao
                  else "Gerada — confira os avisos antes de entregar")
        cor = SUCESSO if not r.precisa_atencao else ATENCAO
        marca = "OK" if not r.precisa_atencao else "!"
        ttk.Label(self.res_topo, text=f"{marca}  {titulo}", style="Secao.TLabel",
                  font=(self.fonte, 17, "bold"), foreground=cor).pack(anchor="w")
        saida = r.saida
        assert saida is not None  # ok=True sempre traz o caminho gerado
        ttk.Label(self.res_topo, text=saida.name, style="TLabel",
                  font=(self.fonte, 11)).pack(anchor="w", pady=(6, 0))
        ttk.Label(self.res_topo, text=str(saida.parent),
                  style="Fraco.TLabel").pack(anchor="w")

        cartoes = ttk.Frame(self.res_corpo, style="Cartao.TFrame", padding=(16, 14))
        cartoes.pack(fill="x")
        metricas = (
            ("Contas lidas", f"{r.contas_lidas}", TEXTO),
            ("Identificadas", f"{r.contas_tratadas}", SUCESSO),
            ("Para revisar", f"{r.contas_nao_identificadas}",
             ATENCAO if r.contas_nao_identificadas else TEXTO_FRACO),
            ("Aproveitamento", f"{r.match_rate:.0%}", TEXTO),
            ("Balanço fecha", "sim" if r.balanco_confere else "NÃO",
             SUCESSO if r.balanco_confere else ERRO),
        )
        for coluna, (rotulo, valor, cor_valor) in enumerate(metricas):
            celula = ttk.Frame(cartoes, style="Cartao.TFrame")
            celula.grid(row=0, column=coluna, sticky="w", padx=(0, 34))
            ttk.Label(celula, text=valor, style="Cartao.TLabel",
                      font=(self.fonte, 18, "bold"), foreground=cor_valor).pack(anchor="w")
            ttk.Label(celula, text=rotulo, style="CartaoFraco.TLabel").pack(anchor="w")

        if r.alertas:
            self._caixa_de_avisos(self.res_corpo, r.alertas)

        if r.pendentes:
            ttk.Label(
                self.res_corpo,
                text=f"Contas que o BP não soube classificar ({r.contas_nao_identificadas})",
                style="Secao.TLabel",
            ).pack(anchor="w", pady=(16, 6))
            recado = ('Estão todas na aba "Contas Não Identificadas" da planilha, '
                      "com o valor, para você classificar à mão.")
            if len(r.pendentes) < r.contas_nao_identificadas:
                recado = (f"Mostrando as {len(r.pendentes)} primeiras. " + recado)
            ttk.Label(self.res_corpo, text=recado,
                      style="Fraco.TLabel").pack(anchor="w", pady=(0, 6))
            self._tabela_pendentes(self.res_corpo, r.pendentes)

        ttk.Button(self.res_rodape, text="Abrir planilha", style="Acao.TButton",
                   command=functools.partial(service.abrir_no_sistema, saida)).pack(
            side="right")
        ttk.Button(self.res_rodape, text="Abrir pasta", style="Secundaria.TButton",
                   command=functools.partial(service.abrir_no_sistema, saida.parent)).pack(
            side="right", padx=(0, 10))
        ttk.Button(self.res_rodape, text="Padronizar outro",
                   style="Secundaria.TButton", command=self._recomecar).pack(side="left")

    #: Altura máxima da caixa de avisos, em linhas de texto. Acima disso ela
    #: rola em vez de crescer. Seis linhas cabem os avisos típicos inteiros;
    #: o caso do Trindade (5 avisos longos, ~14 linhas) rola.
    LINHAS_DE_AVISO = 6

    def _caixa_de_avisos(self, pai: ttk.Frame, alertas: list[str]) -> None:
        """
        Os avisos, em altura fixa e roláveis.

        Antes eram `Label`s empilhados num `Frame`: a caixa crescia sem limite
        e empurrava a tabela e os botões para fora da janela — justamente
        quando havia MAIS a avisar, que é quando o analista mais precisa da
        ação. Um `Text` resolve os dois de uma vez: teto de altura com rolagem
        nativa, e o texto fica selecionável para copiar num e-mail.
        """
        quadro = tk.Frame(pai, bg=ATENCAO_FUNDO,
                          highlightbackground="#E8C98A", highlightthickness=1)
        quadro.pack(fill="x", pady=(12, 0))

        texto = tk.Text(
            quadro, bg=ATENCAO_FUNDO, fg=ATENCAO, font=(self.fonte, 9),
            wrap="word", relief="flat", highlightthickness=0,
            padx=12, pady=8, height=min(self.LINHAS_DE_AVISO, len(alertas) * 2),
            cursor="arrow",
        )
        rolagem = ttk.Scrollbar(quadro, orient="vertical", command=texto.yview)
        texto.configure(yscrollcommand=rolagem.set)

        for i, alerta in enumerate(alertas):
            texto.insert("end", ("\n" if i else "") + "-  " + alerta + "\n")

        # `state="disabled"` só DEPOIS de inserir: um Text desabilitado recusa
        # escrita. Desabilitado ele continua rolável e selecionável, e deixa de
        # ser editável — que é o que se quer de um aviso.
        texto.configure(state="disabled")

        texto.pack(side="left", fill="both", expand=True)
        # A barra só aparece quando há o que rolar; senão fica um traço morto
        # ao lado de um aviso de duas linhas.
        texto.update_idletasks()
        if texto.yview() != (0.0, 1.0):
            rolagem.pack(side="right", fill="y")

    def _tabela_pendentes(
        self, pai: ttk.Frame, pendentes: list[service.ContaPendente]
    ) -> None:
        quadro = ttk.Frame(pai, style="Cartao.TFrame")
        quadro.pack(fill="both", expand=True)
        colunas = ("descricao", "ano", "valor")
        tabela = ttk.Treeview(quadro, columns=colunas, show="headings", height=6)
        tabela.heading("descricao", text="Descrição no balancete")
        tabela.heading("ano", text="Exercício")
        tabela.heading("valor", text="Valor")
        tabela.column("descricao", width=460, anchor="w")
        tabela.column("ano", width=80, anchor="center")
        tabela.column("valor", width=130, anchor="e")
        for conta in pendentes:
            tabela.insert("", "end", values=(conta.descricao or conta.codigo,
                                             conta.ano or "—", _moeda(conta.valor)))
        rolagem = ttk.Scrollbar(quadro, orient="vertical", command=tabela.yview)
        tabela.configure(yscrollcommand=rolagem.set)
        tabela.pack(side="left", fill="both", expand=True)
        rolagem.pack(side="right", fill="y")

    def _recomecar(self) -> None:
        self.entradas.clear()
        self.var_cliente.set("")
        self.var_recado.set("")
        self._atualizar_lista()
        self._mostrar("entrada")

    # -- execução -----------------------------------------------------------

    def _gerar(self) -> None:
        problemas = service.validar(self.entradas, self.var_cliente.get())
        if problemas:
            self.var_recado.set(problemas[0])
            return

        self._salvar_preferencias()
        anos = ", ".join(str(e.ano) for e in sorted(self.entradas, key=lambda x: x.ano or 0))
        self.var_alvo.set(f"{self.var_cliente.get().strip()} — {anos}")
        self.var_passo.set("Lendo os balancetes...")
        self._mostrar("processando")
        self.barra.start(14)

        entradas = list(self.entradas)
        cliente = self.var_cliente.get()
        milhares = self.var_milhares.get()
        pasta = self.pasta_saida

        def trabalhar() -> None:
            resultado = service.gerar(
                entradas, pasta, cliente, em_milhares=milhares,
                progresso=lambda t: self.fila.put(("passo", t)),
            )
            self.fila.put(("fim", resultado))

        threading.Thread(target=trabalhar, daemon=True).start()
        self.root.after(80, self._ler_fila)

    def _ler_fila(self) -> None:
        try:
            while True:
                tipo, carga = self.fila.get_nowait()
                if tipo == "passo":
                    self.var_passo.set(carga)
                elif tipo == "fim":
                    self.barra.stop()
                    self.resultado = carga
                    self._pintar_resultado(carga)
                    self._mostrar("resultado")
                    return
        except queue.Empty:
            pass
        self.root.after(80, self._ler_fila)

    # -- preferências -------------------------------------------------------

    def _erro_em_callback(self, tipo, valor, tb) -> None:
        """
        Erro dentro de um callback do Tk vira mensagem — não silêncio.

        O padrão do Tkinter escreve o traceback em ``sys.stderr``. Num
        executável ``console=False`` **não existe** ``sys.stderr``: a impressão
        falha, o Tcl engole, e o programa segue como se nada tivesse
        acontecido. Foi assim que um erro no caminho do arrastar-e-soltar
        virou "o programa não traz o arquivo".

        Aqui o erro aparece na barra de recado, vai para um arquivo de log ao
        lado do executável, e — por ser coisa que o usuário precisa ver — abre
        uma caixa de diálogo.
        """
        import traceback

        texto = "".join(traceback.format_exception(tipo, valor, tb))
        resumo = f"{tipo.__name__}: {valor}"

        with contextlib.suppress(Exception):
            self.var_recado.set(f"Erro: {resumo}")

        destino = None
        with contextlib.suppress(Exception):
            destino = self._arquivo_de_log()
            with destino.open("a", encoding="utf-8") as saida:
                saida.write(f"\n--- {datetime.now():%Y-%m-%d %H:%M:%S} ---\n")
                saida.write(texto)

        with contextlib.suppress(Exception):
            from tkinter import messagebox

            messagebox.showerror(
                "MAPA — erro",
                f"{resumo}\n\n"
                + (f"Detalhes em:\n{destino}" if destino else "")
                + "\n\nO programa continua aberto; se o erro se repetir, "
                "mande o arquivo de log.",
            )

    def _anotar(self, mensagem: str) -> None:
        """
        Uma linha no log, para o caminho que a gente não consegue ver rodar.

        O arrastar-e-soltar é o único ponto do programa que depende do sistema
        operacional e que nenhum teste alcança de verdade. Quando ele falha na
        máquina de outra pessoa, não há terminal, não há traceback e a única
        informação disponível é "não funciona". Estas linhas custam microssegundos
        e transformam a próxima rodada de diagnóstico em leitura de arquivo.
        """
        with (
            contextlib.suppress(Exception),
            self._arquivo_de_log().open("a", encoding="utf-8") as saida,
        ):
            saida.write(f"{datetime.now():%H:%M:%S} {mensagem}\n")

    @staticmethod
    def _arquivo_de_log() -> Path:
        """Ao lado do executável quando empacotado; no diretório atual se fonte."""
        if getattr(sys, "frozen", False):
            return Path(sys.executable).resolve().parent / "MAPA_erros.log"
        return Path.cwd() / "MAPA_erros.log"

    def _pasta_saida_inicial(self) -> Path:
        from ..utils.json_store import load_json

        try:
            config: dict[str, str] = load_json(paths.settings_path(), {})
            guardada = config.get("pasta_saida")
            if guardada and Path(guardada).is_dir():
                return Path(guardada)
        except Exception:
            pass
        return paths.default_output_dir()

    def _salvar_preferencias(self) -> None:
        from ..utils.json_store import save_json

        try:
            paths.ensure_dir(paths.user_data_dir())
            save_json(paths.settings_path(), {"pasta_saida": str(self.pasta_saida)})
        except Exception:
            pass  # preferência é conforto, não requisito

    # -- ciclo de vida ------------------------------------------------------

    def rodar(self) -> int:
        self.root.mainloop()
        return 0


def main() -> int:
    """Abre a janela do BP."""
    return AplicacaoBP().rodar()


if __name__ == "__main__":
    raise SystemExit(main())
