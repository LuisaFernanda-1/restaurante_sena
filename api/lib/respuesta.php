<?php
/**
 * respuesta.php — Respuestas JSON y manejo de errores de la API
 */

declare(strict_types=1);

/** Error controlado: se devuelve al cliente con un mensaje claro en español. */
final class ErrorAPI extends Exception
{
    public function __construct(
        public readonly string $msg,
        public readonly int $status = 400,
        public readonly ?string $codigo = null,
    ) {
        parent::__construct($msg);
    }
}

/**
 * Convierte las fechas de MySQL ("2026-10-03 13:30:00") a formato ISO
 * ("2026-10-03T13:30:00"), que todos los navegadores entienden.
 */
function normalizar(mixed $valor): mixed
{
    if (is_array($valor)) {
        foreach ($valor as $k => $v) {
            $valor[$k] = normalizar($v);
        }
        return $valor;
    }
    if (is_string($valor) && preg_match('/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/', $valor)) {
        return str_replace(' ', 'T', $valor);
    }
    return $valor;
}

/** Número de una columna DECIMAL: "10.00" → 10, "8.50" → 8.5 */
function num(mixed $valor): int|float|null
{
    if ($valor === null) {
        return null;
    }
    $f = (float) $valor;
    return floor($f) === $f ? (int) $f : $f;
}

function cabeceras_api(): void
{
    header('Content-Type: application/json; charset=utf-8');
    header('Cache-Control: no-store');
    header('X-Content-Type-Options: nosniff');
}

/** Envía la respuesta JSON y termina. */
function responder(mixed $datos, int $status = 200): never
{
    http_response_code($status);
    cabeceras_api();
    echo json_encode(normalizar($datos), JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_INVALID_UTF8_SUBSTITUTE);
    exit;
}

function responder_error(string $msg, int $status, ?string $codigo = null): never
{
    $cuerpo = ['ok' => false, 'msg' => $msg];
    if ($codigo !== null) {
        $cuerpo['codigo'] = $codigo;
    }
    responder($cuerpo, $status);
}

/** Convierte cualquier error en una respuesta JSON (nunca HTML ni detalles internos). */
function instalar_manejo_de_errores(): void
{
    ini_set('display_errors', '0');
    error_reporting(E_ALL);
    set_error_handler(function (int $nivel, string $mensaje, string $archivo, int $linea): bool {
        if (!(error_reporting() & $nivel)) {
            return false;
        }
        throw new ErrorException($mensaje, 0, $nivel, $archivo, $linea);
    });
    set_exception_handler(function (Throwable $e): void {
        if ($e instanceof ErrorAPI) {
            responder_error($e->msg, $e->status, $e->codigo);
        }
        if ($e instanceof DBDuplicado) {
            responder_error('Ya existe un registro con ese valor.', 409);
        }
        if ($e instanceof DBReferencia) {
            responder_error('No se puede completar: el registro está relacionado con otros datos.', 409);
        }
        if ($e instanceof DBError) {
            error_log('[restaurante] Error de base de datos: ' . $e->getMessage());
            responder_error('Error de base de datos. Intente de nuevo o avise al administrador.', 503);
        }
        error_log('[restaurante] Error inesperado: ' . $e);
        responder_error('Error interno del servidor.', 500);
    });
}
