/**
 * personal.js — Utilidades de las pantallas de cocina y meseros
 *
 * - Consulta periódica al servidor (cada 10 s) con indicador de conexión.
 * - Aviso sonoro generado con Web Audio (no necesita archivos).
 * - Tiempo de espera calculado con la hora del servidor.
 * - Pantalla siempre encendida mientras la vista está abierta (si se puede).
 */

const INTERVALO_SONDEO_MS = 10000;

// ============================================================
// API con manejo de sesión vencida
// ============================================================
async function apiPersonal(ruta, opciones = {}) {
  const r = await apiFetch(ruta, opciones);
  if (r.status === 401) { window.location.replace('login.html'); throw new Error('sin sesión'); }
  if (r.status === 403 && r.data.codigo === 'cambiar_clave') {
    window.location.replace('login.html?cambiar=1'); throw new Error('cambiar clave');
  }
  return r;
}

async function cambiarEstadoPedido(id, estado) {
  const r = await apiPersonal(`/pedidos/${id}/estado`, { method: 'PUT', body: JSON.stringify({ estado }) });
  if (!r.ok) showToast(r.data.msg || 'No se pudo cambiar el estado', 'error');
  return r.ok;
}

// ============================================================
// Hora del servidor
// ============================================================
let desfaseReloj = 0;   // milisegundos: hora del servidor − hora de este equipo

async function sincronizarReloj() {
  const antes = Date.now();
  const r = await apiFetch('/config');
  if (r.ok && r.data.ahora) {
    const latencia = (Date.now() - antes) / 2;
    desfaseReloj = new Date(r.data.ahora).getTime() + latencia - Date.now();
  }
}

function minutosDesde(iso) {
  return Math.max(0, Math.floor((Date.now() + desfaseReloj - new Date(iso).getTime()) / 60000));
}

function textoEspera(min) {
  if (min < 1) return 'recién llegado';
  if (min < 60) return `hace ${min} min`;
  const h = Math.floor(min / 60);
  return `hace ${h} h ${min % 60} min`;
}

// ============================================================
// Aviso sonoro (Web Audio)
// Los navegadores solo permiten sonido después de que la persona toca la
// pantalla: por eso cada vista muestra el botón "Activar sonido".
// ============================================================
const Sonido = {
  ctx: null,
  activo: false,

  async activar() {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) { showToast('Este navegador no permite reproducir avisos sonoros', 'warning'); return false; }
    this.ctx = this.ctx || new Ctx();
    if (this.ctx.state === 'suspended') await this.ctx.resume();
    this.activo = true;
    this.tocar('prueba');
    return true;
  },

  desactivar() { this.activo = false; },

  /** tipo: 'pedido' (cocina), 'listo' (mesero), 'llamado' (mesero), 'prueba' */
  tocar(tipo = 'pedido') {
    if (!this.activo || !this.ctx) return;
    const melodias = {
      pedido:  [[880, 0], [1175, 0.18], [880, 0.36], [1175, 0.54]],
      listo:   [[784, 0], [988, 0.15], [1319, 0.30]],
      llamado: [[1047, 0], [1047, 0.25], [1047, 0.50]],
      prueba:  [[988, 0]]
    };
    const t0 = this.ctx.currentTime + 0.02;
    for (const [frecuencia, inicio] of melodias[tipo] || melodias.pedido) {
      const osc = this.ctx.createOscillator();
      const vol = this.ctx.createGain();
      osc.type = 'sine';
      osc.frequency.value = frecuencia;
      vol.gain.setValueAtTime(0.0001, t0 + inicio);
      vol.gain.exponentialRampToValueAtTime(0.5, t0 + inicio + 0.02);
      vol.gain.exponentialRampToValueAtTime(0.0001, t0 + inicio + 0.16);
      osc.connect(vol).connect(this.ctx.destination);
      osc.start(t0 + inicio);
      osc.stop(t0 + inicio + 0.18);
    }
  }
};

function configurarBotonSonido(idBoton) {
  const boton = document.getElementById(idBoton);
  const pintar = () => {
    boton.classList.toggle('activo', Sonido.activo);
    boton.innerHTML = Sonido.activo
      ? '<i class="ti ti-volume"></i> <span>Sonido activado</span>'
      : '<i class="ti ti-volume-off"></i> <span>Activar sonido</span>';
    boton.setAttribute('aria-pressed', Sonido.activo ? 'true' : 'false');
  };
  boton.addEventListener('click', async () => {
    if (Sonido.activo) Sonido.desactivar(); else await Sonido.activar();
    pintar();
  });
  pintar();
}

// ============================================================
// Detectar elementos nuevos entre una consulta y la siguiente
// ============================================================
class DetectorNuevos {
  constructor() { this.vistos = null; }

  /** Devuelve cuántos ids no se habían visto (0 en la primera carga). */
  revisar(ids) {
    if (this.vistos === null) { this.vistos = new Set(ids); return 0; }
    let nuevos = 0;
    for (const id of ids) if (!this.vistos.has(id)) { nuevos++; this.vistos.add(id); }
    return nuevos;
  }
}

// ============================================================
// Sondeo periódico
// ============================================================
function iniciarSondeo(funcion, idIndicador) {
  const indicador = document.getElementById(idIndicador);
  let enCurso = false;
  const ejecutar = async () => {
    if (enCurso) return;
    enCurso = true;
    try {
      const ok = await funcion();
      if (indicador) {
        indicador.classList.toggle('sin-conexion', !ok);
        indicador.textContent = ok
          ? `Actualizado ${new Date().toLocaleTimeString('es-CO', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}`
          : 'Sin conexión con el servidor — reintentando…';
      }
    } finally {
      enCurso = false;
    }
  };
  ejecutar();
  return { ahora: ejecutar, id: setInterval(ejecutar, INTERVALO_SONDEO_MS) };
}

// ============================================================
// Pantalla siempre encendida (tabletas de cocina)
// ============================================================
async function mantenerPantallaEncendida() {
  if (!('wakeLock' in navigator)) return;
  try {
    await navigator.wakeLock.request('screen');
    document.addEventListener('visibilitychange', async () => {
      if (document.visibilityState === 'visible') {
        try { await navigator.wakeLock.request('screen'); } catch (e) { /* sin permiso */ }
      }
    });
  } catch (e) { /* el navegador no lo permitió */ }
}

// ============================================================
// Confirmación sencilla (sin diálogos del navegador)
// ============================================================
function confirmarAccion(mensaje, textoBoton = 'Confirmar') {
  return new Promise(resolver => {
    const velo = document.createElement('div');
    velo.className = 'confirmacion-velo';
    velo.innerHTML = `<div class="confirmacion-caja" role="dialog" aria-modal="true">
        <p></p>
        <div class="confirmacion-botones">
          <button class="boton secundario" data-r="0">Volver</button>
          <button class="boton peligro" data-r="1"></button>
        </div></div>`;
    velo.querySelector('p').textContent = mensaje;
    velo.querySelector('[data-r="1"]').textContent = textoBoton;
    velo.addEventListener('click', e => {
      const r = e.target.dataset.r;
      if (r !== undefined || e.target === velo) { velo.remove(); resolver(r === '1'); }
    });
    document.body.appendChild(velo);
    velo.querySelector('[data-r="0"]').focus();
  });
}

/** Encabezado común: nombre del usuario y salir. */
async function iniciarPantallaPersonal(roles) {
  const user = await requerirSesion(roles);
  document.getElementById('usuarioNombre').textContent = `${user.nombre} · ${user.rol}`;
  await sincronizarReloj();
  mantenerPantallaEncendida();
  return user;
}
