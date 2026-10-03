-- ============================================================
--  restaurante_sena_completo.sql
--  Script de instalación completa de la BD
--  GA7-220501096-AA2-EV02 — Restaurante SENA
--  Ejecutar en MySQL Workbench
-- ============================================================

-- 1. CREAR Y SELECCIONAR BASE DE DATOS
DROP DATABASE IF EXISTS restaurante_sena;
CREATE DATABASE restaurante_sena
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
USE restaurante_sena;

-- ============================================================
-- 2. TABLAS
-- ============================================================

-- ROLES
CREATE TABLE roles (
  id_rol      INT NOT NULL AUTO_INCREMENT,
  nombre_rol  VARCHAR(50) NOT NULL,
  descripcion VARCHAR(150) DEFAULT NULL,
  PRIMARY KEY (id_rol),
  UNIQUE KEY uq_roles_nombre (nombre_rol)
);

-- USUARIOS
CREATE TABLE usuarios (
  id_usuario      INT NOT NULL AUTO_INCREMENT,
  id_rol          INT NOT NULL,
  nombre          VARCHAR(100) NOT NULL,
  correo          VARCHAR(150) NOT NULL,
  contrasena_hash VARCHAR(255) NOT NULL,
  activo          TINYINT(1) NOT NULL DEFAULT 1,
  fecha_creacion  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id_usuario),
  UNIQUE KEY uq_usuarios_correo (correo),
  CONSTRAINT fk_usuarios_rol FOREIGN KEY (id_rol) REFERENCES roles (id_rol)
);

-- CATEGORÍAS
CREATE TABLE categorias (
  id_categoria    INT NOT NULL AUTO_INCREMENT,
  nombre_categoria VARCHAR(80) NOT NULL,
  descripcion     VARCHAR(200) DEFAULT NULL,
  activo          TINYINT(1) NOT NULL DEFAULT 1,
  PRIMARY KEY (id_categoria),
  UNIQUE KEY uq_categorias_nombre (nombre_categoria)
);

-- PRODUCTOS
CREATE TABLE productos (
  id_producto  INT NOT NULL AUTO_INCREMENT,
  id_categoria INT NOT NULL,
  nombre       VARCHAR(100) NOT NULL,
  descripcion  VARCHAR(300) DEFAULT NULL,
  precio       DECIMAL(10,2) NOT NULL,
  disponible   TINYINT(1) NOT NULL DEFAULT 1,
  imagen_url   VARCHAR(255) DEFAULT NULL,
  PRIMARY KEY (id_producto),
  CONSTRAINT fk_productos_cat FOREIGN KEY (id_categoria) REFERENCES categorias (id_categoria),
  CONSTRAINT chk_productos_precio CHECK (precio > 0)
);

-- MESAS
CREATE TABLE mesas (
  id_mesa     INT NOT NULL AUTO_INCREMENT,
  numero_mesa INT NOT NULL,
  capacidad   INT NOT NULL DEFAULT 4,
  estado      VARCHAR(20) NOT NULL DEFAULT 'disponible',
  codigo_qr   VARCHAR(255) DEFAULT NULL,
  PRIMARY KEY (id_mesa),
  UNIQUE KEY uq_mesas_numero (numero_mesa),
  CONSTRAINT chk_mesas_estado  CHECK (estado IN ('disponible','ocupada','reservada','inactiva')),
  CONSTRAINT chk_mesas_numero  CHECK (numero_mesa BETWEEN 1 AND 50)
);

-- PEDIDOS
CREATE TABLE pedidos (
  id_pedido     INT NOT NULL AUTO_INCREMENT,
  id_mesa       INT NOT NULL,
  id_usuario    INT DEFAULT NULL,
  numero_pedido VARCHAR(20) NOT NULL,
  estado        VARCHAR(20) NOT NULL DEFAULT 'pendiente',
  notas         VARCHAR(300) DEFAULT NULL,
  fecha_pedido  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  fecha_entrega DATETIME DEFAULT NULL,
  PRIMARY KEY (id_pedido),
  UNIQUE KEY uq_pedidos_numero (numero_pedido),
  CONSTRAINT fk_pedidos_mesa    FOREIGN KEY (id_mesa)    REFERENCES mesas (id_mesa),
  CONSTRAINT fk_pedidos_usuario FOREIGN KEY (id_usuario) REFERENCES usuarios (id_usuario),
  CONSTRAINT chk_pedidos_estado CHECK (estado IN ('pendiente','en_preparacion','listo','entregado','cancelado'))
);

-- DETALLE DE PEDIDOS
CREATE TABLE detalle_pedidos (
  id_detalle  INT NOT NULL AUTO_INCREMENT,
  id_pedido   INT NOT NULL,
  id_producto INT NOT NULL,
  cantidad    INT NOT NULL,
  precio_unit DECIMAL(10,2) NOT NULL,
  subtotal    DECIMAL(10,2) NOT NULL,
  PRIMARY KEY (id_detalle),
  CONSTRAINT fk_detalle_pedido  FOREIGN KEY (id_pedido)   REFERENCES pedidos (id_pedido),
  CONSTRAINT fk_detalle_prod    FOREIGN KEY (id_producto) REFERENCES productos (id_producto),
  CONSTRAINT chk_detalle_cant   CHECK (cantidad BETWEEN 1 AND 10),
  CONSTRAINT chk_detalle_precio CHECK (precio_unit > 0)
);

-- FACTURAS
CREATE TABLE facturas (
  id_factura     INT NOT NULL AUTO_INCREMENT,
  id_pedido      INT NOT NULL,
  numero_factura VARCHAR(20) NOT NULL,
  subtotal       DECIMAL(10,2) NOT NULL,
  iva            DECIMAL(10,2) NOT NULL,
  servicio       DECIMAL(10,2) NOT NULL,
  total          DECIMAL(10,2) NOT NULL,
  metodo_pago    VARCHAR(30) NOT NULL DEFAULT 'efectivo',
  fecha_factura  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id_factura),
  UNIQUE KEY uq_facturas_numero (numero_factura),
  CONSTRAINT fk_facturas_pedido FOREIGN KEY (id_pedido) REFERENCES pedidos (id_pedido),
  CONSTRAINT chk_facturas_pago  CHECK (metodo_pago IN ('efectivo','tarjeta','digital')),
  CONSTRAINT chk_facturas_total CHECK (total > 0)
);

-- CARRITOS (temporal)
CREATE TABLE carritos (
  id_carrito    INT NOT NULL AUTO_INCREMENT,
  id_mesa       INT NOT NULL,
  id_producto   INT NOT NULL,
  cantidad      INT NOT NULL DEFAULT 1,
  fecha_agregado DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id_carrito),
  CONSTRAINT fk_carritos_mesa    FOREIGN KEY (id_mesa)    REFERENCES mesas (id_mesa),
  CONSTRAINT fk_carritos_producto FOREIGN KEY (id_producto) REFERENCES productos (id_producto),
  CONSTRAINT chk_carritos_cant   CHECK (cantidad BETWEEN 1 AND 10)
);

-- CUPONES
CREATE TABLE cupones (
  id_cupon  INT NOT NULL AUTO_INCREMENT,
  codigo    VARCHAR(20) NOT NULL,
  descuento DECIMAL(5,2) NOT NULL,
  activo    TINYINT(1) NOT NULL DEFAULT 1,
  fecha_fin DATE DEFAULT NULL,
  PRIMARY KEY (id_cupon),
  UNIQUE KEY uq_cupones_cod (codigo),
  CONSTRAINT chk_cupon_desc CHECK (descuento BETWEEN 1 AND 100)
);

-- ============================================================
-- 3. DATOS INICIALES
-- ============================================================

-- Roles
INSERT INTO roles (nombre_rol, descripcion) VALUES
  ('Administrador', 'Acceso total al sistema'),
  ('Chef',          'Gestión de cocina y pedidos'),
  ('Mesero',        'Atención al cliente y entregas'),
  ('Cliente',       'Realización de pedidos');

-- Usuarios (contraseñas en SHA-256)
-- admin123  → 240be518fabd2724ddb6f04eeb1da5967448d7e831c08c8fa822809f74c720a9
-- chef123   → b14361404c078ffd549c03db443c3fede2f3e534d73f78f77301ed97d4a436a9
-- mesero123 → 5e52c7e19bb3f99b0e677e40aef50fb4f1d4b91bda46b9f2de6b0bcdc8ad1e2a
INSERT INTO usuarios (id_rol, nombre, correo, contrasena_hash) VALUES
  (1, 'Admin SENA',    'admin@sena.edu.co',    SHA2('admin123', 256)),
  (2, 'Chef Principal','chef@sena.edu.co',     SHA2('chef123', 256)),
  (3, 'Mesero 1',      'mesero@sena.edu.co',   SHA2('mesero123', 256));

-- Categorías
INSERT INTO categorias (nombre_categoria, descripcion) VALUES
  ('Entradas',    'Aperitivos y entradas del menú'),
  ('Principales', 'Platos fuertes y principales'),
  ('Bebidas',     'Bebidas frías, calientes y naturales'),
  ('Postres',     'Dulces y postres artesanales');

-- Productos
INSERT INTO productos (id_categoria, nombre, descripcion, precio) VALUES
  -- Entradas
  (1, 'Patacones con Hogao',  'Tostones de plátano verde con salsa de tomate y cebolla criolla', 12500.00),
  (1, 'Empanadas (x3)',       'Empanadas de pipián con ají y guacamole casero',                   9800.00),
  (1, 'Ceviche de Camarón',   'Camarón fresco, limón, cilantro y cebolla morada',                18000.00),
  (1, 'Arepas con Queso',     'Arepas de chócolo con queso campesino derretido',                  8500.00),
  -- Principales
  (2, 'Bandeja Paisa',        'Frijoles, chicharrón, carne molida, huevo, aguacate, arroz y arepa', 28500.00),
  (2, 'Sancocho Trifásico',   'Sopa con pollo, res, cerdo, papa, yuca y mazorca',                 24000.00),
  (2, 'Trucha a la Plancha',  'Trucha fresca con papas al vapor y ensalada criolla',              32000.00),
  (2, 'Posta Negra',          'Carne de res en salsa negra con arroz de coco y tajadas',          26000.00),
  (2, 'Arroz con Pollo',      'Arroz amarillo con pollo, vegetales y aliños criollos',            22000.00),
  -- Bebidas
  (3, 'Limonada de Coco',     'Limón natural, leche de coco y azúcar morena',                     7500.00),
  (3, 'Jugo de Lulo',         'Lulo natural recién exprimido, frío o natural',                    6000.00),
  (3, 'Agua Aromática',       'Hierbas frescas: menta, manzanilla o canela',                      3500.00),
  (3, 'Refajo',               'Cerveza + Colombiana, la combinación clásica',                     9000.00),
  (3, 'Chocolate Santafereño','Chocolate espeso con queso y pan de bono',                         6500.00),
  -- Postres
  (4, 'Tres Leches',          'Bizcocho esponjoso bañado en tres leches con nata',               11000.00),
  (4, 'Arroz con Leche',      'Cremoso arroz con leche, canela y pasas',                          8500.00),
  (4, 'Brownie de Chocolate', 'Brownie tibio con helado de vainilla artesanal',                  13500.00),
  (4, 'Flan de Caramelo',     'Flan casero con salsa de caramelo artesanal',                     10000.00);

-- Mesas (1 a 20)
INSERT INTO mesas (numero_mesa, capacidad, estado, codigo_qr) VALUES
  (1,  2, 'disponible', 'QR-MESA-001'),
  (2,  4, 'disponible', 'QR-MESA-002'),
  (3,  4, 'disponible', 'QR-MESA-003'),
  (4,  6, 'disponible', 'QR-MESA-004'),
  (5,  4, 'disponible', 'QR-MESA-005'),
  (6,  2, 'disponible', 'QR-MESA-006'),
  (7,  8, 'disponible', 'QR-MESA-007'),
  (8,  4, 'disponible', 'QR-MESA-008'),
  (9,  4, 'disponible', 'QR-MESA-009'),
  (10, 6, 'disponible', 'QR-MESA-010'),
  (11, 2, 'disponible', 'QR-MESA-011'),
  (12, 4, 'disponible', 'QR-MESA-012'),
  (13, 4, 'disponible', 'QR-MESA-013'),
  (14, 6, 'disponible', 'QR-MESA-014'),
  (15, 4, 'disponible', 'QR-MESA-015'),
  (16, 8, 'inactiva',   'QR-MESA-016'),
  (17, 4, 'disponible', 'QR-MESA-017'),
  (18, 4, 'disponible', 'QR-MESA-018'),
  (19, 2, 'disponible', 'QR-MESA-019'),
  (20, 6, 'disponible', 'QR-MESA-020');

-- Cupones de descuento
INSERT INTO cupones (codigo, descuento, fecha_fin) VALUES
  ('SENA2025',  15.00, '2025-12-31'),
  ('BIENVENIDO', 10.00, NULL),
  ('PROMO20',   20.00, '2025-06-30');

-- ============================================================
-- 4. PEDIDOS Y FACTURAS DE EJEMPLO
-- ============================================================

-- Pedido 1 (entregado)
INSERT INTO pedidos (id_mesa, numero_pedido, estado, notas, fecha_pedido, fecha_entrega) VALUES
  (5, 'ORD-000001', 'entregado', 'Sin picante', NOW() - INTERVAL 2 HOUR, NOW() - INTERVAL 1 HOUR);
INSERT INTO detalle_pedidos (id_pedido, id_producto, cantidad, precio_unit, subtotal) VALUES
  (1, 5, 1, 28500.00, 28500.00),
  (1, 10, 2, 7500.00,  15000.00);
INSERT INTO facturas (id_pedido, numero_factura, subtotal, iva, servicio, total, metodo_pago) VALUES
  (1, 'FAC-000001', 43500.00, 8265.00, 4350.00, 56115.00, 'efectivo');

-- Pedido 2 (listo)
INSERT INTO pedidos (id_mesa, numero_pedido, estado, fecha_pedido) VALUES
  (3, 'ORD-000002', 'listo', NOW() - INTERVAL 30 MINUTE);
INSERT INTO detalle_pedidos (id_pedido, id_producto, cantidad, precio_unit, subtotal) VALUES
  (2, 7, 1, 32000.00, 32000.00),
  (2, 11, 1, 6000.00,  6000.00),
  (2, 15, 1, 11000.00, 11000.00);
INSERT INTO facturas (id_pedido, numero_factura, subtotal, iva, servicio, total, metodo_pago) VALUES
  (2, 'FAC-000002', 49000.00, 9310.00, 4900.00, 63210.00, 'tarjeta');

-- Pedido 3 (en preparación)
INSERT INTO pedidos (id_mesa, numero_pedido, estado, notas, fecha_pedido) VALUES
  (7, 'ORD-000003', 'en_preparacion', 'Mesa cumpleaños', NOW() - INTERVAL 15 MINUTE);
INSERT INTO detalle_pedidos (id_pedido, id_producto, cantidad, precio_unit, subtotal) VALUES
  (3, 6, 2, 24000.00, 48000.00),
  (3, 13, 2, 9000.00, 18000.00),
  (3, 16, 2, 8500.00, 17000.00);
INSERT INTO facturas (id_pedido, numero_factura, subtotal, iva, servicio, total) VALUES
  (3, 'FAC-000003', 83000.00, 15770.00, 8300.00, 107070.00);

-- Pedido 4 (pendiente)
INSERT INTO pedidos (id_mesa, numero_pedido, estado, fecha_pedido) VALUES
  (2, 'ORD-000004', 'pendiente', NOW() - INTERVAL 5 MINUTE);
INSERT INTO detalle_pedidos (id_pedido, id_producto, cantidad, precio_unit, subtotal) VALUES
  (4, 1, 2, 12500.00, 25000.00),
  (4, 10, 2, 7500.00,  15000.00);
INSERT INTO facturas (id_pedido, numero_factura, subtotal, iva, servicio, total) VALUES
  (4, 'FAC-000004', 40000.00, 7600.00, 4000.00, 51600.00);

-- Actualizar estados de las mesas ocupadas
UPDATE mesas SET estado = 'ocupada' WHERE numero_mesa IN (2, 3, 7);

-- ============================================================
-- 5. VISTAS ÚTILES PARA REPORTES EN WORKBENCH
-- ============================================================

CREATE OR REPLACE VIEW v_pedidos_detalle AS
  SELECT
    p.id_pedido,
    p.numero_pedido,
    p.estado,
    p.notas,
    p.fecha_pedido,
    p.fecha_entrega,
    m.numero_mesa,
    m.capacidad,
    f.numero_factura,
    f.subtotal,
    f.iva,
    f.servicio,
    f.total,
    f.metodo_pago
  FROM pedidos p
  JOIN mesas m ON p.id_mesa = m.id_mesa
  LEFT JOIN facturas f ON f.id_pedido = p.id_pedido;

CREATE OR REPLACE VIEW v_ventas_por_categoria AS
  SELECT
    c.nombre_categoria,
    COUNT(DISTINCT p.id_pedido) AS num_pedidos,
    SUM(d.cantidad) AS unidades_vendidas,
    SUM(d.subtotal) AS ingresos_brutos
  FROM categorias c
  LEFT JOIN productos pr ON pr.id_categoria = c.id_categoria
  LEFT JOIN detalle_pedidos d ON d.id_producto = pr.id_producto
  LEFT JOIN pedidos p ON p.id_pedido = d.id_pedido
    AND p.estado NOT IN ('cancelado')
  GROUP BY c.id_categoria, c.nombre_categoria
  ORDER BY ingresos_brutos DESC;

CREATE OR REPLACE VIEW v_productos_populares AS
  SELECT
    pr.id_producto,
    pr.nombre,
    c.nombre_categoria,
    pr.precio,
    COALESCE(SUM(d.cantidad), 0) AS veces_pedido,
    COALESCE(SUM(d.subtotal), 0) AS ingresos_total
  FROM productos pr
  JOIN categorias c ON pr.id_categoria = c.id_categoria
  LEFT JOIN detalle_pedidos d ON d.id_producto = pr.id_producto
  GROUP BY pr.id_producto
  ORDER BY veces_pedido DESC;

CREATE OR REPLACE VIEW v_resumen_diario AS
  SELECT
    DATE(p.fecha_pedido) AS fecha,
    COUNT(*) AS total_pedidos,
    SUM(CASE WHEN p.estado = 'entregado' THEN 1 ELSE 0 END) AS entregados,
    SUM(CASE WHEN p.estado = 'cancelado' THEN 1 ELSE 0 END) AS cancelados,
    COALESCE(SUM(f.total), 0) AS ingresos
  FROM pedidos p
  LEFT JOIN facturas f ON f.id_pedido = p.id_pedido
  GROUP BY DATE(p.fecha_pedido)
  ORDER BY fecha DESC;

-- ============================================================
-- 6. VERIFICACIÓN FINAL
-- ============================================================
SELECT '✅ Base de datos lista' AS resultado;
SELECT tabla, total FROM (
  SELECT 'roles'    AS tabla, COUNT(*) AS total FROM roles UNION ALL
  SELECT 'usuarios',          COUNT(*) FROM usuarios UNION ALL
  SELECT 'categorias',        COUNT(*) FROM categorias UNION ALL
  SELECT 'productos',         COUNT(*) FROM productos UNION ALL
  SELECT 'mesas',             COUNT(*) FROM mesas UNION ALL
  SELECT 'pedidos',           COUNT(*) FROM pedidos UNION ALL
  SELECT 'detalle_pedidos',   COUNT(*) FROM detalle_pedidos UNION ALL
  SELECT 'facturas',          COUNT(*) FROM facturas UNION ALL
  SELECT 'cupones',           COUNT(*) FROM cupones
) t;
