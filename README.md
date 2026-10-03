# Restaurante SENA — Pedidos por código QR

Sistema web para tomar pedidos en un restaurante desde el celular del comensal.

1. El comensal **escanea el QR de su mesa** (o, si el restaurante lo permite, **elige su mesa en una lista** sin escanear), ve la carta, arma su pedido y lo envía.
2. La **cocina** ve los pedidos nuevos (con aviso sonoro), los prepara y los marca como *listos*.
3. El **mesero** ve los pedidos listos con su número de mesa, los lleva y los marca como *entregados*.
4. Se genera el **comprobante** (con QR de verificación) y la venta aparece en los **reportes**.

El **administrador** gestiona la carta, las categorías, las mesas y sus QR, el personal, los cupones, los reportes de ventas por día, semana y mes, y descarga los respaldos.

Está hecho en **PHP 8.2+ y MySQL/MariaDB**, sin librerías externas que instalar. Funciona en un hosting compartido (**Hostinger**) o en un computador con **XAMPP**.

> La versión anterior en Python/Flask quedó guardada en la etiqueta de git `version-flask`.

---

## Contenido

1. [Requisitos](#1-requisitos)
2. [Instalación en Hostinger](#2-instalación-en-hostinger)
3. [Instalación local en XAMPP](#3-instalación-local-en-xampp)
4. [Configuración (`api/config.local.php`)](#4-configuración-apiconfiglocalphp)
5. [Usuarios iniciales](#5-usuarios-iniciales)
6. [Imprimir los códigos QR de las mesas](#6-imprimir-los-códigos-qr-de-las-mesas)
7. [Uso diario](#7-uso-diario)
8. [Respaldo y restauración](#8-respaldo-y-restauración)
9. [Actualizar el sistema](#9-actualizar-el-sistema)
10. [Pruebas automáticas y Postman](#10-pruebas-automáticas-y-postman)
11. [Solución de problemas](#11-solución-de-problemas)
12. [Seguridad y limitaciones conocidas](#12-seguridad-y-limitaciones-conocidas)
13. [Estructura del proyecto](#13-estructura-del-proyecto)

---

## 1. Requisitos

| Componente | Versión | Notas |
|---|---|---|
| PHP | **8.2 o superior** | Extensiones `pdo_mysql`, `mbstring`, `zlib` (vienen activas en Hostinger y en XAMPP). |
| Base de datos | MariaDB 10.4+ o MySQL 8 | Probado en MariaDB 10.4.32 (XAMPP). |
| Servidor web | Apache o LiteSpeed con `.htaccess` | Hostinger usa LiteSpeed; XAMPP usa Apache. Ambos leen el `.htaccess` del proyecto. |
| Navegador | Chrome, Edge, Firefox o Safari recientes | En los celulares de los comensales y en las tabletas del personal. |

No hace falta Composer, Node ni Python para usar el sistema.

---

## 2. Instalación en Hostinger

Se instala en un **subdominio**, por ejemplo `https://restaurante.midominio.com`. Todo se hace desde **hPanel**.

### Paso 1 — Generar el paquete

En el computador donde está el proyecto (con XAMPP instalado):

```powershell
C:\xampp\php\php.exe scripts\generar_zip.php
```

Se crea **`restaurante_hostinger.zip`** en la carpeta del proyecto. Solo trae los archivos que van al servidor: las páginas, `css/`, `js/`, `api/` y los `.htaccess`. **No** trae contraseñas, ni `sql/`, ni las pruebas.

### Paso 2 — Crear el subdominio

1. hPanel → **Dominios → Subdominios**.
2. Escriba `restaurante` (o el nombre que prefiera) y pulse **Crear**.
3. Anote la **carpeta** que hPanel le asigna, por ejemplo `public_html/restaurante`.

### Paso 3 — Revisar la versión de PHP

hPanel → **Avanzado → Configuración de PHP** → elija **PHP 8.2** o superior → **Actualizar**.

### Paso 4 — Crear la base de datos y su usuario

1. hPanel → **Bases de datos → Bases de datos MySQL**.
2. En *Crear nueva base de datos MySQL y usuario* escriba un nombre de base (por ejemplo `restaurante`), un usuario (por ejemplo `restaurante`) y una **contraseña segura**. Guárdela en un lugar seguro: la va a necesitar en el paso 7.
3. Pulse **Crear**. Hostinger antepone un prefijo, así que los nombres quedan como `u123456789_restaurante`. **Anote el nombre completo de la base y del usuario** tal como aparecen en la lista.

### Paso 5 — Importar las tablas con phpMyAdmin

1. En la misma página, junto a la base, pulse **Entrar a phpMyAdmin**.
2. Verifique que a la izquierda esté seleccionada **su base** (`u123456789_restaurante`).
3. Pestaña **Importar** → **Seleccionar archivo** → elija **`sql/instalacion_hosting.sql`** del proyecto.
4. Deje el juego de caracteres en **utf-8** y pulse **Importar** (abajo).
5. Debe ver el mensaje verde *"La importación se ejecutó exitosamente"* y, a la izquierda, las tablas `categorias`, `mesas`, `pedidos`, `productos`, `usuarios`, etc.

> Use `instalacion_hosting.sql`, **no** `instalacion_local.sql`: el de hosting no intenta crear la base (en Hostinger no hay permiso para eso) y se importa sobre la base que acaba de crear. Impórtelo sobre una base **vacía**.

### Paso 6 — Subir y extraer el zip

1. hPanel → **Archivos → Administrador de archivos**.
2. Entre a la carpeta del subdominio (paso 2, por ejemplo `public_html/restaurante`). Si trae un `default.php` o `index.php` de muestra, bórrelo.
3. Pulse **Subir** (ícono de flecha hacia arriba) y elija `restaurante_hostinger.zip`.
4. Clic derecho sobre el zip → **Extraer** → deje la misma carpeta → **Extraer**.
5. Verifique que `index.html`, `.htaccess` y la carpeta `api` queden **directamente** dentro de la carpeta del subdominio (no dentro de otra subcarpeta). Luego puede borrar el zip.

> El `.htaccess` empieza con punto y el Administrador de archivos puede ocultarlo. Si no lo ve, active *Mostrar archivos ocultos* en los ajustes del administrador.

### Paso 7 — Crear `api/config.local.php`

Este archivo tiene la contraseña de la base y **solo existe en el servidor**.

1. En el Administrador de archivos entre a la carpeta `api`.
2. Clic derecho sobre **`config.example.php`** → **Copiar** → como destino escriba la misma carpeta `api` y luego **renombre la copia** a **`config.local.php`** (o cree un archivo nuevo con ese nombre y pegue el contenido de la plantilla).
3. Abra `config.local.php` (doble clic) y complete:

```php
'DB_HOST' => 'localhost',
'DB_PORT' => 3306,
'DB_NAME' => 'u123456789_restaurante',   // nombre completo del paso 4
'DB_USER' => 'u123456789_restaurante',   // usuario completo del paso 4
'DB_PASS' => 'la contraseña del paso 4',
'SERVER_URL' => 'https://restaurante.midominio.com',   // sin barra al final
```

4. Revise también `RESTAURANTE_NOMBRE`, `RESTAURANTE_NIT`, `RESTAURANTE_DIRECCION`, `IMPUESTO_PCT`, `PROPINA_SUGERIDA_PCT` y `PERMITIR_SIN_QR` (sección 4) y pulse **Guardar**.

### Paso 8 — Activar SSL (HTTPS)

1. hPanel → **Seguridad → SSL** → instale el certificado gratuito para el subdominio (puede tardar unos minutos).
2. Active **Forzar HTTPS** para el subdominio.

HTTPS es necesario: protege las contraseñas del personal, hace que la cookie de sesión viaje cifrada y permite usar la **cámara** en el botón *Entrar con QR*.

### Paso 9 — Comprobar

1. Abra `https://restaurante.midominio.com/api/status`. Debe responder `{"ok":true,"msg":"Conectado a la base de datos",...}`.
   - Si dice que no conecta, revise `DB_NAME`, `DB_USER` y `DB_PASS` (paso 7).
2. Abra `https://restaurante.midominio.com/api/config.local.php`. Debe responder **403** o **404** (el archivo está protegido). Si ve el contenido, el `.htaccess` no se subió: repita el paso 6.
3. Abra `https://restaurante.midominio.com/login.html`, entre con el usuario `admin` (sección 5) y cambie la contraseña temporal.
4. Haga lo mismo con `chef` y `mesero`, o desactívelos en *Personal* si no los va a usar.
5. Imprima los QR de las mesas (sección 6).

---

## 3. Instalación local en XAMPP

Sirve para probar el sistema en un computador o para usarlo en la **red local** del restaurante sin hosting.

### Paso 1 — XAMPP

1. Instale [XAMPP](https://www.apachefriends.org/es/) con PHP 8.2 o superior.
2. En el **XAMPP Control Panel** pulse **Start** en **Apache** y en **MySQL**.
3. Fíjese en el puerto que muestra MySQL (normalmente **3306**).

### Paso 2 — Crear la base de datos

**Opción A — phpMyAdmin:** abra `http://localhost/phpmyadmin` → pestaña **Importar** → elija **`sql/instalacion_local.sql`** → **Importar**.

**Opción B — consola** (PowerShell, en la carpeta del proyecto):

```powershell
Get-Content sql\instalacion_local.sql -Raw | C:\xampp\mysql\bin\mysql.exe -u root --default-character-set=utf8mb4
```

(Agregue `-P 3307` si su MySQL usa otro puerto.)

> ⚠ `instalacion_local.sql` **borra y vuelve a crear** la base `restaurante_sena`. Si ya tiene datos en una base con ese nombre, haga primero un respaldo (sección 8).

### Paso 3 — Copiar el sistema a htdocs

```powershell
C:\xampp\php\php.exe scripts\publicar_local.php
```

Copia los mismos archivos del zip de Hostinger a `C:\xampp\htdocs\restaurante` y, si no existe, crea `api\config.local.php` a partir de la plantilla. **Nunca** reemplaza un `config.local.php` que ya exista. Ejecútelo de nuevo cada vez que cambie algo en el proyecto.

### Paso 4 — Configurar

Abra `C:\xampp\htdocs\restaurante\api\config.local.php` y revise:

```php
'DB_HOST' => '127.0.0.1',
'DB_PORT' => 3306,            // el puerto de MySQL en XAMPP
'DB_NAME' => 'restaurante_sena',
'DB_USER' => 'root',
'DB_PASS' => '',
'SERVER_URL' => 'http://192.168.1.10/restaurante',   // IP de este computador (ver abajo)
```

### Paso 5 — Probar

- En el mismo computador: `http://localhost/restaurante` (comensal) y `http://localhost/restaurante/login.html` (personal).
- `http://localhost/restaurante/api/status` debe responder `"ok":true`.

### Usarlo desde los celulares (red local)

1. **IP fija.** Averigüe la IP del computador (`ipconfig` → *Dirección IPv4*) y, en el router, cree una **reserva DHCP** para ese computador. Si la IP cambia, **los QR impresos dejan de funcionar**. Ponga esa IP en `SERVER_URL`. El panel avisa en *Mesas y QR* si `SERVER_URL` es `localhost` o si la IP ya no coincide.
2. **Firewall.** Permita el puerto **80** (Apache) solo en redes privadas. En PowerShell como administrador:
   ```powershell
   New-NetFirewallRule -DisplayName "Restaurante SENA (Apache)" -Direction Inbound -Protocol TCP -LocalPort 80 -Action Allow -Profile Private
   ```
   La red Wi-Fi debe estar marcada como **Privada** en Windows. **No** abra el puerto de MySQL.
3. Desde un celular conectado al mismo Wi-Fi abra `SERVER_URL`: debe verse la página de bienvenida.
4. Para que arranque solo: XAMPP Control Panel → *Config* → marque **Apache** y **MySQL** en *Autostart of modules*. Detenga siempre MySQL desde XAMPP antes de apagar el equipo.

> En la red local el sistema funciona con **HTTP**. Ahí el navegador del celular **no permite usar la cámara dentro de la página**, así que *Entrar con QR* ofrece **Subir foto del QR**. Lo más simple es que el comensal escanee con la **cámara normal del celular**, que abre la carta directamente.

---

## 4. Configuración (`api/config.local.php`)

Se crea copiando `api/config.example.php`. **Nunca lo suba a git** (está en `.gitignore`) y el `.htaccess` impide abrirlo desde el navegador.

| Clave | Ejemplo | Qué hace |
|---|---|---|
| `DB_HOST` | `localhost` / `127.0.0.1` | Servidor de la base de datos. |
| `DB_PORT` | `3306` | Puerto de MySQL. |
| `DB_NAME` | `u123456789_restaurante` | Nombre de la base. |
| `DB_USER` | `u123456789_restaurante` | Usuario de la base. |
| `DB_PASS` | — | Contraseña de la base. |
| `SERVER_URL` | `https://restaurante.midominio.com` | Dirección pública, **sin barra final**. Va dentro de los QR de las mesas y de los comprobantes. |
| `IMPUESTO_NOMBRE` | `Impoconsumo` | Nombre que se muestra en la cuenta. |
| `IMPUESTO_PCT` | `8` | Porcentaje del impuesto al consumo. |
| `PROPINA_SUGERIDA_PCT` | `10` | Propina sugerida. Es **voluntaria**: el comensal puede quitarla antes de pedir. |
| `PERMITIR_SIN_QR` | `true` | `true`: la bienvenida muestra **Entrar sin QR** (elegir la mesa de una lista). `false`: se oculta el botón y la API rechaza pedidos sin el código de la mesa. |
| `RESTAURANTE_NOMBRE`, `RESTAURANTE_NIT`, `RESTAURANTE_DIRECCION` | — | Aparecen en el comprobante y en las tarjetas QR. |
| `ZONA_HORARIA` | `America/Bogota` | Hora de los pedidos y de los reportes. |

Los precios están en **pesos colombianos sin decimales**. Los cambios en este archivo se aplican de inmediato, sin reiniciar nada.

---

## 5. Usuarios iniciales

| Usuario | Contraseña temporal | Rol | Al ingresar va a |
|---|---|---|---|
| `admin` | `Admin-Temporal-2026` | Administrador | Panel de administración (`admin.html`) |
| `chef` | `Chef-Temporal-2026` | Chef | Cocina (`cocina.html`) |
| `mesero` | `Mesero-Temporal-2026` | Mesero | Meseros (`mesero.html`) |

- En el **primer ingreso** el sistema **obliga a cambiar la contraseña** (mínimo 8 caracteres, con letras y números, sin el nombre de usuario). Hágalo apenas instale, sobre todo en Hostinger, donde el sistema está en internet.
- Estas contraseñas temporales solo están en este documento; en la base se guarda únicamente su hash seguro.
- El administrador crea más personal en **Panel → Personal → Nuevo usuario**. El sistema genera una contraseña temporal que se muestra una sola vez. Desde ahí también se **restablecen** contraseñas olvidadas y se desactivan usuarios.
- Tras 5 intentos fallidos, la cuenta se bloquea 15 minutos desde ese equipo.

---

## 6. Imprimir los códigos QR de las mesas

Los QR se generan en el navegador; no hace falta internet ni ningún servicio externo.

1. Verifique que `SERVER_URL` sea la dirección definitiva (en Hostinger, la `https://` del subdominio).
2. Entre como administrador → **Mesas y QR**. Verá una tarjeta por mesa con su QR, número, capacidad, estado y la dirección a la que apunta. Si aparece un **aviso amarillo**, corrija `SERVER_URL` antes de imprimir.
3. Escanee un QR con un celular: debe abrir la carta con esa mesa.
4. **Imprimir todas**: abre una hoja con las tarjetas (nombre del restaurante, *Mesa N* en grande, el QR y *"Escanea para ver la carta y pedir"*). Opcionalmente escriba el nombre de la red Wi-Fi. Pulse **Imprimir** o elija *Guardar como PDF* para llevarlo a una papelería.
5. Por mesa también puede **Descargar PNG** o **Imprimir** solo esa tarjeta.

**Seguridad de los QR:** cada mesa tiene un código secreto dentro de su QR, así nadie puede pedir a nombre de otra mesa cambiando el número en la dirección. Si un QR se daña o alguien lo copia, use **Regenerar** en esa mesa: el QR anterior **deja de funcionar** y hay que imprimir el nuevo.

---

## 7. Uso diario

**Comensal** (desde su celular), en la página de bienvenida (`SERVER_URL`) hay dos botones:

- **Entrar con QR**: abre la cámara dentro de la página y lee el QR de la mesa. Si la cámara no está disponible o el comensal no da permiso, puede **subir una foto del QR** o usar **Entrar sin QR**. También puede escanear directamente con la cámara normal del celular.
- **Entrar sin QR** (si `PERMITIR_SIN_QR` es `true`): elige su mesa en la lista de mesas activas. Estos pedidos llegan a cocina y meseros marcados **"Sin QR"** para que el personal confirme la mesa al entregar.

Luego ve la carta → agrega platos → en el carrito puede escribir notas, aplicar un **cupón** y **quitar la propina** → *Confirmar pedido*. Ve el estado de su pedido en tiempo real, puede pulsar **Llamar mesero** y ver su **comprobante**.

**Cocina** (`cocina.html`, ideal en una tableta):

- Al abrir, pulse **Activar sonido** (los navegadores no permiten sonar sin un toque previo).
- Pedidos *Pendientes* y *En preparación*, del más antiguo al más nuevo, con las notas resaltadas. La tarjeta se pone amarilla a los 15 min y roja a los 25.
- **Empezar** → **Listo**. *Cancelar* pide confirmación.

**Meseros** (`mesero.html`):

- Pulse **Activar sonido** al iniciar.
- **Pedidos listos** con el número de mesa → **Entregado** (se genera el comprobante y la mesa queda libre).
- **Mesas que llaman** → **Atendido**.

**Administrador** (`admin.html`):

- **Dashboard** del día; **Pedidos** con filtros, detalle, cambio de estado y **método de pago**.
- **Carta** (productos, precios, disponible/agotado), **Categorías**, **Mesas y QR**, **Personal** y **Cupones**.
- **Reportes** por **día, semana o mes**, con productos más vendidos, categorías, métodos de pago, propinas e impuesto; botón **Descargar Excel (CSV)**.
- **Respaldo** → **Descargar respaldo** (sección 8).

---

## 8. Respaldo y restauración

### Descargar un respaldo (Hostinger y XAMPP)

Panel → **Respaldo** → **Descargar respaldo**. Baja un archivo `restaurante_sena_AAAAMMDD_HHMMSS.sql.gz` con toda la base. Hágalo al menos **una vez por semana** y guárdelo fuera del servidor (Google Drive, OneDrive o una memoria USB).

Hostinger también hace respaldos automáticos según su plan: hPanel → **Archivos → Copias de seguridad**.

### Respaldo desde la consola (XAMPP)

```powershell
C:\xampp\php\php.exe scripts\respaldo.php
C:\xampp\php\php.exe scripts\respaldo.php --dias=60 --dir=D:\Respaldos
```

Guarda el respaldo en `respaldos\` y borra los de más de 30 días (configurable con `--dias`). No necesita `mysqldump`. Para que sea diario, créelo en el **Programador de tareas** de Windows: *Crear tarea básica* → *Diariamente* → programa `C:\xampp\php\php.exe`, argumentos `scripts\respaldo.php`, *Iniciar en* la carpeta del proyecto.

### Restaurar

**En Hostinger:** hPanel → phpMyAdmin → seleccione la base → **Importar** → elija el `.sql.gz` → **Importar**. ⚠ Reemplaza las tablas actuales por las del respaldo.

**En XAMPP:**

```powershell
C:\xampp\php\php.exe scripts\restaurar.php                       # el respaldo más reciente
C:\xampp\php\php.exe scripts\restaurar.php respaldos\restaurante_sena_20261003_233000.sql.gz
C:\xampp\php\php.exe scripts\restaurar.php --bd=restaurante_revision ARCHIVO.sql.gz   # revisar sin tocar la base real
```

Pide escribir el nombre de la base para confirmar y, antes de restaurar, hace un respaldo de seguridad del estado actual.

Un respaldo de XAMPP se puede restaurar en Hostinger y al revés: el archivo no lleva el nombre de la base.

---

## 9. Actualizar el sistema

1. **Descargue un respaldo** (sección 8).
2. Genere un zip nuevo (`scripts\generar_zip.php`), súbalo y extráigalo encima, aceptando reemplazar los archivos. **El zip no trae `config.local.php`**, así que su configuración se conserva.
3. En XAMPP basta con ejecutar otra vez `scripts\publicar_local.php`.

**Si viene de la versión Flask:** la base de datos es la misma, sirve tal cual. Las contraseñas que estaban en formato *pbkdf2* o *SHA-256* siguen funcionando y se convierten solas al formato nuevo al ingresar. Las que estaban en formato *scrypt* no se pueden leer desde PHP: el administrador debe **restablecerlas** en *Personal*.

---

## 10. Pruebas automáticas y Postman

### Pruebas de la API

```powershell
C:\xampp\php\php.exe tests\probar_api.php
C:\xampp\php\php.exe tests\probar_api.php --apache        # además prueba el Apache de XAMPP (http://localhost/restaurante)
C:\xampp\php\php.exe tests\probar_api.php --solo=pedidos  # solo un grupo
```

Usan una base **aparte** (`restaurante_sena_test`) que se crea en cada prueba; **nunca tocan la base real**. Necesitan MySQL encendido y toman la conexión de `api/config.local.php` del proyecto. Cubren todos los endpoints, los permisos (sin sesión → 401, rol incorrecto → 403), el dinero, la validación, los QR, *Entrar sin QR* con `PERMITIR_SIN_QR` activado y desactivado, los reportes, el respaldo y las reglas del `.htaccess`. Se espera **94 pasaron** con `--apache` (unos 2 minutos).

### Postman

En `tests/` están la colección `restaurante_sena.postman_collection.json` y dos environments: **XAMPP** (`http://localhost/restaurante`) y **Hostinger** (`https://restaurante.midominio.com`, cámbielo por su subdominio).

1. Importe la colección y el environment en Postman.
2. En el environment escriba las contraseñas **ya cambiadas** de `admin`, `chef` y `mesero` (con la temporal, la API responde *debe cambiar la contraseña*).
3. Ejecute la colección completa con el **Runner**, en orden. Recorre el flujo real: carta → pedido → cocina → mesero → pago → comprobante → panel → reportes → respaldo → seguridad.

⚠ La colección **crea un pedido real** en la mesa 5 (y lo entrega). Úsela en Hostinger solo antes de abrir el restaurante, o anule ese pedido después.

---

## 11. Solución de problemas

| Problema | Solución |
|---|---|
| `api/status` dice que **no conecta a la base** | Revise `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER` y `DB_PASS` en `api/config.local.php`. En Hostinger los nombres llevan el prefijo `u123456789_`. |
| `api/status` da **404** o **500** | El `.htaccess` de la raíz o de `api/` no está (active *Mostrar archivos ocultos* y súbalo) o la versión de PHP es menor que 8.2. |
| Error de importación en phpMyAdmin | En Hostinger use `sql/instalacion_hosting.sql` (no el local) y una base vacía. |
| Las tildes se ven mal (`Ã³`) | La base se importó con otro juego de caracteres. Vuelva a importar eligiendo **utf-8**. |
| El celular **no abre** la página (XAMPP) | Mismo Wi-Fi, red de Windows *Privada*, puerto 80 permitido en el firewall (sección 3). |
| El QR abre una dirección que **no carga** | `SERVER_URL` está mal o la IP del computador cambió. El panel lo avisa en *Mesas y QR*. Corríjalo e imprima de nuevo. |
| "**Código QR no válido**" | El QR se regeneró o es de otra instalación. Imprima el QR actual de esa mesa. |
| "**La mesa no está habilitada**" | La mesa está *inactiva*. Cámbiela en *Mesas y QR*. |
| *Entrar con QR* dice que la cámara **no está disponible** | La cámara en la página exige HTTPS (sección 2, paso 8) y permiso del navegador. Mientras tanto use *Subir foto del QR*, la cámara normal del celular o *Entrar sin QR*. |
| La sesión del personal **se cierra sola** en Hostinger | Verifique que entra siempre por la misma dirección (`https://`, con o sin `www`, pero siempre igual). |
| La cocina **no suena** | Pulse **Activar sonido** al abrir la pantalla y suba el volumen. |
| "Demasiados intentos fallidos" | Espere 15 minutos o pida al administrador que restablezca la contraseña (eso desbloquea). |
| **Olvidé la contraseña del administrador** | Si hay otro administrador, que la restablezca en *Personal*. Si no, en phpMyAdmin → pestaña **SQL** ejecute: `UPDATE usuarios SET contrasena_hash = SHA2('Temporal-Nueva-2026', 256), debe_cambiar_clave = 1 WHERE usuario = 'admin';` y entre con `Temporal-Nueva-2026`. El sistema le pedirá cambiarla y la guardará en formato seguro. |
| El CSV se ve en una sola columna en Excel | Ábralo con *Datos → Desde texto/CSV* y elija el separador **punto y coma**. |
| MySQL de XAMPP **no arranca** | Revise `C:\xampp\mysql\data\mysql_error.log`. Si dice *"marked as crashed"*, una tabla se dañó (pasa al apagar el equipo sin detener MySQL). Copie `C:\xampp\mysql\data` y pida ayuda técnica. |

---

## 12. Seguridad y limitaciones conocidas

**Medidas incluidas:**

- Contraseñas con `password_hash` (bcrypt) y cambio obligatorio de la temporal; las de versiones anteriores se convierten solas al ingresar.
- Sesión PHP guardada en la base, con cookie `HttpOnly`, `SameSite=Lax` y `Secure` cuando se entra por HTTPS.
- Permisos por rol en el servidor: sin sesión → 401, rol incorrecto → 403. El chef no puede entregar, el mesero no puede cocinar y solo el administrador gestiona.
- Precios y totales calculados **siempre en el servidor**, dentro de transacciones; consultas SQL preparadas; validación de todos los datos.
- Código secreto por mesa en el QR. El comensal consulta su pedido y su comprobante con un token aleatorio, no con un número consecutivo.
- Protección contra CSRF (se revisa el origen de cada petición) y XSS; límite de intentos de ingreso, de pedidos y de llamados por dispositivo.
- El `.htaccess` bloquea `config.local.php`, las carpetas `sql/`, `tests/`, `scripts/` y `api/lib/`, y los archivos `.sql`, `.md`, `.zip`, etc.
- **Entrar sin QR** es una comodidad con un costo: cualquiera que abra la página puede pedir a nombre de cualquier mesa. Por eso esos pedidos llegan marcados *Sin QR*. Si se presentan pedidos falsos, ponga `PERMITIR_SIN_QR` en `false`.

**Limitaciones:**

- El **comprobante no es una factura electrónica DIAN**; así lo indica en pantalla. Si el restaurante está obligado a facturar electrónicamente, debe hacerlo con su proveedor de facturación.
- La cámara dentro de la página solo funciona con **HTTPS** (o en `localhost`).
- Las contraseñas en formato *scrypt* de la versión Flask deben restablecerse.
- Probado en XAMPP (PHP 8.2.12, MariaDB 10.4.32, Apache) en Windows 11. El código es compatible con MySQL 8 y con LiteSpeed (Hostinger), pero en esos entornos no se probó durante el desarrollo.
- Los avisos sonoros requieren tocar **Activar sonido** cada vez que se abre la pantalla (restricción de los navegadores).
- Las fuentes y los íconos se cargan de internet; sin conexión se ven con la tipografía del sistema, pero todo sigue funcionando.

---

## 13. Estructura del proyecto

```
restaurante_sena/
├── index.html, mesas.html, menu.html, pedido.html, factura.html, verificar.html   ← comensal
├── login.html, admin.html, cocina.html, mesero.html, qr-mesas.html              ← personal
├── .htaccess              reglas del servidor (bloqueos, cabeceras de seguridad)
├── css/                   styles.css, personal.css
├── js/
│   ├── api.js, main.js, cliente.js, admin.js, personal.js
│   ├── lector-qr.js       lectura de QR con la cámara (Entrar con QR)
│   ├── qr.js              generación de QR (mesas y comprobante)
│   └── vendor/            jsQR (Apache 2.0) y qrcode-generator (MIT), con sus licencias
├── api/
│   ├── index.php          punto de entrada de la API (todas las rutas /api/...)
│   ├── .htaccess          envía /api/... a index.php y bloquea lo demás
│   ├── config.php         lee config.local.php
│   ├── config.example.php plantilla de configuración
│   ├── config.local.php   (se crea en cada servidor; no va a git)
│   ├── lib/               base de datos, seguridad, validación, dinero, respaldo
│   └── rutas/             público, autenticación, mesas, pedidos, administración, reportes, respaldo
├── sql/
│   ├── instalacion_local.sql     XAMPP (crea la base restaurante_sena)
│   └── instalacion_hosting.sql   Hostinger (se importa sobre una base ya creada)
├── scripts/
│   ├── generar_zip.php           arma restaurante_hostinger.zip
│   ├── publicar_local.php        copia el sistema a C:\xampp\htdocs\restaurante
│   ├── respaldo.php, restaurar.php
│   ├── archivos_publicos.php     lista de archivos que van al servidor
│   └── generar_sql_hosting.php   genera instalacion_hosting.sql a partir del local
├── tests/                 probar_api.php, pruebas/, colección y environments de Postman
└── respaldos/             (se crea sola; no va a git)
```

---

Proyecto formativo **SENA** — Análisis y Desarrollo de Software (GA7-220501096-AA2-EV02).
