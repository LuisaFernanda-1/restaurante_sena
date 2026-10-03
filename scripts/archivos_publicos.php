<?php
/**
 * archivos_publicos.php — Lista de los archivos que se publican en el
 * servidor web (XAMPP htdocs o Hostinger). La usan publicar_local.php y
 * generar_zip.php, así lo que se prueba en XAMPP es lo mismo que se sube.
 *
 * NO se publican: sql/, tests/, scripts/, README, ni api/config.local.php
 * (ese se crea en cada servidor con sus propias contraseñas).
 */

declare(strict_types=1);

/** @return string[] rutas relativas con "/" */
function archivos_publicos(string $raiz): array
{
    $lista = ['.htaccess'];
    foreach (glob("$raiz/*.html") as $html) {
        $lista[] = basename($html);
    }
    foreach (['css', 'js', 'img', 'api'] as $carpeta) {
        if (!is_dir("$raiz/$carpeta")) {
            continue;
        }
        $it = new RecursiveIteratorIterator(
            new RecursiveDirectoryIterator("$raiz/$carpeta", FilesystemIterator::SKIP_DOTS));
        foreach ($it as $archivo) {
            $rel = str_replace('\\', '/', substr($archivo->getPathname(), strlen($raiz) + 1));
            if ($archivo->isFile() && !es_privado($rel)) {
                $lista[] = $rel;
            }
        }
    }
    sort($lista);
    return $lista;
}

function es_privado(string $rel): bool
{
    return $rel === 'api/config.local.php'
        || str_ends_with($rel, '.md')
        || str_ends_with($rel, '~')
        || str_ends_with($rel, '.bak');
}
