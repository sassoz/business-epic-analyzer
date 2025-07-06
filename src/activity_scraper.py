from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

from utils.jira_scraper import JiraScraper
from utils.login_handler import JiraLoginHandler
from utils.logger_config import logger

from bs4 import BeautifulSoup
from datetime import datetime, timezone
import time
import re
import json

def extract_activity_details(html_content):
    """
    Extrahiert und filtert die Aktivitätsdetails (Benutzer, Feldname, neuer Wert, Zeitstempel)
    aus dem übergebenen HTML-Inhalt einer JIRA-Seite.
    """
    soup = BeautifulSoup(html_content, 'lxml')
    action_containers = soup.find_all('div', class_='actionContainer')

    extracted_data = []
    ignored_fields = ['Checklists', 'Link', 'Remote Link', 'Kommentar oder Erstellung']

    for container in action_containers:
        user_name = "N/A"
        timestamp_iso = "N/A"
        timestamp_human = "N/A"
        activity_name = "Kommentar oder Erstellung"
        new_value = "N/A"

        details_block = container.find('div', class_='action-details')
        if not details_block:
            continue

        user_tag = details_block.find('a', class_='user-hover')
        if user_tag:
            user_name = user_tag.get_text(strip=True)

        time_tag = details_block.find('time', class_='livestamp')
        if time_tag:
            timestamp_iso = time_tag.get('datetime', 'N/A')
            timestamp_human = time_tag.get_text(strip=True)

        body_block = container.find('div', class_='action-body')
        if body_block:
            activity_name_tag = body_block.find('td', class_='activity-name')
            if activity_name_tag:
                activity_name = activity_name_tag.get_text(strip=True)

            if activity_name in ignored_fields:
                continue

            new_val_tag = body_block.find('td', class_='activity-new-val')
            if new_val_tag:
                full_text = new_val_tag.get_text(strip=True)

                # NEU: Spezifische Bereinigung für das Status-Feld
                if activity_name == 'Status':
                    try:
                        # Extrahiert 'ANALYSIS' aus 'New:Analysis[ 10004 ]'
                        new_value = full_text.split(':')[1].split('[')[0].strip().upper()
                    except IndexError:
                        # Fallback, falls das Format unerwartet ist
                        new_value = full_text.strip().upper()

                # Bisherige Logik für andere spezielle Felder
                elif activity_name in ['Acceptance Criteria', 'Description']:
                    new_value = '[...]'

                # Standard-Logik für alle anderen Felder (z.B. Kürzung)
                else:
                    if len(full_text) > 100:
                        new_value = full_text[:100] + "..."
                    else:
                        new_value = full_text
        else:
            continue

        extracted_data.append({
            'benutzer': user_name,
            'feld_name': activity_name,
            'neuer_wert': new_value,
            'zeitstempel_iso': timestamp_iso,
            'zeitstempel_lesbar': timestamp_human
        })

    return extracted_data[::-1]


# --- Beispiel für die Ausführung ---
if __name__ == "__main__":
    # Die URL des JIRA-Tickets, das Sie analysieren möchten
    # HINWEIS: Sie müssen bei diesem JIRA eingeloggt sein oder das Ticket muss öffentlich sein.
    JIRA_ISSUE_URL = "https://jira.telekom.de/browse/BEMABU-2054" # Ein öffentliches Beispiel
    USER_EMAIL = "ralf.niemeyer@telekom.de" # Platzhalter

   # Initialisieren Sie Ihren *echten* JiraScraper
    # HINWEIS: Hierfür müssen Ihre Abhängigkeiten wie logger_config, login_handler etc. verfügbar sein.
    scraper = JiraScraper(url=JIRA_ISSUE_URL, email=USER_EMAIL)

    print("Starte den Scraping- und Parsing-Prozess...")

    # Führen Sie den Login-Prozess Ihres Scrapers aus.
    # Annahme: Der Scraper hat eine Methode, die den WebDriver nach erfolgreichem Login bereitstellt.
    # Dies ist eine Adaption Ihres `run`-Ablaufs.
    if scraper.login_handler.login(scraper.url, scraper.email):
        scraper.driver = scraper.login_handler.driver

        try:
            print(f"Navigiere zu: {JIRA_ISSUE_URL}")
            scraper.driver.get(JIRA_ISSUE_URL)

            WebDriverWait(scraper.driver, 15).until(
                EC.presence_of_element_located((By.ID, "issue-content"))
            )
            print("Seite erfolgreich geladen.")

            # --- NEUE LOGIK: KLICK AUF DEN 'ALL'-TAB ---
            try:
                print("Versuche, auf den 'All'-Tab zu klicken...")
                all_tab_link_element = WebDriverWait(scraper.driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "li#all-tabpanel a"))
                )
                scraper.driver.execute_script("arguments[0].click();", all_tab_link_element)
                print("'All'-Tab erfolgreich via JavaScript geklickt.")
                time.sleep(1) # Kurze Pause, damit der erste Ladevorgang beginnen kann.

                # --- NEUE SCHLEIFE: LADE ALLE ÄLTEREN EREIGNISSE ---
                print("Prüfe auf 'Load more older events'-Button...")
                while True:
                    try:
                        # Warte maximal 3 Sekunden auf den Button. Wenn er nicht erscheint, sind wir fertig.
                        load_more_button = WebDriverWait(scraper.driver, 3).until(
                            EC.element_to_be_clickable((By.CLASS_NAME, "show-more-all-tabpanel"))
                        )
                        print("     'Load more'-Button gefunden, klicke...")
                        scraper.driver.execute_script("arguments[0].click();", load_more_button)
                        # Warte kurz, damit die neuen Inhalte geladen werden können.
                        time.sleep(2)
                    except TimeoutException:
                        # Wenn der Button nach 3 Sekunden nicht gefunden wird, gibt es keine weiteren Events.
                        print("'Load more'-Button nicht mehr gefunden. Alle Aktivitäten sollten geladen sein.")
                        break # Verlässt die while-Schleife
                # --- ENDE DER NEUEN SCHLEIFE ---

            except Exception as tab_error:
                print(f"Warnung: Konnte nicht auf den 'All'-Tab klicken oder Inhalte nicht laden. Fahre mit dem Standard-HTML fort. Fehler: {tab_error}")
            # --- ENDE DER NEUEN LOGIK ---

            # Hole den HTML-Quellcode von der Seite
            html_source = scraper.driver.page_source

            # Wir extrahieren den Issue-Key für einen dynamischen Dateinamen.
            issue_key_match = re.search(r'/browse/([A-Z]+-\d+)', JIRA_ISSUE_URL)
            issue_key = issue_key_match.group(1) if issue_key_match else "unbekanntes_issue"
            file_name = f"{issue_key}.html"

            with open(file_name, "w", encoding="utf-8") as f:
                f.write(html_source)
            print(f"Der komplette HTML-Inhalt wurde in der Datei '{file_name}' gespeichert.")

            # Rufe unsere spezialisierte Parser-Funktion auf
            activities = extract_activity_details(html_source)

            print(f"\n--- Extraktion abgeschlossen: {len(activities)} Aktivitäten gefunden ---")
            for activity in activities:
                print("\n-------------------------")
                print(f"Benutzer:      {activity['benutzer']}")
                print(f"Zeitstempel:   {activity['zeitstempel_lesbar']}")
                print(f"Feld:          {activity['feld_name']}")
                print(f"Neuer Wert:    {activity['neuer_wert']}")

        except Exception as e:
            print(f"Ein Fehler während des Scraping-Vorgangs ist aufgetreten: {e}")
        finally:
            print("\nProzess beendet. Browser wird geschlossen.")
            scraper.driver.quit()
    else:
        print("Login fehlgeschlagen. Bitte überprüfen Sie Ihre Konfiguration und Zugangsdaten.")
