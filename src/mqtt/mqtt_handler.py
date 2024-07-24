import paho.mqtt.client as mqtt
from collections import OrderedDict
from src.classes.enums import PublishType, SeverityLevel
from src.utils.queue_operations import SafeQueue
import json
import logging
from typing import Any
import threading
from src.models.config_schema import ConfigSchema

class MqttHandler:
    def __init__(self, config: ConfigSchema, queue: SafeQueue):
        self.config = config
        self.client: mqtt.Client | None = None
        self.queue = queue
        self.logger = logging.getLogger(__name__)
        self.attempt_count = 0
        self.is_connected = False

    def connect(self) -> None:
        try:
            self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=self._get_client_id())
            self.client.username_pw_set(username=self.config.mqtt.usuario, password=self.config.mqtt.contrasena)
            self.client.tls_set()
            self.client.will_set(self._get_will_topic(), payload=json.dumps(self._get_will_message()), qos=2, retain=True)
            self.client.connect(self.config.mqtt.url, self.config.mqtt.puerto)
            self.client.on_message = self.on_message
            self.client.on_connect = self.on_connect
            self.client.on_disconnect = self.on_disconnect
            self.client.loop_start()
            self.attempt_count = 0
            self.is_connected = True
        except Exception as e:
            self.logger.error(f"An error occurred initializing the MQTT connection: {e}")
            self.is_connected = False
            raise ConnectionError(f"Error initializing MQTT connection: {e}")
        
    def disconnect(self) -> None:
        if self.client and self.is_connected:
            try:
                self._publish(self._get_will_message(), PublishType.ESTADO)
                self.client.disconnect()
                self.client.loop_stop()
                self.is_connected = False
                self.logger.info("Successfully disconnected from MQTT broker")
            except Exception as e:
                self.logger.error(f"Error disconnecting from MQTT broker: {e}")

    def _get_client_id(self) -> str:
        return f"{self.config.client.id_client}_{self.config.client.id_sbc}_Network"

    def _get_will_topic(self) -> str:
        return f"{self.config.client.id_client}/SBC/{self.config.client.id_sbc}"
    def on_message(self, client: mqtt.Client, userdata: Any, msg: mqtt.MQTTMessage) -> None:
        self.logger.info(f"Message received on topic {msg.topic}: {msg.payload}")

    def on_connect(self, client: mqtt.Client, userdata: Any, flags: dict, rc: int, properties: Any) -> None:
        if rc == 0:
            self.is_connected = True
            self.logger.info("Successfully connected to MQTT broker")
            self._publish_connected_message()
            self.attempt_count = 0
        else:
            self.logger.error(f"Failed to connect to MQTT broker with error code {rc}")

    def on_disconnect(self, client, userdata, rc, properties=None, reason_code=None):
        self.is_connected = False
        self.logger.warning(f"Disconnected from MQTT broker with return code {rc}")
        if rc != 0:
            self.logger.info("Unexpected disconnection, attempting to reconnect...")
        if reason_code:
            self.logger.info(f"Disconnect reason: {reason_code}")

    def _get_will_message(self) -> OrderedDict:
        return OrderedDict([
            ("ID_Cliente", self.config.client.id_client),
            ("ID_SBC", self.config.client.id_sbc),
            ("Mensaje", "Desconectado"),
            ("Tipo", "Estado"),
            ("Nivel_Severidad", SeverityLevel.DESCONEXION.value)
        ])

    def _publish_connected_message(self) -> None:
        try:
            message = OrderedDict([
                ("ID_Cliente", self.config.client.id_client),
                ("ID_SBC", self.config.client.id_sbc),
                ("Mensaje", "Conectado"),
                ("Tipo", "Estado"),
                ("Nivel_Severidad", SeverityLevel.ONLINE.value)
            ])
            self._publish(message, PublishType.ESTADO)
        except Exception as e:
            raise ConnectionError(f"An unexpected error occurred while trying to create the 'Connected' status message {e}")

    def _get_publish_topic(self, pub_type: PublishType) -> str:
        base_topic = f"{self.config.client.id_client}"
        match pub_type:
            case PublishType.EVENTO:
                return f"{base_topic}/Network/"
            case PublishType.ESTADO:
                return f"{base_topic}/SBC/{self.config.client.id_sbc}"
            case _:
                raise ValueError("Invalid publication type entered")

    def _publish(self, message: OrderedDict, pub_type: PublishType) -> None:
        if self.client is None:
            raise ConnectionError("MQTT client is not initialized")
        try:
            topic = self._get_publish_topic(pub_type)
            if topic[-1] == "/":
                topic = topic + message["Subnet"] + "/" + message["IP"]
            qos = 2
            retain = True
            self.client.publish(topic, json.dumps(message), qos=qos, retain=retain)
            self.logger.debug(f"Successfully published a message to the MQTT broker on topic: {topic}")
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
                self.logger.error(f"Unexpected error occurred. Attempting to connect to MQTT broker again: {e}")
                self.attempt_count += 1
                if shutdown_flag.wait(min(60, 2 ** self.attempt_count)):
                    break
        
        if self.client:
            self.disconnect()