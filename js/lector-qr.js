/**
 * lector-qr.js — "Entrar con QR": lee el código QR de la mesa con la cámara
 * dentro de la página (usa js/vendor/jsQR.js, licencia Apache 2.0).
 *
 * Nota: también se puede escanear con la cámara normal del celular, porque
 * el QR ya trae la dirección completa de la mesa.
 */

const LectorQR = {
  /**
   * Revisa que el texto leído sea la dirección de una mesa DE ESTE SITIO:
   *   <sitio>/menu.html?mesa=N&c=<código de 10 caracteres>
   * origenes: direcciones aceptadas (la página actual y SERVER_URL).
   * Devuelve { mesa, codigo } o lanza un Error con un mensaje claro.
   */
  validarEnlace(texto, origenes) {
    let url;
    try {
      url = new URL(String(texto || '').trim());
    } catch (e) {
      throw new Error('Este código QR no es el de una mesa del restaurante.');
    }
    if (url.protocol !== 'http:' && url.protocol !== 'https:') {
      throw new Error('Este código QR no es el de una mesa del restaurante.');
    }
    const permitidos = (origenes || []).filter(Boolean).map(o => {
      try { return new URL(o).origin; } catch (e) { return null; }
    });
    if (!permitidos.includes(url.origin)) {
      throw new Error('Este código QR es de otro sitio, no de este restaurante.');
    }
    if (!/\/menu\.html$/.test(url.pathname)) {
      throw new Error('Este código QR no es el de una mesa del restaurante.');
    }
    const mesa = url.searchParams.get('mesa') || '';
    const codigo = (url.searchParams.get('c') || '').toLowerCase();
    if (!/^\d{1,3}$/.test(mesa) || !/^[0-9a-f]{10}$/.test(codigo)) {
      throw new Error('El código QR de la mesa está incompleto. Pide ayuda al mesero.');
    }
    return { mesa: Number(mesa), codigo };
  },

  /** Dirección relativa de la carta de esa mesa. */
  urlMenu({ mesa, codigo }) {
    return `menu.html?mesa=${mesa}&c=${encodeURIComponent(codigo)}`;
  },

  /** Decodifica una imagen (ImageData o {data, width, height}); devuelve el texto o null. */
  decodificar(imagen) {
    if (typeof jsQR !== 'function') throw new Error('No se cargó el lector de códigos QR.');
    const r = jsQR(imagen.data, imagen.width, imagen.height, { inversionAttempts: 'attemptBoth' });
    return r ? r.data : null;
  },

  // ------------------------------------------------------------
  // Cámara
  // ------------------------------------------------------------
  flujo: null,
  temporizador: null,

  /** ¿El navegador permite usar la cámara aquí? (requiere HTTPS o localhost) */
  camaraDisponible() {
    return Boolean(window.isSecureContext && navigator.mediaDevices && navigator.mediaDevices.getUserMedia);
  },

  /** Mensaje claro según el error de la cámara. */
  mensajeError(error) {
    if (!window.isSecureContext) {
      return 'El navegador solo permite usar la cámara en conexiones seguras (https). ' +
             'Abre la cámara normal de tu celular y apunta al QR, o usa "Entrar sin QR".';
    }
    const nombre = error && error.name;
    if (nombre === 'NotAllowedError' || nombre === 'SecurityError') {
      return 'No diste permiso para usar la cámara. Puedes permitirlo en la configuración del navegador, ' +
             'escanear con la cámara normal del celular o usar "Entrar sin QR".';
    }
    if (nombre === 'NotFoundError' || nombre === 'OverconstrainedError') {
      return 'No encontramos una cámara en este dispositivo. Usa "Entrar sin QR".';
    }
    if (nombre === 'NotReadableError') {
      return 'La cámara está siendo usada por otra aplicación. Ciérrala e intenta de nuevo.';
    }
    return 'No se pudo abrir la cámara. Usa la cámara normal del celular o "Entrar sin QR".';
  },

  /**
   * Abre la cámara en el <video> y busca un QR cada 250 ms.
   * alLeer(texto) se llama con cada código encontrado.
   */
  async iniciar(video, alLeer) {
    if (!this.camaraDisponible()) throw Object.assign(new Error('sin contexto seguro'), { name: 'SecurityError' });
    this.detener();
    this.flujo = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: 'environment' } }, audio: false
    });
    video.srcObject = this.flujo;
    video.setAttribute('playsinline', '');
    await video.play();
    const lienzo = document.createElement('canvas');
    const ctx = lienzo.getContext('2d', { willReadFrequently: true });
    this.temporizador = setInterval(() => {
      if (!video.videoWidth) return;
      // Se reduce la imagen para que la lectura sea rápida en celulares
      const escala = Math.min(1, 640 / video.videoWidth);
      lienzo.width = Math.round(video.videoWidth * escala);
      lienzo.height = Math.round(video.videoHeight * escala);
      ctx.drawImage(video, 0, 0, lienzo.width, lienzo.height);
      const texto = this.decodificar(ctx.getImageData(0, 0, lienzo.width, lienzo.height));
      if (texto) alLeer(texto);
    }, 250);
  },

  detener() {
    clearInterval(this.temporizador);
    this.temporizador = null;
    if (this.flujo) {
      this.flujo.getTracks().forEach(t => t.stop());
      this.flujo = null;
    }
  },

  /** Lee el QR de una foto (input type=file): funciona aunque no haya https. */
  leerArchivo(archivo) {
    return new Promise((resolver, rechazar) => {
      const img = new Image();
      const url = URL.createObjectURL(archivo);
      img.onload = () => {
        URL.revokeObjectURL(url);
        const escala = Math.min(1, 1200 / Math.max(img.width, img.height));
        const lienzo = document.createElement('canvas');
        lienzo.width = Math.round(img.width * escala);
        lienzo.height = Math.round(img.height * escala);
        const ctx = lienzo.getContext('2d');
        ctx.drawImage(img, 0, 0, lienzo.width, lienzo.height);
        resolver(this.decodificar(ctx.getImageData(0, 0, lienzo.width, lienzo.height)));
      };
      img.onerror = () => { URL.revokeObjectURL(url); rechazar(new Error('No se pudo leer la imagen.')); };
      img.src = url;
    });
  }
};

if (typeof module !== 'undefined') module.exports = LectorQR;   // para las pruebas en Node
