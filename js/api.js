/**
 * api.js — Conector del frontend con el backend Flask
 * GA7-220501096-AA2-EV02 — Restaurante SENA
 *
 * Todas las páginas hablan con el servidor por aquí (fetch a /api/...).
 */

// Ruta RELATIVA a la página: funciona igual en una subcarpeta
// (http://localhost/restaurante/) y en la raíz de un subdominio
// (https://restaurante.midominio.com/), en el computador y en el celular.
const API_BASE = "api";

// ============================================================
// HELPER GENÉRICO
// Devuelve siempre { ok, status, data } y data.msg con un mensaje claro.
// ============================================================
async function apiFetch(path, options = {}) {
  let res;
  try {
    res = await fetch(API_BASE + path, {
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",   // envía la cookie de sesión
      ...options
    });
  } catch (e) {
    console.error("[API ERROR]", e);
    return { ok: false, status: 0, data: { ok: false, msg: "Sin conexión con el servidor. Revise la red Wi-Fi." } };
  }
  let data;
  try {
    data = await res.json();
  } catch (e) {
    data = { ok: false, msg: `Respuesta inesperada del servidor (${res.status}).` };
  }
  return { ok: res.ok, status: res.status, data };
}

// ============================================================
// ESCAPAR TEXTO para insertarlo en HTML (evita inyección de código)
// ============================================================
function esc(valor) {
  return String(valor ?? "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
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
async function apiLogin(usuario, password, recordar = false) {
  return apiFetch("/auth/login", {
    method: "POST",
    body: JSON.stringify({ usuario, password, recordar })
  });
}

async function apiLogout() {
  await apiFetch("/auth/logout", { method: "POST" });
  window.location.href = "login.html";
}

async function apiGetMe() {
  return apiFetch("/auth/me");
}

async function apiCambiarClave(actual, nueva) {
  return apiFetch("/auth/cambiar-clave", {
    method: "POST",
    body: JSON.stringify({ actual, nueva })
  });
}

// Página de inicio de cada rol
const PAGINA_POR_ROL = {
  "Administrador": "admin.html",
  "Chef": "cocina.html",
  "Mesero": "mesero.html"
};

function paginaDeRol(rol) {
  return PAGINA_POR_ROL[rol] || "login.html";
}

/**
 * Protege una página del personal. Úsela al cargar la página:
 *     const user = await requerirSesion(["Administrador"]);
 * - Sin sesión → login.html
 * - Contraseña temporal sin cambiar → login.html (formulario de cambio)
 * - Rol sin permiso → la página de su rol
 */
async function requerirSesion(rolesPermitidos) {
  const r = await apiGetMe();
  if (!r.ok) {
    window.location.replace("login.html");
    return new Promise(() => {});   // detiene la carga de la página
  }
  const user = r.data.user;
  if (user.debe_cambiar_clave) {
    window.location.replace("login.html?cambiar=1");
    return new Promise(() => {});
  }
  if (rolesPermitidos && !rolesPermitidos.includes(user.rol)) {
    window.location.replace(paginaDeRol(user.rol));
    return new Promise(() => {});
  }
  return user;
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


