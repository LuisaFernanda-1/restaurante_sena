"""
respaldo.py — Copia de seguridad de la base de datos de Restaurante SENA

    backend\\.venv\\Scripts\\python.exe scripts\\respaldo.py
    backend\\.venv\\Scripts\\python.exe scripts\\respaldo.py --dias 60 --dir D:\\Respaldos

- Usa mysqldump (el de XAMPP por defecto) y guarda el resultado comprimido:
      respaldos/restaurante_sena_AAAAMMDD_HHMMSS.sql.gz
- Borra los respaldos con más de 30 días (configurable con --dias).
- Lee la conexión de backend/.env. La contraseña se pasa por variable de
  entorno, nunca en la línea de comandos.
- Termina con código 0 si todo salió bien y 1 si falló (útil para el
  Programador de tareas de Windows).
"""

import argparse
import gzip
import logging
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "backend"))

import config  # noqa: E402

log = logging.getLogger("restaurante.respaldo")
PREFIJO = "restaurante_sena_"
CARPETA_POR_DEFECTO = RAIZ / "respaldos"
RUTAS_XAMPP = [Path(r"C:\xampp\mysql\bin"), Path(r"D:\xampp\mysql\bin")]


class ErrorRespaldo(Exception):
    pass


def buscar_programa(nombre):
    """Busca mysqldump/mysql: variable de entorno, XAMPP o el PATH."""
    variable = os.environ.get(nombre.upper())
    if variable and Path(variable).exists():
        return variable
    for carpeta in RUTAS_XAMPP:
        candidato = carpeta / f"{nombre}.exe"
        if candidato.exists():
            return str(candidato)
    encontrado = shutil.which(nombre)
    if encontrado:
        return encontrado
    raise ErrorRespaldo(f"No se encontró {nombre}. Instale XAMPP o defina la variable {nombre.upper()} con su ruta.")


def entorno_mysql():
    env = os.environ.copy()
    env["MYSQL_PWD"] = config.DB_PASSWORD or ""
    return env


def conexion_args():
    return ["-h", config.DB_HOST, "-P", str(config.DB_PORT), "-u", config.DB_USER]


def hacer_respaldo(carpeta=CARPETA_POR_DEFECTO, bd=None):
    """Crea el respaldo comprimido y devuelve su ruta."""
    bd = bd or config.DB_NAME
    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    marca = datetime.now().strftime("%Y%m%d_%H%M%S")
    destino = carpeta / f"{PREFIJO}{marca}.sql.gz"
    temporal = destino.with_suffix(".gz.parcial")
    comando = [buscar_programa("mysqldump"), *conexion_args(),
               # --no-tablespaces: así no se necesita el privilegio global PROCESS (MySQL 8)
               "--single-transaction", "--no-tablespaces", "--triggers",
               "--default-character-set=utf8mb4", "--add-drop-table", bd]

    log.info("Respaldando la base '%s' en %s", bd, destino)
    with gzip.open(temporal, "wb", compresslevel=6) as salida:
        proceso = subprocess.Popen(comando, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=entorno_mysql())
        final = b""
        for bloque in iter(lambda: proceso.stdout.read(1024 * 1024), b""):
            salida.write(bloque)
            final = (final + bloque)[-500:]
        error = proceso.stderr.read().decode("utf-8", "replace").strip()
        proceso.wait()

    if proceso.returncode != 0 or b"Dump completed" not in final:
        temporal.unlink(missing_ok=True)
        raise ErrorRespaldo(f"mysqldump falló (código {proceso.returncode}): {error or 'respaldo incompleto'}")
    temporal.replace(destino)
    log.info("Respaldo listo: %s (%.1f KB)", destino.name, destino.stat().st_size / 1024)
    return destino


def limpiar_antiguos(carpeta=CARPETA_POR_DEFECTO, dias=30):
    """Borra los respaldos con más de `dias` días. Devuelve la lista de borrados."""
    limite = time.time() - dias * 86400
    borrados = []
    for archivo in Path(carpeta).glob(f"{PREFIJO}*.sql.gz"):
        if archivo.stat().st_mtime < limite:
            archivo.unlink()
            borrados.append(archivo.name)
    if borrados:
        log.info("Respaldos antiguos eliminados (más de %s días): %s", dias, ", ".join(sorted(borrados)))
    return borrados


def configurar_registro():
    carpeta = RAIZ / "logs"
    carpeta.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(carpeta / "respaldo.log", encoding="utf-8"), logging.StreamHandler(sys.stdout)])


def main(argv=None):
    parser = argparse.ArgumentParser(description="Respaldo de la base de datos de Restaurante SENA")
    parser.add_argument("--dir", default=str(CARPETA_POR_DEFECTO), help="Carpeta de los respaldos")
    parser.add_argument("--dias", type=int, default=30, help="Días que se conservan los respaldos (30)")
    args = parser.parse_args(argv)
    configurar_registro()
    try:
        hacer_respaldo(args.dir)
        limpiar_antiguos(args.dir, args.dias)
    except (ErrorRespaldo, OSError) as e:
        log.error("ERROR: %s", e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
