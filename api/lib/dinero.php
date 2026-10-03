<?php
/**
 * dinero.php — Cálculo de totales en pesos colombianos (enteros)
 *
 *   base      = subtotal − descuento del cupón
 *   impuesto  = base × IMPUESTO_PCT             (Impoconsumo 8 %)
 *   propina   = base × PROPINA_SUGERIDA_PCT, solo si el comensal la acepta
 *   total     = base + impuesto + propina
 *
 * Cada valor se redondea al peso más cercano (0,5 hacia arriba). Se
 * calcula con enteros para evitar errores de redondeo de los decimales.
 */

declare(strict_types=1);

function porcentaje_de(int $base, float|int $pct): int
{
    $centesimas = (int) round($pct * 100);          // 8 % → 800; 8,5 % → 850
    return intdiv($base * $centesimas + 5000, 10000);
}

function calcular_totales(int $subtotal, float|int $descuento_pct = 0, bool $con_propina = true): array
{
    $descuento = porcentaje_de($subtotal, $descuento_pct);
    $base = $subtotal - $descuento;
    $impuesto = porcentaje_de($base, cfg('IMPUESTO_PCT'));
    $propina = $con_propina ? porcentaje_de($base, cfg('PROPINA_SUGERIDA_PCT')) : 0;
    return [
        'subtotal' => $subtotal,
        'descuento' => $descuento,
        'impuesto' => $impuesto,
        'propina' => $propina,
        'total' => $base + $impuesto + $propina,
    ];
}
