"""
migrar.py — Actualiza una base restaurante_sena EXISTENTE a la versión
actual SIN borrar datos (no usa DROP DATABASE ni DROP TABLE).

Uso (desde la carpeta backend, con el entorno virtual activo):
    python migrar.py            → pide confirmación
    python migrar.py --si       → sin preguntar

- Haga un respaldo antes (python ../scripts/respaldo.py).
- Se puede ejecutar varias veces: solo aplica los cambios que falten.
- Funciona en MariaDB 10.4+ (XAMPP) y MySQL 8.0.19+.
"""

import re
import secrets
import sys

import mysql.connector

import config
import db
from dinero import calcular_totales

COLLATION = "utf8mb4_unicode_ci"


class Migrador:
    def __init__(self, conn):
        self.conn = conn
        self.cur = conn.cursor(dictionary=True)
        self.cambios = 0

    # --------------------------------------------------------
    # utilidades
    # --------------------------------------------------------
    def sql(self, sentencia, params=()):
        self.cur.execute(sentencia, params)
        return self.cur.fetchall() if self.cur.with_rows else None

    def paso(self, descripcion, sentencia, params=()):
        print(f"  - {descripcion}")
        self.sql(sentencia, params)
        self.conn.commit()
        self.cambios += 1

    def tabla_existe(self, tabla):
        return bool(self.sql(
            "SELECT 1 AS ok FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s", (tabla,)))

    def columna(self, tabla, col):
        filas = self.sql(
            "SELECT DATA_TYPE AS tipo, IS_NULLABLE AS nulo FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s", (tabla, col))
        return filas[0] if filas else None

    def indice_existe(self, tabla, indice):
        return bool(self.sql(
            "SELECT 1 AS ok FROM information_schema.STATISTICS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND INDEX_NAME = %s", (tabla, indice)))

    def restriccion_existe(self, nombre):
        return bool(self.sql(
            "SELECT 1 AS ok FROM information_schema.TABLE_CONSTRAINTS "
            "WHERE CONSTRAINT_SCHEMA = DATABASE() AND CONSTRAINT_NAME = %s", (nombre,)))

    def check_clausula(self, nombre):
        filas = self.sql(
            "SELECT CHECK_CLAUSE AS c FROM information_schema.CHECK_CONSTRAINTS "
            "WHERE CONSTRAINT_SCHEMA = DATABASE() AND CONSTRAINT_NAME = %s", (nombre,))
        return filas[0]["c"] if filas else None

    def agregar_columna(self, tabla, col, definicion):
        if not self.columna(tabla, col):
            self.paso(f"{tabla}: agregar columna {col}", f"ALTER TABLE {tabla} ADD COLUMN {col} {definicion}")
            return True
        return False

    def a_entero(self, tabla, col, definicion="INT NOT NULL"):
        info = self.columna(tabla, col)
        if info and info["tipo"] != "int":
            self.paso(f"{tabla}: {col} a pesos enteros (INT)", f"ALTER TABLE {tabla} MODIFY {col} {definicion}")

    def rellenar_codigos(self, tabla, col_id, col_codigo):
        """Asigna un código aleatorio a las filas que aún no lo tienen."""
        filas = self.sql(f"SELECT {col_id} AS id FROM {tabla} "
                         f"WHERE {col_codigo} IS NULL OR {col_codigo} = ''")
        if not filas:
            return
        print(f"  - {tabla}: generar {col_codigo} para {len(filas)} registros")
        for f in filas:
            self.sql(f"UPDATE {tabla} SET {col_codigo} = %s WHERE {col_id} = %s", (secrets.token_hex(16), f["id"]))
        self.conn.commit()
        self.cambios += 1

    def agregar_indice(self, tabla, indice, definicion):
        if not self.indice_existe(tabla, indice):
            self.paso(f"{tabla}: agregar índice {indice}", f"ALTER TABLE {tabla} ADD {definicion}")

    def reemplazar_check(self, tabla, nombre, clausula, contiene):
        actual = self.check_clausula(nombre)
        if actual is not None and contiene in actual:
            return
        if actual is not None:
            self.paso(f"{tabla}: quitar restricción antigua {nombre}",
                      f"ALTER TABLE {tabla} DROP CONSTRAINT {nombre}")
        self.paso(f"{tabla}: restricción {nombre}",
                  f"ALTER TABLE {tabla} ADD CONSTRAINT {nombre} CHECK ({clausula})")

    # --------------------------------------------------------
    # pasos de la migración
    # --------------------------------------------------------
    def ejecutar(self):
        self.charset()
        self.roles()
        self.usuarios()
        self.categorias()
        self.productos()
        self.mesas()
        self.pedidos()
        self.detalle()
        self.facturas()
        self.llamados()
        self.vistas()

    def charset(self):
        fila = self.sql("SELECT DEFAULT_COLLATION_NAME AS c FROM information_schema.SCHEMATA "
                        "WHERE SCHEMA_NAME = DATABASE()")[0]
        if fila["c"] != COLLATION:
            self.paso("base de datos: utf8mb4_unicode_ci",
                      f"ALTER DATABASE `{config.DB_NAME}` CHARACTER SET utf8mb4 COLLATE {COLLATION}")
        tablas = self.sql(
            "SELECT TABLE_NAME AS t FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() "
            "AND TABLE_TYPE = 'BASE TABLE' AND TABLE_COLLATION <> %s", (COLLATION,))
        for t in tablas:
            self.paso(f"{t['t']}: convertir a utf8mb4_unicode_ci",
                      f"ALTER TABLE `{t['t']}` CONVERT TO CHARACTER SET utf8mb4 COLLATE {COLLATION}")

    def roles(self):
        for nombre, desc in (("Administrador", "Acceso total al sistema"),
                             ("Chef", "Gestión de cocina y pedidos"),
                             ("Mesero", "Atención al cliente y entregas")):
            if not self.sql("SELECT 1 AS ok FROM roles WHERE nombre_rol = %s", (nombre,)):
                self.paso(f"roles: agregar {nombre}",
                          "INSERT INTO roles (nombre_rol, descripcion) VALUES (%s, %s)", (nombre, desc))

    def usuarios(self):
        self.agregar_columna("usuarios", "usuario", "VARCHAR(50) NULL AFTER nombre")
        sin_usuario = self.sql("SELECT id_usuario, correo FROM usuarios "
                               "WHERE usuario IS NULL OR usuario = '' ORDER BY id_usuario")
        if sin_usuario:
            usados = {r["usuario"] for r in self.sql(
                "SELECT usuario FROM usuarios WHERE usuario IS NOT NULL AND usuario <> ''")}
            for u in sin_usuario:
                base = re.sub(r"[^a-z0-9._-]", "", (u["correo"] or "").split("@")[0].lower())
                nombre = base or f"usuario{u['id_usuario']}"
                if nombre in usados:
                    nombre = f"{nombre}{u['id_usuario']}"
                usados.add(nombre)
                self.sql("UPDATE usuarios SET usuario = %s WHERE id_usuario = %s", (nombre, u["id_usuario"]))
                print(f"      {u['correo']} -> usuario '{nombre}'")
            self.conn.commit()
            self.cambios += 1
        if self.columna("usuarios", "usuario")["nulo"] == "YES":
            self.paso("usuarios: usuario obligatorio", "ALTER TABLE usuarios MODIFY usuario VARCHAR(50) NOT NULL")
        self.agregar_indice("usuarios", "uq_usuarios_usuario", "UNIQUE KEY uq_usuarios_usuario (usuario)")
        if self.columna("usuarios", "correo")["nulo"] == "NO":
            self.paso("usuarios: correo opcional", "ALTER TABLE usuarios MODIFY correo VARCHAR(150) DEFAULT NULL")
        # Los usuarios existentes deberán cambiar su contraseña al ingresar.
        self.agregar_columna("usuarios", "debe_cambiar_clave", "TINYINT(1) NOT NULL DEFAULT 1 AFTER contrasena_hash")
        self.agregar_columna("usuarios", "ultimo_ingreso", "DATETIME DEFAULT NULL")

    def categorias(self):
        if self.agregar_columna("categorias", "orden", "INT NOT NULL DEFAULT 0 AFTER descripcion"):
            self.paso("categorias: orden inicial", "UPDATE categorias SET orden = id_categoria")

    def productos(self):
        self.a_entero("productos", "precio")
        self.agregar_columna("productos", "emoji", "VARCHAR(16) DEFAULT NULL AFTER precio")
        self.agregar_columna("productos", "activo", "TINYINT(1) NOT NULL DEFAULT 1 AFTER disponible")

    def mesas(self):
        self.reemplazar_check("mesas", "chk_mesas_numero", "numero_mesa BETWEEN 1 AND 999", "999")

    def pedidos(self):
        self.agregar_columna("pedidos", "id_cupon", "INT DEFAULT NULL AFTER id_usuario")
        if not self.restriccion_existe("fk_pedidos_cupon"):
            self.paso("pedidos: llave foránea del cupón",
                      "ALTER TABLE pedidos ADD CONSTRAINT fk_pedidos_cupon "
                      "FOREIGN KEY (id_cupon) REFERENCES cupones (id_cupon)")
        if self.columna("pedidos", "numero_pedido")["nulo"] == "NO":
            self.paso("pedidos: numero_pedido se asigna al guardar",
                      "ALTER TABLE pedidos MODIFY numero_pedido VARCHAR(20) DEFAULT NULL")

        self.agregar_columna("pedidos", "token", "CHAR(32) NULL AFTER numero_pedido")
        self.rellenar_codigos("pedidos", "id_pedido", "token")
        if self.columna("pedidos", "token")["nulo"] == "YES":
            self.paso("pedidos: token obligatorio", "ALTER TABLE pedidos MODIFY token CHAR(32) NOT NULL")
        self.agregar_indice("pedidos", "uq_pedidos_token", "UNIQUE KEY uq_pedidos_token (token)")

        for col in ("subtotal", "descuento", "impuesto", "propina", "total"):
            self.agregar_columna("pedidos", col, "INT NOT NULL DEFAULT 0 AFTER notas"
                                 if col == "subtotal" else "INT NOT NULL DEFAULT 0")
        self.calcular_totales_pedidos()
        self.agregar_columna("pedidos", "fecha_listo", "DATETIME DEFAULT NULL AFTER fecha_pedido")
        self.agregar_indice("pedidos", "idx_pedidos_estado", "KEY idx_pedidos_estado (estado)")
        self.agregar_indice("pedidos", "idx_pedidos_fecha", "KEY idx_pedidos_fecha (fecha_pedido)")

    def calcular_totales_pedidos(self):
        """Llena los totales de los pedidos antiguos (desde su factura o su detalle)."""
        tiene_iva = bool(self.columna("facturas", "iva"))
        col_imp = "iva" if tiene_iva else "impuesto"
        col_prop = "servicio" if tiene_iva else "propina"
        pedidos = self.sql(
            f"""SELECT p.id_pedido,
                       (SELECT COALESCE(SUM(d.subtotal), 0) FROM detalle_pedidos d
                         WHERE d.id_pedido = p.id_pedido) AS sub_detalle,
                       f.subtotal AS f_sub, f.{col_imp} AS f_imp, f.{col_prop} AS f_prop, f.total AS f_total
                FROM pedidos p LEFT JOIN facturas f ON f.id_pedido = p.id_pedido
                WHERE p.total = 0 AND EXISTS (SELECT 1 FROM detalle_pedidos d WHERE d.id_pedido = p.id_pedido)""")
        if not pedidos:
            return
        print(f"  - pedidos: calcular totales de {len(pedidos)} pedidos antiguos")
        for p in pedidos:
            if p["f_total"] is not None:
                sub, imp, prop, tot = (int(round(float(p[k]))) for k in ("f_sub", "f_imp", "f_prop", "f_total"))
                desc = max(0, sub + imp + prop - tot)
            else:
                t = calcular_totales(int(round(float(p["sub_detalle"]))), 0, True)
                sub, desc, imp, prop, tot = t["subtotal"], t["descuento"], t["impuesto"], t["propina"], t["total"]
            self.sql("UPDATE pedidos SET subtotal=%s, descuento=%s, impuesto=%s, propina=%s, total=%s "
                     "WHERE id_pedido=%s", (sub, desc, imp, prop, tot, p["id_pedido"]))
        self.conn.commit()
        self.cambios += 1

    def detalle(self):
        self.agregar_columna("detalle_pedidos", "nombre_producto", "VARCHAR(100) DEFAULT NULL AFTER id_producto")
        if self.sql("SELECT 1 AS ok FROM detalle_pedidos WHERE nombre_producto IS NULL LIMIT 1"):
            self.paso("detalle_pedidos: guardar nombre de cada producto vendido",
                      "UPDATE detalle_pedidos d JOIN productos p ON d.id_producto = p.id_producto "
                      "SET d.nombre_producto = p.nombre WHERE d.nombre_producto IS NULL")
        self.a_entero("detalle_pedidos", "precio_unit")
        self.a_entero("detalle_pedidos", "subtotal")

    def facturas(self):
        # Las facturas antiguas se calcularon con IVA 19 % + servicio 10 %:
        # se conservan sus valores y se marcan como "IVA 19 %".
        renombro = False
        if self.columna("facturas", "iva"):
            self.paso("facturas: columna iva -> impuesto", "ALTER TABLE facturas CHANGE iva impuesto INT NOT NULL")
            renombro = True
        if self.columna("facturas", "servicio"):
            self.paso("facturas: columna servicio -> propina",
                      "ALTER TABLE facturas CHANGE servicio propina INT NOT NULL DEFAULT 0")
        self.a_entero("facturas", "subtotal")
        self.a_entero("facturas", "total")
        self.a_entero("facturas", "impuesto")
        self.a_entero("facturas", "propina", "INT NOT NULL DEFAULT 0")
        self.agregar_columna("facturas", "descuento", "INT NOT NULL DEFAULT 0 AFTER subtotal")
        nuevo_nombre = self.agregar_columna(
            "facturas", "impuesto_nombre", "VARCHAR(40) NOT NULL DEFAULT 'Impoconsumo' AFTER descuento")
        self.agregar_columna("facturas", "impuesto_pct", "DECIMAL(5,2) NOT NULL DEFAULT 8.00 AFTER impuesto_nombre")
        if renombro and nuevo_nombre:
            self.paso("facturas: marcar facturas antiguas como IVA 19 %",
                      "UPDATE facturas SET impuesto_nombre = 'IVA', impuesto_pct = 19")
        self.agregar_columna("facturas", "codigo_verificacion", "CHAR(32) DEFAULT NULL AFTER numero_factura")
        self.rellenar_codigos("facturas", "id_factura", "codigo_verificacion")
        self.agregar_indice("facturas", "uq_facturas_verif", "UNIQUE KEY uq_facturas_verif (codigo_verificacion)")
        if not self.indice_existe("facturas", "uq_facturas_pedido"):
            repetidas = self.sql("SELECT id_pedido FROM facturas GROUP BY id_pedido HAVING COUNT(*) > 1")
            if repetidas:
                print(f"  ! facturas: hay pedidos con más de una factura {[r['id_pedido'] for r in repetidas]};"
                      " no se agregó la restricción de factura única. Revíselos manualmente.")
            else:
                self.agregar_indice("facturas", "uq_facturas_pedido", "UNIQUE KEY uq_facturas_pedido (id_pedido)")
        self.agregar_indice("facturas", "idx_facturas_fecha", "KEY idx_facturas_fecha (fecha_factura)")
        self.reemplazar_check("facturas", "chk_facturas_total", "total >= 0", ">=")

    def llamados(self):
        if not self.tabla_existe("llamados"):
            self.paso("crear tabla llamados (botón Llamar mesero)", """
                CREATE TABLE llamados (
                  id_llamado      INT NOT NULL AUTO_INCREMENT,
                  id_mesa         INT NOT NULL,
                  estado          VARCHAR(20) NOT NULL DEFAULT 'pendiente',
                  fecha_solicitud DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  fecha_atencion  DATETIME DEFAULT NULL,
                  id_usuario      INT DEFAULT NULL,
                  PRIMARY KEY (id_llamado),
                  KEY idx_llamados_estado (estado),
                  CONSTRAINT fk_llamados_mesa    FOREIGN KEY (id_mesa)    REFERENCES mesas (id_mesa),
                  CONSTRAINT fk_llamados_usuario FOREIGN KEY (id_usuario) REFERENCES usuarios (id_usuario),
                  CONSTRAINT chk_llamados_estado CHECK (estado IN ('pendiente','atendido'))
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""")

    def vistas(self):
        """Recrea las vistas de reportes tal como están en restaurante_sena_completo.sql."""
        texto = (config.BACKEND_DIR / "restaurante_sena_completo.sql").read_text(encoding="utf-8")
        vistas = [s for s in db.dividir_sql(texto) if s.upper().startswith("CREATE OR REPLACE VIEW")]
        for v in vistas:
            self.sql(v)
        self.conn.commit()
        print(f"  - vistas de reportes actualizadas ({len(vistas)})")


def main():
    # La consola de Windows puede no soportar todos los caracteres.
    try:
        sys.stdout.reconfigure(errors="replace")
    except AttributeError:
        pass
    print("=" * 60)
    print("  Migración de Restaurante SENA (sin borrar datos)")
    print(f"  Base: {config.DB_NAME} @ {config.DB_HOST}:{config.DB_PORT}")
    print("=" * 60)
    if "--si" not in sys.argv:
        print("Se recomienda hacer un respaldo antes (scripts/respaldo.py).")
        if input("¿Continuar con la migración? (s/N): ").strip().lower() not in ("s", "si", "sí"):
            print("Cancelado.")
            return 1
    try:
        conn = mysql.connector.connect(**db.parametros_conexion())
    except mysql.connector.Error as e:
        print(f"ERROR: no se pudo conectar a la base de datos: {e}")
        return 2
    try:
        m = Migrador(conn)
        m.ejecutar()
    except mysql.connector.Error as e:
        print(f"\nERROR durante la migración: {e}")
        print("Los pasos anteriores ya quedaron aplicados; corrija el problema y vuelva a ejecutar.")
        return 3
    finally:
        conn.close()
    print("-" * 60)
    print(f"Migración terminada. Cambios aplicados: {m.cambios}" if m.cambios
          else "La base ya estaba actualizada. No hubo cambios.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
