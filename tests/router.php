<?php
/**
 * router.php — Imita las reglas de los .htaccess para el servidor de
 * desarrollo de PHP (php -S), que no lee .htaccess. Solo lo usan las
 * pruebas automáticas (tests/probar_api.php).
 */

declare(strict_types=1);

$raiz = dirname(__DIR__);
$ruta = rawurldecode(parse_url($_SERVER['REQUEST_URI'] ?? '/', PHP_URL_PATH) ?: '/');

// Igual que .htaccess: carpetas y archivos privados no se sirven
if (preg_match('#^/(sql|tests|scripts|backend|respaldos|logs|docs|node_modules|\.git)(/|$)#', $ruta)
    || preg_match('#(^|/)\.|\.(md|sql|gz|zip|log|ps1|bat|py|sh|ini|lock|bak|dist)$|config\.(local|example)\.php$#', $ruta)
    || preg_match('#^/api/(lib|rutas)/#', $ruta)
    || (str_starts_with($ruta, '/api/') && str_ends_with($ruta, '.php') && $ruta !== '/api/index.php')) {
    http_response_code(403);
    echo 'Prohibido';
    return true;
}

// /api/... → api/index.php (front controller)
if ($ruta === '/api' || str_starts_with($ruta, '/api/')) {
    $_SERVER['SCRIPT_NAME'] = '/api/index.php';
    $_SERVER['SCRIPT_FILENAME'] = "$raiz/api/index.php";
    chdir("$raiz/api");
    require "$raiz/api/index.php";
    return true;
}

// Página de inicio
if ($ruta === '/') {
    $_SERVER['SCRIPT_NAME'] = '/index.html';
    readfile("$raiz/index.html");
    return true;
}

return false;   // archivos estáticos: los sirve php -S
