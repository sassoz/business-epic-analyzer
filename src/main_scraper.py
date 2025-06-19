"""
Jira Issue Link Scraper

This script automates the process of extracting, analyzing, and summarizing Jira issue data.
It coordinates multiple components to create a comprehensive knowledge base from Jira issues.

WORKFLOW:
1. Retrieves Business Epic IDs from a text file (default: BE_Liste.txt)
2. [Optional] Scrapes Jira issues recursively (controlled by SCRAPE_HTML flag):
   - Logs into Jira using the provided credentials
   - Extracts data from each issue page
   - Follows "is realized by" links and child issues recursively
   - Stores extracted data as JSON files
   - Cleans up any Story issues to maintain a clean hierarchy
3. For each Business Epic:
   - Builds a hierarchical graph representing issue relationships
   - Creates a visual diagram of the issue hierarchy (PNG format)
   - Generates a structured JSON context containing all issue data
   - Uses AI (Claude/GPT) to create a concise summary of the issue tree
   - Produces an HTML report with embedded visualizations

COMPONENTS:
- JiraScraper: Handles web scraping of Jira issue pages
- JiraTreeGenerator: Builds graph representations of issue relationships
- JiraTreeVisualizer: Generates visual diagrams of issue hierarchies
- JiraContextGenerator: Creates structured context data for AI processing
- ClaudeAPIClient: Interfaces with Claude API for summary generation
- EpicHtmlGenerator: Creates formatted HTML reports

CONFIGURATION:
- LLM_MODEL_HTML_GENERATOR: Model for HTML generation (default: gpt-4.1-mini)
- LLM_MODEL_BUSINESS_VALUE: Model for business value extraction (default: claude-3-7-sonnet-latest)
- LLM_MODEL_SUMMARY: Model for summary generation (default: gpt-4.1)
- SCRAPE_HTML: Controls whether to perform web scraping (default: False)

USAGE:
1. Ensure a text file containing Business Epic IDs (one per line) is available
2. Run the script: python main_scraper.py
3. If prompted, enter the path to the Business Epic file or press Enter for default
4. The script will process all epics and generate output files in the configured directories

OUTPUT DIRECTORIES:
- JIRA_ISSUES_DIR: Extracted JSON data
- ISSUE_TREES_DIR: Visual diagrams of issue hierarchies
- JSON_SUMMARY_DIR: AI-generated summaries in JSON format
- HTML_REPORTS_DIR: Complete HTML reports

NOTES:
- The script is designed to work with Deutsche Telekom's Jira instance
- Login credentials are hardcoded and should be updated for different users
- The modular design enables maintenance and extension of individual components
"""

import os
import sys
import json
import argparse
from utils.jira_scraper import JiraScraper
from utils.cleanup_story_json import cleanup_story_issues
from utils.jira_tree_classes import JiraTreeGenerator, JiraTreeVisualizer, JiraContextGenerator
from utils.azure_ai_client import AzureAIClient
from utils.epic_html_generator import EpicHtmlGenerator
from utils.token_usage_class import TokenUsage
from utils.logger_config import logger
from utils.json_parser import LLMJsonParser
from utils.config import JIRA_ISSUES_DIR, DATA_DIR, HTML_REPORTS_DIR, JSON_SUMMARY_DIR

from utils.config import (
    JIRA_ISSUES_DIR,
    DATA_DIR,
    HTML_REPORTS_DIR,
    JSON_SUMMARY_DIR,
    LLM_MODEL_HTML_GENERATOR,
    LLM_MODEL_BUSINESS_VALUE,
    LLM_MODEL_SUMMARY,
    DEFAULT_SCRAPE_HTML,
    JIRA_EMAIL,
    PROMPTS_DIR
)

def load_prompt(filename, key):
    """Lädt einen Prompt aus einer YAML-Datei im PROMPTS_DIR."""
    file_path = os.path.join(PROMPTS_DIR, filename)
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            prompts = yaml.safe_load(file)
            return prompts[key]
    except FileNotFoundError:
        logger.error(f"Prompt-Datei nicht gefunden: {file_path}")
        sys.exit(1) # Beendet das Skript, wenn ein Prompt fehlt
    except KeyError:
        logger.error(f"Schlüssel '{key}' nicht in der Prompt-Datei '{filename}' gefunden.")
        sys.exit(1)

def get_business_epics_from_file(file_path=None):
    """Lädt Business Epics aus einer Textdatei."""
    print("\n=== Telekom Jira Issue Extractor und Analyst ===")
    print("Bitte geben Sie den Pfad zur TXT-Datei mit Business Epics ein (oder drücken Sie Enter für 'BE_Liste.txt'):")
    if not file_path:
        file_path = "BE_Liste.txt"
    # Überprüfe, ob die Datei existiert
    if os.path.exists(file_path):
        file_to_try = file_path
    # Falls nicht, versuche es mit .txt-Erweiterung
    elif os.path.exists(file_path + ".txt"):
        file_to_try = file_path + ".txt"
        print(f"Hinweis: Verwende Datei '{file_to_try}'")
    else:
        print(f"FEHLER: Die Datei {file_path} oder {file_path}.txt existiert nicht.")
        return []

    # Business Epics aus der Datei lesen
    business_epics = []
    with open(file_to_try, 'r') as file:
        for line in file:
            epic = line.strip()
            if epic:  # Leere Zeilen ignorieren
                business_epics.append(epic)
    print(f"{len(business_epics)} Business Epics gefunden.")
    return business_epics


def main():
    """Hauptfunktion zum Ausführen des Skripts mit Befehlszeilenparametern."""
    # Befehlszeilenparameter definieren
    parser = argparse.ArgumentParser(description='Jira Issue Link Scraper')
    parser.add_argument('--scraper', type=lambda x: x.lower() == 'true', default=DEFAULT_SCRAPE_HTML,
                        help=f'Aktiviert oder deaktiviert das Scraping von Jira (True/False, Standard: {DEFAULT_SCRAPE_HTML})')
    parser.add_argument('--issue', type=str, default=None,
                    help='Spezifische Jira-Issue-ID zur Verarbeitung (z.B. BEMABU-12345)')
    parser.add_argument('--file', type=str, default=None,
                        help='Pfad zur TXT-Datei mit Business Epics (Standard: Interaktive Eingabe oder "BE_Liste.txt")')

    args = parser.parse_args()
    SCRAPE_HTML = args.scraper

    """Hauptfunktion zum Ausführen des Skripts."""
    # Initialisiere den Token-Tracker einmal
    token_tracker = TokenUsage(log_file_path="logs/token_usage.jsonl")  # Ohne Datum für kontinuierliches Logging

    # Überprüfe, ob eine spezifische Issue-ID übergeben wurde
    if args.issue:
        # Wenn ja, verwende diese als einziges Business Epic
        business_epics = [args.issue]
        print(f"Verarbeite einzelnes Issue: {args.issue}")
    else:
        # Ansonsten lade Business Epics aus der Datei
        business_epics = get_business_epics_from_file(args.file)

    if not business_epics:
        print("Keine Business Epics gefunden. Programm wird beendet.")
        return

    email = JIRA_EMAIL
    json_dir = JIRA_ISSUES_DIR
    output_dir = DATA_DIR


    # Stelle sicher, dass die Ausgabeverzeichnisse existieren
    os.makedirs(output_dir, exist_ok=True)

    # 1. Client für allgemeine Aufgaben (z.B. die Zusammenfassung)
    azure_summary_client = AzureAIClient(system_prompt="Du bist ein hilfreicher Assistent für die Analyse von Jira-Tickets.")

    # 2. Spezialisierter Client für die Datenextraktion aus dem Business Value
    business_value_system_prompt = load_prompt("business_value_prompt.yaml", "system_prompt")
    azure_extraction_client = AzureAIClient(system_prompt=business_value_system_prompt)

    # Initialisiere den Scraper nur einmal mit dem ersten Epic
    if business_epics and SCRAPE_HTML==True:
        first_epic = business_epics[0]
        first_url = f"https://jira.telekom.de/browse/{first_epic}"
        scraper = JiraScraper(
            first_url,
            email,
            model=LLM_MODEL_BUSINESS_VALUE,
            token_tracker=token_tracker,
            azure_client=azure_extraction_client
        )

        # Verarbeite alle Business Epics
        for i, epic in enumerate(business_epics):
            print(f"\n\n=============================================================\nVerarbeite Business Epic {i+1}/{len(business_epics)}: {epic}")
            # Für das erste Epic verwenden wir den bereits initialisierten Scraper
            if i == 0:
                scraper.run()
            else:
                # Für alle weiteren Epics aktualisieren wir nur die URL und setzen den Zustand zurück
                new_url = f"https://jira.telekom.de/browse/{epic}"
                scraper.url = new_url
                scraper.processed_issues = set()  # Zurücksetzen der verarbeiteten Issues
                scraper.run(skip_login=True)  # Überspringe den Login-Prozess für folgende Epics

        # Browser am Ende schließen
        if scraper.login_handler:
            scraper.login_handler.close()

        # Bereinige Jira Issues um mögliche Story Einträge
        cleanup_story_issues(json_dir)

    # Initialisiere die Klassen für die Verarbeitung
    generator = JiraTreeGenerator(json_dir=json_dir)
    visualizer = JiraTreeVisualizer(format='png')
    context_generator = JiraContextGenerator()
    html_generator = EpicHtmlGenerator(model = LLM_MODEL_HTML_GENERATOR, token_tracker=token_tracker)
    parser = LLMJsonParser()

    # Erstelle Visualisierungen und Zusammenfassungen für alle Business Epics
    for epic in business_epics:
        # Build the tree using the generator
        tree = generator.build_issue_tree(epic)
        if tree is None:
            print(f"Fehler bei der Erstellung des Trees für {epic}")
            continue

        # Create visualization
        visualizer.visualize(tree, epic)

        # Generate context
        json_context = context_generator.generate_context(tree, epic)
        if not json_context:
            logger.error(f"Fehler bei der Erstellung des Kontexts für {epic}")
            continue

        # Prompt
        summary_prompt_template = load_prompt("summary_prompt.yaml", "user_prompt_template")
        summary_prompt = summary_prompt_template.format(json_context=json_context)

        # Rufen Sie den neuen Client für die Zusammenfassung auf
        response_data = azure_summary_client.completion(
            model_name=LLM_MODEL_SUMMARY,  # z.B. "o3-mini"
            user_prompt=summary_prompt,
            max_tokens=20000,
            response_format={"type": "json_object"} # Fordert eine JSON-Ausgabe an
        )

        # Loggen Sie die Token-Nutzung
        if token_tracker and "usage" in response_data:
            token_tracker.log_usage(
                model=LLM_MODEL_SUMMARY,
                input_tokens=response_data["usage"]["prompt_tokens"],
                output_tokens=response_data["usage"]["completion_tokens"],
                total_tokens=response_data["usage"]["total_tokens"],
                task_name="summary_generation"
            )

        json_summary = parser.extract_and_parse_json(response_data["text"])

        if json_summary != '{}':
            with open(os.path.join(JSON_SUMMARY_DIR, f"{epic}_json_summary.json"), 'w', encoding='utf-8') as file:
                json.dump(json_summary, file)

            # HTML generieren und speichern
            html_file = os.path.join(HTML_REPORTS_DIR, f"{epic}_summary.html")
            html_content = html_generator.generate_epic_html(json_summary, epic, html_file)
        else:
            logger.error(f"Fehler bei der Erstellung der JSON_Summary für {epic}")
            continue


if __name__ == "__main__":
    main()
