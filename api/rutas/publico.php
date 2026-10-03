<?php
/**
 * publico.php — Rutas públicas: estado, configuración, carta y mesas
 */

declare(strict_types=1);

// ============================================================
// ESTADO Y CONFIGURACIÓN PÚBLICA
// ============================================================
ruta('GET', '/status', function (): void {
    if (probar_conexion()) {
        responder(['ok' => true, 'msg' => 'Conectado a la base de datos', 'db' => cfg('DB_NAME')]);
    }
    responder(['ok' => false, 'msg' => 'Sin conexión a la base de datos'], 503);
});

ruta('GET', '/config', function (): void {
    responder([
        'restaurante' => cfg('RESTAURANTE_NOMBRE'),
        'nit' => cfg('RESTAURANTE_NIT'),
        'direccion' => cfg('RESTAURANTE_DIRECCION'),
        'impuesto_nombre' => cfg('IMPUESTO_NOMBRE'),
        'impuesto_pct' => num(cfg('IMPUESTO_PCT')),
        'propina_pct' => num(cfg('PROPINA_SUGERIDA_PCT')),
        'server_url' => cfg('SERVER_URL'),
        // Hora del servidor: las pantallas del personal calculan con ella
        // los minutos de espera, sin depender del reloj de cada equipo.
        'ahora' => date('Y-m-d\TH:i:s'),
        'pedido_sin_qr' => cfg('PERMITIR_SIN_QR'),
    ]);
});

// ============================================================
// CATEGORÍAS Y PRODUCTOS (carta)
// ============================================================
ruta('GET', '/categorias', function (): void {
    if (arg('todas') === '1') {
        // Panel: también las inactivas, con cuántos productos tiene cada una
        exigir_rol([ROL_ADMIN]);
        responder(consultar(
            'SELECT c.id_categoria, c.nombre_categoria, c.descripcion, c.orden, c.activo,
                    COUNT(p.id_producto) AS productos
             FROM categorias c
             LEFT JOIN productos p ON p.id_categoria = c.id_categoria AND p.activo = 1
             GROUP BY c.id_categoria, c.nombre_categoria, c.descripcion, c.orden, c.activo
             ORDER BY c.orden, c.nombre_categoria'));
    }
    responder(consultar(
        'SELECT id_categoria, nombre_categoria, descripcion, orden, activo
         FROM categorias WHERE activo = 1 ORDER BY orden, nombre_categoria'));
});

const COLUMNAS_PRODUCTO = 'p.id_producto, p.id_categoria, p.nombre, p.descripcion, p.precio,
    p.emoji, p.disponible, p.imagen_url, c.nombre_categoria AS cat, c.activo AS cat_activa';

ruta('GET', '/productos', function (): void {
    $sql = 'SELECT ' . COLUMNAS_PRODUCTO . '
            FROM productos p JOIN categorias c ON p.id_categoria = c.id_categoria
            WHERE p.activo = 1';
    // La carta pública no muestra productos de categorías desactivadas; el
    // administrador (?todas=1) los ve todos para poder gestionarlos.
    if (arg('todas') === '1') {
        exigir_rol([ROL_ADMIN]);
    } else {
        $sql .= ' AND c.activo = 1';
    }
    $params = [];
    if (($cat = arg('cat')) !== null && $cat !== '') {
        $sql .= ' AND c.nombre_categoria = ?';
        $params[] = $cat;
    }
    if (($q = arg('q')) !== null && $q !== '') {
        $sql .= ' AND (p.nombre LIKE ? OR p.descripcion LIKE ?)';
        array_push($params, "%$q%", "%$q%");
    }
    if (arg('disponible') === '1') {
        $sql .= ' AND p.disponible = 1';
    }
    $sql .= ' ORDER BY c.orden, c.nombre_categoria, p.nombre';
    responder(consultar($sql, $params));
});

ruta('GET', '/productos/{id:n}', function (string $id): void {
    $fila = consultar_uno('SELECT ' . COLUMNAS_PRODUCTO . '
        FROM productos p JOIN categorias c ON p.id_categoria = c.id_categoria
        WHERE p.id_producto = ? AND p.activo = 1', [(int) $id]);
    if (!$fila) {
        throw new ErrorAPI('Producto no encontrado.', 404);
    }
    responder($fila);
});

// ============================================================
// MESAS (comensal)
//
// Cada mesa tiene un código secreto (codigo_qr) que va en su QR:
//   menu.html?mesa=5&c=<código>
// Sin el código correcto no se puede pedir a nombre de esa mesa, salvo
// que PERMITIR_SIN_QR esté activo y NO se envíe código (el comensal eligió
// la mesa en la lista). Un código equivocado siempre se rechaza.
// ============================================================
function mesa_por_qr(int $numero, mixed $codigo): array
{
    $mesa = consultar_uno(
        'SELECT id_mesa, numero_mesa, capacidad, estado, codigo_qr FROM mesas WHERE numero_mesa = ?', [$numero]);
    if (!$mesa) {
        throw new ErrorAPI("La mesa $numero no existe.", 404, 'mesa_no_existe');
    }
    $codigo = is_string($codigo) ? strtolower(trim($codigo)) : '';
    if ($codigo === '') {
        if (cfg('PERMITIR_SIN_QR')) {
            $mesa['origen'] = 'manual';
            return $mesa;
        }
        throw new ErrorAPI('Para pedir, escanee el código QR que está en su mesa.', 403, 'qr_requerido');
    }
    if (!$mesa['codigo_qr'] || !hash_equals((string) $mesa['codigo_qr'], $codigo)) {
        throw new ErrorAPI('El código QR de la mesa no es válido. Escanee de nuevo el QR que está en su mesa.',
            403, 'qr_invalido');
    }
    $mesa['origen'] = 'qr';
    return $mesa;
}

ruta('GET', '/mesas/disponibles', function (): void {
    if (!cfg('PERMITIR_SIN_QR')) {
        throw new ErrorAPI('Para pedir, escanee el código QR que está en su mesa.', 403, 'qr_requerido');
    }
    responder(consultar(
        "SELECT numero_mesa, capacidad, estado FROM mesas WHERE estado <> 'inactiva' ORDER BY numero_mesa"));
});

ruta('GET', '/mesas/{numero:n}', function (string $numero): void {
    $mesa = mesa_por_qr((int) $numero, arg('c'));
    responder([
        'numero_mesa' => $mesa['numero_mesa'],
        'capacidad' => $mesa['capacidad'],
        'estado' => $mesa['estado'],
        'activa' => $mesa['estado'] !== 'inactiva',
        'origen' => $mesa['origen'],
    ]);
});
