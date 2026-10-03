/**
 * cliente.js — Lógica del comensal (menú, carrito, pedido y factura)
 * Restaurante SENA
 *
 * - La mesa SOLO se toma del QR (menu.html?mesa=N&c=código). El código
 *   lo valida el servidor; no se puede cambiar la mesa a mano.
 * - El carrito vive en este navegador; los precios y totales definitivos
 *   los calcula el servidor al enviar el pedido.
 */

const DOCE_HORAS = 12 * 3600 * 1000;

function leerJSON(clave, defecto) {
  try {
    const v = JSON.parse(localStorage.getItem(clave));
    return v ?? defecto;
  } catch (e) {
    return defecto;
  }
}

function guardarJSON(clave, valor) {
  try { localStorage.setItem(clave, JSON.stringify(valor)); } catch (e) { /* modo privado */ }
}

// ============================================================
// MESA (del QR)
// ============================================================
const Mesa = {
  CLAVE: "sena_mesa",

  /** Mesa del QR: primero la dirección, si no la última escaneada (12 h). */
  actual() {
    const p = new URLSearchParams(window.location.search);
    const numero = p.get("mesa");
    const codigo = p.get("c");
    if (numero !== null) {
      return { numero: numero.trim(), codigo: (codigo || "").trim(), deUrl: true };
    }
    const guardada = leerJSON(this.CLAVE, null);
    if (guardada && Date.now() - guardada.ts < DOCE_HORAS) {
      return { numero: String(guardada.numero), codigo: guardada.codigo, deUrl: false };
    }
    return null;
  },

  guardar(numero, codigo) {
    guardarJSON(this.CLAVE, { numero, codigo, ts: Date.now() });
  },

  olvidar() {
    try { localStorage.removeItem(this.CLAVE); } catch (e) { /* nada */ }
  },

  /** Enlace al menú de la mesa guardada (o al menú en modo consulta). */
  urlMenu() {
    const m = leerJSON(this.CLAVE, null);
    if (m && Date.now() - m.ts < DOCE_HORAS) {
      return `menu.html?mesa=${encodeURIComponent(m.numero)}&c=${encodeURIComponent(m.codigo)}`;
    }
    return "menu.html";
  }
};

// ============================================================
// CARRITO: [{ id, cantidad }] — solo ids y cantidades, nunca precios
// ============================================================
const Carrito = {
  clave(mesa) { return `sena_carrito_${mesa}`; },

  leer(mesa) {
    const items = leerJSON(this.clave(mesa), []);
    return Array.isArray(items)
      ? items.filter(i => Number.isInteger(i.id) && Number.isInteger(i.cantidad) && i.cantidad >= 1)
      : [];
  },

  guardar(mesa, items) { guardarJSON(this.clave(mesa), items); },

  agregar(mesa, id) {
    const items = this.leer(mesa);
    const item = items.find(i => i.id === id);
    if (item) {
      if (item.cantidad >= 10) return { ok: false, msg: "Máximo 10 unidades por producto" };
      item.cantidad++;
    } else {
      items.push({ id, cantidad: 1 });
    }
    this.guardar(mesa, items);
    return { ok: true };
  },

  cambiar(mesa, id, delta) {
    const items = this.leer(mesa);
    const item = items.find(i => i.id === id);
    if (!item) return;
    item.cantidad = Math.max(1, Math.min(10, item.cantidad + delta));
    this.guardar(mesa, items);
  },

  quitar(mesa, id) { this.guardar(mesa, this.leer(mesa).filter(i => i.id !== id)); },

  vaciar(mesa) { this.guardar(mesa, []); },

  unidades(mesa) { return this.leer(mesa).reduce((s, i) => s + i.cantidad, 0); }
};

// ============================================================
// MIS PEDIDOS (tokens para consultar estado y factura)
// ============================================================
const MisPedidos = {
  CLAVE: "sena_mis_pedidos",

  todos() {
    const lista = leerJSON(this.CLAVE, []);
    const hace24h = Date.now() - 24 * 3600 * 1000;
    return (Array.isArray(lista) ? lista : []).filter(p => p.ts > hace24h);
  },

  agregar(p) {
    const lista = this.todos().filter(x => x.token !== p.token);
    lista.unshift({ token: p.token, numero: p.numero_pedido, mesa: p.mesa, ts: Date.now() });
    guardarJSON(this.CLAVE, lista.slice(0, 20));
  },

  ultimo() { return this.todos()[0] || null; }
};

// ============================================================
// TOTALES (vista previa; mismo cálculo que el servidor, dinero.py)
// ============================================================
function porcentajeDe(base, pct) {
  return Math.round(base * pct / 100);
}

function calcularTotales(subtotal, descuentoPct, conPropina, cfg) {
  const descuento = porcentajeDe(subtotal, descuentoPct || 0);
  const base = subtotal - descuento;
  const impuesto = porcentajeDe(base, cfg.impuesto_pct);
  const propina = conPropina ? porcentajeDe(base, cfg.propina_pct) : 0;
  return { subtotal, descuento, impuesto, propina, total: base + impuesto + propina };
}

/** "8" o "8,5" para mostrar porcentajes. */
function pct(valor) {
  return Number(valor).toLocaleString("es-CO", { maximumFractionDigits: 2 });
}

// ============================================================
// ESTADOS DEL PEDIDO
// ============================================================
const ESTADOS_PEDIDO = {
  pendiente:      { texto: "Pendiente",          icono: "ti-clock" },
  en_preparacion: { texto: "En preparación",     icono: "ti-chef-hat" },
  listo:          { texto: "Listo para servir",  icono: "ti-circle-check" },
  entregado:      { texto: "Entregado",          icono: "ti-hand-finger" },
  cancelado:      { texto: "Cancelado",          icono: "ti-circle-x" }
};

// ============================================================
// LLAMAR AL MESERO
// ============================================================
async function llamarMesero() {
  const m = leerJSON(Mesa.CLAVE, null);
  if (!m) {
    showToast("Escanea el código QR de tu mesa para llamar al mesero.", "warning");
    return;
  }
  const r = await apiFetch("/llamados", {
    method: "POST",
    body: JSON.stringify({ mesa: Number(m.numero), codigo: m.codigo })
  });
  showToast(r.data.msg || "No se pudo avisar al mesero.", r.ok ? "success" : "error");
}
