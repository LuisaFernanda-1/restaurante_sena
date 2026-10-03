<?php
/**
 * restaurar.php — Restaura un respaldo desde la consola (XAMPP)
 *
 *   C:\xampp\php\php.exe scripts\restaurar.php
 *       → restaura el respaldo MÁS RECIENTE de la carpeta respaldos\
 *   C:\xampp\php\php.exe scripts\restaurar.php respaldos\restaurante_sena_20261003_233000.sql.gz
 *   C:\xampp\php\php.exe scripts\restaurar.php --bd=restaurante_revision ARCHIVO
 *       → restaura en otra base (para revisar un respaldo sin tocar la real)
 *
 * ¡ATENCIÓN! Reemplaza las tablas de la base de destino. Antes de restaurar
 * sobre la base en uso hace un respaldo de seguridad de su estado actual.
 *
 * En Hostinger restaure desde phpMyAdmin: seleccione la base → Importar.
 */

declare(strict_types=1);

$raiz = dirname(__DIR__);
require "$raiz/api/config.php";
require "$raiz/api/lib/respuesta.php";
require "$raiz/api/lib/db.php";
require "$raiz/api/lib/respaldo.php";

date_default_timezone_set(cfg('ZONA_HORARIA'));
$opciones = getopt('', ['bd::', 'si', 'sin-respaldo'], $resto);
$argumentos = array_slice($argv, $resto);
$bd = (string) ($opciones['bd'] ?? cfg('DB_NAME'));
$archivo = $argumentos[0] ?? null;

try {
    if (!preg_match('/^[A-Za-z0-9_]{1,64}$/', $bd)) {
        throw new RuntimeException('Nombre de base de datos inválido.');
    }
    if ($archivo === null) {
        $lista = glob("$raiz/respaldos/restaurante_sena_*.sql.gz");
        sort($lista);
        $archivo = end($lista) ?: throw new RuntimeException("No hay respaldos en $raiz/respaldos");
    }
    if (!is_file($archivo)) {
        throw new RuntimeException("No existe el archivo $archivo");
    }
    echo "Respaldo:         $archivo\n";
    echo 'Base de destino:  ' . $bd . ' @ ' . cfg('DB_HOST') . ':' . cfg('DB_PORT') . "\n";
    if (!isset($opciones['si'])) {
        echo "\n¡ATENCIÓN! Se reemplazarán los datos actuales de esa base.\n";
        echo "Escriba el nombre de la base ($bd) para confirmar: ";
        if (trim((string) fgets(STDIN)) !== $bd) {
            echo "Cancelado.\n";
            exit(1);
        }
    }
    $sql = gzdecode((string) file_get_contents($archivo));
    if ($sql === false || !str_contains($sql, '-- Respaldo completo')) {
        throw new RuntimeException('El archivo no es un respaldo completo de Restaurante SENA.');
    }
    if (!isset($opciones['sin-respaldo']) && $bd === cfg('DB_NAME')) {
        @mkdir("$raiz/respaldos", 0775, true);
        $seguridad = "$raiz/respaldos/" . nombre_archivo_respaldo();
        file_put_contents($seguridad, gzencode(generar_respaldo_sql(), 6));
        echo "Respaldo de seguridad del estado actual: $seguridad\n";
    }
    $pdo = new PDO(sprintf('mysql:host=%s;port=%d;charset=utf8mb4', cfg('DB_HOST'), cfg('DB_PORT')),
        (string) cfg('DB_USER'), (string) cfg('DB_PASS'),
        [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION, PDO::ATTR_EMULATE_PREPARES => false]);
    $pdo->exec("CREATE DATABASE IF NOT EXISTS `$bd` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci");
    $pdo->exec("USE `$bd`");
    $n = ejecutar_script_sql($pdo, $sql);
    echo "Listo: $n sentencias ejecutadas en la base '$bd'.\n";
    exit(0);
} catch (Throwable $e) {
    fwrite(STDERR, 'ERROR: ' . $e->getMessage() . "\n");
    exit(1);
}
