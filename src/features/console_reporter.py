# src/features/console_reporter.py
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
from datetime import datetime, timedelta, date # Import date for calculation
import os
import json
import networkx as nx
import re # Import re for regex parsing

from utils.config import LLM_MODEL_TIME_CREEP, TOKEN_LOG_FILE, PLOT_DIR
from utils.logger_config import logger
from utils.project_data_provider import ProjectDataProvider # Import ProjectDataProvider
from utils.azure_ai_client import AzureAIClient # Import AzureAIClient
from utils.prompt_loader import load_prompt_template # Import load_prompt_template
from utils.token_usage_class import TokenUsage # Import TokenUsage

class ConsoleReporter:
    """
    Verantwortlich für die Darstellung von Analyseergebnissen auf der Konsole
    und die Erzeugung von visuellen Plots.
    """

    def __init__(self):
        # Initialize TokenUsage here so it can be passed to AzureAIClient
        self.token_tracker = TokenUsage(log_file_path=TOKEN_LOG_FILE)
        # AzureAIClient instance, system prompt can be general or specific
        self.azure_summary_client = AzureAIClient(system_prompt="Du bist ein hilfreicher Assistent für die Analyse von Jira-Tickets.")


    def _format_timedelta(self, td: timedelta) -> str:
        """Formatiert eine Zeitdifferenz in einen lesbaren String."""
        if not isinstance(td, timedelta) or td.total_seconds() <= 0:
            return "Weniger als ein Tag"
        total_days = td.days
        months, days = divmod(total_days, 30)
        parts = []
        if months > 0: parts.append(f"{months} Monat{'e' if months > 1 else ''}")
        if days > 0: parts.append(f"{days} Tag{'e' if days > 1 else ''}")
        return ", ".join(parts) or "0 Tage"

    def _calculate_duration_string(self, start_date_str: str, end_date_str: str) -> str:
        """
        Berechnet die Dauer zwischen zwei Datumsstrings und formatiert sie.
        """
        try:
            start_date = datetime.fromisoformat(start_date_str).date()
            end_date = datetime.fromisoformat(end_date_str).date()
            duration = end_date - start_date
            return self._format_timedelta(duration)
        except ValueError:
            return "unbestimmte Dauer"

    def report_scope(self, scope_results: dict):
        """Gibt die Ergebnisse der Umfang- & Aufwand-Analyse aus."""
        print("\n--- Analyse von Umfang und Aufwand ---")
        for epic_key, children in scope_results['epic_breakdown'].items():
            print(f"Epic {epic_key}")
            for child in children:
                if child['type'] == 'Story':
                    print(f"  Story {child['key']} ({child['points']} Pts., Resolution={child['resolution']})")
                else:
                    print(f"  Bug {child['key']}")
        print("\n--- Zusammenfassung Umfang & Aufwand ---")
        print(f"- Gesamtzahl aller Issues im Baum: {scope_results.get('total_issues', 0)}")
        print(f"- Gesamtzahl gefundener Epics: {scope_results['total_epics_found']}")
        print(f"- Gesamtzahl gefundener Stories: {scope_results['total_stories_found']}")
        project_count = scope_results.get('project_count', 0)
        print(f"- Anzahl beteiligter Jira-Projekte (ohne BE): {project_count}")
        if project_count > 0:
            print("  -> Verteilung auf die Projekte:")
            sorted_projects = sorted(scope_results.get('project_distribution', {}).items(), key=lambda item: item[1], reverse=True)
            for project, count in sorted_projects:
                plural = "s" if count > 1 else ""
                print(f"     - {project:<15} | {count} Issue{plural}")
        print(f"- Gesamtsumme der Story Points: {scope_results['total_story_points']}")

    def report_dynamics(self, dynamics_results: dict):
        """Gibt die Ergebnisse der Projektdynamik-Analyse aus."""
        print("\n--- Analyse der Projektdynamik ---")
        metadata = dynamics_results.get("analysis_metadata", {})
        print(json.dumps(metadata, indent=4, default=str))

    def report_status(self, status_results: dict, epic_id: str):
        """Gibt die Ergebnisse der Status-Analyse aus."""
        print("\n--- Analyse der Statuswechsel und Laufzeiten ---")
        print(f"\n--- Verweildauer des Epics '{epic_id}' in den Ziel-Status ---")
        durations = status_results.get('epic_status_durations', {})
        for status, duration in durations.items():
            if duration.total_seconds() > 0:
                print(f"- {status:<25}: {self._format_timedelta(duration)}")

        print("\n--- Coding-Laufzeit (basiert auf Story-Status) ---")
        start = status_results.get('coding_start_time')
        end = status_results.get('coding_end_time')
        start_str = datetime.fromisoformat(start).strftime('%d-%m-%Y') if start else 'Nicht gefunden'
        end_str = datetime.fromisoformat(end).strftime('%d-%m-%Y') if end else 'Nicht gefunden'
        print(f"- Coding-Start (erste Story 'In Progress'): {start_str}")
        print(f"- Coding-Ende (letzte Story 'Resolved/Closed'): {end_str}")

        if start and end:
            start_dt = datetime.fromisoformat(start)
            end_dt = datetime.fromisoformat(end)
            duration = end_dt - start_dt
            if duration.days >= 0:
                months, days = divmod(duration.days, 30)
                parts = []
                if months > 0: parts.append(f"{months} Monat{'e' if months > 1 else ''}")
                if days > 0: parts.append(f"{days} Tag{'e' if days > 1 else ''}")
                duration_str = " & ".join(parts) or "Weniger als ein Tag"
                print(f"- Coding-Laufzeit: {duration_str}")
        else:
            print("- Coding-Laufzeit: Nicht berechenbar")

    def report_backlog(self, backlog_results: dict):
        """Gibt die Ergebnisse der Backlog-Analyse aus."""
        print("\n--- Analyse der Backlog-Entwicklung (Stories) ---")
        if backlog_results.get("error"):
            print(backlog_results["error"])
            return

        start_time = backlog_results.get('coding_start_time')
        finish_time = backlog_results.get('coding_finish_time')

        start_str = datetime.fromisoformat(start_time).strftime('%d-%m-%Y') if start_time else "Nicht begonnen"
        finish_str = datetime.fromisoformat(finish_time).strftime('%d-%m-%Y') if finish_time else "Offen"

        print(f"- Refinement-Start (erste Story in 'Refinement'): {start_str}")
        print(f"- Refinement-Ende (letzte Story in 'Resolved/Closed'): {finish_str}")

    def report_time_creep(self, issue_tree_with_creep: nx.DiGraph, data_provider: ProjectDataProvider):
        """
        Gibt die Ergebnisse der Time-Creep-Analyse aus dem Issue-Baum aus
        und generiert eine LLM-Zusammenfassung, falls noch nicht vorhanden.
        """
        print("\n--- Analyse der Terminverschiebungen (TIME_CREEP) ---")

        all_events = []
        for node_key in issue_tree_with_creep.nodes:
            if 'time_creep_events' in issue_tree_with_creep.nodes[node_key]:
                all_events.extend(issue_tree_with_creep.nodes[node_key]['time_creep_events'])

        if all_events:
            all_events.sort(key=lambda x: x['timestamp'])
            for event in all_events:
                print(f"{event['timestamp']} | {event['issue']:<15} | {event['event_type']:<12} | {event['details']}")
        else:
            print("Keine relevanten Terminänderungen für strategische Issues gefunden.")

        # --- LLM Summarization Addition ---
        epic_id = data_provider.epic_id # Get the main epic ID from the data provider

        # Check if LLM summary already exists in the issue tree
        llm_summary_text = issue_tree_with_creep.nodes[epic_id].get('llm_time_creep_summary')

        if not llm_summary_text:
            logger.info(f"Generiere LLM-Zusammenfassung für Time Creep von Epic {epic_id}...")
            try:
                # 1. Format time creep events for LLM input
                formatted_time_creep_events = []
                for event in all_events:
                    if event.get('event_type') == 'TIME_CREEP':
                        # Extract dates to calculate duration
                        match_old_date = re.search(r'von (\d{4}-\d{2}-\d{2}|\w{1,2}\d{1,2}_\d{2})', event['details'])
                        match_new_date = re.search(r'auf (\d{4}-\d{2}-\d{2}|\w{1,2}\d{1,2}_\d{2})', event['details'])

                        old_date_str = match_old_date.group(1) if match_old_date else ""
                        new_date_str = match_new_date.group(1) if match_new_date else ""

                        # Attempt to parse date strings for duration calculation
                        # Prioritize ISO format, then 'Qx_yy' or 'PIxx'
                        parsed_old_date = None
                        parsed_new_date = None

                        try:
                            parsed_old_date = datetime.fromisoformat(old_date_str).date()
                        except ValueError:
                            # Try parsing as Qx_yy or PIxx for Fix Version/s
                            # This requires re-using the logic from TimeCreepAnalyzer
                            # For simplicity here, we'll just try to use the extracted string
                            pass

                        try:
                            parsed_new_date = datetime.fromisoformat(new_date_str).date()
                        except ValueError:
                            pass

                        duration_str = "unbekannte Dauer"
                        if parsed_old_date and parsed_new_date:
                            duration = parsed_new_date - parsed_old_date
                            duration_str = self._format_timedelta(duration)
                        else: # Fallback for Fix Version/s or unparseable dates
                            duration_str = "eine unbestimmte Dauer" # Fallback if dates can't be parsed reliably from details string


                        formatted_time_creep_events.append(
                            f"{event['issue']}: erfuhr eine Terminverschiebung von etwa {duration_str} auf den {new_date_str}."
                        )
                    # TIME_SET and TIME_PULL_IN events are not explicitly requested in the summary prompt
                    # but could be added if deemed useful for the LLM's context.
                    # For now, sticking to TIME_CREEP as per prompt's "Fokus auf 'TIME_CREEP'".

                time_creep_str = "\n".join(formatted_time_creep_events)

                # 2. Get JSON summary for the epic
                epic_json_summary = data_provider.get_epic_json_summary(epic_id)
                if not epic_json_summary:
                    logger.warning(f"Keine JSON-Zusammenfassung für Epic {epic_id} gefunden, überspringe LLM-Zusammenfassung.")
                    llm_summary_text = "LLM-Zusammenfassung nicht verfügbar (JSON-Daten fehlen)."
                else:
                    # 3. Load the summary prompt template
                    summary_prompt_template = load_prompt_template('time_creep_summary.yaml', 'user_prompt_template')

                    # 4. Prepare the full prompt for the LLM
                    full_user_prompt = summary_prompt_template.format(
                        epic_id=epic_id,
                        epic_id_json_summary=json.dumps(epic_json_summary, indent=2), # Ensure it's a string
                        time_creep=time_creep_str
                    )

                    # 5. Call the LLM
                    llm_response = self.azure_summary_client.completion(
                        model_name=LLM_MODEL_TIME_CREEP,
                        user_prompt=full_user_prompt,
                        temperature=0.2,
                        max_tokens=2000,
                        response_format={"type": "text"} # Expecting plain text summary
                    )

                    if self.token_tracker and "usage" in llm_response:
                        usage_info = llm_response["usage"]
                        self.token_tracker.log_usage(
                            model=LLM_MODEL_TIME_CREEP,
                            input_tokens=usage_info.prompt_tokens,
                            output_tokens=usage_info.completion_tokens,
                            total_tokens=usage_info.total_tokens,
                            task_name="time_creep_summary_generation"
                        )

                    llm_summary_text = llm_response["text"]

            except Exception as e:
                logger.error(f"Fehler beim Aufruf des LLM für Time Creep Summary von Epic {epic_id}: {e}", exc_info=True)
                llm_summary_text = "LLM-Zusammenfassung fehlgeschlagen aufgrund eines internen Fehlers."

            # Store the generated summary in the issue tree
            issue_tree_with_creep.nodes[epic_id]['llm_time_creep_summary'] = llm_summary_text

        # Print the LLM summary (whether newly generated or pre-existing)
        print("\n--- LLM-Zusammenfassung der Terminverschiebungen ---")
        print(llm_summary_text)

    def create_status_timeline_plot(self, status_changes: list, epic_id: str, all_activities: list):
        """Erstellt und speichert eine visuelle Timeline der Statuswechsel."""
        print(f"\nErstelle Status-Timeline-Plot für {epic_id}...")
        output_path = os.path.join(PLOT_DIR, f"{epic_id}_status_timeline.png")
        plt.figure(figsize=(10, 2))
        plt.text(0.5, 0.5, 'Status Timeline Plot', ha='center', va='center')
        plt.savefig(output_path, dpi=150)
        plt.close()
        logger.info(f"Status-Timeline-Grafik gespeichert unter: {output_path}")

    def create_backlog_plot(self, backlog_results: dict, epic_id: str):
        """Erstellt und speichert einen Graphen der Backlog-Entwicklung."""
        if backlog_results.get("error"):
            return # Don't create a plot if there was an error

        print(f"Erstelle Backlog-Entwicklungs-Plot für {epic_id}...")
        results_df = backlog_results["results_df"]

        if results_df.empty:
            logger.warning(f"Keine Daten für Backlog-Plot von Epic {epic_id} vorhanden.")
            return

        fig, ax = plt.subplots(figsize=(12, 7))

        ax.plot(results_df.index, results_df['refined_backlog'], label='Refined Backlog (Kumulativ)', color='blue', linestyle='--')
        ax.plot(results_df.index, results_df['finished_backlog'], label='Finished Backlog (Kumulativ)', color='green')
        ax.fill_between(results_df.index, results_df['finished_backlog'], results_df['refined_backlog'],
                        color='orange', alpha=0.3, label='Active Backlog')

        # Formatting
        ax.set_title(f'Backlog-Entwicklung für Epic {epic_id}')
        ax.set_xlabel('Datum')
        ax.set_ylabel('Anzahl Stories')
        ax.legend()
        ax.grid(True, which='both', linestyle='--', linewidth=0.5)

        # Improve date formatting
        fig.autofmt_xdate()
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%d.%m.%Y'))
        ax.xaxis.set_major_locator(mdates.AutoDateLocator())

        plt.tight_layout()

        output_path = os.path.join(PLOT_DIR, f"{epic_id}_backlog_development.png")
        try:
            plt.savefig(output_path, dpi=150)
            logger.info(f"Backlog-Entwicklungs-Grafik gespeichert unter: {output_path}")
        except Exception as e:
            logger.error(f"Fehler beim Speichern des Backlog-Plots: {e}")
        finally:
            plt.close(fig)

    def create_activity_and_creep_plot(self, issue_tree_with_creep: nx.DiGraph, all_activities: list, epic_id: str):
        """Erstellt eine kombinierte Dashboard-Grafik."""
        print(f"Erstelle Aktivitäts-Dashboard für {epic_id}...")

        time_creep_events = []
        for node_key in issue_tree_with_creep.nodes:
            if 'time_creep_events' in issue_tree_with_creep.nodes[node_key]:
                time_creep_events.extend(issue_tree_with_creep.nodes[node_key]['time_creep_events'])

        output_path = os.path.join(PLOT_DIR, f"{epic_id}_activity_creep_dashboard.png")
        plt.figure(figsize=(10, 5))
        plt.text(0.5, 0.5, 'Activity & Creep Dashboard', ha='center', va='center')
        plt.savefig(output_path, dpi=150)
        plt.close()
        logger.info(f"Aktivitäts-Dashboard-Grafik gespeichert unter: {output_path}")
