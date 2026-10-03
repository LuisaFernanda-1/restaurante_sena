"""
restaurar.py — Restaura un respaldo de la base de datos de Restaurante SENA

    backend\\.venv\\Scripts\\python.exe scripts\\restaurar.py
        → restaura el respaldo MÁS RECIENTE de la carpeta respaldos\\
    backend\\.venv\\Scripts\\python.exe scripts\\restaurar.py respaldos\\restaurante_sena_20261003_230000.sql.gz
    backend\\.venv\\Scripts\\python.exe scripts\\restaurar.py --bd restaurante_sena_prueba ARCHIVO
        → restaura en otra base (sirve para revisar un respaldo sin tocar la real)

¡ATENCIÓN! Reemplaza las tablas de la base de destino. Antes de restaurar
sobre la base en uso, este script hace un respaldo de seguridad de su
estado actual (se puede omitir con --sin-respaldo).
"""

import argparse
import gzip
import re
import subprocess
import sys
from pathlib import Path

import respaldo
from respaldo import ErrorRespaldo, buscar_programa, conexion_args, entorno_mysql

import config

_RE_DEFINER = re.compile(rb"DEFINER=`[^`]*`@`[^`]*`\s*")
_RE_NOMBRE_BD = re.compile(r"^[A-Za-z0-9_]{1,64}$")


def ultimo_respaldo(carpeta=respaldo.CARPETA_POR_DEFECTO):
    archivos = sorted(Path(carpeta).glob(f"{respaldo.PREFIJO}*.sql.gz"))
    if not archivos:
        raise ErrorRespaldo(f"No hay respaldos en {carpeta}")
    return archivos[-1]


def restaurar(archivo, bd=None):
    bd = bd or config.DB_NAME
    if not _RE_NOMBRE_BD.match(bd):
        raise ErrorRespaldo("Nombre de base de datos inválido.")
    archivo = Path(archivo)
    if not archivo.exists():
        raise ErrorRespaldo(f"No existe el archivo {archivo}")
    mysql = buscar_programa("mysql")
    base = [mysql, *conexion_args(), "--default-character-set=utf8mb4"]

    crear = subprocess.run(
        [*base, "-e", f"CREATE DATABASE IF NOT EXISTS `{bd}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"],
        capture_output=True, env=entorno_mysql())
    if crear.returncode != 0:
        raise ErrorRespaldo(crear.stderr.decode("utf-8", "replace").strip())

    proceso = subprocess.Popen([*base, bd], stdin=subprocess.PIPE, stderr=subprocess.PIPE, env=entorno_mysql())
    try:
        with gzip.open(archivo, "rb") as entrada:
            for linea in entrada:
                # Los DEFINER de las vistas pueden no existir en otro servidor: se quitan.
                proceso.stdin.write(_RE_DEFINER.sub(b"", linea))
        proceso.stdin.close()
    except (OSError, EOFError) as e:
        proceso.kill()
        raise ErrorRespaldo(f"No se pudo leer el respaldo: {e}")
    error = proceso.stderr.read().decode("utf-8", "replace").strip()
    proceso.wait()
    if proceso.returncode != 0:
        raise ErrorRespaldo(f"La restauración falló: {error}")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Restaurar un respaldo de Restaurante SENA")
    parser.add_argument("archivo", nargs="?", help="Respaldo .sql.gz (por defecto, el más reciente)")
    parser.add_argument("--bd", default=config.DB_NAME, help=f"Base de destino (por defecto {config.DB_NAME})")
    parser.add_argument("--si", action="store_true", help="No pedir confirmación")
    parser.add_argument("--sin-respaldo", action="store_true", help="No respaldar antes el estado actual")
    args = parser.parse_args(argv)
    respaldo.configurar_registro()
    try:
        archivo = Path(args.archivo) if args.archivo else ultimo_respaldo()
        print(f"Respaldo:          {archivo}")
        print(f"Base de destino:   {args.bd} @ {config.DB_HOST}:{config.DB_PORT}")
        if not args.si:
            print("\n¡ATENCIÓN! Se reemplazarán los datos actuales de esa base.")
            if input(f"Escriba el nombre de la base ({args.bd}) para confirmar: ").strip() != args.bd:
                print("Cancelado.")
                return 1
        if not args.sin_respaldo and args.bd == config.DB_NAME:
            seguridad = respaldo.hacer_respaldo()
            print(f"Respaldo de seguridad del estado actual: {seguridad}")
        restaurar(archivo, args.bd)
    except (ErrorRespaldo, OSError) as e:
        respaldo.log.error("ERROR: %s", e)
        return 1
    respaldo.log.info("Restauración completada en la base '%s' desde %s", args.bd, archivo.name)
    print("Listo. Reinicie el servidor si estaba en funcionamiento.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
