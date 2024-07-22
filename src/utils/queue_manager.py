import threading
from src.utils.file_operations import save_to_file, load_from_file
import logging
import os

class QueueManager:
    def __init__(self, queue, queue_file_path):
        self.queue = queue
        self.queue_file_path = queue_file_path

    def save_queue_periodically(self, shutdown_flag: threading.Event):
        while not shutdown_flag.is_set():
            self.save_queue()
            if shutdown_flag.wait(5):
                break

    def save_queue(self):
        save_to_file(list(self.queue.queue), self.queue_file_path)

    def load_queue(self):
        if os.path.exists(self.queue_file_path):
            loaded_queue = load_from_file(self.queue_file_path)
            for item in loaded_queue:
                self.queue.put(item)
            logging.info(f"Loaded {len(loaded_queue)} items from queue backup")