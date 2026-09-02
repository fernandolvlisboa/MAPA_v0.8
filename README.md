<div align="center">

# 📊 MAPA

### Mapeamento de Plano de Contas

**Balancete do cliente → Template GT preenchido, em menos de um minuto.**

[![Testes](https://img.shields.io/badge/testes-346%20passando-success)]()
[![Python](https://img.shields.io/badge/python-3.13+-blue)]()
[![Licença](https://img.shields.io/badge/uso-interno-lightgrey)]()

</div>

---

## 🚀 Comece por aqui

**Você só quer entregar a planilha:** baixe `MAPA.exe` da [última Release](../../releases/latest), salve no Desktop, duplo-clique. Arrasta o balancete, confere cliente e ano, clica em *Gerar*. É isso.

**Você é o analista do MAPA:** clona, `uv sync`, `uv run python main.py`. A mesma janela. Quer treinar, revisar pendências ou compilar um `.exe` novo? Passe `--menu`.

```bash
uv sync
uv run python main.py             # abre a janela do usuário final
uv run python main.py --menu      # bancada do analista (treinar, revisar)
uv run python build.py            # compila, audita e autotesta o MAPA.exe (Windows)
git tag v0.8.1 && git push origin v0.8.1   # publica a Release, sozinho
```

> **Sobre o nome:** o produto se chama **MAPA**. O pacote Python interno se chama `bp` por herança do desenvolvimento inicial — pense em MAPA como o produto e `bp` como o módulo. Não vale a pena quebrar imports só pelo nome.

---

## 🎯 O problema que resolve

Um contador que atende várias empresas recebe balancetes com:

- códigos de conta diferentes em cada empresa (`1.1.01` numa, `1.1.1.4.2` noutra);
- descrições diferentes para a mesma conta (`BENS NUMERÁRIOS`, `CAIXA GERAL`, `DISPONIBILIDADES` — todas são "Caixa");
- formatos diferentes (Excel, PDF nativo/escaneado, CSV, TXT).

Hoje esse trabalho de "de-para" é **manual, conta a conta**. Quatro a doze horas por balancete. Sujeito a erro invisível — o que passa em silêncio é o mais caro.

O MAPA faz isso em **10 a 60 segundos** por arquivo:

```
Balancete de origem  ─►  Parser  ─►  Matching  ─►  Plano Referencial  ─►  Template GT
(xlsx/xls/csv/           (extrai)     (fuzzy +      (código único e         (entrega ao
 txt/pdf)                              sinônimos +   padronizado —            cliente,
                                       aprendizado)  RFB L100A + L300A)       com fórmulas)
```

E **aprende com o uso**: cada balancete revisado alimenta um dicionário de variações que melhora o próximo matching.

---

## 🖥️ Dois públicos, dois canais

| Você é... | Como usa | Ponto de entrada |
|---|---|---|
| **Colaborador** — só quer entregar a planilha | Duplo-clique no `.exe`, janela | `MAPA.exe` |
| **Analista** — cuida do MAPA | Menu de terminal + fluxo de treino | `uv run python main.py --menu` |

A **janela** tem uma tela, três estados: escolher os balancetes, processando, resultado. A tela de resultado responde a única pergunta que importa: *posso mandar isto para o cliente?* Contas lidas, identificadas, pendentes, aproveitamento e **se o balanço fecha**. Verde só quando não há aviso nenhum. Ver [`PLANO_J_INTERFACE.md`](PLANO_J_INTERFACE.md).

---

## 🧩 A arquitetura por trás — três engrenagens reusáveis

O MAPA é um caso de uso. As três engrenagens internas foram desenhadas **desacopladas** e podem ser reaproveitadas em outras automações (Accounting Advisory, Capital Markets, Due Diligence) com esforço incremental baixo. Cada uma tem seu próprio guia:

| Engrenagem | O que faz | Reuso natural | Guia |
|---|---|---|---|
| 🧾 **Parsers** | Leem xlsx, xls, csv, txt, pdf e devolvem uma lista uniforme de `{codigo, descricao, saldo}` | Qualquer automação que precise ler documentos financeiros do cliente | [`src/bp/parsers/README.md`](src/bp/parsers/README.md) |
| 🎯 **Matchers** | Associam cada linha de origem a um código do plano-alvo, com fuzzy + sinônimos + IA opcional | Qualquer padronização de dados que venham em formatos diferentes contra uma referência | [`src/bp/matchers/README.md`](src/bp/matchers/README.md) |
| 🧠 **Learners** | Aprendem com as classificações do analista e melhoram com o uso | Toda tarefa repetitiva de categorização que evolua no tempo | [`src/bp/training/README.md`](src/bp/training/README.md) |

Para o desenho geral do sistema, ver [`ARQUITETURA.md`](ARQUITETURA.md).

---

## ⚙️ Requisitos

- **Python 3.13+** (o `uv` cuida da versão)
- **[uv](https://docs.astral.sh/uv/)** — gerenciador de dependências
- Em Linux, `sudo apt install python3-tk` (o `tkinter` do Windows e do macOS já vem com o Python)
- **Opcionais:** Tesseract + poppler para OCR de PDF escaneado; PyInstaller para gerar o `.exe`

---

## 📦 Fluxo do analista, resumido

```bash
uv sync                                              # 0. instalar
uv run python -m src.bp.generators.plano_referencial # 1. gerar o alvo (uma vez)
uv run python src/bp/training/train.py               # 2. treinar (repetível)
uv run python -m src.bp.training.review_wizard --all # 3. revisar pendências
uv run python main.py                                # 4. usar a janela
uv run python build.py                               # 5. gerar MAPA.exe (Windows)
```

O passo a passo detalhado de cada etapa está em [`docs/`](docs/) e nos guias por módulo (parsers/matchers/learners).

---

## 🚨 Distribuindo o `.exe`

O `MAPA.exe` sai em `dist/MAPA.exe`, ~55 MB, **onefile**:

- Roda por duplo-clique. Sem instalador.
- **Não precisa de admin** — descompacta em `%TEMP%` do usuário na 1ª execução.
- Nada é gravado em `Program Files`, nada mexe no registry.
- SmartScreen pode alertar na primeira vez (executável não assinado). *Mais informações → Executar assim mesmo*.
- **Abra com duplo clique normal.** O Windows bloqueia arrastar-e-soltar em janela aberta como administrador (UIPI) — e falha calado.

### O `.exe` não entra no repositório

São 55 MB por build. Commitado, o git guarda **todos** para sempre e o histórico não encolhe depois. `dist/` está no `.gitignore` e é assim que fica.

A distribuição é por **GitHub Release**: até 2 GB por arquivo, fora do histórico, com link estável para circular.

### Publicar uma versão

Duas linhas, e o resto é automático:

```bash
git tag v0.8.1
git push origin v0.8.1
```

O workflow [`.github/workflows/release.yml`](.github/workflows/release.yml) acorda sozinho, sobe uma máquina Windows e faz, nesta ordem:

1. `uv sync --extra packaging`
2. `uv run pytest -q` — a suíte inteira
3. `uv run python build.py` — compila, **audita** e **autotesta** o binário
4. publica a Release com o `MAPA.exe` anexado

Leva **5 a 8 minutos**. Acompanhe na aba **Actions**; quando terminar, o arquivo está em **Releases**, e o link para circular é `https://github.com/<owner>/<repo>/releases/latest`.

**Se qualquer passo falhar, não há Release.** Foi exatamente assim que um binário com o pandas quebrado chegou aos usuários — ver [`REVISAO_QUALIDADE.md`](REVISAO_QUALIDADE.md) §24. Os relatórios do build ficam anexados à execução do Actions mesmo quando ela falha.

**Numeração das tags:** `v<maior>.<menor>.<correção>` — `v0.8.1` para correção, `v0.9.0` quando muda o comportamento. A tag precisa começar com `v`, senão o workflow não dispara.

**Refazer uma versão** (algo saiu errado e você quer reaproveitar o número):

```bash
git tag -d v0.8.1 && git push origin :refs/tags/v0.8.1   # apaga local e remoto
git tag v0.8.1 && git push origin v0.8.1                 # recria
```

Apague também a Release antiga pela interface do GitHub, senão ficam duas.

**Testar o workflow sem criar tag:** aba *Actions* → *Release do MAPA.exe* → *Run workflow*. Ele compila e autotesta, e não publica nada.

### Publicar à mão (sem esperar o CI)

Quando você já compilou na sua máquina e quer subir agora — precisa do [`gh`](https://cli.github.com):

```bash
uv run python build.py
gh release create v0.8.1 dist/MAPA.exe --generate-notes
```

O `build.py` só devolve `.exe` que passou na auditoria e no autoteste, então o que sobe por aqui tem a mesma garantia do CI.

### O que o build confere antes de entregar

| Passo | O que prova | Por que existe |
|---|---|---|
| `pytest -q` | o código faz o que promete | a suíte de sempre |
| auditoria do bundle | nenhum dado de cliente dentro; template, plano e `tkdnd` presentes | §23 — o `.exe` saiu sem a biblioteca do arrastar-e-soltar |
| `MAPA.exe --autoteste` | **o binário roda o pipeline completo** | §24 — o `.exe` saiu com o pandas quebrado |

O autoteste monta um balancete sintético, chama o motor de verdade sobre o template embarcado e confere que a entrega saiu. É a diferença entre auditar o *conteúdo* do artefato e provar que ele *funciona*. Ver [`PLANO_K_EMPACOTAMENTO.md`](PLANO_K_EMPACOTAMENTO.md).

---

## 🐍 API programática

```python
from src.bp.parsers.dispatcher import ParseyCaller
from src.bp.matchers import ContaMatcher
from src.bp.generators.plano_contas import PlanodeContas

# 1. ler o balancete
contas = ParseyCaller("balancete_2024.xlsx").parse()

# 2. montar o matcher
plano = PlanodeContas("data/plano_referencial.json")
matcher = ContaMatcher(plano)

# 3. classificar
for conta in contas:
    r = matcher.match(conta["descricao"])
    if r.decision:
        print(conta["descricao"], "→", r.decision.codigo, f"({r.decision.score:.0%})")
    else:
        print(conta["descricao"], "→ ?? precisa revisão")
```

Detalhes em cada guia — [parsers](src/bp/parsers/README.md), [matchers](src/bp/matchers/README.md), [learners](src/bp/training/README.md).

---

## 🗂️ Estrutura

```
MAPA/
├── main.py                 ← ponto de entrada (janela + --menu)
├── app.py                  ← alvo do PyInstaller
├── build.py                ← compila e audita MAPA.exe
├── bp.spec                 ← allowlist do PyInstaller
├── src/bp/
│   ├── app/                # a janela (Plano J)
│   ├── parsers/            # 🧾 leitores → guia próprio
│   ├── matchers/           # 🎯 classificação → guia próprio
│   ├── training/           # 🧠 aprendizado → guia próprio
│   ├── generators/         # plano de contas (loader + geradores)
│   ├── output/             # build_gt_output → Template GT
│   └── exporters/          # xlsx_exporter (diagnóstico)
├── data/
│   ├── plano_referencial.json     # alvo do matching (1.109 contas)
│   ├── plano_contas.json          # master ECF (7.741 contas)
│   └── accounting_synonyms.json   # dicionário de sinônimos
├── templates/
│   └── Template_GT_BP_Padrao_v3.xlsx
├── tests/                  # 346 testes, roda com `uv run pytest -q`
└── docs/                   # apresentação, contratos, migração
```

---

## 🔎 Se algo der errado

| Sintoma | Causa provável | Fix |
|---|---|---|
| Janela não abre; erro de `tkinter` | Linux sem Tk instalado | `sudo apt install python3-tk` |
| Arrastar não funciona | driver `tkdnd` ausente | use o botão *Clique para escolher* |
| Balanço não fechou | conta com saldo ilegível ou escala trocada | conferir aba *Contas Não Identificadas* + escala |
| `Plano de contas não encontrado` | falta `data/plano_referencial.json` | `uv run python -m src.bp.generators.plano_referencial` |
| Match rate < 60% | poucos exemplos ou sem revisão | mais **treino** e **revisão** — ver [guia dos learners](src/bp/training/README.md) |
| `.exe` bloqueado pelo SmartScreen | executável não assinado (esperado) | *Mais informações → Executar assim mesmo* |

---

## 📌 Estado atual

- ✅ Janela do usuário final — **Plano J**
- ✅ Executável com allowlist + teste anti-vazamento — **Plano K**
- ✅ Saída no Template GT (entrega ao cliente) — **Plano H**
- ✅ Anos flexíveis + série histórica multi-arquivo — **Plano I**
- ✅ Parsers (XLSX/XLS/CSV/TXT/PDF nativo), matcher com sinônimos e desempate
- ✅ Treino incremental + review wizard
- ✅ `346 testes passando`
- 🔜 Aprendizado compartilhado por pasta de rede (v2 do Plano J)
- 🔜 OCR para PDFs escaneados (pipeline existe, falta ligar)

Documentos de arquitetura: [`ARQUITETURA.md`](ARQUITETURA.md), [`PLANO_REFERENCIAL.md`](PLANO_REFERENCIAL.md) (A), [`PLANO_B.md`](PLANO_B.md) (B), [`PLANO_C.md`](PLANO_C.md) (C), [`PLANO_D.md`](PLANO_D.md) (D), [`PLANO_E.md`](PLANO_E.md) (E), [`PLANO_F.md`](PLANO_F.md) (F), [`PLANO_G.md`](PLANO_G.md) (G), [`PLANO_H.md`](PLANO_H.md) (H), [`PLANO_I.md`](PLANO_I.md) (I), [`PLANO_J_INTERFACE.md`](PLANO_J_INTERFACE.md) (J — a janela), [`PLANO_K_EMPACOTAMENTO.md`](PLANO_K_EMPACOTAMENTO.md) (K — o `.exe`).

---

<div align="center">

Desenvolvido no Innovation Lab — Valuation | TAS Advisory · Grant Thornton Brasil

</div>
