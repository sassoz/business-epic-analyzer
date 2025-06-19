"""
Business Impact API Module

This module provides functionality for extracting business value metrics from Jira issue descriptions
using AI-powered analysis. It processes textual descriptions to identify and extract structured
business value data, which helps in prioritizing and evaluating the impact of business requirements.

Key Components:
---------------
1. process_description(): Extracts business value data from a description text
2. transform_json_file(): Processes a JSON file containing Jira issue data

Business Value Structure:
------------------------
The module extracts and structures business value into three main categories:
- Business Impact: Measures direct revenue/cost effects
  - Scale (0-5)
  - Revenue impact
  - Cost savings
  - Risk/loss mitigation
  - Justification

- Strategic Enablement: Measures strategic alignment and benefits
  - Scale (0-5)
  - Risk minimization
  - Strategic enablement details
  - Justification

- Time Criticality: Measures urgency and timing importance
  - Scale (0-5)
  - Time frequency/horizon
  - Justification


Usage Examples:
--------------
1. Process a description directly:
   ```python
   result = process_description(description_text)
   business_value = result["business_value"]
   shortened_description = result["description"]
"""

import json
import os
import re
from utils.azure_ai_client import AzureAIClient
from utils.prompt_loader import load_prompt_template
from dotenv import load_dotenv, find_dotenv
_ = load_dotenv(find_dotenv())


def process_description(description_text, model, token_tracker, azure_client: AzureAIClient):
    """
    Processes a description text, extracts business_value and shortens the description.
    Only returns business_value information when it actually exists in the text -
    does not invent any data.

    Args:
        description_text (str): The description text to process
        api_key (str, optional): Claude API key, if not set via environment variable
        model (str, optional): The AI model to use for processing
        token_tracker (TokenUsage, optional): Instance to track token usage

    Returns:
        dict: Dictionary with shortened_description and business_value (can be empty)
    """

    # Laden Sie die Prompt-Vorlage aus der YAML-Datei
    prompt_template = load_prompt_template("business_impact_prompt.yaml", "user_prompt_template")

    # Füllen Sie die Vorlage mit dem dynamischen Inhalt
    prompt = prompt_template.format(description_text=description_text)
    
    # API-Anfrage senden über den neuen Client
    response_data = azure_client.completion(
        model_name=model,
        user_prompt=prompt,
        max_tokens=6000,
        response_format={"type": "json_object"}
    )
    response_text = response_data["text"]

    # Token-Nutzung loggen, wenn ein Tracker übergeben wurde
    if token_tracker and "usage" in response_data:
        token_tracker.log_usage(
            model=model,
            input_tokens=response_data["usage"]["prompt_tokens"],
            output_tokens=response_data["usage"]["completion_tokens"],
            total_tokens=response_data["usage"]["total_tokens"],
            task_name="business_impact",
        )


    # JSON aus der Antwort extrahieren
    json_match = re.search(r'({[\s\S]*})', response_text)
    if not json_match:
        raise ValueError("Konnte keine gültige JSON-Struktur aus der Claude-Antwort extrahieren.")

    # Entferne eventuell vorhandene Kommentare aus der JSON-Antwort
    json_text = re.sub(r'//.*', '', json_match.group(1))

    try:
        business_value_json = json.loads(json_text)
    except json.JSONDecodeError:
        # Wenn das JSON trotz Bereinigung nicht geparst werden kann,
        # erstelle eine leere Struktur
        business_value_json = {
            "business_value": {
                "business_impact": {
                    "scale": 0,
                    "revenue": "",
                    "cost_saving": "",
                    "risk_loss": "",
                    "justification": ""
                },
                "strategic_enablement": {
                    "scale": 0,
                    "risk_minimization": "",
                    "strat_enablement": "",
                    "justification": ""
                },
                "time_criticality": {
                    "scale": 0,
                    "time": "",
                    "justification": ""
                }
            }
        }

    # Überprüfe, ob tatsächlich business_value-Informationen extrahiert wurden
    has_business_value = False
    bv = business_value_json.get("business_value", {})

    # Prüfe für jeden Abschnitt, ob nicht-leere Werte vorhanden sind
    for section in ["business_impact", "strategic_enablement", "time_criticality"]:
        section_data = bv.get(section, {})
        for key, value in section_data.items():
            if key != "scale" and value:  # Wenn ein nicht-leerer Wert gefunden wurde
                has_business_value = True
                break
            elif key == "scale" and value != 0:  # Wenn eine Skala ungleich 0 gefunden wurde
                has_business_value = True
                break
        if has_business_value:
            break

    # Kürze die description, um den Business Value Teil zu entfernen, aber nur wenn tatsächlich
    # Business Value-Informationen gefunden wurden
    if has_business_value:
        # Suche nach "Business Value / Cost of Delay" Abschnitt
        shortened_description = re.sub(
            r'Business Value / Cost of Delay.*?(?=Rahmenbedingungen|$)',
            '',
            description_text,
            flags=re.DOTALL
        )

        # Entferne doppelte Leerzeilen und bereinige Text
        shortened_description = re.sub(r'\n{3,}', '\n\n', shortened_description.strip())
    else:
        # Wenn kein business_value gefunden wurde, behalte den vollständigen Text bei
        shortened_description = description_text

    return {
        "description": shortened_description,
        "business_value": business_value_json.get("business_value", {}),
    }


def transform_json_file(input_file, api_key=None, output_file=None):
    """
    Transforms a BEMABU JSON file using Claude API, extracts business_value information
    and updates the structure. Only adds business_value information if it's
    actually present in the text.

    Args:
        input_file (str): Path to the input JSON file
        api_key (str, optional): Claude API key, if not set via environment variable
        output_file (str, optional): Name of the output file (Default: input_file_transformed.json)

    Returns:
        str: Path to the transformed output file
    """
    # JSON-Datei einlesen
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Beschreibungstext extrahieren
    description_text = data.get("description", "")
    if not description_text:
        raise ValueError("Keine 'description' im JSON gefunden.")

    # Verarbeite den Beschreibungstext
    processed_data = process_description(description_text, api_key)

    # Aktualisiere die JSON-Daten
    data["description"] = processed_data["description"]

    # Füge business_value nach description ein, aber nur wenn wirklich
    # business_value-Informationen gefunden wurden
    business_value = processed_data["business_value"]

    # Überprüfe, ob der business_value Daten enthält (nicht nur leere Felder)
    has_content = False
    for section in ["business_impact", "strategic_enablement", "time_criticality"]:
        section_data = business_value.get(section, {})
        for key, value in section_data.items():
            if key != "scale" and value:
                has_content = True
                break
            elif key == "scale" and value != 0:
                has_content = True
                break
        if has_content:
            break

    # Aktualisiere die JSON-Daten mit neuen business_value nur wenn Informationen gefunden wurden
    if has_content:
        # Füge business_value nach description ein
        items = list(data.items())
        new_items = []

        for i, (key, value) in enumerate(items):
            new_items.append((key, value))
            if key == "description":
                new_items.append(("business_value", business_value))

        # Erstelle die aktualisierte JSON
        data = dict(new_items)

    # Bestimme Ausgabedateinamen
    if not output_file:
        output_file = input_file

    # Ursprüngliche Datei umbennen
    old_file = os.path.splitext(input_file)[0] + "_old" + os.path.splitext(input_file)[1]
    os.rename(input_file, old_file)

    # Schreibe in Ausgabedatei
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return output_file

# Beispielaufruf
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Transformiert BEMABU JSON-Dateien mit Claude API")
    parser.add_argument("input_file", help="Pfad zur Eingabe-JSON-Datei")
    parser.add_argument("--api_key", help="Claude API-Key (optional, falls nicht über Umgebungsvariable gesetzt)")
    parser.add_argument("--output_file", help="Name der Ausgabedatei (optional)")

    args = parser.parse_args()

    try:
        output_path = transform_json_file(
            args.input_file,
            api_key=args.api_key,
            output_file=args.output_file
        )
        print(f"Transformation erfolgreich. Ausgabe gespeichert unter: {output_path}")
    except Exception as e:
        print(f"Fehler: {str(e)}")
