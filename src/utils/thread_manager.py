import logging
import time

class ThreadManager:
    def __init__(self, shutdown_flag):
        self.threads = []
        self.shutdown_flag = shutdown_flag

    def start_threads(self, threads):
        self.threads = threads
        for thread in self.threads:
            thread.daemon = True
            thread.start()

    def stop_threads(self):
        self.shutdown_flag.set()
        for thread in self.threads:
            thread.join(timeout=10)  # Increased timeout for graceful shutdown
        
        # Check if any threads are still alive
        still_alive = [thread for thread in self.threads if thread.is_alive()]
        if still_alive:
            logging.warning(f"{len(still_alive)} threads did not shut down gracefully")
            for thread in still_alive:
                logging.warning(f"Thread {thread.name} is still running")

    def monitor_threads(self):
        while not self.shutdown_flag.is_set():
            if not all(thread.is_alive() for thread in self.threads):
                logging.error("One of the threads has died. Initiating graceful shutdown.")
                self.shutdown_flag.set()
                break
            time.sleep(5)