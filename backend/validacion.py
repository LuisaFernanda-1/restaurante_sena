"""
validacion.py — Validación de los datos que llegan a la API

Todas las funciones lanzan ErrorAPI (HTTP 400) con un mensaje claro en
español cuando el dato no es válido.
"""

import re
from datetime import date

from flask import current_app, request

from errores import ErrorAPI


def jresp(data, status=200):
    """Respuesta JSON (convierte Decimal y fechas, ver app.JSONRestaurante)."""
    return current_app.json.response(data), status

def cuerpo_json():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ErrorAPI("El cuerpo de la petición debe ser un objeto JSON.")
    return data


def v_entero(valor, campo, minimo=None, maximo=None):
    if isinstance(valor, bool):
        raise ErrorAPI(f"{campo}: debe ser un número entero.")
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)
    if isinstance(valor, str) and re.fullmatch(r"\s*-?\d+\s*", valor):
        valor = int(valor)
    if not isinstance(valor, int):
        raise ErrorAPI(f"{campo}: debe ser un número entero.")
    if minimo is not None and valor < minimo:
        raise ErrorAPI(f"{campo}: debe ser como mínimo {minimo}.")
    if maximo is not None and valor > maximo:
        raise ErrorAPI(f"{campo}: debe ser como máximo {maximo}.")
    return valor


def v_texto(valor, campo, max_len, obligatorio=False):
    if valor is None:
        valor = ""
    if not isinstance(valor, str):
        raise ErrorAPI(f"{campo}: debe ser texto.")
    valor = valor.strip()
    if obligatorio and not valor:
        raise ErrorAPI(f"{campo}: es obligatorio.")
    if len(valor) > max_len:
        raise ErrorAPI(f"{campo}: máximo {max_len} caracteres.")
    return valor


def v_bool(valor, campo):
    if isinstance(valor, bool):
        return valor
    if valor in (0, 1, "0", "1"):
        return str(valor) == "1"
    raise ErrorAPI(f"{campo}: debe ser verdadero o falso.")


def arg_entero(nombre, defecto, minimo, maximo):
    valor = request.args.get(nombre)
    if valor in (None, ""):
        return defecto
    return v_entero(valor, nombre, minimo, maximo)


def v_fecha(valor, campo, obligatorio=False):
    """Fecha AAAA-MM-DD (o None si viene vacía y no es obligatoria)."""
    if valor in (None, ""):
        if obligatorio:
            raise ErrorAPI(f"{campo}: es obligatoria.")
        return None
    if not isinstance(valor, str):
        raise ErrorAPI(f"{campo}: use el formato AAAA-MM-DD.")
    try:
        return date.fromisoformat(valor)
    except ValueError:
        raise ErrorAPI(f"{campo}: use el formato AAAA-MM-DD.")


def v_correo(valor, campo="Correo"):
    correo = v_texto(valor, campo, 150).lower()
    if correo and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", correo):
        raise ErrorAPI(f"{campo}: no es un correo válido.")
    return correo or None
