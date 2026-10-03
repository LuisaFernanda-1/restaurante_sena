<?php
/**
 * respaldo.php — Respaldo de la base de datos desde la consola (XAMPP)
 *
 *   C:\xampp\php\php.exe scripts\respaldo.php
 *   C:\xampp\php\php.exe scripts\respaldo.php --dias=60 --dir=D:\Respaldos
 *
 * - Guarda respaldos/restaurante_sena_AAAAMMDD_HHMMSS.sql.gz
 * - Borra los respaldos con más de 30 días (configurable con --dias).
 * - Usa la conexión de api/config.local.php. No necesita mysqldump.
 * - Termina con código 0 si salió bien y 1 si falló (útil para el
 *   Programador de tareas de Windows).
 *
 * En Hostinger use el botón "Descargar respaldo" del panel (o los
 * respaldos automáticos de hPanel).
 */

declare(strict_types=1);

$raiz = dirname(__DIR__);
require "$raiz/api/config.php";
require "$raiz/api/lib/respuesta.php";
require "$raiz/api/lib/db.php";
require "$raiz/api/lib/respaldo.php";

date_default_timezone_set(cfg('ZONA_HORARIA'));
$opciones = getopt('', ['dias::', 'dir::']);
$dias = (int) ($opciones['dias'] ?? 30);
$carpeta = rtrim((string) ($opciones['dir'] ?? "$raiz/respaldos"), '\\/');

function registro(string $mensaje): void
{
    global $raiz;
    $linea = date('Y-m-d H:i:s') . " $mensaje\n";
    echo $linea;
    if (!is_dir("$raiz/logs")) {
        @mkdir("$raiz/logs", 0775, true);
    }
    @file_put_contents("$raiz/logs/respaldo.log", $linea, FILE_APPEND);
}

try {
    if (!is_dir($carpeta) && !mkdir($carpeta, 0775, true) && !is_dir($carpeta)) {
        throw new RuntimeException("No se pudo crear la carpeta $carpeta");
    }
    $destino = "$carpeta/" . nombre_archivo_respaldo();
    registro('Respaldando la base ' . cfg('DB_NAME') . " en $destino");
    $sql = generar_respaldo_sql();
    if (!str_contains($sql, '-- Respaldo completo')) {
        throw new RuntimeException('El respaldo quedó incompleto.');
    }
    $temporal = "$destino.parcial";
    if (file_put_contents($temporal, gzencode($sql, 6)) === false || !rename($temporal, $destino)) {
        @unlink($temporal);
        throw new RuntimeException("No se pudo escribir $destino");
    }
    registro(sprintf('Respaldo listo: %s (%.1f KB)', basename($destino), filesize($destino) / 1024));

    // Retención: se borran los respaldos con más de N días
    $limite = time() - $dias * 86400;
    $borrados = [];
    foreach (glob("$carpeta/restaurante_sena_*.sql.gz") as $archivo) {
        if (filemtime($archivo) < $limite && unlink($archivo)) {
            $borrados[] = basename($archivo);
        }
    }
    if ($borrados) {
        registro("Respaldos con más de $dias días eliminados: " . implode(', ', $borrados));
    }
    exit(0);
} catch (Throwable $e) {
    registro('ERROR: ' . $e->getMessage());
    exit(1);
}
