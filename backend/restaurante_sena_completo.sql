-- ============================================================
--  restaurante_sena_completo.sql
--  Instalación NUEVA de la base de datos — Restaurante SENA
--
--  Compatible con MariaDB 10.4+ (XAMPP) y MySQL 8.
--
--  ¡ATENCIÓN! Este script BORRA la base restaurante_sena si ya
--  existe. Para actualizar una instalación que ya tiene datos use:
--      python backend/migrar.py
--
--  Importar desde la consola de XAMPP:
--      mysql -u root -p --default-character-set=utf8mb4 < restaurante_sena_completo.sql
--  o desde phpMyAdmin → Importar.
-- ============================================================

SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;

-- 1. CREAR Y SELECCIONAR BASE DE DATOS
DROP DATABASE IF EXISTS restaurante_sena;
CREATE DATABASE restaurante_sena
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
USE restaurante_sena;

-- ============================================================
-- 2. TABLAS
--    Todos los valores de dinero se guardan en pesos enteros (INT).
-- ============================================================

-- ROLES
CREATE TABLE roles (
  id_rol      INT NOT NULL AUTO_INCREMENT,
  nombre_rol  VARCHAR(50) NOT NULL,
  descripcion VARCHAR(150) DEFAULT NULL,
  PRIMARY KEY (id_rol),
  UNIQUE KEY uq_roles_nombre (nombre_rol)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- USUARIOS (personal del restaurante)
CREATE TABLE usuarios (
  id_usuario         INT NOT NULL AUTO_INCREMENT,
  id_rol             INT NOT NULL,
  nombre             VARCHAR(100) NOT NULL,
  usuario            VARCHAR(50)  NOT NULL,
  correo             VARCHAR(150) DEFAULT NULL,
  contrasena_hash    VARCHAR(255) NOT NULL,
  debe_cambiar_clave TINYINT(1) NOT NULL DEFAULT 1,
  activo             TINYINT(1) NOT NULL DEFAULT 1,
  fecha_creacion     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  ultimo_ingreso     DATETIME DEFAULT NULL,
  PRIMARY KEY (id_usuario),
  UNIQUE KEY uq_usuarios_usuario (usuario),
  UNIQUE KEY uq_usuarios_correo (correo),
  CONSTRAINT fk_usuarios_rol FOREIGN KEY (id_rol) REFERENCES roles (id_rol)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- CATEGORÍAS
CREATE TABLE categorias (
  id_categoria     INT NOT NULL AUTO_INCREMENT,
  nombre_categoria VARCHAR(80) NOT NULL,
  descripcion      VARCHAR(200) DEFAULT NULL,
  orden            INT NOT NULL DEFAULT 0,
  activo           TINYINT(1) NOT NULL DEFAULT 1,
  PRIMARY KEY (id_categoria),
  UNIQUE KEY uq_categorias_nombre (nombre_categoria)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- PRODUCTOS
--   disponible = se puede pedir hoy (p. ej. se agotó)
--   activo     = 0 cuando el producto se elimina de la carta
--                (no se borra para no perder el historial de ventas)
CREATE TABLE productos (
  id_producto  INT NOT NULL AUTO_INCREMENT,
  id_categoria INT NOT NULL,
  nombre       VARCHAR(100) NOT NULL,
  descripcion  VARCHAR(300) DEFAULT NULL,
  precio       INT NOT NULL,
  emoji        VARCHAR(16) DEFAULT NULL,
  disponible   TINYINT(1) NOT NULL DEFAULT 1,
  activo       TINYINT(1) NOT NULL DEFAULT 1,
  imagen_url   VARCHAR(255) DEFAULT NULL,
  PRIMARY KEY (id_producto),
  CONSTRAINT fk_productos_cat FOREIGN KEY (id_categoria) REFERENCES categorias (id_categoria),
  CONSTRAINT chk_productos_precio CHECK (precio > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- MESAS
CREATE TABLE mesas (
  id_mesa     INT NOT NULL AUTO_INCREMENT,
  numero_mesa INT NOT NULL,
  capacidad   INT NOT NULL DEFAULT 4,
  estado      VARCHAR(20) NOT NULL DEFAULT 'disponible',
  codigo_qr   VARCHAR(255) DEFAULT NULL,
  PRIMARY KEY (id_mesa),
  UNIQUE KEY uq_mesas_numero (numero_mesa),
  CONSTRAINT chk_mesas_estado CHECK (estado IN ('disponible','ocupada','reservada','inactiva')),
  CONSTRAINT chk_mesas_numero CHECK (numero_mesa BETWEEN 1 AND 999)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- CUPONES (descuento en porcentaje)
CREATE TABLE cupones (
  id_cupon  INT NOT NULL AUTO_INCREMENT,
  codigo    VARCHAR(20) NOT NULL,
  descuento DECIMAL(5,2) NOT NULL,
  activo    TINYINT(1) NOT NULL DEFAULT 1,
  fecha_fin DATE DEFAULT NULL,
  PRIMARY KEY (id_cupon),
  UNIQUE KEY uq_cupones_cod (codigo),
  CONSTRAINT chk_cupon_desc CHECK (descuento BETWEEN 1 AND 100)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- PEDIDOS
--   token: identificador secreto con el que el comensal consulta su
--          pedido y su factura (no se puede adivinar como el id).
--   Los totales se calculan en el servidor al crear el pedido.
CREATE TABLE pedidos (
  id_pedido     INT NOT NULL AUTO_INCREMENT,
  id_mesa       INT NOT NULL,
  id_usuario    INT DEFAULT NULL,
  id_cupon      INT DEFAULT NULL,
  numero_pedido VARCHAR(20) DEFAULT NULL,
  token         CHAR(32) NOT NULL,
  estado        VARCHAR(20) NOT NULL DEFAULT 'pendiente',
  notas         VARCHAR(300) DEFAULT NULL,
  subtotal      INT NOT NULL DEFAULT 0,
  descuento     INT NOT NULL DEFAULT 0,
  impuesto      INT NOT NULL DEFAULT 0,
  propina       INT NOT NULL DEFAULT 0,
  total         INT NOT NULL DEFAULT 0,
  fecha_pedido  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  fecha_listo   DATETIME DEFAULT NULL,
  fecha_entrega DATETIME DEFAULT NULL,
  PRIMARY KEY (id_pedido),
  UNIQUE KEY uq_pedidos_numero (numero_pedido),
  UNIQUE KEY uq_pedidos_token (token),
  KEY idx_pedidos_estado (estado),
  KEY idx_pedidos_fecha (fecha_pedido),
  CONSTRAINT fk_pedidos_mesa    FOREIGN KEY (id_mesa)    REFERENCES mesas (id_mesa),
  CONSTRAINT fk_pedidos_usuario FOREIGN KEY (id_usuario) REFERENCES usuarios (id_usuario),
  CONSTRAINT fk_pedidos_cupon   FOREIGN KEY (id_cupon)   REFERENCES cupones (id_cupon),
  CONSTRAINT chk_pedidos_estado CHECK (estado IN ('pendiente','en_preparacion','listo','entregado','cancelado'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- DETALLE DE PEDIDOS
--   nombre_producto guarda el nombre tal como se vendió.
CREATE TABLE detalle_pedidos (
  id_detalle      INT NOT NULL AUTO_INCREMENT,
  id_pedido       INT NOT NULL,
  id_producto     INT NOT NULL,
  nombre_producto VARCHAR(100) DEFAULT NULL,
  cantidad        INT NOT NULL,
  precio_unit     INT NOT NULL,
  subtotal        INT NOT NULL,
  PRIMARY KEY (id_detalle),
  CONSTRAINT fk_detalle_pedido  FOREIGN KEY (id_pedido)   REFERENCES pedidos (id_pedido),
  CONSTRAINT fk_detalle_prod    FOREIGN KEY (id_producto) REFERENCES productos (id_producto),
  CONSTRAINT chk_detalle_cant   CHECK (cantidad BETWEEN 1 AND 10),
  CONSTRAINT chk_detalle_precio CHECK (precio_unit > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- FACTURAS (se generan cuando el pedido se entrega)
CREATE TABLE facturas (
  id_factura          INT NOT NULL AUTO_INCREMENT,
  id_pedido           INT NOT NULL,
  numero_factura      VARCHAR(20) NOT NULL,
  codigo_verificacion CHAR(32) DEFAULT NULL,
  subtotal            INT NOT NULL,
  descuento           INT NOT NULL DEFAULT 0,
  impuesto_nombre     VARCHAR(40) NOT NULL DEFAULT 'Impoconsumo',
  impuesto_pct        DECIMAL(5,2) NOT NULL DEFAULT 8.00,
  impuesto            INT NOT NULL,
  propina             INT NOT NULL DEFAULT 0,
  total               INT NOT NULL,
  metodo_pago         VARCHAR(30) NOT NULL DEFAULT 'efectivo',
  fecha_factura       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id_factura),
  UNIQUE KEY uq_facturas_numero (numero_factura),
  UNIQUE KEY uq_facturas_pedido (id_pedido),
  UNIQUE KEY uq_facturas_verif (codigo_verificacion),
  KEY idx_facturas_fecha (fecha_factura),
  CONSTRAINT fk_facturas_pedido FOREIGN KEY (id_pedido) REFERENCES pedidos (id_pedido),
  CONSTRAINT chk_facturas_pago  CHECK (metodo_pago IN ('efectivo','tarjeta','digital')),
  CONSTRAINT chk_facturas_total CHECK (total >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- LLAMADOS AL MESERO (botón "Llamar mesero" del comensal)
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- 3. DATOS INICIALES
-- ============================================================

INSERT INTO roles (nombre_rol, descripcion) VALUES
  ('Administrador', 'Acceso total al sistema'),
  ('Chef',          'Gestión de cocina y pedidos'),
  ('Mesero',        'Atención al cliente y entregas');

-- Usuarios iniciales. Las contraseñas TEMPORALES están en el README;
-- aquí solo se guarda su hash (werkzeug/scrypt). El sistema obliga a
-- cambiarlas en el primer ingreso (debe_cambiar_clave = 1).
INSERT INTO usuarios (id_rol, nombre, usuario, correo, contrasena_hash, debe_cambiar_clave) VALUES
  (1, 'Administrador', 'admin',  NULL, 'scrypt:32768:8:1$pnv2Z3jY2g7vOd9F$a5cfeb846e7c420ba72fd12bc5be7a0d1acce8cb352764dde56d40d2e62ff93fb3ea93f920174c63798322a22058404b6c47e620a6f263fe1f97a125efd463c3', 1),
  (2, 'Chef Principal', 'chef',  NULL, 'scrypt:32768:8:1$jebP6WRgYtzQAEUp$864e0e80a59858995621d6829cfa70c10f4a636533912cbb404fab28258ef8f6b1eb53efc3205ec943a2012ef2e221a2f9a017ea2161e30d32b0751ab14de3c9', 1),
  (3, 'Mesero 1',      'mesero', NULL, 'scrypt:32768:8:1$nt7v1TxGFnicv6cg$641ee761bb804f98e0fda0d0b850e4abe75cec1db085c0820871fb5eb72e4861779e8c7b44fbfd9f1c8d75151b40d0b4bd84201ce4b62034b9f235beda07b8c2', 1);

INSERT INTO categorias (nombre_categoria, descripcion, orden) VALUES
  ('Entradas',    'Aperitivos y entradas del menú',       1),
  ('Principales', 'Platos fuertes y principales',         2),
  ('Bebidas',     'Bebidas frías, calientes y naturales', 3),
  ('Postres',     'Dulces y postres artesanales',         4);

INSERT INTO productos (id_categoria, nombre, descripcion, precio, emoji) VALUES
  -- Entradas
  (1, 'Patacones con Hogao',   'Tostones de plátano verde con salsa de tomate y cebolla criolla',    12500, '🫓'),
  (1, 'Empanadas (x3)',        'Empanadas de pipián con ají y guacamole casero',                      9800, '🥟'),
  (1, 'Ceviche de Camarón',    'Camarón fresco, limón, cilantro y cebolla morada',                   18000, '🍤'),
  (1, 'Arepas con Queso',      'Arepas de chócolo con queso campesino derretido',                     8500, '🫓'),
  -- Principales
  (2, 'Bandeja Paisa',         'Frijoles, chicharrón, carne molida, huevo, aguacate, arroz y arepa', 28500, '🍛'),
  (2, 'Sancocho Trifásico',    'Sopa con pollo, res, cerdo, papa, yuca y mazorca',                   24000, '🍲'),
  (2, 'Trucha a la Plancha',   'Trucha fresca con papas al vapor y ensalada criolla',                32000, '🐟'),
  (2, 'Posta Negra',           'Carne de res en salsa negra con arroz de coco y tajadas',            26000, '🥩'),
  (2, 'Arroz con Pollo',       'Arroz amarillo con pollo, vegetales y aliños criollos',              22000, '🍗'),
  -- Bebidas
  (3, 'Limonada de Coco',      'Limón natural, leche de coco y azúcar morena',                        7500, '🥥'),
  (3, 'Jugo de Lulo',          'Lulo natural recién exprimido, frío o natural',                       6000, '🍊'),
  (3, 'Agua Aromática',        'Hierbas frescas: menta, manzanilla o canela',                         3500, '🌿'),
  (3, 'Refajo',                'Cerveza + Colombiana, la combinación clásica',                        9000, '🍺'),
  (3, 'Chocolate Santafereño', 'Chocolate espeso con queso y pan de bono',                            6500, '☕'),
  -- Postres
  (4, 'Tres Leches',           'Bizcocho esponjoso bañado en tres leches con nata',                  11000, '🎂'),
  (4, 'Arroz con Leche',       'Cremoso arroz con leche, canela y pasas',                             8500, '🍚'),
  (4, 'Brownie de Chocolate',  'Brownie tibio con helado de vainilla artesanal',                     13500, '🍫'),
  (4, 'Flan de Caramelo',      'Flan casero con salsa de caramelo artesanal',                        10000, '🍮');

INSERT INTO mesas (numero_mesa, capacidad, estado) VALUES
  (1, 2, 'disponible'),  (2, 4, 'disponible'),  (3, 4, 'disponible'),  (4, 6, 'disponible'),
  (5, 4, 'disponible'),  (6, 2, 'disponible'),  (7, 8, 'disponible'),  (8, 4, 'disponible'),
  (9, 4, 'disponible'),  (10, 6, 'disponible'), (11, 2, 'disponible'), (12, 4, 'disponible'),
  (13, 4, 'disponible'), (14, 6, 'disponible'), (15, 4, 'disponible'), (16, 8, 'inactiva'),
  (17, 4, 'disponible'), (18, 4, 'disponible'), (19, 2, 'disponible'), (20, 6, 'disponible');

INSERT INTO cupones (codigo, descuento, fecha_fin) VALUES
  ('BIENVENIDO', 10.00, NULL),
  ('SENA2026',   15.00, '2026-12-31');

-- ============================================================
-- 4. VISTAS PARA REPORTES (solo cuentan pedidos ENTREGADOS)
-- ============================================================

CREATE OR REPLACE VIEW v_pedidos_detalle AS
  SELECT p.id_pedido, p.numero_pedido, p.estado, p.notas,
         p.fecha_pedido, p.fecha_entrega, m.numero_mesa,
         p.subtotal, p.descuento, p.impuesto, p.propina, p.total,
         f.numero_factura, f.metodo_pago
  FROM pedidos p
  JOIN mesas m ON p.id_mesa = m.id_mesa
  LEFT JOIN facturas f ON f.id_pedido = p.id_pedido;

CREATE OR REPLACE VIEW v_ventas_por_categoria AS
  SELECT c.id_categoria, c.nombre_categoria,
         COUNT(DISTINCT p.id_pedido)  AS num_pedidos,
         COALESCE(SUM(d.cantidad), 0) AS unidades_vendidas,
         COALESCE(SUM(d.subtotal), 0) AS ingresos_brutos
  FROM categorias c
  LEFT JOIN productos pr ON pr.id_categoria = c.id_categoria
  LEFT JOIN (detalle_pedidos d
             JOIN pedidos p ON p.id_pedido = d.id_pedido AND p.estado = 'entregado')
         ON d.id_producto = pr.id_producto
  GROUP BY c.id_categoria, c.nombre_categoria;

CREATE OR REPLACE VIEW v_productos_populares AS
  SELECT pr.id_producto, pr.nombre, c.nombre_categoria, pr.precio,
         COALESCE(SUM(d.cantidad), 0) AS veces_pedido,
         COALESCE(SUM(d.subtotal), 0) AS ingresos_total
  FROM productos pr
  JOIN categorias c ON pr.id_categoria = c.id_categoria
  LEFT JOIN (detalle_pedidos d
             JOIN pedidos p ON p.id_pedido = d.id_pedido AND p.estado = 'entregado')
         ON d.id_producto = pr.id_producto
  GROUP BY pr.id_producto, pr.nombre, c.nombre_categoria, pr.precio;

CREATE OR REPLACE VIEW v_resumen_diario AS
  SELECT DATE(p.fecha_pedido) AS fecha,
         COUNT(*) AS total_pedidos,
         SUM(CASE WHEN p.estado = 'entregado' THEN 1 ELSE 0 END) AS entregados,
         SUM(CASE WHEN p.estado = 'cancelado' THEN 1 ELSE 0 END) AS cancelados,
         SUM(CASE WHEN p.estado = 'entregado' THEN p.total ELSE 0 END) AS ingresos
  FROM pedidos p
  GROUP BY DATE(p.fecha_pedido);

-- ============================================================
-- 5. VERIFICACIÓN
-- ============================================================
SELECT 'Base de datos lista' AS resultado;
SELECT tabla, total FROM (
  SELECT 'roles' AS tabla, COUNT(*) AS total FROM roles UNION ALL
  SELECT 'usuarios',   COUNT(*) FROM usuarios   UNION ALL
  SELECT 'categorias', COUNT(*) FROM categorias UNION ALL
  SELECT 'productos',  COUNT(*) FROM productos  UNION ALL
  SELECT 'mesas',      COUNT(*) FROM mesas      UNION ALL
  SELECT 'cupones',    COUNT(*) FROM cupones
) t;
