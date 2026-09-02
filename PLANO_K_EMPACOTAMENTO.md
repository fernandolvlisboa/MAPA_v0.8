# Plano K — Empacotamento em `.exe`

> Estado: **implementado**. `uv run python build.py` gera `dist/MAPA.exe` e
> roda o teste de auditoria sobre ele. Ver
> [`bp.spec`](bp.spec), [`build.py`](build.py),
> [`tests/test_build_seguranca.py`](tests/test_build_seguranca.py).

---

## 1. O problema

Depois de a janela ficar pronta ([Plano J](PLANO_J_INTERFACE.md)), a pergunta
seguinte é: como esse programa chega ao computador do colega **sem** pedir
que ele instale Python, `uv`, `tkinter`, `tkdnd` e três libs pesadas — em
máquina corporativa onde ele nem sequer tem permissão para instalar coisas?

A resposta é um executável Windows onefile. E aí a segunda pergunta, mais
séria: **como garantir que esse executável não leve balancetes de cliente
para dentro?**

## 2. Por que a **ordem** importa

Um `.exe` do PyInstaller é um zip disfarçado. Qualquer pessoa que o receba
descompacta em minutos com `pyinstxtractor` e lê tudo que foi empacotado:
código-fonte, JSONs, planilhas, o que estiver lá. Se você compilar primeiro
e depois "limpar o repositório", o repositório fica limpo mas **o `.exe`
distribuído continua carregando os balancetes dentro dele**. Distribuir é
irreversível.

Por isso o Plano K é rígido em três regras:

1. **Allowlist explícita.** Cada arquivo empacotado é nomeado, um por um, em
   `bp.spec`. Nada de globs como `--add-data src/bp;src/bp`.
2. **Auditoria automática.** `tests/test_build_seguranca.py` abre o `.exe`
   gerado com a **mesma** ferramenta que um curioso mal-intencionado usaria
   (`pyinstxtractor-ng`) e falha se qualquer arquivo com cara de dado de
   cliente estiver dentro.
3. **Um comando só.** `build.py` compila **e** audita. Se a auditoria falhar,
   o comando sai com código de erro — o `.exe` não é considerado pronto.

---

## 3. O que entra e o que não entra

### Entra (declarado em `bp.spec`)

| Arquivo | Por quê |
|---|---|
| `data/plano_referencial.json` | Alvo do matching. Sem ele a janela abre e falha. |
| `data/plano_contas.json` | Plano master ECF. Referência de contas. |
| `data/accounting_synonyms.json` | Sinônimos contábeis usados pelo matcher. |
| `templates/Template_GT_BP_Padrao_v3.xlsx` | O template que a janela preenche. |
| `src/bp/training/account_variations.json` | Aprendizado do matcher. Ver §4. |

### Não entra (nunca)

- `src/bp/training/DFS_Exemple/` — os balancetes de cliente usados para treino.
- `auxil/BP_PDF_ex/` — PDFs de exemplo.
- `output/` — saídas geradas pelos testes.
- `data/match_cache.json` — cache de matching (contém strings de clientes).
- Os JSONs de treino sensíveis (`processed_files.json`, `training_cache.json`,
  `learned_patterns.json`, `training_stats.json`, `training_ignore.json`).

O que o teste procura, em resumo: **qualquer** `.xlsx/.xls/.csv/.pdf` fora
das pastas de biblioteca-terceiro, ou qualquer path que contenha
`DFS_Exemple`, `BP_PDF_ex`, `balanço`, `balancete`. Se aparece, o teste
falha e o build para.

---

## 4. A pergunta sobre o aprendizado

`account_variations.json` é o que faz o matcher acertar cada vez mais.
Duas opções — decidida a primeira, aberta a segunda:

- **v1 (agora): embarca no `.exe`.** Congela até você lançar versão nova.
  Simples de entregar; ruim para evolução — todo mundo tem o aprendizado do
  dia em que a versão saiu.
- **v2 (futuro): pasta de rede da empresa.** O `.exe` lê ao abrir. Todo mundo
  se beneficia do que cada um ensinou; o arquivo mora onde ele pertence, na
  rede corporativa; o `.exe` continua embarcando o `account_variations.json`
  como *fallback* (se a rede estiver fora do ar, ainda funciona). É o que
  a v2 do Plano J já previa como próximo passo.

## 5. Como rodar

```powershell
uv sync --extra packaging
uv run python build.py
```

Saída: `dist\MAPA.exe`, ~70 MB (medido no build de referência em Linux, um
tanto abaixo no Windows por causa da diferença de runtime). O comando falha
se a auditoria pegar algo indevido.

> **PyInstaller não faz cross-compile.** Um `.exe` só sai de um Windows.
> Rodar `build.py` no Linux gera um binário Linux — útil para validar o
> `.spec` e o teste, inútil para distribuir. O Plano K deixa preparado; a
> versão para a máquina do colega precisa ser gerada em máquina Windows
> (a sua, ou um runner Windows no CI).

## 6. Sobre administrador

O `.exe` em modo *onefile*:

- **Não precisa de admin** para rodar. Descompacta em `%TEMP%` do usuário.
- **Precisa** de admin (ou de MSIX/Chocolatey) apenas se você quiser
  *instalar* em `Program Files`.

Distribuição prática numa máquina corporativa travada:

1. Colega salva `MAPA.exe` no Desktop (ou em `Documents\MAPA\`).
2. Duplo-clique. A janela abre. Fim.
3. Nada muda no registry, nada exige elevação.

Antivírus corporativo às vezes marca binários PyInstaller como suspeitos —
é falso positivo comum (por causa do bootloader). Se acontecer, o time de
TI adiciona exceção pelo hash do arquivo.

## 7. Pendências

- **Runner Windows no CI.** Sem ele, todo lançamento depende de você rodar
  `build.py` na sua máquina antes de subir o `.exe` na aba *Releases* do
  GitHub. Configurar um runner GitHub-hosted Windows é meia hora.
- **Assinatura de código.** Windows SmartScreen alerta ao rodar um `.exe`
  não assinado pela primeira vez. Assinatura precisa de certificado (US$
  ~200/ano) — só vale se a distribuição virar rotina.
- **Ícone.** `bp.spec` está com `icon=None`. Colocar um `.ico` com o `M`
  do MAPA é meia hora de trabalho e melhora muito a percepção.

---

## O .exe da v0.8 saiu sem arrastar-e-soltar

Relatado por quem recebeu o binário: arrastar o arquivo para a janela não
trazia nada. O executável compilado no repositório privado funcionava.

**Causa.** `tkinterdnd2` são dois pedaços: os `.py`, que o PyInstaller acha
por importação, e a extensão Tcl `tkdnd` — uma pasta com `.dll` e
`pkgIndex.tcl` **dentro** do pacote. A segunda é *dado*, não módulo:
`hiddenimports` não a traz. O `bp.spec` declarava só

```python
hiddenimports = ["tkinterdnd2"]   # "o hook oficial cobre, mas..."
```

e confiava no hook do `pyinstaller-hooks-contrib`. Em runtime, no binário
distribuído:

```
TkinterDnD.Tk()
  -> tkroot.tk.call('package', 'require', 'tkdnd')
  -> TclError -> RuntimeError('Unable to load tkdnd library.')
```

`app/dnd.py` capturava com `except Exception: pass`, caía para o `tkinter.Tk`
puro e a janela abria com a zona de soltar virada em botão. Como o build é
`console=False`, **não havia mensagem nenhuma**.

**Por que nenhum teste pegou.** Na máquina que compila, o pacote está
instalado e tudo funciona; o defeito só existe dentro do bundle. É a mesma
família do §22 da nota de qualidade: o código está certo, o que falha é o que
foi (ou não foi) empacotado. Só o conteúdo do binário responde.

**Correções.**

1. `bp.spec` embarca a árvore `tkdnd` inteira (113 arquivos, 2,5 MB),
   declarada em vez de herdada de hook. Todas as plataformas entram de
   propósito: `TkinterDnD._require()` escolhe a pasta em runtime por
   `platform.system()`, `PROCESSOR_ARCHITECTURE` e versão do Tcl — filtrar
   pela máquina que compila é a mesma aposta que produziu o defeito. O spec
   localiza o pacote com `find_spec`, sem importá-lo, para não morrer numa
   máquina sem `tkinter`.
2. `app/dnd.py` guarda o motivo em `motivo_indisponivel` e o expõe em
   `diagnostico()`. A falha deixa de ser muda.
3. `app/ui.py` diz "arrastar-e-soltar indisponível nesta máquina" no lugar de
   só oferecer o clique, e põe o motivo técnico no rodapé da zona.
4. `tests/test_build_seguranca.py` audita o binário: a pasta `tkdnd` tem de
   estar lá, com `pkgIndex.tcl`, com a biblioteca nativa, e com a variante da
   plataforma para a qual o `.exe` foi compilado.
5. `build.py` **para** quando `pyinstxtractor-ng` não está instalado, em vez
   de deixar a auditoria pular em silêncio. Build não auditado não sai.
