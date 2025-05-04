# In logger_config.py
import logging
import os
from utils.config import LOGS_DIR  # Add this import

def setup_logger():
    """Konfiguriert und gibt den Logger zurück"""
    # Create logs directory if it doesn't exist
    os.makedirs(LOGS_DIR, exist_ok=True)

    log_file_path = os.path.join(LOGS_DIR, "jira_scraper.log")

    # Konfiguriere das Logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file_path),  # Use the path with LOGS_DIR
            logging.StreamHandler()
        ]
    )
    return logging.getLogger("jira_scraper")
    
# Erstelle eine globale Logger-Instanz, die überall importiert werden kann
logger = setup_logger()
