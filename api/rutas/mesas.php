<?php
/**
 * mesas.php — Mesas para el personal
 *
 * GET /api/mesas                  → todas (personal; el código del QR solo lo ve el admin)
 * PUT /api/mesas/{id}/estado      → cambiar estado (administrador o mesero)
 */

declare(strict_types=1);

const ESTADOS_MESA = ['disponible', 'ocupada', 'reservada', 'inactiva'];

ruta('GET', '/mesas', function (): void {
    $u = exigir_rol();
    $columnas = 'id_mesa, numero_mesa, capacidad, estado';
    if ($u['rol'] === ROL_ADMIN) {
        $columnas .= ', codigo_qr';   // solo el admin necesita los códigos (QR)
    }
    $sql = "SELECT $columnas FROM mesas";
    $params = [];
    if (($estado = arg('estado')) !== null && $estado !== '') {
        if (!in_array($estado, ESTADOS_MESA, true)) {
            throw new ErrorAPI('Estado de mesa inválido.');
        }
        $sql .= ' WHERE estado = ?';
        $params[] = $estado;
    }
    responder(consultar($sql . ' ORDER BY numero_mesa', $params));
});

ruta('PUT', '/mesas/{id:n}/estado', function (string $id): void {
    exigir_rol([ROL_ADMIN, ROL_MESERO]);
    $estado = cuerpo_json()['estado'] ?? null;
    if (!in_array($estado, ESTADOS_MESA, true)) {
        throw new ErrorAPI('Estado de mesa inválido.');
    }
    [$filas] = ejecutar('UPDATE mesas SET estado = ? WHERE id_mesa = ?', [$estado, (int) $id]);
    if ($filas === 0 && !consultar_uno('SELECT 1 AS ok FROM mesas WHERE id_mesa = ?', [(int) $id])) {
        throw new ErrorAPI('Mesa no encontrada.', 404);
    }
    responder(['ok' => true]);
});
