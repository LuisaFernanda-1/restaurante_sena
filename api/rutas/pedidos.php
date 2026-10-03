<?php
/**
 * pedidos.php — Pedidos, facturas, llamados al mesero, cupones y estadísticas
 *
 * GET  /api/pedidos                 → lista (personal) ?mesa=&estado=a,b&fecha=&numero=&limit=&orden=&items=1
 * GET  /api/pedidos/{id}            → detalle (personal)
 * GET  /api/pedidos/token/{token}   → detalle para el comensal
 * POST /api/pedidos                 → crear pedido (comensal)
 * PUT  /api/pedidos/{id}/estado     → cambiar estado (según el rol)
 * GET  /api/facturas/{id_pedido}    → personal
 * GET  /api/facturas/token/{token}  → comensal
 * PUT  /api/facturas/{id}/pago      → administrador o mesero
 * GET  /api/verificar/{código}      → verificación pública de un comprobante (QR)
 * POST /api/llamados                → el comensal llama al mesero
 * GET  /api/llamados                → llamados pendientes (mesero, admin)
 * PUT  /api/llamados/{id}/atender   → marcar atendido
 * GET  /api/cupones/validar?codigo= → validar cupón (comensal)
 * GET  /api/stats                   → tablero del administrador
 */

declare(strict_types=1);

const ESTADOS_PEDIDO = ['pendiente', 'en_preparacion', 'listo', 'entregado', 'cancelado'];
const ESTADOS_ACTIVOS = ['pendiente', 'en_preparacion', 'listo'];
// (estado actual → estado nuevo) → roles que pueden hacer ese cambio
const TRANSICIONES = [
    'pendiente>en_preparacion' => [ROL_CHEF, ROL_ADMIN],
    'en_preparacion>listo' => [ROL_CHEF, ROL_ADMIN],
    'listo>entregado' => [ROL_MESERO, ROL_ADMIN],
    'pendiente>cancelado' => [ROL_CHEF, ROL_ADMIN],
    'en_preparacion>cancelado' => [ROL_CHEF, ROL_ADMIN],
    'listo>cancelado' => [ROL_ADMIN],
];
const MAX_ITEMS_PEDIDO = 30;

const COLUMNAS_PEDIDO = 'p.id_pedido, p.numero_pedido, p.estado, p.notas,
    p.subtotal, p.descuento, p.impuesto, p.propina, p.total,
    p.fecha_pedido, p.fecha_listo, p.fecha_entrega, m.numero_mesa, p.origen';

/** Productos de varios pedidos, agrupados por pedido. */
function items_de(array $ids): array
{
    if (!$ids) {
        return [];
    }
    $filas = consultar(
        'SELECT d.id_pedido, d.id_producto, d.cantidad, d.precio_unit, d.subtotal,
                COALESCE(d.nombre_producto, pr.nombre) AS nombre, pr.emoji
         FROM detalle_pedidos d JOIN productos pr ON d.id_producto = pr.id_producto
         WHERE d.id_pedido IN (' . marcas(count($ids)) . ')
         ORDER BY d.id_detalle', array_values($ids));
    $por = [];
    foreach ($filas as $f) {
        $id = $f['id_pedido'];
        unset($f['id_pedido']);
        $por[$id][] = $f;
    }
    return $por;
}

function token_valido(string $token): bool
{
    return (bool) preg_match('/^[0-9a-f]{32}$/', $token);
}

// ============================================================
// LISTA Y DETALLE
// ============================================================
ruta('GET', '/pedidos', function (): void {
    exigir_rol();
    $limit = arg_entero('limit', 50, 1, 500);
    $sql = 'SELECT ' . COLUMNAS_PEDIDO . ', COUNT(d.id_detalle) AS num_items
            FROM pedidos p
            JOIN mesas m ON p.id_mesa = m.id_mesa
            LEFT JOIN detalle_pedidos d ON p.id_pedido = d.id_pedido
            WHERE 1 = 1';
    $params = [];
    if (($mesa = arg('mesa')) !== null && $mesa !== '') {
        $sql .= ' AND m.numero_mesa = ?';
        $params[] = v_entero($mesa, 'mesa', 1);
    }
    if (($estado = arg('estado')) !== null && $estado !== '') {
        $estados = array_values(array_filter(explode(',', $estado)));
        foreach ($estados as $e) {
            if (!in_array($e, ESTADOS_PEDIDO, true)) {
                throw new ErrorAPI('Estado de pedido inválido.');
            }
        }
        $sql .= ' AND p.estado IN (' . marcas(count($estados)) . ')';
        array_push($params, ...$estados);
    }
    if (($fecha = arg('fecha')) !== null && $fecha !== '') {
        $params[] = v_fecha($fecha, 'fecha');
        $sql .= ' AND p.fecha_pedido >= ? AND p.fecha_pedido < ? + INTERVAL 1 DAY';
        $params[] = $fecha;
    }
    if (($numero = trim((string) arg('numero'))) !== '') {
        $sql .= ' AND p.numero_pedido LIKE ?';
        $params[] = '%' . mb_substr($numero, 0, 20) . '%';
    }
    $orden = arg('orden') === 'asc' ? 'ASC' : 'DESC';
    $sql .= ' GROUP BY ' . COLUMNAS_PEDIDO . " ORDER BY p.fecha_pedido $orden, p.id_pedido $orden LIMIT ?";
    $params[] = $limit;
    $filas = consultar($sql, $params);
    if (arg('items') === '1') {
        $items = items_de(array_column($filas, 'id_pedido'));
        foreach ($filas as &$f) {
            $f['items'] = $items[$f['id_pedido']] ?? [];
        }
        unset($f);
    }
    responder($filas);
});

function pedido_completo(string $donde, mixed $valor): array
{
    $p = consultar_uno('SELECT ' . COLUMNAS_PEDIDO . ', p.token, c.codigo AS cupon
        FROM pedidos p JOIN mesas m ON p.id_mesa = m.id_mesa
        LEFT JOIN cupones c ON p.id_cupon = c.id_cupon
        WHERE ' . $donde, [$valor]);
    if (!$p) {
        throw new ErrorAPI('Pedido no encontrado.', 404);
    }
    $p['items'] = items_de([$p['id_pedido']])[$p['id_pedido']] ?? [];
    $fac = consultar_uno('SELECT numero_factura FROM facturas WHERE id_pedido = ?', [$p['id_pedido']]);
    $p['numero_factura'] = $fac['numero_factura'] ?? null;
    return $p;
}

ruta('GET', '/pedidos/{id:n}', function (string $id): void {
    exigir_rol();
    responder(pedido_completo('p.id_pedido = ?', (int) $id));
});

ruta('GET', '/pedidos/token/{token}', function (string $token): void {
    if (!token_valido($token)) {
        throw new ErrorAPI('Pedido no encontrado.', 404);
    }
    responder(pedido_completo('p.token = ?', $token));
});

// ============================================================
// CREAR PEDIDO (comensal)
// Cuerpo: {"mesa": 5, "codigo": "<código del QR>", "items": [{"id": 3, "cantidad": 2}],
//          "notas": "...", "cupon": "BIENVENIDO", "propina": true}
// Los precios NO se reciben del cliente: se leen de la base de datos.
// ============================================================
function buscar_cupon(string $codigo): ?array
{
    return consultar_uno(
        'SELECT id_cupon, codigo, descuento FROM cupones
         WHERE codigo = ? AND activo = 1 AND (fecha_fin IS NULL OR fecha_fin >= CURDATE())', [$codigo]);
}

/** ORD-000123 / FAC-000123; si ya existe (datos antiguos) agrega -2, -3... */
function numero_libre(string $tabla, string $columna, string $prefijo, int $consecutivo): string
{
    $base = sprintf('%s-%06d', $prefijo, $consecutivo);
    $candidato = $base;
    for ($n = 2; consultar_uno("SELECT 1 AS ok FROM $tabla WHERE $columna = ?", [$candidato]); $n++) {
        $candidato = "$base-$n";
    }
    return $candidato;
}

ruta('POST', '/pedidos', function (): void {
    if (limite_bloqueado('pedido', ip_cliente())) {
        throw new ErrorAPI('Se han enviado demasiados pedidos desde este dispositivo. '
            . 'Espere unos minutos o pida ayuda al mesero.', 429);
    }
    $data = cuerpo_json();
    $numeroMesa = v_entero($data['mesa'] ?? null, 'Mesa', 1);
    $notas = v_texto($data['notas'] ?? null, 'Notas', 300);
    $conPropina = v_bool($data['propina'] ?? true, 'Propina');
    $codigoCupon = mb_strtoupper(v_texto($data['cupon'] ?? null, 'Cupón', 20));

    $items = $data['items'] ?? null;
    if (!is_array($items) || !$items || !array_is_list($items)) {
        throw new ErrorAPI('El pedido debe tener al menos un producto.');
    }
    if (count($items) > MAX_ITEMS_PEDIDO) {
        throw new ErrorAPI('El pedido no puede tener más de ' . MAX_ITEMS_PEDIDO . ' productos distintos.');
    }
    $cantidades = [];
    foreach ($items as $item) {
        if (!is_array($item)) {
            throw new ErrorAPI('Formato de producto inválido.');
        }
        $pid = v_entero($item['id'] ?? null, 'Producto', 1);
        $cant = v_entero($item['cantidad'] ?? $item['qty'] ?? null, 'Cantidad', 1, 10);
        $cantidades[$pid] = ($cantidades[$pid] ?? 0) + $cant;
        if ($cantidades[$pid] > 10) {
            throw new ErrorAPI('Máximo 10 unidades por producto.');
        }
    }

    $mesa = mesa_por_qr($numeroMesa, $data['codigo'] ?? null);
    if ($mesa['estado'] === 'inactiva') {
        throw new ErrorAPI("La mesa $numeroMesa no está habilitada. Por favor avise al personal.", 409);
    }
    $cupon = null;
    if ($codigoCupon !== '') {
        $cupon = buscar_cupon($codigoCupon);
        if (!$cupon) {
            throw new ErrorAPI('El cupón no es válido o está vencido.');
        }
    }

    $ids = array_keys($cantidades);
    $productos = [];
    foreach (consultar('SELECT p.id_producto, p.nombre, p.precio
        FROM productos p JOIN categorias c ON p.id_categoria = c.id_categoria
        WHERE p.id_producto IN (' . marcas(count($ids)) . ')
          AND p.activo = 1 AND p.disponible = 1 AND c.activo = 1', $ids) as $p) {
        $productos[$p['id_producto']] = $p;
    }
    foreach ($ids as $pid) {
        if (!isset($productos[$pid])) {
            throw new ErrorAPI('Algunos productos ya no están disponibles. Actualice la carta e intente de nuevo.', 409);
        }
    }

    $subtotal = 0;
    foreach ($cantidades as $pid => $cant) {
        $subtotal += $productos[$pid]['precio'] * $cant;
    }
    $totales = calcular_totales($subtotal, $cupon ? num($cupon['descuento']) : 0, $conPropina);
    $token = bin2hex(random_bytes(16));

    $resultado = transaccion(function () use ($mesa, $cupon, $token, $notas, $totales, $cantidades, $productos): array {
        [, $pedidoId] = ejecutar(
            "INSERT INTO pedidos (id_mesa, id_cupon, token, origen, estado, notas, subtotal, descuento, impuesto, propina, total)
             VALUES (?, ?, ?, ?, 'pendiente', ?, ?, ?, ?, ?, ?)",
            [$mesa['id_mesa'], $cupon['id_cupon'] ?? null, $token, $mesa['origen'], $notas === '' ? null : $notas,
             $totales['subtotal'], $totales['descuento'], $totales['impuesto'], $totales['propina'], $totales['total']]);
        $numero = numero_libre('pedidos', 'numero_pedido', 'ORD', $pedidoId);
        ejecutar('UPDATE pedidos SET numero_pedido = ? WHERE id_pedido = ?', [$numero, $pedidoId]);
        foreach ($cantidades as $pid => $cant) {
            $prod = $productos[$pid];
            ejecutar('INSERT INTO detalle_pedidos (id_pedido, id_producto, nombre_producto, cantidad, precio_unit, subtotal)
                      VALUES (?, ?, ?, ?, ?, ?)',
                [$pedidoId, $pid, $prod['nombre'], $cant, $prod['precio'], $prod['precio'] * $cant]);
        }
        ejecutar("UPDATE mesas SET estado = 'ocupada' WHERE id_mesa = ? AND estado = 'disponible'", [$mesa['id_mesa']]);
        return [$pedidoId, $numero];
    });
    [$pedidoId, $numero] = $resultado;
    limite_registrar('pedido', ip_cliente());
    responder(array_merge([
        'ok' => true,
        'id_pedido' => $pedidoId,
        'numero_pedido' => $numero,
        'token' => $token,
    ], $totales, ['msg' => 'Pedido enviado a cocina']), 201);
});

// ============================================================
// CAMBIO DE ESTADO (según el rol) y factura al entregar
// ============================================================
function generar_factura(array $pedido): void
{
    if (consultar_uno('SELECT id_factura FROM facturas WHERE id_pedido = ?', [$pedido['id_pedido']])) {
        return;
    }
    [, $idFactura] = ejecutar(
        'INSERT INTO facturas (id_pedido, numero_factura, codigo_verificacion, subtotal, descuento,
                               impuesto_nombre, impuesto_pct, impuesto, propina, total)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        [$pedido['id_pedido'], 'TMP-' . bin2hex(random_bytes(8)), bin2hex(random_bytes(16)),
         $pedido['subtotal'], $pedido['descuento'], cfg('IMPUESTO_NOMBRE'), (string) cfg('IMPUESTO_PCT'),
         $pedido['impuesto'], $pedido['propina'], $pedido['total']]);
    ejecutar('UPDATE facturas SET numero_factura = ? WHERE id_factura = ?',
        [numero_libre('facturas', 'numero_factura', 'FAC', $idFactura), $idFactura]);
}

ruta('PUT', '/pedidos/{id:n}/estado', function (string $id): void {
    $u = exigir_rol();
    $nuevo = cuerpo_json()['estado'] ?? null;
    if (!in_array($nuevo, ESTADOS_PEDIDO, true)) {
        throw new ErrorAPI('Estado inválido.');
    }
    $msg = transaccion(function () use ($id, $nuevo, $u): string {
        // FOR UPDATE: si dos personas cambian el mismo pedido a la vez, la
        // segunda espera y ve el estado ya actualizado.
        $pedido = consultar_uno(
            'SELECT id_pedido, id_mesa, estado, subtotal, descuento, impuesto, propina, total
             FROM pedidos WHERE id_pedido = ? FOR UPDATE', [(int) $id]);
        if (!$pedido) {
            throw new ErrorAPI('Pedido no encontrado.', 404);
        }
        $actual = $pedido['estado'];
        if ($nuevo === $actual) {
            return "El pedido ya estaba en estado $nuevo";
        }
        $roles = TRANSICIONES["$actual>$nuevo"] ?? null;
        if ($roles === null) {
            throw new ErrorAPI("No se puede pasar un pedido de '$actual' a '$nuevo'.", 409);
        }
        if (!in_array($u['rol'], $roles, true)) {
            throw new ErrorAPI("Su rol no puede pasar un pedido de '$actual' a '$nuevo'.", 403, 'sin_permiso');
        }
        $sql = 'UPDATE pedidos SET estado = ?';
        $params = [$nuevo];
        if ($nuevo === 'listo') {
            $sql .= ', fecha_listo = NOW()';
        }
        if ($nuevo === 'entregado') {
            $sql .= ', fecha_entrega = NOW(), id_usuario = ?';
            $params[] = $u['id_usuario'];
        }
        $params[] = (int) $id;
        ejecutar($sql . ' WHERE id_pedido = ?', $params);

        if ($nuevo === 'entregado') {
            generar_factura($pedido);
        }
        if (in_array($nuevo, ['entregado', 'cancelado'], true)) {
            // La mesa queda libre solo si no tiene otros pedidos en curso.
            $activos = consultar_uno('SELECT COUNT(*) AS n FROM pedidos WHERE id_mesa = ? AND estado IN ('
                . marcas(count(ESTADOS_ACTIVOS)) . ')', [$pedido['id_mesa'], ...ESTADOS_ACTIVOS]);
            if ((int) $activos['n'] === 0) {
                ejecutar("UPDATE mesas SET estado = 'disponible' WHERE id_mesa = ? AND estado = 'ocupada'", [$pedido['id_mesa']]);
            }
        }
        return "Estado actualizado a $nuevo";
    });
    responder(['ok' => true, 'msg' => $msg]);
});

// ============================================================
// FACTURAS (comprobantes)
// ============================================================
function factura(string $donde, mixed $valor): array
{
    $f = consultar_uno('SELECT f.*, p.numero_pedido, p.notas, p.estado, m.numero_mesa
        FROM facturas f JOIN pedidos p ON f.id_pedido = p.id_pedido JOIN mesas m ON p.id_mesa = m.id_mesa
        WHERE ' . $donde, [$valor]);
    if (!$f) {
        throw new ErrorAPI('Factura no encontrada.', 404);
    }
    $f['impuesto_pct'] = num($f['impuesto_pct']);
    $f['items'] = items_de([$f['id_pedido']])[$f['id_pedido']] ?? [];
    return $f;
}

ruta('GET', '/facturas/{id:n}', function (string $id): void {
    exigir_rol();
    responder(factura('f.id_pedido = ?', (int) $id));
});

ruta('GET', '/facturas/token/{token}', function (string $token): void {
    if (!token_valido($token)) {
        throw new ErrorAPI('Factura no encontrada.', 404);
    }
    responder(factura('p.token = ?', $token));
});

ruta('PUT', '/facturas/{id:n}/pago', function (string $id): void {
    exigir_rol([ROL_ADMIN, ROL_MESERO]);
    $metodo = cuerpo_json()['metodo_pago'] ?? null;
    if (!in_array($metodo, ['efectivo', 'tarjeta', 'digital'], true)) {
        throw new ErrorAPI('Método de pago inválido.');
    }
    [$filas] = ejecutar('UPDATE facturas SET metodo_pago = ? WHERE id_pedido = ?', [$metodo, (int) $id]);
    if ($filas === 0 && !consultar_uno('SELECT 1 AS ok FROM facturas WHERE id_pedido = ?', [(int) $id])) {
        throw new ErrorAPI('Factura no encontrada.', 404);
    }
    responder(['ok' => true, 'msg' => "Método de pago actualizado a $metodo"]);
});

ruta('GET', '/verificar/{codigo}', function (string $codigo): void {
    $codigo = strtolower(trim($codigo));
    if (!token_valido($codigo)) {
        throw new ErrorAPI('No existe un comprobante con ese código.', 404);
    }
    $f = consultar_uno(
        'SELECT f.numero_factura, f.fecha_factura, f.subtotal, f.descuento, f.impuesto_nombre,
                f.impuesto_pct, f.impuesto, f.propina, f.total, f.metodo_pago,
                p.numero_pedido, p.estado, m.numero_mesa,
                (SELECT CAST(COALESCE(SUM(d.cantidad), 0) AS SIGNED) FROM detalle_pedidos d WHERE d.id_pedido = p.id_pedido) AS unidades
         FROM facturas f JOIN pedidos p ON f.id_pedido = p.id_pedido JOIN mesas m ON p.id_mesa = m.id_mesa
         WHERE f.codigo_verificacion = ?', [$codigo]);
    if (!$f) {
        throw new ErrorAPI('No existe un comprobante con ese código.', 404);
    }
    $f['impuesto_pct'] = num($f['impuesto_pct']);
    $f['restaurante'] = cfg('RESTAURANTE_NOMBRE');
    $f['nit'] = cfg('RESTAURANTE_NIT');
    $f['valido'] = $f['estado'] === 'entregado';
    responder($f);
});

// ============================================================
// LLAMADOS AL MESERO
// ============================================================
ruta('POST', '/llamados', function (): void {
    if (limite_bloqueado('llamado', ip_cliente())) {
        throw new ErrorAPI('Ya avisamos al mesero varias veces. Por favor espere un momento.', 429);
    }
    $data = cuerpo_json();
    $mesa = mesa_por_qr(v_entero($data['mesa'] ?? null, 'Mesa', 1), $data['codigo'] ?? null);
    limite_registrar('llamado', ip_cliente());
    $yaPendiente = transaccion(function () use ($mesa): bool {
        // Una mesa solo tiene un llamado pendiente a la vez.
        if (consultar_uno("SELECT id_llamado FROM llamados WHERE id_mesa = ? AND estado = 'pendiente' FOR UPDATE", [$mesa['id_mesa']])) {
            return true;
        }
        ejecutar('INSERT INTO llamados (id_mesa) VALUES (?)', [$mesa['id_mesa']]);
        return false;
    });
    if ($yaPendiente) {
        responder(['ok' => true, 'ya_pendiente' => true, 'msg' => 'El mesero ya fue avisado y vendrá pronto a tu mesa.']);
    }
    responder(['ok' => true, 'ya_pendiente' => false, 'msg' => '¡Listo! El mesero vendrá a tu mesa en breve.'], 201);
});

ruta('GET', '/llamados', function (): void {
    exigir_rol([ROL_ADMIN, ROL_MESERO]);
    responder(consultar(
        "SELECT l.id_llamado, m.numero_mesa, l.estado, l.fecha_solicitud
         FROM llamados l JOIN mesas m ON l.id_mesa = m.id_mesa
         WHERE l.estado = 'pendiente' ORDER BY l.fecha_solicitud, l.id_llamado"));
});

ruta('PUT', '/llamados/{id:n}/atender', function (string $id): void {
    $u = exigir_rol([ROL_ADMIN, ROL_MESERO]);
    [$filas] = ejecutar(
        "UPDATE llamados SET estado = 'atendido', fecha_atencion = NOW(), id_usuario = ?
         WHERE id_llamado = ? AND estado = 'pendiente'", [$u['id_usuario'], (int) $id]);
    if ($filas === 0) {
        if (!consultar_uno('SELECT 1 AS ok FROM llamados WHERE id_llamado = ?', [(int) $id])) {
            throw new ErrorAPI('Llamado no encontrado.', 404);
        }
        responder(['ok' => true, 'msg' => 'El llamado ya estaba atendido']);
    }
    responder(['ok' => true, 'msg' => 'Llamado atendido']);
});

// ============================================================
// CUPONES Y ESTADÍSTICAS
// ============================================================
ruta('GET', '/cupones/validar', function (): void {
    $codigo = mb_strtoupper(trim((string) arg('codigo')));
    if ($codigo === '' || mb_strlen($codigo) > 20) {
        throw new ErrorAPI('Código requerido.');
    }
    $c = buscar_cupon($codigo);
    if (!$c) {
        throw new ErrorAPI('Cupón inválido o vencido.', 404);
    }
    responder(['ok' => true, 'codigo' => $c['codigo'], 'descuento' => num($c['descuento'])]);
});

/** Ventas solo de pedidos ENTREGADOS (facturados). */
ruta('GET', '/stats', function (): void {
    exigir_rol([ROL_ADMIN]);
    $n = fn (string $sql, array $p = []) => (int) (consultar_uno($sql, $p)['n'] ?? 0);
    responder([
        'pedidos_hoy' => $n("SELECT COUNT(*) AS n FROM pedidos
            WHERE fecha_pedido >= CURDATE() AND fecha_pedido < CURDATE() + INTERVAL 1 DAY AND estado <> 'cancelado'"),
        'ventas_hoy' => $n("SELECT CAST(COALESCE(SUM(f.total), 0) AS SIGNED) AS n
            FROM facturas f JOIN pedidos p ON f.id_pedido = p.id_pedido
            WHERE p.estado = 'entregado' AND f.fecha_factura >= CURDATE() AND f.fecha_factura < CURDATE() + INTERVAL 1 DAY"),
        'activos' => $n("SELECT COUNT(*) AS n FROM pedidos WHERE estado IN ('pendiente','en_preparacion','listo')"),
        'productos' => $n('SELECT COUNT(*) AS n FROM productos WHERE activo = 1 AND disponible = 1'),
        'mesas_ocupadas' => $n("SELECT COUNT(*) AS n FROM mesas WHERE estado = 'ocupada'"),
        'ventas_cat' => array_map(fn ($f) => ['categoria' => $f['categoria'], 'total' => (int) $f['total']], consultar(
            'SELECT nombre_categoria AS categoria, ingresos_brutos AS total FROM v_ventas_por_categoria ORDER BY total DESC')),
    ]);
});
