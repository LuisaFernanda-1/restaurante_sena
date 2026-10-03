/**
 * api.js — Conector del frontend con el backend Flask
 * GA7-220501096-AA2-EV02 — Restaurante SENA
 *
 * Reemplaza las llamadas a localStorage por fetch() al API Flask.
 * Cada función simula un método GET o POST hacia un Servlet.
 */

// Rutas relativas: el mismo servidor Flask entrega las páginas y la API,
// así funciona igual en el computador y en el celular que escanea el QR.
const API_BASE = "/api";

// ============================================================
// HELPER GENÉRICO
// ============================================================
async function apiFetch(path, options = {}) {
  try {
    const res = await fetch(API_BASE + path, {
      headers: { "Content-Type": "application/json" },
      credentials: "include",   // Mantiene sesión (cookie)
      ...options
    });
    const data = await res.json();
    return { ok: res.ok, status: res.status, data };
  } catch (e) {
    console.error("[API ERROR]", e);
    return { ok: false, status: 0, data: { msg: "Sin conexión al servidor" } };
  }
}

// ============================================================
// VERIFICAR ESTADO DE LA API
// ============================================================
async function checkAPIStatus() {
  const badge = document.getElementById("api-status");
  if (!badge) return;

  const r = await apiFetch("/status");
  if (r.ok && r.data.ok) {
    badge.innerHTML = `<span style="color:#198754">● MySQL conectado</span> — ${r.data.db}`;
  } else {
    badge.innerHTML = `<span style="color:#dc3545">● Sin conexión a MySQL</span> — modo offline`;
  }
}

// ============================================================
// AUTH
// ============================================================
async function apiLogin(usuario, password) {
  return apiFetch("/auth/login", {
    method: "POST",
    body: JSON.stringify({ usuario, password })
  });
}

async function apiLogout() {
  await apiFetch("/auth/logout", { method: "POST" });
  window.location.href = "login.html";
}

async function apiGetMe() {
  return apiFetch("/auth/me");
}

// ============================================================
// PRODUCTOS — GET (con parámetros de búsqueda)
// ============================================================
async function apiGetProductos(params = {}) {
  // Construye query string: ?cat=X&q=Y&disponible=1
  const qs = new URLSearchParams(params).toString();
  return apiFetch(`/productos${qs ? "?" + qs : ""}`);
}

async function apiGetProducto(id) {
  return apiFetch(`/productos/${id}`);
}

// PRODUCTOS — POST/PUT/DELETE (formularios de admin)
async function apiCrearProducto(data) {
  return apiFetch("/productos", {
    method: "POST",
    body: JSON.stringify(data)
  });
}

async function apiEditarProducto(id, data) {
  return apiFetch(`/productos/${id}`, {
    method: "PUT",
    body: JSON.stringify(data)
  });
}

async function apiEliminarProducto(id) {
  return apiFetch(`/productos/${id}`, { method: "DELETE" });
}

// ============================================================
// PEDIDOS — POST (envío de formulario)
// ============================================================
async function apiCrearPedido(mesa, items, notas) {
  return apiFetch("/pedidos", {
    method: "POST",
    body: JSON.stringify({ mesa, items, notas })
  });
}

async function apiGetPedidos(params = {}) {
  const qs = new URLSearchParams(params).toString();
  return apiFetch(`/pedidos${qs ? "?" + qs : ""}`);
}

async function apiGetPedido(id) {
  return apiFetch(`/pedidos/${id}`);
}

async function apiCambiarEstadoPedido(id, estado) {
  return apiFetch(`/pedidos/${id}/estado`, {
    method: "PUT",
    body: JSON.stringify({ estado })
  });
}

// ============================================================
// MESAS
// ============================================================
async function apiGetMesas(params = {}) {
  const qs = new URLSearchParams(params).toString();
  return apiFetch(`/mesas${qs ? "?" + qs : ""}`);
}

// ============================================================
// CATEGORÍAS
// ============================================================
async function apiGetCategorias() {
  return apiFetch("/categorias");
}

// ============================================================
// FACTURA
// ============================================================
async function apiGetFactura(pedidoId) {
  return apiFetch(`/facturas/${pedidoId}`);
}

// ============================================================
// CUPONES — GET con parámetro
// ============================================================
async function apiValidarCupon(codigo) {
  return apiFetch(`/cupones/validar?codigo=${encodeURIComponent(codigo)}`);
}

// ============================================================
// ESTADÍSTICAS
// ============================================================
async function apiGetStats() {
  return apiFetch("/stats");
}

// ============================================================
// INICIALIZACIÓN — Muestra badge de conexión
// ============================================================
document.addEventListener("DOMContentLoaded", () => {
  checkAPIStatus();
});


