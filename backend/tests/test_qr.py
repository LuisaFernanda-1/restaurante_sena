"""Pruebas de los códigos QR de las mesas y de la verificación de comprobantes."""

import io

import pytest
import segno

import config
import db
from conftest import codigo_mesa


def qr_esperado(texto, formato="svg"):
    """Mismo QR que genera el servidor: si los bytes coinciden, el contenido es ese texto."""
    buf = io.BytesIO()
    q = segno.make(texto, error="m")
    if formato == "png":
        q.save(buf, kind="png", scale=12, border=3, dark="#004d26")
    else:
        q.save(buf, kind="svg", scale=10, border=3, dark="#004d26", xmldecl=False, omitsize=True)
    return buf.getvalue()


def id_mesa(numero):
    return db.consultar_uno("SELECT id_mesa FROM mesas WHERE numero_mesa = %s", (numero,))["id_mesa"]


def test_qr_de_mesa_contiene_la_direccion_correcta(admin):
    r = admin.get(f"/api/mesas/{id_mesa(5)}/qr")
    assert r.status_code == 200
    assert r.headers["Content-Type"] == "image/svg+xml"
    assert b"viewBox" in r.data                       # escalable para imprimir
    esperado = f"{config.SERVER_URL}/menu.html?mesa=5&c={codigo_mesa(5)}"
    assert r.data == qr_esperado(esperado)


def test_qr_de_mesa_en_png_y_descarga(admin):
    r = admin.get(f"/api/mesas/{id_mesa(3)}/qr?formato=png&descargar=1")
    assert r.status_code == 200 and r.headers["Content-Type"] == "image/png"
    assert r.data[:8] == b"\x89PNG\r\n\x1a\n"
    assert 'filename="qr-mesa-3.png"' in r.headers["Content-Disposition"]
    assert r.data == qr_esperado(f"{config.SERVER_URL}/menu.html?mesa=3&c={codigo_mesa(3)}", "png")


def test_enlace_de_mesa(admin):
    datos = admin.get(f"/api/mesas/{id_mesa(7)}/qr/enlace").get_json()
    assert datos["url"] == f"{config.SERVER_URL}/menu.html?mesa=7&c={codigo_mesa(7)}"


@pytest.mark.parametrize("ruta", ["/api/mesas/1/qr", "/api/mesas/1/qr/enlace", "/api/qr/info"])
def test_qr_de_mesas_solo_para_admin(cliente, como, ruta):
    assert cliente.get(ruta).status_code == 401
    assert como("mesero").get(ruta).status_code == 403
    assert como("chef").get(ruta).status_code == 403


def test_regenerar_qr_invalida_el_anterior(admin, cliente):
    viejo = codigo_mesa(5)
    r = admin.post(f"/api/mesas/{id_mesa(5)}/regenerar-qr")
    assert r.status_code == 200
    nuevo = codigo_mesa(5)
    assert nuevo != viejo
    assert cliente.get(f"/api/mesas/5?c={viejo}").status_code == 403     # el QR impreso ya no sirve
    assert cliente.get(f"/api/mesas/5?c={nuevo}").status_code == 200
    assert admin.get(f"/api/mesas/{id_mesa(5)}/qr").data == \
        qr_esperado(f"{config.SERVER_URL}/menu.html?mesa=5&c={nuevo}")


def test_regenerar_qr_permisos(cliente, como):
    assert cliente.post("/api/mesas/1/regenerar-qr").status_code == 401
    assert como("mesero").post("/api/mesas/1/regenerar-qr").status_code == 403
    assert como("admin").post("/api/mesas/999/regenerar-qr").status_code == 404


def test_aviso_si_server_url_es_local(admin, monkeypatch):
    monkeypatch.setattr(config, "SERVER_URL", "http://localhost:8000")
    assert admin.get("/api/qr/info").get_json()["es_local"] is True
    monkeypatch.setattr(config, "SERVER_URL", "http://192.168.1.10:8000")
    assert admin.get("/api/qr/info").get_json()["es_local"] is False


# ------------------------------------------------------------
# Verificación de comprobantes
# ------------------------------------------------------------
def entregar(admin, pid):
    for e in ("en_preparacion", "listo", "entregado"):
        admin.put(f"/api/pedidos/{pid}/estado", json={"estado": e})


def test_qr_de_factura_y_verificacion(cliente, admin, crear_pedido):
    p = crear_pedido(items=[{"id": 5, "cantidad": 2}])
    assert cliente.get(f"/api/facturas/token/{p['token']}/qr").status_code == 404   # aún no hay factura
    entregar(admin, p["id_pedido"])
    fac = cliente.get(f"/api/facturas/token/{p['token']}").get_json()
    codigo = fac["codigo_verificacion"]

    r = cliente.get(f"/api/facturas/token/{p['token']}/qr")
    assert r.status_code == 200
    assert r.data == qr_esperado(f"{config.SERVER_URL}/verificar.html?c={codigo}")

    v = cliente.get(f"/api/verificar/{codigo}").get_json()
    assert v["valido"] is True
    assert v["numero_factura"] == fac["numero_factura"]
    assert v["total"] == p["total"]
    assert v["numero_mesa"] == 5 and v["unidades"] == 2
    assert "token" not in v and "codigo_verificacion" not in v


@pytest.mark.parametrize("codigo", ["0" * 32, "no-es-un-codigo", "A" * 32])
def test_verificar_codigo_inexistente(cliente, codigo):
    assert cliente.get(f"/api/verificar/{codigo}").status_code == 404


def test_qr_factura_token_invalido(cliente):
    assert cliente.get("/api/facturas/token/xyz/qr").status_code == 404


def test_aviso_si_la_ip_del_servidor_cambio(admin, monkeypatch):
    import qr_api
    monkeypatch.setattr(qr_api, "ips_del_servidor", lambda: ["192.168.1.17"])
    monkeypatch.setattr(config, "SERVER_URL", "http://192.168.1.17:8000")
    assert admin.get("/api/qr/info").get_json()["ip_no_coincide"] is False
    monkeypatch.setattr(config, "SERVER_URL", "http://172.20.10.2:8000")      # IP vieja
    assert admin.get("/api/qr/info").get_json()["ip_no_coincide"] is True
    monkeypatch.setattr(config, "SERVER_URL", "http://restaurante.local:8000")  # nombre: no se puede saber
    assert admin.get("/api/qr/info").get_json()["ip_no_coincide"] is False
