/**
 * main.js — Restaurante SENA
 * GA7-220501096-AA2-EV02
 * Simula lógica JSP/Servlets en el frontend
 */

// ============================================================
// JSP-STYLE: Variables de sesión simuladas (equivalente a session scope)
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
  },
  // Simula out.println() de JSP
  out: {
    println: (selector, html) => {
      const el = document.querySelector(selector);
      if (el) el.innerHTML = html;
    }
  },
  // Simula request.getParameter()
  request: {
    getParameter: (name) => {
      const params = new URLSearchParams(window.location.search);
      return params.get(name);
    }
  }
};

// ============================================================
// DATOS DEL MENÚ (simulan ResultSet de BD)
// ============================================================
const MENU_DATA = [
  { id: 1, cat: 'Entradas', nombre: 'Patacones con Hogao', desc: 'Tostones de plátano verde con salsa de tomate y cebolla criolla', precio: 12500, emoji: '🫓', disponible: true },
  { id: 2, cat: 'Entradas', nombre: 'Empanadas (x3)', desc: 'Empanadas de pipián con ají y guacamole casero', precio: 9800, emoji: '🥟', disponible: true },
  { id: 3, cat: 'Entradas', nombre: 'Ceviche de Camarón', desc: 'Camarón fresco, limón, cilantro y cebolla morada', precio: 18000, emoji: '🍤', disponible: true },
  { id: 4, cat: 'Principales', nombre: 'Bandeja Paisa', desc: 'Frijoles, chicharrón, carne molida, huevo, aguacate, arroz y arepa', precio: 28500, emoji: '🍛', disponible: true },
  { id: 5, cat: 'Principales', nombre: 'Sancocho Trifásico', desc: 'Sopa con pollo, res, cerdo, papa, yuca y mazorca', precio: 24000, emoji: '🍲', disponible: true },
  { id: 6, cat: 'Principales', nombre: 'Trucha a la Plancha', desc: 'Trucha fresca con papas al vapor y ensalada criolla', precio: 32000, emoji: '🐟', disponible: true },
  { id: 7, cat: 'Principales', nombre: 'Posta Negra', desc: 'Carne de res en salsa negra con arroz de coco y tajadas', precio: 26000, emoji: '🥩', disponible: true },
  { id: 8, cat: 'Bebidas', nombre: 'Limonada de Coco', desc: 'Limón natural, leche de coco y azúcar morena', precio: 7500, emoji: '🥥', disponible: true },
  { id: 9, cat: 'Bebidas', nombre: 'Jugo de Lulo', desc: 'Lulo natural recién exprimido, frío o natural', precio: 6000, emoji: '🍊', disponible: true },
  { id: 10, cat: 'Bebidas', nombre: 'Agua Aromática', desc: 'Hierbas frescas: menta, manzanilla o canela', precio: 3500, emoji: '🌿', disponible: true },
  { id: 11, cat: 'Bebidas', nombre: 'Refajo', desc: 'Cerveza + Colombiana, la combinación clásica', precio: 9000, emoji: '🍺', disponible: true },
  { id: 12, cat: 'Postres', nombre: 'Tres Leches', desc: 'Bizcocho esponjoso bañado en tres leches con nata', precio: 11000, emoji: '🎂', disponible: true },
  { id: 13, cat: 'Postres', nombre: 'Arroz con Leche', desc: 'Cremoso arroz con leche, canela y pasas', precio: 8500, emoji: '🍚', disponible: true },
  { id: 14, cat: 'Postres', nombre: 'Brownie de Chocolate', desc: 'Brownie tibio con helado de vainilla artesanal', precio: 13500, emoji: '🍫', disponible: true },
];

// ============================================================
// CART — Gestión del carrito (JSP: session scope)
// ============================================================
function getCart() {
  const raw = JSP.session.get('cart');
  return raw ? JSON.parse(raw) : [];
}

function saveCart(cart) {
  JSP.session.set('cart', JSON.stringify(cart));
  updateCartUI();
}

function addToCart(productId) {
  const product = MENU_DATA.find(p => p.id === productId);
  if (!product) return;
  const cart = getCart();
  const existing = cart.find(i => i.id === productId);
  if (existing) {
    if (existing.qty >= 10) { showToast('Máximo 10 unidades por producto', 'warning'); return; }
    existing.qty++;
  } else {
    cart.push({ id: product.id, nombre: product.nombre, precio: product.precio, emoji: product.emoji, qty: 1 });
  }
  saveCart(cart);
  showToast(`✓ ${product.nombre} agregado al carrito`, 'success');
}

function removeFromCart(productId) {
  let cart = getCart().filter(i => i.id !== productId);
  saveCart(cart);
}

function updateQty(productId, delta) {
  const cart = getCart();
  const item = cart.find(i => i.id === productId);
  if (!item) return;
  item.qty = Math.max(1, Math.min(10, item.qty + delta));
  saveCart(cart);
}

function clearCart() {
  saveCart([]);
}

function getCartTotal() {
  return getCart().reduce((sum, i) => sum + i.precio * i.qty, 0);
}

function getCartCount() {
  return getCart().reduce((sum, i) => sum + i.qty, 0);
}

// ============================================================
// PEDIDOS — Simula tabla pedidos en BD (localStorage)
// ============================================================
const PEDIDOS_KEY = 'sena_pedidos';

function getPedidos() {
  const raw = JSP.application.get(PEDIDOS_KEY);
  return raw ? JSON.parse(raw) : [];
}

function savePedidos(pedidos) {
  JSP.application.set(PEDIDOS_KEY, JSON.stringify(pedidos));
}

function crearPedido(mesa, items, notas) {
  const pedidos = getPedidos();
  const num = 'ORD-' + String(Date.now()).slice(-6);
  const subtotal = items.reduce((s, i) => s + i.precio * i.qty, 0);
  const servicio = Math.round(subtotal * 0.10);
  const iva = Math.round(subtotal * 0.19);
  const total = subtotal + servicio + iva;
  const pedido = {
    id: Date.now(),
    numero: num,
    mesa,
    items: [...items],
    notas: notas || '',
    estado: 'pendiente',
    subtotal, servicio, iva, total,
    fecha: new Date().toISOString()
  };
  pedidos.push(pedido);
  savePedidos(pedidos);
  JSP.session.set('lastOrder', JSON.stringify(pedido));
  return pedido;
}

function actualizarEstadoPedido(id, nuevoEstado) {
  const pedidos = getPedidos();
  const p = pedidos.find(p => p.id === id);
  if (p) {
    p.estado = nuevoEstado;
    if (nuevoEstado === 'entregado') p.fechaEntrega = new Date().toISOString();
    savePedidos(pedidos);
  }
  return p;
}

// ============================================================
// AUTENTICACIÓN — Simula servlet de login
// ============================================================
const USERS = [
  { usuario: 'admin', password: 'admin123', rol: 'Administrador', nombre: 'Admin SENA' },
  { usuario: 'chef', password: 'chef123', rol: 'Chef', nombre: 'Chef Principal' },
  { usuario: 'mesero', password: 'mesero123', rol: 'Mesero', nombre: 'Mesero 1' }
];

function doLogin(usuario, password) {
  const user = USERS.find(u => u.usuario === usuario && u.password === password);
  if (user) {
    JSP.session.set('currentUser', JSON.stringify(user));
    return { ok: true, user };
  }
  return { ok: false, msg: 'Credenciales incorrectas' };
}

function doLogout() {
  JSP.session.remove('currentUser');
  window.location.href = 'login.html';
}

function getUser() {
  const raw = JSP.session.get('currentUser');
  return raw ? JSON.parse(raw) : null;
}

function requireAuth() {
  if (!getUser()) {
    showToast('Debes iniciar sesión primero', 'error');
    setTimeout(() => { window.location.href = 'login.html'; }, 1200);
    return false;
  }
  return true;
}

// ============================================================
// PRODUCTOS CRUD — Simula tabla productos
// ============================================================
const PRODS_KEY = 'sena_productos';

function getProductos() {
  const raw = JSP.application.get(PRODS_KEY);
  return raw ? JSON.parse(raw) : [...MENU_DATA];
}

function saveProductos(prods) {
  JSP.application.set(PRODS_KEY, JSON.stringify(prods));
}

function agregarProducto(data) {
  const prods = getProductos();
  const newProd = { id: Date.now(), ...data, disponible: true };
  prods.push(newProd);
  saveProductos(prods);
  return newProd;
}

function editarProducto(id, data) {
  const prods = getProductos();
  const idx = prods.findIndex(p => p.id === id);
  if (idx > -1) { prods[idx] = { ...prods[idx], ...data }; saveProductos(prods); }
}

function eliminarProducto(id) {
  const prods = getProductos().filter(p => p.id !== id);
  saveProductos(prods);
}

// ============================================================
// UI HELPERS
// ============================================================
function showToast(msg, type = 'info') {
  let container = document.getElementById('toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toast-container';
    document.body.appendChild(container);
  }
  const icons = { success: '✅', error: '❌', warning: '⚠️', info: 'ℹ️' };
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerHTML = `<span>${icons[type] || 'ℹ️'}</span><span>${msg}</span>`;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.animation = 'toastOut .3s ease forwards';
    setTimeout(() => toast.remove(), 300);
  }, 3000);
}

function formatCOP(val) {
  return new Intl.NumberFormat('es-CO', { style: 'currency', currency: 'COP', minimumFractionDigits: 0 }).format(val);
}

function updateCartUI() {
  const count = getCartCount();
  document.querySelectorAll('.cart-count').forEach(el => { el.textContent = count; });
  if (count > 0) {
    document.querySelectorAll('.cart-float').forEach(el => el.classList.add('has-items'));
  }
}

function formatFecha(iso) {
  return new Date(iso).toLocaleString('es-CO', { day:'2-digit', month:'2-digit', year:'numeric', hour:'2-digit', minute:'2-digit' });
}

// Init
document.addEventListener('DOMContentLoaded', () => {
  updateCartUI();
});
