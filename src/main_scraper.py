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
- Set SCRAPE_HTML to True to enable web scraping; otherwise, the script will use existing JSON files
- The modular design enables maintenance and extension of individual components
"""

import os
import sys
from utils.jira_scraper import JiraScraper
from utils.cleanup_story_json import cleanup_story_issues
from utils.jira_tree_classes import JiraTreeGenerator, JiraTreeVisualizer, JiraContextGenerator
from utils.claude_api_integration import ClaudeAPIClient
from utils.epic_html_generator import EpicHtmlGenerator
from utils.token_usage_class import TokenUsage
from utils.config import JIRA_ISSUES_DIR, DATA_DIR, HTML_REPORTS_DIR, JSON_SUMMARY_DIR

LLM_MODEL_HTML_GENERATOR = "gpt-4.1-mini"
LLM_MODEL_BUSINESS_VALUE = "claude-3-7-sonnet-latest"
#LLM_MODEL_SUMMARY = "claude-3-7-sonnet-latest"
LLM_MODEL_SUMMARY = "gpt-4.1"

SCRAPE_HTML = False

def get_business_epics_from_file():
    """Lädt Business Epics aus einer Textdatei."""
    print("\n=== Telekom Jira Issue Extractor und Analyst ===")
    print("Bitte geben Sie den Pfad zur TXT-Datei mit Business Epics ein (oder drücken Sie Enter für 'BE_Liste.txt'):")
    file_path = input("> ").strip()
    # Wenn kein Pfad angegeben wird, Standardwert verwenden
    if not file_path:
        file_path = "BE_Liste.txt"
    # Prüfen, ob die Datei existiert
    if not os.path.exists(file_path):
        print(f"FEHLER: Die Datei {file_path} existiert nicht.")
        return []
    # Business Epics aus der Datei lesen
    business_epics = []
    with open(file_path, 'r') as file:
        for line in file:
            epic = line.strip()
            if epic:  # Leere Zeilen ignorieren
                business_epics.append(epic)
    print(f"{len(business_epics)} Business Epics gefunden.")
    return business_epics


def main():
    """Hauptfunktion zum Ausführen des Skripts."""
    # Initialisiere den Token-Tracker einmal
    token_tracker = TokenUsage(log_file_path="logs/token_usage.jsonl")  # Ohne Datum für kontinuierliches Logging

    # Lade Business Epics aus der Datei
    business_epics = get_business_epics_from_file()

    if not business_epics:
        print("Keine Business Epics gefunden. Programm wird beendet.")
        return

    email = "ralf.niemeyer@telekom.de"
    json_dir = JIRA_ISSUES_DIR
    output_dir = DATA_DIR

    # Stelle sicher, dass die Ausgabeverzeichnisse existieren
    os.makedirs(output_dir, exist_ok=True)

    # Initialisiere den Scraper nur einmal mit dem ersten Epic
    if business_epics and SCRAPE_HTML==True:
        first_epic = business_epics[0]
        first_url = f"https://jira.telekom.de/browse/{first_epic}"
        scraper = JiraScraper(first_url, email, model = LLM_MODEL_BUSINESS_VALUE, token_tracker=token_tracker)

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
    claude_client = ClaudeAPIClient(model = LLM_MODEL_SUMMARY, token_tracker=token_tracker)

    # Erstelle Visualisierungen und Zusammenfassungen für alle Business Epics
    for epic in business_epics:
        # Build the tree using the generator
        tree = generator.build_issue_tree(epic)
        if tree is None:
            print(f"Fehler bei der Erstellung des Trees für {epic}")
            continue

        # Create visualization
        if visualizer.visualize(tree, epic):
            print(f"Visualisierung für {epic} erfolgreich erstellt")
        else:
            print(f"Fehler bei der Erstellung der Visualisierung für {epic}")

        # Generate context
        json_context = context_generator.generate_context(tree, epic)
        if json_context:
            print(f"Kontext für {epic} erfolgreich erstellt ")
        else:
            print(f"Fehler bei der Erstellung des Kontexts für {epic}")
            continue

        # Generate summary
        try:
            json_summary = claude_client.generate_summary(json_context)
            with open(os.path.join(JSON_SUMMARY_DIR, f"{epic}_json_summary.json"), 'w', encoding='utf-8') as file:
                file.write(json_summary)
        except Exception as e:
            print(f"Fehler bei der Erstellung der Zusammenfassung für {epic}: {e}")

        # HTML generieren und speichern
        html_file = os.path.join(HTML_REPORTS_DIR, f"{epic}_summary.html")
        try:
            html_content = html_generator.generate_epic_html(json_summary, epic, html_file)
            print(f"HTML-Zusammenfassung für {epic} erfolgreich erstellt und gespeichert in: {html_file}")
        except Exception as e:
            print(f"Fehler bei der Erstellung der HTML-Zusammenfassung für {epic}: {e}")



if __name__ == "__main__":
    main()
