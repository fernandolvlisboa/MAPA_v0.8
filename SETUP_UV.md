# Setup Rápido - Projeto BP

## Gerenciamento de Dependências com UV

Este projeto usa `uv` ao invés de `pip` para gerenciamento de dependências mais rápido e eficiente.

### Instalação do UV

Se ainda não tem o `uv` instalado:

```powershell
# Windows (PowerShell)
pip install uv

# Ou via pipx (recomendado)
pipx install uv
```

### Verificar Dependências

```powershell
python check_dependencies.py
```

### Instalar Dependências

**Opção 1: Instalar tudo (recomendado)**
```powershell
uv pip install -e .
```

**Opção 2: Instalar apenas as principais**
```powershell
uv pip install pandas openpyxl rapidfuzz pdfplumber pytesseract
```

**Opção 3: Instalar dependências faltantes individualmente**
```powershell
# Apenas as que faltam (veja output de check_dependencies.py)
uv pip install python-dotenv python-json-logger tabula-py pdfminer.six
```

### Comandos Úteis

**Listar pacotes instalados:**
```powershell
uv pip list
```

**Buscar pacote específico:**
```powershell
uv pip list | Select-String "rapidfuzz"
```

**Atualizar pacote:**
```powershell
uv pip install --upgrade rapidfuzz
```

**Desinstalar pacote:**
```powershell
uv pip uninstall rapidfuzz
```

### Vantagens do UV vs PIP

| Recurso | pip | uv |
|---------|-----|-----|
| Velocidade | Lento | **10-100x mais rápido** |
| Resolução de deps | Sequencial | **Paralela** |
| Cache | Básico | **Avançado com hardlinks** |
| Compatibilidade | 100% | 100% compatível com pip |
| Lock file | requirements.txt | pyproject.toml nativo |

### Dependências Principais do Projeto

**Parsing:**
- `pandas>=2.3.3` - DataFrames e manipulação de dados
- `openpyxl>=3.1.5` - Arquivos Excel (.xlsx)
- `xlrd>=2.0.2` - Arquivos Excel legado (.xls)
- `pdfplumber>=0.11.8` - Extração de PDFs
- `pymupdf>=1.23.0` - PDFs avançados

**Matching/Fuzzy:**
- `rapidfuzz>=3.14.3` - ✅ Fuzzy matching ultra-rápido
- `python-levenshtein>=0.27.3` - Distância de edição

**OCR/Imagem:**
- `pytesseract>=0.3.10` - OCR
- `pdf2image>=1.17.0` - PDF para imagem
- `pillow>=10.0.0` - Processamento de imagem
- `opencv-python>=4.8.0` - Visão computacional

**Validação:**
- `pydantic>=2.12.5` - Validação de dados

**Testes:**
- `pytest>=9.0.1` - Framework de testes

### Status Atual

```
✅ 15/21 dependências principais instaladas (71%)
❌ 6 faltando (python-dotenv, tabula-py, pyqt6, etc.)
❌ 1 dev dependency faltando (ipykernel)
```

Para instalar as faltantes:
```powershell
uv pip install python-dotenv python-json-logger tabula-py pdfminer.six pyqt6 ipykernel
```

### Workflows Comuns

**Setup inicial completo:**
```powershell
# 1. Verificar status
python check_dependencies.py

# 2. Instalar tudo
uv pip install -e .

# 3. Verificar novamente
python check_dependencies.py
```

**Adicionar nova dependência:**
```powershell
# 1. Adicionar ao pyproject.toml em [project.dependencies]
# 2. Instalar
uv pip install nome-do-pacote>=versao

# 3. Confirmar
python check_dependencies.py
```

**Ambiente limpo (reinstalar tudo):**
```powershell
# 1. Criar novo venv
python -m venv .venv

# 2. Ativar
.\.venv\Scripts\Activate.ps1

# 3. Instalar via uv
uv pip install -e .
```

### Troubleshooting

**Erro: `uv: command not found`**
```powershell
pip install uv
# Ou adicione ao PATH: C:\Users\<user>\AppData\Local\Programs\Python\Python313\Scripts
```

**Conflitos de versão:**
```powershell
# Forçar reinstalação
uv pip install --force-reinstall rapidfuzz
```

**Cache corrompido:**
```powershell
# Limpar cache do uv
uv cache clean
```
