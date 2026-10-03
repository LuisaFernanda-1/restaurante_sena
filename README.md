# Restaurante SENA — Pedidos por código QR

Sistema web para tomar pedidos en un restaurante desde el celular del comensal.

1. El comensal **escanea el QR de su mesa**, ve la carta, arma su pedido y lo envía.
2. La **cocina** ve los pedidos nuevos (con aviso sonoro), los prepara y los marca como *listos*.
3. El **mesero** ve los pedidos listos con su número de mesa, los lleva y los marca como *entregados*.
4. Se genera el **comprobante** (con QR de verificación) y la venta aparece en los **reportes**.

El **administrador** gestiona la carta, las categorías, las mesas y sus QR, el personal, los cupones y los reportes de ventas por día, semana y mes.

Todo funciona en la red local del restaurante: un computador con Windows hace de servidor y los celulares se conectan por Wi-Fi.

---

## Contenido

1. [Requisitos](#1-requisitos)
2. [Instalación en XAMPP paso a paso](#2-instalación-en-xampp-paso-a-paso)
3. [Configuración (`backend/.env`)](#3-configuración-backendenv)
4. [Usuarios iniciales](#4-usuarios-iniciales)
5. [Iniciar el sistema](#5-iniciar-el-sistema)
6. [IP fija del servidor (¡importante!)](#6-ip-fija-del-servidor-importante)
7. [Abrir el puerto en el firewall de Windows](#7-abrir-el-puerto-en-el-firewall-de-windows)
8. [Imprimir los códigos QR de las mesas](#8-imprimir-los-códigos-qr-de-las-mesas)
9. [Uso diario](#9-uso-diario)
10. [Respaldo y restauración](#10-respaldo-y-restauración)
11. [Actualizar desde la versión anterior](#11-actualizar-desde-la-versión-anterior)
12. [Pruebas automáticas](#12-pruebas-automáticas)
13. [Solución de problemas](#13-solución-de-problemas)
14. [Seguridad y limitaciones conocidas](#14-seguridad-y-limitaciones-conocidas)
15. [Estructura del proyecto](#15-estructura-del-proyecto)

---

## 1. Requisitos

| Componente | Versión | Notas |
|---|---|---|
| Windows | 10 u 11 | Computador que hará de servidor (debe quedar encendido durante el servicio). |
| [XAMPP](https://www.apachefriends.org/es/) | con MariaDB 10.4 o superior | Solo se usa **MySQL/MariaDB** (no hace falta Apache). También funciona con MySQL 8. |
| [Python](https://www.python.org/downloads/) | **3.12 o superior** | Al instalarlo marque **"Add python.exe to PATH"**. |
| Red Wi-Fi | — | El servidor y los celulares deben estar en la misma red. |
| Navegador | Chrome, Edge, Firefox o Safari recientes | En los celulares de los comensales y en las tabletas del personal. |

Se necesita internet solo durante la instalación (para descargar las librerías de Python). Durante el servicio el sistema funciona en la red local. Las fuentes y los íconos se cargan de internet y, si no hay conexión, se ven con la tipografía del sistema, pero todo sigue funcionando.

---

## 2. Instalación en XAMPP paso a paso

### Paso 1 — Instalar XAMPP y encender MySQL

1. Instale XAMPP (por ejemplo en `C:\xampp`).
2. Abra el **XAMPP Control Panel** y pulse **Start** en la fila **MySQL**. Debe quedar en verde.
3. Revise el puerto de MySQL que muestra el panel (normalmente **3306**; algunos equipos usan 3307).

### Paso 2 — Copiar el proyecto

Copie la carpeta del proyecto a una ubicación fija, por ejemplo `C:\RestauranteSENA`.

### Paso 3 — Instalación automática (recomendada)

Abra **PowerShell** en la carpeta del proyecto (en el Explorador: *Archivo → Abrir Windows PowerShell*) y ejecute:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\instalar.ps1
```

El instalador hace lo siguiente:

- Verifica que haya Python 3.12 o superior.
- Crea el entorno virtual `backend\.venv` e instala las dependencias de `backend\requirements.txt`.
- Crea `backend\.env` con una `SECRET_KEY` aleatoria, el **puerto de MySQL de XAMPP** y la **IP de este computador**.
- Crea la base de datos **solo si no existe**. Nunca borra datos.

Al terminar, revise el archivo `backend\.env` (sección 3), sobre todo `SERVER_URL` y, si su MySQL tiene contraseña, `DB_PASSWORD`.

### Paso 3 (alternativo) — Instalación manual

```powershell
cd C:\RestauranteSENA\backend
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env        # y luego edite .env (sección 3)
```

Para crear la base de datos, elija una de estas opciones:

- **phpMyAdmin**: abra `http://localhost/phpmyadmin` (requiere Apache encendido) → **Importar** → elija `backend\restaurante_sena_completo.sql` → **Continuar**.
- **Consola de XAMPP** (botón *Shell* del panel):
  ```
  mysql -u root -p --default-character-set=utf8mb4 < C:\RestauranteSENA\backend\restaurante_sena_completo.sql
  ```
  Si su MySQL usa el puerto 3307, agregue `-P 3307 -h 127.0.0.1`.

> ⚠️ `restaurante_sena_completo.sql` **borra y vuelve a crear** la base `restaurante_sena`. Úselo solo en una instalación nueva. Para actualizar una base que ya tiene datos, vea la sección 11.

### Paso 4 — Iniciar y probar

Haga doble clic en **`scripts\iniciar_servidor.bat`** y abra en el navegador `http://localhost:8000`. Luego siga las secciones 6, 7 y 8 para que los celulares puedan entrar.

### (Recomendado) Usuario de MySQL propio para el sistema

XAMPP trae el usuario `root` **sin contraseña**. Para un restaurante en funcionamiento, cree un usuario solo para el sistema. Desde la consola de XAMPP (`mysql -u root -p`, con `-P 3307 -h 127.0.0.1` si aplica):

```sql
CREATE USER 'restaurante'@'localhost' IDENTIFIED BY 'una-contraseña-larga-y-segura';
GRANT ALL PRIVILEGES ON restaurante_sena.* TO 'restaurante'@'localhost';
FLUSH PRIVILEGES;
```

Luego ponga en `backend\.env` `DB_USER=restaurante` y `DB_PASSWORD=...`. Ese usuario solo puede usar la base del restaurante; el respaldo funciona con él. Si su servidor tiene activada la opción `skip-name-resolve`, cree el usuario también para `'127.0.0.1'`.

---

## 3. Configuración (`backend/.env`)

Todas las claves y datos del restaurante están en `backend\.env`. **Este archivo nunca se sube a git**: está en `.gitignore`. La plantilla es `backend\.env.example`.

| Variable | Ejemplo | Qué es |
|---|---|---|
| `DB_HOST` | `127.0.0.1` | Servidor de MySQL (el mismo computador). |
| `DB_PORT` | `3306` | Puerto de MySQL (el que muestra XAMPP). |
| `DB_USER` | `root` | Usuario de MySQL. |
| `DB_PASSWORD` | *(vacío en XAMPP)* | Contraseña de MySQL. |
| `DB_NAME` | `restaurante_sena` | Nombre de la base de datos. |
| `SECRET_KEY` | *64 caracteres aleatorios* | Firma las sesiones del personal. Genere una con `python -c "import secrets; print(secrets.token_hex(32))"`. Si la cambia, todo el personal debe volver a iniciar sesión. |
| `SERVER_URL` | `http://192.168.1.10:8000` | **Dirección con la que los celulares abren el sistema.** Va dentro de los QR. Use la IP fija del servidor (sección 6). |
| `COOKIE_SEGURA` | `0` | Ponga `1` solo si publica el sistema con HTTPS. |
| `IMPUESTO_NOMBRE` | `Impoconsumo` | Nombre del impuesto en la factura. |
| `IMPUESTO_PCT` | `8` | Porcentaje del impuesto (impoconsumo de restaurantes: 8 %). |
| `PROPINA_SUGERIDA_PCT` | `10` | Propina sugerida. **Es voluntaria**: el comensal puede quitarla antes de confirmar. |
| `RESTAURANTE_NOMBRE` | `Restaurante SENA` | Aparece en los comprobantes y en las tarjetas QR. |
| `RESTAURANTE_NIT` | `900.123.456-7` | Aparece en el comprobante. |
| `RESTAURANTE_DIRECCION` | `Calle 1 # 2-3, Bogotá` | Aparece en el comprobante. |

**Cómo se calcula la cuenta** (en el servidor, en pesos enteros):

```
base      = subtotal − descuento del cupón
impuesto  = base × IMPUESTO_PCT
propina   = base × PROPINA_SUGERIDA_PCT   (solo si el comensal la deja)
total     = base + impuesto + propina
```

Confirme los porcentajes con el contador del restaurante. Después de cambiar `.env`, **reinicie el servidor**.

---

## 4. Usuarios iniciales

| Usuario | Contraseña temporal | Rol | Al ingresar va a |
|---|---|---|---|
| `admin` | `Admin-Temporal-2026` | Administrador | Panel de administración (`admin.html`) |
| `chef` | `Chef-Temporal-2026` | Chef | Cocina (`cocina.html`) |
| `mesero` | `Mesero-Temporal-2026` | Mesero | Meseros (`mesero.html`) |

- En el **primer ingreso**, el sistema **obliga a cambiar la contraseña** (mínimo 8 caracteres, con letras y números, sin el nombre de usuario).
- Estas contraseñas temporales solo están en este documento; en la base de datos se guarda únicamente su hash seguro.
- El administrador crea más personal en **Panel → Personal → Nuevo usuario**. El sistema genera una contraseña temporal que se muestra una sola vez y que la persona debe cambiar al ingresar. Desde ahí también se **restablecen** contraseñas olvidadas y se desactivan usuarios.
- Por seguridad, tras 5 intentos fallidos la cuenta se bloquea 15 minutos desde ese equipo.

---

## 5. Iniciar el sistema

- **Doble clic en `scripts\iniciar_servidor.bat`** (o `powershell -ExecutionPolicy Bypass -File scripts\iniciar_servidor.ps1`).
- El script verifica que MySQL esté encendido y arranca el servidor de producción **Waitress** en `0.0.0.0:8000`. La ventana muestra las direcciones:
  - En el servidor: `http://localhost:8000`
  - Desde los celulares: el valor de `SERVER_URL`
  - Personal: `SERVER_URL/login.html`
- **Deje la ventana abierta** durante el servicio; cerrarla detiene el sistema.
- El registro de actividad se guarda en `logs\servidor.log` (un archivo por día; se conservan 30 días).

**Arranque automático al encender el computador** (opcional):

1. En XAMPP Control Panel → *Config* → marque **MySQL** en *Autostart of modules*. Esto requiere abrir XAMPP como administrador; también puede instalar MySQL como servicio con el botón ✖ que aparece junto a *MySQL*.
2. Pulse `Win + R`, escriba `shell:startup` y cree ahí un **acceso directo** a `scripts\iniciar_servidor.bat`.

---

## 6. IP fija del servidor (¡importante!)

Los QR de las mesas contienen la dirección `SERVER_URL`, por ejemplo `http://192.168.1.10:8000`. Si el router le asigna **otra IP** al servidor, **todos los QR impresos dejan de funcionar**.

1. Averigüe la IP del servidor: en PowerShell, `ipconfig` → *Dirección IPv4* del adaptador Wi-Fi o Ethernet.
2. En la configuración del router, cree una **reserva DHCP** (o "IP estática / DHCP binding") para la tarjeta de red del servidor con esa IP. Si no sabe hacerlo, pídalo al técnico o al proveedor de internet.
3. Ponga esa IP en `backend\.env`, en `SERVER_URL=http://ESA_IP:8000`, y reinicie el servidor.

El panel **avisa** en *Mesas y QR* y en la página de impresión si `SERVER_URL` es `localhost` o si usa una IP que el servidor ya no tiene.

> Los celulares de los comensales deben estar conectados a la **misma red Wi-Fi** del restaurante. Puede escribir el nombre de la red en las tarjetas QR (sección 8).

---

## 7. Abrir el puerto en el firewall de Windows

Para que los celulares lleguen al servidor hay que permitir el puerto **8000** (y solo ese; **no** abra el 3306 de MySQL).

**Opción A — PowerShell como administrador** (clic derecho en Inicio → *Terminal (Administrador)*):

```powershell
New-NetFirewallRule -DisplayName "Restaurante SENA (puerto 8000)" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow -Profile Private
```

La red del restaurante debe estar marcada como **Privada**: *Configuración → Red e Internet → Wi-Fi (o Ethernet) → Propiedades → Tipo de perfil de red: Privada*. Por seguridad la regla no se aplica a redes públicas.

**Opción B — Ventanas de Windows:**

1. Inicio → escriba **"Firewall de Windows Defender con seguridad avanzada"**.
2. **Reglas de entrada** → **Nueva regla…**
3. Tipo **Puerto** → **TCP**, puertos locales específicos **8000** → **Permitir la conexión**.
4. Marque solo **Privado** → Nombre: *Restaurante SENA (puerto 8000)* → **Finalizar**.

**Comprobar:** desde un celular conectado al Wi-Fi abra `SERVER_URL` (por ejemplo `http://192.168.1.10:8000`); debe verse la página de inicio.

---

## 8. Imprimir los códigos QR de las mesas

1. Verifique que `SERVER_URL` tenga la **IP fija** del servidor (sección 6) y que un celular pueda abrirla (sección 7).
2. Entre como administrador → **Mesas y QR**. Si aparece un aviso amarillo, corrija `SERVER_URL` antes de imprimir.
3. Pruebe un QR: pulse **QR** en una mesa y escanéelo con un celular. Debe abrir la carta con esa mesa.
4. Pulse **Imprimir tarjetas QR**. En la página que se abre:
   - escriba (opcional) el **nombre de la red Wi-Fi** del restaurante;
   - marque *Incluir mesas inactivas* si también quiere esas;
   - pulse **Imprimir** (6 tarjetas por hoja carta o A4). Puede elegir "Guardar como PDF" para llevarlo a una papelería.
5. Recorte por la línea punteada y ponga cada tarjeta en su mesa (idealmente plastificada).

**Seguridad de los QR:** cada mesa tiene un código secreto dentro de su QR, así nadie puede pedir a nombre de otra mesa cambiando el número en la dirección. Si un QR se daña o alguien lo copia, use **QR → Regenerar** en esa mesa: el QR anterior deja de funcionar y se imprime el nuevo. Cada mesa nueva recibe su QR automáticamente. También puede **Descargar PNG** de un QR suelto.

---

## 9. Uso diario

**Comensal** (desde su celular):

- Escanea el QR → ve la carta → agrega platos → en el carrito puede escribir notas, aplicar un **cupón** y **quitar la propina** si lo desea → *Confirmar pedido*.
- Ve el estado de su pedido en tiempo real (se actualiza cada 10 s), puede pulsar **Llamar mesero** y ver su **comprobante**.

**Cocina** (`cocina.html`, ideal en una tableta):

- Al abrir, pulse **Activar sonido**: los navegadores no permiten sonar sin un toque previo. Hágalo al iniciar cada turno.
- Pedidos *Pendientes* y *En preparación*, del más antiguo al más nuevo, con notas resaltadas. La tarjeta se pone amarilla a los 15 min y roja a los 25.
- **Empezar** → **Listo**. *Cancelar* pide confirmación.

**Meseros** (`mesero.html`, en el celular del mesero):

- Pulse **Activar sonido** al iniciar.
- **Pedidos listos** con el número de mesa → **Entregado** (se genera el comprobante y la mesa queda libre).
- **Mesas que llaman** → **Atendido**.

**Administrador** (`admin.html`):

- **Dashboard** del día.
- **Pedidos**: con filtros; ver detalle, cambiar estado, cancelar y registrar el **método de pago**.
- **Carta**: productos, precios y el interruptor **disponible/agotado**. Al eliminar un producto sale de la carta, pero sus ventas se conservan.
- **Categorías**, **Mesas y QR**, **Personal** y **Cupones** (porcentaje, vencimiento y usos).
- **Reportes**: ventas por **día, semana o mes** con rango de fechas, ticket promedio, propinas, impuesto, productos más vendidos, categorías y métodos de pago. El botón **Descargar Excel (CSV)** baja el mismo reporte.

---

## 10. Respaldo y restauración

Los respaldos se guardan comprimidos en la carpeta `respaldos\` con el nombre `restaurante_sena_AAAAMMDD_HHMMSS.sql.gz`. **Se borran automáticamente los de más de 30 días.**

### Respaldo manual

Doble clic en **`scripts\respaldo_manual.bat`**, o:

```powershell
backend\.venv\Scripts\python.exe scripts\respaldo.py
backend\.venv\Scripts\python.exe scripts\respaldo.py --dias 60 --dir D:\Respaldos   # otra carpeta y retención
```

### Respaldo automático diario

Ejecute **una sola vez**, en PowerShell como administrador:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\programar_respaldo.ps1            # todos los días a las 23:30
powershell -ExecutionPolicy Bypass -File scripts\programar_respaldo.ps1 -Hora 22:00
```

La tarea queda en el **Programador de tareas** de Windows como *"Restaurante SENA - Respaldo diario"*. MySQL debe estar encendido a esa hora. El resultado de cada respaldo queda en `logs\respaldo.log`.

> **Copie los respaldos fuera del computador** (una memoria USB o una carpeta de Google Drive/OneDrive) al menos una vez por semana. Si el disco se daña, los respaldos guardados en el mismo equipo se pierden con él.

### Restaurar un respaldo

1. Detenga el servidor (cierre su ventana).
2. Ejecute:
   ```powershell
   backend\.venv\Scripts\python.exe scripts\restaurar.py                                    # el más reciente
   backend\.venv\Scripts\python.exe scripts\restaurar.py respaldos\restaurante_sena_20261003_233000.sql.gz
   ```
3. Escriba el nombre de la base para confirmar. **Antes de restaurar**, el script hace un respaldo de seguridad del estado actual.
4. Inicie el servidor de nuevo.

Para **revisar un respaldo sin tocar la base real**, restáurelo en otra base:

```powershell
backend\.venv\Scripts\python.exe scripts\restaurar.py --bd restaurante_sena_revision ARCHIVO.sql.gz
```

---

## 11. Actualizar desde la versión anterior

Si ya tenía una base `restaurante_sena` de la versión anterior del proyecto, **no** importe `restaurante_sena_completo.sql`, porque borraría los datos. En su lugar:

1. Haga un respaldo (sección 10).
2. Ejecute la migración, que agrega lo que falta sin borrar nada y se puede repetir sin problema:
   ```powershell
   backend\.venv\Scripts\python.exe backend\migrar.py
   ```
3. Después de migrar:
   - Los usuarios existentes conservan su contraseña, que se convierte a un formato seguro al ingresar. Se les pedirá cambiarla. Su nombre de usuario es la parte del correo antes de la `@` (por ejemplo `admin@sena.edu.co` → `admin`).
   - Las mesas reciben **códigos QR nuevos**: imprima los QR otra vez (sección 8).
   - Las facturas antiguas conservan sus valores originales (IVA 19 %) y quedan marcadas así.

---

## 12. Pruebas automáticas

Las pruebas usan una base **aparte** (`restaurante_sena_test`), que se crea y se borra sola. **Nunca tocan la base real.** Necesitan MySQL encendido.

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest
```

Cubren todos los endpoints, los permisos (sin sesión → 401, rol incorrecto → 403), los cálculos de dinero, la validación de datos, los QR, los reportes, la migración desde la versión anterior, y el respaldo y la restauración. Se espera `210 passed` (unos 2 minutos).

---

## 13. Solución de problemas

| Problema | Solución |
|---|---|
| `iniciar_servidor` dice que **MySQL no responde** | Encienda MySQL en el panel de XAMPP. Revise `DB_PORT` en `.env`. |
| MySQL de XAMPP **no arranca** o se cierra solo | Revise `C:\xampp\mysql\data\mysql_error.log`. Si dice *"marked as crashed"* o *"wrong checksum"*, alguna tabla del sistema se dañó (suele pasar tras apagar el equipo sin detener MySQL). Haga una copia de `C:\xampp\mysql\data` y pida ayuda técnica para repararla. Siempre detenga MySQL desde XAMPP antes de apagar el equipo. |
| El celular **no abre** la página | El celular debe estar en el mismo Wi-Fi. Revise el firewall (sección 7) y que la red de Windows sea *Privada*. Pruebe abrir `SERVER_URL` en el navegador del celular. |
| El QR abre una dirección que **no carga** | La IP del servidor cambió o `SERVER_URL` es `localhost`. El panel lo avisa en *Mesas y QR*. Corrija `.env` y fije la IP (sección 6). |
| "**Código QR no válido**" al escanear | El QR fue regenerado o es de otra instalación. Imprima el QR actual de esa mesa. |
| "**La mesa no está habilitada**" | La mesa está *inactiva*. Cámbiela en *Mesas y QR*. |
| La cocina **no suena** | Pulse **Activar sonido** al abrir la pantalla y suba el volumen de la tableta. |
| Olvidé la contraseña del administrador | Otro administrador puede restablecerla en *Personal*. Si no hay otro, pida a soporte técnico que ejecute, desde la carpeta `backend`: `.\.venv\Scripts\python.exe -c "import db, seguridad; db.ejecutar('UPDATE usuarios SET contrasena_hash=%s, debe_cambiar_clave=1 WHERE usuario=%s', (seguridad.crear_hash('Temporal-Nueva-2026'), 'admin'))"` y entre con `Temporal-Nueva-2026`. |
| "Demasiados intentos fallidos" | Espere 15 minutos, o pida al administrador que restablezca la contraseña (eso desbloquea). |
| Las tildes se ven mal (`Ã³`) | La base se importó sin `utf8mb4`. Vuelva a importar con `--default-character-set=utf8mb4`, o use `instalar.ps1`. |
| El CSV se ve en una sola columna en Excel | Ábralo con *Datos → Desde texto/CSV* y elija el separador **punto y coma**. |

---

## 14. Seguridad y limitaciones conocidas

**Medidas incluidas:**

- Contraseñas con hash seguro (werkzeug/scrypt) y cambio obligatorio de la temporal.
- Permisos por rol en el servidor: sin sesión → 401, rol incorrecto → 403. El chef no puede entregar, el mesero no puede cocinar, solo el administrador gestiona.
- Precios y totales calculados **siempre en el servidor**; consultas SQL parametrizadas; validación de todos los datos.
- Código secreto por mesa en el QR. El comensal consulta su pedido y su comprobante con un token aleatorio, no con un número consecutivo.
- Protección contra CSRF y XSS, cookie de sesión `HttpOnly`, límite de intentos de ingreso y de pedidos por dispositivo.
- El servidor solo entrega los archivos de la página; nunca el código del backend ni el `.env`.

**Limitaciones:**

- El **comprobante no es una factura electrónica DIAN**; así lo indica en pantalla. Si el restaurante está obligado a facturar electrónicamente, debe hacerlo con su proveedor de facturación.
- El sistema funciona con **HTTP en la red local**. Si se publica en internet, debe ponerse detrás de HTTPS (y usar `COOKIE_SEGURA=1`).
- Probado en **XAMPP con MariaDB 10.4.32** y Python 3.14 en Windows 11. El SQL y el código son compatibles con MySQL 8, pero en ese motor no se probó durante el desarrollo.
- Los avisos sonoros requieren tocar **Activar sonido** cada vez que se abre la pantalla (restricción de los navegadores).

---

## 15. Estructura del proyecto

```
restaurante_sena/
├── index.html, menu.html, pedido.html, factura.html, verificar.html   ← comensal
├── login.html, admin.html, cocina.html, mesero.html, qr-mesas.html    ← personal
├── css/   styles.css, personal.css
├── js/    api.js (conexión con la API), main.js, cliente.js, admin.js, personal.js
├── backend/
│   ├── app.py              API principal (Flask) y entrega de las páginas
│   ├── admin_api.py        categorías, mesas, personal y cupones
│   ├── qr_api.py           códigos QR y verificación de comprobantes
│   ├── reportes_api.py     reportes de ventas y CSV
│   ├── seguridad.py        contraseñas, sesiones y permisos
│   ├── db.py, config.py, dinero.py, validacion.py, errores.py
│   ├── servidor.py         arranque de producción (Waitress)
│   ├── migrar.py           actualización de bases de la versión anterior
│   ├── restaurante_sena_completo.sql   instalación nueva de la base
│   ├── requirements.txt, .env.example
│   └── tests/              pruebas automáticas (pytest)
├── scripts/
│   ├── instalar.ps1, iniciar_servidor.ps1/.bat
│   ├── respaldo.py, respaldo_manual.bat, programar_respaldo.ps1, restaurar.py
├── respaldos/   (se crea sola; no va a git)
└── logs/        (se crea sola; no va a git)
```

---

Proyecto formativo **SENA** — Análisis y Desarrollo de Software (GA7-220501096-AA2-EV02).
