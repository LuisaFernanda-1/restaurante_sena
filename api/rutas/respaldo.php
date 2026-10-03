<?php
/**
 * respaldo.php — Botón "Descargar respaldo" del panel
 *
 * GET /api/respaldo → descarga restaurante_sena_AAAAMMDD_HHMMSS.sql.gz (administrador)
 */

declare(strict_types=1);

require_once __DIR__ . '/../lib/respaldo.php';

ruta('GET', '/respaldo', function (): void {
    $u = exigir_rol([ROL_ADMIN]);
    $gz = gzencode(generar_respaldo_sql(), 6);
    error_log("[restaurante] Respaldo descargado por '{$u['usuario']}'");
    if (session_status() === PHP_SESSION_ACTIVE) {
        session_write_close();
    }
    header('Content-Type: application/gzip');
    header('Content-Disposition: attachment; filename="' . nombre_archivo_respaldo() . '"');
    header('Content-Length: ' . strlen($gz));
    header('Cache-Control: no-store');
    header('X-Content-Type-Options: nosniff');
    echo $gz;
    exit;
});
