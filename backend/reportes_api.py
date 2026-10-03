"""
reportes_api.py — Reportes de ventas por día, semana y mes

Solo cuentan los pedidos ENTREGADOS (los que tienen comprobante), por la
fecha del comprobante. Los cancelados se informan aparte.

GET /api/reportes/ventas?periodo=dia|semana|mes&desde=AAAA-MM-DD&hasta=AAAA-MM-DD
GET /api/reportes/ventas.csv?...   → mismo reporte para abrir en Excel
"""

import csv
import io
from datetime import date, timedelta

from flask import Blueprint, make_response, request

import db
from errores import ErrorAPI
from seguridad import ROL_ADMIN, requiere_rol
from validacion import jresp, v_fecha

bp = Blueprint("reportes", __name__)

# Expresión SQL que agrupa la fecha del comprobante según el período.
# (Funciones disponibles igual en MariaDB y MySQL 8.)
AGRUPAR = {
    "dia": "DATE(f.fecha_factura)",
    "semana": "DATE_SUB(DATE(f.fecha_factura), INTERVAL WEEKDAY(f.fecha_factura) DAY)",   # lunes
    "mes": "DATE_FORMAT(f.fecha_factura, '%Y-%m-01')",
}
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
MAX_DIAS = 3 * 366


def _inicio_periodo(d, periodo):
    if periodo == "semana":
        return d - timedelta(days=d.weekday())
    if periodo == "mes":
        return d.replace(day=1)
    return d


def _siguiente(d, periodo):
    if periodo == "dia":
        return d + timedelta(days=1)
    if periodo == "semana":
        return d + timedelta(days=7)
    return (d.replace(day=28) + timedelta(days=4)).replace(day=1)


def etiqueta(d, periodo):
    if periodo == "dia":
        return d.strftime("%d/%m/%Y")
    if periodo == "semana":
        fin = d + timedelta(days=6)
        return f"{d.strftime('%d/%m')} – {fin.strftime('%d/%m/%Y')}"
    return f"{MESES[d.month - 1].capitalize()} {d.year}"


def _rango():
    """Período y fechas (por defecto: 30 días, 12 semanas o 12 meses hasta hoy)."""
    periodo = request.args.get("periodo", "dia")
    if periodo not in AGRUPAR:
        raise ErrorAPI("periodo: use dia, semana o mes.")
    hoy = date.today()
    hasta = v_fecha(request.args.get("hasta"), "Hasta") or hoy
    desde = v_fecha(request.args.get("desde"), "Desde")
    if desde is None:
        if periodo == "dia":
            desde = hasta - timedelta(days=29)
        elif periodo == "semana":
            desde = _inicio_periodo(hasta, "semana") - timedelta(weeks=11)
        else:
            m = hasta.month - 11
            desde = date(hasta.year + (m - 1) // 12, (m - 1) % 12 + 1, 1)
    if desde > hasta:
        raise ErrorAPI("La fecha inicial no puede ser posterior a la final.")
    if (hasta - desde).days > MAX_DIAS:
        raise ErrorAPI("El rango máximo es de 3 años.")
    return periodo, desde, hasta


def calcular_reporte(periodo, desde, hasta):
    # Rango por fecha y hora: [desde 00:00, hasta+1 00:00) usa el índice de fecha
    params = (desde, hasta + timedelta(days=1))
    filtro = """FROM facturas f
                JOIN pedidos p ON f.id_pedido = p.id_pedido
                WHERE p.estado = 'entregado'
                  AND f.fecha_factura >= %s AND f.fecha_factura < %s"""

    filas = db.consultar(
        f"""SELECT {AGRUPAR[periodo]} AS inicio, COUNT(*) AS pedidos,
                   SUM(f.subtotal) AS subtotal, SUM(f.descuento) AS descuento,
                   SUM(f.impuesto) AS impuesto, SUM(f.propina) AS propina, SUM(f.total) AS total
            {filtro}
            GROUP BY inicio ORDER BY inicio""", params)
    por_inicio = {}
    for f in filas:
        inicio = f["inicio"] if isinstance(f["inicio"], date) else date.fromisoformat(str(f["inicio"])[:10])
        por_inicio[inicio] = f

    # Todos los períodos del rango, también los que no tuvieron ventas
    series = []
    d = _inicio_periodo(desde, periodo)
    while d <= hasta:
        f = por_inicio.get(d, {})
        pedidos = int(f.get("pedidos") or 0)
        total = int(f.get("total") or 0)
        series.append({
            "inicio": d.isoformat(), "etiqueta": etiqueta(d, periodo),
            "pedidos": pedidos,
            "subtotal": int(f.get("subtotal") or 0), "descuento": int(f.get("descuento") or 0),
            "impuesto": int(f.get("impuesto") or 0), "propina": int(f.get("propina") or 0),
            "total": total, "ticket_promedio": round(total / pedidos) if pedidos else 0,
        })
        d = _siguiente(d, periodo)

    resumen = {k: sum(s[k] for s in series) for k in ("pedidos", "subtotal", "descuento", "impuesto", "propina", "total")}
    resumen["ticket_promedio"] = round(resumen["total"] / resumen["pedidos"]) if resumen["pedidos"] else 0
    resumen["cancelados"] = db.consultar_uno(
        """SELECT COUNT(*) AS n FROM pedidos
           WHERE estado = 'cancelado' AND fecha_pedido >= %s AND fecha_pedido < %s""", params)["n"]

    productos = db.consultar(
        f"""SELECT COALESCE(d.nombre_producto, pr.nombre) AS producto,
                   SUM(d.cantidad) AS unidades, SUM(d.subtotal) AS ventas
            FROM detalle_pedidos d
            JOIN productos pr ON d.id_producto = pr.id_producto
            JOIN pedidos p ON d.id_pedido = p.id_pedido
            JOIN facturas f ON f.id_pedido = p.id_pedido
            WHERE p.estado = 'entregado' AND f.fecha_factura >= %s AND f.fecha_factura < %s
            GROUP BY COALESCE(d.nombre_producto, pr.nombre)
            ORDER BY unidades DESC, ventas DESC LIMIT 10""", params)
    categorias = db.consultar(
        """SELECT c.nombre_categoria AS categoria, SUM(d.cantidad) AS unidades, SUM(d.subtotal) AS ventas
           FROM detalle_pedidos d
           JOIN productos pr ON d.id_producto = pr.id_producto
           JOIN categorias c ON pr.id_categoria = c.id_categoria
           JOIN pedidos p ON d.id_pedido = p.id_pedido
           JOIN facturas f ON f.id_pedido = p.id_pedido
           WHERE p.estado = 'entregado' AND f.fecha_factura >= %s AND f.fecha_factura < %s
           GROUP BY c.nombre_categoria ORDER BY ventas DESC""", params)
    pagos = db.consultar(
        f"""SELECT f.metodo_pago, COUNT(*) AS pedidos, SUM(f.total) AS total
            {filtro} GROUP BY f.metodo_pago ORDER BY total DESC""", params)

    return {
        "periodo": periodo, "desde": desde.isoformat(), "hasta": hasta.isoformat(),
        "resumen": resumen, "series": series,
        "productos": productos, "categorias": categorias, "pagos": pagos,
    }


@bp.route("/api/reportes/ventas", methods=["GET"])
@requiere_rol(ROL_ADMIN)
def reporte_ventas():
    return jresp(calcular_reporte(*_rango()))


@bp.route("/api/reportes/ventas.csv", methods=["GET"])
@requiere_rol(ROL_ADMIN)
def reporte_ventas_csv():
    periodo, desde, hasta = _rango()
    rep = calcular_reporte(periodo, desde, hasta)
    buf = io.StringIO()
    # Punto y coma: es el separador que Excel espera con la configuración regional de Colombia.
    w = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    nombre_periodo = {"dia": "Día", "semana": "Semana", "mes": "Mes"}[periodo]
    w.writerow([f"Reporte de ventas por {nombre_periodo.lower()}", f"Del {desde.strftime('%d/%m/%Y')} al {hasta.strftime('%d/%m/%Y')}"])
    w.writerow([])
    w.writerow([nombre_periodo, "Pedidos", "Subtotal", "Descuentos", "Impuesto", "Propinas", "Total", "Ticket promedio"])
    for s in rep["series"]:
        w.writerow([s["etiqueta"], s["pedidos"], s["subtotal"], s["descuento"], s["impuesto"],
                    s["propina"], s["total"], s["ticket_promedio"]])
    r = rep["resumen"]
    w.writerow(["TOTAL", r["pedidos"], r["subtotal"], r["descuento"], r["impuesto"], r["propina"], r["total"],
                r["ticket_promedio"]])
    w.writerow(["Pedidos cancelados", r["cancelados"]])
    w.writerow([])
    w.writerow(["Productos más vendidos", "Unidades", "Ventas"])
    for p in rep["productos"]:
        w.writerow([p["producto"], int(p["unidades"]), int(p["ventas"])])
    w.writerow([])
    w.writerow(["Categoría", "Unidades", "Ventas"])
    for c in rep["categorias"]:
        w.writerow([c["categoria"], int(c["unidades"]), int(c["ventas"])])
    w.writerow([])
    w.writerow(["Método de pago", "Pedidos", "Total"])
    for p in rep["pagos"]:
        w.writerow([p["metodo_pago"], p["pedidos"], int(p["total"])])

    # BOM UTF-8 para que Excel muestre bien las tildes
    resp = make_response("﻿" + buf.getvalue())
    resp.headers["Content-Type"] = "text/csv; charset=utf-8"
    resp.headers["Content-Disposition"] = (
        f'attachment; filename="ventas_{periodo}_{desde.isoformat()}_{hasta.isoformat()}.csv"')
    resp.headers["Cache-Control"] = "no-store"
    return resp
