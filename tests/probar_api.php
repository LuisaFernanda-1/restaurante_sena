<?php
/**
 * probar_api.php — Pruebas automáticas de Restaurante SENA (backend PHP)
 *
 * Uso (desde la carpeta del proyecto):
 *   C:\xampp\php\php.exe tests\probar_api.php                 pruebas completas
 *   C:\xampp\php\php.exe tests\probar_api.php --solo=pedido   solo las que contienen "pedido"
 *   C:\xampp\php\php.exe tests\probar_api.php --apache        además prueba el Apache de XAMPP
 *                                     (--apache=http://localhost/restaurante por defecto)
 *
 * Las pruebas completas usan una base de datos APARTE (restaurante_sena_test)
 * que se crea de nuevo antes de cada prueba, y el servidor de desarrollo de
 * PHP. Nunca tocan la base real. Necesitan MySQL encendido; la conexión se
 * toma de api/config.local.php (solo se cambia el nombre de la base).
 */

declare(strict_types=1);

require __DIR__ . '/lib_pruebas.php';
require dirname(__DIR__) . '/api/config.php';
require dirname(__DIR__) . '/api/lib/respaldo.php';   // dividir_sql()

date_default_timezone_set(cfg('ZONA_HORARIA'));

const RAIZ = __DIR__ . '/..';
const BD_PRUEBAS = 'restaurante_sena_test';
const PUERTOS = ['solo_qr' => 8099, 'sin_qr' => 8098];

// Contraseñas SOLO para las pruebas (las temporales reales están en el README)
const CLAVES = ['admin' => 'Prueba-Admin-111', 'chef' => 'Prueba-Cocina-222', 'mesero' => 'Prueba-Salon-333'];

$opciones = getopt('', ['solo:', 'apache::', 'sin-completas']);
$filtro = $opciones['solo'] ?? null;
$urlApache = array_key_exists('apache', $opciones) ? ($opciones['apache'] ?: 'http://localhost/restaurante') : null;

// ------------------------------------------------------------
// Base de datos de pruebas
// ------------------------------------------------------------
function pdo_servidor(): PDO
{
    static $pdo = null;
    return $pdo ??= new PDO(sprintf('mysql:host=%s;port=%d;charset=utf8mb4', cfg('DB_HOST'), cfg('DB_PORT')),
        (string) cfg('DB_USER'), (string) cfg('DB_PASS'),
        [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION, PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
         PDO::ATTR_EMULATE_PREPARES => false]);
}

/** Ejecuta un script .sql en la base indicada (cambia el nombre restaurante_sena). */
function cargar_script(string $archivo, string $bd, bool $sinCrearBase = false): void
{
    $pdo = pdo_servidor();
    $pdo->exec('SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci');
    if ($sinCrearBase) {
        $pdo->exec("DROP DATABASE IF EXISTS `$bd`");
        $pdo->exec("CREATE DATABASE `$bd` CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci");
        $pdo->exec("USE `$bd`");
    }
    foreach (dividir_sql(file_get_contents($archivo)) as $sentencia) {
        if (preg_match('/^(DROP DATABASE|CREATE DATABASE|USE)\b/i', $sentencia)) {
            $sentencia = preg_replace('/\brestaurante_sena\b/', $bd, $sentencia);
        }
        $st = $pdo->query($sentencia);
        if ($st->columnCount() > 0) {
            $st->fetchAll();
        }
        $st->closeCursor();
    }
}

function recrear_bd(): void
{
    cargar_script(RAIZ . '/sql/instalacion_local.sql', BD_PRUEBAS);
    $pdo = pdo_servidor();
    $pdo->exec('USE `' . BD_PRUEBAS . '`');
    $st = $pdo->prepare('UPDATE usuarios SET contrasena_hash = ? WHERE usuario = ?');
    foreach (CLAVES as $usuario => $clave) {
        $st->execute([password_hash($clave, PASSWORD_BCRYPT, ['cost' => 4]), $usuario]);   // rápido, solo pruebas
    }
}

/** Consultas directas a la base de pruebas. */
function sql_todos(string $sql, array $p = []): array
{
    $pdo = pdo_servidor();
    $pdo->exec('USE `' . BD_PRUEBAS . '`');
    $st = $pdo->prepare($sql);
    $st->execute($p);
    return $st->fetchAll();
}

function sql_uno(string $sql, array $p = []): ?array
{
    return sql_todos($sql, $p)[0] ?? null;
}

function sql_valor(string $sql, array $p = []): mixed
{
    $fila = sql_uno($sql, $p);
    return $fila === null ? null : reset($fila);
}

function sql_ejecutar(string $sql, array $p = []): void
{
    $pdo = pdo_servidor();
    $pdo->exec('USE `' . BD_PRUEBAS . '`');
    $pdo->prepare($sql)->execute($p);
}

// ------------------------------------------------------------
// Ayudas para las pruebas
// ------------------------------------------------------------
$GLOBALS['SERVIDOR'] = 'solo_qr';

function base_url(?string $servidor = null): string
{
    return 'http://127.0.0.1:' . PUERTOS[$servidor ?? $GLOBALS['SERVIDOR']];
}

function cliente(?string $servidor = null): Cliente
{
    return new Cliente(base_url($servidor));
}

function codigo_mesa(int $numero): ?string
{
    return sql_valor('SELECT codigo_qr FROM mesas WHERE numero_mesa = ?', [$numero]);
}

/** Cliente con sesión iniciada como admin, chef o mesero (clave ya cambiada). */
function como(string $usuario): Cliente
{
    sql_ejecutar('UPDATE usuarios SET debe_cambiar_clave = 0 WHERE usuario = ?', [$usuario]);
    $c = cliente();
    $r = $c->post('/api/auth/login', ['usuario' => $usuario, 'password' => CLAVES[$usuario]]);
    igual(200, $r->status, "login de $usuario");
    return $c;
}

/** Crea un pedido con el código QR correcto y devuelve el JSON. */
function crear_pedido(int $mesa = 5, ?array $items = null, array $extra = []): array
{
    $r = cliente()->post('/api/pedidos', array_merge(
        ['mesa' => $mesa, 'codigo' => codigo_mesa($mesa), 'items' => $items ?? [['id' => 1, 'cantidad' => 1]]], $extra));
    igual(201, $r->status, 'crear pedido (' . $r->cuerpo . ')');
    return $r->json();
}

function entregar(Cliente $admin, int $id): void
{
    foreach (['en_preparacion', 'listo', 'entregado'] as $e) {
        igual(200, $admin->put("/api/pedidos/$id/estado", ['estado' => $e])->status, "pasar a $e");
    }
}

// ------------------------------------------------------------
// Servidores de desarrollo de PHP (uno con "solo QR" y otro con "sin QR")
// ------------------------------------------------------------
function iniciar_servidores(): array
{
    $procesos = [];
    foreach (PUERTOS as $modo => $puerto) {
        $env = array_merge(getenv(), [
            'RS_DB_NAME' => BD_PRUEBAS,
            'RS_PERMITIR_SIN_QR' => $modo === 'sin_qr' ? '1' : '0',
            'RS_SERVER_URL' => "http://127.0.0.1:$puerto",
            'RS_IMPUESTO_PCT' => '8',
            'RS_PROPINA_SUGERIDA_PCT' => '10',
        ]);
        $nulo = PHP_OS_FAMILY === 'Windows' ? 'NUL' : '/dev/null';
        $proc = proc_open([PHP_BINARY, '-S', "127.0.0.1:$puerto", '-t', realpath(RAIZ), realpath(__DIR__ . '/router.php')],
            [0 => ['pipe', 'r'], 1 => ['file', $nulo, 'w'], 2 => ['file', $nulo, 'w']], $tuberias, realpath(RAIZ), $env);
        if (!is_resource($proc)) {
            throw new RuntimeException("No se pudo iniciar el servidor de pruebas en el puerto $puerto");
        }
        $procesos[] = $proc;
        for ($i = 0; $i < 50; $i++) {
            $s = @fsockopen('127.0.0.1', $puerto, $errno, $errstr, 0.2);
            if ($s) {
                fclose($s);
                continue 2;
            }
            usleep(100000);
        }
        throw new RuntimeException("El servidor de pruebas no respondió en el puerto $puerto");
    }
    return $procesos;
}

function detener_servidores(array $procesos): void
{
    foreach ($procesos as $p) {
        $estado = proc_get_status($p);
        if (PHP_OS_FAMILY === 'Windows') {
            exec('taskkill /F /T /PID ' . $estado['pid'] . ' 2>NUL');
        } else {
            proc_terminate($p);
        }
        proc_close($p);
    }
}

// ------------------------------------------------------------
// Ejecución
// ------------------------------------------------------------
foreach (glob(__DIR__ . '/pruebas/*.php') as $archivo) {
    require $archivo;
}

$aEjecutar = array_values(array_filter($GLOBALS['PRUEBAS'], function (array $p) use ($filtro, $urlApache): bool {
    $esApache = ($p['opciones']['apache'] ?? false) === true;
    if ($esApache && $urlApache === null) {
        return false;
    }
    if (!$esApache && isset($GLOBALS['opciones']['sin-completas'])) {
        return false;
    }
    return $filtro === null || stripos($p['grupo'] . ' ' . $p['nombre'], $filtro) !== false;
}));

$hayCompletas = (bool) array_filter($aEjecutar, fn ($p) => !($p['opciones']['apache'] ?? false));
$procesos = [];
if ($hayCompletas) {
    if (!str_ends_with(BD_PRUEBAS, '_test')) {
        exit("Por seguridad, la base de pruebas debe terminar en _test\n");
    }
    echo 'Base de pruebas: ' . BD_PRUEBAS . ' @ ' . cfg('DB_HOST') . ':' . cfg('DB_PORT') . "\n";
    $procesos = iniciar_servidores();
}
$GLOBALS['URL_APACHE'] = $urlApache;

$ok = 0;
$fallos = [];
$grupoAnterior = null;
$inicio = microtime(true);
try {
    foreach ($aEjecutar as $p) {
        if ($p['grupo'] !== $grupoAnterior) {
            echo "\n== {$p['grupo']}\n";
            $grupoAnterior = $p['grupo'];
        }
        $GLOBALS['SERVIDOR'] = $p['opciones']['servidor'] ?? 'solo_qr';
        try {
            if (!($p['opciones']['apache'] ?? false) && !($p['opciones']['sin_bd'] ?? false)) {
                recrear_bd();
            }
            ($p['fn'])();
            $ok++;
            echo "  OK     {$p['nombre']}\n";
        } catch (Throwable $e) {
            $fallos[] = "{$p['grupo']} › {$p['nombre']}: " . $e->getMessage();
            echo "  FALLA  {$p['nombre']}\n         → " . $e->getMessage() . "\n";
        }
    }
} finally {
    detener_servidores($procesos);
}

$segundos = round(microtime(true) - $inicio, 1);
echo "\n" . str_repeat('-', 60) . "\n";
echo count($fallos) ? count($fallos) . " fallaron, $ok pasaron ($segundos s)\n" : "$ok pasaron ($segundos s)\n";
exit(count($fallos) ? 1 : 0);
