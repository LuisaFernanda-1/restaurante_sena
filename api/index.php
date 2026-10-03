<?php
/**
 * api/index.php — Punto de entrada único de la API de Restaurante SENA
 *
 * El .htaccess de esta carpeta envía aquí todas las peticiones a /api/...
 * Las rutas y el JSON son los mismos de la versión anterior (Flask), así
 * el frontend (js/api.js) funciona igual.
 */

declare(strict_types=1);

require __DIR__ . '/config.php';
require __DIR__ . '/lib/respuesta.php';
require __DIR__ . '/lib/db.php';
require __DIR__ . '/lib/validacion.php';
require __DIR__ . '/lib/dinero.php';

instalar_manejo_de_errores();
date_default_timezone_set(cfg('ZONA_HORARIA'));

// ------------------------------------------------------------
// Enrutador
// ------------------------------------------------------------
final class Enrutador
{
    /** @var array<int, array{0:string,1:string,2:callable}> */
    private array $rutas = [];

    /**
     * Registra una ruta. En el patrón, {nombre} acepta un segmento y
     * {nombre:n} solo dígitos. Ejemplo: '/pedidos/{id:n}/estado'
     */
    public function agregar(string $metodo, string $patron, callable $accion): void
    {
        $regex = preg_replace_callback('/\{(\w+)(:n)?\}/', function (array $m): string {
            return '(?P<' . $m[1] . '>' . (isset($m[2]) && $m[2] !== '' ? '\d{1,10}' : '[^/]+') . ')';
        }, $patron);
        $this->rutas[] = [$metodo, '#^' . $regex . '$#', $accion];
    }

    public function despachar(string $metodo, string $ruta): never
    {
        $metodo = $metodo === 'HEAD' ? 'GET' : $metodo;
        $existe = false;
        foreach ($this->rutas as [$m, $regex, $accion]) {
            if (!preg_match($regex, $ruta, $coincide)) {
                continue;
            }
            $existe = true;
            if ($m !== $metodo) {
                continue;
            }
            $params = array_filter($coincide, 'is_string', ARRAY_FILTER_USE_KEY);
            $accion(...$params);
            responder_error('La acción no devolvió respuesta.', 500);
        }
        if ($existe) {
            responder_error('Método no permitido.', 405);
        }
        responder_error('Recurso no encontrado.', 404);
    }
}

$enrutador = new Enrutador();

function ruta(string $metodo, string $patron, callable $accion): void
{
    global $enrutador;
    $enrutador->agregar($metodo, $patron, $accion);
}

// Ruta pedida, relativa a esta carpeta: /restaurante/api/productos → /productos
function ruta_actual(): string
{
    $uri = rawurldecode(parse_url($_SERVER['REQUEST_URI'] ?? '/', PHP_URL_PATH) ?: '/');
    $base = rtrim(str_replace('\\', '/', dirname($_SERVER['SCRIPT_NAME'] ?? '/api/index.php')), '/');
    if ($base !== '' && str_starts_with($uri, $base)) {
        $uri = substr($uri, strlen($base));
    }
    return '/' . trim($uri, '/');
}

require __DIR__ . '/rutas/publico.php';

$enrutador->despachar($_SERVER['REQUEST_METHOD'] ?? 'GET', ruta_actual());
