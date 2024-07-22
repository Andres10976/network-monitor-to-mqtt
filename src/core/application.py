import threading
import logging
from src.models.config_schema import ConfigSchema
from src.mqtt.mqtt_handler import MqttHandler
from src.core.ping_monitor import PingMonitor
from src.utils.queue_operations import SafeQueue
from src.utils.thread_manager import ThreadManager
from src.utils.queue_manager import QueueManager

class Application:
    def __init__(self, config: ConfigSchema):
        self.config = config
        self.queue = SafeQueue()
        self.mqtt_handler = MqttHandler(self.config, self.queue)
        self.ping_monitor = PingMonitor(self.config, self.queue)
        self.shutdown_flag = threading.Event()
        self.thread_manager = ThreadManager(self.shutdown_flag)
        self.queue_manager = QueueManager(self.queue, "queue_backup.pkl")

    def start(self):
        self.queue_manager.load_queue()

        threads = [
            threading.Thread(target=self.ping_monitor.run, args=(self.shutdown_flag,)),
            threading.Thread(target=self.mqtt_handler.listen_to_mqtt, args=(self.shutdown_flag,)),
            threading.Thread(target=self.queue_manager.save_queue_periodically, args=(self.shutdown_flag,)),
        ]

        self.thread_manager.start_threads(threads)

        try:
            self.thread_manager.monitor_threads()
        except KeyboardInterrupt:
            logging.info("Program terminated by user")
        finally:
            self.shutdown()

    def shutdown(self):
        logging.info("Initiating graceful shutdown...")
        self.thread_manager.stop_threads()
        self.queue_manager.save_queue()
        self.mqtt_handler.disconnect()
        logging.info("Graceful shutdown completed")