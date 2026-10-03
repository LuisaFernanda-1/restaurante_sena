"""
servidor.py — Arranque de PRODUCCIÓN de Restaurante SENA con Waitress

    python servidor.py          (o scripts\\iniciar_servidor.ps1)

Escucha en 0.0.0.0:8000 (todas las tarjetas de red) para que los
celulares del restaurante puedan entrar. El registro se guarda en
logs/servidor.log (un archivo por día, se conservan 30 días).
"""

import logging
import logging.handlers
import os
import sys

import config

HOST = "0.0.0.0"
PUERTO = int(os.environ.get("PUERTO", "8000"))
HILOS = 8


def configurar_registro():
    carpeta = config.PROYECTO_DIR / "logs"
    carpeta.mkdir(exist_ok=True)
    formato = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    archivo = logging.handlers.TimedRotatingFileHandler(
        carpeta / "servidor.log", when="midnight", backupCount=30, encoding="utf-8")
    archivo.setFormatter(formato)
    consola = logging.StreamHandler(sys.stdout)
    consola.setFormatter(formato)
    raiz = logging.getLogger()
    raiz.setLevel(logging.INFO)
    raiz.addHandler(archivo)
    raiz.addHandler(consola)


def main():
    configurar_registro()
    log = logging.getLogger("restaurante.servidor")

    import db
    from app import app
    from waitress import serve

    if not db.probar_conexion():
        log.error("No hay conexión con MySQL (%s:%s, base %s). Inicie MySQL desde el panel de XAMPP "
                  "y revise backend/.env.", config.DB_HOST, config.DB_PORT, config.DB_NAME)
        return 1

    print("=" * 62)
    print("  Restaurante SENA — servidor en funcionamiento")
    print(f"  En este computador:   http://localhost:{PUERTO}")
    print(f"  Desde los celulares:  {config.SERVER_URL}")
    print(f"  Personal:             {config.SERVER_URL}/login.html")
    print("  Para detenerlo cierre esta ventana o presione Ctrl+C.")
    print("=" * 62)
    log.info("Servidor iniciado en %s:%s (base %s)", HOST, PUERTO, config.DB_NAME)
    serve(app, host=HOST, port=PUERTO, threads=HILOS, ident="RestauranteSENA")
    return 0


if __name__ == "__main__":
    sys.exit(main())
