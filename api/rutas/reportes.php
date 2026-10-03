<?php
/**
 * reportes.php — Reportes de ventas por día, semana y mes (administrador)
 *
 * Solo cuentan los pedidos ENTREGADOS (con comprobante), por la fecha del
 * comprobante. Los cancelados se informan aparte.
 *
 * GET /api/reportes/ventas?periodo=dia|semana|mes&desde=AAAA-MM-DD&hasta=AAAA-MM-DD
 * GET /api/reportes/ventas.csv?...   → el mismo reporte para abrir en Excel
 */

declare(strict_types=1);

// Expresión SQL que agrupa la fecha del comprobante (igual en MariaDB y MySQL 8)
const AGRUPAR_PERIODO = [
    'dia' => 'DATE(f.fecha_factura)',
    'semana' => 'DATE_SUB(DATE(f.fecha_factura), INTERVAL WEEKDAY(f.fecha_factura) DAY)',   // lunes
    'mes' => "DATE_FORMAT(f.fecha_factura, '%Y-%m-01')",
];
const MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto',
    'septiembre', 'octubre', 'noviembre', 'diciembre'];
const MAX_DIAS_REPORTE = 3 * 366;

function inicio_periodo(DateTimeImmutable $d, string $periodo): DateTimeImmutable
{
    return match ($periodo) {
        'semana' => $d->modify('-' . ((int) $d->format('N') - 1) . ' days'),
        'mes' => $d->modify('first day of this month'),
        default => $d,
    };
}

function siguiente_periodo(DateTimeImmutable $d, string $periodo): DateTimeImmutable
{
    return match ($periodo) {
        'dia' => $d->modify('+1 day'),
        'semana' => $d->modify('+7 days'),
        default => $d->modify('first day of next month'),
    };
}

function etiqueta_periodo(DateTimeImmutable $d, string $periodo): string
{
    return match ($periodo) {
        'dia' => $d->format('d/m/Y'),
        'semana' => $d->format('d/m') . ' – ' . $d->modify('+6 days')->format('d/m/Y'),
        default => ucfirst(MESES[(int) $d->format('n') - 1]) . ' ' . $d->format('Y'),
    };
}

/** @return array{0: string, 1: DateTimeImmutable, 2: DateTimeImmutable} */
function rango_reporte(): array
{
    $periodo = arg('periodo') ?? 'dia';
    if (!isset(AGRUPAR_PERIODO[$periodo])) {
        throw new ErrorAPI('periodo: use dia, semana o mes.');
    }
    $hoy = new DateTimeImmutable('today');
    $hasta = ($h = v_fecha(arg('hasta'), 'Hasta')) ? new DateTimeImmutable($h) : $hoy;
    $desdeTxt = v_fecha(arg('desde'), 'Desde');
    if ($desdeTxt !== null) {
        $desde = new DateTimeImmutable($desdeTxt);
    } else {
        $desde = match ($periodo) {
            'dia' => $hasta->modify('-29 days'),
            'semana' => inicio_periodo($hasta, 'semana')->modify('-11 weeks'),
            default => $hasta->modify('first day of this month')->modify('-11 months'),
        };
    }
    if ($desde > $hasta) {
        throw new ErrorAPI('La fecha inicial no puede ser posterior a la final.');
    }
    if ($desde->diff($hasta)->days > MAX_DIAS_REPORTE) {
        throw new ErrorAPI('El rango máximo es de 3 años.');
    }
    return [$periodo, $desde, $hasta];
}

function calcular_reporte(string $periodo, DateTimeImmutable $desde, DateTimeImmutable $hasta): array
{
    // Rango [desde 00:00, hasta+1 00:00): aprovecha el índice de fecha
    $params = [$desde->format('Y-m-d'), $hasta->modify('+1 day')->format('Y-m-d')];
    $filtro = "FROM facturas f JOIN pedidos p ON f.id_pedido = p.id_pedido
               WHERE p.estado = 'entregado' AND f.fecha_factura >= ? AND f.fecha_factura < ?";

    $porInicio = [];
    foreach (consultar('SELECT ' . AGRUPAR_PERIODO[$periodo] . " AS inicio, COUNT(*) AS pedidos,
            CAST(SUM(f.subtotal) AS SIGNED) AS subtotal, CAST(SUM(f.descuento) AS SIGNED) AS descuento,
            CAST(SUM(f.impuesto) AS SIGNED) AS impuesto, CAST(SUM(f.propina) AS SIGNED) AS propina,
            CAST(SUM(f.total) AS SIGNED) AS total
            $filtro GROUP BY inicio ORDER BY inicio", $params) as $f) {
        $porInicio[substr((string) $f['inicio'], 0, 10)] = $f;
    }

    // Todos los períodos del rango, también los que no tuvieron ventas
    $series = [];
    for ($d = inicio_periodo($desde, $periodo); $d <= $hasta; $d = siguiente_periodo($d, $periodo)) {
        $clave = $d->format('Y-m-d');
        $f = $porInicio[$clave] ?? [];
        $pedidos = (int) ($f['pedidos'] ?? 0);
        $total = (int) ($f['total'] ?? 0);
        $series[] = [
            'inicio' => $clave,
            'etiqueta' => etiqueta_periodo($d, $periodo),
            'pedidos' => $pedidos,
            'subtotal' => (int) ($f['subtotal'] ?? 0),
            'descuento' => (int) ($f['descuento'] ?? 0),
            'impuesto' => (int) ($f['impuesto'] ?? 0),
            'propina' => (int) ($f['propina'] ?? 0),
            'total' => $total,
            'ticket_promedio' => $pedidos ? (int) round($total / $pedidos) : 0,
        ];
    }

    $resumen = [];
    foreach (['pedidos', 'subtotal', 'descuento', 'impuesto', 'propina', 'total'] as $k) {
        $resumen[$k] = array_sum(array_column($series, $k));
    }
    $resumen['ticket_promedio'] = $resumen['pedidos'] ? (int) round($resumen['total'] / $resumen['pedidos']) : 0;
    $resumen['cancelados'] = (int) consultar_uno(
        "SELECT COUNT(*) AS n FROM pedidos WHERE estado = 'cancelado' AND fecha_pedido >= ? AND fecha_pedido < ?",
        $params)['n'];

    $productos = consultar(
        "SELECT COALESCE(d.nombre_producto, pr.nombre) AS producto,
                CAST(SUM(d.cantidad) AS SIGNED) AS unidades, CAST(SUM(d.subtotal) AS SIGNED) AS ventas
         FROM detalle_pedidos d
         JOIN productos pr ON d.id_producto = pr.id_producto
         JOIN pedidos p ON d.id_pedido = p.id_pedido
         JOIN facturas f ON f.id_pedido = p.id_pedido
         WHERE p.estado = 'entregado' AND f.fecha_factura >= ? AND f.fecha_factura < ?
         GROUP BY COALESCE(d.nombre_producto, pr.nombre)
         ORDER BY unidades DESC, ventas DESC LIMIT 10", $params);
    $categorias = consultar(
        "SELECT c.nombre_categoria AS categoria,
                CAST(SUM(d.cantidad) AS SIGNED) AS unidades, CAST(SUM(d.subtotal) AS SIGNED) AS ventas
         FROM detalle_pedidos d
         JOIN productos pr ON d.id_producto = pr.id_producto
         JOIN categorias c ON pr.id_categoria = c.id_categoria
         JOIN pedidos p ON d.id_pedido = p.id_pedido
         JOIN facturas f ON f.id_pedido = p.id_pedido
         WHERE p.estado = 'entregado' AND f.fecha_factura >= ? AND f.fecha_factura < ?
         GROUP BY c.nombre_categoria ORDER BY ventas DESC", $params);
    $pagos = consultar("SELECT f.metodo_pago, COUNT(*) AS pedidos, CAST(SUM(f.total) AS SIGNED) AS total
                        $filtro GROUP BY f.metodo_pago ORDER BY total DESC", $params);

    return [
        'periodo' => $periodo,
        'desde' => $desde->format('Y-m-d'),
        'hasta' => $hasta->format('Y-m-d'),
        'resumen' => $resumen,
        'series' => $series,
        'productos' => $productos,
        'categorias' => $categorias,
        'pagos' => $pagos,
    ];
}

ruta('GET', '/reportes/ventas', function (): void {
    exigir_rol([ROL_ADMIN]);
    responder(calcular_reporte(...rango_reporte()));
});

ruta('GET', '/reportes/ventas.csv', function (): void {
    exigir_rol([ROL_ADMIN]);
    [$periodo, $desde, $hasta] = rango_reporte();
    $rep = calcular_reporte($periodo, $desde, $hasta);
    $nombre = ['dia' => 'Día', 'semana' => 'Semana', 'mes' => 'Mes'][$periodo];
    $buf = fopen('php://temp', 'w+');
    // Punto y coma: el separador que Excel espera con la configuración regional de Colombia.
    $fila = fn (array $c) => fputcsv($buf, $c, ';', '"', '\\', "\r\n");
    $fila(['Reporte de ventas por ' . mb_strtolower($nombre), 'Del ' . $desde->format('d/m/Y') . ' al ' . $hasta->format('d/m/Y')]);
    $fila([]);
    $fila([$nombre, 'Pedidos', 'Subtotal', 'Descuentos', 'Impuesto', 'Propinas', 'Total', 'Ticket promedio']);
    foreach ($rep['series'] as $s) {
        $fila([$s['etiqueta'], $s['pedidos'], $s['subtotal'], $s['descuento'], $s['impuesto'], $s['propina'], $s['total'], $s['ticket_promedio']]);
    }
    $r = $rep['resumen'];
    $fila(['TOTAL', $r['pedidos'], $r['subtotal'], $r['descuento'], $r['impuesto'], $r['propina'], $r['total'], $r['ticket_promedio']]);
    $fila(['Pedidos cancelados', $r['cancelados']]);
    $fila([]);
    $fila(['Productos más vendidos', 'Unidades', 'Ventas']);
    foreach ($rep['productos'] as $p) {
        $fila([$p['producto'], $p['unidades'], $p['ventas']]);
    }
    $fila([]);
    $fila(['Categoría', 'Unidades', 'Ventas']);
    foreach ($rep['categorias'] as $c) {
        $fila([$c['categoria'], $c['unidades'], $c['ventas']]);
    }
    $fila([]);
    $fila(['Método de pago', 'Pedidos', 'Total']);
    foreach ($rep['pagos'] as $p) {
        $fila([$p['metodo_pago'], $p['pedidos'], $p['total']]);
    }
    rewind($buf);
    $csv = stream_get_contents($buf);
    fclose($buf);

    if (session_status() === PHP_SESSION_ACTIVE) {
        session_write_close();
    }
    header('Content-Type: text/csv; charset=utf-8');
    header('Cache-Control: no-store');
    header('X-Content-Type-Options: nosniff');
    header('Content-Disposition: attachment; filename="ventas_' . $periodo . '_' . $desde->format('Y-m-d') . '_' . $hasta->format('Y-m-d') . '.csv"');
    echo "\u{FEFF}" . $csv;   // BOM UTF-8 para que Excel muestre bien las tildes
    exit;
});
