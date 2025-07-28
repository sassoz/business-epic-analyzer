# **JIRA Business Epic Analyzer & Reporter**

Ein umfassendes Tool, das die Extraktion, Analyse, Visualisierung und Berichterstattung von JIRA Business Epics automatisiert. Dieses Projekt extrahiert JIRA-Vorgänge, führt eine tiefgehende, mehrstufige Analyse durch und generiert detaillierte HTML-Berichte, die sowohl quantitative Metriken als auch KI-gestützte qualitative Zusammenfassungen enthalten.

## **Features**

* **Automatisierte JIRA-Extraktion**: Meldet sich bei JIRA an und extrahiert rekursiv Rohdaten von Business Epics und allen verknüpften Vorgängen.  
* **Modulare Metrik-Analyse**: Führt spezialisierte Analysen in verschiedenen Bereichen durch:  
  * **Scope-Analyse**: Bewertet Umfang, Komplexität und die Verteilung der Arbeit auf verschiedene Teams/Jira-Projekte.  
  * **Status-Analyse**: Berechnet die Verweildauer in einzelnen Status sowie die gesamte Durchlaufzeit ("Coding Time").  
  * **Time-Creep-Analyse**: Erkennt und bewertet Terminverschiebungen bei Zielterminen und Fix-Versionen mithilfe eines LLMs.  
  * **Backlog-Analyse**: Visualisiert die Entwicklung des aktiven Story-Backlogs über die Zeit (hinzugefügt vs. abgeschlossen).  
* **KI-gestützte Inhalts-Zusammenfassung**: Nutzt ein LLM, um aus den Rohdaten eine verständliche, geschäftsorientierte Zusammenfassung des Epics zu generieren.  
* **Hierarchie- & Daten-Visualisierung**:  
  * Erstellt mit GraphViz automatisch Baumdiagramme der Vorgangshierarchie.  
  * Generiert Plots zur Entwicklung des Backlogs.  
* **Intelligente HTML-Berichterstellung**: Fusioniert alle Analyse-Metriken und qualitativen Zusammenfassungen in einem einzigen Datenobjekt und generiert daraus mithilfe eines LLMs einen formatierten, leicht lesbaren HTML-Bericht.  
* **Flexible Konfiguration & Steuerung**: Ermöglicht die einfache Konfiguration von JIRA-Zugängen, LLM-Modellen und Skriptverhalten über eine Konfigurationsdatei, Umgebungsvariablen und Kommandozeilen-Argumente.

## **Analyse-Workflow**

Der Prozess ist in mehrere logische Schritte unterteilt, um eine hohe Datenqualität und nachvollziehbare Ergebnisse zu gewährleisten:

1. **Datenerfassung (jira\_scraper.py)**: Extrahiert die Rohdaten der angegebenen JIRA-Epics und aller verknüpften Vorgänge und speichert sie als einzelne JSON-Dateien.  
2. **Datenaufbereitung (project\_data\_provider.py)**: Lädt die Rohdaten für ein Epic, baut einen Abhängigkeitsbaum auf und stellt alle relevanten Informationen (Details, Aktivitäten) zentral für die Analyse-Module bereit.  
3. **Metrische Analyse (features/\*\_analyzer.py)**: Der AnalysisRunner führt die einzelnen, spezialisierten Analyzer aus. Jeder Analyzer verarbeitet die Daten aus dem ProjectDataProvider und gibt ein strukturiertes Ergebnis mit seinen spezifischen Metriken zurück.  
4. **Inhaltliche Analyse (main\_scraper.py)**: Ein LLM wird verwendet, um aus dem reinen Inhalt der JIRA-Tickets eine qualitative Zusammenfassung zu erstellen.  
5. **Visualisierung (jira\_tree\_classes.py, console\_reporter.py)**: Parallel zur Analyse werden die Hierarchie-Graphen und Backlog-Diagramme als Bilddateien generiert.  
6. **Synthese (json\_summary\_generator.py)**: Die Ergebnisse aus **allen** metrischen Analysen (Schritt 3\) und der inhaltlichen Analyse (Schritt 4\) werden zu einer einzigen, umfassenden JSON-Datei (\*\_complete\_summary.json) zusammengeführt.  
7. **Berichterstellung (epic\_html\_generator.py)**: Diese finale JSON-Datei dient als Kontext für ein weiteres LLM, das mithilfe einer HTML-Vorlage den finalen, formatierten Bericht generiert und die zuvor erstellten Visualisierungen einbettet.

## **Quick Start**

1. **Repository klonen und installieren**:  
   git clone \<repository\_url\>  
   cd jira-business-epic-analyzer  
   pip install \-r requirements.txt

2. Umgebungsvariablen einrichten:  
   Erstellen Sie eine .env-Datei im Stammverzeichnis und fügen Sie Ihre Azure AI-Anmeldeinformationen hinzu:  
   AZURE\_OPENAI\_API\_KEY="IHR\_OPENAI\_API\_SCHLUESSEL"  
   AZURE\_OPENAI\_API\_VERSION="IHRE\_API\_VERSION"  
   AZURE\_OPENAI\_ENDPOINT="IHR\_OPENAI\_ENDPOINT"

   AZURE\_AIFOUNDRY\_API\_KEY="IHR\_AIFOUNDRY\_API\_SCHLUESSEL"  
   AZURE\_AIFOUNDRY\_ENDPOINT="IHR\_AIFOUNDRY\_ENDPOINT"

3. JIRA-Vorgänge definieren:  
   Erstellen Sie eine Textdatei (z. B. BE\_Liste.txt) und fügen Sie die JIRA Business Epic-Keys hinzu (einer pro Zeile).  
4. **Skript ausführen**:  
   python src/main\_scraper.py \--file BE\_Liste.txt \--scraper check \--html\_summary true

5. Ergebnisse prüfen:  
   Die generierten Artefakte finden Sie im data-Verzeichnis:  
   * data/html\_reports/: Fertige HTML-Berichte.  
   * data/issue\_trees/: PNG-Visualisierungen der Hierarchien.  
   * data/json\_summary/: Finale, zusammengeführte JSON-Berichte.  
   * data/jira\_issues/: Rohe JSON-Daten aus JIRA.  
   * data/plots/: Generierte Diagramme (z.B. Backlog-Entwicklung).

## **CLI-Referenz**

Das Skript wird über src/main\_scraper.py gesteuert:

| Argument | Typ | Standard | Beschreibung |
| :---- | :---- | :---- | :---- |
| \--scraper | true/false/check | check | **true**: Erzwingt das erneute Scrapen aller Daten. \<br\> **false**: Überspringt das Scraping komplett. \<br\> **check**: Scrapt nur Issues, deren lokale Dateien veraltet sind. |
| \--html\_summary | true/false/check | false | **true**: Erzwingt die komplette Neu-Analyse und HTML-Erstellung. \<br\> **false**: Überspringt Analyse & Reporting. \<br\> **check**: Nutzt eine gecachte Analyse-Datei (\*\_complete\_summary.json), falls vorhanden, sonst wird neu analysiert. |
| \--issue | string | None | Verarbeitet eine einzelne, spezifische JIRA-Issue-ID anstelle einer Datei. |
| \--file | string | None | Pfad zur .txt-Datei mit den Business Epic-Keys. Wenn nicht angegeben, wird interaktiv danach gefragt. |

### **Beispiele**

* **Standard-Durchlauf (empfohlen)**: Veraltete Daten neu scrapen, Analyse aus Cache laden (falls vorhanden), HTML-Bericht neu erstellen.  
  python src/main\_scraper.py \--file BE\_Liste.txt \--scraper check \--html\_summary check

* **Nur Analyse und Reporting (ohne Scraping)**:  
  python src/main\_scraper.py \--file BE\_Liste.txt \--scraper false \--html\_summary true

* **Komplett-Erneuerung aller Daten und Berichte**:  
  python src/main\_scraper.py \--file BE\_Liste.txt \--scraper true \--html\_summary true

* **Verarbeitung eines einzelnen Business Epics**:  
  python src/main\_scraper.py \--issue BEMABU-12345 \--scraper check \--html\_summary true

* **Auswertung der verbrauchten Tokens**:  
  python src/utils/token\_usage\_class.py \--time week

## **Projektstruktur**

Das Projekt ist modular aufgebaut, um eine klare Trennung der Verantwortlichkeiten zu gewährleisten.

jira-business-epic-analyzer/  
├── data/  
│   ├── html\_reports/     \# Finale HTML-Berichte  
│   ├── issue\_trees/      \# Gespeicherte PNG-Hierarchien  
│   ├── jira\_issues/      \# Rohe JSON-Daten aus JIRA  
│   ├── json\_summary/     \# Zusammengeführte JSON-Berichte  
│   └── plots/            \# Generierte Diagramme  
├── logs/  
│   └── token\_usage.jsonl \# Protokoll der LLM-Token-Nutzung  
├── prompts/              \# YAML-Dateien mit den LLM-Prompts  
│   ├── business\_value\_prompt.yaml  
│   ├── html\_generator\_prompt.yaml  
│   ├── summary\_prompt.yaml  
│   └── time\_creep\_summary.yaml  
├── src/  
│   ├── features/         \# Module für die metrische Analyse  
│   │   ├── ...  
│   ├── utils/            \# Hilfsmodule und Clients  
│   │   ├── azure\_ai\_client.py  
│   │   ├── config.py  
│   │   ├── jira\_scraper.py  
│   │   └── ...  
│   └── main\_scraper.py   \# Hauptskript zur Orchestrierung  
├── templates/  
│   └── epic-html\_template.html \# HTML-Vorlage für Berichte  
├── .env                    \# Umgebungsvariablen (API-Schlüssel etc.)  
└── README.md

## **Prompt Templates**

Die von den LLMs verwendeten Anweisungen (Prompts) sind zur einfachen Anpassung in externen YAML-Dateien im prompts/-Verzeichnis gespeichert. Das Modul prompt\_loader.py ist dafür verantwortlich, diese Vorlagen zu laden.

* business\_value\_prompt.yaml: Definiert den System-Prompt für die Extraktion von strukturierten Daten aus dem "Business Value"-Feld in JIRA während des Scraping-Prozesses.  
* summary\_prompt.yaml: Enthält die Vorlage zur Generierung einer umfassenden, qualitativen JSON-Zusammenfassung des gesamten Vorgangsbaums (Ziele, Funktionen etc.).  
* time\_creep\_summary.yaml: Steuert die LLM-Analyse der erfassten Terminverschiebungen und erstellt eine textliche Bewertung der Projektdynamik.  
* html\_generator\_prompt.yaml: Definiert die Anweisungen für das LLM, um aus dem finalen, zusammengeführten JSON-Datenobjekt den vollständigen HTML-Bericht zu erstellen.

## **KI-Integration & LLM-Nutzung**

Die gesamte Interaktion mit Sprachmodellen wird durch das Modul src/utils/azure\_ai\_client.py gekapselt.

### **Zentraler AzureAIClient**

Die Klasse AzureAIClient dient als vereinheitlichte Schnittstelle (Wrapper) für verschiedene KI-Dienste von Azure. Dies hat den Vorteil, dass der restliche Programmcode nicht wissen muss, welches spezifische Backend für eine Anfrage verwendet wird. Der Client leitet Anfragen automatisch an den richtigen Dienst weiter, basierend auf dem im Aufruf angegebenen Modellnamen.

### **Unterstützte Modellfamilien**

Der Client ist für die Arbeit mit zwei Hauptkategorien von Azure-Diensten ausgelegt:

1. **Azure OpenAI Service**: Wird für leistungsstarke, multimodale Modelle wie gpt-4o oder gpt-4.1-mini verwendet. Diese Modelle können sowohl Text als auch Bilder verarbeiten.  
2. **Azure AI Foundation Models**: Dient als Endpunkt für eine Vielzahl von Open-Source-Modellen wie Llama oder Mistral, die primär für Text-zu-Text-Aufgaben optimiert sind.

Die Zuordnung, welches Modell für welche Aufgabe (z.B. HTML-Generierung, inhaltliche Zusammenfassung) verwendet wird, ist zentral in der src/utils/config.py-Datei festgelegt und kann dort einfach geändert werden, um verschiedene Modelle zu testen.

## **Logging**

Das Programm verfügt über ein robustes Logging-System, das in src/utils/logger\_config.py konfiguriert wird, um den Ablauf nachvollziehbar zu machen und die Fehlersuche zu erleichtern.

Es werden zwei Arten von Logs parallel geschrieben:

1. **Datei-Log (logs/jira\_scraper.log)**: Hier werden alle Ereignisse ab dem Loglevel INFO detailliert protokolliert. Diese Datei enthält eine vollständige Aufzeichnung aller durchgeführten Schritte, einschließlich erfolgreicher Operationen, und dient zur nachträglichen Analyse und zum Debugging.  
2. **Konsolen-Log**: Im Terminal werden standardmäßig nur Meldungen ab dem Loglevel WARNING ausgegeben. Dadurch bleibt die Bildschirmausgabe übersichtlich und lenkt den Fokus auf wichtige Warnungen oder kritische Fehler, die ein Eingreifen erfordern könnten.

Zusätzlich wird eine separate Log-Datei für die **Token-Nutzung** (logs/token\_usage.jsonl) geführt, um die Kosten der LLM-Aufrufe transparent zu verfolgen.

## **Konfiguration**

Die Konfiguration des Tools erfolgt an zwei zentralen Stellen:

1. **src/utils/config.py**: Enthält globale Konfigurationen wie Pfade, Standard-Flags und LLM-Modellnamen für spezifische Aufgaben (LLM\_MODEL\_SUMMARY, LLM\_MODEL\_TIME\_CREEP etc.).  
2. **.env-Datei**: Enthält sensible Anmeldeinformationen (API-Keys, Endpunkte) und wird von der Anwendung automatisch geladen. Diese Datei sollte nicht in die Versionskontrolle eingecheckt werden.

## **Requirements**

### **Software**

* Python 3.10+  
* Google Chrome Browser

### **Python-Bibliotheken**

Die erforderlichen Pakete sind in requirements.txt aufgeführt. Die wichtigsten sind:

* selenium & beautifulsoup4: Für das Web-Scraping.  
* openai: Offizieller Client für Azure OpenAI.  
* pyyaml: Zum Laden der Prompt-Vorlagen.  
* python-dotenv: Zum Laden von Umgebungsvariablen.  
* pandas: Für Datenaggregation (insb. Backlog-Analyse).  
* networkx & matplotlib: Zur Erstellung und Visualisierung der Graphen.