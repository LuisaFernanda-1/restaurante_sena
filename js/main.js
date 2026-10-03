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
