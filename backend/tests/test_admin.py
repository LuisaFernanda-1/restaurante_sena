"""Pruebas de los endpoints del panel de administración."""

import re

import pytest

import db

# ------------------------------------------------------------
# Permisos: todo lo de administración es solo para el Administrador
# ------------------------------------------------------------
RUTAS_ADMIN = [
    ("GET", "/api/categorias?todas=1", None),
    ("GET", "/api/productos?todas=1", None),
    ("POST", "/api/categorias", {"nombre_categoria": "Sopas"}),
    ("PUT", "/api/categorias/1", {"orden": 9}),
    ("DELETE", "/api/categorias/4", None),
    ("POST", "/api/mesas", {"numero_mesa": 30, "capacidad": 4}),
    ("PUT", "/api/mesas/1", {"capacidad": 3}),
    ("DELETE", "/api/mesas/20", None),
    ("GET", "/api/roles", None),
    ("GET", "/api/usuarios", None),
    ("POST", "/api/usuarios", {"nombre": "Ana", "usuario": "ana", "id_rol": 3}),
    ("PUT", "/api/usuarios/3", {"nombre": "Mesero Uno"}),
    ("POST", "/api/usuarios/3/restablecer-clave", None),
    ("GET", "/api/cupones", None),
    ("POST", "/api/cupones", {"codigo": "NUEVO10", "descuento": 10}),
    ("PUT", "/api/cupones/1", {"descuento": 12}),
    ("DELETE", "/api/cupones/2", None),
]


@pytest.mark.parametrize("metodo,ruta,cuerpo", RUTAS_ADMIN)
def test_solo_administrador(cliente, como, metodo, ruta, cuerpo):
    assert cliente.open(ruta, method=metodo, json=cuerpo).status_code in (401, 403)
    for rol in ("chef", "mesero"):
        assert como(rol).open(ruta, method=metodo, json=cuerpo).status_code == 403
    # el admin pasa el control de permisos (puede recibir 409 por reglas de negocio)
    assert como("admin").open(ruta, method=metodo, json=cuerpo).status_code not in (401, 403)


# ------------------------------------------------------------
# Categorías
# ------------------------------------------------------------
def test_crud_categorias(admin, cliente):
    r = admin.post("/api/categorias", json={"nombre_categoria": "Sopas", "descripcion": "Calientes", "orden": 5})
    assert r.status_code == 201
    cid = r.get_json()["id_categoria"]
    assert admin.post("/api/categorias", json={"nombre_categoria": "sopas"}).status_code == 409   # duplicada
    assert admin.put(f"/api/categorias/{cid}", json={"nombre_categoria": "Sopas y cremas"}).status_code == 200
    nombres = [c["nombre_categoria"] for c in cliente.get("/api/categorias").get_json()]
    assert "Sopas y cremas" in nombres
    assert admin.delete(f"/api/categorias/{cid}").status_code == 200
    assert admin.put(f"/api/categorias/{cid}", json={"orden": 1}).status_code == 404


def test_no_se_borra_categoria_con_productos(admin):
    r = admin.delete("/api/categorias/1")
    assert r.status_code == 409
    assert "producto" in r.get_json()["msg"]


def test_categoria_desactivada_oculta_sus_productos(admin, cliente):
    admin.put("/api/categorias/4", json={"activo": False})
    publicos = cliente.get("/api/productos").get_json()
    assert all(p["cat"] != "Postres" for p in publicos)
    assert "Postres" not in [c["nombre_categoria"] for c in cliente.get("/api/categorias").get_json()]
    todos = admin.get("/api/productos?todas=1").get_json()
    assert any(p["cat"] == "Postres" for p in todos)        # el admin sí los ve


def test_categoria_con_historial_se_desactiva(admin, crear_pedido):
    crear_pedido(items=[{"id": 15, "cantidad": 1}])          # Tres Leches (Postres)
    for pid in (15, 16, 17, 18):
        admin.delete(f"/api/productos/{pid}")
    r = admin.delete("/api/categorias/4")
    assert r.status_code == 200 and "desactivó" in r.get_json()["msg"]
    assert db.consultar_uno("SELECT activo FROM categorias WHERE id_categoria = 4")["activo"] == 0


# ------------------------------------------------------------
# Mesas
# ------------------------------------------------------------
def test_crear_mesa_genera_codigo_qr(admin):
    r = admin.post("/api/mesas", json={"numero_mesa": 21, "capacidad": 2})
    assert r.status_code == 201
    mesa = next(m for m in admin.get("/api/mesas").get_json() if m["numero_mesa"] == 21)
    assert re.fullmatch(r"[0-9a-f]{10}", mesa["codigo_qr"])
    assert admin.post("/api/mesas", json={"numero_mesa": 21}).status_code == 409


@pytest.mark.parametrize("cuerpo", [{"numero_mesa": 0}, {"numero_mesa": 1000}, {"numero_mesa": "x"},
                                    {"numero_mesa": 40, "capacidad": 0}])
def test_mesa_invalida(admin, cuerpo):
    assert admin.post("/api/mesas", json=cuerpo).status_code == 400


def test_editar_y_eliminar_mesa(admin, crear_pedido):
    assert admin.put("/api/mesas/20", json={"capacidad": 10, "estado": "reservada"}).status_code == 200
    assert db.consultar_uno("SELECT capacidad, estado FROM mesas WHERE numero_mesa = 20") == \
        {"capacidad": 10, "estado": "reservada"}
    assert admin.delete("/api/mesas/20").status_code == 200
    crear_pedido(mesa=5)
    r = admin.delete("/api/mesas/5")                         # tiene pedidos
    assert r.status_code == 409 and "inactiva" in r.get_json()["msg"]


# ------------------------------------------------------------
# Usuarios del personal
# ------------------------------------------------------------
def test_crear_usuario_con_clave_temporal(admin, app):
    r = admin.post("/api/usuarios", json={"nombre": "Ana Gómez", "usuario": "Ana.Gomez", "id_rol": 3,
                                          "correo": "ana@restaurante.co"})
    assert r.status_code == 201
    datos = r.get_json()
    assert datos["usuario"] == "ana.gomez"
    clave = datos["clave_temporal"]
    assert re.fullmatch(r"Temporal-[A-Za-z2-9]{4}-[A-Za-z2-9]{4}", clave)
    guardado = db.consultar_uno("SELECT contrasena_hash, debe_cambiar_clave FROM usuarios WHERE usuario = 'ana.gomez'")
    assert guardado["debe_cambiar_clave"] == 1 and clave not in guardado["contrasena_hash"]
    nueva = app.test_client()
    r = nueva.post("/api/auth/login", json={"usuario": "ana.gomez", "password": clave})
    assert r.status_code == 200 and r.get_json()["user"]["debe_cambiar_clave"] is True
    assert "clave_temporal" not in str(admin.get("/api/usuarios").get_json())


@pytest.mark.parametrize("cuerpo,codigo", [
    ({"nombre": "X", "usuario": "ab", "id_rol": 3}, 400),               # usuario muy corto
    ({"nombre": "X", "usuario": "con espacio", "id_rol": 3}, 400),
    ({"nombre": "X", "usuario": "nuevo", "id_rol": 99}, 400),           # rol inexistente
    ({"nombre": "X", "usuario": "nuevo", "id_rol": 3, "correo": "malo"}, 400),
    ({"nombre": "", "usuario": "nuevo", "id_rol": 3}, 400),
    ({"nombre": "X", "usuario": "chef", "id_rol": 3}, 409),             # ya existe
])
def test_usuario_invalido(admin, cuerpo, codigo):
    assert admin.post("/api/usuarios", json=cuerpo).status_code == codigo


def test_restablecer_clave_cierra_sesion_y_exige_cambio(admin, como, app):
    sesion_mesero = como("mesero")
    r = admin.post("/api/usuarios/3/restablecer-clave")
    assert r.status_code == 200
    clave = r.get_json()["clave_temporal"]
    assert sesion_mesero.get("/api/pedidos").status_code == 401        # su sesión se cerró
    c = app.test_client()
    assert c.post("/api/auth/login", json={"usuario": "mesero", "password": clave}).get_json()["user"]["debe_cambiar_clave"]


def test_desactivar_usuario(admin, como):
    sesion_chef = como("chef")
    assert admin.put("/api/usuarios/2", json={"activo": False}).status_code == 200
    assert sesion_chef.get("/api/pedidos").status_code == 401


def test_cambiar_rol(admin, como):
    chef = como("chef")
    assert chef.get("/api/llamados").status_code == 403
    assert admin.put("/api/usuarios/2", json={"id_rol": 3}).status_code == 200   # ahora es mesero
    assert chef.get("/api/llamados").status_code == 200


def test_admin_no_puede_desactivarse_ni_quitarse_el_rol(admin):
    assert admin.put("/api/usuarios/1", json={"activo": False}).status_code == 409
    assert admin.put("/api/usuarios/1", json={"id_rol": 2}).status_code == 409
    assert admin.post("/api/usuarios/1/restablecer-clave").status_code == 409


def test_siempre_queda_un_administrador(admin, app):
    # Segundo admin: puede desactivar al primero, pero no quedarse sin ninguno.
    r = admin.post("/api/usuarios", json={"nombre": "Gerente", "usuario": "gerente", "id_rol": 1})
    gid = r.get_json()["id_usuario"]
    assert admin.put(f"/api/usuarios/{gid}", json={"activo": False}).status_code == 200
    # El único admin activo es el actual; no puede quitarse a sí mismo (ya probado)
    assert db.consultar_uno(
        "SELECT COUNT(*) AS n FROM usuarios WHERE id_rol = 1 AND activo = 1")["n"] == 1


# ------------------------------------------------------------
# Cupones
# ------------------------------------------------------------
def test_crud_cupones(admin, cliente):
    r = admin.post("/api/cupones", json={"codigo": "verano25", "descuento": 25, "fecha_fin": "2099-01-31"})
    assert r.status_code == 201
    cid = r.get_json()["id_cupon"]
    assert cliente.get("/api/cupones/validar?codigo=VERANO25").get_json()["descuento"] == 25
    assert admin.post("/api/cupones", json={"codigo": "VERANO25", "descuento": 5}).status_code == 409
    assert admin.put(f"/api/cupones/{cid}", json={"activo": False}).status_code == 200
    assert cliente.get("/api/cupones/validar?codigo=VERANO25").status_code == 404
    assert admin.delete(f"/api/cupones/{cid}").status_code == 200


@pytest.mark.parametrize("cuerpo", [
    {"codigo": "AB", "descuento": 10}, {"codigo": "CON ESPACIO", "descuento": 10},
    {"codigo": "VALIDO", "descuento": 0}, {"codigo": "VALIDO", "descuento": 101},
    {"codigo": "VALIDO", "descuento": 10, "fecha_fin": "31/12/2026"},
])
def test_cupon_invalido(admin, cuerpo):
    assert admin.post("/api/cupones", json=cuerpo).status_code == 400


def test_cupon_vencido_no_aplica(admin, cliente):
    admin.post("/api/cupones", json={"codigo": "VIEJO", "descuento": 30, "fecha_fin": "2020-01-01"})
    assert cliente.get("/api/cupones/validar?codigo=VIEJO").status_code == 404
    viejo = next(c for c in admin.get("/api/cupones").get_json() if c["codigo"] == "VIEJO")
    assert viejo["vencido"] == 1


def test_cupon_usado_se_desactiva_en_vez_de_borrarse(admin, crear_pedido):
    crear_pedido(cupon="BIENVENIDO")
    cupon = next(c for c in admin.get("/api/cupones").get_json() if c["codigo"] == "BIENVENIDO")
    assert cupon["usos"] == 1
    r = admin.delete(f"/api/cupones/{cupon['id_cupon']}")
    assert r.status_code == 200 and "desactivó" in r.get_json()["msg"]
    assert db.consultar_uno("SELECT activo FROM cupones WHERE codigo = 'BIENVENIDO'")["activo"] == 0


# ------------------------------------------------------------
# Pedidos: filtros del panel
# ------------------------------------------------------------
def test_filtros_de_pedidos(admin, crear_pedido):
    p1 = crear_pedido(mesa=3)
    crear_pedido(mesa=4)
    admin.put(f"/api/pedidos/{p1['id_pedido']}/estado", json={"estado": "cancelado"})
    assert len(admin.get("/api/pedidos?mesa=3").get_json()) == 1
    assert len(admin.get("/api/pedidos?estado=cancelado").get_json()) == 1
    assert len(admin.get("/api/pedidos?estado=pendiente,cancelado").get_json()) == 2
    assert len(admin.get(f"/api/pedidos?numero={p1['numero_pedido']}").get_json()) == 1
    from datetime import date
    assert len(admin.get(f"/api/pedidos?fecha={date.today().isoformat()}").get_json()) == 2
    assert admin.get("/api/pedidos?fecha=2020-01-01").get_json() == []
