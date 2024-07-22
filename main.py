import os
from src.utils.config_loader import load_and_validate_config
from src.core.application import Application
import logging

def setup_logging():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

def main():
    setup_logging()

    config_path = os.path.join("config", "config.yml")
    config = load_and_validate_config(config_path)

    app = Application(config)
    app.start()

if __name__ == "__main__":
    main()