<?php
/** Fase 4: panel de administración, reportes y respaldo. */

declare(strict_types=1);

// ============================================================
grupo('Administración: permisos');
// ============================================================
prueba('todo lo de administración es solo para el Administrador', function (): void {
    $rutas = [
        ['GET', '/api/categorias?todas=1', null], ['GET', '/api/productos?todas=1', null],
        ['POST', '/api/productos', ['nombre' => 'X', 'precio' => 1000, 'id_categoria' => 1]],
        ['PUT', '/api/productos/1', ['precio' => 13000]], ['DELETE', '/api/productos/2', null],
        ['POST', '/api/categorias', ['nombre_categoria' => 'Sopas']], ['PUT', '/api/categorias/1', ['orden' => 9]],
        ['DELETE', '/api/categorias/4', null],
        ['POST', '/api/mesas', ['numero_mesa' => 30, 'capacidad' => 4]], ['PUT', '/api/mesas/1', ['capacidad' => 3]],
        ['DELETE', '/api/mesas/20', null], ['POST', '/api/mesas/1/regenerar-qr', null],
        ['GET', '/api/roles', null], ['GET', '/api/usuarios', null],
        ['POST', '/api/usuarios', ['nombre' => 'Ana', 'usuario' => 'ana', 'id_rol' => 3]],
        ['PUT', '/api/usuarios/3', ['nombre' => 'Mesero Uno']],
        ['GET', '/api/cupones', null], ['POST', '/api/cupones', ['codigo' => 'NUEVO10', 'descuento' => 10]],
        ['PUT', '/api/cupones/1', ['descuento' => 12]], ['DELETE', '/api/cupones/2', null],
        ['GET', '/api/reportes/ventas', null], ['GET', '/api/reportes/ventas.csv', null], ['GET', '/api/respaldo', null],
        // Al final: restablecer la clave del mesero cierra su sesión (es lo correcto)
        ['POST', '/api/usuarios/3/restablecer-clave', null],
    ];
    $chef = como('chef');
    $mesero = como('mesero');
    $admin = como('admin');
    foreach ($rutas as [$m, $r, $c]) {
        igual(401, cliente()->pedir($m, $r, $c)->status, "$m $r sin sesión");
        igual(403, $chef->pedir($m, $r, $c)->status, "$m $r chef");
        igual(403, $mesero->pedir($m, $r, $c)->status, "$m $r mesero");
        verdadero(!in_array($admin->pedir($m, $r, $c)->status, [401, 403], true), "$m $r admin");
    }
});

// ============================================================
grupo('Administración: carta y categorías');
// ============================================================
prueba('crear, editar y quitar productos (borrado lógico)', function (): void {
    $a = como('admin');
    $r = $a->post('/api/productos', ['nombre' => 'Ajiaco Santafereño', 'precio' => 25900, 'id_categoria' => 2, 'emoji' => '🥘']);
    igual(201, $r->status, $r->cuerpo);
    $id = $r->json()['id_producto'];
    igual('Ajiaco Santafereño', sql_valor('SELECT nombre FROM productos WHERE id_producto = ?', [$id]));
    igual(200, $a->put("/api/productos/$id", ['disponible' => false, 'precio' => 26500])->status);
    igual(['precio' => 26500, 'disponible' => 0], sql_uno('SELECT precio, disponible FROM productos WHERE id_producto = ?', [$id]));
    $p = crear_pedido(5, [['id' => 5, 'cantidad' => 1]]);
    igual(200, $a->delete('/api/productos/5')->status, 'no falla por la llave foránea');
    verdadero(!in_array('Bandeja Paisa', array_column(cliente()->get('/api/productos')->json(), 'nombre'), true), 'sale de la carta');
    igual('Bandeja Paisa', cliente()->get("/api/pedidos/token/{$p['token']}")->json()['items'][0]['nombre'], 'el historial se conserva');
    igual(404, $a->delete('/api/productos/5')->status);
});

prueba('validación de productos', function (): void {
    $a = como('admin');
    igual(400, $a->post('/api/productos', ['nombre' => '', 'precio' => 100, 'id_categoria' => 1])->status);
    igual(400, $a->post('/api/productos', ['nombre' => 'A', 'precio' => 0, 'id_categoria' => 1])->status);
    igual(400, $a->post('/api/productos', ['nombre' => 'A', 'precio' => 100, 'id_categoria' => 77])->status);
    igual(400, $a->put('/api/productos/1', ['imagen_url' => 'javascript:alert(1)'])->status);
    igual(404, $a->put('/api/productos/999', ['precio' => 100])->status);
});

prueba('categorías: crear, duplicada, editar y eliminar', function (): void {
    $a = como('admin');
    $r = $a->post('/api/categorias', ['nombre_categoria' => 'Sopas', 'descripcion' => 'Calientes', 'orden' => 5]);
    igual(201, $r->status);
    $id = $r->json()['id_categoria'];
    igual(409, $a->post('/api/categorias', ['nombre_categoria' => 'sopas'])->status, 'duplicada');
    igual(200, $a->put("/api/categorias/$id", ['nombre_categoria' => 'Sopas y cremas'])->status);
    verdadero(in_array('Sopas y cremas', array_column(cliente()->get('/api/categorias')->json(), 'nombre_categoria'), true), 'visible');
    igual(200, $a->delete("/api/categorias/$id")->status);
    igual(404, $a->put("/api/categorias/$id", ['orden' => 1])->status);
    $r = $a->delete('/api/categorias/1');
    igual(409, $r->status, 'con productos no se borra');
    contiene('producto', $r->json()['msg']);
});

prueba('categoría desactivada oculta sus productos; el admin los ve', function (): void {
    $a = como('admin');
    $a->put('/api/categorias/4', ['activo' => false]);
    verdadero(!in_array('Postres', array_column(cliente()->get('/api/productos')->json(), 'cat'), true), 'carta pública');
    verdadero(!in_array('Postres', array_column(cliente()->get('/api/categorias')->json(), 'nombre_categoria'), true), 'categorías públicas');
    verdadero(in_array('Postres', array_column($a->get('/api/productos?todas=1')->json(), 'cat'), true), 'admin');
    $cats = $a->get('/api/categorias?todas=1')->json();
    igual(4, count($cats));
    igual(4, $cats[3]['productos']);
});

prueba('categoría con historial se desactiva en vez de borrarse', function (): void {
    crear_pedido(5, [['id' => 15, 'cantidad' => 1]]);   // Tres Leches (Postres)
    $a = como('admin');
    foreach ([15, 16, 17, 18] as $id) {
        $a->delete("/api/productos/$id");
    }
    $r = $a->delete('/api/categorias/4');
    igual(200, $r->status);
    contiene('desactivó', $r->json()['msg']);
    igual(0, (int) sql_valor('SELECT activo FROM categorias WHERE id_categoria = 4'));
});

// ============================================================
grupo('Administración: mesas');
// ============================================================
prueba('crear mesa con código QR y validar datos', function (): void {
    $a = como('admin');
    igual(201, $a->post('/api/mesas', ['numero_mesa' => 21, 'capacidad' => 2])->status);
    verdadero((bool) preg_match('/^[0-9a-f]{10}$/', (string) codigo_mesa(21)), 'código de 10 caracteres');
    igual(409, $a->post('/api/mesas', ['numero_mesa' => 21])->status);
    foreach ([['numero_mesa' => 0], ['numero_mesa' => 1000], ['numero_mesa' => 'x'], ['numero_mesa' => 40, 'capacidad' => 0]] as $c) {
        igual(400, $a->post('/api/mesas', $c)->status, json_encode($c));
    }
});

prueba('editar y eliminar mesas', function (): void {
    $a = como('admin');
    igual(200, $a->put('/api/mesas/20', ['capacidad' => 10, 'estado' => 'reservada'])->status);
    igual(['capacidad' => 10, 'estado' => 'reservada'], sql_uno('SELECT capacidad, estado FROM mesas WHERE numero_mesa = 20'));
    igual(200, $a->delete('/api/mesas/20')->status);
    crear_pedido(5);
    $id5 = (int) sql_valor('SELECT id_mesa FROM mesas WHERE numero_mesa = 5');
    $r = $a->delete("/api/mesas/$id5");
    igual(409, $r->status, 'con pedidos no se borra');
    contiene('inactiva', $r->json()['msg']);
});

prueba('regenerar el código QR: el anterior deja de funcionar', function (): void {
    $viejo = codigo_mesa(5);
    $id5 = (int) sql_valor('SELECT id_mesa FROM mesas WHERE numero_mesa = 5');
    $r = como('admin')->post("/api/mesas/$id5/regenerar-qr");
    igual(200, $r->status);
    $nuevo = codigo_mesa(5);
    igual($nuevo, $r->json()['codigo_qr']);
    verdadero($nuevo !== $viejo, 'código distinto');
    igual(403, cliente()->get("/api/mesas/5?c=$viejo")->status, 'el QR impreso ya no sirve');
    igual(200, cliente()->get("/api/mesas/5?c=$nuevo")->status);
    igual(403, cliente()->post('/api/pedidos', ['mesa' => 5, 'codigo' => $viejo, 'items' => [['id' => 1, 'cantidad' => 1]]])->status);
    igual(404, como('admin')->post('/api/mesas/999/regenerar-qr')->status);
});

// ============================================================
grupo('Administración: personal');
// ============================================================
prueba('crear usuario con contraseña temporal aleatoria', function (): void {
    $r = como('admin')->post('/api/usuarios', ['nombre' => 'Ana Gómez', 'usuario' => 'Ana.Gomez', 'id_rol' => 3, 'correo' => 'ana@restaurante.co']);
    igual(201, $r->status, $r->cuerpo);
    $d = $r->json();
    igual('ana.gomez', $d['usuario']);
    verdadero((bool) preg_match('/^Temporal-[A-Za-z2-9]{4}-[A-Za-z2-9]{4}$/', $d['clave_temporal']), 'formato de la clave temporal');
    $g = sql_uno("SELECT contrasena_hash, debe_cambiar_clave FROM usuarios WHERE usuario = 'ana.gomez'");
    igual(1, $g['debe_cambiar_clave']);
    verdadero(!str_contains($g['contrasena_hash'], $d['clave_temporal']), 'solo se guarda el hash');
    $r = cliente()->post('/api/auth/login', ['usuario' => 'ana.gomez', 'password' => $d['clave_temporal']]);
    igual(true, $r->json()['user']['debe_cambiar_clave']);
    verdadero(!str_contains(como('admin')->get('/api/usuarios')->cuerpo, 'clave_temporal'), 'la lista no muestra claves');
});

prueba('usuarios inválidos', function (): void {
    $a = como('admin');
    foreach ([[['nombre' => 'X', 'usuario' => 'ab', 'id_rol' => 3], 400], [['nombre' => 'X', 'usuario' => 'con espacio', 'id_rol' => 3], 400],
              [['nombre' => 'X', 'usuario' => 'nuevo', 'id_rol' => 99], 400], [['nombre' => 'X', 'usuario' => 'nuevo', 'id_rol' => 3, 'correo' => 'malo'], 400],
              [['nombre' => '', 'usuario' => 'nuevo', 'id_rol' => 3], 400], [['nombre' => 'X', 'usuario' => 'chef', 'id_rol' => 3], 409]] as [$c, $codigo]) {
        igual($codigo, $a->post('/api/usuarios', $c)->status, json_encode($c));
    }
});

prueba('restablecer clave cierra la sesión y exige cambio', function (): void {
    $sesionMesero = como('mesero');
    $r = como('admin')->post('/api/usuarios/3/restablecer-clave');
    igual(200, $r->status);
    igual(401, $sesionMesero->get('/api/pedidos')->status, 'su sesión se cerró');
    $l = cliente()->post('/api/auth/login', ['usuario' => 'mesero', 'password' => $r->json()['clave_temporal']]);
    igual(true, $l->json()['user']['debe_cambiar_clave']);
});

prueba('desactivar usuario y cambiar rol', function (): void {
    $chef = como('chef');
    $a = como('admin');
    igual(403, $chef->get('/api/llamados')->status);
    igual(200, $a->put('/api/usuarios/2', ['id_rol' => 3])->status);
    igual(200, $chef->get('/api/llamados')->status, 'el rol nuevo aplica de inmediato');
    igual(200, $a->put('/api/usuarios/2', ['activo' => false])->status);
    igual(401, $chef->get('/api/pedidos')->status, 'desactivado: sesión cerrada');
});

prueba('el admin no puede desactivarse ni quedarse sin administradores', function (): void {
    $a = como('admin');
    igual(409, $a->put('/api/usuarios/1', ['activo' => false])->status);
    igual(409, $a->put('/api/usuarios/1', ['id_rol' => 2])->status);
    igual(409, $a->post('/api/usuarios/1/restablecer-clave')->status);
    $g = $a->post('/api/usuarios', ['nombre' => 'Gerente', 'usuario' => 'gerente', 'id_rol' => 1])->json()['id_usuario'];
    igual(200, $a->put("/api/usuarios/$g", ['activo' => false])->status);
    igual(1, (int) sql_valor('SELECT COUNT(*) FROM usuarios WHERE id_rol = 1 AND activo = 1'));
});

// ============================================================
grupo('Administración: cupones');
// ============================================================
prueba('crear, desactivar y borrar cupones', function (): void {
    $a = como('admin');
    $r = $a->post('/api/cupones', ['codigo' => 'verano25', 'descuento' => 25, 'fecha_fin' => '2099-01-31']);
    igual(201, $r->status);
    $id = $r->json()['id_cupon'];
    igual(25, cliente()->get('/api/cupones/validar?codigo=VERANO25')->json()['descuento']);
    igual(409, $a->post('/api/cupones', ['codigo' => 'VERANO25', 'descuento' => 5])->status);
    igual(200, $a->put("/api/cupones/$id", ['activo' => false])->status);
    igual(404, cliente()->get('/api/cupones/validar?codigo=VERANO25')->status);
    igual(200, $a->delete("/api/cupones/$id")->status);
});

prueba('cupones inválidos y vencidos', function (): void {
    $a = como('admin');
    foreach ([['codigo' => 'AB', 'descuento' => 10], ['codigo' => 'CON ESPACIO', 'descuento' => 10], ['codigo' => 'VALIDO', 'descuento' => 0],
              ['codigo' => 'VALIDO', 'descuento' => 101], ['codigo' => 'VALIDO', 'descuento' => 10, 'fecha_fin' => '31/12/2026']] as $c) {
        igual(400, $a->post('/api/cupones', $c)->status, json_encode($c));
    }
    $a->post('/api/cupones', ['codigo' => 'VIEJO', 'descuento' => 30, 'fecha_fin' => '2020-01-01']);
    igual(404, cliente()->get('/api/cupones/validar?codigo=VIEJO')->status);
    $viejo = array_values(array_filter($a->get('/api/cupones')->json(), fn ($c) => $c['codigo'] === 'VIEJO'))[0];
    igual(1, $viejo['vencido']);
    igual(30, $viejo['descuento']);
});

prueba('cupón usado se desactiva en vez de borrarse', function (): void {
    crear_pedido(5, null, ['cupon' => 'BIENVENIDO']);
    $a = como('admin');
    $c = array_values(array_filter($a->get('/api/cupones')->json(), fn ($c) => $c['codigo'] === 'BIENVENIDO'))[0];
    igual(1, $c['usos']);
    $r = $a->delete("/api/cupones/{$c['id_cupon']}");
    contiene('desactivó', $r->json()['msg']);
    igual(0, (int) sql_valor("SELECT activo FROM cupones WHERE codigo = 'BIENVENIDO'"));
});

// ============================================================
grupo('Reportes de ventas');
// ============================================================
/** Cuatro ventas entregadas en fechas conocidas, un cancelado y un pendiente. */
function ventas_de_prueba(): void
{
    $admin = como('admin');
    $vender = function (array $items, string $fecha) use ($admin): void {
        $p = crear_pedido(5, $items, ['propina' => false]);
        entregar($admin, $p['id_pedido']);
        sql_ejecutar('UPDATE facturas SET fecha_factura = ? WHERE id_pedido = ?', ["$fecha 13:30:00", $p['id_pedido']]);
    };
    $vender([['id' => 5, 'cantidad' => 2]], '2026-09-07');    // lunes, 57.000
    $vender([['id' => 10, 'cantidad' => 1]], '2026-09-09');   // misma semana, 7.500
    $vender([['id' => 7, 'cantidad' => 1]], '2026-09-14');    // semana siguiente, 32.000
    $vender([['id' => 3, 'cantidad' => 1]], '2026-08-20');    // mes anterior, 18.000
    $c = crear_pedido(5);
    $admin->put("/api/pedidos/{$c['id_pedido']}/estado", ['estado' => 'cancelado']);
    sql_ejecutar("UPDATE pedidos SET fecha_pedido = '2026-09-08 12:00:00' WHERE id_pedido = ?", [$c['id_pedido']]);
    $p = crear_pedido(5);   // pendiente: no cuenta
    sql_ejecutar("UPDATE pedidos SET fecha_pedido = '2026-09-08 12:00:00' WHERE id_pedido = ?", [$p['id_pedido']]);
}

function con_impuesto(int $subtotal): int
{
    return $subtotal + (int) round($subtotal * 0.08);
}

prueba('reporte por día', function (): void {
    ventas_de_prueba();
    $r = como('admin')->get('/api/reportes/ventas?periodo=dia&desde=2026-09-07&hasta=2026-09-14')->json();
    igual(8, count($r['series']), 'incluye los días sin ventas');
    $dias = array_column($r['series'], null, 'inicio');
    igual(1, $dias['2026-09-07']['pedidos']);
    igual(con_impuesto(57000), $dias['2026-09-07']['total']);
    igual(0, $dias['2026-09-08']['total']);
    igual('07/09/2026', $dias['2026-09-07']['etiqueta']);
    igual(3, $r['resumen']['pedidos']);
    igual(57000 + 7500 + 32000, $r['resumen']['subtotal']);
    igual(con_impuesto(57000) + con_impuesto(7500) + con_impuesto(32000), $r['resumen']['total']);
    igual((int) round($r['resumen']['total'] / 3), $r['resumen']['ticket_promedio']);
    igual(1, $r['resumen']['cancelados']);
});

prueba('reporte por semana (empieza el lunes) y por mes', function (): void {
    ventas_de_prueba();
    $a = como('admin');
    $s = $a->get('/api/reportes/ventas?periodo=semana&desde=2026-09-07&hasta=2026-09-20')->json();
    igual([['2026-09-07', 2], ['2026-09-14', 1]], array_map(fn ($x) => [$x['inicio'], $x['pedidos']], $s['series']));
    igual(64500, $s['series'][0]['subtotal']);
    igual('07/09 – 13/09/2026', $s['series'][0]['etiqueta']);
    igual('2026-09-07', $a->get('/api/reportes/ventas?periodo=semana&desde=2026-09-09&hasta=2026-09-13')->json()['series'][0]['inicio']);
    $m = $a->get('/api/reportes/ventas?periodo=mes&desde=2026-08-01&hasta=2026-09-30')->json();
    igual([['2026-08-01', 1, 18000], ['2026-09-01', 3, 96500]], array_map(fn ($x) => [$x['inicio'], $x['pedidos'], $x['subtotal']], $m['series']));
    igual('Septiembre 2026', $m['series'][1]['etiqueta']);
});

prueba('productos, categorías y métodos de pago del reporte', function (): void {
    ventas_de_prueba();
    $r = como('admin')->get('/api/reportes/ventas?periodo=mes&desde=2026-09-01&hasta=2026-09-30')->json();
    igual(['producto' => 'Bandeja Paisa', 'unidades' => 2, 'ventas' => 57000], $r['productos'][0]);
    igual(['Principales' => 89000, 'Bebidas' => 7500], array_column($r['categorias'], 'ventas', 'categoria'));
    igual([['metodo_pago' => 'efectivo', 'pedidos' => 3, 'total' => $r['resumen']['total']]], $r['pagos']);
});

prueba('rangos por defecto y parámetros inválidos', function (): void {
    $a = como('admin');
    $d = $a->get('/api/reportes/ventas?periodo=dia')->json();
    igual(30, count($d['series']));
    igual(date('Y-m-d'), $d['hasta']);
    $s = $a->get('/api/reportes/ventas?periodo=semana')->json();
    igual(12, count($s['series']));
    igual('1', date('N', strtotime($s['series'][0]['inicio'])), 'empieza en lunes');
    $m = $a->get('/api/reportes/ventas?periodo=mes')->json();
    igual(12, count($m['series']));
    igual(date('Y-m-01'), end($m['series'])['inicio']);
    foreach (['periodo=anio', 'desde=2026-09-10&hasta=2026-09-01', 'desde=10/09/2026', 'desde=2020-01-01&hasta=2026-01-01'] as $qs) {
        igual(400, $a->get("/api/reportes/ventas?$qs")->status, $qs);
    }
});

prueba('CSV para Excel (punto y coma y BOM)', function (): void {
    ventas_de_prueba();
    $r = como('admin')->get('/api/reportes/ventas.csv?periodo=semana&desde=2026-09-07&hasta=2026-09-20');
    igual(200, $r->status);
    verdadero(str_starts_with((string) $r->cabecera('content-type'), 'text/csv'), 'tipo CSV');
    contiene('filename="ventas_semana_2026-09-07_2026-09-20.csv"', (string) $r->cabecera('content-disposition'));
    verdadero(str_starts_with($r->cuerpo, "\u{FEFF}"), 'BOM para las tildes');
    $lineas = explode("\r\n", substr($r->cuerpo, 3));
    igual('Semana;Pedidos;Subtotal;Descuentos;Impuesto;Propinas;Total;"Ticket promedio"', $lineas[2]);
    verdadero(str_starts_with($lineas[3], '"07/09 – 13/09/2026";2;64500;'), 'primera semana');
    contiene('TOTAL;3;96500;', $r->cuerpo);
    contiene('"Bandeja Paisa";2;57000', $r->cuerpo);
    contiene('"Pedidos cancelados";1', $r->cuerpo);
});

prueba('una venta de hoy aparece en el reporte del día', function (): void {
    $p = crear_pedido(5, [['id' => 6, 'cantidad' => 1]]);
    $a = como('admin');
    entregar($a, $p['id_pedido']);
    $series = $a->get('/api/reportes/ventas?periodo=dia')->json()['series'];
    igual(date('Y-m-d'), end($series)['inicio']);
    igual($p['total'], end($series)['total']);
});

// ============================================================
grupo('Respaldo');
// ============================================================
prueba('descargar respaldo desde el panel (.sql.gz completo)', function (): void {
    crear_pedido(5, null, ['notas' => 'Respaldo con tildes: ñandú; y punto y coma']);
    $r = como('admin')->get('/api/respaldo');
    igual(200, $r->status);
    igual('application/gzip', $r->cabecera('content-type'));
    verdadero((bool) preg_match('/filename="restaurante_sena_\d{8}_\d{6}\.sql\.gz"/', (string) $r->cabecera('content-disposition')), 'nombre del archivo');
    $sql = gzdecode($r->cuerpo);
    contiene('CREATE TABLE `pedidos`', $sql);
    contiene('Respaldo con tildes: ñandú; y punto y coma', $sql);
    contiene('CREATE OR REPLACE VIEW `v_ventas_por_categoria`', $sql);
    contiene('-- Respaldo completo', $sql);
    verdadero(!str_contains($sql, 'DEFINER'), 'sin DEFINER');
    verdadero(!str_contains($sql, '`' . BD_PRUEBAS . '`.'), 'sin el nombre de la base');
    verdadero(!preg_match('/INSERT INTO `sesiones`/', $sql), 'sin sesiones');
});

prueba('el respaldo se restaura en una base con otro nombre (como la del hosting)', function (): void {
    $p = crear_pedido(5, [['id' => 3, 'cantidad' => 2]], ['notas' => "Comillas ' y \\ barra"]);
    $gz = como('admin')->get('/api/respaldo')->cuerpo;
    $archivo = sys_get_temp_dir() . '/respaldo_prueba_' . getmypid() . '.sql.gz';
    file_put_contents($archivo, $gz);
    $otra = 'u123456789_restaurada_test';
    try {
        $cmd = escapeshellarg(PHP_BINARY) . ' ' . escapeshellarg(RAIZ . '/scripts/restaurar.php') . " --si --bd=$otra " . escapeshellarg($archivo);
        exec($cmd . ' 2>&1', $salida, $codigo);
        igual(0, $codigo, implode(' ', $salida));
        $pdo = pdo_servidor();
        $fila = $pdo->query("SELECT p.total, p.notas, d.nombre_producto FROM `$otra`.pedidos p
            JOIN `$otra`.detalle_pedidos d ON d.id_pedido = p.id_pedido WHERE p.token = '{$p['token']}'")->fetch();
        igual(['total' => $p['total'], 'notas' => "Comillas ' y \\ barra", 'nombre_producto' => 'Ceviche de Camarón'], $fila);
        igual(4, count($pdo->query("SELECT * FROM `$otra`.v_ventas_por_categoria")->fetchAll()), 'las vistas funcionan');
    } finally {
        @unlink($archivo);
        pdo_servidor()->exec("DROP DATABASE IF EXISTS `$otra`");
    }
});

prueba('respaldo de consola con retención de 30 días', function (): void {
    $dir = sys_get_temp_dir() . '/respaldos_prueba_' . getmypid();
    @mkdir($dir);
    $viejo = "$dir/restaurante_sena_20250101_000000.sql.gz";
    $otro = "$dir/otro_archivo.txt";
    file_put_contents($viejo, 'x');
    file_put_contents($otro, 'x');
    touch($viejo, time() - 40 * 86400);
    touch($otro, time() - 40 * 86400);
    try {
        putenv('RS_DB_NAME=' . BD_PRUEBAS);
        exec(escapeshellarg(PHP_BINARY) . ' ' . escapeshellarg(RAIZ . '/scripts/respaldo.php') . ' --dir=' . escapeshellarg($dir) . ' 2>&1', $salida, $codigo);
        putenv('RS_DB_NAME');
        igual(0, $codigo, implode(' ', $salida));
        $nuevos = glob("$dir/restaurante_sena_2*.sql.gz");
        igual(1, count($nuevos), 'un respaldo nuevo');
        contiene('-- Respaldo completo', gzdecode(file_get_contents($nuevos[0])));
        verdadero(!file_exists($viejo), 'el de más de 30 días se borró');
        verdadero(file_exists($otro), 'solo borra respaldos');
    } finally {
        array_map('unlink', glob("$dir/*"));
        @rmdir($dir);
    }
});
