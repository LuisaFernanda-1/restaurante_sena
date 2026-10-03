"""
seguridad.py — Contraseñas, sesiones y permisos por rol

- Contraseñas con werkzeug.security (hash con sal, scrypt).
- Los hashes SHA-256 sin sal de la versión anterior se aceptan una sola
  vez y se reemplazan automáticamente por uno seguro al iniciar sesión.
- @requiere_rol(...): sin sesión → 401; rol incorrecto → 403.
- En cada petición se verifica contra la base de datos que el usuario
  siga activo y que su contraseña no haya cambiado; si cambió, las
  sesiones anteriores dejan de valer.
"""

import hashlib
import hmac
import re
import secrets
import threading
import time
from functools import wraps

from flask import g, session
from werkzeug.security import check_password_hash, generate_password_hash

import db
from errores import ErrorAPI

ROL_ADMIN = "Administrador"
ROL_CHEF = "Chef"
ROL_MESERO = "Mesero"
ROLES_PERSONAL = (ROL_ADMIN, ROL_CHEF, ROL_MESERO)

DURACION_SESION = 12 * 3600            # una jornada de trabajo
DURACION_SESION_RECORDADA = 7 * 24 * 3600

# Hash de relleno: se usa cuando el usuario no existe para que la
# respuesta tarde lo mismo y no revele qué usuarios existen.
_HASH_RELLENO = generate_password_hash("relleno-para-igualar-tiempos")
_RE_SHA256 = re.compile(r"^[0-9a-f]{64}$")


# ------------------------------------------------------------
# Contraseñas
# ------------------------------------------------------------
def crear_hash(password):
    return generate_password_hash(password)


def verificar_clave(hash_guardado, password):
    """Devuelve (correcta, hay_que_actualizar_el_hash)."""
    if hash_guardado and _RE_SHA256.match(hash_guardado):
        # Formato antiguo (SHA-256 sin sal)
        calculado = hashlib.sha256(password.encode("utf-8")).hexdigest()
        return hmac.compare_digest(calculado, hash_guardado), True
    return check_password_hash(hash_guardado or _HASH_RELLENO, password), False


def validar_clave_nueva(nueva, usuario=""):
    if not isinstance(nueva, str) or len(nueva) < 8:
        raise ErrorAPI("La contraseña debe tener al menos 8 caracteres.")
    if len(nueva) > 128:
        raise ErrorAPI("La contraseña es demasiado larga (máximo 128 caracteres).")
    if not re.search(r"[A-Za-zÁÉÍÓÚáéíóúÑñ]", nueva) or not re.search(r"\d", nueva):
        raise ErrorAPI("La contraseña debe tener letras y números.")
    if usuario and usuario.lower() in nueva.lower():
        raise ErrorAPI("La contraseña no puede contener el nombre de usuario.")
    if "temporal" in nueva.lower():
        raise ErrorAPI("Elija una contraseña distinta a la temporal.")


_ALFABETO_CLAVE = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"  # sin 0/O, 1/l/I


def generar_clave_temporal():
    """Contraseña temporal aleatoria, fácil de dictar: p. ej. 'Temporal-Xk7p-9mQa'."""
    bloque = lambda: "".join(secrets.choice(_ALFABETO_CLAVE) for _ in range(4))  # noqa: E731
    return f"Temporal-{bloque()}-{bloque()}"


def huella(hash_guardado):
    """Fragmento del hash guardado en la sesión: si la contraseña cambia, no coincide."""
    return hashlib.sha256(hash_guardado.encode("utf-8")).hexdigest()[:16]


# ------------------------------------------------------------
# Límite de intentos de inicio de sesión
# ------------------------------------------------------------
class LimitadorIntentos:
    """Bloquea 15 minutos tras 5 intentos fallidos (por IP y usuario)."""

    def __init__(self, maximo=5, ventana=15 * 60):
        self.maximo = maximo
        self.ventana = ventana
        self._fallos = {}
        self._lock = threading.Lock()

    def _vigentes(self, clave, ahora):
        fallos = [t for t in self._fallos.get(clave, []) if ahora - t < self.ventana]
        if fallos:
            self._fallos[clave] = fallos
        else:
            self._fallos.pop(clave, None)
        return fallos

    def bloqueado(self, clave):
        with self._lock:
            fallos = self._vigentes(clave, time.time())
            if len(fallos) >= self.maximo:
                return int(self.ventana - (time.time() - fallos[0])) // 60 + 1
            return 0

    def fallo(self, clave):
        with self._lock:
            self._fallos.setdefault(clave, []).append(time.time())

    registrar = fallo  # para contar eventos que no son fallos (p. ej. pedidos)

    def limpiar(self, clave=None):
        with self._lock:
            if clave is None:
                self._fallos.clear()
            else:
                self._fallos.pop(clave, None)


limitador_login = LimitadorIntentos()
# Crear pedidos es público: se limita por IP para evitar abusos en la red.
limitador_pedidos = LimitadorIntentos(maximo=20, ventana=10 * 60)
limitador_llamados = LimitadorIntentos(maximo=10, ventana=10 * 60)


# ------------------------------------------------------------
# Sesión
# ------------------------------------------------------------
def iniciar_sesion(usuario, recordar=False):
    session.clear()
    session.permanent = bool(recordar)
    session["user_id"] = usuario["id_usuario"]
    session["huella"] = huella(usuario["contrasena_hash"])
    session["expira"] = int(time.time()) + (DURACION_SESION_RECORDADA if recordar else DURACION_SESION)


def usuario_actual():
    """Usuario de la sesión, validado contra la base de datos (o None)."""
    if "usuario_actual" in g:
        return g.usuario_actual
    g.usuario_actual = None
    uid = session.get("user_id")
    if not uid:
        return None
    if session.get("expira", 0) < time.time():
        session.clear()
        return None
    fila = db.consultar_uno(
        """SELECT u.id_usuario, u.nombre, u.usuario, u.contrasena_hash,
                  u.debe_cambiar_clave, u.activo, r.nombre_rol AS rol
           FROM usuarios u JOIN roles r ON u.id_rol = r.id_rol
           WHERE u.id_usuario = %s""",
        (uid,),
    )
    if (not fila or not fila["activo"]
            or not hmac.compare_digest(session.get("huella", ""), huella(fila["contrasena_hash"]))):
        session.clear()
        return None
    fila["debe_cambiar_clave"] = bool(fila["debe_cambiar_clave"])
    g.usuario_actual = fila
    return fila


def datos_publicos(u):
    return {
        "id": u["id_usuario"],
        "nombre": u["nombre"],
        "usuario": u["usuario"],
        "rol": u["rol"],
        "debe_cambiar_clave": bool(u["debe_cambiar_clave"]),
    }


def requiere_rol(*roles, permitir_cambio_pendiente=False):
    """
    @requiere_rol()                       → cualquier usuario del personal
    @requiere_rol(ROL_ADMIN)              → solo administrador
    @requiere_rol(ROL_ADMIN, ROL_MESERO)  → administrador o mesero
    """
    def decorador(vista):
        @wraps(vista)
        def envoltura(*args, **kwargs):
            u = usuario_actual()
            if not u:
                raise ErrorAPI("Debe iniciar sesión.", 401, "sin_sesion")
            if u["debe_cambiar_clave"] and not permitir_cambio_pendiente:
                raise ErrorAPI("Debe cambiar su contraseña temporal antes de continuar.", 403, "cambiar_clave")
            if roles and u["rol"] not in roles:
                raise ErrorAPI("No tiene permiso para esta acción.", 403, "sin_permiso")
            return vista(*args, **kwargs)
        return envoltura
    return decorador
