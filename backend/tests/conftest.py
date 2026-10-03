"""
Configuración de las pruebas automáticas.

Las pruebas usan una base de datos APARTE (restaurante_sena_test por
defecto) que se borra y se crea de nuevo antes de cada prueba a partir
de restaurante_sena_completo.sql. Nunca tocan la base real.

Ejecutar desde la carpeta backend:
    python -m pytest
"""

import os
import re

import pytest

# Debe definirse ANTES de importar config/app.
NOMBRE_BD_PRUEBAS = os.environ.get("TEST_DB_NAME", "restaurante_sena_test")
if not NOMBRE_BD_PRUEBAS.endswith("_test"):
    raise RuntimeError("Por seguridad, la base de pruebas debe terminar en _test")
os.environ["DB_NAME"] = NOMBRE_BD_PRUEBAS
os.environ.setdefault("SECRET_KEY", "clave-solo-para-pruebas")
os.environ["IMPUESTO_NOMBRE"] = "Impoconsumo"
os.environ["IMPUESTO_PCT"] = "8"
os.environ["PROPINA_SUGERIDA_PCT"] = "10"

import mysql.connector  # noqa: E402

import config  # noqa: E402
import db  # noqa: E402

_RE_SENTENCIA_BD = re.compile(r"^(DROP DATABASE|CREATE DATABASE|USE)\b", re.IGNORECASE)


def cargar_script(ruta, nombre_bd):
    """Ejecuta un .sql cambiando el nombre de la base por nombre_bd."""
    texto = ruta.read_text(encoding="utf-8")
    conn = mysql.connector.connect(**db.parametros_conexion(database=False))
    try:
        cur = conn.cursor()
        cur.execute("SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci")
        for sentencia in db.dividir_sql(texto):
            if _RE_SENTENCIA_BD.match(sentencia):
                sentencia = re.sub(r"\brestaurante_sena\b", nombre_bd, sentencia)
            cur.execute(sentencia)
            if cur.with_rows:
                cur.fetchall()
        conn.commit()
    finally:
        conn.close()


def borrar_bd(nombre_bd):
    conn = mysql.connector.connect(**db.parametros_conexion(database=False))
    try:
        conn.cursor().execute(f"DROP DATABASE IF EXISTS `{nombre_bd}`")
    finally:
        conn.close()


@pytest.fixture
def bd():
    """Base de pruebas recién creada."""
    db.reiniciar_pool()
    cargar_script(config.BACKEND_DIR / "restaurante_sena_completo.sql", NOMBRE_BD_PRUEBAS)
    yield
    db.reiniciar_pool()


@pytest.fixture
def app(bd):
    from app import app as flask_app
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture
def cliente(app):
    return app.test_client()


@pytest.fixture
def crear_pedido(cliente):
    """Crea un pedido y devuelve la respuesta JSON."""
    def _crear(mesa=5, items=None, **extra):
        cuerpo = {"mesa": mesa, "items": items or [{"id": 1, "cantidad": 1}], **extra}
        r = cliente.post("/api/pedidos", json=cuerpo)
        assert r.status_code == 201, r.get_json()
        return r.get_json()
    return _crear
