"""
Prueba del script de migración: parte del esquema ORIGINAL del proyecto
(tests/datos/esquema_v1_original.sql), lo migra y verifica que queda
igual que una instalación nueva y que los datos se conservan.
"""

import mysql.connector
import pytest

import config
import db
from conftest import NOMBRE_BD_PRUEBAS, borrar_bd, cargar_script
from migrar import Migrador

BD_MIG = NOMBRE_BD_PRUEBAS.replace("_test", "_mig_test")
BD_NUEVA = NOMBRE_BD_PRUEBAS


def conectar(nombre):
    params = db.parametros_conexion(database=False)
    params["database"] = nombre
    return mysql.connector.connect(**params)


def esquema(nombre):
    conn = conectar(nombre)
    cur = conn.cursor()
    cur.execute("""SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE
                   FROM information_schema.COLUMNS
                   WHERE TABLE_SCHEMA = %s AND TABLE_NAME <> 'carritos'""", (nombre,))
    columnas = set(cur.fetchall())
    cur.execute("""SELECT TABLE_NAME, INDEX_NAME FROM information_schema.STATISTICS
                   WHERE TABLE_SCHEMA = %s AND TABLE_NAME <> 'carritos'
                     AND INDEX_NAME NOT LIKE 'fk\\_%%'""", (nombre,))
    indices = set(cur.fetchall())
    conn.close()
    return columnas, indices


@pytest.fixture
def bd_antigua(monkeypatch):
    cargar_script(config.BACKEND_DIR / "tests" / "datos" / "esquema_v1_original.sql", BD_MIG)
    monkeypatch.setattr(config, "DB_NAME", BD_MIG)
    yield BD_MIG
    borrar_bd(BD_MIG)


def migrar(nombre):
    conn = conectar(nombre)
    m = Migrador(conn)
    m.ejecutar()
    conn.close()
    return m.cambios


def test_migracion_desde_version_original(bd, bd_antigua):
    assert migrar(bd_antigua) > 0
    assert esquema(bd_antigua) == esquema(BD_NUEVA)

    conn = conectar(bd_antigua)
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT usuario, debe_cambiar_clave FROM usuarios ORDER BY id_usuario")
    assert cur.fetchall() == [
        {"usuario": "admin", "debe_cambiar_clave": 1},
        {"usuario": "chef", "debe_cambiar_clave": 1},
        {"usuario": "mesero", "debe_cambiar_clave": 1},
    ]
    cur.execute("SELECT COUNT(*) AS n FROM pedidos WHERE token IS NULL OR total = 0")
    assert cur.fetchone()["n"] == 0
    cur.execute("SELECT subtotal, impuesto, propina, total FROM pedidos WHERE id_pedido = 1")
    assert cur.fetchone() == {"subtotal": 43500, "impuesto": 8265, "propina": 4350, "total": 56115}
    cur.execute("SELECT impuesto_nombre FROM facturas WHERE id_pedido = 1")
    assert cur.fetchone()["impuesto_nombre"] == "IVA"
    cur.execute("SELECT COUNT(*) AS n FROM mesas WHERE codigo_qr LIKE 'QR-MESA-%' OR codigo_qr IS NULL")
    assert cur.fetchone()["n"] == 0
    cur.execute("SELECT nombre FROM productos WHERE id_producto = 3")
    assert cur.fetchone()["nombre"] == "Ceviche de Camarón"
    conn.close()


def test_migracion_se_puede_repetir(bd, bd_antigua):
    migrar(bd_antigua)
    assert migrar(bd_antigua) == 0
