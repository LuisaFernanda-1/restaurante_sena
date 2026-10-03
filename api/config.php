<?php
/**
 * config.php — Configuración de Restaurante SENA
 *
 * Toma los valores de api/config.local.php (no versionado; copie
 * config.example.php). Para las pruebas automáticas, cualquier valor se
 * puede reemplazar con una variable de entorno RS_<NOMBRE>
 * (por ejemplo RS_DB_NAME=restaurante_sena_test).
 */

declare(strict_types=1);

const CONFIG_POR_DEFECTO = [
    'DB_HOST' => '127.0.0.1',
    'DB_PORT' => 3306,
    'DB_NAME' => 'restaurante_sena',
    'DB_USER' => 'root',
    'DB_PASS' => '',
    'SERVER_URL' => '',
    'IMPUESTO_NOMBRE' => 'Impoconsumo',
    'IMPUESTO_PCT' => 8,
    'PROPINA_SUGERIDA_PCT' => 10,
    'PERMITIR_SIN_QR' => true,
    'RESTAURANTE_NOMBRE' => 'Restaurante SENA',
    'RESTAURANTE_NIT' => '',
    'RESTAURANTE_DIRECCION' => '',
    'ZONA_HORARIA' => 'America/Bogota',
];

function cargar_config(): array
{
    $config = CONFIG_POR_DEFECTO;
    $archivo = __DIR__ . '/config.local.php';
    if (is_file($archivo)) {
        $local = require $archivo;
        if (!is_array($local)) {
            throw new RuntimeException('api/config.local.php debe devolver un arreglo (vea config.example.php).');
        }
        $config = array_merge($config, $local);
    }
    foreach (array_keys(CONFIG_POR_DEFECTO) as $clave) {
        $env = getenv('RS_' . $clave);
        if ($env !== false) {
            $config[$clave] = $env;
        }
    }

    // Tipos y validaciones
    $config['DB_PORT'] = (int) $config['DB_PORT'];
    $config['SERVER_URL'] = rtrim(trim((string) $config['SERVER_URL']), '/');
    foreach (['IMPUESTO_PCT', 'PROPINA_SUGERIDA_PCT'] as $pct) {
        $valor = str_replace(',', '.', (string) $config[$pct]);
        if (!is_numeric($valor) || (float) $valor < 0 || (float) $valor > 100) {
            throw new RuntimeException("$pct debe ser un número entre 0 y 100.");
        }
        $config[$pct] = (float) $valor;
    }
    $permitir = $config['PERMITIR_SIN_QR'];
    $config['PERMITIR_SIN_QR'] = is_bool($permitir)
        ? $permitir
        : in_array(strtolower(trim((string) $permitir)), ['1', 'true', 'si', 'sí', 'yes', 'on'], true);
    if (!in_array($config['ZONA_HORARIA'], timezone_identifiers_list(), true)) {
        throw new RuntimeException('ZONA_HORARIA no es válida (ejemplo: America/Bogota).');
    }
    return $config;
}

/** Valor de configuración. */
function cfg(string $clave): mixed
{
    static $config = null;
    $config ??= cargar_config();
    return $config[$clave];
}
