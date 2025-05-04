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
from utils.login_handler import JiraLoginHandler
from utils.file_exporter import FileExporter
from utils.data_extractor import DataExtractor
from utils.business_impact_api import process_description

class JiraScraper:
    """Hauptklasse zum Scraping von Jira-Issues."""

    def __init__(self, url, email, model="claude-3-7-sonnet-latest", token_tracker=None):
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
        self.data_extractor = DataExtractor(description_processor=process_description, model = model, token_tracker = token_tracker)



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

            # Hole den HTML-Inhalt
            html_content = self.driver.page_source

            # Verwende die Instanzmethode des DataExtractors anstelle der statischen Methode
            issue_data = self.data_extractor.extract_issue_data(self.driver, issue_key)

            # Speichere die extrahierten Daten
            FileExporter.process_and_save_issue(self.driver, issue_key, html_content, issue_data)

            return issue_data

        except Exception as e:
            logger.error(f"Fehler beim Verarbeiten von Issue {issue_key}: {str(e)}")
            return None

    def process_related_issues(self, issue_data, current_url):
        """
        Verarbeitet rekursiv alle verwandten Issues (realized_by und Child Issues).

        Args:
            issue_data (dict): Die Daten des aktuellen Issues
            current_url (str): Die URL der aktuellen Seite, zu der zurückgekehrt werden soll
        """
        if not issue_data:
            return

        try:
            # 1. Verarbeite alle "is realized by" Issues
            if "realized_by" in issue_data and issue_data["realized_by"]:
                for realized_item in issue_data["realized_by"]:
                    if "key" in realized_item and "url" in realized_item:
                        related_key = realized_item["key"]
                        related_url = realized_item["url"]

                        if related_key not in self.processed_issues:
                            logger.info(f"Folge 'realized by' Link: {related_key}")
                            related_data = self.extract_and_save_issue_data(related_url, related_key)

                            # Rekursiv auch die verwandten Issues dieses Issues verarbeiten
                            if related_data:
                                self.process_related_issues(related_data, related_url)

            # 2. Stelle sicher, dass wir auf der richtigen Seite sind für Child Issues
            self.driver.get(current_url)
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "issue-content"))
            )

            # 3. Verarbeite Child Issues
            child_issues = self.find_child_issues()
            for child_key, child_url in child_issues:
                if child_key not in self.processed_issues:
                    logger.info(f"Verarbeite Child Issue: {child_key}")
                    child_data = self.extract_and_save_issue_data(child_url, child_key)

                    # Rekursiv auch die verwandten Issues dieses Child Issues verarbeiten
                    if child_data:
                        self.process_related_issues(child_data, child_url)

            # 4. Kehre zur ursprünglichen URL zurück (falls wir uns wegbewegt haben)
            if self.driver.current_url != current_url:
                self.driver.get(current_url)

        except Exception as e:
            logger.error(f"Fehler bei der Verarbeitung verwandter Issues: {str(e)}")
            # Falls ein Fehler auftritt, versuche zur ursprünglichen URL zurückzukehren
            try:
                self.driver.get(current_url)
            except:
                pass

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
