import queue
import logging
from typing import Any, List

logger = logging.getLogger(__name__)

class SafeQueue(queue.Queue):
    def __init__(self, maxsize: int = 0):
        super().__init__(maxsize)
        self.is_serial_connected = False

    def save_to_file(self, file_path: str) -> None:
        from utils.file_operations import save_to_file
        with self.mutex:
            save_to_file(list(self.queue), file_path)

    def load_from_file(self, file_path: str) -> None:
        from utils.file_operations import load_from_file
        with self.mutex:
            try:
                items: List[Any] = load_from_file(file_path)
                for item in items:
                    self.put(item)
            except FileNotFoundError:
                logger.warning(f"File {file_path} not found. Creating a new queue.")
            except EOFError:
                logger.debug("No pending events or reports")
            except Exception as e:
                logger.error(f"Unknown error loading queue: {e}")