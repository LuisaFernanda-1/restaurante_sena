"""
admin_api.py — Endpoints del panel de administración

Categorías, mesas, usuarios del personal y cupones. Todos exigen el rol
Administrador. Lo que tiene historial (ventas, pedidos) no se borra:
se desactiva, para no perder los reportes.
"""

import logging
import re
import secrets

from flask import Blueprint

import db
import seguridad
from errores import ErrorAPI
from seguridad import ROL_ADMIN, requiere_rol, usuario_actual
from validacion import cuerpo_json, jresp, v_bool, v_correo, v_entero, v_fecha, v_texto

log = logging.getLogger("restaurante.admin")
bp = Blueprint("admin", __name__)

ESTADOS_MESA = ("disponible", "ocupada", "reservada", "inactiva")


def _existe(sql, params):
    return db.consultar_uno(sql, params) is not None


def _actualizar(tabla, col_id, id_valor, campos):
    """UPDATE con columnas de una lista fija (nunca datos del usuario como nombres)."""
    if not campos:
        raise ErrorAPI("Nada que actualizar.")
    asignaciones = ", ".join(f"{c} = %s" for c in campos)
    db.ejecutar(f"UPDATE {tabla} SET {asignaciones} WHERE {col_id} = %s", [*campos.values(), id_valor])


# ============================================================
# CATEGORÍAS
# POST   /api/categorias
# PUT    /api/categorias/<id>
# DELETE /api/categorias/<id>
# ============================================================
def _validar_categoria(data, parcial=False):
    campos = {}
    if not parcial or "nombre_categoria" in data:
        campos["nombre_categoria"] = v_texto(data.get("nombre_categoria"), "Nombre", 80, obligatorio=True)
    if "descripcion" in data:
        campos["descripcion"] = v_texto(data.get("descripcion"), "Descripción", 200) or None
    if "orden" in data:
        campos["orden"] = v_entero(data.get("orden"), "Orden", 0, 999)
    if "activo" in data:
        campos["activo"] = 1 if v_bool(data.get("activo"), "Activa") else 0
    return campos


@bp.route("/api/categorias", methods=["POST"])
@requiere_rol(ROL_ADMIN)
def crear_categoria():
    campos = _validar_categoria(cuerpo_json())
    try:
        _, nuevo = db.ejecutar(
            f"INSERT INTO categorias ({', '.join(campos)}) VALUES ({', '.join(['%s'] * len(campos))})",
            list(campos.values()))
    except db.DBDuplicado:
        raise ErrorAPI("Ya existe una categoría con ese nombre.", 409)
    return jresp({"ok": True, "id_categoria": nuevo, "msg": "Categoría creada"}, 201)


@bp.route("/api/categorias/<int:cid>", methods=["PUT"])
@requiere_rol(ROL_ADMIN)
def editar_categoria(cid):
    if not _existe("SELECT 1 AS ok FROM categorias WHERE id_categoria = %s", (cid,)):
        raise ErrorAPI("Categoría no encontrada.", 404)
    try:
        _actualizar("categorias", "id_categoria", cid, _validar_categoria(cuerpo_json(), parcial=True))
    except db.DBDuplicado:
        raise ErrorAPI("Ya existe una categoría con ese nombre.", 409)
    return jresp({"ok": True, "msg": "Categoría actualizada"})


@bp.route("/api/categorias/<int:cid>", methods=["DELETE"])
@requiere_rol(ROL_ADMIN)
def eliminar_categoria(cid):
    if not _existe("SELECT 1 AS ok FROM categorias WHERE id_categoria = %s", (cid,)):
        raise ErrorAPI("Categoría no encontrada.", 404)
    activos = db.consultar_uno(
        "SELECT COUNT(*) AS n FROM productos WHERE id_categoria = %s AND activo = 1", (cid,))["n"]
    if activos:
        raise ErrorAPI(f"La categoría tiene {activos} producto(s) en la carta. Muévalos a otra "
                       "categoría o elimínelos primero, o desactive la categoría.", 409)
    if _existe("SELECT 1 AS ok FROM productos WHERE id_categoria = %s LIMIT 1", (cid,)):
        # Tiene productos antiguos con ventas: se desactiva en vez de borrar.
        db.ejecutar("UPDATE categorias SET activo = 0 WHERE id_categoria = %s", (cid,))
        return jresp({"ok": True, "msg": "La categoría tiene historial de ventas: se desactivó."})
    db.ejecutar("DELETE FROM categorias WHERE id_categoria = %s", (cid,))
    return jresp({"ok": True, "msg": "Categoría eliminada"})


# ============================================================
# MESAS
# POST   /api/mesas
# PUT    /api/mesas/<id>
# DELETE /api/mesas/<id>
# ============================================================
def _validar_mesa(data, parcial=False):
    campos = {}
    if not parcial or "numero_mesa" in data:
        campos["numero_mesa"] = v_entero(data.get("numero_mesa"), "Número de mesa", 1, 999)
    if not parcial or "capacidad" in data:
        campos["capacidad"] = v_entero(data.get("capacidad", 4), "Capacidad", 1, 50)
    if "estado" in data:
        if data["estado"] not in ESTADOS_MESA:
            raise ErrorAPI("Estado de mesa inválido.")
        campos["estado"] = data["estado"]
    return campos


@bp.route("/api/mesas", methods=["POST"])
@requiere_rol(ROL_ADMIN)
def crear_mesa():
    campos = _validar_mesa(cuerpo_json())
    campos["codigo_qr"] = secrets.token_hex(5)
    try:
        _, nuevo = db.ejecutar(
            f"INSERT INTO mesas ({', '.join(campos)}) VALUES ({', '.join(['%s'] * len(campos))})",
            list(campos.values()))
    except db.DBDuplicado:
        raise ErrorAPI(f"Ya existe la mesa {campos['numero_mesa']}.", 409)
    return jresp({"ok": True, "id_mesa": nuevo, "msg": f"Mesa {campos['numero_mesa']} creada"}, 201)


@bp.route("/api/mesas/<int:mid>", methods=["PUT"])
@requiere_rol(ROL_ADMIN)
def editar_mesa(mid):
    if not _existe("SELECT 1 AS ok FROM mesas WHERE id_mesa = %s", (mid,)):
        raise ErrorAPI("Mesa no encontrada.", 404)
    campos = _validar_mesa(cuerpo_json(), parcial=True)
    try:
        _actualizar("mesas", "id_mesa", mid, campos)
    except db.DBDuplicado:
        raise ErrorAPI(f"Ya existe la mesa {campos.get('numero_mesa')}.", 409)
    return jresp({"ok": True, "msg": "Mesa actualizada"})


@bp.route("/api/mesas/<int:mid>", methods=["DELETE"])
@requiere_rol(ROL_ADMIN)
def eliminar_mesa(mid):
    if not _existe("SELECT 1 AS ok FROM mesas WHERE id_mesa = %s", (mid,)):
        raise ErrorAPI("Mesa no encontrada.", 404)
    if (_existe("SELECT 1 AS ok FROM pedidos WHERE id_mesa = %s LIMIT 1", (mid,))
            or _existe("SELECT 1 AS ok FROM llamados WHERE id_mesa = %s LIMIT 1", (mid,))):
        raise ErrorAPI("La mesa tiene pedidos registrados y no se puede eliminar. "
                       "Márquela como «inactiva» para que no reciba pedidos.", 409)
    db.ejecutar("DELETE FROM mesas WHERE id_mesa = %s", (mid,))
    return jresp({"ok": True, "msg": "Mesa eliminada"})


# ============================================================
# USUARIOS DEL PERSONAL
# GET  /api/roles
# GET  /api/usuarios
# POST /api/usuarios                         → crea con contraseña temporal
# PUT  /api/usuarios/<id>
# POST /api/usuarios/<id>/restablecer-clave  → nueva contraseña temporal
# ============================================================
_RE_USUARIO = re.compile(r"^[a-z0-9._-]{3,50}$")


@bp.route("/api/roles", methods=["GET"])
@requiere_rol(ROL_ADMIN)
def get_roles():
    return jresp(db.consultar(
        "SELECT id_rol, nombre_rol, descripcion FROM roles "
        "WHERE nombre_rol IN ('Administrador', 'Chef', 'Mesero') ORDER BY id_rol"))


@bp.route("/api/usuarios", methods=["GET"])
@requiere_rol(ROL_ADMIN)
def get_usuarios():
    return jresp(db.consultar(
        """SELECT u.id_usuario, u.nombre, u.usuario, u.correo, u.id_rol, r.nombre_rol AS rol,
                  u.activo, u.debe_cambiar_clave, u.ultimo_ingreso, u.fecha_creacion
           FROM usuarios u JOIN roles r ON u.id_rol = r.id_rol
           ORDER BY u.activo DESC, r.id_rol, u.nombre"""))


def _rol_valido(id_rol):
    fila = db.consultar_uno(
        "SELECT nombre_rol FROM roles WHERE id_rol = %s AND nombre_rol IN ('Administrador', 'Chef', 'Mesero')",
        (id_rol,))
    if not fila:
        raise ErrorAPI("Rol inválido.")
    return fila["nombre_rol"]


@bp.route("/api/usuarios", methods=["POST"])
@requiere_rol(ROL_ADMIN)
def crear_usuario():
    data = cuerpo_json()
    nombre = v_texto(data.get("nombre"), "Nombre", 100, obligatorio=True)
    usuario = v_texto(data.get("usuario"), "Usuario", 50, obligatorio=True).lower()
    if not _RE_USUARIO.match(usuario):
        raise ErrorAPI("Usuario: entre 3 y 50 caracteres; solo letras minúsculas, números, punto, guion y guion bajo.")
    correo = v_correo(data.get("correo"))
    id_rol = v_entero(data.get("id_rol"), "Rol", 1)
    _rol_valido(id_rol)
    clave = seguridad.generar_clave_temporal()
    try:
        _, nuevo = db.ejecutar(
            """INSERT INTO usuarios (id_rol, nombre, usuario, correo, contrasena_hash, debe_cambiar_clave)
               VALUES (%s, %s, %s, %s, %s, 1)""",
            (id_rol, nombre, usuario, correo, seguridad.crear_hash(clave)))
    except db.DBDuplicado:
        raise ErrorAPI("Ya existe un usuario con ese nombre de usuario o correo.", 409)
    log.info("Usuario '%s' creado por '%s'", usuario, usuario_actual()["usuario"])
    return jresp({"ok": True, "id_usuario": nuevo, "usuario": usuario, "clave_temporal": clave,
                  "msg": "Usuario creado. Entréguele la contraseña temporal: deberá cambiarla al ingresar."}, 201)


def _admins_activos(excepto=None):
    return db.consultar_uno(
        """SELECT COUNT(*) AS n FROM usuarios u JOIN roles r ON u.id_rol = r.id_rol
           WHERE r.nombre_rol = 'Administrador' AND u.activo = 1 AND u.id_usuario <> %s""",
        (excepto or 0,))["n"]


@bp.route("/api/usuarios/<int:uid>", methods=["PUT"])
@requiere_rol(ROL_ADMIN)
def editar_usuario(uid):
    actual = db.consultar_uno(
        """SELECT u.id_usuario, u.activo, r.nombre_rol AS rol FROM usuarios u
           JOIN roles r ON u.id_rol = r.id_rol WHERE u.id_usuario = %s""", (uid,))
    if not actual:
        raise ErrorAPI("Usuario no encontrado.", 404)
    data = cuerpo_json()
    campos = {}
    if "nombre" in data:
        campos["nombre"] = v_texto(data.get("nombre"), "Nombre", 100, obligatorio=True)
    if "correo" in data:
        campos["correo"] = v_correo(data.get("correo"))
    nuevo_rol = actual["rol"]
    if "id_rol" in data:
        campos["id_rol"] = v_entero(data.get("id_rol"), "Rol", 1)
        nuevo_rol = _rol_valido(campos["id_rol"])
    nuevo_activo = actual["activo"]
    if "activo" in data:
        nuevo_activo = 1 if v_bool(data.get("activo"), "Activo") else 0
        campos["activo"] = nuevo_activo

    yo = usuario_actual()["id_usuario"]
    if uid == yo and (not nuevo_activo or nuevo_rol != ROL_ADMIN):
        raise ErrorAPI("No puede desactivarse ni quitarse el rol de administrador a sí mismo.", 409)
    deja_de_ser_admin = actual["rol"] == ROL_ADMIN and actual["activo"] and (not nuevo_activo or nuevo_rol != ROL_ADMIN)
    if deja_de_ser_admin and _admins_activos(excepto=uid) == 0:
        raise ErrorAPI("Debe quedar al menos un administrador activo.", 409)
    try:
        _actualizar("usuarios", "id_usuario", uid, campos)
    except db.DBDuplicado:
        raise ErrorAPI("Ya existe un usuario con ese correo.", 409)
    # Si se desactivó, su sesión abierta deja de valer en la siguiente
    # petición (seguridad.usuario_actual revisa "activo" cada vez); si
    # cambió el rol, los permisos nuevos aplican de inmediato.
    return jresp({"ok": True, "msg": "Usuario actualizado"})


@bp.route("/api/usuarios/<int:uid>/restablecer-clave", methods=["POST"])
@requiere_rol(ROL_ADMIN)
def restablecer_clave(uid):
    if uid == usuario_actual()["id_usuario"]:
        raise ErrorAPI("Para cambiar su propia contraseña use «Cambiar contraseña».", 409)
    if not _existe("SELECT 1 AS ok FROM usuarios WHERE id_usuario = %s", (uid,)):
        raise ErrorAPI("Usuario no encontrado.", 404)
    clave = seguridad.generar_clave_temporal()
    # Al cambiar el hash, las sesiones abiertas de ese usuario se cierran.
    db.ejecutar("UPDATE usuarios SET contrasena_hash = %s, debe_cambiar_clave = 1 WHERE id_usuario = %s",
                (seguridad.crear_hash(clave), uid))
    seguridad.limitador_login.limpiar()
    log.info("Contraseña del usuario %s restablecida por '%s'", uid, usuario_actual()["usuario"])
    return jresp({"ok": True, "clave_temporal": clave,
                  "msg": "Contraseña restablecida. Entréguele la nueva contraseña temporal."})


# ============================================================
# CUPONES
# GET    /api/cupones
# POST   /api/cupones
# PUT    /api/cupones/<id>
# DELETE /api/cupones/<id>
# ============================================================
_RE_CUPON = re.compile(r"^[A-Z0-9_-]{3,20}$")


def _validar_cupon(data, parcial=False):
    campos = {}
    if not parcial or "codigo" in data:
        codigo = v_texto(data.get("codigo"), "Código", 20, obligatorio=True).upper()
        if not _RE_CUPON.match(codigo):
            raise ErrorAPI("Código: de 3 a 20 caracteres; solo letras, números, guion y guion bajo.")
        campos["codigo"] = codigo
    if not parcial or "descuento" in data:
        campos["descuento"] = v_entero(data.get("descuento"), "Descuento (%)", 1, 100)
    if "fecha_fin" in data:
        campos["fecha_fin"] = v_fecha(data.get("fecha_fin"), "Válido hasta")
    if "activo" in data:
        campos["activo"] = 1 if v_bool(data.get("activo"), "Activo") else 0
    return campos


@bp.route("/api/cupones", methods=["GET"])
@requiere_rol(ROL_ADMIN)
def get_cupones():
    return jresp(db.consultar(
        """SELECT c.id_cupon, c.codigo, c.descuento, c.activo, c.fecha_fin,
                  (c.fecha_fin IS NOT NULL AND c.fecha_fin < CURDATE()) AS vencido,
                  COUNT(p.id_pedido) AS usos
           FROM cupones c LEFT JOIN pedidos p ON p.id_cupon = c.id_cupon AND p.estado <> 'cancelado'
           GROUP BY c.id_cupon, c.codigo, c.descuento, c.activo, c.fecha_fin
           ORDER BY c.activo DESC, c.codigo"""))


@bp.route("/api/cupones", methods=["POST"])
@requiere_rol(ROL_ADMIN)
def crear_cupon():
    campos = _validar_cupon(cuerpo_json())
    try:
        _, nuevo = db.ejecutar(
            f"INSERT INTO cupones ({', '.join(campos)}) VALUES ({', '.join(['%s'] * len(campos))})",
            list(campos.values()))
    except db.DBDuplicado:
        raise ErrorAPI("Ya existe un cupón con ese código.", 409)
    return jresp({"ok": True, "id_cupon": nuevo, "msg": f"Cupón {campos['codigo']} creado"}, 201)


@bp.route("/api/cupones/<int:cid>", methods=["PUT"])
@requiere_rol(ROL_ADMIN)
def editar_cupon(cid):
    if not _existe("SELECT 1 AS ok FROM cupones WHERE id_cupon = %s", (cid,)):
        raise ErrorAPI("Cupón no encontrado.", 404)
    try:
        _actualizar("cupones", "id_cupon", cid, _validar_cupon(cuerpo_json(), parcial=True))
    except db.DBDuplicado:
        raise ErrorAPI("Ya existe un cupón con ese código.", 409)
    return jresp({"ok": True, "msg": "Cupón actualizado"})


@bp.route("/api/cupones/<int:cid>", methods=["DELETE"])
@requiere_rol(ROL_ADMIN)
def eliminar_cupon(cid):
    if not _existe("SELECT 1 AS ok FROM cupones WHERE id_cupon = %s", (cid,)):
        raise ErrorAPI("Cupón no encontrado.", 404)
    if _existe("SELECT 1 AS ok FROM pedidos WHERE id_cupon = %s LIMIT 1", (cid,)):
        db.ejecutar("UPDATE cupones SET activo = 0 WHERE id_cupon = %s", (cid,))
        return jresp({"ok": True, "msg": "El cupón ya se usó en pedidos: se desactivó en lugar de borrarlo."})
    db.ejecutar("DELETE FROM cupones WHERE id_cupon = %s", (cid,))
    return jresp({"ok": True, "msg": "Cupón eliminado"})
