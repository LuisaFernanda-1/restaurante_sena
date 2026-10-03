/**
 * qr.js — Códigos QR generados en el navegador (usa js/vendor/qrcode-generator.js, licencia MIT)
 *
 *   QR de una mesa:        SERVER_URL/menu.html?mesa=N&c=<código secreto de la mesa>
 *   QR de un comprobante:  SERVER_URL/verificar.html?c=<código de verificación>
 *
 * SVG para mostrar e imprimir (se escala sin perder nitidez) y PNG para
 * descargar. El PNG se codifica aquí mismo, sin depender del canvas.
 */

const QR = {
  COLOR: '#004d26',

  /** Dirección base del sistema: SERVER_URL o, si falta, la carpeta de esta página. */
  base(serverUrl) {
    if (serverUrl) return String(serverUrl).replace(/\/+$/, '');
    return window.location.href.replace(/[?#].*$/, '').replace(/\/[^/]*$/, '');
  },

  urlMesa(serverUrl, numero, codigo) {
    return `${this.base(serverUrl)}/menu.html?mesa=${numero}&c=${encodeURIComponent(codigo)}`;
  },

  urlVerificacion(serverUrl, codigo) {
    return `${this.base(serverUrl)}/verificar.html?c=${encodeURIComponent(codigo)}`;
  },

  /** Matriz del QR (corrección de errores M: soporta manchas pequeñas en la tarjeta). */
  matriz(texto) {
    const q = qrcode(0, 'M');
    q.addData(texto);
    q.make();
    return q;
  },

  /** SVG escalable con 4 módulos de margen blanco (lo que exige la norma QR). */
  svg(texto, etiqueta = 'Código QR') {
    const q = this.matriz(texto);
    const n = q.getModuleCount();
    const borde = 4;
    const lado = n + borde * 2;
    let trazo = '';
    for (let f = 0; f < n; f++) {
      for (let c = 0; c < n; c++) {
        if (q.isDark(f, c)) trazo += `M${c + borde} ${f + borde}h1v1h-1z`;
      }
    }
    const titulo = String(etiqueta).replace(/[<>&"]/g, '');
    return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${lado} ${lado}" role="img" aria-label="${titulo}"
      shape-rendering="crispEdges"><title>${titulo}</title><rect width="${lado}" height="${lado}" fill="#fff"/>
      <path d="${trazo}" fill="${this.COLOR}"/></svg>`;
  },

  /** PNG en escala de grises: devuelve un Uint8Array con el archivo. */
  png(texto, escala = 10) {
    const q = this.matriz(texto);
    const n = q.getModuleCount();
    const borde = 4;
    const lado = (n + borde * 2) * escala;
    const oscuro = 0x26;   // verde muy oscuro convertido a gris: contraste alto
    const filas = new Uint8Array(lado * (lado + 1));
    for (let y = 0; y < lado; y++) {
      const base = y * (lado + 1);
      filas[base] = 0;   // filtro "ninguno" de cada fila PNG
      const f = Math.floor(y / escala) - borde;
      for (let x = 0; x < lado; x++) {
        const c = Math.floor(x / escala) - borde;
        const negro = f >= 0 && f < n && c >= 0 && c < n && q.isDark(f, c);
        filas[base + 1 + x] = negro ? oscuro : 0xff;
      }
    }
    return this._codificarPNG(lado, lado, filas);
  },

  /** Descarga el PNG del QR con el nombre indicado. */
  descargarPNG(texto, nombre) {
    const blob = new Blob([this.png(texto)], { type: 'image/png' });
    const enlace = document.createElement('a');
    enlace.href = URL.createObjectURL(blob);
    enlace.download = nombre;
    document.body.appendChild(enlace);
    enlace.click();
    setTimeout(() => { URL.revokeObjectURL(enlace.href); enlace.remove(); }, 1000);
  },

  // ------------------------------------------------------------
  // Codificador PNG mínimo (zlib con bloques "almacenados", sin compresión)
  // ------------------------------------------------------------
  _crcTabla: null,

  _crc32(bytes) {
    if (!this._crcTabla) {
      this._crcTabla = new Uint32Array(256);
      for (let i = 0; i < 256; i++) {
        let c = i;
        for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
        this._crcTabla[i] = c >>> 0;
      }
    }
    let crc = 0xffffffff;
    for (let i = 0; i < bytes.length; i++) crc = this._crcTabla[(crc ^ bytes[i]) & 0xff] ^ (crc >>> 8);
    return (crc ^ 0xffffffff) >>> 0;
  },

  _zlibAlmacenado(datos) {
    const bloques = Math.ceil(datos.length / 65535) || 1;
    const salida = new Uint8Array(2 + datos.length + bloques * 5 + 4);
    let p = 0;
    salida[p++] = 0x78; salida[p++] = 0x01;
    for (let i = 0; i < bloques; i++) {
      const inicio = i * 65535;
      const largo = Math.min(65535, datos.length - inicio);
      salida[p++] = i === bloques - 1 ? 1 : 0;
      salida[p++] = largo & 0xff; salida[p++] = largo >>> 8;
      salida[p++] = ~largo & 0xff; salida[p++] = (~largo >>> 8) & 0xff;
      salida.set(datos.subarray(inicio, inicio + largo), p);
      p += largo;
    }
    let a = 1, b = 0;   // Adler-32
    for (let i = 0; i < datos.length; i++) { a = (a + datos[i]) % 65521; b = (b + a) % 65521; }
    const adler = ((b << 16) | a) >>> 0;
    salida[p++] = adler >>> 24; salida[p++] = (adler >>> 16) & 0xff; salida[p++] = (adler >>> 8) & 0xff; salida[p++] = adler & 0xff;
    return salida;
  },

  _codificarPNG(ancho, alto, filas) {
    const trozo = (tipo, datos) => {
      const t = new Uint8Array(4 + tipo.length + datos.length + 4);
      const v = new DataView(t.buffer);
      v.setUint32(0, datos.length);
      for (let i = 0; i < 4; i++) t[4 + i] = tipo.charCodeAt(i);
      t.set(datos, 8);
      v.setUint32(8 + datos.length, this._crc32(t.subarray(4, 8 + datos.length)));
      return t;
    };
    const ihdr = new Uint8Array(13);
    const v = new DataView(ihdr.buffer);
    v.setUint32(0, ancho); v.setUint32(4, alto);
    ihdr[8] = 8; ihdr[9] = 0;   // 8 bits, escala de grises
    const partes = [new Uint8Array([137, 80, 78, 71, 13, 10, 26, 10]), trozo('IHDR', ihdr),
                    trozo('IDAT', this._zlibAlmacenado(filas)), trozo('IEND', new Uint8Array(0))];
    const total = new Uint8Array(partes.reduce((s, x) => s + x.length, 0));
    let p = 0;
    for (const x of partes) { total.set(x, p); p += x.length; }
    return total;
  }
};

if (typeof module !== 'undefined') module.exports = QR;   // para las pruebas en Node
