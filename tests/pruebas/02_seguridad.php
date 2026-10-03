<?php
/** Fase 2: inicio de sesión, contraseñas, sesiones, permisos y protecciones. */

declare(strict_types=1);

function login(Cliente $c, string $usuario, string $clave, bool $recordar = false): Respuesta
{
    return $c->post('/api/auth/login', ['usuario' => $usuario, 'password' => $clave, 'recordar' => $recordar]);
}

// ============================================================
grupo('Inicio de sesión');
// ============================================================
prueba('login correcto exige cambiar la clave temporal', function (): void {
    $r = login(cliente(), 'admin', CLAVES['admin']);
    igual(200, $r->status);
    $u = $r->json()['user'];
    igual('Administrador', $u['rol']);
    igual(true, $u['debe_cambiar_clave']);
    verdadero(!isset($u['contrasena_hash']), 'no expone el hash');
});

prueba('el usuario no distingue mayúsculas ni espacios', function (): void {
    igual(200, login(cliente(), '  ADMIN ', CLAVES['admin'])->status);
});

prueba('login incorrecto', function (): void {
    foreach ([['admin', 'incorrecta', 401], ['noexiste', 'loquesea', 401], ['admin', '', 400], ['', 'x', 400]] as [$u, $p, $codigo]) {
        $c = cliente();
        igual($codigo, login($c, $u, $p)->status, "$u/$p");
        igual(401, $c->get('/api/auth/me')->status);
    }
});

prueba('mismo mensaje para usuario inexistente y clave mala', function (): void {
    igual(login(cliente(), 'admin', 'mala1234')->json()['msg'], login(cliente(), 'fantasma', 'mala1234')->json()['msg']);
});

prueba('bloqueo de 15 minutos tras 5 intentos fallidos', function (): void {
    $c = cliente();
    for ($i = 0; $i < 5; $i++) {
        igual(401, login($c, 'chef', 'mala')->status);
    }
    $r = login($c, 'chef', CLAVES['chef']);
    igual(429, $r->status);
    contiene('Demasiados intentos', $r->json()['msg']);
    igual(5, (int) sql_valor("SELECT COUNT(*) FROM limites WHERE tipo = 'login'"), 'intentos guardados en la base');
});

prueba('usuario inactivo no entra', function (): void {
    sql_ejecutar("UPDATE usuarios SET activo = 0 WHERE usuario = 'mesero'");
    igual(401, login(cliente(), 'mesero', CLAVES['mesero'])->status);
});

prueba('logout', function (): void {
    $c = como('admin');
    igual(200, $c->get('/api/auth/me')->status);
    igual(200, $c->post('/api/auth/logout')->status);
    igual(401, $c->get('/api/auth/me')->status);
    igual(401, $c->get('/api/mesas')->status);
});

prueba('migración del hash SHA-256 antiguo (versión original)', function (): void {
    sql_ejecutar("UPDATE usuarios SET contrasena_hash = ? WHERE usuario = 'admin'", [hash('sha256', 'admin123')]);
    igual(401, login(cliente(), 'admin', 'otra')->status);
    igual(200, login(cliente(), 'admin', 'admin123')->status);
    $nuevo = sql_valor("SELECT contrasena_hash FROM usuarios WHERE usuario = 'admin'");
    verdadero(str_starts_with($nuevo, '$2y$'), 'ahora es bcrypt');
    igual(200, login(cliente(), 'admin', 'admin123')->status, 'sigue entrando con la misma clave');
});

prueba('migración del hash pbkdf2 de la versión Flask', function (): void {
    $sal = 'salPrueba123';
    $hash = 'pbkdf2:sha256:1000$' . $sal . '$' . hash_pbkdf2('sha256', 'ClaveFlask1', $sal, 1000, 0, false);
    sql_ejecutar("UPDATE usuarios SET contrasena_hash = ? WHERE usuario = 'chef'", [$hash]);
    igual(401, login(cliente(), 'chef', 'mala')->status);
    igual(200, login(cliente(), 'chef', 'ClaveFlask1')->status);
    verdadero(str_starts_with(sql_valor("SELECT contrasena_hash FROM usuarios WHERE usuario = 'chef'"), '$2y$'), 'ahora es bcrypt');
});

prueba('cookie de sesión HttpOnly y SameSite=Lax', function (): void {
    $r = login(cliente(), 'admin', CLAVES['admin']);
    $cookie = $r->cabecera('set-cookie');
    contiene('restaurante_sesion=', $cookie);
    contiene('HttpOnly', $cookie);
    contiene('SameSite=Lax', $cookie);
    verdadero(!str_contains($cookie, 'secure'), 'sin HTTPS la cookie no es Secure (en Hostinger con SSL sí)');
    igual(1, (int) sql_valor('SELECT COUNT(*) FROM sesiones'), 'la sesión se guarda en la base');
});

prueba('recordar sesión: la cookie dura 7 días', function (): void {
    $cookie = login(cliente(), 'admin', CLAVES['admin'], true)->cabecera('set-cookie');
    verdadero(preg_match('/expires=([^;]+)/i', $cookie, $m) === 1, 'tiene fecha de vencimiento');
    $dias = (strtotime($m[1]) - time()) / 86400;
    verdadero($dias > 6.9 && $dias < 7.1, "vence en 7 días ($dias)");
});

prueba('el comensal no crea sesiones', function (): void {
    $c = cliente();
    $c->get('/api/productos');
    $c->get('/api/mesas/5?c=' . codigo_mesa(5));
    igual(0, (int) sql_valor('SELECT COUNT(*) FROM sesiones'));
});

// ============================================================
grupo('Cambio obligatorio de contraseña');
// ============================================================
prueba('la clave temporal bloquea todo hasta cambiarla', function (): void {
    $c = cliente();
    login($c, 'chef', CLAVES['chef']);
    $r = $c->get('/api/mesas');
    igual(403, $r->status);
    igual('cambiar_clave', $r->json()['codigo']);
    igual(200, $c->get('/api/auth/me')->status, 'puede ver quién es');
    $r = $c->post('/api/auth/cambiar-clave', ['actual' => CLAVES['chef'], 'nueva' => 'Cocina2026segura']);
    igual(200, $r->status, $r->cuerpo);
    igual(false, $r->json()['user']['debe_cambiar_clave']);
    igual(200, $c->get('/api/mesas')->status);
    $c->post('/api/auth/logout');
    igual(401, login(cliente(), 'chef', CLAVES['chef'])->status, 'la clave vieja ya no sirve');
    igual(200, login(cliente(), 'chef', 'Cocina2026segura')->status);
});

prueba('política de contraseñas', function (): void {
    $casos = [
        ['mala', 'Cocina2026segura', 'actual no es correcta'],
        [null, 'corta1', 'al menos 8'],
        [null, 'solamenteletras', 'letras y números'],
        [null, '1234567890', 'letras y números'],
        [null, 'chef12345', 'nombre de usuario'],
        [null, 'Cocina-Temporal-2026', 'temporal'],
    ];
    foreach ($casos as [$actual, $nueva, $mensaje]) {
        $c = cliente();
        login($c, 'chef', CLAVES['chef']);
        $r = $c->post('/api/auth/cambiar-clave', ['actual' => $actual ?? CLAVES['chef'], 'nueva' => $nueva]);
        igual(400, $r->status, $nueva);
        contiene($mensaje, $r->json()['msg'], $nueva);
    }
});

prueba('cambiar clave requiere sesión', function (): void {
    igual(401, cliente()->post('/api/auth/cambiar-clave', ['actual' => 'x', 'nueva' => 'Nueva12345'])->status);
});

prueba('cambiar la clave cierra las otras sesiones', function (): void {
    $otra = como('mesero');
    $esta = cliente();
    login($esta, 'mesero', CLAVES['mesero']);
    igual(200, $esta->post('/api/auth/cambiar-clave', ['actual' => CLAVES['mesero'], 'nueva' => 'Salon2026segura'])->status);
    igual(200, $esta->get('/api/mesas')->status, 'la sesión actual sigue');
    igual(401, $otra->get('/api/mesas')->status, 'la otra quedó cerrada');
});

prueba('desactivar un usuario cierra su sesión', function (): void {
    $c = como('mesero');
    igual(200, $c->get('/api/mesas')->status);
    sql_ejecutar("UPDATE usuarios SET activo = 0 WHERE usuario = 'mesero'");
    igual(401, $c->get('/api/mesas')->status);
});

prueba('sesión vencida', function (): void {
    $c = como('admin');
    $datos = sql_valor('SELECT datos FROM sesiones LIMIT 1');
    sql_ejecutar('UPDATE sesiones SET datos = ?', [preg_replace('/expira\|i:\d+/', 'expira|i:' . (time() - 10), $datos)]);
    igual(401, $c->get('/api/mesas')->status);
});

// ============================================================
grupo('Permisos y protecciones');
// ============================================================
prueba('sin sesión → 401; rol sin permiso → 403', function (): void {
    $r = cliente()->get('/api/mesas');
    igual(401, $r->status);
    igual('sin_sesion', $r->json()['codigo']);
    igual(401, cliente()->put('/api/mesas/1/estado', ['estado' => 'reservada'])->status);
    $r = como('chef')->put('/api/mesas/1/estado', ['estado' => 'reservada']);
    igual(403, $r->status);
    igual('sin_permiso', $r->json()['codigo']);
    igual(200, como('mesero')->put('/api/mesas/1/estado', ['estado' => 'reservada'])->status);
    igual(200, como('admin')->put('/api/mesas/2/estado', ['estado' => 'reservada'])->status);
});

prueba('solo el admin ve los códigos QR de las mesas', function (): void {
    verdadero(array_key_exists('codigo_qr', como('admin')->get('/api/mesas')->json()[0]), 'admin');
    verdadero(!array_key_exists('codigo_qr', como('mesero')->get('/api/mesas')->json()[0]), 'mesero');
});

prueba('protección CSRF por Origin', function (): void {
    $c = como('admin');
    $r = $c->put('/api/mesas/1/estado', ['estado' => 'reservada'], ['Origin' => 'http://sitio-malicioso.com']);
    igual(403, $r->status);
    igual('origen', $r->json()['codigo']);
    igual(403, $c->put('/api/mesas/1/estado', ['estado' => 'reservada'], ['Origin' => 'null'])->status, 'Origin null');
    igual(200, $c->put('/api/mesas/1/estado', ['estado' => 'reservada'], ['Origin' => base_url()])->status, 'mismo sitio');
});

prueba('el cuerpo debe ser JSON (otra defensa contra formularios de otros sitios)', function (): void {
    $c = como('admin');
    $r = $c->pedir('PUT', '/api/mesas/1/estado', null, ['Content-Type' => 'text/plain'], '{"estado":"reservada"}');
    igual(400, $r->status);
    $r = $c->pedir('PUT', '/api/mesas/1/estado', null, ['Content-Type' => 'application/x-www-form-urlencoded'], 'estado=reservada');
    igual(400, $r->status);
});

prueba('cabeceras de seguridad en la API', function (): void {
    $r = cliente()->get('/api/status');
    igual('nosniff', $r->cabecera('x-content-type-options'));
    igual('SAMEORIGIN', $r->cabecera('x-frame-options'));
    igual('no-store', $r->cabecera('cache-control'));
});
