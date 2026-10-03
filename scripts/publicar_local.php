<?php
/**
 * publicar_local.php — Copia el sistema a la carpeta de XAMPP para probarlo
 * igual que en el hosting.
 *
 *   C:\xampp\php\php.exe scripts\publicar_local.php
 *   C:\xampp\php\php.exe scripts\publicar_local.php D:\otra\carpeta
 *
 * Destino por defecto: C:\xampp\htdocs\restaurante  → http://localhost/restaurante
 *
 * - Copia solo los archivos públicos (los mismos del zip para Hostinger).
 * - NUNCA reemplaza api/config.local.php del destino. Si no existe, lo crea
 *   a partir de config.example.php para que usted lo complete.
 */

declare(strict_types=1);

require __DIR__ . '/archivos_publicos.php';

$raiz = dirname(__DIR__);
$destino = rtrim($argv[1] ?? 'C:\\xampp\\htdocs\\restaurante', '\\/');

$archivos = archivos_publicos($raiz);
$copiados = 0;
foreach ($archivos as $rel) {
    $de = "$raiz/$rel";
    $a = "$destino/$rel";
    if (!is_dir(dirname($a)) && !mkdir(dirname($a), 0775, true) && !is_dir(dirname($a))) {
        fwrite(STDERR, "No se pudo crear la carpeta " . dirname($a) . "\n");
        exit(1);
    }
    if (!is_file($a) || md5_file($de) !== md5_file($a)) {
        if (!copy($de, $a)) {
            fwrite(STDERR, "No se pudo copiar $rel\n");
            exit(1);
        }
        $copiados++;
    }
}
echo "Publicado en $destino: " . count($archivos) . " archivos ($copiados actualizados).\n";

$local = "$destino/api/config.local.php";
if (!is_file($local)) {
    copy("$raiz/api/config.example.php", $local);
    echo "Se creó api/config.local.php a partir de la plantilla: revise DB_PORT, DB_PASS y SERVER_URL.\n";
}
