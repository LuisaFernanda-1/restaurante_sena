"""errores.py — Error controlado que la API devuelve con un mensaje claro."""


class ErrorAPI(Exception):
    def __init__(self, msg, status=400, codigo=None):
        super().__init__(msg)
        self.msg = msg
        self.status = status
        # Código opcional para que el frontend reaccione (p. ej. "cambiar_clave")
        self.codigo = codigo
