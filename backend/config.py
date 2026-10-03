"""
config.py — Configuración de Restaurante SENA leída desde backend/.env

Las variables de entorno del sistema tienen prioridad sobre el archivo
.env (así las pruebas automáticas pueden usar otra base de datos).
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent
PROYECTO_DIR = BACKEND_DIR.parent

load_dotenv(BACKEND_DIR / ".env", override=False)


class ConfigError(RuntimeError):
    pass


def _texto(nombre, defecto=None, obligatorio=False):
    valor = os.environ.get(nombre, defecto)
    if valor is not None:
        valor = valor.strip()
    if obligatorio and not valor:
        raise ConfigError(
            f"Falta la variable {nombre} en backend/.env "
            f"(copie backend/.env.example como backend/.env y complétela)."
        )
    return valor


def _entero(nombre, defecto):
    valor = _texto(nombre, str(defecto))
    try:
        return int(valor)
    except ValueError:
        raise ConfigError(f"La variable {nombre} debe ser un número entero (valor actual: {valor!r}).")


def _porcentaje(nombre, defecto):
    valor = _texto(nombre, str(defecto))
    try:
        numero = float(valor.replace(",", "."))
    except ValueError:
        raise ConfigError(f"La variable {nombre} debe ser un número (valor actual: {valor!r}).")
    if not 0 <= numero <= 100:
        raise ConfigError(f"La variable {nombre} debe estar entre 0 y 100.")
    return numero


# --- Base de datos ---
DB_HOST = _texto("DB_HOST", "127.0.0.1")
DB_PORT = _entero("DB_PORT", 3306)
DB_USER = _texto("DB_USER", "root")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
DB_NAME = _texto("DB_NAME", "restaurante_sena")

# --- Servidor ---
SECRET_KEY = _texto("SECRET_KEY", obligatorio=True)
# Dirección con la que los celulares abren el sistema (va dentro de los QR)
SERVER_URL = (_texto("SERVER_URL", "http://localhost:8000") or "").rstrip("/")
# Poner en 1 solo si el sistema se publica con HTTPS
COOKIE_SEGURA = _texto("COOKIE_SEGURA", "0") == "1"

# --- Impuestos y propina (se calculan en el servidor, en pesos enteros) ---
IMPUESTO_NOMBRE = _texto("IMPUESTO_NOMBRE", "Impoconsumo") or "Impoconsumo"
IMPUESTO_PCT = _porcentaje("IMPUESTO_PCT", 8)
PROPINA_SUGERIDA_PCT = _porcentaje("PROPINA_SUGERIDA_PCT", 10)

# --- Datos del restaurante (aparecen en la factura) ---
RESTAURANTE_NOMBRE = _texto("RESTAURANTE_NOMBRE", "Restaurante SENA")
RESTAURANTE_NIT = _texto("RESTAURANTE_NIT", "")
RESTAURANTE_DIRECCION = _texto("RESTAURANTE_DIRECCION", "")
