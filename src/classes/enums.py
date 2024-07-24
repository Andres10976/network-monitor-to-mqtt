from enum import Enum

class PublishType(Enum):
    EVENTO = 1
    ESTADO = 3

class SeverityLevel(Enum):
    ONLINE = 0
    NOTIFICACION = 1
    MEDIO = 2
    DESCONEXION = 4
    SEVERO = 6