"""
Conversão de saldo contábil para float — **fonte única** do projeto.

Antes desta extração o projeto convertia "texto de saldo → float" em cinco
lugares independentes (``BaseParser._normalize_saldo``, duas implementações
dentro do próprio ``dispatcher.py``, ``PDFBalanceParser._to_float`` e
``_to_float_safe`` no exporter). Elas divergiam em entradas contábeis
corriqueiras — o mesmo balancete rendia saldos diferentes conforme o caminho —
e quatro delas devolviam ``0.0`` em vez de sinalizar falha, tornando um saldo
perdido indistinguível de uma conta legitimamente zerada.

Ver ``REVISAO_QUALIDADE.md`` §1 para o levantamento e a evidência.

Contrato
--------
``parse_saldo`` devolve ``None`` quando não consegue ler. **Nunca ``0.0`` como
disfarce de erro** — ``0.0`` significa "esta conta vale zero", e a distinção
entre as duas coisas é o que permite ao validador e ao rollup a jusante
detectarem dado corrompido. Quem precisa de um número para somar usa
``parse_saldo_ou(valor, 0.0)`` e assume a decisão explicitamente.

Formatos aceitos
----------------
=====================  ============  =========================================
Entrada                Resultado     Observação
=====================  ============  =========================================
``"1.234,56"``         1234.56       BR canônico
``"1.234"``            1234.0        só milhar
``"1234.56"``          1234.56       decimal com ponto (separador por formato)
``"1,234.56"``         1234.56       US
``"(1.234,56)"``       -1234.56      parênteses = negativo (padrão contábil)
``"1.234,56 C"``       1234.56       marcador D/C removido, magnitude mantida
``"R$ 1.234,56"``      1234.56       símbolo de moeda
``"-"`` ``""``         ``None``      célula vazia
``"abc"``              ``None``      ilegível
``NaN`` ``inf``        ``None``      não-finito não é saldo
=====================  ============  =========================================
"""

from __future__ import annotations

import math
import re
from typing import Any

__all__ = ["parse_saldo", "parse_saldo_ou"]

#: Marcador de natureza no fim do valor ("1.234,56 C", "500D").
#: A magnitude é mantida: a natureza é atributo da CONTA, não do número, e
#: inverter o sinal aqui mudaria a semântica de todo balancete já processado.
_SUFIXO_DC_RE = re.compile(r"\s*[DdCc]\s*$")

#: Tudo que não é dígito ou separador decimal/milhar.
_NAO_NUMERICO_RE = re.compile(r"[^\d.,]")

#: Ponto usado como separador de milhar: "1.234", "12.345.678".
_SO_MILHAR_RE = re.compile(r"\d{1,3}(\.\d{3})+")


def parse_saldo(valor: Any) -> float | None:
    """
    Converte um saldo para float. Devolve ``None`` se não for possível ler.

    O separador decimal é decidido pelo **formato**, não por convenção fixa:
    entre ``.`` e ``,`` o último a aparecer é o decimal. Sozinho, o ponto só é
    milhar quando o texto casa ``1.234`` / ``12.345.678`` — é o que evita que
    ``"1234.56"`` (um float serializado como string) vire ``123456.0``.
    """
    if valor is None:
        return None

    # bool é subclasse de int, mas não é saldo.
    if isinstance(valor, bool):
        return None

    # Não-texto: só passa o que é numérico de fato. `float()` cobre int, float,
    # Decimal e os tipos do numpy, e recusa listas, dicts e os sentinelas do
    # pandas (pd.NA levanta TypeError, pd.NaT vira NaN não-finito). Converter
    # objeto arbitrário para str e raspar dígitos daria valores absurdos —
    # `[1, 2]` viraria 1.2.
    if not isinstance(valor, str):
        try:
            numero = float(valor)
        except (TypeError, ValueError):
            return None
        return numero if math.isfinite(numero) else None

    texto = valor.strip()
    if not texto:
        return None

    negativo = texto.startswith("-") or (
        texto.startswith("(") and texto.endswith(")")
    )

    digitos = _NAO_NUMERICO_RE.sub("", _SUFIXO_DC_RE.sub("", texto))
    if not any(c.isdigit() for c in digitos):
        return None

    if "," in digitos and "." in digitos:
        # O último separador é o decimal; o outro é milhar.
        if digitos.rfind(",") > digitos.rfind("."):
            digitos = digitos.replace(".", "").replace(",", ".")
        else:
            digitos = digitos.replace(",", "")
    elif "," in digitos:
        digitos = digitos.replace(".", "").replace(",", ".")
    elif _SO_MILHAR_RE.fullmatch(digitos):
        digitos = digitos.replace(".", "")

    try:
        numero = float(digitos)
    except ValueError:
        return None
    if not math.isfinite(numero):
        return None
    return -numero if negativo else numero


def parse_saldo_ou(valor: Any, default: float = 0.0) -> float:
    """
    ``parse_saldo`` com fallback explícito.

    Use quando o chamador precisa somar e já decidiu como tratar o ilegível.
    A diferença para o comportamento antigo é que a decisão fica **no ponto de
    chamada**, visível na leitura, em vez de escondida no conversor.
    """
    resultado = parse_saldo(valor)
    return default if resultado is None else resultado
