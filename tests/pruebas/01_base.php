<?php
/** Fase 1: scripts SQL, rutas públicas, JSON y archivos protegidos. */

declare(strict_types=1);

// ============================================================
grupo('Scripts SQL');
// ============================================================
prueba('el script del hosting está actualizado con el local', function (): void {
    $antes = file_get_contents(RAIZ . '/sql/instalacion_hosting.sql');
    exec(escapeshellarg(PHP_BINARY) . ' ' . escapeshellarg(RAIZ . '/scripts/generar_sql_hosting.php'), $salida, $codigo);
    igual(0, $codigo, 'generar_sql_hosting.php');
    igual($antes, file_get_contents(RAIZ . '/sql/instalacion_hosting.sql'),
        'sql/instalacion_hosting.sql no coincide: ejecute scripts/generar_sql_hosting.php');
}, ['sin_bd' => true]);

prueba('el script del hosting no crea, borra ni selecciona bases, ni usa DEFINER', function (): void {
    $sql = file_get_contents(RAIZ . '/sql/instalacion_hosting.sql');
    foreach (['/\bDROP\s+DATABASE\b/i', '/\bCREATE\s+DATABASE\b/i', '/^\s*USE\s/mi', '/\bDEFINER\b/i'] as $patron) {
        verdadero(!preg_match($patron, $sql), "no contiene $patron");
    }
    foreach (['instalacion_local.sql', 'instalacion_hosting.sql'] as $f) {
        $s = file_get_contents(RAIZ . "/sql/$f");
        contiene('SET NAMES utf8mb4', $s, $f);
        contiene('utf8mb4_unicode_ci', $s, $f);
        verdadero(!str_contains($s, 'utf8mb4_0900'), "$f no usa la intercalación de MySQL 8 que MariaDB rechaza");
    }
}, ['sin_bd' => true]);

prueba('el script del hosting crea el mismo esquema que el local', function (): void {
    recrear_bd();
    $hosting = 'u123456789_restaurante_test';
    cargar_script(RAIZ . '/sql/instalacion_hosting.sql', $hosting, true);
    $esquema = function (string $bd): array {
        $pdo = pdo_servidor();
        $consultas = [
            "SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLLATION_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = ? ORDER BY 1, 2",
            "SELECT DISTINCT TABLE_NAME, INDEX_NAME FROM information_schema.STATISTICS WHERE TABLE_SCHEMA = ? ORDER BY 1, 2",
            "SELECT CONSTRAINT_NAME, CHECK_CLAUSE FROM information_schema.CHECK_CONSTRAINTS WHERE CONSTRAINT_SCHEMA = ? ORDER BY 1",
            "SELECT TABLE_NAME FROM information_schema.VIEWS WHERE TABLE_SCHEMA = ? ORDER BY 1",
        ];
        $r = [];
        foreach ($consultas as $q) {
            $st = $pdo->prepare($q);
            $st->execute([$bd]);
            $r[] = $st->fetchAll(PDO::FETCH_NUM);
        }
        return $r;
    };
    try {
        igual($esquema(BD_PRUEBAS), $esquema($hosting), 'esquema');
        $pdo = pdo_servidor();
        igual('Ceviche de Camarón', $pdo->query("SELECT nombre FROM `$hosting`.productos WHERE id_producto = 3")->fetchColumn());
        igual('🍤', $pdo->query("SELECT emoji FROM `$hosting`.productos WHERE id_producto = 3")->fetchColumn());
    } finally {
        pdo_servidor()->exec("DROP DATABASE IF EXISTS `$hosting`");
    }
}, ['sin_bd' => true]);

prueba('usuarios iniciales con hash de password_hash y cambio obligatorio', function (): void {
    $sql = file_get_contents(RAIZ . '/sql/instalacion_local.sql');
    preg_match_all("/'(\\\$2y\\\$\d\d\\\$[^']+)'/", $sql, $m);
    igual(3, count($m[1]), 'hashes bcrypt');
    verdadero(!str_contains($sql, 'Temporal-2026'), 'sin contraseñas en texto');
    recrear_bd();
    igual(3, (int) sql_valor('SELECT COUNT(*) FROM usuarios WHERE debe_cambiar_clave = 1'));
}, ['sin_bd' => true]);

// ============================================================
grupo('Rutas públicas');
// ============================================================
prueba('status', function (): void {
    $r = cliente()->get('/api/status');
    igual(200, $r->status);
    igual(true, $r->json()['ok']);
    igual('application/json; charset=utf-8', $r->cabecera('content-type'));
});

prueba('productos: tildes, emojis y precios enteros', function (): void {
    $productos = cliente()->get('/api/productos')->json();
    igual(18, count($productos));
    $ceviche = array_values(array_filter($productos, fn ($p) => $p['id_producto'] === 3))[0];
    igual('Ceviche de Camarón', $ceviche['nombre']);
    igual('🍤', $ceviche['emoji']);
    igual(18000, $ceviche['precio']);
    igual(1, $ceviche['disponible']);
});

prueba('productos: filtros por categoría, búsqueda y disponibles', function (): void {
    $c = cliente();
    igual(4, count($c->get('/api/productos?cat=Postres')->json()));
    igual('Bandeja Paisa', $c->get('/api/productos?q=bandeja')->json()[0]['nombre']);
    sql_ejecutar('UPDATE productos SET disponible = 0 WHERE id_producto = 1');
    igual(17, count($c->get('/api/productos?disponible=1')->json()));
    igual(18, count($c->get('/api/productos')->json()));   // la carta muestra los agotados
});

prueba('producto por id y producto inexistente', function (): void {
    igual('Bandeja Paisa', cliente()->get('/api/productos/5')->json()['nombre']);
    $r = cliente()->get('/api/productos/999');
    igual(404, $r->status);
    igual(['ok' => false, 'msg' => 'Producto no encontrado.'], $r->json());
});

prueba('categorías activas en orden', function (): void {
    $cats = array_column(cliente()->get('/api/categorias')->json(), 'nombre_categoria');
    igual(['Entradas', 'Principales', 'Bebidas', 'Postres'], $cats);
});

prueba('config pública', function (): void {
    $c = cliente()->get('/api/config')->json();
    igual('Impoconsumo', $c['impuesto_nombre']);
    igual(8, $c['impuesto_pct']);
    igual(10, $c['propina_pct']);
    igual(false, $c['pedido_sin_qr']);
    verdadero(abs(strtotime($c['ahora']) - time()) < 5, 'hora del servidor');
    igual(true, cliente('sin_qr')->get('/api/config')->json()['pedido_sin_qr']);
});

prueba('mesa con su código QR', function (): void {
    $r = cliente()->get('/api/mesas/5?c=' . codigo_mesa(5));
    igual(200, $r->status);
    igual(['numero_mesa' => 5, 'capacidad' => 4, 'estado' => 'disponible', 'activa' => true, 'origen' => 'qr'], $r->json());
});

prueba('mesas inválidas', function (): void {
    $c = cliente();
    igual(404, $c->get('/api/mesas/99?c=abc')->status);
    igual(404, $c->get('/api/mesas/demo')->status);
    $r = $c->get('/api/mesas/5');                                 // sin código en modo solo QR
    igual(403, $r->status);
    igual('qr_requerido', $r->json()['codigo']);
    $r = $c->get('/api/mesas/7?c=' . codigo_mesa(5));             // código de otra mesa
    igual(403, $r->status);
    igual('qr_invalido', $r->json()['codigo']);
    igual(false, $c->get('/api/mesas/16?c=' . codigo_mesa(16))->json()['activa']);
});

prueba('modo sin QR: lista de mesas y mesa sin código', function (): void {
    $c = cliente('sin_qr');
    $mesas = $c->get('/api/mesas/disponibles')->json();
    igual(19, count($mesas));
    verdadero(!in_array(16, array_column($mesas, 'numero_mesa'), true), 'sin la mesa inactiva');
    igual(['numero_mesa', 'capacidad', 'estado'], array_keys($mesas[0]), 'nunca el código del QR');
    igual('manual', $c->get('/api/mesas/7')->json()['origen']);
    igual(403, $c->get('/api/mesas/7?c=0000000000')->status, 'un código equivocado se rechaza igual');
    igual(403, cliente()->get('/api/mesas/disponibles')->status, 'en modo solo QR no hay lista');
});

prueba('ruta inexistente y método no permitido responden JSON', function (): void {
    $r = cliente()->get('/api/no-existe');
    igual(404, $r->status);
    igual(['ok' => false, 'msg' => 'Recurso no encontrado.'], $r->json());
    $r = cliente()->post('/api/status');
    igual(405, $r->status);
    igual(false, $r->json()['ok']);
});

prueba('los archivos privados no se sirven', function (): void {
    $c = cliente();
    foreach (['/api/config.php', '/api/config.local.php', '/api/config.example.php', '/api/lib/db.php',
              '/api/rutas/publico.php', '/sql/instalacion_local.sql', '/tests/probar_api.php',
              '/scripts/publicar_local.php', '/.htaccess', '/README.md'] as $ruta) {
        verdadero(in_array($c->get($ruta)->status, [403, 404], true), "$ruta bloqueado");
    }
    igual(200, $c->get('/menu.html')->status);
    igual(200, $c->get('/js/api.js')->status);
}, ['sin_bd' => true]);

// ============================================================
grupo('Apache de XAMPP (reglas .htaccess reales)');
// ============================================================
prueba('la API responde por Apache', function (): void {
    $c = new Cliente($GLOBALS['URL_APACHE']);
    $r = $c->get('/api/status');
    igual(200, $r->status, 'status');
    igual(true, $r->json()['ok']);
    igual(200, $c->get('/api/productos')->status);
    igual(404, $c->get('/api/no-existe')->status);
    igual(405, $c->post('/api/status')->status);
    igual('application/json; charset=utf-8', $c->get('/api/config')->cabecera('content-type'), '/api/config es la ruta, no config.php');
}, ['apache' => true]);

prueba('Apache no entrega archivos privados', function (): void {
    $c = new Cliente($GLOBALS['URL_APACHE']);
    foreach (['/api/config.php', '/api/config.local.php', '/api/config.example.php', '/api/lib/db.php', '/api/lib/',
              '/api/rutas/publico.php', '/api/index.php/../config.local.php', '/.htaccess', '/api/.htaccess',
              '/sql/', '/tests/', '/scripts/', '/css/', '/js/'] as $ruta) {
        $r = $c->get($ruta);
        verdadero(in_array($r->status, [403, 404], true), "$ruta bloqueado (respondió {$r->status})");
        verdadero(!str_contains($r->cuerpo, 'DB_PASS'), "$ruta no muestra la configuración");
    }
}, ['apache' => true]);

prueba('Apache sirve las páginas con cabeceras de seguridad', function (): void {
    $c = new Cliente($GLOBALS['URL_APACHE']);
    foreach (['/', '/index.html', '/menu.html', '/css/styles.css', '/js/api.js'] as $ruta) {
        igual(200, $c->get($ruta)->status, $ruta);
    }
    $r = $c->get('/index.html');
    igual('nosniff', $r->cabecera('x-content-type-options'));
    igual('SAMEORIGIN', $r->cabecera('x-frame-options'));
}, ['apache' => true]);
