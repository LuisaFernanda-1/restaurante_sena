"""Pruebas de scripts/respaldo.py y scripts/restaurar.py (requieren mysqldump, p. ej. de XAMPP)."""

import gzip
import os
import sys
import time

import pytest

import config
import db
from conftest import NOMBRE_BD_PRUEBAS, borrar_bd

sys.path.insert(0, str(config.PROYECTO_DIR / "scripts"))
import respaldo  # noqa: E402
import restaurar  # noqa: E402

try:
    respaldo.buscar_programa("mysqldump")
    respaldo.buscar_programa("mysql")
    HAY_MYSQLDUMP = True
except respaldo.ErrorRespaldo:
    HAY_MYSQLDUMP = False

requiere_mysqldump = pytest.mark.skipif(not HAY_MYSQLDUMP, reason="mysqldump no está instalado")
BD_RESTAURADA = NOMBRE_BD_PRUEBAS.replace("_test", "_restaurada_test")


@requiere_mysqldump
def test_respaldo_comprimido_y_completo(bd, crear_pedido, tmp_path):
    crear_pedido(notas="Respaldo con tildes: ñandú")
    archivo = respaldo.hacer_respaldo(tmp_path, bd=NOMBRE_BD_PRUEBAS)
    assert archivo.name.startswith("restaurante_sena_") and archivo.name.endswith(".sql.gz")
    texto = gzip.open(archivo).read().decode("utf-8")
    assert "CREATE TABLE `pedidos`" in texto
    assert "Respaldo con tildes: ñandú" in texto
    assert "Dump completed" in texto[-300:]
    assert not list(tmp_path.glob("*.parcial"))            # no deja archivos a medias


@requiere_mysqldump
def test_respaldo_falla_con_base_inexistente(tmp_path):
    with pytest.raises(respaldo.ErrorRespaldo):
        respaldo.hacer_respaldo(tmp_path, bd="no_existe_esta_base_test")
    assert list(tmp_path.iterdir()) == []                   # no queda un respaldo inválido


def test_retencion_de_30_dias(tmp_path):
    viejo = tmp_path / "restaurante_sena_20250101_000000.sql.gz"
    reciente = tmp_path / "restaurante_sena_20261001_000000.sql.gz"
    otro = tmp_path / "otro_archivo_viejo.txt"
    for f in (viejo, reciente, otro):
        f.write_bytes(b"x")
    hace_40_dias = time.time() - 40 * 86400
    os.utime(viejo, (hace_40_dias, hace_40_dias))
    os.utime(otro, (hace_40_dias, hace_40_dias))
    borrados = respaldo.limpiar_antiguos(tmp_path, dias=30)
    assert borrados == [viejo.name]
    assert not viejo.exists() and reciente.exists() and otro.exists()   # solo borra respaldos


@requiere_mysqldump
def test_restaurar_en_otra_base(bd, crear_pedido, tmp_path):
    p = crear_pedido(items=[{"id": 3, "cantidad": 2}])
    archivo = respaldo.hacer_respaldo(tmp_path, bd=NOMBRE_BD_PRUEBAS)
    try:
        restaurar.restaurar(archivo, bd=BD_RESTAURADA)
        fila = db.consultar_uno(
            f"SELECT p.total, d.nombre_producto FROM `{BD_RESTAURADA}`.pedidos p "
            f"JOIN `{BD_RESTAURADA}`.detalle_pedidos d ON d.id_pedido = p.id_pedido WHERE p.token = %s",
            (p["token"],))
        assert fila == {"total": p["total"], "nombre_producto": "Ceviche de Camarón"}
        # las vistas también se restauran y funcionan
        assert len(db.consultar(f"SELECT * FROM `{BD_RESTAURADA}`.v_ventas_por_categoria")) == 4
    finally:
        borrar_bd(BD_RESTAURADA)


def test_restaurar_rechaza_nombre_invalido(tmp_path):
    with pytest.raises(respaldo.ErrorRespaldo):
        restaurar.restaurar(tmp_path / "x.sql.gz", bd="mala; DROP DATABASE x")


def test_ultimo_respaldo(tmp_path):
    for nombre in ("restaurante_sena_20261001_100000.sql.gz", "restaurante_sena_20261003_090000.sql.gz"):
        (tmp_path / nombre).write_bytes(b"x")
    assert restaurar.ultimo_respaldo(tmp_path).name == "restaurante_sena_20261003_090000.sql.gz"
    with pytest.raises(respaldo.ErrorRespaldo):
        restaurar.ultimo_respaldo(tmp_path / "vacia")
