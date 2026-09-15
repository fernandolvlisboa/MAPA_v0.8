"""
Reconhecimento de plano COSIF (instituição financeira).

O balancete de banco usa o COSIF, cuja estrutura de grupos é incompatível com a
convenção ``1=Ativo, 2=Passivo, 3+=Resultado`` do plano de PJ: o grupo 2 é
Permanente (Ativo, não Passivo), os grupos 3 e 9 são compensação (fora do
balanço), o 7 é receita e o 8 é despesa. Sem reconhecer isso, a compensação
inflava o balanço em dezenas de milhões e a equação contábil "não fechava".

Ver ``src/bp/utils/cosif.py`` e REVISAO_QUALIDADE.md.
"""

from __future__ import annotations

import pytest

from src.bp.utils.cosif import (
    detectar_cosif,
    e_compensacao,
    mapear_cosif,
    papel_cosif,
)

pytestmark = pytest.mark.contrato


def _conta(codigo: str, descricao: str) -> dict:
    return {"codigo": codigo, "descricao": descricao}


#: Raízes de grupo de um balancete COSIF (já canonicalizadas: raiz = 1 dígito).
COSIF_RAIZES = [
    _conta("1", "CIRCULANTE E REALIZAVEL A LONGO PRAZO"),
    _conta("2", "PERMANENTE"),
    _conta("3", "COMPENSACAO"),
    _conta("4", "CIRCULANTE E EXIGIVEL A LONGO PRAZO"),
    _conta("6", "PATRIMONIO LIQUIDO"),
    _conta("7", "CONTAS DE RESULTADO CREDORAS"),
    _conta("8", "CONTAS DE RESULTADO DEVEDORAS"),
    _conta("9", "COMPENSACAO"),
]

#: Raízes de um balancete de PJ comum — não pode ser confundido com COSIF.
PJ_RAIZES = [
    _conta("1", "ATIVO"),
    _conta("2", "PASSIVO"),
    _conta("3", "RECEITAS"),
    _conta("4", "DESPESAS"),
]


def test_papel_de_cada_grupo_cosif():
    assert papel_cosif("1.1.2") == "ATIVO"
    assert papel_cosif("2.2.5") == "ATIVO"  # Permanente é Ativo, não Passivo
    assert papel_cosif("3.0.4") == "COMPENSACAO"
    assert papel_cosif("4.9.4") == "PASSIVO"
    assert papel_cosif("6.1.0") == "PASSIVO"  # PL entra do lado do Passivo
    assert papel_cosif("7.1.0") == "RECEITA"
    assert papel_cosif("8.1.7") == "DESPESA"
    assert papel_cosif("9.0.4") == "COMPENSACAO"
    assert papel_cosif("") is None


def test_e_compensacao():
    assert e_compensacao("3.0.0.00.00.00001")
    assert e_compensacao("9.9.9.99.99.09999")
    assert not e_compensacao("1.1.2.30")
    assert not e_compensacao("7.1.0")


def test_detecta_cosif_pela_assinatura_dos_grupos_de_resultado():
    assert detectar_cosif(COSIF_RAIZES) is True


def test_nao_confunde_pj_com_cosif():
    # Um plano de PJ não tem grupo 7 "Resultado Credoras" nem 8 "Devedoras".
    assert detectar_cosif(PJ_RAIZES) is False


def test_de_para_casa_por_prefixo_mais_longo():
    # Opção B: o pessoal (8.1.7.27/30/33) tem de vencer o fallback de despesas
    # administrativas (8.1) — é o que separa pessoal de G&A na DRE.
    assert mapear_cosif("8.1.7.27.00.00003")[0] == "3.01.01.07.01.01"  # pessoal
    assert mapear_cosif("8.1.7.30")[0] == "3.01.01.07.01.01"           # pessoal
    assert mapear_cosif("8.1.8.20.00.00003")[0] == "3.01.01.07.01.23"  # depreciação
    assert mapear_cosif("8.1.7.03.00.00003")[0] == "3.01.01.07.01.04"  # cai no 8.1 = G&A
    assert mapear_cosif("8.1.9.00.00.00002")[0] == "3.01.01.07.01.04"  # idem, via 8.1


def test_de_para_dos_grupos_principais():
    assert mapear_cosif("1.1.0.00.00.00006")[0] == "1.01.01"        # disponibilidades
    assert mapear_cosif("1.6.1.20.40")[0] == "1.01.02.02"           # operações de crédito
    assert mapear_cosif("6.1.1.10.13.00005")[0] == "2.03.01"        # capital social
    assert mapear_cosif("7.1.0.00.00.00008")[0] == "3.01.01.05.01.01"  # receitas
    assert mapear_cosif("8.9.4.10.00.00006")[0] == "3.02.01.01"     # IRPJ/CSLL


def test_de_para_sem_cobertura_devolve_none():
    # Um grupo sem regra na de-para (relações interfinanceiras) não casa.
    assert mapear_cosif("1.4.4.30.10.00018") is None
    assert mapear_cosif("") is None


def test_compensacao_sozinha_nao_basta_sem_resultado_credor():
    # Só "COMPENSACAO" nos grupos 3/9, sem o par de resultado, não é sinal
    # suficiente — evita falso positivo.
    apenas_compensacao = [
        _conta("1", "ATIVO"),
        _conta("3", "COMPENSACAO"),
        _conta("9", "COMPENSACAO"),
    ]
    assert detectar_cosif(apenas_compensacao) is False
