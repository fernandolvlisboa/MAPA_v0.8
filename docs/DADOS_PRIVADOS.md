# Dados privados no MAPA

Este documento diz **o que fazer** e **o que NÃO fazer** com os balancetes de
clientes que alimentam o treino e os testes do MAPA.

Existe para responder a uma pergunta específica: *como manter um corpus de
clientes na máquina, adicionando e removendo à vontade, sem contaminar o
repositório* — em especial agora que o MAPA pode virar público.

---

## Regra única

**Arquivos com dados de cliente ficam em `data/samples/` e nunca são
commitados.** O `.gitignore` já garante isso: a pasta inteira é ignorada,
com exceção do `README.md` que fica lá dentro para orientar quem clona o
repo.

Se essa regra bastasse, este documento acabava aqui. Mas há uma armadilha
que precisa entrar no seu radar antes de mudar a visibilidade do
repositório.

---

## ⚠️ Antes de tornar o repositório público

**Remover os arquivos agora NÃO apaga o passado.** O git guarda todo
commit, e os balancetes antigos continuam recuperáveis por qualquer pessoa
com `git log` e `git show`. Se você tornar público sem tratar isso, os
dados estarão lá — mesmo que a árvore atual esteja limpa.

Você tem três caminhos, do mais seguro ao mais destrutivo:

### Caminho A (mais seguro): repositório público novo

Crie um repositório novo, vazio, no GitHub, e envie **só o estado atual** —
sem histórico:

```bash
# Numa cópia limpa do repo (para não perder o histórico privado):
cd /tmp && git clone --depth 1 https://github.com/fernandolvlisboa/MAPA mapa_v0.8
cd mapa_v0.8
rm -rf .git
git init -q && git add . && git commit -q -m "Initial public release"
git remote add origin https://github.com/fernandolvlisboa/MAPA_v0.8.git
git push -u origin main
```

O repo privado original continua intacto (com histórico completo) e o
público começa do zero. **Perde-se o histórico**, mas ganha-se a certeza
de que nenhum dado sensível vazou.

### Caminho B: reescrever o histórico no repo atual

Se manter o histórico importa, use `git filter-repo` para expurgar os
caminhos com dados de cliente de **todos** os commits:

```bash
pip install git-filter-repo
# Faça backup antes! (destrutivo por definição)
git clone --mirror https://github.com/fernandolvlisboa/MAPA mapa-backup.git

git filter-repo \
  --path src/bp/training/DFS_Exemple \
  --path data/samples \
  --invert-paths

# Depois é preciso force-push, e todos os clones antigos ficam quebrados:
git push origin --force --all
git push origin --force --tags
```

Avisos importantes:
- **Destrutivo.** SHAs mudam, force-push é necessário, todos os clones e
  forks precisam ser refeitos.
- **Não é retroativo em forks.** Se alguém já forkou, o fork guarda o
  histórico antigo. Só o GitHub Support consegue apagar isso.
- **PRs antigos podem referenciar SHAs que sumiram.** URLs quebram.
- Se você usou os balancetes em vários locais (não só `DFS_Exemple` /
  `data/samples`), a lista de `--path` precisa cobrir todos.

### Caminho C (não recomendado): tornar público como está

Só considere se você tem certeza de que nunca commitou balancete de
cliente — o que **não é o caso** deste repositório: o histórico atual tem
45 arquivos em `src/bp/training/DFS_Exemple/`, ~31 MB, muitos deles com
CNPJ e nome de empresa no nome. Este caminho vaza dados.

**Recomendação:** vá pelo Caminho A. É o único que dá garantia sem
contornos.

---

## O que já foi feito no repositório

- `data/samples/` criada e adicionada ao `.gitignore` (só o `README.md`
  dela é rastreado).
- `src/bp/training/DFS_Exemple/` **retirada do rastreamento** e movida
  para `data/samples/` na sua máquina local. Os arquivos **continuam no
  histórico** — ver a seção "Antes de tornar público".
- Código configurável: `src/bp/utils/paths.py` procura os arquivos em
  `MAPA_SAMPLES_DIR` (env var) e cai em `data/samples/` como padrão.
- Testes ajustados: se `data/samples/` estiver vazio, os testes de
  integração pulam com mensagem explicativa — nada quebra.

---

## Uso no dia a dia

**Adicionar balancetes:**
```bash
cp ~/Downloads/Balancete-Cliente-X.xlsx data/samples/
```
Git não enxerga — `git status` continua limpo.

**Remover balancetes:**
```bash
rm data/samples/Balancete-Cliente-X.xlsx
```
Também invisível ao git.

**Rodar treino:**
```bash
uv run python -m src.bp.training.train
```

**Rodar suíte de testes (inclui os que dependem do corpus):**
```bash
uv run pytest
```
Se `data/samples/` estiver vazio: 4 skips a mais, nenhum erro.

**Guardar o corpus fora do repositório** (útil se sincroniza entre
máquinas via Dropbox/Drive):
```bash
export MAPA_SAMPLES_DIR="/mnt/dropbox/clientes/balancetes"
```
Coloque no seu `~/.bashrc` / `~/.zshrc` para persistir. O código lê essa
variável antes do default.

---

## Checklist antes de dar `git push`

- [ ] `git status` está limpo (ou só com mudanças que você quer commitar).
- [ ] Nenhum arquivo em `data/samples/` aparece no status (exceto o
      `README.md`, se você o editou de propósito).
- [ ] `git diff --cached` não mostra saldos, CNPJs ou nomes de clientes.

Se qualquer um desses não bater, **investigue antes de push**. O
`.gitignore` está desenhado para nunca chegar a esse ponto, mas um
`git add -f` ou um caminho fora de `data/samples/` fura a rede.

---

## Referências

- `README.md` §"O que é versionado e o que não é"
- `SECURITY_REVIEW.md` — política geral do projeto
- `data/samples/README.md` — instruções sucintas para quem clona o repo
