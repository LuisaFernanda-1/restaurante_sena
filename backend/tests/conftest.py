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
# Por defecto las pruebas usan el modo "solo QR"; test_sin_qr.py prueba el otro.
os.environ["PERMITIR_PEDIDO_SIN_QR"] = "0"

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


# Contraseñas SOLO para las pruebas: se asignan a los usuarios de la base
# de pruebas (las temporales reales están únicamente en el README).
CLAVES_TEMPORALES = {
    "admin": "Prueba-Admin-111",
    "chef": "Prueba-Cocina-222",
    "mesero": "Prueba-Salon-333",
}


@pytest.fixture
def bd():
    """Base de pruebas recién creada."""
    import seguridad
    from werkzeug.security import generate_password_hash
    db.reiniciar_pool()
    cargar_script(config.BACKEND_DIR / "restaurante_sena_completo.sql", NOMBRE_BD_PRUEBAS)
    for usuario, clave in CLAVES_TEMPORALES.items():
        # pbkdf2 con pocas iteraciones: solo para que las pruebas sean rápidas
        db.ejecutar("UPDATE usuarios SET contrasena_hash = %s WHERE usuario = %s",
                    (generate_password_hash(clave, method="pbkdf2:sha256:1000"), usuario))
    seguridad.limitador_login.limpiar()
    seguridad.limitador_pedidos.limpiar()
    seguridad.limitador_llamados.limpiar()
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
def como(app):
    """
    Devuelve un cliente con sesión iniciada como 'admin', 'chef' o 'mesero'
    (ya con la contraseña temporal cambiada).
    """
    def _como(usuario):
        db.ejecutar("UPDATE usuarios SET debe_cambiar_clave = 0 WHERE usuario = %s", (usuario,))
        c = app.test_client()
        r = c.post("/api/auth/login", json={"usuario": usuario, "password": CLAVES_TEMPORALES[usuario]})
        assert r.status_code == 200, r.get_json()
        return c
    return _como


@pytest.fixture
def admin(como):
    return como("admin")


def codigo_mesa(numero):
    """Código secreto del QR de una mesa (None si la mesa no existe)."""
    fila = db.consultar_uno("SELECT codigo_qr FROM mesas WHERE numero_mesa = %s", (numero,))
    return fila["codigo_qr"] if fila else None


@pytest.fixture
def crear_pedido(cliente):
    """Crea un pedido (con el código QR correcto) y devuelve la respuesta JSON."""
    def _crear(mesa=5, items=None, **extra):
        cuerpo = {"mesa": mesa, "codigo": codigo_mesa(mesa),
                  "items": items or [{"id": 1, "cantidad": 1}], **extra}
        r = cliente.post("/api/pedidos", json=cuerpo)
        assert r.status_code == 201, r.get_json()
        return r.get_json()
    return _crear
