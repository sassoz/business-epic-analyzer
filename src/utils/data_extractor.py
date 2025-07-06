"""
Module for extracting structured data from JIRA issue web pages.

This module provides functionality to parse and extract data from JIRA web pages
using Selenium. It handles the extraction of various fields and relationships
from JIRA issues, including titles, descriptions, statuses, assignees, business
values, acceptance criteria, attachments, and relationship links.

The main class, DataExtractor, implements robust extraction methods with fallback
strategies to handle different JIRA UI layouts and configurations. It includes
special handling for business value information, which can be processed by external
AI services to extract structured business impact metrics.

Key features:
- Extracts structured data from JIRA issue web pages
- Handles "is realized by" links and child issues
- Supports extraction of business value data
- Provides fallback extraction mechanisms for robustness
- Integrates with business impact AI processing
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup
import re
from utils.logger_config import logger


class DataExtractor:
    """
    Class for extracting structured data from JIRA issue web pages.

    This class handles the extraction of various fields and data elements from JIRA
    web pages using Selenium. It implements robust extraction methods with multiple
    fallback strategies to ensure reliable data extraction across different JIRA
    configurations and UI layouts.

    Key features:
    - Extracts issue metadata (key, title, status, type, priority)
    - Captures description and business scope text
    - Processes business value data via external AI service (optional)
    - Extracts acceptance criteria and fix versions
    - Captures attachment information (files, images)
    - Identifies related issues ('realized by' links and child issues)
    - Supports temporal data (target start/end dates)

    The class uses primary extraction methods first, then falls back to alternative
    extraction strategies if the primary methods fail. This ensures maximum data
    extraction even when JIRA's UI structure varies.

    When a description_processor is provided (typically an AI service), the class
    can analyze business value information from issue descriptions, extracting
    structured business impact, strategic enablement and time criticality data.
    """

    def __init__(self, description_processor=None, model="claude-3-7-sonnet-latest", token_tracker=None, azure_client=None):
        """
        Initialisiert den DataExtractor.

        Args:
            description_processor (callable, optional): Eine Funktion, die Beschreibungstexte verarbeitet
                                                     und business_value extrahiert.
                                                     Falls None, wird kein Business Value extrahiert.
        """
        self.description_processor = description_processor
        self.model = model
        self.token_tracker = token_tracker
        self.azure_client = azure_client

    @staticmethod
    def _find_child_issues(driver):
        """
        Sucht nach Child Issues auf der aktuellen Seite.

        Args:
            driver (webdriver): Die Browser-Instanz

        Returns:
            list: Liste von Dictionaries mit Informationen zu Child Issues
        """
        child_issues = []

        try:
            # Suche nach der Child-Issue-Tabelle
            child_table = driver.find_element(By.XPATH, "//table[contains(@class, 'jpo-child-issue-table')]")

            # Finde alle Links in der Tabelle
            child_links = child_table.find_elements(By.XPATH, ".//a[contains(@href, '/browse/')]")

            if child_links:
                logger.info(f"Gefunden: {len(child_links)} Child Issues")

                # Verarbeite jeden Child-Issue-Link
                for child_link in child_links:
                    # Extrahiere Issue-Schlüssel und URL
                    child_key = child_link.text.strip()
                    child_href = child_link.get_attribute("href")

                    # Überspringe leere oder ungültige Links
                    if not child_key or not re.match(r'[A-Z]+-\d+', child_key):
                        continue

                    logger.info(f"Child Issue gefunden: {child_key}")

                    # Versuche, den Summary-Text zu finden (falls vorhanden)
                    try:
                        # Finde das übergeordnete tr-Element
                        parent_row = child_link.find_element(By.XPATH, "./ancestor::tr")

                        # Suche nach der Zelle mit der Zusammenfassung (normalerweise die 2. oder 3. Zelle)
                        summary_cells = parent_row.find_elements(By.XPATH, "./td")
                        summary_text = ""

                        if len(summary_cells) >= 2:
                            # Die 2. Zelle enthält oft die Zusammenfassung
                            summary_text = summary_cells[1].text.strip()

                    except Exception as e:
                        summary_text = ""
                        logger.debug(f"Konnte Summary für Child Issue {child_key} nicht extrahieren: {e}")

                    # Füge die Informationen zur child_issues-Liste hinzu
                    child_issue_item = {
                        "key": child_key,
                        "title": child_key,  # Title ist oft nur der Key
                        "summary": summary_text,
                        "url": child_href
                    }

                    child_issues.append(child_issue_item)

        except Exception as e:
            logger.info(f"Keine Child Issues gefunden")

        return child_issues


    @staticmethod
    def _extract_business_scope(driver):
        """
        Extrahiert den Business Scope-Text aus der Jira-Seite.

        Args:
            driver (webdriver): Die Browser-Instanz

        Returns:
            str: Der extrahierte Business Scope-Text oder leerer String, wenn nicht gefunden
        """
        business_scope = ""

        try:
            # Suche nach dem Label mit title="Business Scope"
            business_scope_label = driver.find_element(By.XPATH,
                "//strong[@title='Business Scope']//label[contains(@for, 'customfield_')]")

            # Hole die customfield_id
            field_id = business_scope_label.get_attribute("for")

            # Suche nach dem zugehörigen Wert-Element
            business_scope_div = driver.find_element(By.XPATH, f"//div[@id='{field_id}-val']")

            # Robustere Extraktion des Textes - versuche verschiedene Wege
            # 1. Versuche zuerst, direkt den Text zu holen
            business_scope = business_scope_div.text.strip()

            # 2. Wenn der Text leer ist, versuche es mit flooded divs
            if not business_scope:
                # Suche nach allen div-Elementen mit Klasse 'flooded' innerhalb des Haupt-divs
                flooded_divs = business_scope_div.find_elements(By.XPATH, ".//div[contains(@class, 'flooded')]")

                # Sammle den Text aus allen gefundenen Elementen
                texts = []
                for div in flooded_divs:
                    div_text = div.text.strip()
                    if div_text:
                        texts.append(div_text)

                # Füge alle gefundenen Texte zusammen
                business_scope = "\n".join(texts)

            # Wenn immer noch leer, extrahiere den HTML-Inhalt und versuche es manuell zu parsen
            if not business_scope:
                html_content = business_scope_div.get_attribute('innerHTML')
                # Entferne HTML-Tags mit einem einfachen Ansatz (für komplexere Fälle könnte BeautifulSoup verwendet werden)
                import re
                business_scope = re.sub(r'<[^>]*>', ' ', html_content)
                business_scope = re.sub(r'\s+', ' ', business_scope).strip()

            if business_scope:
                logger.info(f"Business Scope gefunden: {business_scope[:50]}...")
            else:
                logger.info("Business Scope gefunden, aber Text ist leer")

        except Exception as e:
            logger.info(f"Business Scope konnte nicht extrahiert werden")

        return business_scope


    def extract_issue_data(self, driver, issue_key):
        """
        Extrahiert die wichtigsten Daten eines Jira-Issues in ein strukturiertes Format.

        Args:
            driver (webdriver): Die Browser-Instanz
            issue_key (str): Der Jira-Issue-Key (z.B. "JIRA-1234")

        Returns:
            dict: Die extrahierten Daten
        """
        data = {
            "key": issue_key,
            "issue_type": "",          # Wird mit dem Wert aus dem Title-Attribut gefüllt
            "title": "",
            "status": "",
            "description": "",
            "business_value": {},
            "assignee": "",
            "priority": "",
            "target_start": "",
            "target_end": "",
            "fix_versions": [],           # Liste der FixVersions
            "acceptance_criteria": [],  # Liste der Acceptance Criteria
            "components": [],
            "labels": [],              # Liste der Labels
            "realized_by": [],         # Liste der "is realized by" Links
            "child_issues": [],        # Neue Liste für Child Issues
            "attachments": [],         # Neue Liste für Anhänge
        }

        try:
            # Title
            try:
                title_elem = driver.find_element(By.XPATH, "//h2[@id='summary-val']")
                data["title"] = title_elem.text.strip()
                logger.info(f"Titel gefunden: {data['title']}")
            except Exception as e:
                logger.info(f"Titel nicht gefunden: {e}")

            # Description
            try:
                desc_elem = driver.find_element(By.XPATH, "//div[contains(@id, 'description') or contains(@class, 'description')]")
                data["description"] = desc_elem.text
                logger.info(f"Beschreibung gefunden ({len(desc_elem.text)} Zeichen)")
            except Exception as e:
                logger.info(f"Beschreibung nicht gefunden: {e}")

            # Business Scope extrahieren und zur Description hinzufügen:
            try:
                business_scope = DataExtractor._extract_business_scope(driver)
                if business_scope:
                    # Zur bestehenden Description hinzufügen
                    if data["description"]:
                        data["description"] += "\n\nBusiness Scope:\n" + business_scope
                    else:
                        data["description"] = "Business Scope:\n" + business_scope
                    logger.info(f"Business Scope zur Description hinzugefügt ({len(business_scope)} Zeichen)")
            except Exception as e:
                logger.info(f"Business Scope konnte nicht extrahiert werden: {e}")


            # Status
            try:
                # Look for the dropdown button with the status using the class pattern
                status_button = driver.find_element(By.XPATH, "//a[contains(@class, 'aui-dropdown2-trigger') and contains(@class, 'opsbar-transitions__status-category_')]")

                # Extract the dropdown-text span within this button
                status_span = status_button.find_element(By.XPATH, ".//span[@class='dropdown-text']")

                data["status"] = status_span.text
                logger.info(f"Status gefunden: {status_span.text}")
            except Exception as e:
                logger.info(f"Status nicht gefunden: {e}")

            # Assignee
            try:
                assignee_elem = driver.find_element(By.XPATH, "//span[contains(@id, 'assignee') or contains(@class, 'assignee')]")
                data["assignee"] = assignee_elem.text
                logger.info(f"Assignee gefunden: {assignee_elem.text}")
            except Exception as e:
                logger.info(f"Assignee nicht gefunden: {e}")

            # Issue Type - basierend auf dem alt-Attribut des Icons
            try:
                # Suche nach dem Element mit class="name" und Label für "issuetype"
                issue_type_label = driver.find_element(By.XPATH, "//strong[contains(@class, 'name')]//label[@for='issuetype']")

                # Gehe zum übergeordneten span-Element
                issue_type_container = driver.find_element(By.XPATH, "//span[@id='type-val']")

                # Finde das Bild mit dem alt-Attribut
                issue_type_img = issue_type_container.find_element(By.XPATH, ".//img[@alt]")

                # Extrahiere den Typ aus dem alt-Attribut (Format "Icon: [Type]")
                alt_text = issue_type_img.get_attribute("alt")

                # Verwende regulären Ausdruck um den Typ zu extrahieren
                import re
                match = re.match(r'Icon:\s+(.*)', alt_text)
                if match:
                    issue_type = match.group(1).strip()
                    data["issue_type"] = issue_type
                    logger.info(f"Issue Type gefunden (aus alt-Attribut): {issue_type}")
                else:
                    # Fallback auf title-Attribut, wenn alt-Attribut nicht dem erwarteten Format entspricht
                    issue_type = issue_type_img.get_attribute("title")
                    data["issue_type"] = issue_type
                    logger.info(f"Issue Type gefunden (aus title-Attribut): {issue_type}")

                # Bei issue_type "Business Epic" auch Business Value befüllen
                if issue_type == 'Business Epic' and self.description_processor is not None:
                    # Verwende den injizierten Prozessor anstatt einer direkten Abhängigkeit
                    processed_text = self.description_processor(
                        data["description"],  # description_text
                        self.model,          # model
                        self.token_tracker,   # token_tracker
                        self.azure_client
                    )
                    data["description"] = processed_text['description']
                    data["business_value"] = processed_text['business_value']
                    logger.info(f"Business Value ergänzt")

            except Exception as e:
                # Fallback-Methode, falls die erste Methode fehlschlägt
                try:
                    # Alternative Suche nach dem Issue-Type
                    issue_type_elements = driver.find_elements(By.XPATH,
                        "//img[contains(@alt, 'Icon:') or contains(@alt, 'Type:')]")

                    for img in issue_type_elements:
                        alt_text = img.get_attribute("alt")
                        if alt_text:
                            match = re.match(r'Icon:\s+(.*)', alt_text)
                            if match:
                                issue_type = match.group(1).strip()
                                data["issue_type"] = issue_type
                                logger.info(f"Issue Type mit Fallback-Methode gefunden (aus alt-Attribut): {issue_type}")
                                break

                        # Wenn kein passender alt-Text gefunden wurde, versuchen wir es mit title
                        issue_type = img.get_attribute("title")
                        if issue_type:
                            data["issue_type"] = issue_type
                            logger.info(f"Issue Type mit Fallback-Methode gefunden (aus title-Attribut): {issue_type}")
                            break

                except Exception as fallback_e:
                    logger.info(f"Issue Type mit beiden Methoden nicht gefunden: {e}, {fallback_e}")


            # fixVersion Daten extrahieren
            try:
               fix_version_span = driver.find_element(By.XPATH, "//span[@id='fixVersions-field']")
               fix_version_links = fix_version_span.find_elements(By.XPATH, ".//a[contains(@href, '/issues/')]")

               for link in fix_version_links:
                   # Extract text between > and </a>
                   link_html = link.get_attribute("outerHTML")
                   match = re.search(r'>([^<]+)</a>', link_html)
                   if match:
                       version = match.group(1).strip()
                       if version and version not in data["fix_versions"]:
                           data["fix_versions"].append(version)

               logger.info(f"{len(data['fix_versions'])} Fix Versions gefunden: {', '.join(data['fix_versions'])}")
            except Exception as e:
               # Fallback method
               try:
                   fix_version_elements = driver.find_elements(By.XPATH,
                       "//strong[contains(@title, 'Fix Version') or contains(text(), 'Fix Version')]/following::span[1]//a[contains(@href, '/issues/')]")

                   for elem in fix_version_elements:
                       link_html = elem.get_attribute("outerHTML")
                       match = re.search(r'>([^<]+)</a>', link_html)
                       if match:
                           version = match.group(1).strip()
                           if version and version not in data["fix_versions"]:
                               data["fix_versions"].append(version)

                   logger.info(f"Mit Fallback-Methode {len(data['fix_versions'])} Fix Versions gefunden")
               except Exception as fallback_e:
                   logger.info(f"Fix Versions nicht gefunden: {e}, {fallback_e}")


            # Target Start und Target End Daten extrahieren
            try:
                # Suche nach den Target-Datum-Elementen
                try:
                    # Target Start-Datum extrahieren
                    target_start_span = driver.find_element(By.XPATH, "//span[@data-name='Target start']")
                    target_start_time = target_start_span.find_element(By.XPATH, ".//time[@datetime]")
                    target_start_datetime = target_start_time.get_attribute("datetime")
                    data["target_start"] = target_start_datetime
                    logger.info(f"Target Start-Datum gefunden: {target_start_datetime}")
                except Exception as e:
                    logger.info(f"Target Start-Datum nicht gefunden")

                # Target End-Datum extrahieren
                try:
                    target_end_span = driver.find_element(By.XPATH, "//span[@data-name='Target end']")
                    target_end_time = target_end_span.find_element(By.XPATH, ".//time[@datetime]")
                    target_end_datetime = target_end_time.get_attribute("datetime")
                    data["target_end"] = target_end_datetime
                    logger.info(f"Target End-Datum gefunden: {target_end_datetime}")
                except Exception as e:
                    logger.info(f"Target End-Datum nicht gefunden")
            except Exception as e:
                # Fallback-Methode mit direkten Klassen
                try:
                    # Versuche die spezifischen dd-Elemente mit den Klassen zu finden
                    target_start_dd = driver.find_element(By.XPATH, "//dd[contains(@class, 'type-jpo-custom-field-baseline-start')]")
                    target_end_dd = driver.find_element(By.XPATH, "//dd[contains(@class, 'type-jpo-custom-field-baseline-end')]")

                    # Extrahiere die datetime-Werte aus den time-Elementen
                    target_start_time = target_start_dd.find_element(By.XPATH, ".//time[@datetime]")
                    target_end_time = target_end_dd.find_element(By.XPATH, ".//time[@datetime]")

                    data["target_start"] = target_start_time.get_attribute("datetime")
                    data["target_end"] = target_end_time.get_attribute("datetime")

                    logger.info(f"Target Start-Datum mit Fallback gefunden: {data['target_start']}")
                    logger.info(f"Target End-Datum mit Fallback gefunden: {data['target_end']}")
                except Exception as fallback_e:
                    logger.info(f"Target-Datumsangaben mit beiden Methoden nicht gefunden: {e}, {fallback_e}")


            # Attachments extrahieren
            try:
                # Suche nach dem ol-Element mit id="attachment_thumbnails"
                attachments_list = driver.find_element(By.XPATH, "//ol[@id='attachment_thumbnails' and contains(@class, 'item-attachments')]")

                # Finde alle Listenelemente, die Anhänge repräsentieren
                attachment_items = attachments_list.find_elements(By.XPATH, ".//li[contains(@class, 'attachment-content')]")

                # Extrahiere die Informationen für jeden Anhang
                for item in attachment_items:
                    try:
                        # Extrahiere den Download-URL
                        download_url = item.get_attribute("data-downloadurl")

                        if download_url:
                            # Parse den Download-URL, der im Format "MIME-Type:Dateiname:URL" vorliegt
                            parts = download_url.split(":", 2)
                            if len(parts) >= 3:
                                mime_type = parts[0]
                                file_name = parts[1]
                                url = parts[2]

                                # Größe des Anhangs (falls vorhanden)
                                try:
                                    size_element = item.find_element(By.XPATH, ".//dd[contains(@class, 'attachment-size')]")
                                    file_size = size_element.text.strip()
                                except:
                                    file_size = ""

                                # Datum des Anhangs (falls vorhanden)
                                try:
                                    date_element = item.find_element(By.XPATH, ".//time[@datetime]")
                                    date_time = date_element.get_attribute("datetime")
                                except:
                                    date_time = ""

                                # Füge ein strukturiertes Objekt für jeden Anhang hinzu
                                attachment_item = {
                                    "filename": file_name,
                                    "url": url,
                                    "mime_type": mime_type,
                                    "size": file_size,
                                    "date": date_time
                                }

                                # Füge zur Attachments-Liste hinzu
                                data["attachments"].append(attachment_item)
                    except Exception as item_error:
                        logger.info(f"Fehler beim Extrahieren eines Anhangs: {item_error}")

                logger.info(f"{len(data['attachments'])} Anhänge gefunden")
            except Exception as e:
                # Fallback-Methode
                try:
                    # Alternative Suche nach Anhängen
                    attachment_links = driver.find_elements(By.XPATH,
                        "//div[contains(@class, 'attachment-thumb')]//a[contains(@href, '/secure/attachment/')]")

                    for link in attachment_links:
                        try:
                            file_name = link.get_attribute("title").split(" – ")[0] if link.get_attribute("title") else ""
                            url = link.get_attribute("href")

                            if url and file_name and not any(att["filename"] == file_name for att in data["attachments"]):
                                # Füge ein strukturiertes Objekt für jeden Anhang hinzu
                                attachment_item = {
                                    "filename": file_name,
                                    "url": url,
                                    "mime_type": "",  # Kann im Fallback nicht zuverlässig ermittelt werden
                                    "size": "",       # Kann im Fallback nicht zuverlässig ermittelt werden
                                    "date": ""        # Kann im Fallback nicht zuverlässig ermittelt werden
                                }

                                # Füge zur Attachments-Liste hinzu
                                data["attachments"].append(attachment_item)
                        except Exception as link_error:
                            continue

                    logger.info(f"Mit Fallback-Methode {len(data['attachments'])} Anhänge gefunden")
                except Exception as fallback_e:
                    logger.info(f"Keine Anhänge gefunden")

        # Acceptance Criteria - robuster Ansatz
            try:
                # Suche nach dem Element mit title="Acceptance Criteria"
                acceptance_title = driver.find_element(By.XPATH, "//strong[@title='Acceptance Criteria']")

                # Finde das label-Element und hole die for-ID
                label_elem = acceptance_title.find_element(By.XPATH, ".//label")
                field_id = label_elem.get_attribute("for")

                # Finde das zugehörige Feld über die ID
                acceptance_field = driver.find_element(By.XPATH, f"//div[@id='{field_id}-val']")

                # Suche nach allen Listenelementen innerhalb des Feldes
                criteria_items = acceptance_field.find_elements(By.XPATH, ".//ul/li")

                # Falls keine Listenelemente gefunden wurden, suche nach Paragraphen
                if not criteria_items:
                    criteria_items = acceptance_field.find_elements(By.XPATH, ".//p")

                # Extrahiere den Text aus jedem Listenelement
                for item in criteria_items:
                    criterion_text = item.text.strip()
                    if criterion_text:  # Nur hinzufügen, wenn nicht leer
                        data["acceptance_criteria"].append(criterion_text)

                logger.info(f"{len(data['acceptance_criteria'])} Acceptance Criteria gefunden")
            except Exception as e:
                # Fallback-Methode, falls der erste Ansatz fehlschlägt
                try:
                    # Allgemeinere Suche nach Elementen, die "Acceptance Criteria" enthalten
                    acceptance_elements = driver.find_elements(By.XPATH,
                        "//*[contains(text(), 'Acceptance Criteria') or contains(@title, 'Acceptance Criteria')]")

                    if acceptance_elements:
                        # Suche nach der nächsten Liste im DOM
                        for elem in acceptance_elements:
                            # Versuche, die nächste ul zu finden
                            ul_elements = driver.find_elements(By.XPATH,
                                f"//ul[preceding::*[contains(text(), 'Acceptance Criteria')]][1]//li")

                            if ul_elements:
                                for item in ul_elements:
                                    criterion_text = item.text.strip()
                                    if criterion_text and criterion_text not in data["acceptance_criteria"]:
                                        data["acceptance_criteria"].append(criterion_text)

                    logger.info(f"Mit Fallback-Methode {len(data['acceptance_criteria'])} Acceptance Criteria gefunden")
                except Exception as fallback_e:
                    logger.info(f"Acceptance Criteria mit beiden Methoden nicht gefunden: {e}, {fallback_e}")

            # Labels - basierend auf dem Screenshot
            try:
                # Suche nach ul-Element mit der Klasse "labels"
                labels_ul = driver.find_element(By.XPATH, "//ul[contains(@class, 'labels')]")

                # Finde alle Link-Elemente innerhalb der Listenelemente
                label_links = labels_ul.find_elements(By.XPATH, ".//li/a[@title]")

                # Extrahiere den Titel jedes Labels
                for label_link in label_links:
                    label_title = label_link.get_attribute("title")
                    if label_title:  # Nur hinzufügen, wenn nicht leer
                        data["labels"].append(label_title)

                logger.info(f"{len(data['labels'])} Labels gefunden: {', '.join(data['labels'])}")
            except Exception as e:
                # Fallback-Methode, falls der erste Ansatz fehlschlägt
                try:
                    # Alternative Suche nach Labels
                    label_elements = driver.find_elements(By.XPATH, "//div[contains(@class, 'labels-wrap')]//a[contains(@class, 'lozenge')]")

                    for elem in label_elements:
                        label_text = elem.get_attribute("title") or elem.text.strip()
                        if label_text and label_text not in data["labels"]:
                            data["labels"].append(label_text)

                    logger.info(f"Mit Fallback-Methode {len(data['labels'])} Labels gefunden")
                except Exception as fallback_e:
                    logger.info(f"Labels mit beiden Methoden nicht gefunden: {e}, {fallback_e}")

            # Components extrahieren
            try:
                # Suche nach dem Container mit id="components-val"
                components_container = driver.find_element(By.XPATH, "//span[@id='components-field']")

                # Finde alle Links innerhalb des Containers
                component_links = components_container.find_elements(By.XPATH, ".//a[contains(@href, '/issues/')]")

                # Extrahiere den Text und Titel jedes Components
                for comp_link in component_links:
                    component_code = comp_link.text.strip()
                    component_title = comp_link.get_attribute("title")

                    if component_code:
                        # Füge ein strukturiertes Objekt für jede Component hinzu
                        component_item = {
                            "code": component_code,
                            "title": component_title
                        }
                        data["components"].append(component_item)

                logger.info(f"{len(data['components'])} Components gefunden: {', '.join([comp['code'] for comp in data['components']])}")
            except Exception as e:
                # Fallback-Methode
                try:
                    # Alternative Suche nach Components
                    component_elements = driver.find_elements(By.XPATH,
                        "//strong[contains(@title, 'Component') or contains(@class, 'name')]"
                        "/following::span[contains(@class, 'value')]//a[contains(@href, 'component')]")

                    for elem in component_elements:
                        component_code = elem.text.strip()
                        component_title = elem.get_attribute("title")

                        if component_code and not any(comp["code"] == component_code for comp in data["components"]):
                            component_item = {
                                "code": component_code,
                                "title": component_title
                            }
                            data["components"].append(component_item)

                    logger.info(f"Mit Fallback-Methode {len(data['components'])} Components gefunden")
                except Exception as fallback_e:
                    logger.info(f"Keine Components gefunden")  # Geändert zu info statt warning


            # "is realized by" Links extrahieren
            try:
                # Allgemeine Suche nach Links, die auf "is realized by" hinweisen
                link_elements = driver.find_elements(By.XPATH,
                    "//dl[contains(@class, 'links-list')]/dt[contains(text(), 'is realized by') or @title='is realized by']"
                    "/..//a[contains(@class, 'issue-link')]")

                for link in link_elements:
                    issue_key_attr = link.get_attribute("data-issue-key")
                    link_text = link.text.strip()
                    link_href = link.get_attribute("href")

                    # Optional: Versuche, den Summary-Text zu finden
                    parent_element = link.find_element(By.XPATH, "./ancestor::div[contains(@class, 'link-content')]")
                    try:
                        summary_element = parent_element.find_element(By.XPATH, ".//span[contains(@class, 'link-summary')]")
                        summary_text = summary_element.text.strip()
                    except:
                        summary_text = ""

                    realized_by_item = {
                        "key": issue_key_attr or link_text,
                        "title": link_text,
                        "summary": summary_text,
                        "url": link_href
                    }

                    # Nur hinzufügen, wenn noch nicht vorhanden
                    if not any(item["key"] == realized_by_item["key"] for item in data["realized_by"]):
                        data["realized_by"].append(realized_by_item)

                logger.info(f"{len(data['realized_by'])} 'is realized by' Links gefunden")
            except Exception as e:
                logger.info(f"'is realized by' Links konnten nicht gefunden werden: {e}")


            # Child Issues extrahieren
            child_issues = DataExtractor._find_child_issues(driver)

            # Füge Child Issues zu den realized_by-Links hinzu
            for child in child_issues:
                # Prüfen, ob das Child Issue bereits in realized_by enthalten ist
                if not any(item["key"] == child["key"] for item in data["realized_by"]):
                    # Füge das Child Issue mit dem Type-Attribut "child" hinzu
                    child_realized_item = {
                        "key": child["key"],
                        "title": child["title"],
                        "summary": child["summary"],
                        "url": child["url"],
                        "relation_type": "child"  # Markiere als Child Issue
                    }
                    data["realized_by"].append(child_realized_item)

            # Markiere existierende realized_by Items als "realized_by" Beziehungstyp
            for item in data["realized_by"]:
                if "relation_type" not in item:
                    item["relation_type"] = "realized_by"

            if child_issues:
                logger.info(f"{len(child_issues)} Child Issues zu den realized_by-Links hinzugefügt")


            # Child Issues extrahieren und direkt im Datenobjekt speichern
            child_issues_list = DataExtractor._find_child_issues(driver) #
            if child_issues_list:
                data["child_issues"] = []
                for child_item in child_issues_list:
                    # Struktur an die "realized_by" anlehnen für konsistente Verarbeitung
                    child_issue_data = {
                        "key": child_item.get("key"),
                        "title": child_item.get("title", ""),
                        "summary": child_item.get("summary", ""),
                        "url": child_item.get("url"),
                        "relation_type": "child"
                    }
                    data["child_issues"].append(child_issue_data)
                logger.info(f"{len(data['child_issues'])} Child Issues direkt extrahiert.")

        except Exception as e:
            logger.info(f"Fehler beim Extrahieren der Daten für {issue_key}: {e}")

        return data

    def extract_activity_details(self, html_content):
        """
        Extrahiert und filtert die Aktivitätsdetails. Kann jetzt mehrere
        Änderungen innerhalb einer einzigen Aktion korrekt verarbeiten.
        """
        soup = BeautifulSoup(html_content, 'lxml')
        action_containers = soup.find_all('div', class_='actionContainer')

        extracted_data = []
        ignored_fields = ['Checklists', 'Remote Link', 'Link', 'Kommentar oder Erstellung']

        for container in action_containers:
            # Benutzer und Zeitstempel gelten für alle Änderungen in diesem Container
            user_name = "N/A"
            timestamp_iso = "N/A"

            details_block = container.find('div', class_='action-details')
            if not details_block:
                continue

            user_tag = details_block.find('a', class_='user-hover')
            if user_tag:
                user_name = user_tag.get_text(strip=True)

            time_tag = details_block.find('time', class_='livestamp')
            if time_tag:
                timestamp_iso = time_tag.get('datetime', 'N/A')

            body_block = container.find('div', class_='action-body')
            if body_block:
                # NEUE LOGIK: Finde alle Zeilen (tr) mit Änderungen
                change_rows = body_block.find_all('tr')
                for row in change_rows:
                    activity_name_tag = row.find('td', class_='activity-name')
                    if not activity_name_tag:
                        continue

                    activity_name = activity_name_tag.get_text(strip=True)
                    if activity_name in ignored_fields:
                        continue

                    old_value = "N/A"
                    new_value = "N/A"

                    old_val_tag = row.find('td', class_='activity-old-val')
                    if old_val_tag:
                        old_value = old_val_tag.get_text(strip=True)

                    new_val_tag = row.find('td', class_='activity-new-val')
                    if new_val_tag:
                        full_text = new_val_tag.get_text(strip=True)

                        if activity_name == 'Status':
                            try:
                                new_value = full_text.split(':')[1].split('[')[0].strip().upper()
                            except IndexError:
                                new_value = full_text.strip().upper()
                        elif activity_name == 'Fix Version/s':
                            match = re.search(r'(Q\d_\d{2})', full_text)
                            new_value = match.group(1) if match else full_text
                        elif activity_name in ['Acceptance Criteria', 'Description']:
                            new_value = '[...]'
                        else:
                            new_value = full_text if len(full_text) <= 100 else full_text[:100] + "..."

                    # Erstelle für jede einzelne Änderung einen eigenen Eintrag
                    extracted_data.append({
                        'benutzer': user_name,
                        'feld_name': activity_name,
                        'alter_wert': old_value,
                        'neuer_wert': new_value,
                        'zeitstempel_iso': timestamp_iso
                    })

        # Die finale Liste wird wie gewohnt umgedreht, um chronologisch zu sein
        return extracted_data[::-1]
