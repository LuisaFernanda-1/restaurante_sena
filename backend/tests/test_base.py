"""Pruebas de la base del backend: datos, pedidos, totales y archivos."""

import pytest

import db
from conftest import codigo_mesa


def estado_mesa(numero):
    return db.consultar_uno("SELECT estado FROM mesas WHERE numero_mesa = %s", (numero,))["estado"]


def test_status(cliente):
    r = cliente.get("/api/status")
    assert r.status_code == 200
    assert r.get_json()["ok"] is True


def test_productos_responde_y_conserva_tildes(cliente):
    r = cliente.get("/api/productos")
    assert r.status_code == 200
    productos = r.get_json()
    assert len(productos) == 18
    ceviche = next(p for p in productos if p["id_producto"] == 3)
    assert ceviche["nombre"] == "Ceviche de Camarón"
    assert ceviche["precio"] == 18000 and isinstance(ceviche["precio"], int)


def test_stats_no_falla_con_decimal(admin):
    r = admin.get("/api/stats")
    assert r.status_code == 200
    assert r.get_json()["productos"] == 18


def test_validar_mesa_con_codigo_qr(cliente):
    r = cliente.get(f"/api/mesas/5?c={codigo_mesa(5)}")
    assert r.status_code == 200
    assert r.get_json() == {"numero_mesa": 5, "capacidad": 4, "estado": "disponible", "activa": True, "origen": "qr"}
    assert "codigo_qr" not in r.get_json()


@pytest.mark.parametrize("ruta,codigo", [
    ("/api/mesas/99?c=abc", 404),                 # mesa que no existe
    ("/api/mesas/demo", 404),
    ("/api/mesas/5", 403),                        # sin código
    ("/api/mesas/5?c=0000000000", 403),           # código de otra mesa / inventado
])
def test_validar_mesa_invalida(cliente, ruta, codigo):
    r = cliente.get(ruta)
    assert r.status_code == codigo


def test_codigo_de_una_mesa_no_sirve_para_otra(cliente):
    r = cliente.get(f"/api/mesas/7?c={codigo_mesa(5)}")
    assert r.status_code == 403
    assert r.get_json()["codigo"] == "qr_invalido"
    r = cliente.post("/api/pedidos", json={"mesa": 7, "codigo": codigo_mesa(5),
                                            "items": [{"id": 1, "cantidad": 1}]})
    assert r.status_code == 403


def test_mesa_inactiva_se_informa(cliente):
    r = cliente.get(f"/api/mesas/16?c={codigo_mesa(16)}")
    assert r.status_code == 200 and r.get_json()["activa"] is False


def test_totales_calculados_en_servidor(crear_pedido):
    # 2 × Bandeja Paisa (28.500) + 1 × Limonada (7.500) = 64.500
    p = crear_pedido(items=[{"id": 5, "cantidad": 2}, {"id": 10, "cantidad": 1}],
                     cupon="bienvenido", propina=True)
    assert p["subtotal"] == 64500
    assert p["descuento"] == 6450        # 10 %
    assert p["impuesto"] == 4644         # 8 % de 58.050
    assert p["propina"] == 5805          # 10 % de 58.050
    assert p["total"] == 68499
    assert p["numero_pedido"].startswith("ORD-")
    assert len(p["token"]) == 32


def test_propina_voluntaria(crear_pedido):
    p = crear_pedido(items=[{"id": 5, "cantidad": 1}], propina=False)
    assert p["propina"] == 0
    assert p["total"] == 28500 + 2280


def test_precio_enviado_por_cliente_se_ignora(crear_pedido):
    p = crear_pedido(items=[{"id": 12, "cantidad": 1, "precio": 1}], propina=False)
    assert p["subtotal"] == 3500


@pytest.mark.parametrize("cuerpo,codigo", [
    ({"mesa": "demo", "items": [{"id": 1, "cantidad": 1}]}, 400),
    ({"mesa": 99, "items": [{"id": 1, "cantidad": 1}]}, 404),
    ({"mesa": 16, "items": [{"id": 1, "cantidad": 1}]}, 409),     # mesa inactiva
    ({"mesa": 5, "items": [{"id": 1, "cantidad": 11}]}, 400),
    ({"mesa": 5, "items": [{"id": 1, "cantidad": 0}]}, 400),
    ({"mesa": 5, "items": [{"id": 1, "cantidad": "abc"}]}, 400),
    ({"mesa": 5, "items": [{"id": 1, "cantidad": 6}, {"id": 1, "cantidad": 5}]}, 400),
    ({"mesa": 5, "items": [{"id": 9999, "cantidad": 1}]}, 409),
    ({"mesa": 5, "items": []}, 400),
    ({"mesa": 5}, 400),
    ({"mesa": 5, "items": [{"id": 1, "cantidad": 1}], "cupon": "FALSO"}, 400),
    ({"mesa": 5, "items": [{"id": 1, "cantidad": 1}], "notas": "x" * 301}, 400),
])
def test_pedido_invalido(cliente, cuerpo, codigo):
    if isinstance(cuerpo.get("mesa"), int):
        cuerpo = {**cuerpo, "codigo": codigo_mesa(cuerpo["mesa"])}
    r = cliente.post("/api/pedidos", json=cuerpo)
    assert r.status_code == codigo
    assert r.get_json()["ok"] is False


def test_pedido_cuerpo_no_json(cliente):
    r = cliente.post("/api/pedidos", data="hola", content_type="text/plain")
    assert r.status_code == 400


def test_producto_no_disponible_no_se_puede_pedir(admin):
    admin.put("/api/productos/1", json={"disponible": False})
    r = admin.post("/api/pedidos", json={"mesa": 5, "codigo": codigo_mesa(5), "items": [{"id": 1, "cantidad": 1}]})
    assert r.status_code == 409


def test_pedido_es_atomico(cliente):
    """Si falla, no queda un pedido a medias."""
    antes = db.consultar_uno("SELECT COUNT(*) AS n FROM pedidos")["n"]
    r = cliente.post("/api/pedidos", json={"mesa": 5, "codigo": codigo_mesa(5),
                                            "items": [{"id": 1, "cantidad": 1}, {"id": 9999, "cantidad": 1}]})
    assert r.status_code == 409
    assert db.consultar_uno("SELECT COUNT(*) AS n FROM pedidos")["n"] == antes


def test_flujo_de_estados_y_factura(admin, crear_pedido):
    p = crear_pedido(mesa=5)
    pid = p["id_pedido"]
    assert estado_mesa(5) == "ocupada"
    assert admin.get(f"/api/facturas/{pid}").status_code == 404   # aún no hay factura

    def cambiar(estado):
        return admin.put(f"/api/pedidos/{pid}/estado", json={"estado": estado})

    assert cambiar("listo").status_code == 409            # no se puede saltar la cocina
    assert cambiar("en_preparacion").status_code == 200
    assert cambiar("pendiente").status_code == 409        # no se devuelve
    assert cambiar("listo").status_code == 200
    assert cambiar("entregado").status_code == 200
    assert cambiar("cancelado").status_code == 409        # ya entregado

    fac = admin.get(f"/api/facturas/{pid}").get_json()
    assert fac["numero_factura"].startswith("FAC-")
    assert fac["total"] == p["total"]
    assert fac["impuesto_nombre"] == "Impoconsumo"
    assert len(fac["codigo_verificacion"]) == 32
    assert estado_mesa(5) == "disponible"
    assert admin.get("/api/stats").get_json()["ventas_hoy"] == p["total"]


def test_mesa_sigue_ocupada_si_tiene_otro_pedido(admin, crear_pedido):
    p1 = crear_pedido(mesa=3)
    crear_pedido(mesa=3)
    admin.put(f"/api/pedidos/{p1['id_pedido']}/estado", json={"estado": "cancelado"})
    assert estado_mesa(3) == "ocupada"


def test_cancelado_no_cuenta_en_ventas(admin, crear_pedido):
    p = crear_pedido()
    admin.put(f"/api/pedidos/{p['id_pedido']}/estado", json={"estado": "cancelado"})
    stats = admin.get("/api/stats").get_json()
    assert stats["ventas_hoy"] == 0 and stats["pedidos_hoy"] == 0


def test_pedido_por_token(cliente, crear_pedido):
    p = crear_pedido(items=[{"id": 3, "cantidad": 2}])
    r = cliente.get(f"/api/pedidos/token/{p['token']}")
    assert r.status_code == 200
    datos = r.get_json()
    assert datos["items"][0]["nombre"] == "Ceviche de Camarón"
    assert datos["items"][0]["cantidad"] == 2
    assert cliente.get("/api/pedidos/token/" + "0" * 32).status_code == 404


def test_borrado_logico_de_producto(admin, crear_pedido):
    p = crear_pedido(items=[{"id": 5, "cantidad": 1}])
    r = admin.delete("/api/productos/5")
    assert r.status_code == 200                                # no falla por la llave foránea
    nombres = [x["nombre"] for x in admin.get("/api/productos").get_json()]
    assert "Bandeja Paisa" not in nombres
    detalle = admin.get(f"/api/pedidos/token/{p['token']}").get_json()
    assert detalle["items"][0]["nombre"] == "Bandeja Paisa"   # el historial se conserva


def test_validacion_de_producto(admin):
    assert admin.post("/api/productos", json={"nombre": "", "precio": 100, "id_categoria": 1}).status_code == 400
    assert admin.post("/api/productos", json={"nombre": "A", "precio": 0, "id_categoria": 1}).status_code == 400
    assert admin.post("/api/productos", json={"nombre": "A", "precio": 100, "id_categoria": 77}).status_code == 400
    assert admin.put("/api/productos/1", json={"imagen_url": "javascript:alert(1)"}).status_code == 400
    r = admin.post("/api/productos", json={"nombre": "Nuevo", "precio": 4500, "id_categoria": 2})
    assert r.status_code == 201


@pytest.mark.parametrize("ruta,codigo", [
    ("/", 200), ("/menu.html", 200), ("/css/styles.css", 200), ("/js/api.js", 200),
    ("/backend/.env", 404), ("/backend/app.py", 404), ("/.git/config", 404),
    ("/css/../backend/.env", 404), ("/README.md", 404),
])
def test_archivos_frontend(cliente, ruta, codigo):
    assert cliente.get(ruta).status_code == codigo


def test_api_inexistente_responde_json(cliente):
    r = cliente.get("/api/no-existe")
    assert r.status_code == 404
    assert r.get_json()["ok"] is False
