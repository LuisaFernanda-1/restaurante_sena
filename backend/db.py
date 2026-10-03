"""
db.py — Acceso a MySQL / MariaDB para Restaurante SENA

- Usa un pool de conexiones (Waitress atiende varias peticiones a la vez).
- Todas las consultas son parametrizadas (%s); nunca se arma SQL con
  datos del usuario.
- Los errores NO se esconden: se lanzan como DBError y la aplicación
  responde con un mensaje claro.
"""

import logging
import threading
from contextlib import contextmanager

import mysql.connector
from mysql.connector import errorcode, pooling

import config

log = logging.getLogger("restaurante.db")

_pool = None
_pool_lock = threading.Lock()


class DBError(Exception):
    """Error de base de datos (conexión, sintaxis, restricciones...)."""

    def __init__(self, mensaje, original=None):
        super().__init__(mensaje)
        self.original = original
        self.errno = getattr(original, "errno", None)


class DBDuplicado(DBError):
    """Se violó una clave única (p. ej. dos productos con el mismo código)."""


class DBReferencia(DBError):
    """Se violó una llave foránea (p. ej. borrar algo que está en uso)."""


def parametros_conexion(database=True):
    params = {
        "host": config.DB_HOST,
        "port": config.DB_PORT,
        "user": config.DB_USER,
        "password": config.DB_PASSWORD,
        "charset": "utf8mb4",
        # MariaDB no conoce la intercalación por defecto de MySQL 8
        # (utf8mb4_0900_ai_ci); se fija una que existe en ambos.
        "collation": "utf8mb4_unicode_ci",
        "autocommit": False,
        "connection_timeout": 10,
    }
    if database:
        params["database"] = config.DB_NAME
    return params


def _obtener_pool():
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = pooling.MySQLConnectionPool(
                    pool_name="restaurante",
                    pool_size=10,
                    pool_reset_session=True,
                    **parametros_conexion(),
                )
    return _pool


def _traducir(e):
    if isinstance(e, DBError):
        return e
    errno = getattr(e, "errno", None)
    if errno == errorcode.ER_DUP_ENTRY:
        return DBDuplicado("Ya existe un registro con ese valor.", e)
    if errno in (errorcode.ER_ROW_IS_REFERENCED_2, errorcode.ER_ROW_IS_REFERENCED,
                 errorcode.ER_NO_REFERENCED_ROW_2, errorcode.ER_NO_REFERENCED_ROW):
        return DBReferencia("El registro está relacionado con otros datos.", e)
    return DBError(f"Error de base de datos: {e}", e)


@contextmanager
def conexion():
    """Entrega una conexión del pool y la devuelve al terminar."""
    try:
        conn = _obtener_pool().get_connection()
        # Si MySQL cerró la conexión por inactividad, reconecta.
        conn.ping(reconnect=True, attempts=2, delay=0)
    except mysql.connector.Error as e:
        log.error("No se pudo conectar a MySQL: %s", e)
        raise DBError("No hay conexión con la base de datos.", e)
    try:
        yield conn
    finally:
        try:
            conn.close()
        except mysql.connector.Error:
            pass


@contextmanager
def transaccion():
    """
    Ejecuta varias sentencias como una sola unidad:
    si algo falla se deshace todo (rollback).

        with transaccion() as cur:
            cur.execute("INSERT ...", (...))
            cur.execute("UPDATE ...", (...))
    """
    with conexion() as conn:
        cur = conn.cursor(dictionary=True)
        try:
            yield cur
            conn.commit()
        except mysql.connector.Error as e:
            conn.rollback()
            log.error("Error SQL: %s", e)
            raise _traducir(e)
        except BaseException:
            conn.rollback()
            raise
        finally:
            cur.close()


def consultar(sql, params=()):
    """SELECT que devuelve una lista de diccionarios."""
    with transaccion() as cur:
        cur.execute(sql, tuple(params))
        return cur.fetchall()


def consultar_uno(sql, params=()):
    """SELECT que devuelve un diccionario o None."""
    with transaccion() as cur:
        cur.execute(sql, tuple(params))
        filas = cur.fetchall()
        return filas[0] if filas else None


def ejecutar(sql, params=()):
    """INSERT/UPDATE/DELETE. Devuelve (filas_afectadas, id_insertado)."""
    with transaccion() as cur:
        cur.execute(sql, tuple(params))
        return cur.rowcount, cur.lastrowid


def probar_conexion():
    try:
        consultar_uno("SELECT 1 AS ok")
        return True
    except DBError:
        return False


def reiniciar_pool():
    """Descarta el pool (lo usan las pruebas al cambiar de base de datos)."""
    global _pool
    with _pool_lock:
        _pool = None


# ------------------------------------------------------------
# Ejecución de scripts .sql (instalación, migración y pruebas)
# ------------------------------------------------------------
def dividir_sql(texto):
    """Divide un script en sentencias, respetando comillas y comentarios."""
    sentencias, actual = [], []
    i, n = 0, len(texto)
    comilla = None
    while i < n:
        c = texto[i]
        if comilla:
            actual.append(c)
            if c == "\\" and i + 1 < n:
                actual.append(texto[i + 1])
                i += 2
                continue
            if c == comilla:
                comilla = None
        elif c in ("'", '"', "`"):
            comilla = c
            actual.append(c)
        elif c == "-" and texto.startswith("--", i):
            fin = texto.find("\n", i)
            i = n if fin == -1 else fin
            continue
        elif c == "#":
            fin = texto.find("\n", i)
            i = n if fin == -1 else fin
            continue
        elif c == "/" and texto.startswith("/*", i):
            fin = texto.find("*/", i + 2)
            i = n if fin == -1 else fin + 2
            continue
        elif c == ";":
            sentencia = "".join(actual).strip()
            if sentencia:
                sentencias.append(sentencia)
            actual = []
        else:
            actual.append(c)
        i += 1
    sentencia = "".join(actual).strip()
    if sentencia:
        sentencias.append(sentencia)
    return sentencias


def ejecutar_script(cursor, texto):
    for sentencia in dividir_sql(texto):
        cursor.execute(sentencia)
        if cursor.with_rows:
            cursor.fetchall()
