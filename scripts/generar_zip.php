<?php
/**
 * generar_zip.php — Arma restaurante_hostinger.zip con SOLO los archivos que
 * se suben al hosting (los mismos que publicar_local.php copia a XAMPP).
 *
 *   C:\xampp\php\php.exe scripts\generar_zip.php
 *   C:\xampp\php\php.exe scripts\generar_zip.php D:\salida\restaurante.zip
 *
 * El zip NO incluye api/config.local.php (contraseñas), sql/, tests/,
 * scripts/ ni el README. Los archivos quedan en la raíz del zip: al
 * extraerlo dentro de la carpeta del subdominio, index.html queda en ella.
 */

declare(strict_types=1);

require __DIR__ . '/archivos_publicos.php';

if (!class_exists('ZipArchive')) {
    fwrite(STDERR, "Falta la extensión zip de PHP (en XAMPP viene activada: revise php.ini, extension=zip).\n");
    exit(1);
}

$raiz = dirname(__DIR__);
$salida = $argv[1] ?? "$raiz/restaurante_hostinger.zip";

$archivos = archivos_publicos($raiz);
foreach ($archivos as $rel) {
    if (es_privado($rel) || str_starts_with($rel, 'sql/')) {
        fwrite(STDERR, "Archivo privado en la lista: $rel\n");
        exit(1);
    }
}

if (is_file($salida) && !unlink($salida)) {
    fwrite(STDERR, "No se pudo reemplazar $salida (¿está abierto?)\n");
    exit(1);
}
$zip = new ZipArchive();
if ($zip->open($salida, ZipArchive::CREATE) !== true) {
    fwrite(STDERR, "No se pudo crear $salida\n");
    exit(1);
}
$bytes = 0;
foreach ($archivos as $rel) {
    $zip->addFile("$raiz/$rel", $rel);
    $bytes += filesize("$raiz/$rel");
}
$zip->close();

printf("Listo: %s\n  %d archivos, %s KB sin comprimir, %s KB el zip.\n",
    $salida, count($archivos), number_format($bytes / 1024, 0, ',', '.'),
    number_format(filesize($salida) / 1024, 0, ',', '.'));
echo "Siguiente paso: súbalo con el Administrador de archivos de Hostinger y cree api/config.local.php (vea el README).\n";
