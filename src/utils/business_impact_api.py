import json
import os
import anthropic
import re
from dotenv import load_dotenv, find_dotenv
_ = load_dotenv(find_dotenv())


def process_description(description_text, api_key=None, model="claude-3-7-sonnet-latest", token_tracker=None):
    """
    Verarbeitet einen Beschreibungstext, extrahiert business_value und kürzt die Beschreibung.

    Gibt nur dann business_value Informationen zurück, wenn diese tatsächlich
    im Text vorhanden sind - erfindet keine Daten.

    Args:
        description_text (str): Der zu verarbeitende Beschreibungstext
        api_key (str, optional): Claude API-Key, falls nicht über Umgebungsvariable gesetzt

    Returns:
        dict: Dictionary mit shortened_description und business_value (kann leer sein)
    """
    # Prüfe, ob API-Key vorhanden
    if not api_key:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("Kein API-Key gefunden. Bitte als Parameter übergeben oder ANTHROPIC_API_KEY Umgebungsvariable setzen.")

    # Claude-Client initialisieren
    client = anthropic.Anthropic(api_key=api_key)

    # Verbessertes Prompt für verlässlichere Ausgaben
    prompt = f"""
    Analysiere folgenden Beschreibungstext auf konkrete, explizite Informationen zum Geschäftswert (Business Value):

    ```
    {description_text}
    ```

    Fülle die folgende JSON-Struktur NUR mit Informationen, die EXPLIZIT im Text genannt werden.
    Falls zu einem Feld keine eindeutigen Angaben im Text vorhanden sind, LASSE das Feld leer ("") oder setze den Wert auf 0.

    Wichtig:
    - Fülle nur Werte aus, die explizit im Text erwähnt sind
    - Erfinde KEINE Daten oder Werte
    - Falls der Text keinen "Business Value" oder "Geschäftswert" Abschnitt enthält, gib eine leere Struktur zurück
    - Wenn keine Zahlenwerte/Skalen vorhanden sind, setze diese auf 0
    - Bei jedem Feld, das du füllst, notiere in einem Kommentar die exakte Textstelle, die du als Quelle verwendest

    Beispiel für einen strukturierten Business Value:
    ```json
    {{
      "business_value": {{
        "business_impact": {{
          "scale": 3, // Explizit im Text: "Business Impact (Scale: 3)"
          "revenue": "", // Keine explizite Angabe im Text
          "cost_saving": "Aufwandsreduzierung durch optimierte Arbeit mit EOS", // Explizit im Text: "Cost Saving: Aufwandsreduzierung durch optimierte Arbeit mit EOS"
          "risk_loss": "", // Keine explizite Angabe im Text
          "justification": "Das Vorhaben schafft durch die optimierte Arbeit mit EOS einen schnelleren und auch besseren Serviceprozess, welcher in Aufwandsreduzierung resultiert." // Explizit im Text als Justification unter Business Impact
        }},
        "strategic_enablement": {{
          "scale": 2, // Explizit im Text: "Strategic Enablement (Scale: 2)"
          "risk_minimization": "", // Keine explizite Angabe im Text
          "strat_enablement": "Optimierung des Serviceprozesses durch direkte Bearbeitung in EOS statt manuell in verschiedenen Produktionsstraßen", // Explizit im Text unter Strategic Enablement
          "justification": "Die Nutzer arbeiten schneller und effizienter im System, können dadurch mehr Zeit für die Beratung der Kunden aufwänden." // Explizit im Text als Justification unter Strategic Enablement
        }},
        "time_criticality": {{
          "scale": 2, // Explizit im Text: "Time Criticality (Scale: 2)"
          "time": "Täglich", // Explizit im Text: "Time: Täglich"
          "justification": "Für die MitarbeiterInnen aus SGrK, die täglich mit EOS arbeiten, ist es notwendig, dass diese AGB-Kette mit Features erweitert wird." // Explizit im Text als Justification unter Time Criticality
        }}
      }}
    }}
    ```

    Ausgabeformat:
    1. Wenn der Text KEINE business_value Informationen enthält, gib die leere Struktur zurück:
    ```json
    {{
      "business_value": {{
        "business_impact": {{
          "scale": 0,
          "revenue": "",
          "cost_saving": "",
          "risk_loss": "",
          "justification": ""
        }},
        "strategic_enablement": {{
          "scale": 0,
          "risk_minimization": "",
          "strat_enablement": "",
          "justification": ""
        }},
        "time_criticality": {{
          "scale": 0,
          "time": "",
          "justification": ""
        }}
      }}
    }}
    ```

    2. Wenn der Text business_value Informationen enthält, fülle nur die entsprechenden Felder:
    Gib NUR die befüllte JSON-Struktur zurück ohne zusätzlichen Text, beginnend mit {{.
    """

    # API-Anfrage senden
    response = client.messages.create(
        model = model,
        max_tokens = 4000,
        temperature = 0,
        system="""Du bist ein präziser Datenextraktions-Assistent, der Texte analysiert und nur explizit genannte Informationen extrahiert.
        1. Extrahiere nur Informationen, die EXPLIZIT im Text genannt werden
        2. Erfinde NIEMALS Daten oder fülle Felder mit Annahmen
        3. Wenn zu einem Feld keine Information vorhanden ist, lasse es leer ("") oder setze nummerische Werte auf 0
        4. Gib nur die angeforderte JSON-Struktur zurück, ohne zusätzliche Erklärungen""",
        messages=[
            {"role": "user", "content": prompt}
        ]
    )

    # Extrahiere die JSON-Antwort
    response_text = response.content[0].text
    print(f"Token Tracker = {token_tracker}, Model = {model}\nUsage = {response.usage}")
    # Token-Nutzung loggen, wenn ein Tracker übergeben wurde
    if token_tracker:
        token_tracker.log_usage(
            model=model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            total_tokens=response.usage.input_tokens+response.usage.output_tokens,
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
    Transformiert eine BEMABU JSON-Datei mit Claude API, extrahiert business_value Informationen
    und aktualisiert die Struktur. Fügt nur dann business_value-Informationen hinzu, wenn diese
    tatsächlich im Text vorhanden sind.

    Args:
        input_file (str): Pfad zur Eingabe-JSON-Datei
        api_key (str, optional): Claude API-Key, falls nicht über Umgebungsvariable gesetzt
        output_file (str, optional): Name der Ausgabedatei (Default: input_file_transformed.json)

    Returns:
        str: Pfad zur transformierten Ausgabedatei
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
