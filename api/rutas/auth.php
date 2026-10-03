<?php
/**
 * auth.php — Inicio y cierre de sesión del personal
 *
 * POST /api/auth/login          → inicia sesión con usuario/contraseña
 * POST /api/auth/logout         → cierra sesión
 * GET  /api/auth/me             → usuario de la sesión actual
 * POST /api/auth/cambiar-clave  → cambia la contraseña propia
 */

declare(strict_types=1);

ruta('POST', '/auth/login', function (): void {
    $data = cuerpo_json();
    $usuario = mb_strtolower(v_texto($data['usuario'] ?? null, 'Usuario', 150));
    $password = $data['password'] ?? '';
    if ($usuario === '' || !is_string($password) || $password === '') {
        throw new ErrorAPI('Usuario y contraseña son obligatorios.');
    }

    $claveLimite = ip_cliente() . '|' . $usuario;
    if ($minutos = limite_bloqueado('login', $claveLimite)) {
        throw new ErrorAPI("Demasiados intentos fallidos. Intente de nuevo en $minutos minutos.", 429);
    }

    $fila = consultar_uno(
        'SELECT u.id_usuario, u.nombre, u.usuario, u.contrasena_hash, u.debe_cambiar_clave, r.nombre_rol AS rol
         FROM usuarios u JOIN roles r ON u.id_rol = r.id_rol
         WHERE (u.usuario = ? OR u.correo = ?) AND u.activo = 1',
        [$usuario, $usuario]);
    [$correcta, $actualizar] = verificar_clave($fila['contrasena_hash'] ?? null, $password);
    if (!$fila || !$correcta) {
        limite_registrar('login', $claveLimite);
        error_log("[restaurante] Inicio de sesión fallido para '$usuario' desde " . ip_cliente());
        throw new ErrorAPI('Usuario o contraseña incorrectos.', 401);
    }
    limite_limpiar('login', $claveLimite);

    if ($actualizar) {
        // Hash antiguo (SHA-256 sin sal o pbkdf2): se reemplaza por uno seguro
        // ahora que conocemos la contraseña.
        $fila['contrasena_hash'] = crear_hash($password);
        ejecutar('UPDATE usuarios SET contrasena_hash = ? WHERE id_usuario = ?',
            [$fila['contrasena_hash'], $fila['id_usuario']]);
    }
    ejecutar('UPDATE usuarios SET ultimo_ingreso = NOW() WHERE id_usuario = ?', [$fila['id_usuario']]);
    iniciar_sesion($fila, ($data['recordar'] ?? false) === true);
    responder(['ok' => true, 'user' => datos_publicos($fila)]);
});

ruta('POST', '/auth/logout', function (): void {
    cerrar_sesion();
    responder(['ok' => true]);
});

ruta('GET', '/auth/me', function (): void {
    $u = usuario_actual();
    if (!$u) {
        throw new ErrorAPI('No autenticado.', 401, 'sin_sesion');
    }
    responder(['ok' => true, 'user' => datos_publicos($u)]);
});

ruta('POST', '/auth/cambiar-clave', function (): void {
    $u = exigir_rol([], true);
    $data = cuerpo_json();
    $actual = $data['actual'] ?? '';
    $nueva = $data['nueva'] ?? '';
    [$correcta] = verificar_clave($u['contrasena_hash'], is_string($actual) ? $actual : '');
    if (!$correcta) {
        throw new ErrorAPI('La contraseña actual no es correcta.');
    }
    validar_clave_nueva($nueva, $u['usuario']);
    if ($nueva === $actual) {
        throw new ErrorAPI('La nueva contraseña debe ser diferente a la actual.');
    }
    $hash = crear_hash($nueva);
    ejecutar('UPDATE usuarios SET contrasena_hash = ?, debe_cambiar_clave = 0 WHERE id_usuario = ?',
        [$hash, $u['id_usuario']]);
    // Las demás sesiones de este usuario caducan (cambió la huella);
    // esta se renueva para seguir trabajando.
    $u['contrasena_hash'] = $hash;
    $u['debe_cambiar_clave'] = false;
    iniciar_sesion($u, (bool) ($_SESSION['recordar'] ?? false));
    responder(['ok' => true, 'msg' => 'Contraseña actualizada', 'user' => datos_publicos($u)]);
});
