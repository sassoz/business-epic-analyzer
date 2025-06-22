# JIRA Business Epic Analyzer and Reporter

Ein umfassendes Tool, das die Extraktion, Analyse, Visualisierung und Berichterstattung von JIRA Business Epics automatisiert. Dieses Projekt extrahiert JIRA-Vorgänge, analysiert deren Beziehungen, generiert visuelle Darstellungen der Hierarchie und erstellt mithilfe von KI-gestützten Zusammenfassungen detaillierte HTML-Berichte.

## Features

-   **Automatisierte JIRA-Extraktion**: Meldet sich bei JIRA an und extrahiert rekursiv Daten von Business Epics, verknüpften Vorgängen ("is realized by") und Kind-Vorgängen.
-   **Hierarchie-Visualisierung**: Erstellt mit GraphViz automatisch Baumdiagramme, um die Beziehungen zwischen den Vorgängen darzustellen.
-   **KI-gestützte Analyse**: Nutzt leistungsstarke Sprachmodelle (LLMs) via Azure AI, um den geschäftlichen Nutzen zu extrahieren und umfassende Zusammenfassungen zu generieren.
-   **HTML-Berichterstellung**: Generiert gut lesbare und formatierte HTML-Berichte aus Vorlagen, die die KI-Zusammenfassungen und Visualisierungen enthalten.
-   **Robuste Datenverarbeitung**: Bereinigt und strukturiert die extrahierten JIRA-Daten für eine konsistente Analyse.
-   **Flexible Konfiguration**: Ermöglicht die einfache Konfiguration von LLM-Modellen, Anmeldeinformationen und Skriptverhalten über eine Konfigurationsdatei und Umgebungsvariablen.
-   **Detailliertes Logging**: Verfolgt die Token-Nutzung für LLM-Aufrufe und protokolliert den Fortschritt des gesamten Prozesses.

## Quick Start

Folgen Sie diesen Schritten, um das Tool schnell in Betrieb zu nehmen.

1.  **Repository klonen und installieren**:
    ```bash
    git clone <repository_url>
    cd business-epic-analyzer
    pip install -r requirements.txt
    ```

2.  **Umgebungsvariablen einrichten**:
    Erstellen Sie eine `.env`-Datei im Stammverzeichnis des Projekts und fügen Sie Ihre Azure AI-Anmeldeinformationen hinzu:
    ```env
    AZURE_OPENAI_API_KEY="IHR_OPENAI_API_SCHLUESSEL"
    AZURE_OPENAI_API_VERSION="IHRE_API_VERSION"
    AZURE_OPENAI_ENDPOINT="IHR_OPENAI_ENDPOINT"

    AZURE_AIFOUNDRY_API_KEY="IHR_AIFOUNDRY_API_SCHLUESSEL"
    AZURE_AIFOUNDRY_ENDPOINT="IHR_AIFOUNDRY_ENDPOINT"
    ```

3.  **JIRA-Vorgänge definieren**:
    Erstellen Sie eine Textdatei (z. B. `BE_Liste.txt`) und fügen Sie die JIRA Business Epic-Keys hinzu, die Sie analysieren möchten (einer pro Zeile):
    ```
    BEMABU-1825
    BEMABU-1844
    ```

4.  **Skript ausführen**:
    Führen Sie das Hauptskript aus dem `src`-Verzeichnis aus. Standardmäßig wird das Scraping aktiviert.
    ```bash
    python src/main_scraper.py --file BE_Liste.txt
    ```

5.  **Ergebnisse prüfen**:
    Die generierten Berichte und Artefakte finden Sie in den folgenden Verzeichnissen im `data`-Ordner:
    -   `data/html_reports/`: Fertige HTML-Zusammenfassungen.
    -   `data/issue_trees/`: PNG-Visualisierungen der Vorgangshierarchien.
    -   `data/json_summary/`: KI-generierte JSON-Zusammenfassungen.
    -   `data/jira_issues/`: Rohe JSON-Daten, die aus JIRA extrahiert wurden.

## CLI Reference

Das Skript kann über die Befehlszeile mit den folgenden Argumenten gesteuert werden:

| Argument    | Typ     | Standard                               | Beschreibung                                                                               |
| :---------- | :------ | :------------------------------------- | :----------------------------------------------------------------------------------------- |
| `--scraper` | `true/false` | `true`                                 | Aktiviert (`true`) oder deaktiviert (`false`) das Live-Scraping von Daten aus JIRA.        |
| `--issue`   | `string`  | `None`                                 | Verarbeitet eine einzelne, spezifische JIRA-Issue-ID anstelle einer Datei.                  |
| `--file`    | `string`  | `BE_Liste.txt` (nach interaktiver Eingabe) | Pfad zur `.txt`-Datei, die die Liste der Business Epic-Keys enthält.                       |

## Usage Examples

-   **Verarbeitung einer Liste von Epics mit Scraping (Standard)**:
    ```bash
    python src/main_scraper.py --file meine_epics.txt
    ```

-   **Verarbeitung einer Liste ohne erneutes Scraping (nur Analyse und HTML-Bericht)**:
    ```bash
    python src/main_scraper.py --scraper false
    ```

-   **Verarbeitung eines einzelnen Business Epics**:
    ```bash
    python src/main_scraper.py --issue BEMABU-12345
    ```

-   **Auswertung der verbrauchten Tokens**:
    ```bash
    python src/utils/token_usage_class.py --time week
    ```

## Project Structure

Das Projekt ist wie folgt organisiert, um eine klare Trennung der Verantwortlichkeiten zu gewährleisten:

```
business-epic-analyzer/
├── data/
│   ├── html_reports/     # Generierte HTML-Berichte
│   ├── issue_trees/      # Gespeicherte PNG-Visualisierungen
│   ├── jira_issues/      # Rohe JSON-Daten aus JIRA
│   └── json_summary/     # KI-generierte JSON-Zusammenfassungen
├── logs/
│   └── token_usage.jsonl # Protokoll der LLM-Token-Nutzung
├── prompts/
│   ├── business_value_prompt.yaml
│   ├── html_generator_prompt.yaml
│   └── summary_prompt.yaml
├── src/
│   ├── utils/
│   │   ├── azure_ai_client.py    # Client für Azure AI Services
│   │   ├── config.py             # Zentrale Konfiguration
│   │   ├── epic_html_generator.py# HTML-Berichtsgenerator
│   │   ├── jira_scraper.py       # Selenium-basierter JIRA-Scraper
│   │   ├── json_parser.py        # Parser für LLM JSON-Antworten
│   │   └── prompt_loader.py      # Lädt Prompts aus YAML-Dateien
│   └── main_scraper.py       # Hauptskript zur Orchestrierung
├── templates/
│   └── epic-html_template.html # HTML-Vorlage für Berichte
├── .env                    # Umgebungsvariablen (API-Schlüssel)
└── README.md
```

## Prompt Templates

Die von den LLMs verwendeten Prompts sind zur einfachen Anpassung in externen YAML-Dateien im `prompts/`-Verzeichnis gespeichert. Das Modul `prompt_loader.py` ist dafür verantwortlich, diese Vorlagen zu laden.

-   `business_value_prompt.yaml`: Definiert den System-Prompt für die Extraktion von strukturierten Daten aus dem "Business Value"-Feld in JIRA.
-   `summary_prompt.yaml`: Enthält die Vorlage zur Generierung einer umfassenden JSON-Zusammenfassung des gesamten Vorgangsbaums.
-   `html_generator_prompt.yaml`: Steuert die Umwandlung der JSON-Zusammenfassung in einen formatierten HTML-Bericht.

## Configuration

Die Konfiguration des Tools erfolgt an zwei Stellen:

1.  **`src/utils/config.py`**: Diese Datei enthält zentrale Konfigurationen:
    -   **LLM-Modelle**: Legen Sie fest, welche Modelle für bestimmte Aufgaben verwendet werden sollen (`LLM_MODEL_HTML_GENERATOR`, `LLM_MODEL_BUSINESS_VALUE`, `LLM_MODEL_SUMMARY`).
    -   **Standard-Flags**: Konfigurieren Sie das Standardverhalten, z. B. ob das Scraping standardmäßig aktiviert ist (`DEFAULT_SCRAPE_HTML`).
    -   **Anmeldeinformationen**: Die für den JIRA-Login verwendete E-Mail-Adresse (`JIRA_EMAIL`).

2.  **.env-Datei**: Diese Datei im Stammverzeichnis des Projekts enthält sensible Anmeldeinformationen und Endpunkte für die Azure AI Services. Sie wird von `python-dotenv` geladen und sollte nicht in die Versionskontrolle eingecheckt werden. Siehe Abschnitt *Quick Start* für die erforderlichen Variablen.

## Requirements

### Software
-   Python 3.10+
-   Google Chrome Browser

### Python-Bibliotheken
Die erforderlichen Python-Pakete sind in der Datei `requirements.txt` aufgeführt. Die wichtigsten sind:
-   `selenium`: Zur Steuerung des Webbrowsers für das Scraping.
-   `beautifulsoup4`: Zum Parsen von HTML.
-   `openai`: Offizieller Python-Client für Azure OpenAI.
-   `azure-ai-inference`: Client für Azure AI Foundation Models.
-   `pyyaml`: Zum Laden der Prompt-Vorlagen.
-   `python-dotenv`: Zum Laden von Umgebungsvariablen.
-   `pandas`, `networkx`, `matplotlib`: Zur Datenverarbeitung und Visualisierung.
