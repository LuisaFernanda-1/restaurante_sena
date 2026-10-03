"""Pruebas de los reportes de ventas por día, semana y mes."""

from datetime import date, timedelta

import pytest

import db


@pytest.fixture
def ventas(admin, crear_pedido):
    """
    Cuatro ventas entregadas en fechas conocidas y un pedido cancelado:
      lunes 2026-09-07  → 2 × Bandeja Paisa  (subtotal 57.000)
      miércoles 09-09   → 1 × Limonada       (subtotal  7.500)  misma semana
      lunes 2026-09-14  → 1 × Trucha         (subtotal 32.000)  semana siguiente
      2026-08-20        → 1 × Ceviche        (subtotal 18.000)  mes anterior
    """
    def vender(items, fecha):
        p = crear_pedido(items=items, propina=False)
        for e in ("en_preparacion", "listo", "entregado"):
            admin.put(f"/api/pedidos/{p['id_pedido']}/estado", json={"estado": e})
        db.ejecutar("UPDATE facturas SET fecha_factura = %s WHERE id_pedido = %s", (f"{fecha} 13:30:00", p["id_pedido"]))
        return p
    v = [vender([{"id": 5, "cantidad": 2}], "2026-09-07"),
         vender([{"id": 10, "cantidad": 1}], "2026-09-09"),
         vender([{"id": 7, "cantidad": 1}], "2026-09-14"),
         vender([{"id": 3, "cantidad": 1}], "2026-08-20")]
    cancelado = crear_pedido(items=[{"id": 1, "cantidad": 1}])
    admin.put(f"/api/pedidos/{cancelado['id_pedido']}/estado", json={"estado": "cancelado"})
    db.ejecutar("UPDATE pedidos SET fecha_pedido = '2026-09-08 12:00:00' WHERE id_pedido = %s", (cancelado["id_pedido"],))
    pendiente = crear_pedido(items=[{"id": 2, "cantidad": 1}])        # no entregado: no cuenta
    db.ejecutar("UPDATE pedidos SET fecha_pedido = '2026-09-08 12:00:00' WHERE id_pedido = %s", (pendiente["id_pedido"],))
    return v


def total_con_impuesto(subtotal):
    return subtotal + round(subtotal * 0.08)


def test_reporte_por_dia(admin, ventas):
    r = admin.get("/api/reportes/ventas?periodo=dia&desde=2026-09-07&hasta=2026-09-14").get_json()
    assert [s["inicio"] for s in r["series"]][0] == "2026-09-07"
    assert len(r["series"]) == 8                                   # incluye los días sin ventas
    por_dia = {s["inicio"]: s for s in r["series"]}
    assert por_dia["2026-09-07"]["pedidos"] == 1
    assert por_dia["2026-09-07"]["total"] == total_con_impuesto(57000)
    assert por_dia["2026-09-08"]["pedidos"] == 0 and por_dia["2026-09-08"]["total"] == 0
    assert por_dia["2026-09-07"]["etiqueta"] == "07/09/2026"
    res = r["resumen"]
    assert res["pedidos"] == 3
    assert res["subtotal"] == 57000 + 7500 + 32000
    assert res["total"] == sum(total_con_impuesto(x) for x in (57000, 7500, 32000))
    assert res["ticket_promedio"] == round(res["total"] / 3)
    assert res["cancelados"] == 1


def test_reporte_por_semana(admin, ventas):
    r = admin.get("/api/reportes/ventas?periodo=semana&desde=2026-09-07&hasta=2026-09-20").get_json()
    assert [(s["inicio"], s["pedidos"]) for s in r["series"]] == [("2026-09-07", 2), ("2026-09-14", 1)]
    assert r["series"][0]["subtotal"] == 57000 + 7500
    assert r["series"][0]["etiqueta"] == "07/09 – 13/09/2026"


def test_semana_empieza_el_lunes_aunque_el_rango_no(admin, ventas):
    r = admin.get("/api/reportes/ventas?periodo=semana&desde=2026-09-09&hasta=2026-09-13").get_json()
    assert r["series"][0]["inicio"] == "2026-09-07"


def test_reporte_por_mes(admin, ventas):
    r = admin.get("/api/reportes/ventas?periodo=mes&desde=2026-08-01&hasta=2026-09-30").get_json()
    assert [(s["inicio"], s["pedidos"], s["subtotal"]) for s in r["series"]] == [
        ("2026-08-01", 1, 18000), ("2026-09-01", 3, 96500)]
    assert r["series"][1]["etiqueta"] == "Septiembre 2026"


def test_productos_categorias_y_pagos(admin, ventas):
    r = admin.get("/api/reportes/ventas?periodo=mes&desde=2026-09-01&hasta=2026-09-30").get_json()
    assert r["productos"][0] == {"producto": "Bandeja Paisa", "unidades": 2, "ventas": 57000}
    categorias = {c["categoria"]: c["ventas"] for c in r["categorias"]}
    assert categorias == {"Principales": 89000, "Bebidas": 7500}
    assert r["pagos"] == [{"metodo_pago": "efectivo", "pedidos": 3, "total": r["resumen"]["total"]}]


def test_rangos_por_defecto(admin):
    hoy = date.today()
    dia = admin.get("/api/reportes/ventas?periodo=dia").get_json()
    assert len(dia["series"]) == 30 and dia["hasta"] == hoy.isoformat()
    semana = admin.get("/api/reportes/ventas?periodo=semana").get_json()
    assert len(semana["series"]) == 12
    assert date.fromisoformat(semana["series"][0]["inicio"]).weekday() == 0
    mes = admin.get("/api/reportes/ventas?periodo=mes").get_json()
    assert len(mes["series"]) == 12 and mes["series"][-1]["inicio"] == hoy.replace(day=1).isoformat()


@pytest.mark.parametrize("qs", ["periodo=anio", "desde=2026-09-10&hasta=2026-09-01",
                                "desde=10/09/2026", "desde=2020-01-01&hasta=2026-01-01"])
def test_parametros_invalidos(admin, qs):
    assert admin.get(f"/api/reportes/ventas?{qs}").status_code == 400


def test_csv_para_excel(admin, ventas):
    r = admin.get("/api/reportes/ventas.csv?periodo=semana&desde=2026-09-07&hasta=2026-09-20")
    assert r.status_code == 200
    assert r.headers["Content-Type"].startswith("text/csv")
    assert 'filename="ventas_semana_2026-09-07_2026-09-20.csv"' in r.headers["Content-Disposition"]
    texto = r.data.decode("utf-8")
    assert texto.startswith("﻿")                              # BOM: Excel muestra las tildes
    lineas = texto.lstrip("﻿").split("\r\n")
    assert lineas[2] == "Semana;Pedidos;Subtotal;Descuentos;Impuesto;Propinas;Total;Ticket promedio"
    assert lineas[3].startswith("07/09 – 13/09/2026;2;64500;")
    assert any(l.startswith("TOTAL;3;96500;") for l in lineas)
    assert "Bandeja Paisa;2;57000" in texto
    assert "Pedidos cancelados;1" in texto


@pytest.mark.parametrize("ruta", ["/api/reportes/ventas", "/api/reportes/ventas.csv"])
def test_reportes_solo_admin(cliente, como, ruta):
    assert cliente.get(ruta).status_code == 401
    assert como("chef").get(ruta).status_code == 403
    assert como("mesero").get(ruta).status_code == 403


def test_venta_de_hoy_aparece_en_el_reporte(admin, crear_pedido):
    p = crear_pedido(items=[{"id": 6, "cantidad": 1}])
    for e in ("en_preparacion", "listo", "entregado"):
        admin.put(f"/api/pedidos/{p['id_pedido']}/estado", json={"estado": e})
    r = admin.get("/api/reportes/ventas?periodo=dia").get_json()
    assert r["series"][-1]["inicio"] == date.today().isoformat()
    assert r["series"][-1]["total"] == p["total"]
    ayer = (date.today() - timedelta(days=1)).isoformat()
    assert next(s for s in r["series"] if s["inicio"] == ayer)["total"] == 0
