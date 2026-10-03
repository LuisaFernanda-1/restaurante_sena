<?php
/**
 * db.php — Acceso a MySQL / MariaDB con PDO
 *
 * - Todas las consultas son parametrizadas (?), nunca se arma SQL con
 *   datos del usuario.
 * - Los errores no se esconden: se lanzan como DBError.
 * - La sesión de MySQL usa la zona horaria configurada, para que NOW() y
 *   los reportes coincidan con la hora del restaurante aunque el servidor
 *   del hosting esté en otra zona.
 */

declare(strict_types=1);

class DBError extends RuntimeException {}
final class DBDuplicado extends DBError {}
final class DBReferencia extends DBError {}

function db(): PDO
{
    static $pdo = null;
    if ($pdo !== null) {
        return $pdo;
    }
    $dsn = sprintf('mysql:host=%s;port=%d;dbname=%s;charset=utf8mb4',
        cfg('DB_HOST'), cfg('DB_PORT'), cfg('DB_NAME'));
    try {
        $pdo = new PDO($dsn, (string) cfg('DB_USER'), (string) cfg('DB_PASS'), [
            PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
            PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
            PDO::ATTR_EMULATE_PREPARES => false,   // los INT llegan como números
            PDO::ATTR_TIMEOUT => 10,
        ]);
        $desfase = (new DateTime('now', new DateTimeZone(cfg('ZONA_HORARIA'))))->format('P');
        $pdo->exec("SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci, time_zone = '$desfase'");
    } catch (PDOException $e) {
        $pdo = null;
        throw new DBError('No hay conexión con la base de datos: ' . $e->getMessage(), 0, $e);
    }
    return $pdo;
}

function traducir_error_pdo(PDOException $e): DBError
{
    $codigo = $e->errorInfo[1] ?? null;
    return match ($codigo) {
        1062 => new DBDuplicado('Registro duplicado', 0, $e),
        1451, 1452 => new DBReferencia('Registro relacionado', 0, $e),
        default => new DBError($e->getMessage(), 0, $e),
    };
}

function preparar(string $sql, array $params): PDOStatement
{
    try {
        $st = db()->prepare($sql);
        $i = 1;
        foreach ($params as $valor) {
            $tipo = match (true) {
                is_int($valor), is_bool($valor) => PDO::PARAM_INT,
                $valor === null => PDO::PARAM_NULL,
                default => PDO::PARAM_STR,
            };
            $st->bindValue($i++, is_bool($valor) ? (int) $valor : $valor, $tipo);
        }
        $st->execute();
        return $st;
    } catch (PDOException $e) {
        throw traducir_error_pdo($e);
    }
}

/** SELECT que devuelve todas las filas. */
function consultar(string $sql, array $params = []): array
{
    return preparar($sql, $params)->fetchAll();
}

/** SELECT que devuelve una fila o null. */
function consultar_uno(string $sql, array $params = []): ?array
{
    $fila = preparar($sql, $params)->fetch();
    return $fila === false ? null : $fila;
}

/** INSERT/UPDATE/DELETE. Devuelve [filas afectadas, id insertado]. */
function ejecutar(string $sql, array $params = []): array
{
    $st = preparar($sql, $params);
    return [$st->rowCount(), (int) db()->lastInsertId()];
}

/**
 * Ejecuta varias sentencias como una sola unidad: si algo falla se
 * deshace todo.
 */
function transaccion(callable $trabajo): mixed
{
    $pdo = db();
    $pdo->beginTransaction();
    try {
        $resultado = $trabajo();
        $pdo->commit();
        return $resultado;
    } catch (Throwable $e) {
        if ($pdo->inTransaction()) {
            $pdo->rollBack();
        }
        throw $e;
    }
}

function probar_conexion(): bool
{
    try {
        consultar_uno('SELECT 1 AS ok');
        return true;
    } catch (DBError) {
        return false;
    }
}

/** "?, ?, ?" para una lista IN (...). */
function marcas(int $cantidad): string
{
    return implode(', ', array_fill(0, $cantidad, '?'));
}
