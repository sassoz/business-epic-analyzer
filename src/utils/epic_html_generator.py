"""
Module for generating HTML summary reports from JIRA Business Epic data.

This module provides functionality to create rich HTML reports for Business Epics
using templated generation augmented by Large Language Models. It transforms structured
JSON summaries into comprehensive HTML reports with embedded visualizations.

The main class, EpicHtmlGenerator, handles template loading, LLM-based content
generation, image embedding, and HTML file output. It supports customization of
templates, output locations, and model selection for generation.

Key features:
- Template-based HTML generation for Business Epics
- LLM integration for intelligent content transformation and formatting
- Automatic embedding of visualization images into HTML via Base64 encoding
- JIRA issue link formatting and hyperlinking
- Token usage tracking for LLM API calls
- Batch processing of multiple Business Epics
"""

import os
import base64
import re
import mimetypes
from pathlib import Path
import json
from utils.logger_config import logger
from typing import Dict, Tuple, Optional
from openai import OpenAI
from dotenv import load_dotenv
from utils.prompt_loader import load_prompt_template
from utils.config import EPIC_HTML_TEMPLATE, HTML_REPORTS_DIR, ISSUE_TREES_DIR

class EpicHtmlGenerator:
    """
    Klasse zur Generierung von HTML-Dateien für Business Epics mit Unterstützung
    für Template-basierte Generierung, LLM-Integration und Bild-Einbettung.
    """

    def __init__(self,
                 template_path: str = EPIC_HTML_TEMPLATE,
                 model: str = "gpt-4.1-mini",
                 output_dir: Optional[str] = HTML_REPORTS_DIR,
                 token_tracker=None):
        """
        Initialisiert den HTML-Generator mit dem angegebenen Template und LLM-Modell.

        Args:
            template_path: Pfad zur HTML-Vorlagendatei
            model: Name des zu verwendenden LLM-Modells
            output_dir: Optionales Ausgabeverzeichnis für HTML-Dateien
        """
        # Umgebungsvariablen aus .env-Datei laden
        load_dotenv()

        self.template_path = template_path
        self.client = OpenAI()
        self.model = model
        self.output_dir = output_dir
        self.template_html = self._load_template()
        self.token_tracker = token_tracker
        self.prompt_template = load_prompt_template("html_generator_prompt.yaml", "user_prompt_template")

        # Mimetypes initialisieren
        if not mimetypes.inited:
            mimetypes.init()

    def _load_template(self) -> str:
        """
        Lädt die HTML-Vorlage aus der angegebenen Datei.

        Returns:
            Inhalt der HTML-Vorlage als String

        Raises:
            Exception: Wenn die Template-Datei nicht gelesen werden kann
        """
        try:
            with open(self.template_path, 'r', encoding='utf-8') as file:
                return file.read()
        except Exception as e:
            raise Exception(f"Fehler beim Lesen der Template-Datei {self.template_path}: {e}")

    def _extract_html(self, response: str) -> str:
        """
        Extrahiert HTML-Inhalt aus der LLM-Antwort.

        Args:
            response: Antwort des LLM-Models

        Returns:
            Extrahierter HTML-Inhalt
        """
        # Nach HTML-Inhalt zwischen <!DOCTYPE html> und </html> suchen
        start_index = response.find('<!DOCTYPE html>')
        end_index = response.find('</html>')

        if start_index != -1 and end_index != -1:
            return response[start_index:end_index + 7]  # +7 für '</html>'

        # Wenn nicht gefunden, nach Inhalt zwischen <html> und </html> suchen
        start_index = response.find('<html')
        end_index = response.find('</html>')

        if start_index != -1 and end_index != -1:
            return response[start_index:end_index + 7]

        # Wenn nichts gefunden wurde, vollständige Antwort zurückgeben
        return response

    def _embed_images_in_html(self, html_content: str, output_dir: str, BE_key: str) -> str:
        """Embeds images directly in HTML content using Base64 encoding."""
        # Find all image tags in HTML
        img_pattern = re.compile(r'<img\s+[^>]*src=["\']([^"\']+)["\'][^>]*>')
        img_matches = img_pattern.finditer(html_content)

        for match in img_matches:
            img_tag = match.group(0)
            img_src = match.group(1)

            # Skip already embedded or remote images
            if img_src.startswith('data:') or img_src.startswith('http'):
                continue

            # Check if image matches the BE_key pattern
            if f"{BE_key}_issue_tree.png" in img_src:
                # Use direct path to issue tree in ISSUE_TREES_DIR
                img_path = os.path.join(ISSUE_TREES_DIR, f"{BE_key}_issue_tree.png")

                if not os.path.exists(img_path):
                    logger.error(f"Warning: Image file not found at {img_path}")
                    continue

                try:
                    # Get image MIME type
                    mime_type, _ = mimetypes.guess_type(img_path)
                    if not mime_type:
                        mime_type = 'image/png'

                    # Read and encode image as Base64
                    with open(img_path, 'rb') as img_file:
                        img_data = img_file.read()
                        img_base64 = base64.b64encode(img_data).decode('utf-8')

                    # Create data URI
                    data_uri = f'data:{mime_type};base64,{img_base64}'

                    # Replace src attribute in img tag
                    new_img_tag = img_tag.replace(img_src, data_uri)
                    html_content = html_content.replace(img_tag, new_img_tag)

                    logger.info(f"Image embedded: {img_src}")
                except Exception as e:
                    logger.error(f"Error processing image {img_src}: {str(e)}")

        return html_content


    def generate_epic_html(self, issue_content: str, BE_key: str, output_file: Optional[str] = None) -> Tuple[str, Dict[str, int]]:
        """
        Generiert eine HTML-Datei mit eingebetteten Bildern aus dem übergebenen Inhalt.

        Args:
            issue_content: Inhalt des Issues als String (JSON-Format)
            BE_key: Business Epic Key (z.B. "BEMABU-1825")
            output_file: Optionaler Dateipfad für die Ausgabe-HTML-Datei

        Returns:
            Tuple aus generiertem HTML-Inhalt und Token-Nutzung (dict mit input_tokens, output_tokens, total_tokens)

        Raises:
            Exception: Bei Fehlern in der API-Kommunikation oder HTML-Verarbeitung
        """
        # Wenn kein output_file-Parameter angegeben wurde, einen aus BE_key und output_dir erstellen
        if output_file is None:
            if self.output_dir is None:
                raise ValueError("Entweder output_file oder output_dir muss angegeben werden")
            output_file = os.path.join(self.output_dir, f"{BE_key}_summary.html")

        # Ausgabeverzeichnis sicherstellen
        output_dir = os.path.dirname(output_file)
        os.makedirs(output_dir, exist_ok=True)
        
        # Prompt für LLM erstellen, indem die geladene Vorlage formatiert wird
        prompt = self.prompt_template.format(
            template_html=self.template_html,
            issue_content=issue_content
        )

        logger.info(f"Starte HTML-Generierung mit Model ''{self.model}'")

        try:
            # OpenAI API aufrufen
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{
                    "role": "user",
                    "content": prompt}],
                temperature=0,
                max_tokens=6000
                )
            response_content = response.choices[0].message.content

            # Token-Nutzung loggen, wenn ein Tracker übergeben wurde
            if self.token_tracker:
                self.token_tracker.log_usage(
                    model=self.model,
                    input_tokens=response.usage.prompt_tokens,
                    output_tokens=response.usage.completion_tokens,
                    total_tokens=response.usage.total_tokens,
                    task_name="html_generation",
                )

            # HTML aus Antwort extrahieren
            html_content = self._extract_html(response_content)

            # Bilder in HTML-Inhalt einbetten
            html_content = self._embed_images_in_html(html_content, output_dir, BE_key)

            # HTML in Ausgabedatei speichern
            with open(output_file, 'w', encoding='utf-8') as file:
                file.write(html_content)

            logger.info(f"HTML-Summary erfolgreich erstellt für {BE_key}")
            return html_content

        except Exception as e:
            raise Exception(f"Fehler beim Aufruf der OpenAI API oder bei der HTML-Verarbeitung: {e}")

    def process_multiple_epics(self, be_file_path: str, json_dir: str = '../output') -> Dict[str, Dict[str, int]]:
        """
        Verarbeitet mehrere Business Epics aus einer Datei.

        Args:
            be_file_path: Pfad zur Datei mit Business Epic Keys
            json_dir: Verzeichnis mit den JSON-Zusammenfassungen

        Returns:
            Dictionary mit Token-Nutzung pro Business Epic
        """
        token_usage_results = {}

        try:
            # Business Epic Keys aus Datei lesen
            with open(be_file_path, 'r', encoding='utf-8') as file:
                be_keys = [line.strip() for line in file if line.strip()]

            if not be_keys:
                print(f"Fehler: Keine Business Epic Keys in {be_file_path} gefunden")
                return token_usage_results

        except Exception as e:
            print(f"Fehler beim Lesen der Business Epic Keys Datei: {e}")
            return token_usage_results

        # Jeden Business Epic Key verarbeiten
        for be_key in be_keys:
            print(f"Verarbeite Business Epic: {be_key}")

            # Eingabedatei lesen
            try:
                with open(f"{json_dir}/{be_key}_json_summary.json", 'r', encoding='utf-8') as file:
                    issue_content = file.read()
            except Exception as e:
                print(f"Fehler beim Lesen der Eingabedatei für {be_key}: {e}")
                continue

            # HTML generieren und speichern
            output_file = os.path.join(json_dir, f"{be_key}_summary.html") if self.output_dir is None else os.path.join(self.output_dir, f"{be_key}_summary.html")

            try:
                _, token_usage = self.generate_epic_html(issue_content, be_key, output_file)
                token_usage_results[be_key] = token_usage
                print(f"HTML-Datei erfolgreich erstellt bei {output_file}")
            except Exception as e:
                print(f"Fehler bei der HTML-Generierung für {be_key}: {e}")

        return token_usage_results


# Beispielverwendung
if __name__ == "__main__":
    import argparse

    # Kommandozeilenargumente parsen
    parser = argparse.ArgumentParser(description='Konvertiere JIRA-Issue-Text zu HTML mit eingebetteten Bildern')
    parser.add_argument('--file', default='BE_Liste.txt', help='Datei mit Business Epic Keys (Standard: BE_Liste.txt)')
    parser.add_argument('--model', default='gpt-4.1-mini', help='LLM-Modell für die Generierung (Standard: gpt-4.1-mini)')
    parser.add_argument('--output-dir', default='../output', help='Ausgabeverzeichnis für HTML-Dateien (Standard: ../output)')
    parser.add_argument('--template', default='./epic-html_template.html', help='Pfad zur HTML-Vorlage (Standard: ./epic-html_template.html)')
    args = parser.parse_args()

    # HTML-Generator initialisieren
    generator = EpicHtmlGenerator(
        template_path=args.template,
        model=args.model,
        output_dir=args.output_dir
    )

    # Mehrere Epics verarbeiten
    token_usage = generator.process_multiple_epics(args.file)
