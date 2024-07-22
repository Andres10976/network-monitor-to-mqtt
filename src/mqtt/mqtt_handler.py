import paho.mqtt.client as mqtt
from collections import OrderedDict
from classes.enums import PublishType
from utils.queue_operations import SafeQueue
import json
import logging
from typing import Dict, Any
import threading

class MqttHandler:
    def __init__(self, config: Dict[str, Any], queue: SafeQueue):
        self.config = config
        self.client: mqtt.Client | None = None
        self.queue = queue
        self.logger = logging.getLogger(__name__)
        self.attempt_count = 0
        self.is_connected = False

    def connect(self) -> None:
        try:
            self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=self._get_client_id())
            self.client.username_pw_set(username=self.config["mqtt"]["usuario"], password=self.config["mqtt"]["contrasena"])
            self.client.tls_set()
            self.client.will_set(self._get_will_topic(), payload=self._get_will_message(), qos=2, retain=True)
            self.client.connect(self.config["mqtt"]["url"], self.config["mqtt"]["puerto"])
            self.client.on_message = self.on_message
            self.client.on_connect = self.on_connect
            self.client.on_disconnect = self.on_disconnect
            self.client.loop_start()
            self.attempt_count = 0
            self.is_connected = True
        except KeyError as e:
            raise KeyError(f"Configuration error: missing key {e}")
        except Exception as e:
            self.logger.error("An error occurred initializing the MQTT connection. Verify the credentials and broker data.")
            self.is_connected = False
            raise ConnectionError(f"Error initializing MQTT connection: {e}")
        
    def disconnect(self) -> None:
        if self.client and self.is_connected:
            try:
                # Publish the last will message before disconnecting
                self._publish(self._get_will_message(), PublishType.ESTADO)
                self.client.disconnect()
                self.client.loop_stop()
                self.is_connected = False
                self.logger.info("Successfully disconnected from MQTT broker")
            except Exception as e:
                self.logger.error(f"Error disconnecting from MQTT broker: {e}")

    def _get_client_id(self) -> str:
        return f"{self.config['cliente']['id_cliente']}_{self.config['cliente']['id_panel']}_FACP"

    def _get_will_topic(self) -> str:
        return f"{self.config['cliente']['id_cliente']}/FACP/{self.config['cliente']['id_panel']}/Estado"
    
    def on_message(self, client: mqtt.Client, userdata: Any, msg: mqtt.MQTTMessage) -> None:
        self.logger.info(f"Message received on topic {msg.topic}: {msg.payload}")

    def on_connect(self, client: mqtt.Client, userdata: Any, flags: Dict[str, int], reason_code: int, properties: Any) -> None:
        if reason_code == 0:
            self.is_connected = True
            self.logger.info("Successfully connected to MQTT broker")
            self._publish_connected_message()
            self.attempt_count = 0
        else:
            self.logger.error(f"Failed to connect to MQTT broker with error code {reason_code}")

    def on_disconnect(self, client: mqtt.Client, userdata: Any, flags: Dict[str, int], reason_code: int, properties: Any) -> None:
        self.is_connected = False
        self.logger.warning(f"Disconnected from MQTT broker with return code {reason_code}")
        if reason_code != 0:
            self.logger.info("Unexpected disconnection, attempting to reconnect...")

    def _get_will_message(self) -> str:
        return json.dumps(OrderedDict([
            ("ID_Cliente", self.config["cliente"]["id_cliente"]),
            ("ID_SBC", self.config["cliente"]["id_sbc"]),
            ("Mensaje", "Desconectado"),
            ("Tipo", "Estado"),
            ("Nivel_Severidad", 4),
            ("latitud", self.config["cliente"]["coordenadas"]["latitud"]),
            ("longitud", self.config["cliente"]["coordenadas"]["longitud"])
        ]))

    def _publish_connected_message(self) -> None:
        try:
            message = json.dumps(OrderedDict([
                ("ID_Cliente", self.config["cliente"]["id_cliente"]),
                ("ID_SBC", self.config["cliente"]["id_sbc"]),
                ("Mensaje", "Conectado" if self.queue.is_serial_connected else "Fallo serial"),
                ("Tipo", "Estado"),
                ("Nivel_Severidad", 0 if self.queue.is_serial_connected else 5),
                ("latitud", self.config["cliente"]["coordenadas"]["latitud"]),
                ("longitud", self.config["cliente"]["coordenadas"]["longitud"])
            ]))
            self._publish(message, PublishType.ESTADO)
        except KeyError as e:
            raise KeyError(f"Configuration error: missing key {e}")
        except json.JSONDecodeError as e:
            raise ValueError(f"Error generating JSON message: {e}")
        except Exception as e:
            raise ConnectionError(f"An unexpected error occurred while trying to create the 'Connected' status message {e}")

    def _get_publish_topic(self, pub_type: PublishType) -> str:
        base_topic = f"{self.config['cliente']['id_cliente']}/Network"
        match pub_type:
            case PublishType.EVENTO:
                return f"{base_topic}/Eventos"
            case PublishType.ESTADO:
                return f"{base_topic}/Estado"
            case _:
                raise ValueError("Invalid publication type entered")

    def _publish(self, message: str, pub_type: PublishType) -> None:
        if self.client is None:
            raise ConnectionError("MQTT client is not initialized")
        try:
            topic = self._get_publish_topic(pub_type)
            qos = 2
            retain = True
            self.client.publish(topic, message, qos=qos, retain=retain)
            self.logger.debug("Successfully published a message to the MQTT broker")
        except Exception as e:
            raise ConnectionError(f"Error attempting to publish message to MQTT broker: {e}")

    def _process_queue_messages(self) -> bool:
        while not self.queue.empty():
            if not self.is_connected:
                return False
            else:
                pub_type, message_data = self.queue.get()
                try:
                    self._publish(message_data, pub_type)
                except ConnectionError as e:
                    self.logger.error(f"Lost connection while publishing, re-queueing message: {e}")
                    self.queue.put((pub_type, message_data))
                    return False
                except Exception as e:
                    self.logger.error(f"An unknown error occurred while trying to publish the message, re-queueing message: {e}")
                    self.queue.put((pub_type, message_data))
                    return False
        return True

    def listen_to_mqtt(self, shutdown_flag: threading.Event) -> None:
        while not shutdown_flag.is_set():
            try:
                if self.client is None or not self.is_connected:
                    if self.client is not None:
                        self.client.loop_stop()
                        self.client = None
                    self.logger.debug(f"Attempting to connect to MQTT broker, attempt #{self.attempt_count + 1}")
                    self.connect()
                    self.attempt_count += 1
                    if shutdown_flag.wait(min(60, 2 ** self.attempt_count)):
                        break
                if self.client is not None:
                    if not self._process_queue_messages():
                        self.logger.debug("Lost connection to MQTT broker. Restarting connection")
                        self.client.loop_stop()
                        self.client = None
                    else:
                        if shutdown_flag.wait(1):
                            break
            except Exception as e:
                self.logger.debug(f"From general Exception, attempting to connect to MQTT broker, attempt #{self.attempt_count + 1}")
                self.attempt_count += 1
                if shutdown_flag.wait(min(60, 2 ** self.attempt_count)):
                    break
                self.logger.error(f"Unexpected error occurred. Attempting to connect to MQTT broker again: {e}")
        
        if self.client:
            self.disconnect()