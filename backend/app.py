"""
app.py — Backend Flask para Restaurante SENA
GA7-220501096-AA2-EV02
Conecta con MySQL usando mysql-connector-python
"""

from flask import Flask, request, jsonify, session
from flask_cors import CORS
import mysql.connector
from mysql.connector import Error
import hashlib
import os
from datetime import datetime, date
import json

app = Flask(__name__)
app.secret_key = "sena_restaurante_2025_secret"
CORS(app, supports_credentials=True, origins=["http://localhost:5500", "http://127.0.0.1:5500", "http://localhost:3000", "null", "*"])

# ============================================================
# CONFIGURACIÓN DE BASE DE DATOS
# ============================================================
DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "root",          # Cambia si tu usuario es diferente
    "password": "root",      # Cambia por tu contraseña de MySQL
    "database": "restaurante_sena",
    "charset": "utf8mb4",
    "autocommit": True
}

def get_db():
    """Crea y retorna una conexión a MySQL."""
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except Error as e:
        print(f"[ERROR DB] {e}")
        return None

def query(sql, params=None, fetch="all"):
    """Helper para ejecutar queries. Retorna filas o None."""
    conn = get_db()
    if not conn:
        return None
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, params or ())
        if fetch == "all":
            return cur.fetchall()
        elif fetch == "one":
            return cur.fetchone()
        else:
            conn.commit()
            return cur.lastrowid
    except Error as e:
        print(f"[ERROR QUERY] {e}\nSQL: {sql}")
        return None
    finally:
        cur.close()
        conn.close()

def serialize(obj):
    """Convierte tipos no serializables (date, datetime) a string."""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")

def jresp(data, status=200):
    return app.response_class(
        response=json.dumps(data, default=serialize),
        status=status,
        mimetype="application/json"
    )

# ============================================================
# RUTA: ESTADO DE LA API
# ============================================================
@app.route("/api/status", methods=["GET"])
def status():
    conn = get_db()
    if conn:
        conn.close()
        return jresp({"ok": True, "msg": "Conectado a MySQL ✓", "db": DB_CONFIG["database"]})
    return jresp({"ok": False, "msg": "Sin conexión a MySQL"}, 500)

# ============================================================
# RUTA: AUTENTICACIÓN
# GET  /api/auth/me       → usuario actual (session)
# POST /api/auth/login    → login con usuario/password
# POST /api/auth/logout   → cierra sesión
# ============================================================
@app.route("/api/auth/login", methods=["POST"])
def login():
    """POST /api/auth/login — Servlet de autenticación."""
    data = request.get_json() or {}
    usuario = data.get("usuario", "").strip()
    password = data.get("password", "")

    if not usuario or not password:
        return jresp({"ok": False, "msg": "Usuario y contraseña requeridos"}, 400)

    # Hash SHA-256 de la contraseña (método GET de parámetros: usuario viene en body POST)
    pwd_hash = hashlib.sha256(password.encode()).hexdigest()

    row = query(
        """SELECT u.id_usuario, u.nombre, u.correo, r.nombre_rol
           FROM usuarios u
           JOIN roles r ON u.id_rol = r.id_rol
           WHERE u.correo = %s AND u.contrasena_hash = %s AND u.activo = 1""",
        (usuario, pwd_hash),
        fetch="one"
    )

    # También buscar por nombre de usuario (campo correo o nombre)
    if not row:
        row = query(
            """SELECT u.id_usuario, u.nombre, u.correo, r.nombre_rol
               FROM usuarios u
               JOIN roles r ON u.id_rol = r.id_rol
               WHERE u.nombre = %s AND u.contrasena_hash = %s AND u.activo = 1""",
            (usuario, pwd_hash),
            fetch="one"
        )

    if row:
        session["user_id"] = row["id_usuario"]
        session["user_nombre"] = row["nombre"]
        session["user_rol"] = row["nombre_rol"]
        return jresp({"ok": True, "user": row})
    return jresp({"ok": False, "msg": "Credenciales incorrectas"}, 401)

@app.route("/api/auth/logout", methods=["POST"])
def logout():
    session.clear()
    return jresp({"ok": True})

@app.route("/api/auth/me", methods=["GET"])
def me():
    if "user_id" not in session:
        return jresp({"ok": False, "msg": "No autenticado"}, 401)
    return jresp({"ok": True, "user": {
        "id": session["user_id"],
        "nombre": session["user_nombre"],
        "rol": session["user_rol"]
    }})

# ============================================================
# RUTA: CATEGORÍAS
# GET  /api/categorias
# ============================================================
@app.route("/api/categorias", methods=["GET"])
def get_categorias():
    rows = query("SELECT * FROM categorias WHERE activo = 1 ORDER BY nombre_categoria")
    return jresp(rows or [])

# ============================================================
# RUTA: PRODUCTOS
# GET    /api/productos              → lista todos
# GET    /api/productos?cat=X        → filtra por categoría
# GET    /api/productos?q=busqueda   → búsqueda (método GET con parámetros)
# GET    /api/productos/<id>         → uno solo
# POST   /api/productos              → crear
# PUT    /api/productos/<id>         → editar
# DELETE /api/productos/<id>         → eliminar
# ============================================================
@app.route("/api/productos", methods=["GET"])
def get_productos():
    """
    GET /api/productos — usa request.args (equivalente a request.getParameter en JSP).
    Soporta parámetros: ?cat=Entradas&q=bandeja&disponible=1
    """
    cat = request.args.get("cat")         # request.getParameter("cat")
    q   = request.args.get("q")           # request.getParameter("q")
    disp = request.args.get("disponible") # request.getParameter("disponible")

    sql = """
        SELECT p.id_producto, p.nombre, p.descripcion, p.precio,
               p.disponible, p.imagen_url, c.nombre_categoria AS cat
        FROM productos p
        JOIN categorias c ON p.id_categoria = c.id_categoria
        WHERE 1=1
    """
    params = []
    if cat:
        sql += " AND c.nombre_categoria = %s"
        params.append(cat)
    if q:
        sql += " AND (p.nombre LIKE %s OR p.descripcion LIKE %s)"
        params.extend([f"%{q}%", f"%{q}%"])
    if disp == "1":
        sql += " AND p.disponible = 1"
    sql += " ORDER BY c.nombre_categoria, p.nombre"

    rows = query(sql, params)
    return jresp(rows or [])

@app.route("/api/productos/<int:pid>", methods=["GET"])
def get_producto(pid):
    row = query(
        """SELECT p.*, c.nombre_categoria AS cat FROM productos p
           JOIN categorias c ON p.id_categoria = c.id_categoria
           WHERE p.id_producto = %s""",
        (pid,), fetch="one"
    )
    if not row:
        return jresp({"error": "Producto no encontrado"}, 404)
    return jresp(row)

@app.route("/api/productos", methods=["POST"])
def crear_producto():
    """POST /api/productos — crea producto (body con campos del formulario HTML)."""
    data = request.get_json() or {}
    nombre    = data.get("nombre", "").strip()
    desc      = data.get("descripcion", "")
    precio    = data.get("precio")
    cat_id    = data.get("id_categoria")
    imagen    = data.get("imagen_url", "")

    if not nombre or not precio or not cat_id:
        return jresp({"ok": False, "msg": "Nombre, precio y categoría son requeridos"}, 400)

    new_id = query(
        "INSERT INTO productos (id_categoria, nombre, descripcion, precio, imagen_url) VALUES (%s,%s,%s,%s,%s)",
        (cat_id, nombre, desc, precio, imagen),
        fetch="insert"
    )
    return jresp({"ok": True, "id_producto": new_id, "msg": f"Producto '{nombre}' creado"})

@app.route("/api/productos/<int:pid>", methods=["PUT"])
def editar_producto(pid):
    data = request.get_json() or {}
    campos = []
    params = []
    for f in ["nombre", "descripcion", "precio", "disponible", "imagen_url", "id_categoria"]:
        if f in data:
            campos.append(f"{f} = %s")
            params.append(data[f])
    if not campos:
        return jresp({"ok": False, "msg": "Nada que actualizar"}, 400)
    params.append(pid)
    query(f"UPDATE productos SET {', '.join(campos)} WHERE id_producto = %s", params, fetch="insert")
    return jresp({"ok": True, "msg": "Producto actualizado"})

@app.route("/api/productos/<int:pid>", methods=["DELETE"])
def eliminar_producto(pid):
    query("DELETE FROM productos WHERE id_producto = %s", (pid,), fetch="insert")
    return jresp({"ok": True, "msg": "Producto eliminado"})

# ============================================================
# RUTA: MESAS
# GET  /api/mesas
# GET  /api/mesas/<numero>
# PUT  /api/mesas/<id>/estado
# ============================================================
@app.route("/api/mesas", methods=["GET"])
def get_mesas():
    estado = request.args.get("estado")
    sql = "SELECT * FROM mesas"
    params = []
    if estado:
        sql += " WHERE estado = %s"
        params.append(estado)
    sql += " ORDER BY numero_mesa"
    return jresp(query(sql, params) or [])

@app.route("/api/mesas/<int:numero>", methods=["GET"])
def get_mesa(numero):
    row = query("SELECT * FROM mesas WHERE numero_mesa = %s", (numero,), fetch="one")
    if not row:
        return jresp({"error": "Mesa no encontrada"}, 404)
    return jresp(row)

@app.route("/api/mesas/<int:mid>/estado", methods=["PUT"])
def cambiar_estado_mesa(mid):
    data = request.get_json() or {}
    estado = data.get("estado")
    if estado not in ["disponible", "ocupada", "reservada", "inactiva"]:
        return jresp({"ok": False, "msg": "Estado inválido"}, 400)
    query("UPDATE mesas SET estado = %s WHERE id_mesa = %s", (estado, mid), fetch="insert")
    return jresp({"ok": True})

# ============================================================
# RUTA: PEDIDOS
# GET  /api/pedidos              → todos (admin)
# GET  /api/pedidos?mesa=X       → por mesa
# GET  /api/pedidos?estado=X     → por estado
# GET  /api/pedidos/<id>         → detalle con items
# POST /api/pedidos              → crear pedido
# PUT  /api/pedidos/<id>/estado  → cambiar estado
# ============================================================
@app.route("/api/pedidos", methods=["GET"])
def get_pedidos():
    """GET /api/pedidos — parámetros opcionales: mesa, estado, limit."""
    mesa   = request.args.get("mesa")
    estado = request.args.get("estado")
    limit  = request.args.get("limit", 50)

    sql = """
        SELECT p.id_pedido, p.numero_pedido, p.estado, p.notas,
               p.fecha_pedido, p.fecha_entrega,
               m.numero_mesa,
               COALESCE(SUM(d.subtotal), 0) AS total,
               COUNT(d.id_detalle) AS num_items
        FROM pedidos p
        JOIN mesas m ON p.id_mesa = m.id_mesa
        LEFT JOIN detalle_pedidos d ON p.id_pedido = d.id_pedido
        WHERE 1=1
    """
    params = []
    if mesa:
        sql += " AND m.numero_mesa = %s"
        params.append(mesa)
    if estado:
        sql += " AND p.estado = %s"
        params.append(estado)
    sql += " GROUP BY p.id_pedido ORDER BY p.fecha_pedido DESC LIMIT %s"
    params.append(int(limit))

    rows = query(sql, params)
    return jresp(rows or [])

@app.route("/api/pedidos/<int:pid>", methods=["GET"])
def get_pedido(pid):
    pedido = query(
        """SELECT p.*, m.numero_mesa
           FROM pedidos p JOIN mesas m ON p.id_mesa = m.id_mesa
           WHERE p.id_pedido = %s""",
        (pid,), fetch="one"
    )
    if not pedido:
        return jresp({"error": "Pedido no encontrado"}, 404)
    items = query(
        """SELECT d.*, pr.nombre, pr.imagen_url
           FROM detalle_pedidos d
           JOIN productos pr ON d.id_producto = pr.id_producto
           WHERE d.id_pedido = %s""",
        (pid,)
    )
    pedido["items"] = items or []
    return jresp(pedido)

@app.route("/api/pedidos", methods=["POST"])
def crear_pedido():
    """
    POST /api/pedidos — recibe JSON con mesa, items y notas.
    Equivale al envío de un formulario HTML con method="POST".
    """
    data = request.get_json() or {}
    mesa_num = data.get("mesa")
    items    = data.get("items", [])
    notas    = data.get("notas", "")

    if not mesa_num or not items:
        return jresp({"ok": False, "msg": "Mesa e ítems son requeridos"}, 400)

    # Buscar id_mesa
    mesa = query("SELECT id_mesa, estado FROM mesas WHERE numero_mesa = %s", (mesa_num,), fetch="one")
    if not mesa:
        return jresp({"ok": False, "msg": f"Mesa {mesa_num} no existe"}, 404)

    # Generar número único de pedido
    numero = f"ORD-{int(datetime.now().timestamp() * 1000) % 1000000:06d}"

    conn = get_db()
    if not conn:
        return jresp({"ok": False, "msg": "Error de base de datos"}, 500)
    try:
        cur = conn.cursor(dictionary=True)

        # Insertar pedido
        cur.execute(
            "INSERT INTO pedidos (id_mesa, numero_pedido, estado, notas) VALUES (%s, %s, 'pendiente', %s)",
            (mesa["id_mesa"], numero, notas)
        )
        pedido_id = cur.lastrowid

        total = 0
        # Insertar cada ítem en detalle_pedidos
        for item in items:
            prod = None
            cur2 = conn.cursor(dictionary=True)
            cur2.execute("SELECT precio FROM productos WHERE id_producto = %s AND disponible = 1", (item["id"],))
            prod = cur2.fetchone()
            cur2.close()

            if not prod:
                continue
            precio   = float(prod["precio"])
            cantidad = max(1, min(10, int(item.get("qty", 1))))
            subtotal = precio * cantidad
            total   += subtotal
            cur.execute(
                "INSERT INTO detalle_pedidos (id_pedido, id_producto, cantidad, precio_unit, subtotal) VALUES (%s,%s,%s,%s,%s)",
                (pedido_id, item["id"], cantidad, precio, subtotal)
            )

        # Cambiar estado de la mesa a ocupada
        cur.execute("UPDATE mesas SET estado = 'ocupada' WHERE id_mesa = %s", (mesa["id_mesa"],))

        conn.commit()

        # Generar factura automáticamente
        iva      = round(total * 0.19, 2)
        servicio = round(total * 0.10, 2)
        total_f  = round(total + iva + servicio, 2)
        num_fac  = f"FAC-{pedido_id:06d}"
        cur.execute(
            "INSERT INTO facturas (id_pedido, numero_factura, subtotal, iva, servicio, total) VALUES (%s,%s,%s,%s,%s,%s)",
            (pedido_id, num_fac, round(total,2), iva, servicio, total_f)
        )
        conn.commit()

        return jresp({
            "ok": True,
            "id_pedido": pedido_id,
            "numero_pedido": numero,
            "numero_factura": num_fac,
            "total": total_f,
            "msg": "Pedido creado exitosamente"
        })
    except Error as e:
        conn.rollback()
        return jresp({"ok": False, "msg": str(e)}, 500)
    finally:
        cur.close()
        conn.close()

@app.route("/api/pedidos/<int:pid>/estado", methods=["PUT"])
def cambiar_estado_pedido(pid):
    data   = request.get_json() or {}
    estado = data.get("estado")
    validos = ["pendiente", "en_preparacion", "listo", "entregado", "cancelado"]
    if estado not in validos:
        return jresp({"ok": False, "msg": "Estado inválido"}, 400)

    params = [estado]
    sql    = "UPDATE pedidos SET estado = %s"
    if estado == "entregado":
        sql += ", fecha_entrega = NOW()"
    sql += " WHERE id_pedido = %s"
    params.append(pid)
    query(sql, params, fetch="insert")

    # Si se entrega, liberar mesa
    if estado == "entregado":
        pedido = query("SELECT id_mesa FROM pedidos WHERE id_pedido = %s", (pid,), fetch="one")
        if pedido:
            query("UPDATE mesas SET estado = 'disponible' WHERE id_mesa = %s",
                  (pedido["id_mesa"],), fetch="insert")

    return jresp({"ok": True, "msg": f"Estado → {estado}"})

# ============================================================
# RUTA: FACTURAS
# GET /api/facturas/<id_pedido>
# ============================================================
@app.route("/api/facturas/<int:pid>", methods=["GET"])
def get_factura(pid):
    fac = query(
        "SELECT * FROM facturas WHERE id_pedido = %s ORDER BY fecha_factura DESC LIMIT 1",
        (pid,), fetch="one"
    )
    if not fac:
        return jresp({"error": "Factura no encontrada"}, 404)
    items = query(
        """SELECT d.cantidad, d.precio_unit, d.subtotal, pr.nombre
           FROM detalle_pedidos d
           JOIN productos pr ON d.id_producto = pr.id_producto
           WHERE d.id_pedido = %s""",
        (pid,)
    )
    fac["items"] = items or []
    return jresp(fac)

@app.route("/api/facturas/<int:pid>/pago", methods=["PUT"])
def actualizar_metodo_pago(pid):
    data   = request.get_json() or {}
    metodo = data.get("metodo_pago", "efectivo")
    if metodo not in ["efectivo", "tarjeta", "digital"]:
        return jresp({"ok": False, "msg": "Método de pago inválido"}, 400)
    query(
        "UPDATE facturas SET metodo_pago = %s WHERE id_pedido = %s",
        (metodo, pid), fetch="insert"
    )
    return jresp({"ok": True, "msg": f"Método de pago actualizado a {metodo}"})

# ============================================================
# RUTA: CUPONES
# GET  /api/cupones/validar?codigo=X
# ============================================================
@app.route("/api/cupones/validar", methods=["GET"])
def validar_cupon():
    """GET con parámetro ?codigo=X — criterio método GET."""
    codigo = request.args.get("codigo", "").strip().upper()
    if not codigo:
        return jresp({"ok": False, "msg": "Código requerido"}, 400)
    row = query(
        "SELECT * FROM cupones WHERE codigo = %s AND activo = 1 AND (fecha_fin IS NULL OR fecha_fin >= CURDATE())",
        (codigo,), fetch="one"
    )
    if row:
        return jresp({"ok": True, "descuento": float(row["descuento"]), "codigo": codigo})
    return jresp({"ok": False, "msg": "Cupón inválido o vencido"}, 404)

# ============================================================
# RUTA: ESTADÍSTICAS (Dashboard)
# GET /api/stats
# ============================================================
@app.route("/api/stats", methods=["GET"])
def get_stats():
    hoy = date.today().isoformat()

    pedidos_hoy = query(
        "SELECT COUNT(*) AS total FROM pedidos WHERE DATE(fecha_pedido) = %s", (hoy,), fetch="one"
    ) or {"total": 0}

    ventas_hoy = query(
        """SELECT COALESCE(SUM(f.total), 0) AS total
           FROM facturas f JOIN pedidos p ON f.id_pedido = p.id_pedido
           WHERE DATE(p.fecha_pedido) = %s""",
        (hoy,), fetch="one"
    ) or {"total": 0}

    activos = query(
        "SELECT COUNT(*) AS total FROM pedidos WHERE estado IN ('pendiente','en_preparacion','listo')",
        fetch="one"
    ) or {"total": 0}

    productos = query(
        "SELECT COUNT(*) AS total FROM productos WHERE disponible = 1",
        fetch="one"
    ) or {"total": 0}

    mesas_ocupadas = query(
        "SELECT COUNT(*) AS total FROM mesas WHERE estado = 'ocupada'",
        fetch="one"
    ) or {"total": 0}

    ventas_cat = query(
        """SELECT c.nombre_categoria AS categoria, COALESCE(SUM(d.subtotal),0) AS total
           FROM categorias c
           LEFT JOIN productos p ON p.id_categoria = c.id_categoria
           LEFT JOIN detalle_pedidos d ON d.id_producto = p.id_producto
           GROUP BY c.id_categoria ORDER BY total DESC"""
    ) or []

    return jresp({
        "pedidos_hoy":   pedidos_hoy["total"],
        "ventas_hoy":    float(ventas_hoy["total"]),
        "activos":       activos["total"],
        "productos":     productos["total"],
        "mesas_ocupadas":mesas_ocupadas["total"],
        "ventas_cat":    ventas_cat
    })

# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    print("=" * 50)
    print("  🍽  Restaurante SENA — Backend Flask")
    print("  GA7-220501096-AA2-EV02")
    print("=" * 50)
    print(f"  API corriendo en: http://localhost:5000")
    print(f"  Base de datos:    {DB_CONFIG['database']} @ {DB_CONFIG['host']}")
    print("=" * 50)
    app.run(debug=True, host="0.0.0.0", port=5000)