"""Pruebas del flujo del comensal: códigos QR de mesa y llamados al mesero."""

import re

import pytest

import db
from conftest import codigo_mesa


def test_cada_mesa_tiene_codigo_distinto_y_aleatorio(bd):
    codigos = [f["codigo_qr"] for f in db.consultar("SELECT codigo_qr FROM mesas")]
    assert len(codigos) == 20
    assert len(set(codigos)) == 20
    assert all(re.fullmatch(r"[0-9a-f]{10}", c) for c in codigos)


def test_solo_el_admin_ve_los_codigos(como):
    assert "codigo_qr" in como("admin").get("/api/mesas").get_json()[0]
    assert "codigo_qr" not in como("mesero").get("/api/mesas").get_json()[0]


def llamar(cliente, mesa=4, codigo=None):
    return cliente.post("/api/llamados", json={"mesa": mesa, "codigo": codigo or codigo_mesa(mesa)})


def test_llamar_mesero_y_atender(cliente, como):
    r = llamar(cliente)
    assert r.status_code == 201
    assert r.get_json()["ya_pendiente"] is False

    # Llamar otra vez no duplica el aviso
    r = llamar(cliente)
    assert r.status_code == 200 and r.get_json()["ya_pendiente"] is True

    mesero = como("mesero")
    pendientes = mesero.get("/api/llamados").get_json()
    assert [p["numero_mesa"] for p in pendientes] == [4]

    lid = pendientes[0]["id_llamado"]
    assert mesero.put(f"/api/llamados/{lid}/atender").status_code == 200
    assert mesero.get("/api/llamados").get_json() == []
    atendido = db.consultar_uno(
        "SELECT l.estado, u.usuario FROM llamados l JOIN usuarios u ON l.id_usuario = u.id_usuario "
        "WHERE l.id_llamado = %s", (lid,))
    assert atendido == {"estado": "atendido", "usuario": "mesero"}

    # Después de atendido, la mesa puede volver a llamar
    assert llamar(cliente).status_code == 201


@pytest.mark.parametrize("mesa,codigo,esperado", [
    (4, "0000000000", 403),
    (99, "abc", 404),
    ("x", "abc", 400),
])
def test_llamado_invalido(cliente, mesa, codigo, esperado):
    assert llamar(cliente, mesa, codigo).status_code == esperado


def test_permisos_llamados(cliente, como):
    llamar(cliente)
    lid = db.consultar_uno("SELECT id_llamado FROM llamados")["id_llamado"]
    assert cliente.get("/api/llamados").status_code == 401
    assert cliente.put(f"/api/llamados/{lid}/atender").status_code == 401
    chef = como("chef")
    assert chef.get("/api/llamados").status_code == 403
    assert chef.put(f"/api/llamados/{lid}/atender").status_code == 403
    assert como("admin").get("/api/llamados").status_code == 200


def test_atender_llamado_inexistente(como):
    assert como("mesero").put("/api/llamados/999/atender").status_code == 404


def test_limite_de_llamados(cliente):
    for mesa in range(1, 11):
        if mesa != 16:
            assert llamar(cliente, mesa).status_code == 201
    assert llamar(cliente, 11).status_code == 429
