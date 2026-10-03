"""Pruebas de "pedir sin escanear": el comensal elige la mesa en una lista."""

import pytest

import config
import db
from conftest import codigo_mesa


@pytest.fixture
def sin_qr(monkeypatch):
    monkeypatch.setattr(config, "PERMITIR_PEDIDO_SIN_QR", True)


@pytest.fixture
def solo_qr(monkeypatch):
    monkeypatch.setattr(config, "PERMITIR_PEDIDO_SIN_QR", False)


def pedir(cliente, mesa, codigo=None, items=None):
    cuerpo = {"mesa": mesa, "items": items or [{"id": 12, "cantidad": 1}], "propina": False}
    if codigo is not None:
        cuerpo["codigo"] = codigo
    return cliente.post("/api/pedidos", json=cuerpo)


# ------------------------------------------------------------
# Modo activado
# ------------------------------------------------------------
def test_config_informa_el_modo(cliente, sin_qr):
    assert cliente.get("/api/config").get_json()["pedido_sin_qr"] is True


def test_lista_de_mesas_para_elegir(cliente, sin_qr):
    r = cliente.get("/api/mesas/disponibles")
    assert r.status_code == 200
    mesas = r.get_json()
    numeros = [m["numero_mesa"] for m in mesas]
    assert len(mesas) == 19 and 16 not in numeros               # la mesa inactiva no aparece
    assert set(mesas[0]) == {"numero_mesa", "capacidad", "estado"}   # nunca el código del QR


def test_validar_mesa_sin_codigo(cliente, sin_qr):
    r = cliente.get("/api/mesas/7")
    assert r.status_code == 200
    assert r.get_json()["origen"] == "manual"
    assert cliente.get(f"/api/mesas/7?c={codigo_mesa(7)}").get_json()["origen"] == "qr"


def test_pedido_sin_codigo_queda_marcado(cliente, admin, sin_qr):
    r = pedir(cliente, 7)
    assert r.status_code == 201
    pid = r.get_json()["id_pedido"]
    assert db.consultar_uno("SELECT origen FROM pedidos WHERE id_pedido = %s", (pid,))["origen"] == "manual"
    # el personal lo ve marcado en sus listas
    lista = admin.get("/api/pedidos?estado=pendiente&items=1").get_json()
    assert lista[0]["origen"] == "manual"
    assert admin.get(f"/api/pedidos/{pid}").get_json()["origen"] == "manual"


def test_pedido_con_qr_sigue_marcado_como_qr(cliente, sin_qr):
    pid = pedir(cliente, 7, codigo_mesa(7)).get_json()["id_pedido"]
    assert db.consultar_uno("SELECT origen FROM pedidos WHERE id_pedido = %s", (pid,))["origen"] == "qr"


def test_codigo_equivocado_se_rechaza_aunque_se_permita_sin_qr(cliente, sin_qr):
    """Un QR con código incorrecto no se convierte en pedido 'sin QR' en silencio."""
    assert pedir(cliente, 7, "0000000000").status_code == 403
    assert pedir(cliente, 7, codigo_mesa(5)).status_code == 403
    assert cliente.get("/api/mesas/7?c=0000000000").status_code == 403


def test_sin_codigo_mesa_inexistente_o_inactiva(cliente, sin_qr):
    assert pedir(cliente, 99).status_code == 404
    assert pedir(cliente, 16).status_code == 409
    assert cliente.get("/api/mesas/16").get_json()["activa"] is False


def test_llamar_mesero_sin_codigo(cliente, como, sin_qr):
    assert cliente.post("/api/llamados", json={"mesa": 9}).status_code == 201
    assert [l["numero_mesa"] for l in como("mesero").get("/api/llamados").get_json()] == [9]


def test_el_pedido_sin_qr_hace_el_flujo_completo(cliente, admin, sin_qr):
    p = pedir(cliente, 11, items=[{"id": 5, "cantidad": 1}]).get_json()
    for e in ("en_preparacion", "listo", "entregado"):
        assert admin.put(f"/api/pedidos/{p['id_pedido']}/estado", json={"estado": e}).status_code == 200
    fac = cliente.get(f"/api/facturas/token/{p['token']}").get_json()
    assert fac["numero_factura"].startswith("FAC-") and fac["total"] == p["total"]


# ------------------------------------------------------------
# Modo desactivado (solo QR)
# ------------------------------------------------------------
def test_modo_solo_qr(cliente, solo_qr):
    assert cliente.get("/api/config").get_json()["pedido_sin_qr"] is False
    r = cliente.get("/api/mesas/disponibles")
    assert r.status_code == 403 and r.get_json()["codigo"] == "qr_requerido"
    r = pedir(cliente, 7)
    assert r.status_code == 403 and r.get_json()["codigo"] == "qr_requerido"
    assert cliente.get("/api/mesas/7").status_code == 403
    assert cliente.post("/api/llamados", json={"mesa": 9}).status_code == 403
    assert pedir(cliente, 7, codigo_mesa(7)).status_code == 201     # con QR sí
