#!/usr/bin/env python3
"""
Module for integrating with Claude API to generate summaries of Jira issue trees.

This module provides functionality to connect to Anthropic's Claude API and generate
structured summaries of Jira issues in JSON format. It supports customizable prompts
and handles token usage tracking.

The main class, ClaudeAPIClient, handles the API communication, prompt construction,
and response processing, returning structured JSON summaries that can be used for
generating HTML reports.
"""

class ClaudeAPIClient:

    def __init__(self, model: str = "claude-3-7-sonnet-latest", token_tracker=None):

    def generate_summary(self, context, prompt=None, max_tokens=8000):


import os
import json
from anthropic import Anthropic
from litellm import completion
from utils.logger_config import logger

from dotenv import load_dotenv, find_dotenv
_ = load_dotenv(find_dotenv())

class ClaudeAPIClient:
    """
    Client for interacting with Claude API.

    This class handles authentication, communication, and response processing for
    Anthropic's Claude API. It provides methods to generate structured summaries
    from Jira issue data and supports token usage tracking.

    The client uses environment variables for API authentication by default but
    can also accept explicit API keys.
    """

    def __init__(self, model: str = "claude-3-7-sonnet-latest", token_tracker=None):
        """
        Initializes the Claude API client with specified parameters.

        Args:
            model (str): The Claude model to use for generation. Default is "claude-3-7-sonnet-latest".
            token_tracker: Optional token usage tracker that logs token consumption.
                          Should implement a log_usage method.

        Raises:
            ValueError: If no API key is available through environment variables
                       or direct parameters.
        """
        self.api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("API key required via constructor or ANTHROPIC_API_KEY environment variable")
        self.client = Anthropic(api_key=self.api_key)
        self.model =  model
        self.token_tracker = token_tracker

    def generate_summary(self, context, prompt=None, max_tokens=8000):
        """
        Generates a structured JSON summary of Jira issues using Claude API.

        This method takes the context data from Jira issues and generates a
        comprehensive summary in JSON format. It supports custom prompts
        or uses a detailed default prompt designed for Jira issue analysis.

        Args:
            context (str): The JSON context data containing Jira issues to summarize.
            prompt (str, optional): Custom prompt for the API. If None, uses a
                                   default prompt tailored for Jira issue analysis.
            max_tokens (int): Maximum tokens for the response. Default is 8000.

        Returns:
            str: The generated JSON summary containing structured information about
                business goals, features, acceptance criteria, and timelines.

        Raises:
            Exception: On API communication errors or issues with JSON processing.
        """
        if not prompt:
            prompt = f"""
                Sie sind ein Product Owner in einem Telekommunikationsunternehmen und arbeiten mit einem IT-Team.
                Ihre Aufgabe ist es, eine detaillierte Zusammenfassung der Geschäftsanforderungen zu erstellen, die in einem Business Epic und den zugehörigen Issues für Ihr IT-Team beschrieben sind. Folgen Sie diesen Schritten:
                1. Sichten Sie sorgfältig den unten angehängten JSON-Context der das Business Epic sowie die angehängten Portfolio Epics, Epics und anderen Jira-Issues umfasst

                2. Erstellen Sie eine umfassende Zusammenfassung der im Business Epic und den zugehörigen Issues beschriebenen Geschäftsanforderungen. Ihre Zusammenfassung sollte:
                   a. Gesamtziel des Business Epics und Liste der Einzelziele => nutze für das Gesamtziel insbesondere die {{description}} und {{title}} des Business Epics; nutze für die Einzelziele insbesondere die {{description}} und {{title}} aller über {{realized_by}} verbundenen Jira-Issues
                   b. Geschäftlicher Nutzen ("Business Value") => nutze dafür die {{business_value}} Inhalte des Business Epics
                   c. Liste der Schlüsselfunktionen oder angeforderte Funktionalitäten und erläutern => nutze dafür insbesondere die {{description}}, {{title}} und {{key}} aller Jira-Issues, die als {{realized_by}} mit dem Business Epic verbunden sind
                   d. Liste mit den Akzeptanzkriterie => nutze dafür ausschließlich die {{acceptance_criteria}} Inhalte aller Jira-Issues
                   => Falls die angehängten Jira Issues zu den Punkten 3.a - 3.d keine Informationen beinhalten, schreibe 'Keine Informationen verfügbar'

                3. Alle erwähnten spezifischen technischen Anforderungen hervorheben
                   a. Liste mit den beteiligten IT Applications und domains; nutze dafür insbesondere {{components}}; prüfe, ob in den {{acceptance_criteria}} ggf auch IT Applications enthalten sind; versuche NIEMALS die IT Applications auszuschreiben oder die Bedeutung der Abkürzungen zu erraten!
                   b. Abhängigkeiten & Risiken => prüfe {{description}}, {{acceptance_criteria}}, {{status}} und {{target_end}} aller Jira issues; sind große, fachliche Abhängigkeiten zwischen den Abliefergegenständen erkennbar? Gibt es externe Abhängigkeiten, die durch die Teams nicht direkt beeinflusst werden können? Gibt es Risiken für die vollständige, termingerechte Ablieferung aller JIRA Issues? Passen die {{target_end}} Daten des Business Epics zu denen der über {{realized_by}} verbundenen Jira Issue?
                   => Falls die angehängten Jira Issues zu den Punkten 4.a - 4.b keine Informationen beinhalten, schreibe 'Keine Informationen verfügbar'

                4. Alle relevanten Zeitpläne, geplanter oder tatsächlicher Umsetzungsstart, Geplantes oder tatsächliches Umsetzungsende
                    => nutze dafür ausschließlich die {{target_start}}, {{target_end}} und {{fix_versions}} Inhalte aller Jira-Issues
                    => Falls die angehängten Jira Issues zu den Punkten keine Informationen beinhalten, schreibe 'Keine Informationen verfügbar'

                5. Formatieren Sie Ihre Zusammenfassung wie folgt:
                   - Verwenden Sie klare, präzise Sprache, die für ein IT-Team geeignet ist
                   - Organisieren Sie Informationen in einer logischen Struktur (z.B. Aufzählungspunkte, nummerierte Listen)
                   - Fügen Sie Abschnittsüberschriften für eine einfache Navigation ein
                   - Stellen Sie sicher, dass alle wichtigen Punkte aus dem Business Epic und den zugehörigen Issues abgedeckt sind
                   - Falls die angehängten Jira Issues keine Informationen beinhalten, schreibe 'Keine Informationen verfügbar'

                Überprüfen Sie nach der Erstellung Ihrer Zusammenfassung, ob diese den gesamten Umfang des Business Epics und der zugehörigen Issues genau wiedergibt, ohne wesentliche Details auszulassen.
                DON'T MAKE UP FACTS!!!
                !!! Antworten Sie immer auf Deutsch!!!

                Antworte ausschließlich mit einem gültigen JSON-Objekt und ohne erklärenden Text.
                {{
                  "epicId": "EPIC-ID",
                  "title": "Epic-Titel",
                  "ziele": {{
                    "gesamtziel": "Zusammenfassung des übergreifendes Ziels des Business Epics, wie dieses erreicht wird und zu welchem geplanten Zeitpunkt dieses Ziel erreicht wird",
                    "einzelziele": [
                      "Einzelziel 1",
                      "Einzelziel 2",
                      "Einzelziel 3"
                    ]
                  }},
                  "businessValue": {{
                    "businessImpact": {{
                      "skala": 0,
                      "beschreibung": "Beschreibung des Nutzens aus Umsatzsteigerung und/oder Kosteneinsparung"
                    }},
                    "strategicEnablement": {{
                      "skala": 0,
                      "beschreibung": "Beschreibung des strategischen Nutzens"
                    }},
                    "timeCriticality": {{
                      "skala": 0,
                      "beschreibung": "Beschreibung der zeitlichen Kritikalität"
                    }}
                  }},
                  "funktionen": [
                    {{
                      "id": "TICKET-ID-1",
                      "titel": "Funktionstitel 1",
                      "funktionalitäten": [
                        "Funktionalität 1.1",
                        "Funktionalität 1.2",
                        "Funktionalität 1.3"
                      ]
                    }},
                    {{
                      "id": "TICKET-ID-2",
                      "titel": "Funktionstitel 2",
                      "funktionalitäten": [
                        "Funktionalität 2.1",
                        "Funktionalität 2.2",
                        "Funktionalität 2.3"
                      ]
                    }}
                  ],
                  "acceptance_criteria": [
                      "Acceptance Criteria 1",
                      "Acceptance Criteria 2",
                      "Acceptance Criteria 3"
                  ],
                  "domainsAndITApplications": [
                      "Domain/IT Application 1",
                      "Domain/IT Application 2",
                      "Domain/IT Application 3"
                  ],
                  "abhängigkeitenUndRisiken": [
                      "Abhängigkeit/Risiko 1",
                      "Abhängigkeit/Risiko 2",
                      "Abhängigkeit/Risiko 3"
                  ],
                  "zeitplan": {{
                    "umsetzungsstart": "Startdatum",
                    "umsetzungsende": "Enddatum",
                    "fixVersions": ["Version 1", "Version 2"],
                    "meilensteine": [
                      {{
                        "id": "MILESTONE-ID-1",
                        "beschreibung": "Meilensteinbeschreibung 1",
                        "zeitraum": "Zeitraum des Meilensteins 1"
                      }},
                      {{
                        "id": "MILESTONE-ID-2",
                        "beschreibung": "Meilensteinbeschreibung 2",
                        "zeitraum": "Zeitraum des Meilensteins 2"
                      }}
                    ]
                  }}
                }}

                ### JIRA-ISSUES ###
                {context}
                """

        try:
            # litellm aufrufen
            response = completion(
                model=self.model,
                messages=[
                    {"role": "system", "content": "Du bist ein hilfreicher Assistent, der Informationen aus Texten extrahiert und in strukturiertes JSON-Formate umwandelt."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0,
                max_tokens=8000,
                num_retries=3
                )

            result = response['choices'][0]['message']['content']

            # Token-Nutzung loggen, wenn ein Tracker übergeben wurde
            if self.token_tracker:
                self.token_tracker.log_usage(
                    model=self.model,
                    input_tokens=response.usage.prompt_tokens,
                    output_tokens=response.usage.completion_tokens,
                    total_tokens=response.usage.total_tokens,
                    task_name="summary_generation",
                )

            return result

        except Exception as e:
            logger.error(f"got exception in 'generate_summary': {e}")
            raise
