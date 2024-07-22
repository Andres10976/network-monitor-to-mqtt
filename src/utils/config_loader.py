import yaml
from typing import Dict, Any
from src.models.config_schema import ConfigSchema

def load_yaml(file_path: str) -> Dict[str, Any]:
    with open(file_path, 'r') as file:
        return yaml.safe_load(file)

def load_and_validate_config(config_path: str) -> ConfigSchema:
    config_data = load_yaml(config_path)
    return ConfigSchema(**config_data)