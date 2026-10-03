<?php
/** Fase 3: pedidos, estados, facturas, llamados, cupones, modo sin QR y permisos. */

declare(strict_types=1);

// ============================================================
grupo('Pedidos');
// ============================================================
prueba('totales calculados en el servidor (impoconsumo 8 % + propina voluntaria)', function (): void {
    // 2 × Bandeja Paisa (28.500) + 1 × Limonada (7.500) = 64.500
    $p = crear_pedido(5, [['id' => 5, 'cantidad' => 2], ['id' => 10, 'cantidad' => 1]], ['cupon' => 'bienvenido', 'propina' => true]);
    igual(64500, $p['subtotal']);
    igual(6450, $p['descuento'], 'descuento 10 %');
    igual(4644, $p['impuesto'], '8 % de 58.050');
    igual(5805, $p['propina'], '10 % de 58.050');
    igual(68499, $p['total']);
    verdadero(str_starts_with($p['numero_pedido'], 'ORD-'), 'número ORD-');
    igual(32, strlen($p['token']));
});

prueba('propina voluntaria y precio del cliente ignorado', function (): void {
    $p = crear_pedido(5, [['id' => 5, 'cantidad' => 1]], ['propina' => false]);
    igual(0, $p['propina']);
    igual(28500 + 2280, $p['total']);
    $p = crear_pedido(5, [['id' => 12, 'cantidad' => 1, 'precio' => 1]], ['propina' => false]);
    igual(3500, $p['subtotal']);
});

prueba('pedidos inválidos', function (): void {
    $casos = [
        [['mesa' => 'demo', 'items' => [['id' => 1, 'cantidad' => 1]]], 400],
        [['mesa' => 99, 'items' => [['id' => 1, 'cantidad' => 1]]], 404],
        [['mesa' => 16, 'items' => [['id' => 1, 'cantidad' => 1]]], 409],          // mesa inactiva
        [['mesa' => 5, 'items' => [['id' => 1, 'cantidad' => 11]]], 400],
        [['mesa' => 5, 'items' => [['id' => 1, 'cantidad' => 0]]], 400],
        [['mesa' => 5, 'items' => [['id' => 1, 'cantidad' => 'abc']]], 400],
        [['mesa' => 5, 'items' => [['id' => 1, 'cantidad' => 6], ['id' => 1, 'cantidad' => 5]]], 400],
        [['mesa' => 5, 'items' => [['id' => 9999, 'cantidad' => 1]]], 409],
        [['mesa' => 5, 'items' => []], 400],
        [['mesa' => 5], 400],
        [['mesa' => 5, 'items' => [['id' => 1, 'cantidad' => 1]], 'cupon' => 'FALSO'], 400],
        [['mesa' => 5, 'items' => [['id' => 1, 'cantidad' => 1]], 'notas' => str_repeat('x', 301)], 400],
    ];
    foreach ($casos as $i => [$cuerpo, $codigo]) {
        if (is_int($cuerpo['mesa'])) {
            $cuerpo['codigo'] = codigo_mesa($cuerpo['mesa']);
        }
        $r = cliente()->post('/api/pedidos', $cuerpo);
        igual($codigo, $r->status, "caso $i " . json_encode($cuerpo));
        igual(false, $r->json()['ok']);
    }
    igual(400, cliente()->pedir('POST', '/api/pedidos', null, ['Content-Type' => 'text/plain'], 'hola')->status, 'no JSON');
});

prueba('producto agotado no se puede pedir y el pedido es atómico', function (): void {
    sql_ejecutar('UPDATE productos SET disponible = 0 WHERE id_producto = 1');
    igual(409, cliente()->post('/api/pedidos', ['mesa' => 5, 'codigo' => codigo_mesa(5), 'items' => [['id' => 1, 'cantidad' => 1]]])->status);
    $antes = (int) sql_valor('SELECT COUNT(*) FROM pedidos');
    igual(409, cliente()->post('/api/pedidos', ['mesa' => 5, 'codigo' => codigo_mesa(5),
        'items' => [['id' => 2, 'cantidad' => 1], ['id' => 9999, 'cantidad' => 1]]])->status);
    igual($antes, (int) sql_valor('SELECT COUNT(*) FROM pedidos'), 'no quedó un pedido a medias');
});

prueba('código QR de otra mesa no sirve', function (): void {
    $r = cliente()->post('/api/pedidos', ['mesa' => 7, 'codigo' => codigo_mesa(5), 'items' => [['id' => 1, 'cantidad' => 1]]]);
    igual(403, $r->status);
    igual('qr_invalido', $r->json()['codigo']);
});

prueba('flujo de estados, factura y mesa', function (): void {
    $p = crear_pedido(5);
    $id = $p['id_pedido'];
    igual('ocupada', sql_valor('SELECT estado FROM mesas WHERE numero_mesa = 5'));
    $admin = como('admin');
    igual(404, $admin->get("/api/facturas/$id")->status, 'aún sin factura');
    $cambiar = fn (string $e) => $admin->put("/api/pedidos/$id/estado", ['estado' => $e])->status;
    igual(409, $cambiar('listo'), 'no se salta la cocina');
    igual(200, $cambiar('en_preparacion'));
    igual(409, $cambiar('pendiente'), 'no se devuelve');
    igual(200, $cambiar('listo'));
    igual(200, $cambiar('entregado'));
    igual(409, $cambiar('cancelado'), 'ya entregado');
    $f = $admin->get("/api/facturas/$id")->json();
    verdadero(str_starts_with($f['numero_factura'], 'FAC-'), 'número FAC-');
    igual($p['total'], $f['total']);
    igual('Impoconsumo', $f['impuesto_nombre']);
    igual(8, $f['impuesto_pct']);
    igual(32, strlen($f['codigo_verificacion']));
    igual('disponible', sql_valor('SELECT estado FROM mesas WHERE numero_mesa = 5'));
    igual($p['total'], $admin->get('/api/stats')->json()['ventas_hoy']);
});

prueba('la mesa sigue ocupada si tiene otro pedido', function (): void {
    $p1 = crear_pedido(3);
    crear_pedido(3);
    como('admin')->put("/api/pedidos/{$p1['id_pedido']}/estado", ['estado' => 'cancelado']);
    igual('ocupada', sql_valor('SELECT estado FROM mesas WHERE numero_mesa = 3'));
});

prueba('cancelado no cuenta en ventas', function (): void {
    $p = crear_pedido();
    $admin = como('admin');
    $admin->put("/api/pedidos/{$p['id_pedido']}/estado", ['estado' => 'cancelado']);
    $s = $admin->get('/api/stats')->json();
    igual(0, $s['ventas_hoy']);
    igual(0, $s['pedidos_hoy']);
});

prueba('el comensal consulta su pedido y su factura con el token', function (): void {
    $p = crear_pedido(5, [['id' => 3, 'cantidad' => 2]]);
    $d = cliente()->get("/api/pedidos/token/{$p['token']}")->json();
    igual('Ceviche de Camarón', $d['items'][0]['nombre']);
    igual(2, $d['items'][0]['cantidad']);
    igual(404, cliente()->get('/api/pedidos/token/' . str_repeat('0', 32))->status);
    igual(404, cliente()->get('/api/pedidos/token/xyz')->status);
    entregar(como('admin'), $p['id_pedido']);
    igual(200, cliente()->get("/api/facturas/token/{$p['token']}")->status);
    igual(401, cliente()->get("/api/facturas/{$p['id_pedido']}")->status, 'por id solo el personal');
    igual(401, cliente()->get("/api/pedidos/{$p['id_pedido']}")->status);
});

prueba('verificación pública del comprobante', function (): void {
    $p = crear_pedido(5, [['id' => 5, 'cantidad' => 2]]);
    entregar(como('admin'), $p['id_pedido']);
    $codigo = cliente()->get("/api/facturas/token/{$p['token']}")->json()['codigo_verificacion'];
    $v = cliente()->get("/api/verificar/$codigo")->json();
    igual(true, $v['valido']);
    igual($p['total'], $v['total']);
    igual(5, $v['numero_mesa']);
    igual(2, $v['unidades']);
    verdadero(!isset($v['token']) && !isset($v['codigo_verificacion']), 'no expone códigos');
    igual(404, cliente()->get('/api/verificar/' . str_repeat('0', 32))->status);
    igual(404, cliente()->get('/api/verificar/no-es-un-codigo')->status);
});

prueba('método de pago (admin y mesero)', function (): void {
    $p = crear_pedido();
    entregar(como('admin'), $p['id_pedido']);
    igual(200, como('mesero')->put("/api/facturas/{$p['id_pedido']}/pago", ['metodo_pago' => 'tarjeta'])->status);
    igual('tarjeta', sql_valor('SELECT metodo_pago FROM facturas WHERE id_pedido = ?', [$p['id_pedido']]));
    igual(400, como('admin')->put("/api/facturas/{$p['id_pedido']}/pago", ['metodo_pago' => 'bitcoin'])->status);
    igual(403, como('chef')->put("/api/facturas/{$p['id_pedido']}/pago", ['metodo_pago' => 'efectivo'])->status);
});

prueba('transiciones por rol y quién entregó', function (): void {
    $id = crear_pedido()['id_pedido'];
    $chef = como('chef');
    $mesero = como('mesero');
    $cambiar = fn (Cliente $c, string $e) => $c->put("/api/pedidos/$id/estado", ['estado' => $e])->status;
    igual(403, $cambiar($mesero, 'en_preparacion'), 'el mesero no cocina');
    igual(200, $cambiar($chef, 'en_preparacion'));
    igual(403, $cambiar($mesero, 'cancelado'));
    igual(200, $cambiar($chef, 'listo'));
    igual(403, $cambiar($chef, 'entregado'), 'el chef no entrega');
    igual(403, $cambiar($chef, 'cancelado'), 'listo: solo el admin cancela');
    igual(200, $cambiar($mesero, 'entregado'));
    igual('mesero', sql_valor('SELECT u.usuario FROM pedidos p JOIN usuarios u ON p.id_usuario = u.id_usuario WHERE p.id_pedido = ?', [$id]));
});

prueba('filtros de la lista de pedidos', function (): void {
    $p1 = crear_pedido(3);
    crear_pedido(4, [['id' => 6, 'cantidad' => 2]], ['notas' => 'Sin sal']);
    $admin = como('admin');
    $admin->put("/api/pedidos/{$p1['id_pedido']}/estado", ['estado' => 'cancelado']);
    igual(1, count($admin->get('/api/pedidos?mesa=3')->json()));
    igual(1, count($admin->get('/api/pedidos?estado=cancelado')->json()));
    igual(2, count($admin->get('/api/pedidos?estado=pendiente,cancelado')->json()));
    igual(1, count($admin->get('/api/pedidos?numero=' . $p1['numero_pedido'])->json()));
    igual(2, count($admin->get('/api/pedidos?fecha=' . date('Y-m-d'))->json()));
    igual([], $admin->get('/api/pedidos?fecha=2020-01-01')->json());
    igual(400, $admin->get('/api/pedidos?limit=xyz')->status);
    igual(400, $admin->get('/api/pedidos?estado=inventado')->status);
    $cocina = como('chef')->get('/api/pedidos?estado=pendiente,en_preparacion&items=1&orden=asc&limit=100')->json();
    igual(1, count($cocina));
    igual('Sin sal', $cocina[0]['notas']);
    igual('Sancocho Trifásico', $cocina[0]['items'][0]['nombre']);
    igual(2, $cocina[0]['items'][0]['cantidad']);
    igual('qr', $cocina[0]['origen']);
    verdadero(str_contains($cocina[0]['fecha_pedido'], 'T'), 'fecha en formato ISO');
});

prueba('límite de 20 pedidos por dispositivo', function (): void {
    for ($i = 0; $i < 20; $i++) {
        crear_pedido(2, [['id' => 12, 'cantidad' => 1]]);
    }
    igual(429, cliente()->post('/api/pedidos', ['mesa' => 2, 'codigo' => codigo_mesa(2), 'items' => [['id' => 12, 'cantidad' => 1]]])->status);
});

// ============================================================
grupo('Llamar mesero y cupones');
// ============================================================
prueba('llamar al mesero y atender', function (): void {
    $c = cliente();
    $llamar = fn () => $c->post('/api/llamados', ['mesa' => 4, 'codigo' => codigo_mesa(4)]);
    $r = $llamar();
    igual(201, $r->status);
    igual(false, $r->json()['ya_pendiente']);
    $r = $llamar();
    igual(200, $r->status);
    igual(true, $r->json()['ya_pendiente'], 'no duplica el aviso');
    $mesero = como('mesero');
    $pendientes = $mesero->get('/api/llamados')->json();
    igual([4], array_column($pendientes, 'numero_mesa'));
    igual(200, $mesero->put("/api/llamados/{$pendientes[0]['id_llamado']}/atender")->status);
    igual([], $mesero->get('/api/llamados')->json());
    igual('mesero', sql_valor("SELECT u.usuario FROM llamados l JOIN usuarios u ON l.id_usuario = u.id_usuario"));
    igual(201, $llamar()->status, 'puede volver a llamar');
    igual(404, $mesero->put('/api/llamados/999/atender')->status);
});

prueba('llamados inválidos y permisos', function (): void {
    igual(403, cliente()->post('/api/llamados', ['mesa' => 4, 'codigo' => '0000000000'])->status);
    igual(404, cliente()->post('/api/llamados', ['mesa' => 99, 'codigo' => 'abc'])->status);
    igual(400, cliente()->post('/api/llamados', ['mesa' => 'x'])->status);
    igual(401, cliente()->get('/api/llamados')->status);
    igual(403, como('chef')->get('/api/llamados')->status);
    igual(200, como('admin')->get('/api/llamados')->status);
});

prueba('límite de llamados por dispositivo', function (): void {
    $c = cliente();
    foreach ([1, 2, 3, 4, 5, 6, 7, 8, 9, 10] as $mesa) {
        igual(201, $c->post('/api/llamados', ['mesa' => $mesa, 'codigo' => codigo_mesa($mesa)])->status, "mesa $mesa");
    }
    igual(429, $c->post('/api/llamados', ['mesa' => 11, 'codigo' => codigo_mesa(11)])->status);
});

prueba('validar cupón', function (): void {
    igual(['ok' => true, 'codigo' => 'BIENVENIDO', 'descuento' => 10], cliente()->get('/api/cupones/validar?codigo=bienvenido')->json());
    igual(404, cliente()->get('/api/cupones/validar?codigo=FALSO')->status);
    igual(400, cliente()->get('/api/cupones/validar')->status);
});

// ============================================================
grupo('Entrar sin QR (PERMITIR_SIN_QR)');
// ============================================================
prueba('pedido sin código queda marcado y lo ve el personal', function (): void {
    $r = cliente('sin_qr')->post('/api/pedidos', ['mesa' => 7, 'items' => [['id' => 12, 'cantidad' => 1]], 'propina' => false]);
    igual(201, $r->status, $r->cuerpo);
    $id = $r->json()['id_pedido'];
    igual('manual', sql_valor('SELECT origen FROM pedidos WHERE id_pedido = ?', [$id]));
    $lista = como('chef')->get('/api/pedidos?estado=pendiente&items=1')->json();
    igual('manual', $lista[0]['origen']);
});

prueba('con QR el pedido queda como qr; código equivocado siempre se rechaza', function (): void {
    $r = cliente('sin_qr')->post('/api/pedidos', ['mesa' => 7, 'codigo' => codigo_mesa(7), 'items' => [['id' => 12, 'cantidad' => 1]]]);
    igual('qr', sql_valor('SELECT origen FROM pedidos WHERE id_pedido = ?', [$r->json()['id_pedido']]));
    igual(403, cliente('sin_qr')->post('/api/pedidos', ['mesa' => 7, 'codigo' => '0000000000', 'items' => [['id' => 12, 'cantidad' => 1]]])->status);
    igual(404, cliente('sin_qr')->post('/api/pedidos', ['mesa' => 99, 'items' => [['id' => 12, 'cantidad' => 1]]])->status);
    igual(409, cliente('sin_qr')->post('/api/pedidos', ['mesa' => 16, 'items' => [['id' => 12, 'cantidad' => 1]]])->status);
});

prueba('llamar mesero sin código y flujo completo de un pedido sin QR', function (): void {
    igual(201, cliente('sin_qr')->post('/api/llamados', ['mesa' => 9])->status);
    $r = cliente('sin_qr')->post('/api/pedidos', ['mesa' => 11, 'items' => [['id' => 5, 'cantidad' => 1]]]);
    entregar(como('admin'), $r->json()['id_pedido']);
    verdadero(str_starts_with(cliente('sin_qr')->get('/api/facturas/token/' . $r->json()['token'])->json()['numero_factura'], 'FAC-'), 'factura');
});

prueba('con PERMITIR_SIN_QR=false la API rechaza pedidos sin código', function (): void {
    $r = cliente()->post('/api/pedidos', ['mesa' => 7, 'items' => [['id' => 12, 'cantidad' => 1]]]);
    igual(403, $r->status);
    igual('qr_requerido', $r->json()['codigo']);
    igual(403, cliente()->post('/api/llamados', ['mesa' => 9])->status);
    igual(201, cliente()->post('/api/pedidos', ['mesa' => 7, 'codigo' => codigo_mesa(7), 'items' => [['id' => 12, 'cantidad' => 1]]])->status);
});

// ============================================================
grupo('Matriz de permisos');
// ============================================================
prueba('cada endpoint del personal: 401 sin sesión y 403 al rol sin permiso', function (): void {
    $id = crear_pedido()['id_pedido'];
    entregar(como('admin'), crear_pedido()['id_pedido']);   // pedido 2 con factura
    $endpoints = [
        ['GET', '/api/mesas', null, ['admin', 'chef', 'mesero']],
        ['PUT', '/api/mesas/1/estado', ['estado' => 'reservada'], ['admin', 'mesero']],
        ['GET', '/api/pedidos', null, ['admin', 'chef', 'mesero']],
        ['GET', "/api/pedidos/$id", null, ['admin', 'chef', 'mesero']],
        ['GET', '/api/facturas/2', null, ['admin', 'chef', 'mesero']],
        ['PUT', '/api/facturas/2/pago', ['metodo_pago' => 'tarjeta'], ['admin', 'mesero']],
        ['GET', '/api/llamados', null, ['admin', 'mesero']],
        ['GET', '/api/stats', null, ['admin']],
    ];
    $clientes = ['admin' => como('admin'), 'chef' => como('chef'), 'mesero' => como('mesero')];
    foreach ($endpoints as [$metodo, $ruta, $cuerpo, $permitidos]) {
        $r = cliente()->pedir($metodo, $ruta, $cuerpo);
        igual(401, $r->status, "$metodo $ruta sin sesión");
        foreach ($clientes as $rol => $c) {
            $r = $c->pedir($metodo, $ruta, $cuerpo);
            if (in_array($rol, $permitidos, true)) {
                verdadero(in_array($r->status, [200, 201], true), "$rol en $metodo $ruta (respondió {$r->status})");
            } else {
                igual(403, $r->status, "$rol en $metodo $ruta");
                igual('sin_permiso', $r->json()['codigo']);
            }
        }
    }
});
