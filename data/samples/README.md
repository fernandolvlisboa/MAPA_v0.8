# `data/samples/` — balancetes de treinamento e teste

Esta pasta é o **único lugar** onde o MAPA procura os balancetes que ele lê
para treinar e testar. Ela existe no repositório, para a versão do MAPA original ela não é ignorada,
mas deve ser tratada com cautela e não deve estar disponível para clone..

## Por que essa separação existe

Os balancetes carregam dados de clientes (CNPJ, nomes, saldos). Se
entrassem no repositório, viajariam junto com todo commit e todo clone.

O Clone já aconteceu no MAPA v0.8 e esse repositório deve se manter privado.

## Como usar

**Adicionar balancetes:** copie os arquivos para dentro desta pasta.

Formatos aceitos: `.xls`, `.xlsx`, `.csv`, `.txt`, `.pdf`.

**Remover balancetes:** delete os arquivos. Nada acontece no git.

**Rodar treino:**
```bash
uv run python -m src.bp.training.train
```

**Rodar os testes que usam corpus:**
```bash
uv run pytest -m integration
```

Se a pasta estiver vazia, os testes de corpus **pulam** com mensagem
explicativa — nada quebra.

## Guardar os balancetes em outro lugar (opcional)

Se você prefere manter os balancetes fora do repositório (num pen drive,
Dropbox, pasta compartilhada), aponte a variável de ambiente
`MAPA_SAMPLES_DIR` para lá:

```bash
export MAPA_SAMPLES_DIR="/mnt/dropbox/clientes/balancetes"
uv run python -m src.bp.training.train
```

O código lê essa variável antes de cair no default `data/samples/`.

## Documentação completa

Ver `docs/DADOS_PRIVADOS.md` — inclui o procedimento para tornar o
repositório público sem expor os dados que **já estão no histórico** do
git.
