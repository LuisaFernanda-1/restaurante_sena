/**
 * main.js — Utilidades comunes de Restaurante SENA
 * GA7-220501096-AA2-EV02
 *
 * Avisos (toasts), formato de pesos y fechas. Los datos del sistema
 * vienen siempre del servidor (ver js/api.js).
 */

// ============================================================
// UI HELPERS
// ============================================================
function showToast(msg, type = 'info') {
  let container = document.getElementById('toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toast-container';
    container.setAttribute('role', 'status');
    container.setAttribute('aria-live', 'polite');
    document.body.appendChild(container);
  }
  const icons = { success: '✅', error: '❌', warning: '⚠️', info: 'ℹ️' };
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  const icono = document.createElement('span');
  icono.textContent = icons[type] || icons.info;
  const texto = document.createElement('span');
  texto.textContent = msg;            // siempre como texto, nunca como HTML
  toast.append(icono, texto);
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.animation = 'toastOut .3s ease forwards';
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}

// Pesos colombianos sin decimales: $ 28.500
function formatCOP(val) {
  return new Intl.NumberFormat('es-CO', {
    style: 'currency', currency: 'COP', minimumFractionDigits: 0, maximumFractionDigits: 0
  }).format(Number(val) || 0);
}

function formatFecha(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('es-CO', {
    day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit'
  });
}

function formatHora(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleTimeString('es-CO', { hour: '2-digit', minute: '2-digit' });
}

function doLogout() {
  apiLogout();
}

// ============================================================
// LEGADO — solo lo usa admin.html mientras se conecta a la API
// (fase 4). No usar en páginas nuevas.
// ============================================================
const JSP = {
  session: {
    get: (key) => sessionStorage.getItem(key),
    set: (key, val) => sessionStorage.setItem(key, val),
    remove: (key) => sessionStorage.removeItem(key)
  },
  application: {
    get: (key) => localStorage.getItem(key),
    set: (key, val) => localStorage.setItem(key, val)
  }
};

const MENU_DATA = [];

function getPedidos() {
  const raw = JSP.application.get('sena_pedidos');
  return raw ? JSON.parse(raw) : [];
}

function savePedidos(pedidos) {
  JSP.application.set('sena_pedidos', JSON.stringify(pedidos));
}

function crearPedido(mesa, items, notas) {
  const pedidos = getPedidos();
  const subtotal = items.reduce((s, i) => s + i.precio * i.qty, 0);
  const pedido = {
    id: Date.now(), numero: 'ORD-' + String(Date.now()).slice(-6), mesa,
    items: [...items], notas: notas || '', estado: 'pendiente',
    subtotal, servicio: 0, iva: 0, total: subtotal, fecha: new Date().toISOString()
  };
  pedidos.push(pedido);
  savePedidos(pedidos);
  return pedido;
}

function actualizarEstadoPedido(id, nuevoEstado) {
  const pedidos = getPedidos();
  const p = pedidos.find(p => p.id === id);
  if (p) { p.estado = nuevoEstado; savePedidos(pedidos); }
  return p;
}

function getProductos() {
  const raw = JSP.application.get('sena_productos');
  return raw ? JSON.parse(raw) : [...MENU_DATA];
}

function saveProductos(prods) {
  JSP.application.set('sena_productos', JSON.stringify(prods));
}

function agregarProducto(data) {
  const prods = getProductos();
  const nuevo = { id: Date.now(), ...data, disponible: true };
  prods.push(nuevo);
  saveProductos(prods);
  return nuevo;
}

function editarProducto(id, data) {
  const prods = getProductos();
  const idx = prods.findIndex(p => p.id === id);
  if (idx > -1) { prods[idx] = { ...prods[idx], ...data }; saveProductos(prods); }
}

function eliminarProducto(id) {
  saveProductos(getProductos().filter(p => p.id !== id));
}
