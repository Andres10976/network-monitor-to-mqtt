import pickle
import logging

def save_to_file(data, file_path):
    try:
        with open(file_path, 'wb') as file:
            pickle.dump(data, file)
        #logging.info(f"Data successfully saved to {file_path}")
    except Exception as e:
        logging.error(f"Error saving data to {file_path}: {e}")

def load_from_file(file_path):
    try:
        with open(file_path, 'rb') as file:
            data = pickle.load(file)
        logging.info(f"Data successfully loaded from {file_path}")
        return data
    except FileNotFoundError:
        logging.warning(f"File {file_path} not found. Creating a new queue.")
        return []
    except Exception as e:
        logging.error(f"Error loading data from {file_path}: {e}")
        return []