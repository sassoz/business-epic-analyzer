"""
Modul zur Handhabung des Browser-basierten JIRA-Logins.

Dieses Modul stellt Klassen zur Verfügung, um eine Selenium-gesteuerte
Browser-Instanz zu verwalten und einen komplexen, mehrstufigen
Authentifizierungsprozess für Jira durchzuführen, der über Microsoft 365
abgewickelt wird.

Es beinhaltet eine Basisklasse `BrowserHandler` für allgemeine Browser-
Interaktionen und eine spezialisierte Klasse `JiraLoginHandler`, die den
spezifischen Login-Flow implementiert. Eine Besonderheit ist die Verwendung
von AppleScript, um macOS-spezifische Systemdialoge (z.B. für die
Zertifikatsauswahl) zu steuern, die für Selenium unzugänglich sind.
"""

import os
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import subprocess
from utils.logger_config import logger

# Note: You need to have python-dotenv installed (`pip install python-dotenv`)
# and a .env file with your JIRA_PASSWORD in the same directory.
load_dotenv()

class BrowserHandler:
    """
    Basisklasse zur Verwaltung des Browsers und der Browserinteraktionen.

    Stellt grundlegende Methoden zur Initialisierung und zum Schließen des
    Selenium WebDrivers sowie Hilfsfunktionen für plattformspezifische
    Interaktionen bereit.
    """

    def __init__(self):
        """Initialisiert den BrowserHandler."""
        self.driver = None

    def init_browser(self):
        """
        Initialisiert den Chrome-Browser mit optimierten Einstellungen.

        Setzt einen Standard-User-Agent und startet den Browser im
        maximierten Fenstermodus, um eine konsistente Darstellung von
        Webseiten zu gewährleisten.

        Returns:
            webdriver.Chrome: Die initialisierte Browser-Instanz.
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
        Verwendet AppleScript, um die Enter-Taste systemweit zu drücken.

        Diese Methode ist ein Workaround für macOS, um Systemdialoge zu
        bestätigen (z.B. die Zertifikatsauswahl bei der Unternehmensanmeldung),
        auf die Selenium keinen direkten Zugriff hat.
        """
        logger.info("Drücke Enter mit AppleScript für Systemdialog...")
        applescript = '''
        tell application "System Events"
            keystroke return
        end tell
        '''
        try:
            # A brief pause to ensure the dialog is the active window
            time.sleep(2)
            subprocess.run(["osascript", "-e", applescript], check=True, text=True)
            logger.info("Enter-Taste mit AppleScript gedrückt")
        except Exception as e:
            logger.error(f"Fehler beim Ausführen von AppleScript: {e}")

    def close(self):
        """Schließt den Browser und gibt alle damit verbundenen Ressourcen frei."""
        if self.driver:
            self.driver.quit()
            self.driver = None
            logger.info("Browser geschlossen")


class JiraLoginHandler(BrowserHandler):
    """
    Spezialisierte Klasse zum Anmelden bei Jira über den Microsoft-Flow.

    Erbt vom `BrowserHandler` und implementiert den mehrstufigen
    Anmeldeprozess, der eine Weiterleitung zur Microsoft-Anmeldeseite,
    die Handhabung von Systemdialogen und die MFA-Bestätigung umfasst.
    """

    def __init__(self):
        """Initialisiert den JiraLoginHandler."""
        super().__init__()

    def login(self, url, email, password):
        """
        Führt den vollständigen, mehrstufigen Login-Prozess für Jira durch.

        Der Prozess umfasst die folgenden automatisierten Schritte:
        1.  Klick auf den "Windows Account"-Button auf der Jira-Startseite.
        2.  Eingabe der E-Mail-Adresse auf der Microsoft-Anmeldeseite.
        3.  Eingabe des Passworts.
        4.  Bestätigung eines systemeigenen Zertifikatsdialogs via AppleScript.
        5.  Warten auf die manuelle Nutzerinteraktion (MFA-Bestätigung) und
            anschließendes Klicken auf "Ja" im "Angemeldet bleiben?"-Dialog.
        6.  Warten auf die finale Weiterleitung zurück zur Jira-Instanz.

        Args:
            url (str): Die initiale Jira-URL, die geöffnet werden soll.
            email (str): Die E-Mail-Adresse für den Microsoft-Login.
            password (str): Das zugehörige Passwort.

        Returns:
            bool: True, wenn der Login erfolgreich abgeschlossen wurde,
                  andernfalls False. Im Fehlerfall wird ein Screenshot
                  (`login_error.png`) gespeichert.
        """
        if not self.driver:
            self.init_browser()

        try:
            logger.info(f"Öffne URL: {url}")
            self.driver.get(url)

            # 1. Auf der ersten Seite den "Windows Account"-Button klicken
            logger.info("Suche nach 'Windows Account'-Button...")
            windows_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Windows Account')]"))
            )
            windows_button.click()
            logger.info("'Windows Account'-Button geklickt, leite zu Microsoft-Login weiter.")

            # 2. E-Mail auf der Microsoft-Seite eingeben und auf "Weiter" klicken
            logger.info("Warte auf E-Mail-Eingabefeld von Microsoft...")
            email_field = WebDriverWait(self.driver, 10).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, "input[type='email']"))
            )
            email_field.send_keys(email)

            logger.info("Suche nach 'Weiter'-Button...")
            weiter_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//input[@type='submit' and @value='Weiter']"))
            )
            weiter_button.click()
            logger.info(f"E-Mail {email} eingegeben und 'Weiter' geklickt.")

            # 3. Passwort eingeben und auf "Anmelden" klicken
            logger.info("Warte auf Passwort-Eingabefeld...")
            password_field = WebDriverWait(self.driver, 10).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, "input[type='password']"))
            )
            password_field.send_keys(password)

            logger.info("Suche nach 'Anmelden'-Button...")
            anmelden_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//input[@type='submit' and @value='Anmelden']"))
            )
            anmelden_button.click()
            logger.info("Passwort eingegeben und 'Anmelden' geklickt.")

            # 4. Systemdialog für Zertifikatsauswahl mit AppleScript bestätigen
            self.press_enter_with_applescript()

            # 5. Warten auf manuelle MFA & "Angemeldet bleiben?"-Dialog
            # Das Skript wartet auf die manuelle Bestätigung im Authenticator.
            # Danach erscheint der "Angemeldet bleiben?"-Dialog.
            logger.info("Warte auf manuelle Bestätigung im Authenticator und 'Angemeldet bleiben'-Dialog...")
            stay_signed_in_button = WebDriverWait(self.driver, 60).until(
                EC.element_to_be_clickable((By.XPATH, "//input[@type='submit' and @value='Ja']"))
            )
            logger.info("'Angemeldet bleiben?'-Dialog erschienen.")
            stay_signed_in_button.click()
            logger.info("'Ja' geklickt.")

            # 6. Warten auf die finale Weiterleitung zur Jira-Seite
            logger.info("Warte auf die Weiterleitung zu Jira...")
            WebDriverWait(self.driver, 20).until(
                EC.url_contains("jira") # Wartet, bis "jira" in der URL erscheint
            )

            logger.info("Login erfolgreich! Jira-Dashboard wurde geladen.")
            return True

        except Exception as e:
            logger.error(f"Fehler beim Login: {e}")
            self.driver.save_screenshot("login_error.png") # Speichert einen Screenshot bei Fehlern
            return False

# Beispiel für die Verwendung (Example Usage)
# if __name__ == '__main__':
#     jira_url = "DEINE_JIRA_URL"
#     jira_email = "DEINE_EMAIL"
#     jira_password = os.getenv("JIRA_PASSWORD") # Holt das Passwort aus der .env Datei

#     if not jira_password:
#         print("Fehler: JIRA_PASSWORD nicht in der .env-Datei gefunden.")
#     else:
#         login_handler = JiraLoginHandler()
#         try:
#             success = login_handler.login(jira_url, jira_email, jira_password)
#             if success:
#                 print("Erfolgreich bei Jira angemeldet.")
#                 # Hier kannst du weitere Aktionen mit dem Browser durchführen
#                 time.sleep(20) # 20 Sekunden warten, um die Seite zu sehen
#             else:
#                 print("Jira-Login fehlgeschlagen. Siehe Log und Screenshot 'login_error.png'.")
#         finally:
#             login_handler.close()
