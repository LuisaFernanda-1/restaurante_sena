"""
qr_api.py — Códigos QR de las mesas y verificación de comprobantes

Los QR se generan en el servidor con la librería segno (Python puro,
sin conexión a internet). Contienen direcciones basadas en SERVER_URL
(backend/.env), que debe ser la IP fija del computador servidor para que
los celulares puedan abrirlas.

  Mesa:        SERVER_URL/menu.html?mesa=N&c=<código secreto de la mesa>
  Comprobante: SERVER_URL/verificar.html?c=<código de verificación>
"""

import io
import ipaddress
import logging
import re
import secrets
import socket
from urllib.parse import quote, urlsplit

import segno
from flask import Blueprint, make_response, request

import config
import db
from errores import ErrorAPI
from seguridad import ROL_ADMIN, requiere_rol, usuario_actual
from validacion import jresp

log = logging.getLogger("restaurante.qr")
bp = Blueprint("qr", __name__)

COLOR_QR = "#004d26"


def url_menu_mesa(numero, codigo):
    return f"{config.SERVER_URL}/menu.html?mesa={numero}&c={quote(codigo)}"


def url_verificacion(codigo):
    return f"{config.SERVER_URL}/verificar.html?c={quote(codigo)}"


def server_url_local():
    """True si SERVER_URL apunta a este mismo equipo (los celulares no la abrirían)."""
    host = (urlsplit(config.SERVER_URL).hostname or "").lower()
    return host in ("localhost", "127.0.0.1", "0.0.0.0", "::1", "")


def ips_del_servidor():
    """Direcciones IPv4 de este computador en la red."""
    try:
        return sorted({a[4][0] for a in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
                       if not a[4][0].startswith("127.")})
    except OSError:
        return []


def ip_no_coincide():
    """
    True si SERVER_URL usa una IP que este computador ya no tiene (por
    ejemplo, el router le asignó otra): los QR impresos no funcionarían.
    Si SERVER_URL usa un nombre (no una IP) no se puede comprobar.
    """
    host = urlsplit(config.SERVER_URL).hostname or ""
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    ips = ips_del_servidor()
    return bool(ips) and not server_url_local() and host not in ips


def respuesta_qr(texto, nombre_archivo):
    """Imagen QR: SVG (por defecto, escalable para imprimir) o PNG (?formato=png)."""
    qr = segno.make(texto, error="m")
    buf = io.BytesIO()
    if request.args.get("formato") == "png":
        qr.save(buf, kind="png", scale=12, border=3, dark=COLOR_QR)
        tipo, extension = "image/png", "png"
    else:
        qr.save(buf, kind="svg", scale=10, border=3, dark=COLOR_QR, xmldecl=False, omitsize=True)
        tipo, extension = "image/svg+xml", "svg"
    resp = make_response(buf.getvalue())
    resp.headers["Content-Type"] = tipo
    resp.headers["Cache-Control"] = "no-store"
    if request.args.get("descargar") == "1":
        resp.headers["Content-Disposition"] = f'attachment; filename="{nombre_archivo}.{extension}"'
    return resp


def _mesa(mid):
    mesa = db.consultar_uno(
        "SELECT id_mesa, numero_mesa, capacidad, estado, codigo_qr FROM mesas WHERE id_mesa = %s", (mid,))
    if not mesa:
        raise ErrorAPI("Mesa no encontrada.", 404)
    return mesa


# ============================================================
# QR DE LAS MESAS (solo administrador: contienen el código secreto)
# GET  /api/qr/info                    → SERVER_URL y si es local
# GET  /api/mesas/<id>/qr              → imagen (SVG o ?formato=png)
# GET  /api/mesas/<id>/qr/enlace       → la dirección que va en el QR
# POST /api/mesas/<id>/regenerar-qr    → código nuevo (invalida el QR impreso)
# ============================================================
@bp.route("/api/qr/info", methods=["GET"])
@requiere_rol(ROL_ADMIN)
def info_qr():
    return jresp({"server_url": config.SERVER_URL, "es_local": server_url_local(),
                  "ip_no_coincide": ip_no_coincide(), "ips_servidor": ips_del_servidor()})


@bp.route("/api/mesas/<int:mid>/qr", methods=["GET"])
@requiere_rol(ROL_ADMIN)
def qr_mesa(mid):
    mesa = _mesa(mid)
    if not mesa["codigo_qr"]:
        raise ErrorAPI("La mesa no tiene código QR. Regenérelo.", 409)
    return respuesta_qr(url_menu_mesa(mesa["numero_mesa"], mesa["codigo_qr"]), f"qr-mesa-{mesa['numero_mesa']}")


@bp.route("/api/mesas/<int:mid>/qr/enlace", methods=["GET"])
@requiere_rol(ROL_ADMIN)
def enlace_mesa(mid):
    mesa = _mesa(mid)
    return jresp({"numero_mesa": mesa["numero_mesa"], "url": url_menu_mesa(mesa["numero_mesa"], mesa["codigo_qr"]),
                  "es_local": server_url_local()})


@bp.route("/api/mesas/<int:mid>/regenerar-qr", methods=["POST"])
@requiere_rol(ROL_ADMIN)
def regenerar_qr(mid):
    mesa = _mesa(mid)
    db.ejecutar("UPDATE mesas SET codigo_qr = %s WHERE id_mesa = %s", (secrets.token_hex(5), mid))
    log.info("QR de la mesa %s regenerado por '%s'", mesa["numero_mesa"], usuario_actual()["usuario"])
    return jresp({"ok": True, "msg": f"Nuevo QR para la mesa {mesa['numero_mesa']}. Imprímalo y reemplace el anterior."})


# ============================================================
# VERIFICACIÓN DE COMPROBANTES (público)
# GET /api/facturas/token/<token>/qr   → QR de verificación (comensal)
# GET /api/verificar/<código>          → datos básicos del comprobante
# ============================================================
_RE_HEX32 = re.compile(r"^[0-9a-f]{32}$")


@bp.route("/api/facturas/token/<token>/qr", methods=["GET"])
def qr_factura(token):
    if not _RE_HEX32.match(token):
        raise ErrorAPI("Factura no encontrada.", 404)
    fac = db.consultar_uno(
        """SELECT f.numero_factura, f.codigo_verificacion FROM facturas f
           JOIN pedidos p ON f.id_pedido = p.id_pedido WHERE p.token = %s""", (token,))
    if not fac or not fac["codigo_verificacion"]:
        raise ErrorAPI("Factura no encontrada.", 404)
    return respuesta_qr(url_verificacion(fac["codigo_verificacion"]), f"verificar-{fac['numero_factura']}")


@bp.route("/api/verificar/<codigo>", methods=["GET"])
def verificar(codigo):
    codigo = codigo.strip().lower()
    if not _RE_HEX32.match(codigo):
        raise ErrorAPI("No existe un comprobante con ese código.", 404)
    fac = db.consultar_uno(
        """SELECT f.numero_factura, f.fecha_factura, f.subtotal, f.descuento, f.impuesto_nombre,
                  f.impuesto_pct, f.impuesto, f.propina, f.total, f.metodo_pago,
                  p.numero_pedido, p.estado, m.numero_mesa,
                  (SELECT COALESCE(SUM(d.cantidad), 0) FROM detalle_pedidos d WHERE d.id_pedido = p.id_pedido) AS unidades
           FROM facturas f
           JOIN pedidos p ON f.id_pedido = p.id_pedido
           JOIN mesas m ON p.id_mesa = m.id_mesa
           WHERE f.codigo_verificacion = %s""",
        (codigo,))
    if not fac:
        raise ErrorAPI("No existe un comprobante con ese código.", 404)
    fac["restaurante"] = config.RESTAURANTE_NOMBRE
    fac["nit"] = config.RESTAURANTE_NIT
    fac["valido"] = fac["estado"] == "entregado"
    return jresp(fac)
