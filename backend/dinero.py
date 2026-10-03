"""
dinero.py — Cálculo de totales en pesos colombianos (enteros)

    base      = subtotal - descuento del cupón
    impuesto  = base × IMPUESTO_PCT      (Impoconsumo 8 % por defecto)
    propina   = base × PROPINA_SUGERIDA_PCT, solo si el comensal la acepta
    total     = base + impuesto + propina

Cada valor se redondea al peso más cercano (0,5 hacia arriba).
"""

from decimal import ROUND_HALF_UP, Decimal

import config


def pesos(valor):
    return int(Decimal(str(valor)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def porcentaje_de(base, pct):
    return pesos(Decimal(base) * Decimal(str(pct)) / 100)


def calcular_totales(subtotal, descuento_pct=0, con_propina=True):
    descuento = porcentaje_de(subtotal, descuento_pct)
    base = subtotal - descuento
    impuesto = porcentaje_de(base, config.IMPUESTO_PCT)
    propina = porcentaje_de(base, config.PROPINA_SUGERIDA_PCT) if con_propina else 0
    return {
        "subtotal": subtotal,
        "descuento": descuento,
        "impuesto": impuesto,
        "propina": propina,
        "total": base + impuesto + propina,
    }
