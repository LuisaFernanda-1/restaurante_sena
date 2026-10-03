"""Pruebas de inicio de sesión, contraseñas, sesiones y permisos por rol."""

import hashlib

import pytest

import db
from conftest import CLAVES_TEMPORALES

# (método, ruta, cuerpo, roles que SÍ pueden)
ADMIN, CHEF, MESERO = "admin", "chef", "mesero"
ENDPOINTS_PROTEGIDOS = [
    ("POST", "/api/productos", {"nombre": "X", "precio": 1000, "id_categoria": 1}, {ADMIN}),
    ("PUT", "/api/productos/1", {"precio": 13000}, {ADMIN}),
    ("DELETE", "/api/productos/2", None, {ADMIN}),
    ("GET", "/api/stats", None, {ADMIN}),
    ("GET", "/api/mesas", None, {ADMIN, CHEF, MESERO}),
    ("PUT", "/api/mesas/1/estado", {"estado": "reservada"}, {ADMIN, MESERO}),
    ("GET", "/api/pedidos", None, {ADMIN, CHEF, MESERO}),
    ("GET", "/api/pedidos/1", None, {ADMIN, CHEF, MESERO}),
    ("GET", "/api/facturas/1", None, {ADMIN, CHEF, MESERO}),
    ("PUT", "/api/facturas/1/pago", {"metodo_pago": "tarjeta"}, {ADMIN, MESERO}),
]


def llamar(c, metodo, ruta, cuerpo):
    return c.open(ruta, method=metodo, json=cuerpo)


@pytest.mark.parametrize("metodo,ruta,cuerpo,roles", ENDPOINTS_PROTEGIDOS)
def test_sin_sesion_responde_401(cliente, metodo, ruta, cuerpo, roles):
    r = llamar(cliente, metodo, ruta, cuerpo)
    assert r.status_code == 401
    assert r.get_json()["codigo"] == "sin_sesion"


@pytest.mark.parametrize("metodo,ruta,cuerpo,roles", ENDPOINTS_PROTEGIDOS)
@pytest.mark.parametrize("rol", [ADMIN, CHEF, MESERO])
def test_permisos_por_rol(como, crear_pedido, metodo, ruta, cuerpo, roles, rol):
    crear_pedido()                       # pedido 1, para las rutas que lo usan
    c = como(rol)
    if ruta.startswith("/api/facturas/1"):
        # la factura existe solo cuando el pedido se entrega
        a = como(ADMIN)
        for e in ("en_preparacion", "listo", "entregado"):
            a.put("/api/pedidos/1/estado", json={"estado": e})
    r = llamar(c, metodo, ruta, cuerpo)
    if rol in roles:
        assert r.status_code in (200, 201), (rol, ruta, r.get_json())
    else:
        assert r.status_code == 403, (rol, ruta, r.get_json())
        assert r.get_json()["codigo"] == "sin_permiso"


# ------------------------------------------------------------
# Inicio de sesión
# ------------------------------------------------------------
def test_login_correcto_exige_cambiar_clave(cliente):
    r = cliente.post("/api/auth/login", json={"usuario": "admin", "password": CLAVES_TEMPORALES["admin"]})
    assert r.status_code == 200
    user = r.get_json()["user"]
    assert user["rol"] == "Administrador"
    assert user["debe_cambiar_clave"] is True
    assert "contrasena_hash" not in user


def test_login_no_distingue_mayusculas_en_usuario(cliente):
    r = cliente.post("/api/auth/login", json={"usuario": " ADMIN ", "password": CLAVES_TEMPORALES["admin"]})
    assert r.status_code == 200


@pytest.mark.parametrize("usuario,password", [
    ("admin", "incorrecta"), ("noexiste", "loquesea"), ("admin", ""), ("", "x"),
])
def test_login_incorrecto(cliente, usuario, password):
    r = cliente.post("/api/auth/login", json={"usuario": usuario, "password": password})
    assert r.status_code in (400, 401)
    assert cliente.get("/api/auth/me").status_code == 401


def test_mismo_mensaje_para_usuario_inexistente_y_clave_mala(cliente):
    a = cliente.post("/api/auth/login", json={"usuario": "admin", "password": "mala1234"}).get_json()
    b = cliente.post("/api/auth/login", json={"usuario": "fantasma", "password": "mala1234"}).get_json()
    assert a["msg"] == b["msg"]


def test_bloqueo_tras_intentos_fallidos(cliente):
    for _ in range(5):
        assert cliente.post("/api/auth/login", json={"usuario": "chef", "password": "mala"}).status_code == 401
    r = cliente.post("/api/auth/login", json={"usuario": "chef", "password": CLAVES_TEMPORALES["chef"]})
    assert r.status_code == 429


def test_usuario_inactivo_no_entra(cliente):
    db.ejecutar("UPDATE usuarios SET activo = 0 WHERE usuario = 'mesero'")
    r = cliente.post("/api/auth/login", json={"usuario": "mesero", "password": CLAVES_TEMPORALES["mesero"]})
    assert r.status_code == 401


def test_logout(admin):
    assert admin.get("/api/auth/me").status_code == 200
    admin.post("/api/auth/logout")
    assert admin.get("/api/auth/me").status_code == 401
    assert admin.get("/api/stats").status_code == 401


def test_sql_inicial_solo_tiene_hashes_seguros():
    """El script de instalación guarda hashes scrypt, nunca contraseñas en texto."""
    import re
    import config
    sql = (config.BACKEND_DIR / "restaurante_sena_completo.sql").read_text(encoding="utf-8")
    insert = sql[sql.index("INSERT INTO usuarios"):]
    insert = insert[:insert.index(";")]
    hashes = re.findall(r"'(scrypt:[^']+)'", insert)
    assert len(hashes) == 3
    assert "SHA2(" not in insert and "Temporal" not in insert


def test_migracion_de_hash_sha256_antiguo(cliente):
    viejo = hashlib.sha256(b"admin123").hexdigest()
    db.ejecutar("UPDATE usuarios SET contrasena_hash = %s WHERE usuario = 'admin'", (viejo,))
    r = cliente.post("/api/auth/login", json={"usuario": "admin", "password": "admin123"})
    assert r.status_code == 200
    nuevo = db.consultar_uno("SELECT contrasena_hash FROM usuarios WHERE usuario = 'admin'")["contrasena_hash"]
    assert nuevo.startswith("scrypt:")
    # y se sigue pudiendo entrar con la misma contraseña
    cliente.post("/api/auth/logout")
    assert cliente.post("/api/auth/login", json={"usuario": "admin", "password": "admin123"}).status_code == 200


def test_hash_sha256_antiguo_con_clave_incorrecta(cliente):
    viejo = hashlib.sha256(b"admin123").hexdigest()
    db.ejecutar("UPDATE usuarios SET contrasena_hash = %s WHERE usuario = 'admin'", (viejo,))
    assert cliente.post("/api/auth/login", json={"usuario": "admin", "password": "otra"}).status_code == 401


# ------------------------------------------------------------
# Cambio obligatorio de contraseña
# ------------------------------------------------------------
def login_temporal(cliente, usuario="chef"):
    r = cliente.post("/api/auth/login", json={"usuario": usuario, "password": CLAVES_TEMPORALES[usuario]})
    assert r.status_code == 200


def test_clave_temporal_bloquea_todo_hasta_cambiarla(cliente):
    login_temporal(cliente)
    r = cliente.get("/api/pedidos")
    assert r.status_code == 403
    assert r.get_json()["codigo"] == "cambiar_clave"
    assert cliente.get("/api/auth/me").status_code == 200          # pero puede ver quién es

    r = cliente.post("/api/auth/cambiar-clave",
                     json={"actual": CLAVES_TEMPORALES["chef"], "nueva": "Cocina2026segura"})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["user"]["debe_cambiar_clave"] is False
    assert cliente.get("/api/pedidos").status_code == 200

    cliente.post("/api/auth/logout")
    assert cliente.post("/api/auth/login", json={"usuario": "chef", "password": CLAVES_TEMPORALES["chef"]}).status_code == 401
    assert cliente.post("/api/auth/login", json={"usuario": "chef", "password": "Cocina2026segura"}).status_code == 200


@pytest.mark.parametrize("actual,nueva,mensaje", [
    ("mala", "Cocina2026segura", "actual no es correcta"),
    (None, "corta1", "al menos 8"),
    (None, "solamenteletras", "letras y números"),
    (None, "1234567890", "letras y números"),
    (None, "chef12345", "nombre de usuario"),
    (None, "Cocina-Temporal-2026", "temporal"),
    (None, "OtraTemporal99", "temporal"),
])
def test_politica_de_contrasenas(cliente, actual, nueva, mensaje):
    login_temporal(cliente)
    r = cliente.post("/api/auth/cambiar-clave", json={"actual": actual or CLAVES_TEMPORALES["chef"], "nueva": nueva})
    assert r.status_code == 400
    assert mensaje in r.get_json()["msg"]


def test_cambiar_clave_requiere_sesion(cliente):
    r = cliente.post("/api/auth/cambiar-clave", json={"actual": "x", "nueva": "Nueva12345"})
    assert r.status_code == 401


def test_cambiar_clave_cierra_otras_sesiones(app, como):
    otra = como("mesero")                  # sesión en otro dispositivo
    esta = app.test_client()
    esta.post("/api/auth/login", json={"usuario": "mesero", "password": CLAVES_TEMPORALES["mesero"]})
    r = esta.post("/api/auth/cambiar-clave", json={"actual": CLAVES_TEMPORALES["mesero"], "nueva": "Salon2026segura"})
    assert r.status_code == 200
    assert esta.get("/api/pedidos").status_code == 200   # la sesión actual sigue
    assert otra.get("/api/pedidos").status_code == 401   # la otra quedó cerrada


def test_desactivar_usuario_cierra_su_sesion(como):
    c = como("mesero")
    assert c.get("/api/pedidos").status_code == 200
    db.ejecutar("UPDATE usuarios SET activo = 0 WHERE usuario = 'mesero'")
    assert c.get("/api/pedidos").status_code == 401


def test_cookie_de_sesion_protegida(cliente):
    r = cliente.post("/api/auth/login", json={"usuario": "admin", "password": CLAVES_TEMPORALES["admin"]})
    cookie = r.headers["Set-Cookie"]
    assert "HttpOnly" in cookie
    assert "SameSite=Lax" in cookie


# ------------------------------------------------------------
# Cambios de estado según el rol
# ------------------------------------------------------------
def test_transiciones_por_rol(como, crear_pedido):
    pid = crear_pedido()["id_pedido"]
    chef, mesero = como("chef"), como("mesero")

    def cambiar(c, estado):
        return c.put(f"/api/pedidos/{pid}/estado", json={"estado": estado}).status_code

    assert cambiar(mesero, "en_preparacion") == 403   # el mesero no cocina
    assert cambiar(chef, "en_preparacion") == 200
    assert cambiar(mesero, "cancelado") == 403
    assert cambiar(chef, "listo") == 200
    assert cambiar(chef, "entregado") == 403          # el chef no entrega
    assert cambiar(chef, "cancelado") == 403          # listo: solo el admin cancela
    assert cambiar(mesero, "entregado") == 200
    entregado_por = db.consultar_uno(
        "SELECT u.usuario FROM pedidos p JOIN usuarios u ON p.id_usuario = u.id_usuario WHERE p.id_pedido = %s",
        (pid,))
    assert entregado_por["usuario"] == "mesero"


# ------------------------------------------------------------
# Acceso del comensal y protecciones generales
# ------------------------------------------------------------
def test_comensal_ve_su_factura_con_el_token(cliente, admin, crear_pedido):
    p = crear_pedido()
    for e in ("en_preparacion", "listo", "entregado"):
        admin.put(f"/api/pedidos/{p['id_pedido']}/estado", json={"estado": e})
    assert cliente.get(f"/api/facturas/token/{p['token']}").status_code == 200
    assert cliente.get(f"/api/facturas/{p['id_pedido']}").status_code == 401
    assert cliente.get(f"/api/pedidos/{p['id_pedido']}").status_code == 401


def test_proteccion_csrf_por_origen(admin):
    r = admin.put("/api/productos/1", json={"precio": 1}, headers={"Origin": "http://sitio-malicioso.com"})
    assert r.status_code == 403
    assert r.get_json()["codigo"] == "origen"
    r = admin.put("/api/productos/1", json={"precio": 12600}, headers={"Origin": "http://localhost"})
    assert r.status_code == 200


def test_limite_de_pedidos_por_dispositivo(cliente):
    for _ in range(20):
        r = cliente.post("/api/pedidos", json={"mesa": 2, "items": [{"id": 12, "cantidad": 1}]})
        assert r.status_code == 201
    r = cliente.post("/api/pedidos", json={"mesa": 2, "items": [{"id": 12, "cantidad": 1}]})
    assert r.status_code == 429


def test_cabeceras_de_seguridad(cliente):
    r = cliente.get("/api/status")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "SAMEORIGIN"
    assert r.headers["Cache-Control"] == "no-store"
