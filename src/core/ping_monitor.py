import time
from ping3 import ping
from typing import Dict, Any
import logging
from src.utils.queue_operations import SafeQueue
from src.models.config_schema import ConfigSchema
from classes.enums import PublishType

class PingMonitor:
    def __init__(self, config: ConfigSchema, queue: SafeQueue):
        self.config = config
        self.queue = queue
        self.logger = logging.getLogger(__name__)

    def ping_device(self, device: Dict[str, str]) -> bool:
        for attempt in range(self.config.monitor.retry_attempts):
            if ping(device['ip']):
                return True
            time.sleep(self.config.monitor.retry_interval)
        return False

    def run(self, shutdown_flag):
        self.logger.info("Starting network monitoring...")
        while not shutdown_flag.is_set():
            for device in self.config.devices:
                if shutdown_flag.is_set():
                    break
                if not self.ping_device(device):
                    self.logger.warning(f"Device {device['name']} ({device['ip']}) is not responsive")
                    message = {
                        "ip": device['ip'],
                        "name": device['name'],
                        "status": "offline"
                    }
                    self.queue.put((PublishType.ESTADO, message))
                else:
                    message = {
                        "ip": device['ip'],
                        "name": device['name'],
                        "status": "online"
                    }
                    self.queue.put((PublishType.ESTADO, message))

            self.logger.info(f"Sleeping for {self.config.monitor.iteration_interval} seconds before next iteration")
            time.sleep(self.config.monitor.iteration_interval)

        self.logger.info("Network monitoring stopped.")