from pydantic import BaseModel
from typing import List

class MqttConfig(BaseModel):
    usuario: str
    contrasena: str
    url: str
    puerto: int

class DeviceConfig(BaseModel):
    ip: str
    name: str

class MonitorConfig(BaseModel):
    retry_attempts: int
    retry_interval: float
    iteration_interval: float

class Coordinates(BaseModel):
    latitud: float
    longitud: float

class ClientConfig(BaseModel):
    id_cliente: str
    id_sbc: int
    coordenadas: Coordinates

class ConfigSchema(BaseModel):
    mqtt: MqttConfig
    devices: List[DeviceConfig]
    monitor: MonitorConfig
    client: ClientConfig