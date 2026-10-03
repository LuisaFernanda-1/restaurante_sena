<?php
/**
 * generar_sql_hosting.php — Crea sql/instalacion_hosting.sql a partir de
 * sql/instalacion_local.sql.
 *
 * En Hostinger la base de datos ya existe (con un nombre tipo
 * u123456789_restaurante) y se importa desde phpMyAdmin, así que el script
 * del hosting NO debe tener DROP DATABASE, CREATE DATABASE, USE ni
 * cláusulas DEFINER.
 *
 * Uso:  C:\xampp\php\php.exe scripts\generar_sql_hosting.php
 */

declare(strict_types=1);

$raiz = dirname(__DIR__);
$origen = "$raiz/sql/instalacion_local.sql";
$destino = "$raiz/sql/instalacion_hosting.sql";

$sql = file_get_contents($origen);
if ($sql === false) {
    fwrite(STDERR, "No se pudo leer $origen\n");
    exit(1);
}

// 1. Cabecera propia del hosting
$inicio = strpos($sql, 'SET NAMES utf8mb4');
$cabecera = <<<TXT
-- ============================================================
--  sql/instalacion_hosting.sql
--  Instalación de la base de datos de Restaurante SENA en el HOSTING
--  (Hostinger u otro hosting compartido con phpMyAdmin).
--
--  ARCHIVO GENERADO por scripts/generar_sql_hosting.php a partir de
--  sql/instalacion_local.sql. No lo edite a mano.
--
--  Cómo usarlo:
--    1. En hPanel cree la base de datos y su usuario (vea el README).
--    2. Abra phpMyAdmin, SELECCIONE esa base en la columna izquierda.
--    3. Pestaña "Importar" → elija este archivo → "Importar".
--
--  No crea ni borra la base de datos: se importa en la base que ya
--  existe. Debe importarse en una base VACÍA.
--  Compatible con MariaDB 10.4+ y MySQL 8.
-- ============================================================


TXT;
$sql = $cabecera . substr($sql, $inicio);

// 2. Quitar la creación y selección de la base de datos
$sql = preg_replace('/^--\s*1\. CREAR Y SELECCIONAR BASE DE DATOS\s*$\n/mi', '', $sql);
$sql = preg_replace('/^\s*DROP\s+DATABASE\b[^;]*;\s*$\n?/mi', '', $sql);
$sql = preg_replace('/^\s*CREATE\s+DATABASE\b[^;]*;\s*$\n?/mis', '', $sql);
$sql = preg_replace('/^\s*USE\s+[^;]+;\s*$\n?/mi', '', $sql);

// 3. Quitar cualquier DEFINER (el usuario del hosting no puede asignarlos)
$sql = preg_replace('/\s*DEFINER\s*=\s*(`[^`]*`|\'[^\']*\'|\S+)@(`[^`]*`|\'[^\']*\'|\S+)/i', '', $sql);

// Verificación
foreach (['/\bDROP\s+DATABASE\b/i', '/\bCREATE\s+DATABASE\b/i', '/^\s*USE\s/mi', '/\bDEFINER\b/i'] as $prohibido) {
    if (preg_match($prohibido, $sql)) {
        fwrite(STDERR, "ERROR: el script del hosting todavía contiene $prohibido\n");
        exit(1);
    }
}

file_put_contents($destino, $sql);
echo "Generado: sql/instalacion_hosting.sql (" . strlen($sql) . " bytes)\n";
