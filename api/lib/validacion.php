<?php
/**
 * validacion.php — Validación de los datos que llegan a la API
 *
 * Todas las funciones lanzan ErrorAPI (HTTP 400) con un mensaje claro.
 */

declare(strict_types=1);

/**
 * Cuerpo JSON de la petición (objeto). Exigir Content-Type JSON también
 * protege contra formularios enviados desde otros sitios (CSRF).
 */
function cuerpo_json(): array
{
    $tipo = strtolower($_SERVER['CONTENT_TYPE'] ?? '');
    $crudo = file_get_contents('php://input');
    $objeto = str_starts_with($tipo, 'application/json') && $crudo !== false ? json_decode($crudo) : null;
    if (!($objeto instanceof stdClass)) {
        throw new ErrorAPI('El cuerpo de la petición debe ser un objeto JSON.');
    }
    return json_decode($crudo, true);
}

function v_entero(mixed $valor, string $campo, ?int $minimo = null, ?int $maximo = null): int
{
    if (is_float($valor) && floor($valor) === $valor && abs($valor) < PHP_INT_MAX) {
        $valor = (int) $valor;
    }
    if (is_string($valor) && preg_match('/^\s*-?\d{1,15}\s*$/', $valor)) {
        $valor = (int) $valor;
    }
    if (!is_int($valor)) {
        throw new ErrorAPI("$campo: debe ser un número entero.");
    }
    if ($minimo !== null && $valor < $minimo) {
        throw new ErrorAPI("$campo: debe ser como mínimo $minimo.");
    }
    if ($maximo !== null && $valor > $maximo) {
        throw new ErrorAPI("$campo: debe ser como máximo $maximo.");
    }
    return $valor;
}

function v_texto(mixed $valor, string $campo, int $max, bool $obligatorio = false): string
{
    $valor ??= '';
    if (!is_string($valor)) {
        throw new ErrorAPI("$campo: debe ser texto.");
    }
    $valor = trim($valor);
    if ($obligatorio && $valor === '') {
        throw new ErrorAPI("$campo: es obligatorio.");
    }
    if (mb_strlen($valor) > $max) {
        throw new ErrorAPI("$campo: máximo $max caracteres.");
    }
    return $valor;
}

function v_bool(mixed $valor, string $campo): bool
{
    if (is_bool($valor)) {
        return $valor;
    }
    if (in_array($valor, [0, 1, '0', '1'], true)) {
        return (string) $valor === '1';
    }
    throw new ErrorAPI("$campo: debe ser verdadero o falso.");
}

/** Fecha AAAA-MM-DD (o null si viene vacía y no es obligatoria). */
function v_fecha(mixed $valor, string $campo, bool $obligatoria = false): ?string
{
    if ($valor === null || $valor === '') {
        if ($obligatoria) {
            throw new ErrorAPI("$campo: es obligatoria.");
        }
        return null;
    }
    $f = is_string($valor) ? DateTime::createFromFormat('!Y-m-d', $valor) : false;
    if (!$f || $f->format('Y-m-d') !== $valor) {
        throw new ErrorAPI("$campo: use el formato AAAA-MM-DD.");
    }
    return $valor;
}

function v_correo(mixed $valor, string $campo = 'Correo'): ?string
{
    $correo = mb_strtolower(v_texto($valor, $campo, 150));
    if ($correo !== '' && !preg_match('/^[^@\s]+@[^@\s]+\.[^@\s]+$/u', $correo)) {
        throw new ErrorAPI("$campo: no es un correo válido.");
    }
    return $correo === '' ? null : $correo;
}

/** Parámetro entero de la dirección (?limit=50). */
function arg_entero(string $nombre, int $defecto, int $minimo, int $maximo): int
{
    $valor = $_GET[$nombre] ?? null;
    if ($valor === null || $valor === '') {
        return $defecto;
    }
    return v_entero($valor, $nombre, $minimo, $maximo);
}

function arg(string $nombre): ?string
{
    $valor = $_GET[$nombre] ?? null;
    return is_string($valor) ? $valor : null;
}
