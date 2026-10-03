/**
 * admin.js — Panel de administración de Restaurante SENA
 *
 * Todo se lee y se guarda en el servidor (API Flask + MySQL).
 * Secciones: dashboard, pedidos, carta, categorías, mesas, personal,
 * cupones y reportes.
 */

const ESTADOS = {
  pendiente:      { texto: 'Pendiente',      icono: 'ti-clock' },
  en_preparacion: { texto: 'En preparación', icono: 'ti-flame' },
  listo:          { texto: 'Listo',          icono: 'ti-circle-check' },
  entregado:      { texto: 'Entregado',      icono: 'ti-check' },
  cancelado:      { texto: 'Cancelado',      icono: 'ti-circle-x' }
};
// Siguiente paso de cada estado (el administrador puede hacer todos)
const SIGUIENTE = {
  pendiente:      { estado: 'en_preparacion', texto: 'Preparar', icono: 'ti-flame' },
  en_preparacion: { estado: 'listo',          texto: 'Listo',    icono: 'ti-circle-check' },
  listo:          { estado: 'entregado',      texto: 'Entregar', icono: 'ti-check' }
};
const ESTADOS_MESA = ['disponible', 'ocupada', 'reservada', 'inactiva'];
const PAGOS = { efectivo: 'Efectivo', tarjeta: 'Tarjeta', digital: 'Pago digital' };

const datos = { categorias: [], productos: [], roles: [], yo: null };
let seccionActual = null;
let pedidosListados = [];
let refrescoDashboard = null;

// ============================================================
// LLAMADAS A LA API (con manejo de sesión vencida)
// ============================================================
async function api(ruta, opciones = {}) {
  const r = await apiFetch(ruta, opciones);
  if (r.status === 401) { window.location.replace('login.html'); throw new Error('sin sesión'); }
  if (r.status === 403 && r.data.codigo === 'cambiar_clave') { window.location.replace('login.html?cambiar=1'); throw new Error('cambiar clave'); }
  return r;
}

const enviar = (ruta, metodo, cuerpo) =>
  api(ruta, { method: metodo, body: cuerpo === undefined ? undefined : JSON.stringify(cuerpo) });

/** Ejecuta una acción y muestra el resultado; devuelve true si salió bien. */
async function accion(promesa, exito) {
  const r = await promesa;
  if (r.ok) showToast(r.data.msg || exito || 'Listo', 'success');
  else showToast(r.data.msg || 'No se pudo completar la acción', 'error');
  return r.ok;
}

function badge(texto, clase) {
  return `<span class="badge-status ${clase}">${esc(texto)}</span>`;
}

function badgeEstado(estado) {
  const e = ESTADOS[estado] || { texto: estado, icono: 'ti-info-circle' };
  return `<span class="badge-status badge-${esc(estado)}"><i class="ti ${e.icono}"></i> ${esc(e.texto)}</span>`;
}

function vacio(icono, texto) {
  return `<div class="vacio"><i class="ti ${icono}"></i>${esc(texto)}</div>`;
}

function hoyISO() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

// ============================================================
// MODAL GENÉRICO: formularios, confirmaciones y avisos
// ============================================================
let alCerrarModal = null;

function abrirModal({ titulo, subtitulo = '', cuerpo = '', acciones = [] }) {
  document.getElementById('modalTitulo').textContent = titulo;
  document.getElementById('modalSub').textContent = subtitulo;
  document.getElementById('modalSub').hidden = !subtitulo;
  document.getElementById('modalCuerpo').innerHTML = cuerpo;
  mostrarErrorModal('');
  const cont = document.getElementById('modalAcciones');
  cont.innerHTML = '';
  for (const a of acciones) {
    const b = document.createElement('button');
    b.type = a.tipo || 'button';
    b.className = `btn ${a.clase || 'btn-ghost'}`;
    b.innerHTML = a.html || esc(a.texto);
    if (a.form) b.setAttribute('form', a.form);
    if (a.alClic) b.addEventListener('click', a.alClic);
    cont.appendChild(b);
  }
  document.getElementById('modal').classList.add('open');
  const primero = document.querySelector('#modalCuerpo input:not([type=hidden]), #modalCuerpo select, #modalCuerpo textarea');
  if (primero) setTimeout(() => primero.focus(), 50);
}

function cerrarModal() {
  document.getElementById('modal').classList.remove('open');
  if (alCerrarModal) { const f = alCerrarModal; alCerrarModal = null; f(); }
}

function mostrarErrorModal(msg) {
  const el = document.getElementById('modalError');
  el.textContent = msg;
  el.style.display = msg ? 'block' : 'none';
}

/** Pregunta y devuelve una promesa con true/false. */
function confirmar({ titulo, mensaje, textoBoton = 'Confirmar', peligro = false }) {
  return new Promise(resolver => {
    let respuesta = false;
    alCerrarModal = () => resolver(respuesta);
    abrirModal({
      titulo, cuerpo: `<p>${esc(mensaje)}</p>`,
      acciones: [
        { texto: 'Cancelar', alClic: cerrarModal },
        { texto: textoBoton, clase: peligro ? 'btn-danger' : 'btn-primary', alClic: () => { respuesta = true; cerrarModal(); } }
      ]
    });
  });
}

function mostrarClaveTemporal(titulo, usuario, clave) {
  abrirModal({
    titulo,
    cuerpo: `<p>Entrega esta contraseña temporal a <strong>${esc(usuario)}</strong>.
             Al ingresar, el sistema le pedirá crear una propia.</p>
             <div class="clave-temporal">${esc(clave)}</div>
             <p class="muted">Por seguridad, esta contraseña no se volverá a mostrar.</p>`,
    acciones: [{ texto: 'Entendido', clase: 'btn-primary', alClic: cerrarModal }]
  });
}

/**
 * Formulario a partir de una lista de campos:
 *   { id, etiqueta, tipo: 'text'|'number'|'email'|'date'|'textarea'|'select'|'check',
 *     opciones: [{valor, texto}], requerido, min, max, maxlength, ayuda, medio }
 * alGuardar(valores) devuelve la respuesta de la API; si falla, el error se
 * muestra dentro del formulario sin cerrarlo.
 */
function formulario({ titulo, subtitulo, campos, valores = {}, textoGuardar = 'Guardar', alGuardar }) {
  const campoHTML = (c) => {
    const v = valores[c.id] ?? c.defecto ?? '';
    const req = c.requerido ? 'required' : '';
    const ayuda = c.ayuda ? `<div class="form-ayuda">${esc(c.ayuda)}</div>` : '';
    if (c.tipo === 'check') {
      return `<div class="form-group"><label class="check-linea">
        <input type="checkbox" name="${c.id}" ${v === true || v === 1 ? 'checked' : ''}> ${esc(c.etiqueta)}</label>${ayuda}</div>`;
    }
    let control;
    if (c.tipo === 'textarea') {
      control = `<textarea name="${c.id}" class="form-textarea" rows="3" ${c.maxlength ? `maxlength="${c.maxlength}"` : ''} ${req}>${esc(v)}</textarea>`;
    } else if (c.tipo === 'select') {
      control = `<select name="${c.id}" class="form-select" ${req}>${c.opciones.map(o =>
        `<option value="${esc(o.valor)}" ${String(o.valor) === String(v) ? 'selected' : ''}>${esc(o.texto)}</option>`).join('')}</select>`;
    } else {
      const extra = [c.min !== undefined ? `min="${c.min}"` : '', c.max !== undefined ? `max="${c.max}"` : '',
                     c.maxlength ? `maxlength="${c.maxlength}"` : '', c.placeholder ? `placeholder="${esc(c.placeholder)}"` : ''].join(' ');
      control = `<input type="${c.tipo || 'text'}" name="${c.id}" class="form-input" value="${esc(v)}" ${extra} ${req}>`;
    }
    return `<div class="form-group"><label for="campo_${c.id}">${esc(c.etiqueta)}${c.requerido ? ' *' : ''}</label>${control.replace('name=', `id="campo_${c.id}" name=`)}${ayuda}</div>`;
  };
  // Campos "medio" se agrupan de a dos por fila
  let html = '';
  for (let i = 0; i < campos.length; i++) {
    if (campos[i].medio && campos[i + 1]?.medio) {
      html += `<div class="form-row">${campoHTML(campos[i])}${campoHTML(campos[i + 1])}</div>`;
      i++;
    } else {
      html += campoHTML(campos[i]);
    }
  }
  abrirModal({
    titulo, subtitulo,
    cuerpo: `<form id="formModal" novalidate>${html}</form>`,
    acciones: [
      { texto: 'Cancelar', alClic: cerrarModal },
      { texto: textoGuardar, clase: 'btn-primary', tipo: 'submit', form: 'formModal' }
    ]
  });
  const form = document.getElementById('formModal');
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!form.reportValidity()) return;
    const valoresForm = {};
    for (const c of campos) {
      const el = form.elements[c.id];
      if (c.tipo === 'check') valoresForm[c.id] = el.checked;
      else if (c.tipo === 'number') valoresForm[c.id] = el.value === '' ? null : Number(el.value);
      else if (c.tipo === 'password') valoresForm[c.id] = el.value;   // las contraseñas no se recortan
      else valoresForm[c.id] = el.value.trim();
    }
    const boton = document.querySelector('#modalAcciones button[type=submit]');
    boton.disabled = true;
    const r = await alGuardar(valoresForm);
    boton.disabled = false;
    if (r && r.ok === false) { mostrarErrorModal(r.data.msg || 'No se pudo guardar'); return; }
    if (r !== false) cerrarModal();
  });
}

// ============================================================
// NAVEGACIÓN
// ============================================================
const CARGAR = {
  dashboard: cargarDashboard, pedidos: cargarPedidos, carta: cargarCarta, categorias: cargarCategorias,
  mesas: cargarMesas, personal: cargarPersonal, cupones: cargarCupones, reportes: cargarReportes,
  respaldo: () => {}
};

function mostrarSeccion(nombre) {
  if (!CARGAR[nombre]) nombre = 'dashboard';
  seccionActual = nombre;
  document.querySelectorAll('.seccion').forEach(s => { s.hidden = s.id !== `sec-${nombre}`; });
  document.querySelectorAll('#menuLateral a').forEach(a => a.classList.toggle('active', a.dataset.seccion === nombre));
  clearInterval(refrescoDashboard);
  if (nombre === 'dashboard') refrescoDashboard = setInterval(cargarDashboard, 30000);
  CARGAR[nombre]();
}

window.addEventListener('hashchange', () => mostrarSeccion(location.hash.slice(1)));

// ============================================================
// DASHBOARD
// ============================================================
async function cargarDashboard() {
  const [rs, rp] = await Promise.all([api('/stats'), api('/pedidos?limit=8')]);
  if (!rs.ok) { document.getElementById('statsGrid').innerHTML = vacio('ti-alert-triangle', rs.data.msg); return; }
  const s = rs.data;
  const tarjeta = (icono, num, etiqueta, destacada = false) => `
    <div class="stat-card${destacada ? ' highlight' : ''}">
      <div class="stat-icon"><i class="ti ${icono}"></i></div>
      <div class="stat-num">${num}</div>
      <div class="stat-label">${etiqueta}</div>
    </div>`;
  document.getElementById('statsGrid').innerHTML =
    tarjeta('ti-cash', formatCOP(s.ventas_hoy), 'Ventas de hoy', true) +
    tarjeta('ti-receipt', s.pedidos_hoy, 'Pedidos de hoy') +
    tarjeta('ti-flame', s.activos, 'Pedidos en curso') +
    tarjeta('ti-armchair', s.mesas_ocupadas, 'Mesas ocupadas') +
    tarjeta('ti-tools-kitchen-2', s.productos, 'Productos disponibles');

  const recientes = rp.ok ? rp.data : [];
  document.getElementById('recentOrders').innerHTML = recientes.length
    ? `<div class="orders-list">${recientes.map(p => `
        <div class="order-item">
          <div class="order-info">
            <div class="order-num">${esc(p.numero_pedido)}</div>
            <div class="order-table">Mesa ${p.numero_mesa} · ${p.num_items} producto(s) · ${formatCOP(p.total)}</div>
            <div class="order-time">${formatFecha(p.fecha_pedido)}</div>
          </div>
          ${badgeEstado(p.estado)}
        </div>`).join('')}</div>`
    : vacio('ti-receipt-off', 'Todavía no hay pedidos.');
  pintarBarras('ventasCategoria', s.ventas_cat);
}

function pintarBarras(idContenedor, filas) {
  const max = Math.max(1, ...filas.map(f => f.total));
  document.getElementById(idContenedor).innerHTML = filas.some(f => f.total > 0)
    ? filas.map(f => `
        <div class="barra-cat">
          <span class="nombre">${esc(f.categoria)}</span>
          <span class="pista"><span class="relleno" style="width:${(f.total / max * 100).toFixed(1)}%"></span></span>
          <span class="valor">${formatCOP(f.total)}</span>
        </div>`).join('')
    : vacio('ti-chart-bar-off', 'Aún no hay ventas entregadas.');
}

// ============================================================
// PEDIDOS
// ============================================================
function limpiarFiltrosPedidos() {
  document.getElementById('fPedFecha').value = hoyISO();
  document.getElementById('fPedEstado').value = '';
  document.getElementById('fPedMesa').value = '';
  document.getElementById('fPedNumero').value = '';
  cargarPedidos();
}

async function cargarPedidos() {
  const p = new URLSearchParams({ limit: 200 });
  const fecha = document.getElementById('fPedFecha').value;
  const est = document.getElementById('fPedEstado').value;
  const mesa = document.getElementById('fPedMesa').value;
  const numero = document.getElementById('fPedNumero').value.trim();
  if (fecha) p.set('fecha', fecha);
  if (est) p.set('estado', est);
  if (mesa) p.set('mesa', mesa);
  if (numero) p.set('numero', numero);
  const r = await api(`/pedidos?${p}`);
  const cont = document.getElementById('pedidosList');
  if (!r.ok) { cont.innerHTML = vacio('ti-alert-triangle', r.data.msg); return; }
  pedidosListados = r.data;
  if (!r.data.length) { cont.innerHTML = vacio('ti-receipt-off', 'No hay pedidos con estos filtros.'); return; }
  cont.innerHTML = `<table class="data-table">
    <thead><tr><th>Pedido</th><th>Mesa</th><th>Hora</th><th>Productos</th><th>Total</th><th>Estado</th><th>Acciones</th></tr></thead>
    <tbody>${r.data.map(ped => {
      const sig = SIGUIENTE[ped.estado];
      const activo = ['pendiente', 'en_preparacion', 'listo'].includes(ped.estado);
      return `<tr>
        <td><strong>${esc(ped.numero_pedido)}</strong></td>
        <td>${ped.numero_mesa}${ped.origen === 'manual' ? ' ' + badge('sin QR', 'badge-amarillo') : ''}</td>
        <td>${formatHora(ped.fecha_pedido)}</td>
        <td>${ped.num_items}</td>
        <td>${formatCOP(ped.total)}</td>
        <td>${badgeEstado(ped.estado)}</td>
        <td><div class="table-actions">
          <button class="btn btn-secondary btn-sm" onclick="verPedido(${ped.id_pedido})"><i class="ti ti-eye"></i> Ver</button>
          ${sig ? `<button class="btn btn-primary btn-sm" onclick="cambiarEstado(${ped.id_pedido}, '${sig.estado}')"><i class="ti ${sig.icono}"></i> ${sig.texto}</button>` : ''}
          ${activo ? `<button class="btn btn-danger-ghost btn-sm" onclick="cancelarPedido(${ped.id_pedido})"><i class="ti ti-x"></i> Cancelar</button>` : ''}
        </div></td>
      </tr>`;
    }).join('')}</tbody></table>`;
}

async function cambiarEstado(id, estado) {
  if (await accion(enviar(`/pedidos/${id}/estado`, 'PUT', { estado }))) {
    cargarPedidos();
    if (document.getElementById('modal').classList.contains('open')) verPedido(id);
  }
}

async function cancelarPedido(id) {
  const numero = pedidosListados.find(p => p.id_pedido === id)?.numero_pedido || '';
  const ok = await confirmar({ titulo: '¿Cancelar el pedido?', mensaje: `El pedido ${numero} se cancelará y no se cobrará.`,
                               textoBoton: 'Sí, cancelar', peligro: true });
  if (ok && await accion(enviar(`/pedidos/${id}/estado`, 'PUT', { estado: 'cancelado' }))) cargarPedidos();
}

async function verPedido(id) {
  const r = await api(`/pedidos/${id}`);
  if (!r.ok) { showToast(r.data.msg, 'error'); return; }
  const p = r.data;
  let pago = '';
  if (p.numero_factura) {
    const rf = await api(`/facturas/${id}`);
    const metodo = rf.ok ? rf.data.metodo_pago : 'efectivo';
    pago = `<div class="form-group" style="margin-top:1rem">
      <label for="metodoPago">Método de pago · ${esc(p.numero_factura)}</label>
      <div class="filtros"><select id="metodoPago" class="form-select">${Object.entries(PAGOS).map(([v, t]) =>
        `<option value="${v}" ${v === metodo ? 'selected' : ''}>${t}</option>`).join('')}</select>
      <button class="btn btn-secondary btn-sm" onclick="guardarPago(${id})">Guardar</button></div></div>`;
  }
  const fila = (txt, val, mostrar = true) => mostrar ? `<div><span>${esc(txt)}</span><span>${val}</span></div>` : '';
  const sig = SIGUIENTE[p.estado];
  abrirModal({
    titulo: `Pedido ${p.numero_pedido}`,
    subtitulo: `Mesa ${p.numero_mesa} · ${formatFecha(p.fecha_pedido)}`,
    cuerpo: `<div>${badgeEstado(p.estado)}${p.origen === 'manual'
        ? ' ' + badge('Mesa elegida sin escanear el QR', 'badge-amarillo') : ''}</div>
      <table class="detalle-items">${p.items.map(i => `<tr>
        <td>${esc(i.emoji || '')} ${esc(i.nombre)}</td><td style="text-align:center">×${i.cantidad}</td>
        <td style="text-align:right">${formatCOP(i.subtotal)}</td></tr>`).join('')}</table>
      <div class="detalle-totales">
        ${fila('Subtotal', formatCOP(p.subtotal))}
        ${fila(`Descuento${p.cupon ? ' (' + p.cupon + ')' : ''}`, '− ' + formatCOP(p.descuento), p.descuento > 0)}
        ${fila('Impuesto', formatCOP(p.impuesto))}
        ${fila('Propina', formatCOP(p.propina))}
        <div class="total"><span>Total</span><span>${formatCOP(p.total)}</span></div>
      </div>
      ${p.notas ? `<p style="margin-top:1rem"><strong>Notas:</strong> ${esc(p.notas)}</p>` : ''}
      ${p.fecha_entrega ? `<p class="muted" style="margin-top:.5rem">Entregado: ${formatFecha(p.fecha_entrega)}</p>` : ''}
      ${pago}`,
    acciones: [
      { texto: 'Cerrar', alClic: cerrarModal },
      ...(sig ? [{ html: `<i class="ti ${sig.icono}"></i> ${sig.texto}`, clase: 'btn-primary',
                   alClic: () => cambiarEstado(id, sig.estado) }] : [])
    ]
  });
}

async function guardarPago(id) {
  const metodo = document.getElementById('metodoPago').value;
  await accion(enviar(`/facturas/${id}/pago`, 'PUT', { metodo_pago: metodo }));
}

// ============================================================
// CARTA (productos)
// ============================================================
async function cargarCategoriasAdmin() {
  const r = await api('/categorias?todas=1');
  if (r.ok) datos.categorias = r.data;
  return r;
}

async function cargarCarta() {
  const [rp] = await Promise.all([api('/productos?todas=1'), cargarCategoriasAdmin()]);
  const sel = document.getElementById('fProdCategoria');
  const elegida = sel.value;
  sel.innerHTML = '<option value="">Todas las categorías</option>' +
    datos.categorias.map(c => `<option value="${esc(c.nombre_categoria)}">${esc(c.nombre_categoria)}</option>`).join('');
  sel.value = elegida;
  if (!rp.ok) { document.getElementById('productosTabla').innerHTML = vacio('ti-alert-triangle', rp.data.msg); return; }
  datos.productos = rp.data;
  pintarProductos();
}

function pintarProductos() {
  const texto = document.getElementById('fProdTexto').value.trim().toLowerCase();
  const cat = document.getElementById('fProdCategoria').value;
  const lista = datos.productos.filter(p =>
    (!cat || p.cat === cat) &&
    (!texto || p.nombre.toLowerCase().includes(texto) || (p.descripcion || '').toLowerCase().includes(texto)));
  const cont = document.getElementById('productosTabla');
  if (!lista.length) { cont.innerHTML = vacio('ti-tools-kitchen-off', 'No hay productos.'); return; }
  cont.innerHTML = `<table class="data-table">
    <thead><tr><th></th><th>Producto</th><th>Categoría</th><th>Precio</th><th>Disponible</th><th>Acciones</th></tr></thead>
    <tbody>${lista.map(p => `<tr>
      <td class="emoji-celda">${esc(p.emoji || '🍽️')}</td>
      <td><strong>${esc(p.nombre)}</strong><div class="muted">${esc(p.descripcion || '')}</div></td>
      <td>${esc(p.cat)}${p.cat_activa ? '' : ' ' + badge('categoría inactiva', 'badge-gris')}</td>
      <td>${formatCOP(p.precio)}</td>
      <td><label class="switch" title="${p.disponible ? 'Disponible' : 'Agotado'}">
        <input type="checkbox" ${p.disponible ? 'checked' : ''} onchange="cambiarDisponible(${p.id_producto}, this)"
               aria-label="Disponible: ${esc(p.nombre)}"><span></span></label></td>
      <td><div class="table-actions">
        <button class="btn btn-secondary btn-sm" onclick="formProducto(${p.id_producto})"><i class="ti ti-edit"></i> Editar</button>
        <button class="btn btn-danger-ghost btn-sm" onclick="eliminarProducto(${p.id_producto})"><i class="ti ti-trash"></i></button>
      </div></td>
    </tr>`).join('')}</tbody></table>`;
}

async function cambiarDisponible(id, casilla) {
  const ok = await accion(enviar(`/productos/${id}`, 'PUT', { disponible: casilla.checked }),
                          casilla.checked ? 'Producto disponible' : 'Producto marcado como agotado');
  if (!ok) casilla.checked = !casilla.checked;
  else datos.productos.find(p => p.id_producto === id).disponible = casilla.checked ? 1 : 0;
}

async function formProducto(id) {
  if (!datos.categorias.length) await cargarCategoriasAdmin();
  const p = id ? datos.productos.find(x => x.id_producto === id) : null;
  formulario({
    titulo: p ? 'Editar producto' : 'Nuevo producto',
    subtitulo: p ? p.nombre : 'Aparecerá en la carta de inmediato',
    valores: p ? { ...p, disponible: Boolean(p.disponible) } : { disponible: true },
    campos: [
      { id: 'nombre', etiqueta: 'Nombre', requerido: true, maxlength: 100, medio: true },
      { id: 'emoji', etiqueta: 'Emoji', maxlength: 16, placeholder: '🍛', medio: true },
      { id: 'id_categoria', etiqueta: 'Categoría', tipo: 'select', requerido: true, medio: true,
        opciones: datos.categorias.map(c => ({ valor: c.id_categoria, texto: c.nombre_categoria + (c.activo ? '' : ' (inactiva)') })) },
      { id: 'precio', etiqueta: 'Precio (pesos)', tipo: 'number', requerido: true, min: 1, max: 10000000, medio: true },
      { id: 'descripcion', etiqueta: 'Descripción', tipo: 'textarea', maxlength: 300 },
      { id: 'imagen_url', etiqueta: 'Imagen (opcional)', maxlength: 255, placeholder: 'https://… o img/plato.jpg',
        ayuda: 'Si no hay imagen, la carta muestra el emoji.' },
      { id: 'disponible', etiqueta: 'Disponible para pedir', tipo: 'check' }
    ],
    alGuardar: async (v) => {
      v.id_categoria = Number(v.id_categoria);
      const r = p ? await enviar(`/productos/${p.id_producto}`, 'PUT', v) : await enviar('/productos', 'POST', v);
      if (r.ok) { showToast(r.data.msg, 'success'); cargarCarta(); }
      return r;
    }
  });
}

async function eliminarProducto(id) {
  const p = datos.productos.find(x => x.id_producto === id);
  const ok = await confirmar({ titulo: '¿Quitar de la carta?', peligro: true, textoBoton: 'Sí, quitar',
    mensaje: `«${p.nombre}» dejará de aparecer en la carta. Las ventas anteriores se conservan en los reportes.` });
  if (ok && await accion(enviar(`/productos/${id}`, 'DELETE'))) cargarCarta();
}

// ============================================================
// CATEGORÍAS
// ============================================================
async function cargarCategorias() {
  const r = await cargarCategoriasAdmin();
  const cont = document.getElementById('categoriasTabla');
  if (!r.ok) { cont.innerHTML = vacio('ti-alert-triangle', r.data.msg); return; }
  if (!datos.categorias.length) { cont.innerHTML = vacio('ti-category', 'No hay categorías.'); return; }
  cont.innerHTML = `<table class="data-table">
    <thead><tr><th>Orden</th><th>Categoría</th><th>Productos</th><th>Activa</th><th>Acciones</th></tr></thead>
    <tbody>${datos.categorias.map(c => `<tr class="${c.activo ? '' : 'fila-inactiva'}">
      <td>${c.orden}</td>
      <td><strong>${esc(c.nombre_categoria)}</strong><div class="muted">${esc(c.descripcion || '')}</div></td>
      <td>${c.productos}</td>
      <td><label class="switch"><input type="checkbox" ${c.activo ? 'checked' : ''}
          onchange="activarCategoria(${c.id_categoria}, this)" aria-label="Activa: ${esc(c.nombre_categoria)}"><span></span></label></td>
      <td><div class="table-actions">
        <button class="btn btn-secondary btn-sm" onclick="formCategoria(${c.id_categoria})"><i class="ti ti-edit"></i> Editar</button>
        <button class="btn btn-danger-ghost btn-sm" onclick="eliminarCategoria(${c.id_categoria})"><i class="ti ti-trash"></i></button>
      </div></td>
    </tr>`).join('')}</tbody></table>`;
}

async function activarCategoria(id, casilla) {
  const ok = await accion(enviar(`/categorias/${id}`, 'PUT', { activo: casilla.checked }),
                          casilla.checked ? 'Categoría visible en la carta' : 'Categoría oculta de la carta');
  if (!ok) casilla.checked = !casilla.checked;
  cargarCategorias();
}

function formCategoria(id) {
  const c = id ? datos.categorias.find(x => x.id_categoria === id) : null;
  formulario({
    titulo: c ? 'Editar categoría' : 'Nueva categoría',
    valores: c || { orden: datos.categorias.length + 1 },
    campos: [
      { id: 'nombre_categoria', etiqueta: 'Nombre', requerido: true, maxlength: 80, medio: true },
      { id: 'orden', etiqueta: 'Orden en la carta', tipo: 'number', min: 0, max: 999, defecto: 0, medio: true },
      { id: 'descripcion', etiqueta: 'Descripción', maxlength: 200 }
    ],
    alGuardar: async (v) => {
      v.orden = v.orden ?? 0;
      const r = c ? await enviar(`/categorias/${c.id_categoria}`, 'PUT', v) : await enviar('/categorias', 'POST', v);
      if (r.ok) { showToast(r.data.msg, 'success'); cargarCategorias(); }
      return r;
    }
  });
}

async function eliminarCategoria(id) {
  const c = datos.categorias.find(x => x.id_categoria === id);
  const ok = await confirmar({ titulo: '¿Eliminar la categoría?', peligro: true, textoBoton: 'Sí, eliminar',
                               mensaje: `Se eliminará «${c.nombre_categoria}».` });
  if (ok && await accion(enviar(`/categorias/${id}`, 'DELETE'))) cargarCategorias();
}

// ============================================================
// MESAS Y QR (los QR se generan en el navegador con js/qr.js)
// ============================================================
let mesas = [];
let infoQR = { server_url: '', configurado: false };

function urlQrMesa(m) {
  return QR.urlMesa(infoQR.server_url, m.numero_mesa, m.codigo_qr);
}

function pintarAvisoServerUrl() {
  const aviso = document.getElementById('avisoServerUrl');
  let titulo = '';
  if (!infoQR.configurado) {
    titulo = 'SERVER_URL no está configurado en api/config.local.php: los QR saldrían con la dirección de este '
           + `navegador (${QR.base('')}), que puede no servir desde los celulares.`;
  } else if (infoQR.es_local) {
    titulo = `Los QR apuntan a ${infoQR.server_url}, que solo funciona en este computador.`;
  } else if (infoQR.ip_no_coincide) {
    titulo = `Los QR apuntan a ${infoQR.server_url}, pero este servidor tiene ahora la IP ${infoQR.ips_servidor.join(', ')}.`;
  }
  aviso.hidden = !titulo;
  document.getElementById('avisoServerUrlTitulo').textContent = titulo;
}

async function cargarMesas() {
  const [r, ri] = await Promise.all([api('/mesas'), api('/qr/info')]);
  if (ri.ok) infoQR = ri.data;
  pintarAvisoServerUrl();
  const cont = document.getElementById('mesasTabla');
  if (!r.ok) { cont.innerHTML = vacio('ti-alert-triangle', r.data.msg); return; }
  mesas = r.data;
  if (!mesas.length) { cont.innerHTML = vacio('ti-armchair', 'No hay mesas.'); return; }
  cont.innerHTML = `<div class="rejilla-mesas">${mesas.map(m => {
    const url = urlQrMesa(m);
    return `<article class="tarjeta-mesa${m.estado === 'inactiva' ? ' inactiva' : ''}" data-mesa="${m.id_mesa}">
      <div class="qr-caja" title="Abrir en grande" onclick="verQrMesa(${m.id_mesa})">${QR.svg(url, `QR de la mesa ${m.numero_mesa}`)}</div>
      <div class="tarjeta-mesa-datos">
        <h4>Mesa ${m.numero_mesa}</h4>
        <div class="muted">${m.capacidad} puestos</div>
        <select class="form-select" onchange="cambiarEstadoMesa(${m.id_mesa}, this)" aria-label="Estado de la mesa ${m.numero_mesa}">
          ${ESTADOS_MESA.map(e => `<option value="${e}" ${e === m.estado ? 'selected' : ''}>${e[0].toUpperCase() + e.slice(1)}</option>`).join('')}
        </select>
        <div class="enlace-qr url-mesa">${esc(url)}</div>
      </div>
      <div class="table-actions">
        <button class="btn btn-secondary btn-sm" onclick="descargarQrMesa(${m.id_mesa})" title="Descargar PNG"><i class="ti ti-download"></i> PNG</button>
        <button class="btn btn-secondary btn-sm" onclick="imprimirQrMesa(${m.id_mesa})" title="Imprimir esta tarjeta"><i class="ti ti-printer"></i> Imprimir</button>
        <button class="btn btn-danger-ghost btn-sm" onclick="regenerarQr(${m.id_mesa})" title="Generar un código nuevo"><i class="ti ti-refresh"></i> Regenerar</button>
        <button class="btn btn-ghost btn-sm" onclick="formMesa(${m.id_mesa})" title="Editar"><i class="ti ti-edit"></i></button>
        <button class="btn btn-danger-ghost btn-sm" onclick="eliminarMesa(${m.id_mesa})" title="Eliminar"><i class="ti ti-trash"></i></button>
      </div>
    </article>`;
  }).join('')}</div>`;
}

function verQrMesa(id) {
  const m = mesas.find(x => x.id_mesa === id);
  const url = urlQrMesa(m);
  abrirModal({
    titulo: `QR de la mesa ${m.numero_mesa}`,
    subtitulo: 'Al escanearlo se abre la carta de esta mesa',
    cuerpo: `<div class="qr-grande">${QR.svg(url, `QR de la mesa ${m.numero_mesa}`)}</div>
      <div class="enlace-qr" id="enlaceQr">${esc(url)}</div>`,
    acciones: [
      { html: '<i class="ti ti-refresh"></i> Regenerar', clase: 'btn-danger-ghost', alClic: () => regenerarQr(id) },
      { html: '<i class="ti ti-copy"></i> Copiar enlace', clase: 'btn-secondary', alClic: () => copiarEnlace(url) },
      { html: '<i class="ti ti-download"></i> Descargar PNG', clase: 'btn-primary', alClic: () => descargarQrMesa(id) }
    ]
  });
}

function descargarQrMesa(id) {
  const m = mesas.find(x => x.id_mesa === id);
  QR.descargarPNG(urlQrMesa(m), `qr-mesa-${m.numero_mesa}.png`);
}

function imprimirQrMesa(id) {
  window.open(`qr-mesas.html?mesa=${id}&imprimir=1`, '_blank', 'noopener');
}

async function copiarEnlace(url) {
  try {
    await navigator.clipboard.writeText(url);
    showToast('Enlace copiado', 'success');
  } catch (e) {
    showToast('No se pudo copiar; selecciona el enlace y cópialo a mano', 'warning');
  }
}

async function regenerarQr(id) {
  const m = mesas.find(x => x.id_mesa === id);
  const ok = await confirmar({
    titulo: `¿Generar un QR nuevo para la mesa ${m.numero_mesa}?`, peligro: true, textoBoton: 'Sí, generar nuevo',
    mensaje: 'El QR que está impreso en la mesa dejará de funcionar. Úselo si el QR se dañó o alguien lo copió; ' +
             'luego imprima el nuevo y reemplácelo.'
  });
  if (ok && await accion(enviar(`/mesas/${id}/regenerar-qr`, 'POST'))) {
    await cargarMesas();
    verQrMesa(id);
  }
}

async function cambiarEstadoMesa(id, select) {
  if (!await accion(enviar(`/mesas/${id}`, 'PUT', { estado: select.value }), 'Estado de la mesa actualizado')) cargarMesas();
  else cargarMesas();
}

function formMesa(id) {
  const m = id ? mesas.find(x => x.id_mesa === id) : null;
  const siguiente = mesas.length ? Math.max(...mesas.map(x => x.numero_mesa)) + 1 : 1;
  formulario({
    titulo: m ? `Editar mesa ${m.numero_mesa}` : 'Nueva mesa',
    subtitulo: m ? '' : 'Se le asigna un código QR nuevo automáticamente',
    valores: m || { numero_mesa: siguiente, capacidad: 4 },
    campos: [
      { id: 'numero_mesa', etiqueta: 'Número de mesa', tipo: 'number', requerido: true, min: 1, max: 999, medio: true },
      { id: 'capacidad', etiqueta: 'Puestos', tipo: 'number', requerido: true, min: 1, max: 50, medio: true }
    ],
    alGuardar: async (v) => {
      const r = m ? await enviar(`/mesas/${m.id_mesa}`, 'PUT', v) : await enviar('/mesas', 'POST', v);
      if (r.ok) { showToast(r.data.msg, 'success'); cargarMesas(); }
      return r;
    }
  });
}

async function eliminarMesa(id) {
  const m = mesas.find(x => x.id_mesa === id);
  const ok = await confirmar({ titulo: `¿Eliminar la mesa ${m.numero_mesa}?`, peligro: true, textoBoton: 'Sí, eliminar',
                               mensaje: 'Solo se pueden eliminar mesas sin pedidos. Si ya tiene historial, márquela como inactiva.' });
  if (ok && await accion(enviar(`/mesas/${id}`, 'DELETE'))) cargarMesas();
}

// ============================================================
// PERSONAL
// ============================================================
let usuarios = [];

async function cargarPersonal() {
  const [r, rr] = await Promise.all([api('/usuarios'), datos.roles.length ? null : api('/roles')]);
  if (rr && rr.ok) datos.roles = rr.data;
  const cont = document.getElementById('personalTabla');
  if (!r.ok) { cont.innerHTML = vacio('ti-alert-triangle', r.data.msg); return; }
  usuarios = r.data;
  cont.innerHTML = `<table class="data-table">
    <thead><tr><th>Nombre</th><th>Usuario</th><th>Rol</th><th>Estado</th><th>Último ingreso</th><th>Acciones</th></tr></thead>
    <tbody>${usuarios.map(u => {
      const yo = u.id_usuario === datos.yo.id;
      const estado = !u.activo ? badge('Inactivo', 'badge-gris')
        : u.debe_cambiar_clave ? badge('Clave temporal', 'badge-amarillo') : badge('Activo', 'badge-verde');
      return `<tr class="${u.activo ? '' : 'fila-inactiva'}">
        <td><strong>${esc(u.nombre)}</strong>${yo ? ' <span class="muted">(tú)</span>' : ''}<div class="muted">${esc(u.correo || '')}</div></td>
        <td>${esc(u.usuario)}</td>
        <td>${esc(u.rol)}</td>
        <td>${estado}</td>
        <td>${u.ultimo_ingreso ? formatFecha(u.ultimo_ingreso) : '<span class="muted">Nunca</span>'}</td>
        <td><div class="table-actions">
          <button class="btn btn-secondary btn-sm" onclick="formUsuario(${u.id_usuario})"><i class="ti ti-edit"></i> Editar</button>
          ${yo ? '' : `<button class="btn btn-ghost btn-sm" onclick="restablecerClave(${u.id_usuario})"><i class="ti ti-key"></i> Restablecer clave</button>`}
        </div></td>
      </tr>`;
    }).join('')}</tbody></table>`;
}

async function formUsuario(id) {
  if (!datos.roles.length) { const rr = await api('/roles'); if (rr.ok) datos.roles = rr.data; }
  const u = id ? usuarios.find(x => x.id_usuario === id) : null;
  const opcionesRol = datos.roles.map(r => ({ valor: r.id_rol, texto: r.nombre_rol }));
  const campos = [
    { id: 'nombre', etiqueta: 'Nombre completo', requerido: true, maxlength: 100 },
    ...(u ? [] : [{ id: 'usuario', etiqueta: 'Usuario para ingresar', requerido: true, maxlength: 50, medio: true,
                    ayuda: 'Minúsculas, números, punto o guion. Ej: ana.gomez' }]),
    { id: 'id_rol', etiqueta: 'Rol', tipo: 'select', requerido: true, opciones: opcionesRol, medio: !u },
    { id: 'correo', etiqueta: 'Correo (opcional)', tipo: 'email', maxlength: 150 },
    ...(u ? [{ id: 'activo', etiqueta: 'Puede ingresar al sistema', tipo: 'check' }] : [])
  ];
  formulario({
    titulo: u ? 'Editar usuario' : 'Nuevo usuario',
    subtitulo: u ? `Usuario: ${u.usuario}` : 'El sistema generará una contraseña temporal',
    valores: u ? { ...u, activo: Boolean(u.activo) } : { id_rol: datos.roles.find(r => r.nombre_rol === 'Mesero')?.id_rol },
    campos,
    textoGuardar: u ? 'Guardar' : 'Crear usuario',
    alGuardar: async (v) => {
      v.id_rol = Number(v.id_rol);
      const r = u ? await enviar(`/usuarios/${u.id_usuario}`, 'PUT', v) : await enviar('/usuarios', 'POST', v);
      if (!r.ok) return r;
      cargarPersonal();
      if (!u) { mostrarClaveTemporal('Usuario creado', r.data.usuario, r.data.clave_temporal); return false; }
      showToast(r.data.msg, 'success');
      return r;
    }
  });
}

async function restablecerClave(id) {
  const u = usuarios.find(x => x.id_usuario === id);
  const ok = await confirmar({ titulo: '¿Restablecer la contraseña?', textoBoton: 'Sí, restablecer',
    mensaje: `Se generará una contraseña temporal para ${u.nombre} y se cerrarán sus sesiones abiertas.` });
  if (!ok) return;
  const r = await enviar(`/usuarios/${id}/restablecer-clave`, 'POST');
  if (!r.ok) { showToast(r.data.msg, 'error'); return; }
  mostrarClaveTemporal('Contraseña restablecida', u.usuario, r.data.clave_temporal);
  cargarPersonal();
}

function cambiarMiClave() {
  formulario({
    titulo: 'Cambiar mi contraseña',
    subtitulo: 'Mínimo 8 caracteres, con letras y números',
    campos: [
      { id: 'actual', etiqueta: 'Contraseña actual', tipo: 'password', requerido: true },
      { id: 'nueva', etiqueta: 'Nueva contraseña', tipo: 'password', requerido: true },
      { id: 'confirma', etiqueta: 'Repite la nueva contraseña', tipo: 'password', requerido: true }
    ],
    alGuardar: async (v) => {
      if (v.nueva !== v.confirma) { mostrarErrorModal('Las dos contraseñas nuevas no coinciden.'); return false; }
      const r = await apiCambiarClave(v.actual, v.nueva);
      if (r.ok) showToast('Contraseña actualizada', 'success');
      return r;
    }
  });
}

// ============================================================
// CUPONES
// ============================================================
let cupones = [];

async function cargarCupones() {
  const r = await api('/cupones');
  const cont = document.getElementById('cuponesTabla');
  if (!r.ok) { cont.innerHTML = vacio('ti-alert-triangle', r.data.msg); return; }
  cupones = r.data;
  if (!cupones.length) { cont.innerHTML = vacio('ti-discount-2', 'No hay cupones.'); return; }
  cont.innerHTML = `<table class="data-table">
    <thead><tr><th>Código</th><th>Descuento</th><th>Válido hasta</th><th>Estado</th><th>Usos</th><th>Acciones</th></tr></thead>
    <tbody>${cupones.map(c => {
      const estado = !c.activo ? badge('Inactivo', 'badge-gris') : c.vencido ? badge('Vencido', 'badge-rojo') : badge('Activo', 'badge-verde');
      return `<tr class="${c.activo && !c.vencido ? '' : 'fila-inactiva'}">
        <td><strong>${esc(c.codigo)}</strong></td>
        <td>${Number(c.descuento)}%</td>
        <td>${c.fecha_fin ? new Date(c.fecha_fin + 'T00:00').toLocaleDateString('es-CO') : '<span class="muted">Sin fecha</span>'}</td>
        <td>${estado}</td>
        <td>${c.usos}</td>
        <td><div class="table-actions">
          <button class="btn btn-secondary btn-sm" onclick="formCupon(${c.id_cupon})"><i class="ti ti-edit"></i> Editar</button>
          <button class="btn btn-danger-ghost btn-sm" onclick="eliminarCupon(${c.id_cupon})"><i class="ti ti-trash"></i></button>
        </div></td>
      </tr>`;
    }).join('')}</tbody></table>`;
}

function formCupon(id) {
  const c = id ? cupones.find(x => x.id_cupon === id) : null;
  formulario({
    titulo: c ? `Editar cupón ${c.codigo}` : 'Nuevo cupón',
    valores: c ? { ...c, descuento: Number(c.descuento), activo: Boolean(c.activo), fecha_fin: c.fecha_fin || '' } : { activo: true },
    campos: [
      { id: 'codigo', etiqueta: 'Código', requerido: true, maxlength: 20, medio: true, ayuda: 'Letras, números, guion. Ej: VERANO25' },
      { id: 'descuento', etiqueta: 'Descuento (%)', tipo: 'number', requerido: true, min: 1, max: 100, medio: true },
      { id: 'fecha_fin', etiqueta: 'Válido hasta (opcional)', tipo: 'date', ayuda: 'Vacío = sin fecha de vencimiento' },
      { id: 'activo', etiqueta: 'Activo', tipo: 'check' }
    ],
    alGuardar: async (v) => {
      v.codigo = v.codigo.toUpperCase();
      v.fecha_fin = v.fecha_fin || null;
      const r = c ? await enviar(`/cupones/${c.id_cupon}`, 'PUT', v) : await enviar('/cupones', 'POST', v);
      if (r.ok) { showToast(r.data.msg, 'success'); cargarCupones(); }
      return r;
    }
  });
}

async function eliminarCupon(id) {
  const c = cupones.find(x => x.id_cupon === id);
  const ok = await confirmar({ titulo: `¿Eliminar el cupón ${c.codigo}?`, peligro: true, textoBoton: 'Sí, eliminar',
                               mensaje: c.usos ? 'Ya se usó en pedidos: se desactivará en lugar de borrarse.' : 'Se eliminará el cupón.' });
  if (ok && await accion(enviar(`/cupones/${id}`, 'DELETE'))) cargarCupones();
}

// ============================================================
// REPORTES (ventas por día, semana o mes)
// ============================================================
const NOMBRE_PERIODO = { dia: 'día', semana: 'semana', mes: 'mes' };
let periodoReporte = 'dia';

function parametrosReporte() {
  const p = new URLSearchParams({ periodo: periodoReporte });
  const desde = document.getElementById('repDesde').value;
  const hasta = document.getElementById('repHasta').value;
  if (desde) p.set('desde', desde);
  if (hasta) p.set('hasta', hasta);
  return p;
}

async function cargarReportes() {
  const r = await api(`/reportes/ventas?${parametrosReporte()}`);
  if (!r.ok) {
    showToast(r.data.msg, 'error');
    document.getElementById('repGrafica').innerHTML = vacio('ti-alert-triangle', r.data.msg);
    return;
  }
  const rep = r.data;
  // Mostrar el rango real (útil cuando se usan los valores por defecto)
  document.getElementById('repDesde').value = rep.desde;
  document.getElementById('repHasta').value = rep.hasta;
  document.getElementById('repCsv').href = `api/reportes/ventas.csv?${parametrosReporte()}`;

  const res = rep.resumen;
  const tarjeta = (icono, num, etiqueta, destacada = false) => `
    <div class="stat-card${destacada ? ' highlight' : ''}">
      <div class="stat-icon"><i class="ti ${icono}"></i></div>
      <div class="stat-num mediano">${num}</div>
      <div class="stat-label">${etiqueta}</div>
    </div>`;
  document.getElementById('repResumen').innerHTML =
    tarjeta('ti-cash', formatCOP(res.total), 'Ventas totales', true) +
    tarjeta('ti-receipt', res.pedidos, 'Pedidos entregados') +
    tarjeta('ti-calculator', formatCOP(res.ticket_promedio), 'Ticket promedio') +
    tarjeta('ti-heart-handshake', formatCOP(res.propina), 'Propinas') +
    tarjeta('ti-building-bank', formatCOP(res.impuesto), 'Impuesto') +
    tarjeta('ti-discount-2', formatCOP(res.descuento), 'Descuentos') +
    tarjeta('ti-circle-x', res.cancelados, 'Pedidos cancelados');

  document.getElementById('repTituloGrafica').innerHTML =
    `<i class="ti ti-chart-bar"></i> Ventas por ${NOMBRE_PERIODO[rep.periodo]}`;
  pintarGrafica(rep.series);
  pintarTablaReporte(rep);

  document.getElementById('repProductos').innerHTML = rep.productos.length
    ? `<table class="data-table"><thead><tr><th>#</th><th>Producto</th><th class="num">Unidades</th><th class="num">Ventas</th></tr></thead>
       <tbody>${rep.productos.map((p, i) => `<tr><td>${i + 1}</td><td>${esc(p.producto)}</td>
         <td class="num">${p.unidades}</td><td class="num">${formatCOP(p.ventas)}</td></tr>`).join('')}</tbody></table>`
    : vacio('ti-tools-kitchen-off', 'Sin ventas en este rango.');
  pintarBarras('repCategorias', rep.categorias.map(c => ({ categoria: c.categoria, total: c.ventas })));
  document.getElementById('repPagos').innerHTML = rep.pagos.length
    ? `<table class="data-table"><thead><tr><th>Método</th><th class="num">Pedidos</th><th class="num">Total</th></tr></thead>
       <tbody>${rep.pagos.map(p => `<tr><td>${esc(PAGOS[p.metodo_pago] || p.metodo_pago)}</td>
         <td class="num">${p.pedidos}</td><td class="num">${formatCOP(p.total)}</td></tr>`).join('')}</tbody></table>`
    : vacio('ti-credit-card-off', 'Sin ventas en este rango.');
}

/** Valor "redondo" para el tope del eje (1, 2 o 5 × 10^n). */
function topeEje(max) {
  if (max <= 0) return 1;
  const base = Math.pow(10, Math.floor(Math.log10(max)));
  for (const m of [1, 2, 5, 10]) if (m * base >= max) return m * base;
  return 10 * base;
}

function pesosCortos(v) {
  if (v >= 1e6) return `$${(v / 1e6).toLocaleString('es-CO', { maximumFractionDigits: 1 })} M`;
  if (v >= 1e3) return `$${Math.round(v / 1e3).toLocaleString('es-CO')} mil`;
  return `$${Math.round(v)}`;
}

function etiquetaCorta(s, periodo) {
  const d = new Date(s.inicio + 'T00:00');
  if (periodo === 'mes') return d.toLocaleDateString('es-CO', { month: 'short' }).replace('.', '');
  return `${d.getDate()}/${d.getMonth() + 1}`;
}

function pintarGrafica(series) {
  const cont = document.getElementById('repGrafica');
  const max = Math.max(0, ...series.map(s => s.total));
  const tope = topeEje(max);
  const rejilla = [0, 0.5, 1].map(f =>
    `<div class="rejilla" style="bottom:calc(26px + ${f} * (100% - 26px))"><span>${pesosCortos(tope * f)}</span></div>`).join('');
  // Etiquetas del eje X: como máximo ~10 para que no se monten
  const cada = Math.max(1, Math.ceil(series.length / 10));
  const barras = series.map((s, i) => `
    <div class="barra" tabindex="0" data-i="${i}" aria-label="${esc(s.etiqueta)}: ${formatCOP(s.total)}, ${s.pedidos} pedidos">
      <i style="height:${s.total ? Math.max(2, s.total / tope * 100) : 0}%"></i>
    </div>`).join('');
  const ejeX = series.map((s, i) => `<span>${i % cada === 0 ? esc(etiquetaCorta(s, periodoReporte)) : ''}</span>`).join('');
  cont.innerHTML = rejilla + `<div class="barras">${barras}</div><div class="eje-x">${ejeX}</div>` +
    (max === 0 ? '<div class="sin-datos">Sin ventas entregadas en este rango</div>' : '') +
    '<div class="tooltip-grafica" hidden></div>';

  const tip = cont.querySelector('.tooltip-grafica');
  const mostrar = (barra) => {
    const s = series[Number(barra.dataset.i)];
    tip.innerHTML = `<strong>${formatCOP(s.total)}</strong>${esc(s.etiqueta)} · ${s.pedidos} pedido(s)`;
    const caja = cont.getBoundingClientRect();
    const b = barra.getBoundingClientRect();
    const alto = barra.querySelector('i').getBoundingClientRect();
    tip.style.left = `${b.left - caja.left + b.width / 2}px`;
    tip.style.top = `${Math.max(alto.top - caja.top - 6, 30)}px`;
    tip.hidden = false;
  };
  cont.querySelectorAll('.barra').forEach(b => {
    b.addEventListener('mouseenter', () => mostrar(b));
    b.addEventListener('focus', () => mostrar(b));
    b.addEventListener('mouseleave', () => { tip.hidden = true; });
    b.addEventListener('blur', () => { tip.hidden = true; });
  });
}

function pintarTablaReporte(rep) {
  const r = rep.resumen;
  const titulo = NOMBRE_PERIODO[rep.periodo][0].toUpperCase() + NOMBRE_PERIODO[rep.periodo].slice(1);
  document.getElementById('repTabla').innerHTML = `<table class="data-table">
    <thead><tr><th>${esc(titulo)}</th>
      <th class="num">Pedidos</th><th class="num">Subtotal</th><th class="num">Descuentos</th><th class="num">Impuesto</th>
      <th class="num">Propinas</th><th class="num">Total</th><th class="num">Ticket prom.</th></tr></thead>
    <tbody>${rep.series.map(s => `<tr><td>${esc(s.etiqueta)}</td><td class="num">${s.pedidos}</td>
      <td class="num">${formatCOP(s.subtotal)}</td><td class="num">${formatCOP(s.descuento)}</td>
      <td class="num">${formatCOP(s.impuesto)}</td><td class="num">${formatCOP(s.propina)}</td>
      <td class="num"><strong>${formatCOP(s.total)}</strong></td><td class="num">${formatCOP(s.ticket_promedio)}</td></tr>`).join('')}
      <tr><td><strong>Total</strong></td><td class="num"><strong>${r.pedidos}</strong></td><td class="num">${formatCOP(r.subtotal)}</td>
      <td class="num">${formatCOP(r.descuento)}</td><td class="num">${formatCOP(r.impuesto)}</td><td class="num">${formatCOP(r.propina)}</td>
      <td class="num"><strong>${formatCOP(r.total)}</strong></td><td class="num">${formatCOP(r.ticket_promedio)}</td></tr>
    </tbody></table>`;
}

function configurarFiltrosReporte() {
  document.querySelectorAll('.segmentado button').forEach(b => b.addEventListener('click', () => {
    periodoReporte = b.dataset.periodo;
    document.querySelectorAll('.segmentado button').forEach(x => x.classList.toggle('activo', x === b));
    // Al cambiar de período se vuelve al rango por defecto (30 días / 12 semanas / 12 meses)
    document.getElementById('repDesde').value = '';
    document.getElementById('repHasta').value = '';
    cargarReportes();
  }));
  document.getElementById('repDesde').addEventListener('change', cargarReportes);
  document.getElementById('repHasta').addEventListener('change', cargarReportes);
}

// ============================================================
// INICIO
// ============================================================
(async () => {
  datos.yo = await requerirSesion(['Administrador']);
  document.getElementById('userBadge').innerHTML = `<i class="ti ti-user"></i> ${esc(datos.yo.nombre)}`;
  document.getElementById('fechaHoy').textContent = new Date().toLocaleDateString('es-CO',
    { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });
  document.getElementById('fPedFecha').value = hoyISO();
  for (const id of ['fPedFecha', 'fPedEstado', 'fPedMesa']) document.getElementById(id).addEventListener('change', cargarPedidos);
  let espera;
  document.getElementById('fPedNumero').addEventListener('input', () => { clearTimeout(espera); espera = setTimeout(cargarPedidos, 350); });
  document.getElementById('fProdTexto').addEventListener('input', pintarProductos);
  document.getElementById('fProdCategoria').addEventListener('change', pintarProductos);
  configurarFiltrosReporte();
  document.getElementById('modal').addEventListener('click', e => { if (e.target.id === 'modal') cerrarModal(); });
  document.addEventListener('keydown', e => { if (e.key === 'Escape') cerrarModal(); });
  mostrarSeccion(location.hash.slice(1) || 'dashboard');
})();
