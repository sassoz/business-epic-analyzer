# main_scraper.py

import os
import re
import sys
import json
import argparse
import yaml
import time
import threading
import subprocess

# Fügen Sie das übergeordnete Verzeichnis (Projekt-Root) zum Suchpfad hinzu...
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from utils.jira_scraper import JiraScraper
from utils.jira_tree_classes import JiraTreeGenerator, JiraTreeVisualizer, JiraContextGenerator
from utils.azure_ai_client import AzureAIClient
from utils.epic_html_generator import EpicHtmlGenerator
from utils.token_usage_class import TokenUsage
from utils.logger_config import logger
from utils.json_parser import LLMJsonParser

from utils.project_data_provider import ProjectDataProvider
from features.console_reporter import ConsoleReporter
from features.json_summary_generator import JsonSummaryGenerator

# Importiere die spezifischen Analyzer-Klassen
from features.scope_analyzer import ScopeAnalyzer
from features.dynamics_analyzer import DynamicsAnalyzer
from features.status_analyzer import StatusAnalyzer
from features.time_creep_analyzer import TimeCreepAnalyzer
from features.backlog_analyzer import BacklogAnalyzer
from features.analysis_runner import AnalysisRunner



from utils.config import (
    JIRA_ISSUES_DIR,
    JSON_SUMMARY_DIR,
    HTML_REPORTS_DIR,
    LLM_MODEL_HTML_GENERATOR,
    LLM_MODEL_BUSINESS_VALUE,
    LLM_MODEL_SUMMARY,
    DEFAULT_SCRAPE_HTML,
    JIRA_EMAIL,
    PROMPTS_DIR,
    TOKEN_LOG_FILE,
    SCRAPER_CHECK_DAYS,
    ISSUE_LOG_FILE,
    JIRA_TREE_MANAGEMENT,
    JIRA_TREE_FULL
)

# Zentrale Liste der zu verwendenden Analyzer
ANALYZERS_TO_RUN = [
    ScopeAnalyzer,
    #DynamicsAnalyzer,
    StatusAnalyzer,
    TimeCreepAnalyzer,
    BacklogAnalyzer
]


def prevent_screensaver(stop_event):
    """
    Läuft in einem separaten Thread und drückt alle 8 Minuten die Leertaste via
    AppleScript, um den System-Bildschirmschoner zu verhindern.
    """
    logger.info("Keep-Awake-Thread gestartet. Drückt alle 8 Minuten die Leertaste.")
    while not stop_event.is_set():
        if stop_event.wait(480):
            break
        if not stop_event.is_set():
            try:
                script = 'tell application "System Events" to key code 49'
                subprocess.run(['osascript', '-e', script], check=True, capture_output=True)
                logger.info("Keep-Awake: Leertaste gedrückt, um den Bildschirmschoner zu verhindern.")
            except subprocess.CalledProcessError as e:
                logger.error(f"Keep-Awake-Fehler: AppleScript konnte nicht ausgeführt werden. {e}")
            except FileNotFoundError:
                logger.error("Keep-Awake-Fehler: 'osascript' Befehl nicht gefunden. Nur auf macOS verfügbar.")
                break
    logger.info("Keep-Awake-Thread wurde beendet.")

def perform_final_retry(azure_client, token_tracker):
    """
    Liest hartnäckig fehlgeschlagene Issues aus einer Log-Datei
    und versucht einen letzten, gezielten Scraping-Durchlauf für diese.
    """
    if not os.path.exists(ISSUE_LOG_FILE) or os.path.getsize(ISSUE_LOG_FILE) == 0:
        logger.info("Keine fehlgeschlagenen Issues in der Log-Datei gefunden. Überspringe finalen Retry.")
        return
    logger.info(f"--- Starte finalen Retry-Versuch für Issues aus '{ISSUE_LOG_FILE}' ---")
    with open(ISSUE_LOG_FILE, 'r') as f:
        failed_keys = [line.strip() for line in f if line.strip()]
    if not failed_keys:
        logger.info("Log-Datei ist leer. Kein Retry notwendig.")
        return
    retry_scraper = JiraScraper(
        f"https://jira.telekom.de/browse/{failed_keys[0]}", JIRA_EMAIL,
        model=LLM_MODEL_BUSINESS_VALUE, token_tracker=token_tracker,
        azure_client=azure_client, scrape_mode='true', check_days=0
    )
    login_success = retry_scraper.login_handler.login(retry_scraper.url, retry_scraper.email)
    if not login_success:
        logger.error("Login für den finalen Retry-Versuch fehlgeschlagen. Breche ab.")
        return
    successful_retries, persistent_failures = [], []
    for key in failed_keys:
        logger.info(f"Dritter Versuch für Issue: {key}")
        url = f"https://jira.telekom.de/browse/{key}"
        issue_data = retry_scraper.extract_and_save_issue_data(url, key)
        if issue_data:
            logger.info(f"Issue {key} im dritten Anlauf erfolgreich verarbeitet.")
            successful_retries.append(key)
        else:
            logger.warning(f"Issue {key} konnte auch im dritten Anlauf nicht verarbeitet werden.")
            persistent_failures.append(key)
    retry_scraper.login_handler.close()
    with open(ISSUE_LOG_FILE, 'w') as f:
        for key in persistent_failures: f.write(f"{key}\n")
    logger.info("--- Finaler Retry-Versuch abgeschlossen. ---")
    logger.info(f"Erfolgreich nachgeholt: {len(successful_retries)}")
    logger.info(f"Endgültig fehlgeschlagen: {len(persistent_failures)}")

def load_prompt(filename, key):
    """Lädt einen Prompt aus einer YAML-Datei im PROMPTS_DIR."""
    file_path = os.path.join(PROMPTS_DIR, filename)
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            prompts = yaml.safe_load(file)
            return prompts[key]
    except (FileNotFoundError, KeyError) as e:
        logger.error(f"Fehler beim Laden des Prompts: {e}")
        sys.exit(1)

def get_business_epics_from_file(file_path=None):
    """
    Lädt und extrahiert Business Epic IDs aus einer Textdatei.
    """
    print("\n=== Telekom Jira Issue Extractor und Analyst ===")
    if not file_path:
        file_path = input("Bitte geben Sie den Pfad zur TXT-Datei mit Business Epics ein (oder drücken Sie Enter für 'BE_Liste.txt'): ")
        if not file_path:
            file_path = "BE_Liste.txt"

    file_to_try = file_path if os.path.exists(file_path) else f"{file_path}.txt"
    if not os.path.exists(file_to_try):
        print(f"FEHLER: Die Datei {file_to_try} existiert nicht.")
        return []

    business_epics = []
    epic_id_pattern = re.compile(r'[A-Z][A-Z0-9]*-\d+')

    with open(file_to_try, 'r', encoding='utf-8') as file:
        for line in file:
            match = epic_id_pattern.search(line)
            if match:
                business_epics.append(match.group(0))

    print(f"{len(business_epics)} Business Epics gefunden.")
    return business_epics

def main():
    """
    Hauptfunktion zur Orchestrierung des Skripts.
    """
    parser = argparse.ArgumentParser(description='Jira Issue Link Scraper')
    parser.add_argument('--scraper', type=str.lower, choices=['true', 'false', 'check'], default='check', help='Steuert das Scraping')
    # +++ ANPASSUNG: Choices für html_summary erweitert +++
    parser.add_argument('--html_summary', type=str.lower, choices=['true', 'false', 'check'], default='false', help="Erstellt JSON-Zusammenfassung und HTML-Report. 'true': immer neu; 'check': aus Cache, falls vorhanden; 'false': keine Erstellung.")
    parser.add_argument('--issue', type=str, default=None, help='Spezifische Jira-Issue-ID')
    parser.add_argument('--file', type=str, default=None, help='Pfad zur TXT-Datei mit Business Epics')
    args = parser.parse_args()

    stop_event = threading.Event()
    keep_awake_thread = threading.Thread(target=prevent_screensaver, args=(stop_event,))
    keep_awake_thread.daemon = True
    keep_awake_thread.start()

    try:
        token_tracker = TokenUsage(log_file_path=TOKEN_LOG_FILE)
        business_epics = [args.issue] if args.issue else get_business_epics_from_file(args.file)
        if not business_epics:
            print("Keine Business Epics gefunden. Programm wird beendet.")
            return

        if args.scraper != 'false':
            print(f"\n--- Scraping-Modus gestartet (Mode: {args.scraper}) ---")
            business_value_system_prompt = load_prompt("business_value_prompt.yaml", "system_prompt")
            azure_extraction_client = AzureAIClient(system_prompt=business_value_system_prompt)

            scraper = JiraScraper(
                f"https://jira.telekom.de/browse/{business_epics[0]}", JIRA_EMAIL,
                model=LLM_MODEL_BUSINESS_VALUE, token_tracker=token_tracker,
                azure_client=azure_extraction_client, scrape_mode=args.scraper,
                check_days=SCRAPER_CHECK_DAYS
            )
            for i, epic in enumerate(business_epics):
                print(f"\n\n=============================================================\nVerarbeite Business Epic {i+1}/{len(business_epics)}: {epic}")
                scraper.url = f"https://jira.telekom.de/browse/{epic}"
                scraper.processed_issues = set()
                scraper.run(skip_login=(i > 0))
            if scraper.login_handler: scraper.login_handler.close()
        else:
            print("\n--- Scraping übersprungen (Mode: 'false') ---")

        # +++ NEUE, VEREINHEITLICHTE LOGIK FÜR ANALYSE UND REPORTING +++
        if args.html_summary != 'false':
            print("\n--- Analyse / Reporting gestartet ---")

            # Initialisierung der benötigten Clients und Generatoren
            azure_summary_client = AzureAIClient()
            visualizer = JiraTreeVisualizer(format='png')
            context_generator = JiraContextGenerator()
            html_generator = EpicHtmlGenerator(model=LLM_MODEL_HTML_GENERATOR, token_tracker=token_tracker)
            json_parser = LLMJsonParser()
            analysis_runner = AnalysisRunner(ANALYZERS_TO_RUN)
            json_summary_generator = JsonSummaryGenerator()
            reporter = ConsoleReporter()


            for epic in business_epics:
                print(f"\n--- Starte Verarbeitung für {epic} ---")
                complete_epic_data = None
                complete_summary_path = os.path.join(JSON_SUMMARY_DIR, f"{epic}_complete_summary.json")

                # Schritt 1: Prüfen, ob eine gecachte Datei verwendet werden soll ('check'-Modus)
                if args.html_summary == 'check' and os.path.exists(complete_summary_path):
                    logger.info(f"Lade vollständige Zusammenfassung aus Cache: {complete_summary_path}")
                    try:
                        with open(complete_summary_path, 'r', encoding='utf-8') as f:
                            complete_epic_data = json.load(f)
                    except (json.JSONDecodeError, IOError) as e:
                        logger.info(f"Konnte Cache-Datei nicht lesen ({e}). Erstelle Zusammenfassung neu.")

                # Schritt 2: Wenn keine Cache-Datei vorhanden oder '--html_summary true', alles neu generieren
                if complete_epic_data is None:
                    logger.info("Keine gültige Cache-Datei gefunden oder Neuerstellung erzwungen. Generiere alle Daten...")

                    # 2a: Metrische Analysen durchführen
                    data_provider = ProjectDataProvider(epic_id=epic, hierarchy_config=JIRA_TREE_FULL)
                    if not data_provider.is_valid():
                        logger.error(f"Fehler: Konnte keine gültigen Daten für Analyse von Epic '{epic}' laden. Verarbeitung wird übersprungen.")
                        continue
                    print(f"     - Erstelle Analyse für {epic}")
                    analysis_results = analysis_runner.run_analyses(data_provider)
                    reporter.create_backlog_plot(analysis_results.get("BacklogAnalyzer", {}), epic)

                    # Optional: Konsolen-Reporting der Analyse-Ergebnisse
                    #reporter.report_scope(analysis_results.get("ScopeAnalyzer", {}))
                    #reporter.report_status(analysis_results.get("StatusAnalyzer", {}), epic)
                    #reporter.report_time_creep(analysis_results.get("TimeCreepAnalyzer",{}))
                    #reporter.create_activity_and_creep_plot(analysis_results.get("TimeCreepAnalyzer",{}), data_provider.all_activities, epic)
                    #reporter.report_backlog(analysis_results.get("BacklogAnalyzer", {}))

                    # 2b: Inhaltliche Zusammenfassung per LLM erstellen
                    tree_generator_mgmt = JiraTreeGenerator(allowed_types=JIRA_TREE_MANAGEMENT)
                    issue_tree_mgmt = tree_generator_mgmt.build_issue_tree(epic)
                    visualizer.visualize(issue_tree_mgmt, epic) # Baum-Visualisierung erstellen
                    json_context = context_generator.generate_context(issue_tree_mgmt, epic)
                    summary_prompt_template = load_prompt("summary_prompt.yaml", "user_prompt_template")
                    summary_prompt = summary_prompt_template.format(json_context=json_context)

                    print(f"     - Erstelle Summary für {epic}")

                    response_data = azure_summary_client.completion(
                        model_name=LLM_MODEL_SUMMARY,
                        user_prompt=summary_prompt,
                        max_tokens=20000,
                        response_format={"type": "json_object"}
                    )

                    # Token-Nutzung loggen
                    if token_tracker and "usage" in response_data:
                        usage = response_data["usage"]
                        token_tracker.log_usage(
                            model=LLM_MODEL_SUMMARY,
                            input_tokens=usage.prompt_tokens,
                            output_tokens=usage.completion_tokens,
                            total_tokens=usage.total_tokens,
                            task_name=f"summary_generation"
                        )

                    content_summary = json_parser.extract_and_parse_json(response_data["text"])

                    # Status aus dem DataProvider holen
                    epic_status = data_provider.issue_details.get(epic, {}).get('status', 'Unbekannt')
                    target_start_status = data_provider.issue_details.get(epic, {}).get('target_start', 'Unbekannt')
                    target_end_status = data_provider.issue_details.get(epic, {}).get('target_end', 'Unbekannt')
                    fix_version_status = data_provider.issue_details.get(epic, {}).get('fix_versions', 'Unbekannt')

                    # Ein neues, geordnetes Dictionary erstellen und den Status einfügen
                    ordered_content_summary = {
                        "epicId": content_summary.get("epicId"),
                        "title": content_summary.get("title"),
                        "status": epic_status,
                        "target_start": target_start_status,
                        "target_end": target_end_status,
                        "fix_versions": fix_version_status
                    }
                    # Den Rest der ursprünglichen Zusammenfassung hinzufügen
                    ordered_content_summary.update({k: v for k, v in content_summary.items() if k not in ordered_content_summary})
                    content_summary = ordered_content_summary

                    # 2c: Alle Daten fusionieren und als eine JSON-Datei speichern
                    complete_epic_data = json_summary_generator.generate_and_save_complete_summary(
                        analysis_results=analysis_results,
                        content_summary=content_summary,
                        epic_id=epic
                    )

                # Schritt 3: HTML-Datei aus den vollständigen Daten (neu oder aus Cache) erstellen
                if complete_epic_data:
                    print(f"     - Erstelle HTML-File für {epic}")
                    logger.info(f"Erstelle HTML-Report für {epic}...")
                    html_file = os.path.join(HTML_REPORTS_DIR, f"{epic}_summary.html")
                    # Der Generator erhält nun das vollständige, zusammengeführte Datenobjekt
                    html_generator.generate_epic_html(complete_epic_data, epic, html_file)
                else:
                    logger.error(f"Konnte keine vollständigen Daten für die HTML-Erstellung von {epic} erzeugen.")

        else:
            print("\n--- Analyse und HTML-Summary übersprungen ---")

    finally:
        logger.info("Hauptprogramm wird beendet. Stoppe den Keep-Awake-Thread...")
        stop_event.set()
        keep_awake_thread.join(timeout=2)

if __name__ == "__main__":
    main()
