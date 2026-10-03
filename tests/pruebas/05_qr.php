<?php
/** Fase 5: diagnóstico de SERVER_URL para los QR (los QR se generan en el navegador). */

declare(strict_types=1);

grupo('Códigos QR');

prueba('diagnóstico de SERVER_URL (solo administrador)', function (): void {
    igual(401, cliente()->get('/api/qr/info')->status);
    igual(403, como('mesero')->get('/api/qr/info')->status);
    $i = como('admin')->get('/api/qr/info')->json();
    igual(base_url(), $i['server_url']);
    igual(true, $i['configurado']);
    igual(true, $i['es_local'], '127.0.0.1 solo sirve en este equipo');
    igual(false, $i['https']);
});

prueba('las mesas del panel traen el código para armar el QR', function (): void {
    $mesas = como('admin')->get('/api/mesas')->json();
    igual(20, count($mesas));
    foreach ($mesas as $m) {
        verdadero((bool) preg_match('/^[0-9a-f]{10}$/', (string) $m['codigo_qr']), "mesa {$m['numero_mesa']}");
    }
    igual(20, count(array_unique(array_column($mesas, 'codigo_qr'))), 'códigos distintos');
});

prueba('la librería de QR y su licencia están en el proyecto (no por CDN)', function (): void {
    foreach (['js/vendor/qrcode-generator.js', 'js/vendor/LICENCIA-qrcode-generator.txt', 'js/vendor/jsQR.js', 'js/vendor/LICENCIA-jsQR.txt'] as $f) {
        verdadero(is_file(RAIZ . "/$f"), $f);
    }
    contiene('MIT', file_get_contents(RAIZ . '/js/vendor/LICENCIA-qrcode-generator.txt'));
    contiene('Apache License', file_get_contents(RAIZ . '/js/vendor/LICENCIA-jsQR.txt'));
    foreach (['admin.html', 'qr-mesas.html', 'factura.html', 'index.html'] as $pagina) {
        $html = file_get_contents(RAIZ . "/$pagina");
        verdadero(!preg_match('#<script[^>]+src="https?://[^"]*(qr|jsqr)#i', $html), "$pagina no carga QR desde un CDN");
    }
}, ['sin_bd' => true]);
