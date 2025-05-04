from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import subprocess
import re
import json
import xml.dom.minidom as md
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup

from utils.logger_config import logger

class BrowserHandler:
    """Klasse zur Verwaltung des Browsers und der Browserinteraktionen."""

    def __init__(self):
        """Initialisiert den BrowserHandler."""
        self.driver = None

    def init_browser(self):
        """
        Initialisiert den Browser mit den optimalen Einstellungen.

        Returns:
            webdriver: Die initialisierte Browser-Instanz
        """
        options = Options()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36")

        self.driver = webdriver.Chrome(options=options)
        self.driver.maximize_window()
        return self.driver

    def press_enter_with_applescript(self):
        """
        Verwendet AppleScript, um die Enter-Taste zu drücken.
        Hilfreich bei Systemdialogen, auf die Selenium keinen Zugriff hat.
        """
        logger.info("Drücke Enter mit AppleScript...")
        applescript = '''
        tell application "System Events"
            keystroke return
        end tell
        '''

        try:
            subprocess.run(["osascript", "-e", applescript],
                          capture_output=True,
                          text=True)
            logger.info("Enter-Taste mit AppleScript gedrückt")
        except Exception as e:
            logger.info(f"Fehler beim Ausführen von AppleScript: {e}")

    def close(self):
        """Schließt den Browser und gibt Ressourcen frei."""
        if self.driver:
            self.driver.quit()
            self.driver = None
            logger.info("Browser geschlossen")


class JiraLoginHandler(BrowserHandler):
    """Spezialisierte Klasse zum Anmelden bei Jira."""

    def __init__(self):
        """Initialisiert den JiraLoginHandler."""
        super().__init__()

    def login(self, url, email):
        """
        Führt den Login-Prozess für Jira durch.

        Args:
            url (str): Die Jira-URL, die geöffnet werden soll
            email (str): Die E-Mail-Adresse für den Login

        Returns:
            bool: True, wenn der Login erfolgreich war, sonst False
        """
        if not self.driver:
            self.init_browser()

        logger.info(f"Öffne URL: {url}")
        self.driver.get(url)

        logger.info("Warte 4 Sekunden auf Anmeldeseite...")
        time.sleep(4)

        try:
            # Windows Account Button klicken
            logger.info("Suche nach Windows Account Button...")
            windows_button = self.driver.find_element(By.XPATH, "//button[contains(text(), 'Windows Account')]")
            windows_button.click()
            logger.info("Windows Account Button geklickt")

            # E-Mail-Feld finden und ausfüllen
            logger.info("Warte auf E-Mail-Eingabeseite...")
            time.sleep(4)

            email_field = WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='email'], input[type='text']"))
            )
            email_field.clear()
            email_field.send_keys(email)
            email_field.send_keys(Keys.RETURN)
            logger.info(f"E-Mail {email} eingegeben und Enter gedrückt")

            # AppleScript für Systemdialog
            logger.info("Warte 8 Sekunden und drücke dann Enter mit AppleScript...")
            time.sleep(8)
            self.press_enter_with_applescript()

            # Warten auf Jira-Seite
            logger.info("Warte auf das Laden der Jira-Seite...")
            time.sleep(7)

            return True

        except Exception as e:
            logger.info(f"Fehler beim Login: {e}")
            return False
