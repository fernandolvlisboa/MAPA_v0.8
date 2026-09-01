"""
Testes da interface do usuário final (``src/bp/app``).

A janela em si não é testada aqui — o que é testado é tudo que ela **decide**:
o palpite de exercício e de cliente, a validação da seleção, o nome do arquivo
entregue, a leitura do drop e a tradução dos avisos do núcleo. Essa é a razão de
``service.py`` e ``dnd.py`` existirem separados de ``ui.py``.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from openpyxl import Workbook

from src.bp.app import dnd, paths, service
from src.bp.app.service import Entrada

# --------------------------------------------------------------- exercício


@pytest.mark.parametrize(
    "nome,esperado",
    [
        ("Balancete 2024 -Ultimo.csv", 2024),
        ("2012-12.TXT", 2012),
        ("2019-01.TXT", 2019),
        ("202404_2024 - Balancete.xls", 2024),
        ("1544 - BALANCETE 1222024.csv", 2024),           # MMAAAA colado
        ("Balancete 042025 em excel.xls", 2025),
        ("Balanc dez 25.xls", 2025),                       # mês + ano de 2 dígitos
        ("... Consolidado Dez24 - Parecer.pdf", 2024),
        ("3T25 _ DFS - MGLU3.pdf", 2025),                  # trimestre
        ("Balancete Real Life.xlsx", None),                # não há ano: não invente
        ("Balancete 1899.xlsx", None),                     # fora da faixa plausível
    ],
)
def test_ano_do_nome(nome, esperado):
    assert service.ano_do_nome(nome) == esperado


def test_ano_repetido_no_nome_vence():
    """"072022 122022" é o mesmo exercício escrito duas vezes."""
    assert service.ano_do_nome("Balancete 072022 122022 - RBM.xls") == 2022


def test_ano_futuro_distante_e_recusado():
    futuro = date.today().year + 5
    assert service.ano_do_nome(f"Balancete {futuro}.xlsx") is None


# ------------------------------------------------------------------ cliente


@pytest.mark.parametrize(
    "nome,esperado",
    [
        ("Balancete 072022 122022 - RBM.xls", "RBM"),
        ("BALANÇO-DRE 2024 - ADA.pdf", "ADA"),
        ("Balancete Real Life.xlsx", "Real Life"),
        ("2458-25 DF Neo Invest Controladora e Consolidado Dez24.pdf", "Neo Invest"),
    ],
)
def test_cliente_do_nome(nome, esperado):
    assert service.cliente_do_nome(nome) == esperado


def test_cliente_vazio_quando_o_nome_so_tem_data():
    """
    Sem palpite é melhor que palpite ruim.

    "Balancete 042025 em excel" como nome de cliente sairia impresso na capa de
    BP_GT. Campo vazio faz a tela exigir que a pessoa digite.
    """
    assert service.cliente_do_nome("Balancete 042025 em excel.xls") == ""
    assert service.cliente_do_nome("2012-12.TXT") == ""


def test_cliente_da_serie_usa_o_palpite_que_se_repete():
    nomes = ["Balancete 2022 - RBM.xls", "Balancete 2023 - RBM.xls", "Anexo 2024.xls"]
    assert service.cliente_do_nome(nomes) == "RBM"


# ------------------------------------------------------- nome do arquivo


def test_nome_de_saida_um_ano_e_serie():
    assert service.nome_de_saida("RBM Ltda", [2024]) == "RBM_Ltda_2024.xlsx"
    assert service.nome_de_saida("RBM", [2024, 2022, 2023]) == "RBM_2022-2024.xlsx"


def test_sanitizar_nome_tira_o_que_o_windows_recusa():
    assert service.sanitizar_nome('Cli<ente>:"/\\|?*') == "Cliente"
    assert service.sanitizar_nome("   ") == "Cliente"


def test_nunca_sobrescreve_entrega_anterior(tmp_path: Path):
    """Sobrescrever em silêncio é a forma mais barata de perder revisão feita."""
    (tmp_path / "X_2024.xlsx").write_text("entrega revisada")
    primeiro = service.caminho_sem_colisao(tmp_path, "X_2024.xlsx")
    assert primeiro.name == "X_2024 (2).xlsx"

    primeiro.write_text("outra")
    assert service.caminho_sem_colisao(tmp_path, "X_2024.xlsx").name == "X_2024 (3).xlsx"


# ----------------------------------------------------------------- seleção


def test_selecionar_separa_o_que_da_para_ler(tmp_path: Path):
    bom = tmp_path / "Balancete 2024.xlsx"
    ruim = tmp_path / "foto.png"
    for arquivo in (bom, ruim):
        arquivo.write_text("x")

    aceitos, recusados = service.selecionar([bom, ruim])
    assert [e.path for e in aceitos] == [bom]
    assert recusados == [ruim]
    assert aceitos[0].ano == 2024  # palpite já vem preenchido


def test_selecionar_pasta_pega_os_arquivos_de_dentro(tmp_path: Path):
    (tmp_path / "Balancete 2023.csv").write_text("x")
    (tmp_path / "Balancete 2024.csv").write_text("x")
    (tmp_path / "leiame.docx").write_text("x")

    aceitos, recusados = service.selecionar([tmp_path])
    assert sorted(e.nome for e in aceitos) == ["Balancete 2023.csv", "Balancete 2024.csv"]
    assert [p.name for p in recusados] == ["leiame.docx"]


def test_selecionar_nao_duplica(tmp_path: Path):
    arquivo = tmp_path / "Balancete 2024.csv"
    arquivo.write_text("x")
    aceitos, _ = service.selecionar([arquivo, arquivo])
    assert len(aceitos) == 1


# --------------------------------------------------------------- validação


def _entrada(tmp_path: Path, nome: str, ano: int | None) -> Entrada:
    caminho = tmp_path / nome
    caminho.write_text("x")
    return Entrada(caminho, ano)


def test_validar_sem_arquivo():
    assert service.validar([]) == ["Escolha pelo menos um balancete."]


def test_validar_exige_ano(tmp_path: Path):
    problemas = service.validar([_entrada(tmp_path, "b.xlsx", None)], "Cliente")
    assert any("exercício" in p for p in problemas)


def test_validar_recusa_dois_arquivos_no_mesmo_ano(tmp_path: Path):
    entradas = [_entrada(tmp_path, "a.xlsx", 2024), _entrada(tmp_path, "b.xlsx", 2024)]
    problemas = service.validar(entradas, "Cliente")
    assert any("2024" in p for p in problemas)


def test_validar_respeita_o_limite_do_template(tmp_path: Path):
    entradas = [
        _entrada(tmp_path, f"b{ano}.xlsx", ano) for ano in range(2019, 2019 + 6)
    ]
    problemas = service.validar(entradas, "Cliente")
    assert any(str(service.MAX_EXERCICIOS) in p for p in problemas)


def test_validar_exige_cliente(tmp_path: Path):
    problemas = service.validar([_entrada(tmp_path, "b.xlsx", 2024)], "   ")
    assert any("cliente" in p.lower() for p in problemas)


def test_validar_arquivo_sumido(tmp_path: Path):
    entrada = _entrada(tmp_path, "b.xlsx", 2024)
    entrada.path.unlink()
    assert any("não encontrei" in p.lower() for p in service.validar([entrada], "C"))


# -------------------------------------------------------- avisos do núcleo


def test_avisos_viram_frase_de_tela_sem_repetir():
    """
    O aviso de desequilíbrio do núcleo cita o saldo ilegível como causa. Se a
    tradução do desequilíbrio não for testada primeiro, os dois avisos viram a
    mesma frase e a tela mostra o mesmo alerta duas vezes.
    """
    alertas = service._alertas(
        [
            "[2024] 1 conta(s) com saldo ilegível na origem — o valor não pôde "
            "ser convertido e entrou como zero.",
            "[2024] Ativo (6,881.6) != Passivo+PL (2,110.7) — há contas com "
            "saldo ilegível (acima).",
        ]
    )
    assert len(alertas) == 2
    assert alertas[0].startswith("2024: Algumas contas")
    assert "balanço não fechou" in alertas[1]


def test_aviso_desconhecido_passa_inteiro():
    (frase,) = service._alertas(["[2023] algo novo que o núcleo passou a avisar"])
    assert frase == "2023: algo novo que o núcleo passou a avisar"


# --------------------------------------------------- fila de revisão lida


def test_ler_pendentes_da_planilha_gerada(tmp_path: Path):
    planilha = tmp_path / "saida.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "Contas Não Identificadas"
    ws.append(["Fila de revisão do analista."])
    ws.append(["ano", "codigo_original", "descricao_original", "motivo_no_match", "valor"])
    ws.append([2024, "1.1.01", "BENS NUMERARIOS", "score baixo", 1234.56])
    ws.append([2024, "1.1.02", "CONTA XPTO", "sem candidato", None])
    wb.save(planilha)

    pendentes = service.ler_pendentes(planilha)
    assert [p.descricao for p in pendentes] == ["BENS NUMERARIOS", "CONTA XPTO"]
    assert pendentes[0].valor == pytest.approx(1234.56)
    assert pendentes[1].valor is None


def test_ler_pendentes_nao_derruba_com_planilha_ruim(tmp_path: Path):
    """A entrega já está no disco; falhar aqui não pode virar erro de tela."""
    ruim = tmp_path / "nao_e_xlsx.xlsx"
    ruim.write_text("isto não é uma planilha")
    assert service.ler_pendentes(ruim) == []


# ------------------------------------------------------------- execução


def test_gerar_com_arquivo_inexistente_vira_mensagem(tmp_path: Path):
    """Usuário final não vê stacktrace — nunca."""
    entrada = Entrada(tmp_path / "sumido.xlsx", 2024)
    resultado = service.gerar([entrada], tmp_path / "saida", "Cliente")
    assert resultado.ok is False
    assert resultado.erro
    assert "sumido.xlsx" in resultado.erro


def test_resultado_pede_atencao_quando_balanco_nao_fecha():
    limpo = service.Resultado(ok=True, balanco_confere=True)
    torto = service.Resultado(ok=True, balanco_confere=False)
    assert limpo.precisa_atencao is False
    assert torto.precisa_atencao is True


# ------------------------------------------------------------ arrastar


def test_drop_com_chaves_e_espaco_no_caminho():
    """
    Compara a string inteira, não ``.name``: numa suíte rodando em Linux,
    ``Path`` não trata ``\\`` como separador e ``.name`` devolveria o caminho
    todo — o teste passaria a medir o SO, não o parser.
    """
    caminhos = dnd.caminhos_do_drop(r"{C:\Meus Balancetes\jan 24.xlsx} C:\outro.csv")
    assert [str(p) for p in caminhos] == [
        r"C:\Meus Balancetes\jan 24.xlsx",
        r"C:\outro.csv",
    ]


def test_drop_sem_chaves_reagrupa_pelo_que_existe(tmp_path: Path):
    """
    Alguns sistemas mandam o caminho com espaço sem envolver em ``{}``. Quebrar
    por espaço criaria dois arquivos inexistentes; o desempate é o disco.
    """
    arquivo = tmp_path / "Balancete de 2024.xlsx"
    arquivo.write_text("x")
    assert dnd.caminhos_do_drop(str(arquivo)) == [arquivo]


def test_drop_vazio():
    assert dnd.caminhos_do_drop("") == []


# --------------------------------------------------------------- caminhos


def test_resource_dir_aponta_para_o_que_o_app_le():
    """Da fonte, os recursos do runtime têm de estar sob resource_dir()."""
    raiz = paths.resource_dir()
    assert (raiz / "templates" / "Template_GT_BP_Padrao_v3.xlsx").exists()
    assert (raiz / "data" / "plano_referencial.json").exists()


def test_pastas_de_escrita_ficam_fora_da_pasta_do_programa():
    """
    Congelado, ``resource_dir()`` é temporária e pode ser só-leitura. Config,
    log e saída não podem morar lá dentro.
    """
    recursos = paths.resource_dir().resolve()
    for gravavel in (paths.user_data_dir(), paths.default_output_dir()):
        assert recursos not in gravavel.resolve().parents
        assert gravavel.resolve() != recursos


# ============================================================================
# Reconciliação na tela — a frase precisa carregar os números
# ============================================================================


def test_tela_explica_o_desequilibrio_com_o_valor():
    """
    "Não fechou" não ajuda ninguém. A tela tem de dizer POR QUANTO não fecha e
    QUANTAS contas somam esse valor — é o que permite decidir entre entregar e
    voltar ao balancete.

    Esta é a mensagem que o núcleo emite de verdade hoje (ver
    ``build_gt_output._validar``), não uma string montada à mão.
    """
    (frase,) = service._alertas(
        [
            "[2022] Não fecha por 540,192.45. Há 3 conta(s) sem destino no "
            "template somando 540,192.45 — exatamente a diferença. As 3 "
            "conta(s) explicam 100% do desequilíbrio; não há mais nada faltando."
        ]
    )
    assert frase.startswith("2022: ")
    assert "540,192.45" in frase, "a tela perdeu o valor da diferença"
    assert "3 conta(s)" in frase, "a tela perdeu a contagem"
    assert "Sumário" in frase, "a tela não diz onde ver a lista"


def test_tela_grita_quando_a_diferenca_nao_e_explicada():
    """
    O caso perigoso: sobra diferença sem explicação. Significa valor contado
    duas vezes ou perdido — a tela não pode tranquilizar.
    """
    (frase,) = service._alertas(
        [
            "[2022] Não fecha por 1,000.00. Há 1 conta(s) sem destino no "
            "template somando 400.00, mas sobram 600.00 sem explicação. "
            "ATENÇÃO: há conta contada duas vezes ou perdida no caminho."
        ]
    )
    assert "ATENÇÃO" in frase
    assert "Não entregue" in frase


def test_traducao_do_nucleo_para_a_tela_esta_viva():
    """
    Guarda contra o defeito que este arquivo já teve: os testes construíam à
    mão avisos que o núcleo tinha deixado de emitir. Verdes, validando um
    contrato morto.

    Aqui a mensagem vem do próprio núcleo — se ela mudar de forma, este teste
    quebra e a tradução é revista junto.
    """
    from src.bp.output.build_gt_output import ContaSemDestino, Reconciliacao

    reconc = Reconciliacao(
        desequilibrio=540192.45,
        soma_sem_destino=-540192.45,
        contas=[ContaSemDestino("2.2.1", "PARCELAMENTOS", -540192.45, "sem match")],
    )
    (frase,) = service._alertas([f"[2022] {reconc.mensagem()}"])
    assert "O balanço não fechou por" in frase, (
        f"a tradução da tela não reconhece mais a mensagem do núcleo: {frase}"
    )
