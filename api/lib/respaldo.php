<?php
/**
 * respaldo.php — Exportador de la base de datos en SQL (sin mysqldump)
 *
 * En el hosting compartido no hay mysqldump, así que el respaldo se arma
 * con PDO: estructura de las tablas, datos y vistas. El resultado se puede
 * importar en phpMyAdmin (Importar → archivo .sql.gz) en una base con
 * cualquier nombre: no lleva el nombre de la base ni cláusulas DEFINER.
 *
 * Lo usan el botón "Descargar respaldo" del panel (GET /api/respaldo) y
 * los scripts de consola scripts/respaldo.php y scripts/restaurar.php.
 */

declare(strict_types=1);

// Tablas cuyo contenido es temporal: se respalda solo su estructura.
const TABLAS_SIN_DATOS = ['sesiones', 'limites'];

/** Genera el respaldo completo como texto SQL. */
function generar_respaldo_sql(): string
{
    $pdo = db();
    $bd = (string) $pdo->query('SELECT DATABASE()')->fetchColumn();
    $sql = [];
    $sql[] = '-- ============================================================';
    $sql[] = '--  Respaldo de Restaurante SENA';
    $sql[] = '--  Fecha: ' . date('Y-m-d H:i:s') . ' (' . cfg('ZONA_HORARIA') . ')';
    $sql[] = '--  Restaurar: phpMyAdmin → seleccionar la base → Importar este archivo.';
    $sql[] = '--  Reemplaza las tablas de la base donde se importe.';
    $sql[] = '-- ============================================================';
    $sql[] = '';
    $sql[] = 'SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;';
    $sql[] = 'SET FOREIGN_KEY_CHECKS = 0;';
    $sql[] = "SET SQL_MODE = 'NO_AUTO_VALUE_ON_ZERO';";
    $sql[] = '';

    $tablas = $pdo->query("SHOW FULL TABLES WHERE Table_type = 'BASE TABLE'")->fetchAll(PDO::FETCH_NUM);
    $vistas = $pdo->query("SHOW FULL TABLES WHERE Table_type = 'VIEW'")->fetchAll(PDO::FETCH_NUM);

    // Primero se quitan las vistas (dependen de las tablas)
    foreach ($vistas as [$vista]) {
        $sql[] = 'DROP VIEW IF EXISTS `' . $vista . '`;';
    }
    foreach ($tablas as [$tabla]) {
        $crear = $pdo->query('SHOW CREATE TABLE `' . $tabla . '`')->fetch(PDO::FETCH_NUM)[1];
        $sql[] = '';
        $sql[] = "-- Tabla $tabla";
        $sql[] = 'DROP TABLE IF EXISTS `' . $tabla . '`;';
        $sql[] = $crear . ';';
        if (in_array($tabla, TABLAS_SIN_DATOS, true)) {
            continue;
        }
        $columnas = null;
        $lote = [];
        $st = $pdo->query('SELECT * FROM `' . $tabla . '`');
        while ($fila = $st->fetch(PDO::FETCH_ASSOC)) {
            $columnas ??= '(`' . implode('`, `', array_keys($fila)) . '`)';
            $valores = array_map(function ($v) use ($pdo) {
                if ($v === null) {
                    return 'NULL';
                }
                if (is_int($v) || is_float($v)) {
                    return (string) $v;
                }
                return $pdo->quote((string) $v);
            }, array_values($fila));
            $lote[] = '(' . implode(', ', $valores) . ')';
            if (count($lote) === 200) {
                $sql[] = 'INSERT INTO `' . $tabla . "` $columnas VALUES\n" . implode(",\n", $lote) . ';';
                $lote = [];
            }
        }
        if ($lote) {
            $sql[] = 'INSERT INTO `' . $tabla . "` $columnas VALUES\n" . implode(",\n", $lote) . ';';
        }
    }

    foreach ($vistas as [$vista]) {
        $crear = $pdo->query('SHOW CREATE VIEW `' . $vista . '`')->fetch(PDO::FETCH_NUM)[1];
        // Sin DEFINER/ALGORITHM/SQL SECURITY y sin el nombre de la base: así se
        // puede restaurar en una base con otro nombre (como la del hosting).
        $crear = preg_replace('/^CREATE\s+.*?\bVIEW\b/is', 'CREATE OR REPLACE VIEW', $crear);
        $crear = str_replace('`' . $bd . '`.', '', $crear);
        $sql[] = '';
        $sql[] = "-- Vista $vista";
        $sql[] = $crear . ';';
    }
    $sql[] = '';
    $sql[] = 'SET FOREIGN_KEY_CHECKS = 1;';
    $sql[] = '-- Respaldo completo';
    return implode("\n", $sql) . "\n";
}

function nombre_archivo_respaldo(): string
{
    return 'restaurante_sena_' . date('Ymd_His') . '.sql.gz';
}

/** Divide un script SQL en sentencias, respetando comillas y comentarios. */
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

/** Ejecuta un script SQL completo en la conexión indicada. */
function ejecutar_script_sql(PDO $pdo, string $texto): int
{
    $total = 0;
    foreach (dividir_sql($texto) as $sentencia) {
        $st = $pdo->query($sentencia);
        if ($st->columnCount() > 0) {
            $st->fetchAll();
        }
        $st->closeCursor();
        $total++;
    }
    return $total;
}
