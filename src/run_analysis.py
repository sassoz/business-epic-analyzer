# src/run_analysis.py
"""
Haupt-Skript zur Ausführung der Jira-Projektanalyse.

Dieses Skript dient als Kommandozeilenschnittstelle (CLI), um gezielte Analysen
für ein spezifiziertes Business Epic durchzuführen. Es orchestriert die
Datenbeschaffung, die Ausführung der ausgewählten Analysen und die anschließende
Berichterstattung der Ergebnisse.

Benutzung (wenn im src-Verzeichnis):
python run_analysis.py <EPIC_ID> --analyze scope status creep
"""
import argparse
import json
import sys
import os

# Fügen Sie das übergeordnete Verzeichnis (Projekt-Root) zum Suchpfad hinzu...
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from utils.project_data_provider import ProjectDataProvider
from features.dynamics_analyzer import DynamicsAnalyzer
from features.status_analyzer import StatusAnalyzer
from features.scope_analyzer import ScopeAnalyzer
from features.time_creep_analyzer import TimeCreepAnalyzer
from features.console_reporter import ConsoleReporter

def main():
    """
    Verarbeitet Kommandozeilenargumente und steuert den Analyse-Workflow.
    """
    parser = argparse.ArgumentParser(
        description="Führt eine modulare Projektanalyse für ein JIRA Business Epic aus."
    )
    parser.add_argument(
        "epic_id",
        type=str,
        help="Die ID des Business Epics (z.B. BEB2B-259)."
    )
    parser.add_argument(
        "--analyze",
        nargs='+',
        choices=['dynamics', 'status', 'scope', 'creep', 'all'],
        default=['all'],
        help="Gibt an, welche Analysen ausgeführt werden sollen. 'all' führt alle aus."
    )
    args = parser.parse_args()

    # Wenn 'all' gewählt wurde, alle Analysen ausführen
    requested_analyses = set(args.analyze)
    if 'all' in requested_analyses:
        requested_analyses = {'dynamics', 'status', 'scope', 'creep'}

    print(f"\n--- Starte Analyse für '{args.epic_id}' ---")

    # 1. Daten laden
    data_provider = ProjectDataProvider(args.epic_id)
    if not data_provider.is_valid():
        print(f"Fehler: Konnte keine gültigen Daten für Epic '{args.epic_id}' laden. Abbruch.")
        return

    # 2. Reporter instanziieren
    reporter = ConsoleReporter()

    # 3. Ausgewählte Analysen ausführen und Ergebnisse berichten
    if 'dynamics' in requested_analyses:
        dynamics_results = DynamicsAnalyzer().analyze(data_provider)
        reporter.report_dynamics(dynamics_results)

        # Optional: Ergebnis in Datei speichern
        output_filename = f"activity_analysis_{args.epic_id}.json"
        with open(output_filename, 'w', encoding='utf-8') as f:
            # datetime objekte sind nicht json serialisierbar, daher manuell umwandeln
            if dynamics_results.get('analysis_metadata', {}).get('key_contributors'):
                 for contrib in dynamics_results['analysis_metadata']['key_contributors']:
                      if 'last_activity_date' in contrib:
                           contrib['last_activity_date'] = contrib['last_activity_date'].isoformat()
            json.dump(dynamics_results, f, indent=4)
        print(f"Dynamik-Analyse in '{output_filename}' gespeichert.")


    if 'status' in requested_analyses:
        status_results = StatusAnalyzer().analyze(data_provider)
        reporter.report_status(status_results, args.epic_id)
        reporter.create_status_timeline_plot(
            status_results['all_status_changes'],
            data_provider.epic_id,
            data_provider.all_activities
        )

    if 'scope' in requested_analyses:
        scope_results = ScopeAnalyzer().analyze(data_provider)
        reporter.report_scope(scope_results)

    if 'creep' in requested_analyses:
        creep_results = TimeCreepAnalyzer().analyze(data_provider)
        reporter.report_time_creep(creep_results)
        # Plot, der Time-Creep-Daten benötigt
        reporter.create_activity_and_creep_plot(
            creep_results,
            data_provider.all_activities,
            data_provider.epic_id
        )

    print("\n--- Analyse abgeschlossen ---")

if __name__ == '__main__':
    main()
