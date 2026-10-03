"""
app.py — Backend Flask para Restaurante SENA

Sirve la API (/api/...) y también el frontend (HTML, CSS y JS), de modo
que todo el sistema funciona en una sola dirección: http://IP:8000

Desarrollo:   python app.py
Producción:   scripts/iniciar_servidor.ps1  (Waitress)
"""

import hmac
import logging
import re
import secrets
from datetime import date, datetime, timedelta
from decimal import Decimal
from urllib.parse import urlsplit

from flask import Flask, abort, request, send_from_directory, session
from flask.json.provider import DefaultJSONProvider
from werkzeug.exceptions import HTTPException

import config
import db
import seguridad
from db import DBDuplicado, DBError, DBReferencia
from dinero import calcular_totales
from errores import ErrorAPI
from seguridad import ROL_ADMIN, ROL_CHEF, ROL_MESERO, requiere_rol, usuario_actual
from validacion import arg_entero, cuerpo_json, jresp, v_bool, v_entero, v_texto

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
log = logging.getLogger("restaurante")


# ============================================================
# JSON: convierte Decimal y fechas (MySQL devuelve SUM() como Decimal)
# ============================================================
class JSONRestaurante(DefaultJSONProvider):
    ensure_ascii = False
    sort_keys = False

    @staticmethod
    def default(o):
        if isinstance(o, Decimal):
            return int(o) if o == o.to_integral_value() else float(o)
        if isinstance(o, datetime):
            return o.isoformat(timespec="seconds")
        if isinstance(o, date):
            return o.isoformat()
        return DefaultJSONProvider.default(o)


app = Flask(__name__, static_folder=None)
app.json_provider_class = JSONRestaurante
app.json = JSONRestaurante(app)
app.config.update(
    SECRET_KEY=config.SECRET_KEY,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=config.COOKIE_SEGURA,
    SESSION_COOKIE_NAME="restaurante_sesion",
    PERMANENT_SESSION_LIFETIME=timedelta(seconds=seguridad.DURACION_SESION_RECORDADA),
    MAX_CONTENT_LENGTH=1024 * 1024,  # 1 MB por petición es más que suficiente
)

# Panel de administración: categorías, mesas, usuarios y cupones
from admin_api import bp as admin_bp  # noqa: E402
app.register_blueprint(admin_bp)

# Códigos QR de las mesas y verificación de comprobantes
from qr_api import bp as qr_bp  # noqa: E402
app.register_blueprint(qr_bp)


# ============================================================
# ERRORES
# ============================================================
@app.errorhandler(ErrorAPI)
def _error_api(e):
    cuerpo = {"ok": False, "msg": e.msg}
    if e.codigo:
        cuerpo["codigo"] = e.codigo
    return jresp(cuerpo, e.status)


@app.errorhandler(DBDuplicado)
def _error_duplicado(e):
    return jresp({"ok": False, "msg": "Ya existe un registro con ese valor."}, 409)


@app.errorhandler(DBReferencia)
def _error_referencia(e):
    return jresp({"ok": False, "msg": "No se puede completar: el registro está relacionado con otros datos."}, 409)


@app.errorhandler(DBError)
def _error_db(e):
    log.error("Error de base de datos: %s", e)
    return jresp({"ok": False, "msg": "Error de base de datos. Intente de nuevo o avise al administrador."}, 503)


@app.errorhandler(HTTPException)
def _error_http(e):
    if request.path.startswith("/api/"):
        mensajes = {
            400: "Petición inválida.",
            401: "Debe iniciar sesión.",
            403: "No tiene permiso para esta acción.",
            404: "Recurso no encontrado.",
            405: "Método no permitido.",
            413: "La petición es demasiado grande.",
        }
        return jresp({"ok": False, "msg": mensajes.get(e.code, e.name)}, e.code)
    return e


@app.errorhandler(Exception)
def _error_inesperado(e):
    log.exception("Error inesperado en %s %s", request.method, request.path)
    return jresp({"ok": False, "msg": "Error interno del servidor."}, 500)


# ============================================================
# PROTECCIONES GENERALES
# ============================================================
@app.before_request
def _proteger_peticiones():
    """
    Protección CSRF: una página de OTRO sitio no puede enviar peticiones
    que modifiquen datos usando la sesión del personal. Los navegadores
    siempre envían la cabecera Origin en POST/PUT/DELETE entre sitios.
    """
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and request.path.startswith("/api/"):
        origen = request.headers.get("Origin")
        if origen and urlsplit(origen).netloc != request.host:
            raise ErrorAPI("Origen de la petición no permitido.", 403, "origen")


@app.after_request
def _cabeceras_seguridad(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    if request.path.startswith("/api/"):
        resp.headers.setdefault("Cache-Control", "no-store")
    return resp


# ============================================================
# ESTADO DE LA API Y CONFIGURACIÓN PÚBLICA
# ============================================================
@app.route("/api/status", methods=["GET"])
def status():
    if db.probar_conexion():
        return jresp({"ok": True, "msg": "Conectado a la base de datos", "db": config.DB_NAME})
    return jresp({"ok": False, "msg": "Sin conexión a la base de datos"}, 503)


@app.route("/api/config", methods=["GET"])
def config_publica():
    """Datos que el frontend necesita para mostrar precios y la factura."""
    return jresp({
        "restaurante": config.RESTAURANTE_NOMBRE,
        "nit": config.RESTAURANTE_NIT,
        "direccion": config.RESTAURANTE_DIRECCION,
        "impuesto_nombre": config.IMPUESTO_NOMBRE,
        "impuesto_pct": config.IMPUESTO_PCT,
        "propina_pct": config.PROPINA_SUGERIDA_PCT,
        "server_url": config.SERVER_URL,
        # Hora del servidor: las pantallas del personal calculan los minutos
        # de espera con ella, sin depender del reloj de cada dispositivo.
        "ahora": datetime.now().isoformat(timespec="seconds"),
    })


# ============================================================
# AUTENTICACIÓN
# POST /api/auth/login    → inicia sesión con usuario/contraseña
# POST /api/auth/logout   → cierra sesión
# GET  /api/auth/me       → usuario de la sesión actual
# POST /api/auth/cambiar-clave → cambia la contraseña propia
# ============================================================
@app.route("/api/auth/login", methods=["POST"])
def login():
    data = cuerpo_json()
    usuario = v_texto(data.get("usuario"), "Usuario", 150).lower()
    password = data.get("password") or ""
    if not usuario or not isinstance(password, str) or not password:
        raise ErrorAPI("Usuario y contraseña son obligatorios.")

    clave_limite = f"{request.remote_addr}|{usuario}"
    minutos = seguridad.limitador_login.bloqueado(clave_limite)
    if minutos:
        raise ErrorAPI(f"Demasiados intentos fallidos. Intente de nuevo en {minutos} minutos.", 429)

    row = db.consultar_uno(
        """SELECT u.id_usuario, u.nombre, u.usuario, u.contrasena_hash,
                  u.debe_cambiar_clave, r.nombre_rol AS rol
           FROM usuarios u JOIN roles r ON u.id_rol = r.id_rol
           WHERE (u.usuario = %s OR u.correo = %s) AND u.activo = 1""",
        (usuario, usuario),
    )
    correcta, actualizar = seguridad.verificar_clave(row["contrasena_hash"] if row else None, password)
    if not row or not correcta:
        seguridad.limitador_login.fallo(clave_limite)
        log.warning("Inicio de sesión fallido para '%s' desde %s", usuario, request.remote_addr)
        raise ErrorAPI("Usuario o contraseña incorrectos.", 401)
    seguridad.limitador_login.limpiar(clave_limite)

    if actualizar:
        # Contraseña con el hash antiguo (SHA-256 sin sal): se reemplaza
        # por un hash seguro ahora que conocemos la contraseña.
        row["contrasena_hash"] = seguridad.crear_hash(password)
        db.ejecutar("UPDATE usuarios SET contrasena_hash = %s WHERE id_usuario = %s",
                    (row["contrasena_hash"], row["id_usuario"]))
        log.info("Hash de contraseña actualizado al formato seguro para '%s'", row["usuario"])

    db.ejecutar("UPDATE usuarios SET ultimo_ingreso = NOW() WHERE id_usuario = %s", (row["id_usuario"],))
    seguridad.iniciar_sesion(row, recordar=data.get("recordar") is True)
    return jresp({"ok": True, "user": seguridad.datos_publicos(row)})


@app.route("/api/auth/logout", methods=["POST"])
def logout():
    session.clear()
    return jresp({"ok": True})


@app.route("/api/auth/me", methods=["GET"])
def me():
    u = usuario_actual()
    if not u:
        raise ErrorAPI("No autenticado.", 401, "sin_sesion")
    return jresp({"ok": True, "user": seguridad.datos_publicos(u)})


@app.route("/api/auth/cambiar-clave", methods=["POST"])
@requiere_rol(permitir_cambio_pendiente=True)
def cambiar_clave():
    data = cuerpo_json()
    actual = data.get("actual")
    nueva = data.get("nueva")
    u = usuario_actual()
    correcta, _ = seguridad.verificar_clave(u["contrasena_hash"], actual if isinstance(actual, str) else "")
    if not correcta:
        raise ErrorAPI("La contraseña actual no es correcta.")
    seguridad.validar_clave_nueva(nueva, u["usuario"])
    if nueva == actual:
        raise ErrorAPI("La nueva contraseña debe ser diferente a la actual.")
    nuevo_hash = seguridad.crear_hash(nueva)
    db.ejecutar("UPDATE usuarios SET contrasena_hash = %s, debe_cambiar_clave = 0 WHERE id_usuario = %s",
                (nuevo_hash, u["id_usuario"]))
    # Las demás sesiones de este usuario quedan cerradas (cambió la huella
    # de la contraseña); esta se renueva para seguir trabajando.
    u.update(contrasena_hash=nuevo_hash, debe_cambiar_clave=False)
    seguridad.iniciar_sesion(u, recordar=session.permanent)
    log.info("El usuario '%s' cambió su contraseña", u["usuario"])
    return jresp({"ok": True, "msg": "Contraseña actualizada", "user": seguridad.datos_publicos(u)})


# ============================================================
# CATEGORÍAS
# ============================================================
@app.route("/api/categorias", methods=["GET"])
def get_categorias():
    """Carta: solo activas. ?todas=1 (administrador): también las inactivas."""
    if request.args.get("todas") == "1":
        u = usuario_actual()
        if not u or u["rol"] != ROL_ADMIN or u["debe_cambiar_clave"]:
            raise ErrorAPI("No tiene permiso para esta acción.", 403, "sin_permiso")
        return jresp(db.consultar(
            """SELECT c.id_categoria, c.nombre_categoria, c.descripcion, c.orden, c.activo,
                      COUNT(p.id_producto) AS productos
               FROM categorias c
               LEFT JOIN productos p ON p.id_categoria = c.id_categoria AND p.activo = 1
               GROUP BY c.id_categoria, c.nombre_categoria, c.descripcion, c.orden, c.activo
               ORDER BY c.orden, c.nombre_categoria"""
        ))
    rows = db.consultar(
        "SELECT id_categoria, nombre_categoria, descripcion, orden, activo "
        "FROM categorias WHERE activo = 1 ORDER BY orden, nombre_categoria"
    )
    return jresp(rows)


# ============================================================
# PRODUCTOS
# GET    /api/productos              → carta (?cat=&q=&disponible=1)
# GET    /api/productos/<id>         → uno solo
# POST   /api/productos              → crear
# PUT    /api/productos/<id>         → editar
# DELETE /api/productos/<id>         → quitar de la carta (borrado lógico)
# ============================================================
COLUMNAS_PRODUCTO = """
    p.id_producto, p.id_categoria, p.nombre, p.descripcion, p.precio,
    p.emoji, p.disponible, p.imagen_url, c.nombre_categoria AS cat
"""


@app.route("/api/productos", methods=["GET"])
def get_productos():
    cat = request.args.get("cat")
    q = request.args.get("q")
    sql = f"""
        SELECT {COLUMNAS_PRODUCTO}, c.activo AS cat_activa
        FROM productos p
        JOIN categorias c ON p.id_categoria = c.id_categoria
        WHERE p.activo = 1
    """
    # La carta pública no muestra productos de categorías desactivadas;
    # el administrador (?todas=1) los ve todos para poder gestionarlos.
    todas = request.args.get("todas") == "1"
    if todas:
        u = usuario_actual()
        if not u or u["rol"] != ROL_ADMIN or u["debe_cambiar_clave"]:
            raise ErrorAPI("No tiene permiso para esta acción.", 403, "sin_permiso")
    else:
        sql += " AND c.activo = 1"
    params = []
    if cat:
        sql += " AND c.nombre_categoria = %s"
        params.append(cat)
    if q:
        sql += " AND (p.nombre LIKE %s OR p.descripcion LIKE %s)"
        params.extend([f"%{q}%", f"%{q}%"])
    if request.args.get("disponible") == "1":
        sql += " AND p.disponible = 1"
    sql += " ORDER BY c.orden, c.nombre_categoria, p.nombre"
    return jresp(db.consultar(sql, params))


@app.route("/api/productos/<int:pid>", methods=["GET"])
def get_producto(pid):
    row = db.consultar_uno(
        f"""SELECT {COLUMNAS_PRODUCTO} FROM productos p
            JOIN categorias c ON p.id_categoria = c.id_categoria
            WHERE p.id_producto = %s AND p.activo = 1""",
        (pid,),
    )
    if not row:
        raise ErrorAPI("Producto no encontrado.", 404)
    return jresp(row)


def _validar_producto(data, parcial=False):
    campos = {}
    if not parcial or "nombre" in data:
        campos["nombre"] = v_texto(data.get("nombre"), "Nombre", 100, obligatorio=True)
    if "descripcion" in data:
        campos["descripcion"] = v_texto(data.get("descripcion"), "Descripción", 300)
    if not parcial or "precio" in data:
        campos["precio"] = v_entero(data.get("precio"), "Precio", 1, 10_000_000)
    if not parcial or "id_categoria" in data:
        cat_id = v_entero(data.get("id_categoria"), "Categoría", 1)
        if not db.consultar_uno("SELECT 1 AS ok FROM categorias WHERE id_categoria = %s", (cat_id,)):
            raise ErrorAPI("La categoría no existe.")
        campos["id_categoria"] = cat_id
    if "emoji" in data:
        campos["emoji"] = v_texto(data.get("emoji"), "Emoji", 16) or None
    if "imagen_url" in data:
        url = v_texto(data.get("imagen_url"), "Imagen", 255)
        if url and not re.match(r"^(https?://|img/)", url):
            raise ErrorAPI("Imagen: debe ser una dirección http(s):// o una ruta img/...")
        campos["imagen_url"] = url or None
    if "disponible" in data:
        campos["disponible"] = 1 if v_bool(data.get("disponible"), "Disponible") else 0
    return campos


@app.route("/api/productos", methods=["POST"])
@requiere_rol(ROL_ADMIN)
def crear_producto():
    campos = _validar_producto(cuerpo_json())
    columnas = ", ".join(campos)
    marcas = ", ".join(["%s"] * len(campos))
    _, nuevo_id = db.ejecutar(f"INSERT INTO productos ({columnas}) VALUES ({marcas})", list(campos.values()))
    return jresp({"ok": True, "id_producto": nuevo_id, "msg": f"Producto '{campos['nombre']}' creado"}, 201)


@app.route("/api/productos/<int:pid>", methods=["PUT"])
@requiere_rol(ROL_ADMIN)
def editar_producto(pid):
    campos = _validar_producto(cuerpo_json(), parcial=True)
    if not campos:
        raise ErrorAPI("Nada que actualizar.")
    # Los nombres de columna vienen de la lista fija de _validar_producto.
    asignaciones = ", ".join(f"{c} = %s" for c in campos)
    filas, _ = db.ejecutar(
        f"UPDATE productos SET {asignaciones} WHERE id_producto = %s AND activo = 1",
        [*campos.values(), pid],
    )
    if filas == 0 and not db.consultar_uno(
            "SELECT 1 AS ok FROM productos WHERE id_producto = %s AND activo = 1", (pid,)):
        raise ErrorAPI("Producto no encontrado.", 404)
    return jresp({"ok": True, "msg": "Producto actualizado"})


@app.route("/api/productos/<int:pid>", methods=["DELETE"])
@requiere_rol(ROL_ADMIN)
def eliminar_producto(pid):
    # Borrado lógico: el producto sale de la carta pero se conserva en
    # los pedidos y reportes antiguos.
    filas, _ = db.ejecutar(
        "UPDATE productos SET activo = 0, disponible = 0 WHERE id_producto = %s AND activo = 1", (pid,)
    )
    if filas == 0:
        raise ErrorAPI("Producto no encontrado.", 404)
    return jresp({"ok": True, "msg": "Producto eliminado de la carta"})


# ============================================================
# MESAS
# GET  /api/mesas                 → todas (personal)
# GET  /api/mesas/<numero>?c=X    → validar la mesa del QR (comensal)
# PUT  /api/mesas/<id>/estado     → cambiar estado
#
# Cada mesa tiene un código secreto (codigo_qr) que va en su QR:
#   menu.html?mesa=5&c=<código>
# Sin el código correcto no se puede pedir ni llamar al mesero a nombre
# de esa mesa, aunque se cambie el número en la dirección.
# ============================================================
ESTADOS_MESA = ("disponible", "ocupada", "reservada", "inactiva")


def mesa_por_qr(numero, codigo):
    """Devuelve la mesa si el número y el código del QR coinciden."""
    mesa = db.consultar_uno(
        "SELECT id_mesa, numero_mesa, capacidad, estado, codigo_qr FROM mesas WHERE numero_mesa = %s", (numero,)
    )
    if not mesa:
        raise ErrorAPI(f"La mesa {numero} no existe.", 404, "mesa_no_existe")
    if not isinstance(codigo, str) or not codigo or not mesa["codigo_qr"] \
            or not hmac.compare_digest(codigo.strip().lower(), mesa["codigo_qr"]):
        raise ErrorAPI("El código QR de la mesa no es válido. Escanee de nuevo el QR que está en su mesa.",
                       403, "qr_invalido")
    return mesa


@app.route("/api/mesas", methods=["GET"])
@requiere_rol()
def get_mesas():
    estado = request.args.get("estado")
    columnas = "id_mesa, numero_mesa, capacidad, estado"
    if usuario_actual()["rol"] == ROL_ADMIN:
        columnas += ", codigo_qr"          # solo el admin necesita los códigos (QR)
    sql = f"SELECT {columnas} FROM mesas"
    params = []
    if estado:
        if estado not in ESTADOS_MESA:
            raise ErrorAPI("Estado de mesa inválido.")
        sql += " WHERE estado = %s"
        params.append(estado)
    sql += " ORDER BY numero_mesa"
    return jresp(db.consultar(sql, params))


@app.route("/api/mesas/<int:numero>", methods=["GET"])
def get_mesa(numero):
    mesa = mesa_por_qr(numero, request.args.get("c"))
    return jresp({
        "numero_mesa": mesa["numero_mesa"],
        "capacidad": mesa["capacidad"],
        "estado": mesa["estado"],
        "activa": mesa["estado"] != "inactiva",
    })


@app.route("/api/mesas/<int:mid>/estado", methods=["PUT"])
@requiere_rol(ROL_ADMIN, ROL_MESERO)
def cambiar_estado_mesa(mid):
    estado = cuerpo_json().get("estado")
    if estado not in ESTADOS_MESA:
        raise ErrorAPI("Estado de mesa inválido.")
    filas, _ = db.ejecutar("UPDATE mesas SET estado = %s WHERE id_mesa = %s", (estado, mid))
    if filas == 0 and not db.consultar_uno("SELECT 1 AS ok FROM mesas WHERE id_mesa = %s", (mid,)):
        raise ErrorAPI("Mesa no encontrada.", 404)
    return jresp({"ok": True})


# ============================================================
# PEDIDOS
# GET  /api/pedidos                → lista (?mesa=&estado=a,b&fecha=&limit=&items=1)
# GET  /api/pedidos/<id>           → detalle con ítems (personal)
# GET  /api/pedidos/token/<token>  → detalle para el comensal
# POST /api/pedidos                → crear pedido (comensal)
# PUT  /api/pedidos/<id>/estado    → cambiar estado
# ============================================================
ESTADOS_PEDIDO = ("pendiente", "en_preparacion", "listo", "entregado", "cancelado")
ESTADOS_ACTIVOS = ("pendiente", "en_preparacion", "listo")
# (estado actual, estado nuevo) → roles que pueden hacer ese cambio
TRANSICIONES = {
    ("pendiente", "en_preparacion"): {ROL_CHEF, ROL_ADMIN},
    ("en_preparacion", "listo"): {ROL_CHEF, ROL_ADMIN},
    ("listo", "entregado"): {ROL_MESERO, ROL_ADMIN},
    ("pendiente", "cancelado"): {ROL_CHEF, ROL_ADMIN},
    ("en_preparacion", "cancelado"): {ROL_CHEF, ROL_ADMIN},
    ("listo", "cancelado"): {ROL_ADMIN},
}
MAX_ITEMS_PEDIDO = 30

COLUMNAS_PEDIDO = """
    p.id_pedido, p.numero_pedido, p.estado, p.notas,
    p.subtotal, p.descuento, p.impuesto, p.propina, p.total,
    p.fecha_pedido, p.fecha_listo, p.fecha_entrega, m.numero_mesa
"""


def _items_de(ids_pedido):
    if not ids_pedido:
        return {}
    marcas = ", ".join(["%s"] * len(ids_pedido))
    filas = db.consultar(
        f"""SELECT d.id_pedido, d.id_producto, d.cantidad, d.precio_unit, d.subtotal,
                   COALESCE(d.nombre_producto, pr.nombre) AS nombre, pr.emoji
            FROM detalle_pedidos d
            JOIN productos pr ON d.id_producto = pr.id_producto
            WHERE d.id_pedido IN ({marcas})
            ORDER BY d.id_detalle""",
        ids_pedido,
    )
    por_pedido = {}
    for f in filas:
        por_pedido.setdefault(f.pop("id_pedido"), []).append(f)
    return por_pedido


@app.route("/api/pedidos", methods=["GET"])
@requiere_rol()
def get_pedidos():
    limit = arg_entero("limit", 50, 1, 500)
    sql = f"""SELECT {COLUMNAS_PEDIDO}, COUNT(d.id_detalle) AS num_items
              FROM pedidos p
              JOIN mesas m ON p.id_mesa = m.id_mesa
              LEFT JOIN detalle_pedidos d ON p.id_pedido = d.id_pedido
              WHERE 1=1"""
    params = []
    mesa = request.args.get("mesa")
    if mesa:
        sql += " AND m.numero_mesa = %s"
        params.append(v_entero(mesa, "mesa", 1))
    estado = request.args.get("estado")
    if estado:
        estados = [e for e in estado.split(",") if e]
        if any(e not in ESTADOS_PEDIDO for e in estados):
            raise ErrorAPI("Estado de pedido inválido.")
        sql += f" AND p.estado IN ({', '.join(['%s'] * len(estados))})"
        params.extend(estados)
    fecha = request.args.get("fecha")
    if fecha:
        try:
            params.append(date.fromisoformat(fecha))
        except ValueError:
            raise ErrorAPI("fecha: use el formato AAAA-MM-DD.")
        sql += " AND DATE(p.fecha_pedido) = %s"
    numero = (request.args.get("numero") or "").strip()
    if numero:
        sql += " AND p.numero_pedido LIKE %s"
        params.append(f"%{numero[:20]}%")
    orden = "ASC" if request.args.get("orden") == "asc" else "DESC"
    sql += f""" GROUP BY {COLUMNAS_PEDIDO}
                ORDER BY p.fecha_pedido {orden}, p.id_pedido {orden} LIMIT %s"""
    params.append(limit)
    rows = db.consultar(sql, params)
    if request.args.get("items") == "1":
        items = _items_de([r["id_pedido"] for r in rows])
        for r in rows:
            r["items"] = items.get(r["id_pedido"], [])
    return jresp(rows)


def _pedido_completo(where, valor):
    pedido = db.consultar_uno(
        f"""SELECT {COLUMNAS_PEDIDO}, p.token, c.codigo AS cupon
            FROM pedidos p
            JOIN mesas m ON p.id_mesa = m.id_mesa
            LEFT JOIN cupones c ON p.id_cupon = c.id_cupon
            WHERE {where}""",
        (valor,),
    )
    if not pedido:
        raise ErrorAPI("Pedido no encontrado.", 404)
    pedido["items"] = _items_de([pedido["id_pedido"]]).get(pedido["id_pedido"], [])
    fac = db.consultar_uno(
        "SELECT numero_factura FROM facturas WHERE id_pedido = %s", (pedido["id_pedido"],)
    )
    pedido["numero_factura"] = fac["numero_factura"] if fac else None
    return pedido


@app.route("/api/pedidos/<int:pid>", methods=["GET"])
@requiere_rol()
def get_pedido(pid):
    return jresp(_pedido_completo("p.id_pedido = %s", pid))


@app.route("/api/pedidos/token/<token>", methods=["GET"])
def get_pedido_token(token):
    if not re.fullmatch(r"[0-9a-f]{32}", token):
        raise ErrorAPI("Pedido no encontrado.", 404)
    return jresp(_pedido_completo("p.token = %s", token))


def _numero_libre(cur, tabla, columna, prefijo, consecutivo):
    """ORD-000123 / FAC-000123; si ya existe (datos antiguos) agrega -2, -3..."""
    base = f"{prefijo}-{consecutivo:06d}"
    candidato, n = base, 1
    while True:
        # tabla y columna son constantes del código, no datos del usuario
        cur.execute(f"SELECT 1 AS ok FROM {tabla} WHERE {columna} = %s", (candidato,))
        if not cur.fetchall():
            return candidato
        n += 1
        candidato = f"{base}-{n}"


def _buscar_cupon(codigo):
    return db.consultar_uno(
        """SELECT id_cupon, codigo, descuento FROM cupones
           WHERE codigo = %s AND activo = 1 AND (fecha_fin IS NULL OR fecha_fin >= CURDATE())""",
        (codigo,),
    )


@app.route("/api/pedidos", methods=["POST"])
def crear_pedido():
    """
    Cuerpo: {"mesa": 5, "codigo": "<código del QR>",
             "items": [{"id": 3, "cantidad": 2}, ...],
             "notas": "...", "cupon": "BIENVENIDO", "propina": true}
    Los precios NO se reciben del cliente: se leen de la base de datos.
    """
    if seguridad.limitador_pedidos.bloqueado(request.remote_addr):
        raise ErrorAPI("Se han enviado demasiados pedidos desde este dispositivo. "
                       "Espere unos minutos o pida ayuda al mesero.", 429)
    data = cuerpo_json()
    numero_mesa = v_entero(data.get("mesa"), "Mesa", 1)
    notas = v_texto(data.get("notas"), "Notas", 300) or None
    con_propina = v_bool(data.get("propina", True), "Propina")
    codigo_cupon = v_texto(data.get("cupon"), "Cupón", 20).upper()

    items = data.get("items")
    if not isinstance(items, list) or not items:
        raise ErrorAPI("El pedido debe tener al menos un producto.")
    if len(items) > MAX_ITEMS_PEDIDO:
        raise ErrorAPI(f"El pedido no puede tener más de {MAX_ITEMS_PEDIDO} productos distintos.")
    cantidades = {}
    for item in items:
        if not isinstance(item, dict):
            raise ErrorAPI("Formato de producto inválido.")
        pid = v_entero(item.get("id"), "Producto", 1)
        cant = v_entero(item.get("cantidad", item.get("qty")), "Cantidad", 1, 10)
        cantidades[pid] = cantidades.get(pid, 0) + cant
        if cantidades[pid] > 10:
            raise ErrorAPI("Máximo 10 unidades por producto.")

    mesa = mesa_por_qr(numero_mesa, data.get("codigo"))
    if mesa["estado"] == "inactiva":
        raise ErrorAPI(f"La mesa {numero_mesa} no está habilitada. Por favor avise al personal.", 409)

    cupon = None
    if codigo_cupon:
        cupon = _buscar_cupon(codigo_cupon)
        if not cupon:
            raise ErrorAPI("El cupón no es válido o está vencido.")

    marcas = ", ".join(["%s"] * len(cantidades))
    productos = {
        p["id_producto"]: p
        for p in db.consultar(
            f"""SELECT p.id_producto, p.nombre, p.precio
                FROM productos p JOIN categorias c ON p.id_categoria = c.id_categoria
                WHERE p.id_producto IN ({marcas})
                  AND p.activo = 1 AND p.disponible = 1 AND c.activo = 1""",
            list(cantidades),
        )
    }
    faltantes = [pid for pid in cantidades if pid not in productos]
    if faltantes:
        raise ErrorAPI(
            "Algunos productos ya no están disponibles. Actualice la carta e intente de nuevo.", 409
        )

    subtotal = sum(productos[pid]["precio"] * cant for pid, cant in cantidades.items())
    totales = calcular_totales(subtotal, cupon["descuento"] if cupon else 0, con_propina)
    token = secrets.token_hex(16)

    with db.transaccion() as cur:
        cur.execute(
            """INSERT INTO pedidos (id_mesa, id_cupon, token, estado, notas,
                                    subtotal, descuento, impuesto, propina, total)
               VALUES (%s, %s, %s, 'pendiente', %s, %s, %s, %s, %s, %s)""",
            (mesa["id_mesa"], cupon["id_cupon"] if cupon else None, token, notas,
             totales["subtotal"], totales["descuento"], totales["impuesto"],
             totales["propina"], totales["total"]),
        )
        pedido_id = cur.lastrowid
        numero = _numero_libre(cur, "pedidos", "numero_pedido", "ORD", pedido_id)
        cur.execute("UPDATE pedidos SET numero_pedido = %s WHERE id_pedido = %s", (numero, pedido_id))
        for pid, cant in cantidades.items():
            prod = productos[pid]
            cur.execute(
                """INSERT INTO detalle_pedidos
                       (id_pedido, id_producto, nombre_producto, cantidad, precio_unit, subtotal)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (pedido_id, pid, prod["nombre"], cant, prod["precio"], prod["precio"] * cant),
            )
        cur.execute(
            "UPDATE mesas SET estado = 'ocupada' WHERE id_mesa = %s AND estado = 'disponible'",
            (mesa["id_mesa"],),
        )

    seguridad.limitador_pedidos.registrar(request.remote_addr)
    log.info("Pedido %s creado en mesa %s por %s", numero, numero_mesa, totales["total"])
    return jresp({
        "ok": True,
        "id_pedido": pedido_id,
        "numero_pedido": numero,
        "token": token,
        **totales,
        "msg": "Pedido enviado a cocina",
    }, 201)


def _generar_factura(cur, pedido):
    """Crea la factura del pedido entregado (si aún no existe)."""
    cur.execute("SELECT id_factura FROM facturas WHERE id_pedido = %s", (pedido["id_pedido"],))
    if cur.fetchall():
        return
    temporal = "TMP-" + secrets.token_hex(8)
    cur.execute(
        """INSERT INTO facturas (id_pedido, numero_factura, codigo_verificacion, subtotal, descuento,
                                 impuesto_nombre, impuesto_pct, impuesto, propina, total)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (pedido["id_pedido"], temporal, secrets.token_hex(16), pedido["subtotal"], pedido["descuento"],
         config.IMPUESTO_NOMBRE, config.IMPUESTO_PCT, pedido["impuesto"], pedido["propina"], pedido["total"]),
    )
    id_factura = cur.lastrowid
    cur.execute("UPDATE facturas SET numero_factura = %s WHERE id_factura = %s",
                (_numero_libre(cur, "facturas", "numero_factura", "FAC", id_factura), id_factura))


@app.route("/api/pedidos/<int:pid>/estado", methods=["PUT"])
@requiere_rol()
def cambiar_estado_pedido(pid):
    nuevo = cuerpo_json().get("estado")
    if nuevo not in ESTADOS_PEDIDO:
        raise ErrorAPI("Estado inválido.")

    with db.transaccion() as cur:
        # FOR UPDATE: si dos personas cambian el mismo pedido a la vez,
        # la segunda espera y ve el estado ya actualizado.
        cur.execute(
            """SELECT id_pedido, id_mesa, estado, subtotal, descuento, impuesto, propina, total
               FROM pedidos WHERE id_pedido = %s FOR UPDATE""",
            (pid,),
        )
        filas = cur.fetchall()
        if not filas:
            raise ErrorAPI("Pedido no encontrado.", 404)
        pedido = filas[0]
        actual = pedido["estado"]
        if nuevo == actual:
            return jresp({"ok": True, "msg": f"El pedido ya estaba en estado {nuevo}"})
        roles = TRANSICIONES.get((actual, nuevo))
        if roles is None:
            raise ErrorAPI(f"No se puede pasar un pedido de '{actual}' a '{nuevo}'.", 409)
        if usuario_actual()["rol"] not in roles:
            raise ErrorAPI(f"Su rol no puede pasar un pedido de '{actual}' a '{nuevo}'.", 403, "sin_permiso")

        sql = "UPDATE pedidos SET estado = %s"
        if nuevo == "listo":
            sql += ", fecha_listo = NOW()"
        if nuevo == "entregado":
            sql += ", fecha_entrega = NOW(), id_usuario = %s"
        sql += " WHERE id_pedido = %s"
        params = [nuevo] + ([usuario_actual()["id_usuario"]] if nuevo == "entregado" else []) + [pid]
        cur.execute(sql, params)

        if nuevo == "entregado":
            _generar_factura(cur, pedido)

        if nuevo in ("entregado", "cancelado"):
            # La mesa queda libre solo si no tiene otros pedidos en curso.
            cur.execute(
                f"""SELECT COUNT(*) AS n FROM pedidos
                    WHERE id_mesa = %s AND estado IN ({', '.join(['%s'] * len(ESTADOS_ACTIVOS))})""",
                (pedido["id_mesa"], *ESTADOS_ACTIVOS),
            )
            if cur.fetchall()[0]["n"] == 0:
                cur.execute("UPDATE mesas SET estado = 'disponible' WHERE id_mesa = %s AND estado = 'ocupada'",
                            (pedido["id_mesa"],))

    return jresp({"ok": True, "msg": f"Estado actualizado a {nuevo}"})


# ============================================================
# FACTURAS
# GET /api/facturas/<id_pedido>       → personal
# GET /api/facturas/token/<token>     → comensal (token secreto del pedido)
# PUT /api/facturas/<id_pedido>/pago  → administrador o mesero
# ============================================================
def _factura(where, valor):
    fac = db.consultar_uno(
        f"""SELECT f.*, p.numero_pedido, p.notas, p.estado, m.numero_mesa
            FROM facturas f
            JOIN pedidos p ON f.id_pedido = p.id_pedido
            JOIN mesas m ON p.id_mesa = m.id_mesa
            WHERE {where}""",
        (valor,),
    )
    if not fac:
        raise ErrorAPI("Factura no encontrada.", 404)
    fac["items"] = _items_de([fac["id_pedido"]]).get(fac["id_pedido"], [])
    return fac


@app.route("/api/facturas/<int:pid>", methods=["GET"])
@requiere_rol()
def get_factura(pid):
    return jresp(_factura("f.id_pedido = %s", pid))


@app.route("/api/facturas/token/<token>", methods=["GET"])
def get_factura_token(token):
    if not re.fullmatch(r"[0-9a-f]{32}", token):
        raise ErrorAPI("Factura no encontrada.", 404)
    return jresp(_factura("p.token = %s", token))


@app.route("/api/facturas/<int:pid>/pago", methods=["PUT"])
@requiere_rol(ROL_ADMIN, ROL_MESERO)
def actualizar_metodo_pago(pid):
    metodo = cuerpo_json().get("metodo_pago")
    if metodo not in ("efectivo", "tarjeta", "digital"):
        raise ErrorAPI("Método de pago inválido.")
    filas, _ = db.ejecutar("UPDATE facturas SET metodo_pago = %s WHERE id_pedido = %s", (metodo, pid))
    if filas == 0 and not db.consultar_uno("SELECT 1 AS ok FROM facturas WHERE id_pedido = %s", (pid,)):
        raise ErrorAPI("Factura no encontrada.", 404)
    return jresp({"ok": True, "msg": f"Método de pago actualizado a {metodo}"})


# ============================================================
# LLAMADOS AL MESERO (botón "Llamar mesero")
# POST /api/llamados                → el comensal llama (con el código QR)
# GET  /api/llamados                → llamados pendientes (mesero/admin)
# PUT  /api/llamados/<id>/atender   → marcar como atendido
# ============================================================
@app.route("/api/llamados", methods=["POST"])
def crear_llamado():
    if seguridad.limitador_llamados.bloqueado(request.remote_addr):
        raise ErrorAPI("Ya avisamos al mesero varias veces. Por favor espere un momento.", 429)
    data = cuerpo_json()
    mesa = mesa_por_qr(v_entero(data.get("mesa"), "Mesa", 1), data.get("codigo"))
    seguridad.limitador_llamados.registrar(request.remote_addr)
    with db.transaccion() as cur:
        # Una mesa solo tiene un llamado pendiente a la vez.
        cur.execute("SELECT id_llamado FROM llamados WHERE id_mesa = %s AND estado = 'pendiente' FOR UPDATE",
                    (mesa["id_mesa"],))
        if cur.fetchall():
            return jresp({"ok": True, "ya_pendiente": True,
                          "msg": "El mesero ya fue avisado y vendrá pronto a tu mesa."})
        cur.execute("INSERT INTO llamados (id_mesa) VALUES (%s)", (mesa["id_mesa"],))
    log.info("Mesa %s llamó al mesero", mesa["numero_mesa"])
    return jresp({"ok": True, "ya_pendiente": False, "msg": "¡Listo! El mesero vendrá a tu mesa en breve."}, 201)


@app.route("/api/llamados", methods=["GET"])
@requiere_rol(ROL_ADMIN, ROL_MESERO)
def get_llamados():
    return jresp(db.consultar(
        """SELECT l.id_llamado, m.numero_mesa, l.estado, l.fecha_solicitud
           FROM llamados l JOIN mesas m ON l.id_mesa = m.id_mesa
           WHERE l.estado = 'pendiente'
           ORDER BY l.fecha_solicitud"""
    ))


@app.route("/api/llamados/<int:lid>/atender", methods=["PUT"])
@requiere_rol(ROL_ADMIN, ROL_MESERO)
def atender_llamado(lid):
    filas, _ = db.ejecutar(
        """UPDATE llamados SET estado = 'atendido', fecha_atencion = NOW(), id_usuario = %s
           WHERE id_llamado = %s AND estado = 'pendiente'""",
        (usuario_actual()["id_usuario"], lid),
    )
    if filas == 0:
        if not db.consultar_uno("SELECT 1 AS ok FROM llamados WHERE id_llamado = %s", (lid,)):
            raise ErrorAPI("Llamado no encontrado.", 404)
        return jresp({"ok": True, "msg": "El llamado ya estaba atendido"})
    return jresp({"ok": True, "msg": "Llamado atendido"})


# ============================================================
# CUPONES
# GET /api/cupones/validar?codigo=X
# ============================================================
@app.route("/api/cupones/validar", methods=["GET"])
def validar_cupon():
    codigo = (request.args.get("codigo") or "").strip().upper()
    if not codigo or len(codigo) > 20:
        raise ErrorAPI("Código requerido.")
    row = _buscar_cupon(codigo)
    if not row:
        raise ErrorAPI("Cupón inválido o vencido.", 404)
    return jresp({"ok": True, "codigo": row["codigo"], "descuento": row["descuento"]})


# ============================================================
# ESTADÍSTICAS (Dashboard)
# Las ventas solo cuentan pedidos ENTREGADOS (facturados).
# ============================================================
@app.route("/api/stats", methods=["GET"])
@requiere_rol(ROL_ADMIN)
def get_stats():
    hoy = date.today()
    pedidos_hoy = db.consultar_uno(
        "SELECT COUNT(*) AS n FROM pedidos WHERE DATE(fecha_pedido) = %s AND estado <> 'cancelado'", (hoy,)
    )["n"]
    ventas_hoy = db.consultar_uno(
        """SELECT COALESCE(SUM(f.total), 0) AS total
           FROM facturas f JOIN pedidos p ON f.id_pedido = p.id_pedido
           WHERE p.estado = 'entregado' AND DATE(f.fecha_factura) = %s""",
        (hoy,),
    )["total"]
    activos = db.consultar_uno(
        "SELECT COUNT(*) AS n FROM pedidos WHERE estado IN ('pendiente','en_preparacion','listo')"
    )["n"]
    productos = db.consultar_uno(
        "SELECT COUNT(*) AS n FROM productos WHERE activo = 1 AND disponible = 1"
    )["n"]
    mesas_ocupadas = db.consultar_uno("SELECT COUNT(*) AS n FROM mesas WHERE estado = 'ocupada'")["n"]
    ventas_cat = db.consultar(
        """SELECT nombre_categoria AS categoria, ingresos_brutos AS total
           FROM v_ventas_por_categoria ORDER BY total DESC"""
    )
    return jresp({
        "pedidos_hoy": pedidos_hoy,
        "ventas_hoy": ventas_hoy,
        "activos": activos,
        "productos": productos,
        "mesas_ocupadas": mesas_ocupadas,
        "ventas_cat": ventas_cat,
    })


# ============================================================
# FRONTEND (HTML, CSS, JS e imágenes)
# Solo se sirven estos archivos; nunca el código del backend ni el .env
# ============================================================
_HTML_RAIZ = re.compile(r"^[A-Za-z0-9_\-]+\.html$")
_CARPETAS_PUBLICAS = ("css/", "js/", "img/")


@app.route("/")
def pagina_inicio():
    return send_from_directory(config.PROYECTO_DIR, "index.html", max_age=0)


@app.route("/<path:ruta>")
def archivos_frontend(ruta):
    if ruta.startswith("api/"):
        abort(404)
    if _HTML_RAIZ.match(ruta) or (ruta.startswith(_CARPETAS_PUBLICAS) and ".." not in ruta):
        return send_from_directory(config.PROYECTO_DIR, ruta, max_age=0)
    abort(404)


# ============================================================
# MAIN (solo para desarrollo; en producción se usa Waitress)
# ============================================================
if __name__ == "__main__":
    print("=" * 56)
    print("  Restaurante SENA — servidor de DESARROLLO")
    print("  Abra: http://localhost:8000")
    print(f"  Base de datos: {config.DB_NAME} @ {config.DB_HOST}:{config.DB_PORT}")
    print("  Para producción use scripts/iniciar_servidor.ps1")
    print("=" * 56)
    app.run(host="0.0.0.0", port=8000, debug=False)
