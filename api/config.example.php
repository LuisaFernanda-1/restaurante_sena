<?php
/**
 * config.example.php — PLANTILLA de configuración de Restaurante SENA
 *
 * 1. Copie este archivo como  api/config.local.php
 * 2. Complete los valores.
 *
 * config.local.php tiene contraseñas: NUNCA lo suba a git (está en
 * .gitignore) y el .htaccess impide abrirlo desde el navegador.
 */

return [
    // --- Base de datos ---
    // XAMPP:      DB_HOST 127.0.0.1, DB_PORT 3306 (o el que muestre XAMPP),
    //             DB_USER root, DB_PASS vacío, DB_NAME restaurante_sena
    // Hostinger:  copie los datos que muestra hPanel → Bases de datos MySQL
    //             (DB_HOST suele ser "localhost"; DB_NAME y DB_USER tienen
    //             la forma u123456789_algo)
    'DB_HOST' => '127.0.0.1',
    'DB_PORT' => 3306,
    'DB_NAME' => 'restaurante_sena',
    'DB_USER' => 'root',
    'DB_PASS' => '',

    // Dirección pública del sistema, SIN barra final. Va dentro de los QR
    // de las mesas y de los comprobantes.
    //   XAMPP en la red local:  http://192.168.1.10/restaurante
    //   Hostinger:              https://restaurante.midominio.com
    'SERVER_URL' => '',

    // --- Impuestos y propina (porcentajes) ---
    'IMPUESTO_NOMBRE' => 'Impoconsumo',
    'IMPUESTO_PCT' => 8,
    // Propina sugerida: es voluntaria, el comensal puede quitarla.
    'PROPINA_SUGERIDA_PCT' => 10,

    // true  = el comensal puede "Entrar sin QR" eligiendo su mesa en una lista
    //         (el pedido llega marcado "Sin QR" para que el mesero confirme).
    // false = solo se puede pedir escaneando el QR de la mesa.
    'PERMITIR_SIN_QR' => true,

    // --- Datos del restaurante (comprobante y tarjetas QR) ---
    'RESTAURANTE_NOMBRE' => 'Restaurante SENA',
    'RESTAURANTE_NIT' => '',
    'RESTAURANTE_DIRECCION' => '',

    // Zona horaria de los pedidos y reportes (Colombia: America/Bogota)
    'ZONA_HORARIA' => 'America/Bogota',
];
