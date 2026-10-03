<?php
/**
 * seguridad.php — Sesiones, contraseñas, permisos por rol y límites
 *
 * - Contraseñas con password_hash / password_verify. Los hashes antiguos
 *   (SHA-256 sin sal de la versión original y pbkdf2 de la versión Flask)
 *   se aceptan una vez y se reemplazan por uno seguro al iniciar sesión.
 * - Sesiones guardadas en la tabla `sesiones`, con cookie HttpOnly,
 *   SameSite=Lax y Secure cuando hay HTTPS.
 * - exigir_rol(): sin sesión → 401; rol incorrecto → 403. En cada petición
 *   se verifica contra la base que el usuario siga activo y que su
 *   contraseña no haya cambiado (si cambió, las sesiones viejas caducan).
 */

declare(strict_types=1);

const ROL_ADMIN = 'Administrador';
const ROL_CHEF = 'Chef';
const ROL_MESERO = 'Mesero';
const ROLES_PERSONAL = [ROL_ADMIN, ROL_CHEF, ROL_MESERO];

const DURACION_SESION = 12 * 3600;                 // una jornada de trabajo
const DURACION_SESION_RECORDADA = 7 * 24 * 3600;   // "Recordar sesión"
const NOMBRE_COOKIE = 'restaurante_sesion';

// ============================================================
// Contraseñas
// ============================================================
function crear_hash(string $password): string
{
    return password_hash($password, PASSWORD_DEFAULT);
}

/** @return array{0: bool, 1: bool} [correcta, hay que actualizar el hash] */
function verificar_clave(?string $hash, string $password): array
{
    if ($hash === null || $hash === '') {
        // Hash de relleno: el usuario inexistente tarda lo mismo y no revela qué usuarios existen
        password_verify($password, '$2y$10$0QpUQlW4bNFFjy6V4PjBZugKfab89Eexz.S/IS3i35Xq5/7p/3ZiO');
        return [false, false];
    }
    // SHA-256 sin sal (versión original del proyecto)
    if (preg_match('/^[0-9a-f]{64}$/', $hash)) {
        return [hash_equals($hash, hash('sha256', $password)), true];
    }
    // pbkdf2 de werkzeug (versión Flask): "pbkdf2:sha256:600000$sal$hexadecimal"
    if (preg_match('/^pbkdf2:(sha256|sha512):(\d+)\$([^$]+)\$([0-9a-f]+)$/', $hash, $m)) {
        $calculado = hash_pbkdf2($m[1], $password, $m[3], (int) $m[2], 0, false);
        return [hash_equals($m[4], $calculado), true];
    }
    // Los hashes scrypt de werkzeug no se pueden verificar en PHP: el
    // administrador debe restablecer esa contraseña.
    if (str_starts_with($hash, 'scrypt:')) {
        return [false, false];
    }
    $ok = password_verify($password, $hash);
    return [$ok, $ok && password_needs_rehash($hash, PASSWORD_DEFAULT)];
}

function validar_clave_nueva(mixed $nueva, string $usuario = ''): void
{
    if (!is_string($nueva) || mb_strlen($nueva) < 8) {
        throw new ErrorAPI('La contraseña debe tener al menos 8 caracteres.');
    }
    if (mb_strlen($nueva) > 128) {
        throw new ErrorAPI('La contraseña es demasiado larga (máximo 128 caracteres).');
    }
    if (!preg_match('/[A-Za-zÁÉÍÓÚáéíóúÑñ]/u', $nueva) || !preg_match('/\d/', $nueva)) {
        throw new ErrorAPI('La contraseña debe tener letras y números.');
    }
    if ($usuario !== '' && str_contains(mb_strtolower($nueva), mb_strtolower($usuario))) {
        throw new ErrorAPI('La contraseña no puede contener el nombre de usuario.');
    }
    if (str_contains(mb_strtolower($nueva), 'temporal')) {
        throw new ErrorAPI('Elija una contraseña distinta a la temporal.');
    }
}

/** Contraseña temporal aleatoria, fácil de dictar: "Temporal-Xk7p-9mQa" (sin 0/O ni 1/l/I). */
function generar_clave_temporal(): string
{
    $alfabeto = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789';
    $bloque = function () use ($alfabeto): string {
        $s = '';
        for ($i = 0; $i < 4; $i++) {
            $s .= $alfabeto[random_int(0, strlen($alfabeto) - 1)];
        }
        return $s;
    };
    return 'Temporal-' . $bloque() . '-' . $bloque();
}

/** Fragmento del hash guardado en la sesión: si la contraseña cambia, no coincide. */
function huella(string $hash): string
{
    return substr(hash('sha256', $hash), 0, 16);
}

// ============================================================
// Sesiones guardadas en la base de datos
// ============================================================
final class SesionesEnBD implements SessionHandlerInterface
{
    public function open(string $ruta, string $nombre): bool { return true; }
    public function close(): bool { return true; }

    public function read(string $id): string|false
    {
        $fila = consultar_uno('SELECT datos FROM sesiones WHERE id_sesion = ?', [$id]);
        return $fila['datos'] ?? '';
    }

    public function write(string $id, string $datos): bool
    {
        ejecutar('INSERT INTO sesiones (id_sesion, datos, actualizado) VALUES (?, ?, NOW())
                  ON DUPLICATE KEY UPDATE datos = VALUES(datos), actualizado = NOW()', [$id, $datos]);
        return true;
    }

    public function destroy(string $id): bool
    {
        ejecutar('DELETE FROM sesiones WHERE id_sesion = ?', [$id]);
        return true;
    }

    public function gc(int $vida): int|false
    {
        [$borradas] = ejecutar('DELETE FROM sesiones WHERE actualizado < NOW() - INTERVAL ? SECOND',
            [DURACION_SESION_RECORDADA]);
        return $borradas;
    }
}

function es_https(): bool
{
    return (!empty($_SERVER['HTTPS']) && strtolower((string) $_SERVER['HTTPS']) !== 'off')
        || (int) ($_SERVER['SERVER_PORT'] ?? 0) === 443
        || strtolower((string) ($_SERVER['HTTP_X_FORWARDED_PROTO'] ?? '')) === 'https';
}

/** Carpeta del sistema en el servidor ("/restaurante/" en XAMPP, "/" en un subdominio). */
function ruta_base_cookie(): string
{
    $api = str_replace('\\', '/', dirname($_SERVER['SCRIPT_NAME'] ?? '/api/index.php'));
    $base = rtrim(dirname($api), '/');
    return $base . '/';
}

function configurar_sesion(): void
{
    static $hecho = false;
    if ($hecho) {
        return;
    }
    $hecho = true;
    ini_set('session.use_strict_mode', '1');
    ini_set('session.use_only_cookies', '1');
    ini_set('session.gc_maxlifetime', (string) DURACION_SESION_RECORDADA);
    ini_set('session.gc_probability', '1');
    ini_set('session.gc_divisor', '100');
    session_set_save_handler(new SesionesEnBD(), true);
    session_name(NOMBRE_COOKIE);
    session_set_cookie_params([
        'lifetime' => 0,
        'path' => ruta_base_cookie(),
        'secure' => es_https(),
        'httponly' => true,
        'samesite' => 'Lax',
    ]);
}

/** Abre la sesión solo si el navegador ya trae la cookie (los comensales no crean sesiones). */
function abrir_sesion_existente(): bool
{
    if (session_status() === PHP_SESSION_ACTIVE) {
        return true;
    }
    if (empty($_COOKIE[NOMBRE_COOKIE])) {
        return false;
    }
    configurar_sesion();
    return session_start();
}

function iniciar_sesion(array $usuario, bool $recordar = false): void
{
    configurar_sesion();
    if (session_status() !== PHP_SESSION_ACTIVE) {
        session_start();
    }
    session_regenerate_id(true);   // evita la fijación de sesión
    $_SESSION = [
        'user_id' => (int) $usuario['id_usuario'],
        'huella' => huella($usuario['contrasena_hash']),
        'expira' => time() + ($recordar ? DURACION_SESION_RECORDADA : DURACION_SESION),
        'recordar' => $recordar,
    ];
    if ($recordar) {
        // La cookie dura 7 días aunque se cierre el navegador
        setcookie(session_name(), session_id(), [
            'expires' => time() + DURACION_SESION_RECORDADA, 'path' => ruta_base_cookie(),
            'secure' => es_https(), 'httponly' => true, 'samesite' => 'Lax',
        ]);
    }
}

function cerrar_sesion(): void
{
    if (abrir_sesion_existente()) {
        $_SESSION = [];
        session_destroy();
    }
    setcookie(NOMBRE_COOKIE, '', [
        'expires' => time() - 3600, 'path' => ruta_base_cookie(),
        'secure' => es_https(), 'httponly' => true, 'samesite' => 'Lax',
    ]);
}

/** Usuario de la sesión, validado contra la base de datos (o null). */
function usuario_actual(): ?array
{
    static $cache = false;
    if ($cache !== false) {
        return $cache;
    }
    $cache = null;
    if (!abrir_sesion_existente() || empty($_SESSION['user_id'])) {
        return null;
    }
    if (($_SESSION['expira'] ?? 0) < time()) {
        $_SESSION = [];
        return null;
    }
    $fila = consultar_uno(
        'SELECT u.id_usuario, u.nombre, u.usuario, u.contrasena_hash, u.debe_cambiar_clave, u.activo,
                r.nombre_rol AS rol
         FROM usuarios u JOIN roles r ON u.id_rol = r.id_rol WHERE u.id_usuario = ?',
        [(int) $_SESSION['user_id']]);
    if (!$fila || !$fila['activo'] || !hash_equals((string) ($_SESSION['huella'] ?? ''), huella($fila['contrasena_hash']))) {
        $_SESSION = [];
        return null;
    }
    $fila['debe_cambiar_clave'] = (bool) $fila['debe_cambiar_clave'];
    $cache = $fila;
    return $fila;
}

function datos_publicos(array $u): array
{
    return [
        'id' => (int) $u['id_usuario'],
        'nombre' => $u['nombre'],
        'usuario' => $u['usuario'],
        'rol' => $u['rol'],
        'debe_cambiar_clave' => (bool) $u['debe_cambiar_clave'],
    ];
}

/**
 * exigir_rol()                           → cualquier usuario del personal
 * exigir_rol([ROL_ADMIN])                → solo administrador
 * exigir_rol([ROL_ADMIN, ROL_MESERO])    → administrador o mesero
 */
function exigir_rol(array $roles = [], bool $permitirCambioPendiente = false): array
{
    $u = usuario_actual();
    if (!$u) {
        throw new ErrorAPI('Debe iniciar sesión.', 401, 'sin_sesion');
    }
    if ($u['debe_cambiar_clave'] && !$permitirCambioPendiente) {
        throw new ErrorAPI('Debe cambiar su contraseña temporal antes de continuar.', 403, 'cambiar_clave');
    }
    if ($roles && !in_array($u['rol'], $roles, true)) {
        throw new ErrorAPI('No tiene permiso para esta acción.', 403, 'sin_permiso');
    }
    return $u;
}

// ============================================================
// Límites de intentos (guardados en la tabla `limites`)
// ============================================================
const LIMITES = [
    // tipo => [máximo de intentos, ventana en segundos]
    'login' => [5, 15 * 60],        // 5 fallos → 15 minutos de bloqueo
    'pedido' => [20, 10 * 60],      // 20 pedidos por dispositivo cada 10 minutos
    'llamado' => [10, 10 * 60],     // 10 llamados por dispositivo cada 10 minutos
];

/** Minutos que faltan si está bloqueado; 0 si no. */
function limite_bloqueado(string $tipo, string $clave): int
{
    [$maximo, $ventana] = LIMITES[$tipo];
    $fila = consultar_uno(
        'SELECT COUNT(*) AS n, MIN(creado) AS primero FROM limites
         WHERE tipo = ? AND clave = ? AND creado > NOW() - INTERVAL ? SECOND',
        [$tipo, $clave, $ventana]);
    if ((int) $fila['n'] < $maximo) {
        return 0;
    }
    $transcurrido = time() - strtotime((string) $fila['primero']);
    return intdiv(max(0, $ventana - $transcurrido), 60) + 1;
}

function limite_registrar(string $tipo, string $clave): void
{
    ejecutar('INSERT INTO limites (tipo, clave) VALUES (?, ?)', [$tipo, $clave]);
    if (random_int(1, 50) === 1) {   // limpieza ocasional de intentos vencidos
        ejecutar('DELETE FROM limites WHERE creado < NOW() - INTERVAL 1 DAY');
    }
}

function limite_limpiar(string $tipo, ?string $clave = null): void
{
    if ($clave === null) {
        ejecutar('DELETE FROM limites WHERE tipo = ?', [$tipo]);
    } else {
        ejecutar('DELETE FROM limites WHERE tipo = ? AND clave = ?', [$tipo, $clave]);
    }
}

function ip_cliente(): string
{
    return (string) ($_SERVER['REMOTE_ADDR'] ?? 'desconocida');
}

// ============================================================
// Protección CSRF: una página de OTRO sitio no puede enviar peticiones
// que modifiquen datos con la sesión del personal. Los navegadores
// siempre envían la cabecera Origin en POST/PUT/DELETE entre sitios.
// ============================================================
function verificar_origen(): void
{
    $metodo = $_SERVER['REQUEST_METHOD'] ?? 'GET';
    if (!in_array($metodo, ['POST', 'PUT', 'PATCH', 'DELETE'], true)) {
        return;
    }
    $origen = $_SERVER['HTTP_ORIGIN'] ?? '';
    if ($origen === '') {
        return;   // misma página (algunos navegadores no envían Origin)
    }
    $partes = parse_url($origen);
    $hostOrigen = ($partes['host'] ?? '') . (isset($partes['port']) ? ':' . $partes['port'] : '');
    $host = (string) ($_SERVER['HTTP_HOST'] ?? '');
    if (strcasecmp($hostOrigen, $host) !== 0) {
        throw new ErrorAPI('Origen de la petición no permitido.', 403, 'origen');
    }
}
