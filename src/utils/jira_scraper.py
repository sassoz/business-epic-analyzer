"""
Module for scraping and processing JIRA issues from web interfaces.

This module provides functionality to automate JIRA web interaction, extracting
issue data through a headless browser. It handles authentication, navigation,
and recursive traversal of issue relationships to build a complete dataset.

The main class, JiraScraper, manages the browser interaction, login process,
and extraction of JIRA issues including their relationships. It follows both
"is realized by" links and child issues to build a comprehensive graph of
related issues.

Key features:
- Automated JIRA login and session management
- Recursive extraction of connected issues
- Support for "is realized by" relationship traversal
- Child issue identification and processing
- Integration with business value extraction
- Robust error handling and retry mechanisms
"""

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
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
from utils.login_handler import JiraLoginHandler
from utils.file_exporter import FileExporter
from utils.data_extractor import DataExtractor
from utils.business_impact_api import process_description

class JiraScraper:
    """Hauptklasse zum Scraping von Jira-Issues."""

    def __init__(self, url, email, model="o3-mini", token_tracker=None, azure_client=None):
        """
        Initialisiert den JiraScraper.

        Args:
            url (str): Die Jira-URL
            email (str): Die E-Mail-Adresse für den Login
        """
        self.url = url
        self.email = email
        self.login_handler = JiraLoginHandler()
        self.driver = None
        self.processed_issues = set()  # Set zum Speichern bereits verarbeiteter Issues
        self.data_extractor = DataExtractor(
            description_processor=process_description,
            model=model,
            token_tracker=token_tracker,
            azure_client=azure_client # Dies funktioniert jetzt
        )

    def extract_and_save_issue_data(self, issue_url, issue_key=None):
        """
        Extrahiert und speichert die Daten eines einzelnen Issues.

        Args:
            issue_url (str): Die URL des Issues
            issue_key (str, optional): Der Issue-Key, falls bereits bekannt

        Returns:
            dict: Die extrahierten Daten oder None, wenn das Issue bereits verarbeitet wurde
        """
        if not issue_key:
            # Extrahiere Issue-Key aus der URL, falls nicht angegeben
            issue_key = issue_url.split('/browse/')[1] if '/browse/' in issue_url else None

        if not issue_key:
            logger.warning(f"Konnte keinen Issue-Key aus URL extrahieren: {issue_url}")
            return None

        if issue_key in self.processed_issues:
            logger.info(f"Issue {issue_key} wurde bereits verarbeitet, überspringe...")
            return None

        try:
            # Markiere das Issue als verarbeitet
            self.processed_issues.add(issue_key)

            # Navigiere zur Issue-Seite
            self.driver.get(issue_url)
            logger.info(f"Verarbeite Issue: {issue_key}")

            # Warte, bis die Seite geladen ist
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "issue-content"))
            )

            try:
                logger.info(f"Versuche für Issue {issue_key}, alle Aktivitäten zu laden...")
                # 1. Auf "All"-Tab klicken
                all_tab_link_element = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "li#all-tabpanel a"))
                )
                self.driver.execute_script("arguments[0].click();", all_tab_link_element)
                time.sleep(1)

                # 2. Schleife für "Load more older events"
                while True:
                    try:
                        load_more_button = WebDriverWait(self.driver, 3).until(
                            EC.element_to_be_clickable((By.CLASS_NAME, "show-more-all-tabpanel"))
                        )
                        logger.debug(f"     'Load more'-Button für {issue_key} gefunden, klicke...")
                        self.driver.execute_script("arguments[0].click();", load_more_button)
                        time.sleep(2)
                    except TimeoutException:
                        logger.info(f"Alle Aktivitäten für Issue {issue_key} wurden geladen.")
                        break
            except Exception as tab_error:
                logger.warning(f"Konnte für Issue {issue_key} nicht alle Aktivitäten laden. Fahre mit Standard-HTML fort. Fehler: {tab_error}")

            # Hole den HTML-Inhalt
            html_content = self.driver.page_source

            # Verwende die Instanzmethode des DataExtractors anstelle der statischen Methode
            issue_data = self.data_extractor.extract_issue_data(self.driver, issue_key)
            issue_data['activities'] = self.data_extractor.extract_activity_details(html_content)

            # Speichere die extrahierten Daten
            FileExporter.process_and_save_issue(self.driver, issue_key, html_content, issue_data)

            return issue_data

        except TimeoutException:
            logger.error(f"Timeout beim Warten auf die Seite für Issue {issue_key}. Überspringe.")
            return None
        except Exception as e:
            logger.error(f"Ein unerwarteter Fehler ist beim Verarbeiten von Issue {issue_key} aufgetreten: {e}")
            return None


    def process_related_issues(self, issue_data, current_url):
            """
            Verarbeitet rekursiv alle verwandten Issues (realized_by und Child Issues).

            Args:
                issue_data (dict): Die Daten des aktuellen Issues
                current_url (str): Die URL der aktuellen Seite (wird für die Rekursion benötigt)
            """
            if not issue_data:
                return

            all_related_issues = []
            if "realized_by" in issue_data and issue_data["realized_by"]:
                all_related_issues.extend(issue_data["realized_by"])

            if "child_issues" in issue_data and issue_data["child_issues"]:
                all_related_issues.extend(issue_data["child_issues"])

            if not all_related_issues:
                return

            # Verarbeite alle gefundenen verwandten Issues
            for related_item in all_related_issues:
                try: # <-- Fehlerbehandlung für jedes einzelne verwandte Issue
                    if "key" in related_item and "url" in related_item:
                        related_key = related_item["key"]
                        related_url = related_item["url"]

                        # Die Schutzlogik greift hier wie gewohnt
                        if related_key not in self.processed_issues:
                            relation_type = related_item.get("relation_type", "related")
                            logger.info(f"Folge '{relation_type}' Link: {related_key}")

                            # Rekursiver Aufruf für das nächste Ticket
                            related_data = self.extract_and_save_issue_data(related_url, related_key)
                            if related_data:
                                # WICHTIG: Die neue URL des Kind-Tickets wird übergeben
                                self.process_related_issues(related_data, related_url)

                except Exception as e:
                    # Protokolliere den Fehler und fahre mit dem nächsten Item in der Schleife fort
                    item_key = related_item.get('key', 'UNBEKANNT')
                    logger.error(f"Fehler bei der Verarbeitung von Sub-Issue {item_key}: {e}", exc_info=True)
                    continue # <-- Sehr wichtig, damit die Schleife weiterläuft


    def find_child_issues(self):
        """
        Findet alle Child Issues auf der aktuellen Seite.

        Returns:
            list: Liste von Tupeln (child_key, child_url) der gefundenen Child Issues
        """
        child_issues = []
        try:
            # Versuche, die Child-Issue-Tabelle zu finden
            child_table = WebDriverWait(self.driver, 3).until(
                EC.presence_of_element_located((By.XPATH, "//table[contains(@class, 'jpo-child-issue-table')]"))
            )

            # Finde alle Links in der Tabelle
            child_links = child_table.find_elements(By.XPATH, ".//a[contains(@href, '/browse/')]")

            for child_link in child_links:
                # Extrahiere Issue-Schlüssel und URL
                child_key = child_link.text.strip()
                child_url = child_link.get_attribute("href")

                # Überspringe leere oder ungültige Links
                if not child_key or not re.match(r'[A-Z]+-\d+', child_key):
                    continue

                child_issues.append((child_key, child_url))

            if child_issues:
                logger.info(f"Gefunden: {len(child_issues)} Child Issues")

        except Exception as e:
            # Es ist normal, wenn keine Child Issues gefunden werden
            logger.debug(f"Keine Child Issues gefunden: {str(e)}")

        return child_issues

    def run(self, skip_login=False):
        """Führt den Scraping-Prozess aus."""
        try:
            # Login (nur wenn nicht übersprungen werden soll)
            if not skip_login:
                logger.info("Starte Login-Prozess...")
                login_success = self.login_handler.login(self.url, self.email)

                if not login_success:
                    logger.error("Login fehlgeschlagen. Breche ab.")
                    return

                # Speichere die Referenz auf den Browser
                self.driver = self.login_handler.driver
            else:
                logger.info("Login übersprungen, verwende bestehende Session...")
                # Navigiere zur neuen URL
                self.driver.get(self.url)

            # Extrahiere die URL des Start-Issues
            start_url = self.url
            if '/browse/' not in start_url:
                logger.error(f"Ungültiges URL-Format. URL muss '/browse/' enthalten: {start_url}")
                return

            # Extrahiere Issue-Key aus der URL
            issue_key = start_url.split('/browse/')[1]

            if not issue_key:
                logger.error(f"Konnte keinen Issue-Key aus URL extrahieren: {start_url}")
                return

            logger.info(f"Beginne mit Start-Issue: {issue_key}")

            # Extrahiere und speichere die Daten des Start-Issues
            issue_data = self.extract_and_save_issue_data(start_url, issue_key)

            if issue_data:
                # Rekursiv alle verwandten Issues verarbeiten
                self.process_related_issues(issue_data, start_url)

            # Zusammenfassung
            logger.info(f"Scraping abgeschlossen. Insgesamt {len(self.processed_issues)} Issues verarbeitet.")

        except Exception as e:
            logger.error(f"Fehler beim Scraping: {e}")
            import traceback
            traceback.print_exc()  # Detaillierte Fehlerinformationen ausgeben
