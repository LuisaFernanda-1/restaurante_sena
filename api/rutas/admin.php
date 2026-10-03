<?php
/**
 * admin.php — Endpoints del panel de administración (solo Administrador)
 *
 * Productos, categorías, mesas, personal y cupones. Lo que tiene historial
 * (ventas, pedidos) no se borra: se desactiva, para no perder los reportes.
 */

declare(strict_types=1);

/** UPDATE con columnas de una lista fija (los nombres nunca vienen del usuario). */
function actualizar(string $tabla, string $colId, int $id, array $campos): void
{
    if (!$campos) {
        throw new ErrorAPI('Nada que actualizar.');
    }
    $asignaciones = implode(', ', array_map(fn ($c) => "$c = ?", array_keys($campos)));
    ejecutar("UPDATE $tabla SET $asignaciones WHERE $colId = ?", [...array_values($campos), $id]);
}

function insertar(string $tabla, array $campos): int
{
    $columnas = implode(', ', array_keys($campos));
    [, $id] = ejecutar("INSERT INTO $tabla ($columnas) VALUES (" . marcas(count($campos)) . ')', array_values($campos));
    return $id;
}

function existe(string $sql, array $p): bool
{
    return consultar_uno($sql, $p) !== null;
}

// ============================================================
// PRODUCTOS
// POST /api/productos · PUT /api/productos/{id} · DELETE /api/productos/{id}
// (GET /api/productos?todas=1 está en publico.php)
// ============================================================
function validar_producto(array $d, bool $parcial = false): array
{
    $c = [];
    if (!$parcial || array_key_exists('nombre', $d)) {
        $c['nombre'] = v_texto($d['nombre'] ?? null, 'Nombre', 100, true);
    }
    if (array_key_exists('descripcion', $d)) {
        $c['descripcion'] = v_texto($d['descripcion'], 'Descripción', 300);
    }
    if (!$parcial || array_key_exists('precio', $d)) {
        $c['precio'] = v_entero($d['precio'] ?? null, 'Precio', 1, 10_000_000);
    }
    if (!$parcial || array_key_exists('id_categoria', $d)) {
        $cat = v_entero($d['id_categoria'] ?? null, 'Categoría', 1);
        if (!existe('SELECT 1 AS ok FROM categorias WHERE id_categoria = ?', [$cat])) {
            throw new ErrorAPI('La categoría no existe.');
        }
        $c['id_categoria'] = $cat;
    }
    if (array_key_exists('emoji', $d)) {
        $c['emoji'] = v_texto($d['emoji'], 'Emoji', 16) ?: null;
    }
    if (array_key_exists('imagen_url', $d)) {
        $url = v_texto($d['imagen_url'], 'Imagen', 255);
        if ($url !== '' && !preg_match('#^(https?://|img/)#', $url)) {
            throw new ErrorAPI('Imagen: debe ser una dirección http(s):// o una ruta img/...');
        }
        $c['imagen_url'] = $url ?: null;
    }
    if (array_key_exists('disponible', $d)) {
        $c['disponible'] = v_bool($d['disponible'], 'Disponible') ? 1 : 0;
    }
    return $c;
}

ruta('POST', '/productos', function (): void {
    exigir_rol([ROL_ADMIN]);
    $c = validar_producto(cuerpo_json());
    $id = insertar('productos', $c);
    responder(['ok' => true, 'id_producto' => $id, 'msg' => "Producto '{$c['nombre']}' creado"], 201);
});

ruta('PUT', '/productos/{id:n}', function (string $id): void {
    exigir_rol([ROL_ADMIN]);
    $c = validar_producto(cuerpo_json(), true);
    if (!existe('SELECT 1 AS ok FROM productos WHERE id_producto = ? AND activo = 1', [(int) $id])) {
        throw new ErrorAPI('Producto no encontrado.', 404);
    }
    actualizar('productos', 'id_producto', (int) $id, $c);
    responder(['ok' => true, 'msg' => 'Producto actualizado']);
});

ruta('DELETE', '/productos/{id:n}', function (string $id): void {
    exigir_rol([ROL_ADMIN]);
    // Borrado lógico: sale de la carta pero se conserva en pedidos y reportes.
    [$filas] = ejecutar('UPDATE productos SET activo = 0, disponible = 0 WHERE id_producto = ? AND activo = 1', [(int) $id]);
    if ($filas === 0) {
        throw new ErrorAPI('Producto no encontrado.', 404);
    }
    responder(['ok' => true, 'msg' => 'Producto eliminado de la carta']);
});

// ============================================================
// CATEGORÍAS
// ============================================================
function validar_categoria(array $d, bool $parcial = false): array
{
    $c = [];
    if (!$parcial || array_key_exists('nombre_categoria', $d)) {
        $c['nombre_categoria'] = v_texto($d['nombre_categoria'] ?? null, 'Nombre', 80, true);
    }
    if (array_key_exists('descripcion', $d)) {
        $c['descripcion'] = v_texto($d['descripcion'], 'Descripción', 200) ?: null;
    }
    if (array_key_exists('orden', $d)) {
        $c['orden'] = v_entero($d['orden'], 'Orden', 0, 999);
    }
    if (array_key_exists('activo', $d)) {
        $c['activo'] = v_bool($d['activo'], 'Activa') ? 1 : 0;
    }
    return $c;
}

ruta('POST', '/categorias', function (): void {
    exigir_rol([ROL_ADMIN]);
    try {
        $id = insertar('categorias', validar_categoria(cuerpo_json()));
    } catch (DBDuplicado) {
        throw new ErrorAPI('Ya existe una categoría con ese nombre.', 409);
    }
    responder(['ok' => true, 'id_categoria' => $id, 'msg' => 'Categoría creada'], 201);
});

ruta('PUT', '/categorias/{id:n}', function (string $id): void {
    exigir_rol([ROL_ADMIN]);
    if (!existe('SELECT 1 AS ok FROM categorias WHERE id_categoria = ?', [(int) $id])) {
        throw new ErrorAPI('Categoría no encontrada.', 404);
    }
    try {
        actualizar('categorias', 'id_categoria', (int) $id, validar_categoria(cuerpo_json(), true));
    } catch (DBDuplicado) {
        throw new ErrorAPI('Ya existe una categoría con ese nombre.', 409);
    }
    responder(['ok' => true, 'msg' => 'Categoría actualizada']);
});

ruta('DELETE', '/categorias/{id:n}', function (string $id): void {
    exigir_rol([ROL_ADMIN]);
    $id = (int) $id;
    if (!existe('SELECT 1 AS ok FROM categorias WHERE id_categoria = ?', [$id])) {
        throw new ErrorAPI('Categoría no encontrada.', 404);
    }
    $activos = (int) consultar_uno('SELECT COUNT(*) AS n FROM productos WHERE id_categoria = ? AND activo = 1', [$id])['n'];
    if ($activos) {
        throw new ErrorAPI("La categoría tiene $activos producto(s) en la carta. Muévalos a otra categoría "
            . 'o elimínelos primero, o desactive la categoría.', 409);
    }
    if (existe('SELECT 1 AS ok FROM productos WHERE id_categoria = ? LIMIT 1', [$id])) {
        // Tiene productos antiguos con ventas: se desactiva en vez de borrar.
        ejecutar('UPDATE categorias SET activo = 0 WHERE id_categoria = ?', [$id]);
        responder(['ok' => true, 'msg' => 'La categoría tiene historial de ventas: se desactivó.']);
    }
    ejecutar('DELETE FROM categorias WHERE id_categoria = ?', [$id]);
    responder(['ok' => true, 'msg' => 'Categoría eliminada']);
});

// ============================================================
// MESAS (cada mesa nueva recibe un código QR aleatorio)
// ============================================================
function validar_mesa(array $d, bool $parcial = false): array
{
    $c = [];
    if (!$parcial || array_key_exists('numero_mesa', $d)) {
        $c['numero_mesa'] = v_entero($d['numero_mesa'] ?? null, 'Número de mesa', 1, 999);
    }
    if (!$parcial || array_key_exists('capacidad', $d)) {
        $c['capacidad'] = v_entero($d['capacidad'] ?? 4, 'Capacidad', 1, 50);
    }
    if (array_key_exists('estado', $d)) {
        if (!in_array($d['estado'], ESTADOS_MESA, true)) {
            throw new ErrorAPI('Estado de mesa inválido.');
        }
        $c['estado'] = $d['estado'];
    }
    return $c;
}

function nuevo_codigo_qr(): string
{
    return bin2hex(random_bytes(5));   // 10 caracteres hexadecimales
}

ruta('POST', '/mesas', function (): void {
    exigir_rol([ROL_ADMIN]);
    $c = validar_mesa(cuerpo_json());
    $c['codigo_qr'] = nuevo_codigo_qr();
    try {
        $id = insertar('mesas', $c);
    } catch (DBDuplicado) {
        throw new ErrorAPI("Ya existe la mesa {$c['numero_mesa']}.", 409);
    }
    responder(['ok' => true, 'id_mesa' => $id, 'msg' => "Mesa {$c['numero_mesa']} creada"], 201);
});

ruta('PUT', '/mesas/{id:n}', function (string $id): void {
    exigir_rol([ROL_ADMIN]);
    if (!existe('SELECT 1 AS ok FROM mesas WHERE id_mesa = ?', [(int) $id])) {
        throw new ErrorAPI('Mesa no encontrada.', 404);
    }
    $c = validar_mesa(cuerpo_json(), true);
    try {
        actualizar('mesas', 'id_mesa', (int) $id, $c);
    } catch (DBDuplicado) {
        throw new ErrorAPI('Ya existe la mesa ' . ($c['numero_mesa'] ?? '') . '.', 409);
    }
    responder(['ok' => true, 'msg' => 'Mesa actualizada']);
});

ruta('DELETE', '/mesas/{id:n}', function (string $id): void {
    exigir_rol([ROL_ADMIN]);
    $id = (int) $id;
    if (!existe('SELECT 1 AS ok FROM mesas WHERE id_mesa = ?', [$id])) {
        throw new ErrorAPI('Mesa no encontrada.', 404);
    }
    if (existe('SELECT 1 AS ok FROM pedidos WHERE id_mesa = ? LIMIT 1', [$id])
        || existe('SELECT 1 AS ok FROM llamados WHERE id_mesa = ? LIMIT 1', [$id])) {
        throw new ErrorAPI('La mesa tiene pedidos registrados y no se puede eliminar. '
            . 'Márquela como «inactiva» para que no reciba pedidos.', 409);
    }
    ejecutar('DELETE FROM mesas WHERE id_mesa = ?', [$id]);
    responder(['ok' => true, 'msg' => 'Mesa eliminada']);
});

/** Código nuevo para el QR de una mesa: el QR impreso anterior deja de funcionar. */
ruta('POST', '/mesas/{id:n}/regenerar-qr', function (string $id): void {
    $u = exigir_rol([ROL_ADMIN]);
    $mesa = consultar_uno('SELECT numero_mesa FROM mesas WHERE id_mesa = ?', [(int) $id]);
    if (!$mesa) {
        throw new ErrorAPI('Mesa no encontrada.', 404);
    }
    $codigo = nuevo_codigo_qr();
    ejecutar('UPDATE mesas SET codigo_qr = ? WHERE id_mesa = ?', [$codigo, (int) $id]);
    error_log("[restaurante] QR de la mesa {$mesa['numero_mesa']} regenerado por '{$u['usuario']}'");
    responder(['ok' => true, 'codigo_qr' => $codigo,
        'msg' => "Nuevo QR para la mesa {$mesa['numero_mesa']}. Imprímalo y reemplace el anterior."]);
});

// ============================================================
// PERSONAL
// ============================================================
ruta('GET', '/roles', function (): void {
    exigir_rol([ROL_ADMIN]);
    responder(consultar("SELECT id_rol, nombre_rol, descripcion FROM roles
        WHERE nombre_rol IN ('Administrador', 'Chef', 'Mesero') ORDER BY id_rol"));
});

ruta('GET', '/usuarios', function (): void {
    exigir_rol([ROL_ADMIN]);
    responder(consultar(
        'SELECT u.id_usuario, u.nombre, u.usuario, u.correo, u.id_rol, r.nombre_rol AS rol,
                u.activo, u.debe_cambiar_clave, u.ultimo_ingreso, u.fecha_creacion
         FROM usuarios u JOIN roles r ON u.id_rol = r.id_rol
         ORDER BY u.activo DESC, r.id_rol, u.nombre'));
});

function rol_valido(int $idRol): string
{
    $f = consultar_uno("SELECT nombre_rol FROM roles WHERE id_rol = ? AND nombre_rol IN ('Administrador', 'Chef', 'Mesero')", [$idRol]);
    if (!$f) {
        throw new ErrorAPI('Rol inválido.');
    }
    return $f['nombre_rol'];
}

function admins_activos(int $excepto = 0): int
{
    return (int) consultar_uno("SELECT COUNT(*) AS n FROM usuarios u JOIN roles r ON u.id_rol = r.id_rol
        WHERE r.nombre_rol = 'Administrador' AND u.activo = 1 AND u.id_usuario <> ?", [$excepto])['n'];
}

ruta('POST', '/usuarios', function (): void {
    $yo = exigir_rol([ROL_ADMIN]);
    $d = cuerpo_json();
    $nombre = v_texto($d['nombre'] ?? null, 'Nombre', 100, true);
    $usuario = mb_strtolower(v_texto($d['usuario'] ?? null, 'Usuario', 50, true));
    if (!preg_match('/^[a-z0-9._-]{3,50}$/', $usuario)) {
        throw new ErrorAPI('Usuario: entre 3 y 50 caracteres; solo letras minúsculas, números, punto, guion y guion bajo.');
    }
    $correo = v_correo($d['correo'] ?? null);
    $idRol = v_entero($d['id_rol'] ?? null, 'Rol', 1);
    rol_valido($idRol);
    $clave = generar_clave_temporal();
    try {
        $id = insertar('usuarios', ['id_rol' => $idRol, 'nombre' => $nombre, 'usuario' => $usuario, 'correo' => $correo,
            'contrasena_hash' => crear_hash($clave), 'debe_cambiar_clave' => 1]);
    } catch (DBDuplicado) {
        throw new ErrorAPI('Ya existe un usuario con ese nombre de usuario o correo.', 409);
    }
    error_log("[restaurante] Usuario '$usuario' creado por '{$yo['usuario']}'");
    responder(['ok' => true, 'id_usuario' => $id, 'usuario' => $usuario, 'clave_temporal' => $clave,
        'msg' => 'Usuario creado. Entréguele la contraseña temporal: deberá cambiarla al ingresar.'], 201);
});

ruta('PUT', '/usuarios/{id:n}', function (string $id): void {
    $yo = exigir_rol([ROL_ADMIN]);
    $id = (int) $id;
    $actual = consultar_uno('SELECT u.id_usuario, u.activo, r.nombre_rol AS rol FROM usuarios u
        JOIN roles r ON u.id_rol = r.id_rol WHERE u.id_usuario = ?', [$id]);
    if (!$actual) {
        throw new ErrorAPI('Usuario no encontrado.', 404);
    }
    $d = cuerpo_json();
    $c = [];
    if (array_key_exists('nombre', $d)) {
        $c['nombre'] = v_texto($d['nombre'], 'Nombre', 100, true);
    }
    if (array_key_exists('correo', $d)) {
        $c['correo'] = v_correo($d['correo']);
    }
    $nuevoRol = $actual['rol'];
    if (array_key_exists('id_rol', $d)) {
        $c['id_rol'] = v_entero($d['id_rol'], 'Rol', 1);
        $nuevoRol = rol_valido($c['id_rol']);
    }
    $nuevoActivo = (int) $actual['activo'];
    if (array_key_exists('activo', $d)) {
        $nuevoActivo = v_bool($d['activo'], 'Activo') ? 1 : 0;
        $c['activo'] = $nuevoActivo;
    }
    if ($id === (int) $yo['id_usuario'] && (!$nuevoActivo || $nuevoRol !== ROL_ADMIN)) {
        throw new ErrorAPI('No puede desactivarse ni quitarse el rol de administrador a sí mismo.', 409);
    }
    $dejaDeSerAdmin = $actual['rol'] === ROL_ADMIN && $actual['activo'] && (!$nuevoActivo || $nuevoRol !== ROL_ADMIN);
    if ($dejaDeSerAdmin && admins_activos($id) === 0) {
        throw new ErrorAPI('Debe quedar al menos un administrador activo.', 409);
    }
    try {
        actualizar('usuarios', 'id_usuario', $id, $c);
    } catch (DBDuplicado) {
        throw new ErrorAPI('Ya existe un usuario con ese correo.', 409);
    }
    // Si se desactivó, su sesión deja de valer en la siguiente petición
    // (usuario_actual revisa "activo" cada vez); el rol nuevo aplica de inmediato.
    responder(['ok' => true, 'msg' => 'Usuario actualizado']);
});

ruta('POST', '/usuarios/{id:n}/restablecer-clave', function (string $id): void {
    $yo = exigir_rol([ROL_ADMIN]);
    $id = (int) $id;
    if ($id === (int) $yo['id_usuario']) {
        throw new ErrorAPI('Para cambiar su propia contraseña use «Cambiar contraseña».', 409);
    }
    if (!existe('SELECT 1 AS ok FROM usuarios WHERE id_usuario = ?', [$id])) {
        throw new ErrorAPI('Usuario no encontrado.', 404);
    }
    $clave = generar_clave_temporal();
    // Al cambiar el hash, las sesiones abiertas de ese usuario caducan.
    ejecutar('UPDATE usuarios SET contrasena_hash = ?, debe_cambiar_clave = 1 WHERE id_usuario = ?', [crear_hash($clave), $id]);
    limite_limpiar('login');
    error_log("[restaurante] Contraseña del usuario $id restablecida por '{$yo['usuario']}'");
    responder(['ok' => true, 'clave_temporal' => $clave, 'msg' => 'Contraseña restablecida. Entréguele la nueva contraseña temporal.']);
});

// ============================================================
// CUPONES
// ============================================================
function validar_cupon(array $d, bool $parcial = false): array
{
    $c = [];
    if (!$parcial || array_key_exists('codigo', $d)) {
        $codigo = mb_strtoupper(v_texto($d['codigo'] ?? null, 'Código', 20, true));
        if (!preg_match('/^[A-Z0-9_-]{3,20}$/', $codigo)) {
            throw new ErrorAPI('Código: de 3 a 20 caracteres; solo letras, números, guion y guion bajo.');
        }
        $c['codigo'] = $codigo;
    }
    if (!$parcial || array_key_exists('descuento', $d)) {
        $c['descuento'] = v_entero($d['descuento'] ?? null, 'Descuento (%)', 1, 100);
    }
    if (array_key_exists('fecha_fin', $d)) {
        $c['fecha_fin'] = v_fecha($d['fecha_fin'], 'Válido hasta');
    }
    if (array_key_exists('activo', $d)) {
        $c['activo'] = v_bool($d['activo'], 'Activo') ? 1 : 0;
    }
    return $c;
}

ruta('GET', '/cupones', function (): void {
    exigir_rol([ROL_ADMIN]);
    $filas = consultar(
        "SELECT c.id_cupon, c.codigo, c.descuento, c.activo, c.fecha_fin,
                (c.fecha_fin IS NOT NULL AND c.fecha_fin < CURDATE()) AS vencido,
                COUNT(p.id_pedido) AS usos
         FROM cupones c LEFT JOIN pedidos p ON p.id_cupon = c.id_cupon AND p.estado <> 'cancelado'
         GROUP BY c.id_cupon, c.codigo, c.descuento, c.activo, c.fecha_fin
         ORDER BY c.activo DESC, c.codigo");
    foreach ($filas as &$f) {
        $f['descuento'] = num($f['descuento']);
    }
    unset($f);
    responder($filas);
});

ruta('POST', '/cupones', function (): void {
    exigir_rol([ROL_ADMIN]);
    $c = validar_cupon(cuerpo_json());
    try {
        $id = insertar('cupones', $c);
    } catch (DBDuplicado) {
        throw new ErrorAPI('Ya existe un cupón con ese código.', 409);
    }
    responder(['ok' => true, 'id_cupon' => $id, 'msg' => "Cupón {$c['codigo']} creado"], 201);
});

ruta('PUT', '/cupones/{id:n}', function (string $id): void {
    exigir_rol([ROL_ADMIN]);
    if (!existe('SELECT 1 AS ok FROM cupones WHERE id_cupon = ?', [(int) $id])) {
        throw new ErrorAPI('Cupón no encontrado.', 404);
    }
    try {
        actualizar('cupones', 'id_cupon', (int) $id, validar_cupon(cuerpo_json(), true));
    } catch (DBDuplicado) {
        throw new ErrorAPI('Ya existe un cupón con ese código.', 409);
    }
    responder(['ok' => true, 'msg' => 'Cupón actualizado']);
});

ruta('DELETE', '/cupones/{id:n}', function (string $id): void {
    exigir_rol([ROL_ADMIN]);
    $id = (int) $id;
    if (!existe('SELECT 1 AS ok FROM cupones WHERE id_cupon = ?', [$id])) {
        throw new ErrorAPI('Cupón no encontrado.', 404);
    }
    if (existe('SELECT 1 AS ok FROM pedidos WHERE id_cupon = ? LIMIT 1', [$id])) {
        ejecutar('UPDATE cupones SET activo = 0 WHERE id_cupon = ?', [$id]);
        responder(['ok' => true, 'msg' => 'El cupón ya se usó en pedidos: se desactivó en lugar de borrarlo.']);
    }
    ejecutar('DELETE FROM cupones WHERE id_cupon = ?', [$id]);
    responder(['ok' => true, 'msg' => 'Cupón eliminado']);
});

// ============================================================
// DIAGNÓSTICO DE SERVER_URL (los QR llevan esa dirección)
// GET /api/qr/info
// ============================================================
ruta('GET', '/qr/info', function (): void {
    exigir_rol([ROL_ADMIN]);
    $url = (string) cfg('SERVER_URL');
    $host = strtolower((string) (parse_url($url, PHP_URL_HOST) ?? ''));
    $esLocal = in_array($host, ['localhost', '127.0.0.1', '::1', '[::1]', '0.0.0.0'], true);
    // Si SERVER_URL usa una IP (XAMPP en la red local) se comprueba que sea
    // de este computador; con un dominio (Hostinger) no se puede saber.
    $ipsServidor = [];
    $ipNoCoincide = false;
    if ($host !== '' && filter_var($host, FILTER_VALIDATE_IP) && !$esLocal) {
        $ipsServidor = array_values(array_unique(array_filter([
            $_SERVER['SERVER_ADDR'] ?? null,
            ...(gethostbynamel((string) gethostname()) ?: []),
        ], fn ($ip) => $ip && !str_starts_with((string) $ip, '127.') && $ip !== '::1')));
        $ipNoCoincide = $ipsServidor !== [] && !in_array($host, $ipsServidor, true);
    }
    responder([
        'server_url' => $url,
        'configurado' => $url !== '' && preg_match('#^https?://#i', $url) === 1,
        'es_local' => $esLocal,
        'ip_no_coincide' => $ipNoCoincide,
        'ips_servidor' => $ipsServidor,
        'https' => str_starts_with(strtolower($url), 'https://'),
    ]);
});
