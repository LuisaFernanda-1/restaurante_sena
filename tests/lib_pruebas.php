<?php
/**
 * lib_pruebas.php — Mini marco de pruebas (sin dependencias externas)
 *
 * prueba('nombre', function () { igual(1, 1); });
 * Cliente HTTP con cookies propias (cada cliente = un navegador distinto).
 */

declare(strict_types=1);

final class FalloPrueba extends Exception {}

$GLOBALS['PRUEBAS'] = [];

function prueba(string $nombre, callable $fn, array $opciones = []): void
{
    $GLOBALS['PRUEBAS'][] = ['nombre' => $nombre, 'fn' => $fn, 'grupo' => $GLOBALS['GRUPO_ACTUAL'] ?? '', 'opciones' => $opciones];
}

function grupo(string $nombre): void
{
    $GLOBALS['GRUPO_ACTUAL'] = $nombre;
}

function texto_valor(mixed $v): string
{
    return is_string($v) ? "'$v'" : json_encode($v, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
}

function igual(mixed $esperado, mixed $obtenido, string $que = ''): void
{
    if ($esperado !== $obtenido) {
        throw new FalloPrueba(($que ? "$que: " : '') . 'se esperaba ' . texto_valor($esperado) . ' y se obtuvo ' . texto_valor($obtenido));
    }
}

function verdadero(mixed $condicion, string $que = 'condición'): void
{
    if (!$condicion) {
        throw new FalloPrueba("$que: no se cumplió");
    }
}

function contiene(string $aguja, string $pajar, string $que = ''): void
{
    if (!str_contains($pajar, $aguja)) {
        throw new FalloPrueba(($que ? "$que: " : '') . "no contiene '$aguja' (texto: " . mb_substr($pajar, 0, 160) . ')');
    }
}

/** Respuesta HTTP simplificada. */
final class Respuesta
{
    public function __construct(
        public readonly int $status,
        public readonly string $cuerpo,
        public readonly array $cabeceras,
    ) {}

    public function json(): mixed
    {
        return json_decode($this->cuerpo, true);
    }

    public function cabecera(string $nombre): ?string
    {
        return $this->cabeceras[strtolower($nombre)] ?? null;
    }
}

/** Navegador simulado: guarda sus propias cookies de sesión. */
final class Cliente
{
    private array $cookies = [];

    public function __construct(private readonly string $base) {}

    public function pedir(string $metodo, string $ruta, mixed $json = null, array $cabeceras = [], ?string $crudo = null): Respuesta
    {
        $ch = curl_init($this->base . $ruta);
        $hdrs = [];
        foreach ($cabeceras as $k => $v) {
            $hdrs[] = "$k: $v";
        }
        if ($json !== null) {
            $hdrs[] = 'Content-Type: application/json';
            curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode($json, JSON_UNESCAPED_UNICODE));
        } elseif ($crudo !== null) {
            curl_setopt($ch, CURLOPT_POSTFIELDS, $crudo);
        }
        if ($this->cookies) {
            $hdrs[] = 'Cookie: ' . implode('; ', array_map(fn ($k, $v) => "$k=$v", array_keys($this->cookies), $this->cookies));
        }
        $recibidas = [];
        curl_setopt_array($ch, [
            CURLOPT_CUSTOMREQUEST => $metodo,
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_HTTPHEADER => $hdrs,
            CURLOPT_TIMEOUT => 30,
            CURLOPT_PATH_AS_IS => true,
            CURLOPT_HEADERFUNCTION => function ($ch, string $linea) use (&$recibidas): int {
                if (str_contains($linea, ':')) {
                    [$k, $v] = explode(':', $linea, 2);
                    $k = strtolower(trim($k));
                    $v = trim($v);
                    if ($k === 'set-cookie') {
                        [$par] = explode(';', $v, 2);
                        [$nombre, $valor] = array_pad(explode('=', $par, 2), 2, '');
                        if ($valor === '' || $valor === 'deleted') {
                            unset($this->cookies[$nombre]);
                        } else {
                            $this->cookies[$nombre] = $valor;
                        }
                        $recibidas['set-cookie'][] = $v;
                    } else {
                        $recibidas[$k] = $v;
                    }
                }
                return strlen($linea);
            },
        ]);
        $cuerpo = curl_exec($ch);
        if ($cuerpo === false) {
            throw new FalloPrueba('No hubo respuesta del servidor: ' . curl_error($ch));
        }
        $status = (int) curl_getinfo($ch, CURLINFO_RESPONSE_CODE);
        curl_close($ch);
        if (isset($recibidas['set-cookie'])) {
            $recibidas['set-cookie'] = implode("\n", $recibidas['set-cookie']);
        }
        return new Respuesta($status, (string) $cuerpo, $recibidas);
    }

    public function get(string $ruta, array $cabeceras = []): Respuesta { return $this->pedir('GET', $ruta, null, $cabeceras); }
    public function post(string $ruta, mixed $json = null, array $cabeceras = []): Respuesta { return $this->pedir('POST', $ruta, $json ?? new stdClass(), $cabeceras); }
    public function put(string $ruta, mixed $json = null, array $cabeceras = []): Respuesta { return $this->pedir('PUT', $ruta, $json ?? new stdClass(), $cabeceras); }
    public function delete(string $ruta, array $cabeceras = []): Respuesta { return $this->pedir('DELETE', $ruta, null, $cabeceras); }
}

/** Divide un script SQL en sentencias respetando comillas y comentarios. */
function dividir_sql(string $texto): array
{
    $sentencias = [];
    $actual = '';
    $comilla = null;
    $n = strlen($texto);
    for ($i = 0; $i < $n; $i++) {
        $c = $texto[$i];
        if ($comilla !== null) {
            $actual .= $c;
            if ($c === '\\' && $i + 1 < $n) {
                $actual .= $texto[++$i];
            } elseif ($c === $comilla) {
                $comilla = null;
            }
        } elseif ($c === "'" || $c === '"' || $c === '`') {
            $comilla = $c;
            $actual .= $c;
        } elseif ($c === '-' && substr($texto, $i, 2) === '--') {
            $fin = strpos($texto, "\n", $i);
            $i = $fin === false ? $n : $fin;
        } elseif ($c === '/' && substr($texto, $i, 2) === '/*') {
            $fin = strpos($texto, '*/', $i + 2);
            $i = $fin === false ? $n : $fin + 1;
        } elseif ($c === ';') {
            if (trim($actual) !== '') {
                $sentencias[] = trim($actual);
            }
            $actual = '';
        } else {
            $actual .= $c;
        }
    }
    if (trim($actual) !== '') {
        $sentencias[] = trim($actual);
    }
    return $sentencias;
}
