# src/utils/project_analyzer.py
"""
Ein konsolidiertes Analyse-Modul für Jira-Projektdaten.

Dieses Modul stellt die zentrale `ProjectAnalyzer`-Klasse zur Verfügung, die als
einziger Anlaufpunkt für verschiedene tiefgehende Analysen eines Jira-Projekts dient,
das durch ein Business Epic repräsentiert wird.

Der Workflow ist wie folgt:
1.  Ein `ProjectAnalyzer`-Objekt wird mit einer Epic-ID initialisiert.
2.  Beim Initialisieren wird der gesamte zugehörige Issue-Baum aus den vorab
    gescrapeten JSON-Dateien geladen und alle Aktivitäten werden gesammelt.
3.  Verschiedene Methoden können aufgerufen werden, um Analysen durchzuführen:
    - `analyze_dynamics()`: Für allgemeine Projektdynamik-Metriken.
    - `analyze_status()`: Für detaillierte Status-Analysen.
    - `analyze_time_creep()`: Zur Identifizierung von Terminverschiebungen.
4.  Zusätzliche Methoden können visuelle Auswertungen als Bilddateien erzeugen.
"""

import json
import os
import sys
import argparse
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import networkx as nx
import re
import pandas as pd
from datetime import datetime, timedelta, date
from collections import Counter

# Pfad-Konfiguration für korrekte Modul-Importe
src_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from utils.logger_config import logger
from utils.jira_tree_classes import JiraTreeGenerator
from utils.config import JIRA_ISSUES_DIR, ISSUE_TREES_DIR


class ProjectAnalyzer:
    """
    Führt umfassende Analysen eines JIRA-Projekts basierend auf einem Epic durch.

    Die Klasse lädt beim Initialisieren alle Aktivitäten des gesamten Issue-Baums
    und stellt Methoden bereit, um verschiedene Aspekte wie Projektdynamik,
    Statusverläufe und Terminverschiebungen (Time Creep) zu analysieren und
    zu visualisieren.
    """

    def __init__(self, epic_id: str, json_dir: str = JIRA_ISSUES_DIR):
        """
        Initialisiert den Analyzer, baut den Issue-Baum und lädt alle Aktivitäten.

        Args:
            epic_id (str): Die ID des Business Epics, das den Startpunkt des Baums darstellt.
            json_dir (str): Das Verzeichnis, in dem die JSON-Dateien der Issues liegen.
        """
        self.epic_id = epic_id
        self.json_dir = json_dir
        self.tree_generator = JiraTreeGenerator(json_dir=self.json_dir)
        self.issue_tree = self.tree_generator.build_issue_tree(self.epic_id)

        self.all_activities = self._gather_all_activities()
        if self.all_activities:
            # Sortiert alle Aktivitäten einmalig für alle nachfolgenden Analysen.
            self.all_activities.sort(key=lambda x: x.get('zeitstempel_iso', ''))

        logger.info(f"ProjectAnalyzer für Epic '{epic_id}' mit {len(self.all_activities)} Aktivitäten initialisiert.")

    def _gather_all_activities(self) -> list:
        """
        Sammelt die Aktivitäten aller Issues im Baum. Dies ist eine private Hilfsmethode.

        Returns:
            list: Eine unsortierte Liste aller Aktivitäten aus allen zum Projekt gehörenden Issues.
        """
        all_activities = []
        if not self.issue_tree or not isinstance(self.issue_tree, nx.DiGraph): return []
        for issue_key in self.issue_tree.nodes():
            file_path = os.path.join(self.json_dir, f"{issue_key}.json")
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    issue_data = json.load(f)
                    activities = issue_data.get('activities', [])
                    for activity in activities:
                        activity['issue_key'] = issue_key
                    all_activities.extend(activities)
            except (FileNotFoundError, json.JSONDecodeError) as e:
                logger.warning(f"Datei für Issue '{issue_key}' nicht gefunden oder fehlerhaft: {e}")
                continue
        return all_activities

    def analyze_dynamics(self) -> dict:
        """
        Analysiert die allgemeine Projektdynamik.

        Ermittelt Metadaten wie Gesamtzahl der Aktivitäten, Aktivität der letzten
        vier Wochen, signifikante Änderungen und die Hauptbeitragenden. Identifiziert
        zudem Schlüsselereignisse wie Scope-Änderungen oder Status-Blockaden.

        Returns:
            dict: Ein Dictionary mit den Analyse-Metadaten und einer chronologischen
                  Liste der Schlüsselereignisse.
        """
        if not self.all_activities: return {}
        key_events = []
        significant_changes = []
        scope_change_tracker = set()
        SIGNIFICANT_FIELDS = ['Status', 'Description', 'Acceptance Criteria', 'Assignee', 'Fix Version/s']
        for activity in self.all_activities:
            field = activity.get('feld_name')
            new_value = activity.get('neuer_wert', '')
            issue_key = activity.get('issue_key')
            timestamp_iso = activity.get('zeitstempel_iso', '')
            event_type = None
            if field == 'Status' and new_value and 'BLOCKED' in new_value.upper():
                event_type = "STATUS_BLOCK"
                details = f"Status von '{issue_key}' wurde auf Blocked gesetzt."
            elif field in ['Target end', 'Fix Version/s']:
                event_type = "TIME_CHANGE"
                details = f"Zeitplanung von '{issue_key}' ({field}) wurde geändert."
            elif field in ['Description', 'Acceptance Criteria']:
                activity_date = timestamp_iso[:10]
                if (issue_key, activity_date) not in scope_change_tracker:
                    event_type = "SCOPE_CHANGE"
                    details = f"Der Scope von '{issue_key}' wurde an diesem Tag angepasst."
                    scope_change_tracker.add((issue_key, activity_date))
            if event_type:
                key_events.append({"timestamp": timestamp_iso, "issue": issue_key, "event_type": event_type, "details": details})
            if field in SIGNIFICANT_FIELDS:
                significant_changes.append(activity)

        contributors = [act['benutzer'] for act in significant_changes if act.get('benutzer')]
        top_contributors = Counter(contributors).most_common(3)
        key_contributors = [{"name": name, "contributions": count} for name, count in top_contributors]

        now = datetime.now().astimezone()
        four_weeks_ago = now - timedelta(weeks=4)
        activities_last_4_weeks = [act for act in self.all_activities if datetime.fromisoformat(act['zeitstempel_iso']) >= four_weeks_ago]

        field_names = [act.get('feld_name') for act in self.all_activities if act.get('feld_name')]
        activity_counts_by_field = dict(Counter(field_names).most_common())

        key_events.sort(key=lambda x: x.get('timestamp', ''))

        return {
            "analysis_metadata": {
                "total_activities_found": len(self.all_activities),
                "activity_counts_by_field": activity_counts_by_field,
                "total_activities_last_4_weeks": len(activities_last_4_weeks),
                "total_significant_changes": len(significant_changes),
                "key_contributors": key_contributors
            },
            "key_events_chronological": key_events
        }

    def analyze_status(self) -> dict:
        """
        Führt eine detaillierte Analyse der Status-Änderungen durch.

        Returns:
            dict: Ein Dictionary, das eine Liste aller Statuswechsel und die
                  berechneten Verweildauern des Epics in bestimmten Status enthält.
        """
        if not self.all_activities: return {}
        all_status_changes = [
            {"timestamp": act.get('zeitstempel_iso'), "issue": act.get('issue_key'),
             "from_status": self._clean_status_name(act.get('alter_wert', 'N/A')),
             "to_status": self._clean_status_name(act.get('neuer_wert', 'N/A'))}
            for act in self.all_activities if act.get('feld_name') == 'Status'
        ]
        durations = self._calculate_epic_status_durations()
        return {"all_status_changes": all_status_changes, "epic_status_durations": durations}

    def _calculate_epic_status_durations(self) -> dict:
        """
        Berechnet die Verweildauer des Business Epics in vordefinierten Status.
        Fügt einen virtuellen 'FUNNEL'-Status am Anfang hinzu, um die erste Phase zu erfassen.

        Returns:
            dict: Ein Dictionary mit Statusnamen und deren Verweildauer als timedelta-Objekt.
        """
        TARGET_STATUSES = ['FUNNEL', 'REVIEW', 'ANALYSIS', 'BACKLOG', 'BACKLOG FOR ANALYSIS', 'IN PROGRESS']
        status_durations = {status: timedelta(0) for status in TARGET_STATUSES}
        epic_activities_only = [act for act in self.all_activities if act.get('issue_key') == self.epic_id]
        epic_status_changes = [act for act in epic_activities_only if act.get('feld_name') == 'Status']

        if epic_activities_only:
            epic_start_time_iso = epic_activities_only[0]['zeitstempel_iso']
            epic_status_changes.insert(0, {'zeitstempel_iso': epic_start_time_iso, 'neuer_wert': 'FUNNEL'})

        if len(epic_status_changes) < 1: return {}

        for i in range(len(epic_status_changes) - 1):
            start_act, end_act = epic_status_changes[i], epic_status_changes[i+1]
            status_name = self._clean_status_name(start_act.get('neuer_wert'))
            if status_name in TARGET_STATUSES:
                duration = datetime.fromisoformat(end_act['zeitstempel_iso']) - datetime.fromisoformat(start_act['zeitstempel_iso'])
                status_durations[status_name] += duration

        last_change = epic_status_changes[-1]
        last_status_name = self._clean_status_name(last_change.get('neuer_wert'))
        if last_status_name in TARGET_STATUSES:
            duration = datetime.now().astimezone() - datetime.fromisoformat(last_change['zeitstempel_iso'])
            status_durations[last_status_name] += duration

        return status_durations

    def create_status_timeline_plot(self, status_changes: list):
        """
        Erstellt und speichert eine visuelle Timeline der Statuswechsel.
        Die Grafik zeigt das Business Epic und die zugehörigen Issues in separaten Swimlanes.

        Args:
            status_changes (list): Eine Liste von Statuswechsel-Ereignissen,
                                   generiert von `analyze_status`.
        """
        epic_activities_only = [act for act in self.all_activities if act.get('issue_key') == self.epic_id]
        if epic_activities_only:
            epic_start_time_iso = epic_activities_only[0]['zeitstempel_iso']
            status_changes.append({'timestamp': epic_start_time_iso, 'issue': self.epic_id, 'to_status': 'FUNNEL'})
            status_changes.sort(key=lambda x: x['timestamp'])

        epic_dates, epic_labels, child_dates = [], [], []
        for change in status_changes:
            dt_object = datetime.fromisoformat(change['timestamp'])
            if change['issue'] == self.epic_id:
                epic_dates.append(dt_object); epic_labels.append(change['to_status'])
            else:
                child_dates.append(dt_object)

        fig, ax = plt.subplots(figsize=(20, 5), constrained_layout=True)
        ax.vlines(child_dates, 0, 0, color='tab:blue', alpha=0.4, linestyles='dotted')
        ax.vlines(epic_dates, 0, 1, color='tab:red', alpha=0.4, linestyles='dotted')
        ax.plot(child_dates, [0]*len(child_dates), 'x', color='tab:blue', markersize=8, label='Child-Issues')
        ax.plot(epic_dates, [1]*len(epic_dates), 'D', color='tab:red', markersize=8, label=f'Epic: {self.epic_id}')
        for date, label in zip(epic_dates, epic_labels):
            ax.text(date, 1.05, label, ha='center', va='bottom', fontsize=9, rotation=45)

        ax.set_yticks([0, 1]); ax.set_yticklabels(['Andere Issues', 'Business Epic'])
        ax.tick_params(axis='y', length=0)
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
        plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
        ax.grid(axis='x', linestyle='--', alpha=0.6)
        ax.set_title(f"Timeline der Statuswechsel für Epic: {self.epic_id}", fontsize=16)
        ax.legend(); ax.set_ylim(-0.5, 1.5)

        output_path = os.path.join(ISSUE_TREES_DIR, f"{self.epic_id}_status_timeline.png")
        plt.savefig(output_path, dpi=150)
        logger.info(f"Status-Timeline-Grafik gespeichert unter: {output_path}")

    def analyze_time_creep(self) -> list:
        """
        Analysiert Terminverschiebungen durch Konsolidierung aller Änderungen pro Tag.

        Diese Methode identifiziert den Netto-Effekt von Änderungen an den Feldern
        'Target end' und 'Fix Version/s' für jeden Tag, um irrelevantes "Rauschen"
        durch mehrfache Änderungen am selben Tag zu vermeiden.

        Returns:
            list: Eine chronologisch sortierte Liste von konsolidierten
                  Terminänderungs-Ereignissen (TIME_CREEP, TIME_PULL_IN, etc.).
        """
        daily_changes = {}
        for activity in self.all_activities:
            field = activity.get('feld_name')
            if field not in ['Target end', 'Fix Version/s']: continue
            issue_key = activity.get('issue_key')
            date_str = activity['zeitstempel_iso'][:10]
            group_key = (issue_key, date_str, field)
            if group_key not in daily_changes: daily_changes[group_key] = []
            daily_changes[group_key].append(activity)

        consolidated_events = []
        for (issue_key, date_iso, field), activities_for_day in daily_changes.items():
            if not activities_for_day: continue
            activities_for_day.sort(key=lambda x: x['zeitstempel_iso'])

            start_of_day_str = activities_for_day[0].get('alter_wert')
            end_of_day_str = activities_for_day[-1].get('neuer_wert')

            parse_func = self._parse_any_date_string if field == 'Target end' else self._parse_fix_version_to_date
            start_date = parse_func(start_of_day_str)
            end_date = parse_func(end_of_day_str)

            if start_date != end_date:
                event_data = self._compare_dates(issue_key, field, start_date, end_date, end_of_day_str)
                if event_data:
                    event_data['timestamp'] = date_iso
                    consolidated_events.append(event_data)

        consolidated_events.sort(key=lambda x: x['timestamp'])
        return consolidated_events

    def _compare_dates(self, issue_key, field, old_date, new_date, new_value_str):
        """
        Private Hilfsmethode: Klassifiziert eine Terminänderung.

        Args:
            issue_key (str): Der Schlüssel des betroffenen Issues.
            field (str): Das geänderte Feld ('Target end' oder 'Fix Version/s').
            old_date (date|None): Das Datum vor der Änderung.
            new_date (date|None): Das Datum nach der Änderung.
            new_value_str (str): Der rohe String-Wert der Änderung für die Detailbeschreibung.

        Returns:
            dict|None: Ein Event-Dictionary oder None, wenn keine relevante Änderung stattfand.
        """
        event_type = None
        details = ""
        if old_date is None and new_date is not None:
            event_type = "TIME_SET"
            details = f"Termin '{field}' erstmalig gesetzt auf: {new_value_str}"
        elif old_date is not None and new_date is None:
            event_type = "TIME_UNSET"
            details = f"Termin '{field}' (war {old_date}) wurde entfernt."
        elif old_date is not None and new_date is not None:
            if new_date > old_date:
                event_type = "TIME_CREEP"
                details = f"Termin '{field}' verschoben von {old_date} auf {new_date}"
            elif new_date < old_date:
                event_type = "TIME_PULL_IN"
                details = f"Termin '{field}' vorgezogen von {old_date} auf {new_date}"
        if event_type:
            return {"issue": issue_key, "event_type": event_type, "details": details}
        return None

    def _parse_any_date_string(self, date_str: str) -> date | None:
        """
        Private Hilfsmethode: Parst ein Datum aus verschiedenen Formaten (ISO, Custom).

        Args:
            date_str (str): Der zu parsende Datumsstring.

        Returns:
            date|None: Ein date-Objekt oder None, wenn das Parsen fehlschlägt.
        """
        if not date_str: return None
        try:
            return datetime.fromisoformat(date_str).date()
        except ValueError:
            try:
                cleaned_str = date_str.split(':')[-1]
                return datetime.strptime(cleaned_str, '%d/%b/%Y').date()
            except (ValueError, IndexError):
                logger.warning(f"Konnte Datum nicht aus String parsen: '{date_str}'")
                return None

    def _parse_fix_version_to_date(self, version_string: str) -> date | None:
        """
        Private Hilfsmethode: Wandelt einen 'Fix Version'-String in ein Datum um.

        Args:
            version_string (str): Der String der Fix-Version (z.B. 'PrioQ1_25').

        Returns:
            date|None: Das Enddatum des entsprechenden Quartals oder None.
        """
        if not version_string: return None
        match = re.search(r'Q(\d)_(\d{2})', version_string)
        if not match: return None
        quarter, year_short = map(int, match.groups())
        year = 2000 + year_short
        end_dates = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}
        if quarter in end_dates:
            month, day = end_dates[quarter]
            return date(year, month, day)
        return None

    def _clean_status_name(self, raw_name: str) -> str:
        """Private Hilfsmethode: Bereinigt rohe Status-Namen."""
        if not raw_name: return "N/A"
        if '[' in raw_name:
            try: return raw_name.split(':')[1].split('[')[0].strip().upper()
            except IndexError: return raw_name.strip().upper()
        return raw_name.strip().upper()

    def _format_timedelta(self, td: timedelta) -> str:
        """Private Hilfsmethode: Formatiert eine Zeitdifferenz in einen lesbaren String."""
        total_days = td.days
        if total_days <= 0: return "Weniger als ein Tag"
        months, days = divmod(total_days, 30)
        parts = [f"{months} Monat{'e' if months > 1 else ''}" if months > 0 else "", f"{days} Tag{'e' if days > 1 else ''}" if days > 0 else ""]
        return ", ".join(filter(None, parts)) or "0 Tage"

    def create_activity_and_creep_plot(self, time_creep_events: list):
        """
        Erstellt eine kombinierte Dashboard-Grafik.

        Zeigt die monatliche Gesamtaktivität als Säulendiagramm und legt eine
        Swimlane darüber, die kritische TIME_CREEP-Ereignisse als Marker anzeigt.

        Args:
            time_creep_events (list): Eine Liste von Terminänderungs-Ereignissen,
                                      generiert von `analyze_time_creep`.
        """
        if not self.all_activities:
            logger.warning("Keine Aktivitäten für die Grafikerstellung vorhanden.")
            return

        df = pd.DataFrame(self.all_activities)
        df['timestamp_dt'] = pd.to_datetime(df['zeitstempel_iso'], utc=True)
        monthly_counts = df.set_index('timestamp_dt').resample('ME').size()

        creep_events = [event for event in time_creep_events if event['event_type'] == 'TIME_CREEP']
        creep_dates = [datetime.fromisoformat(event['timestamp']) for event in creep_events]

        fig, (ax1, ax2) = plt.subplots(
            2, 1, sharex=True, figsize=(20, 8),
            gridspec_kw={'height_ratios': [1, 4]}
        )
        fig.suptitle(f"Projektübersicht für Epic: {self.epic_id}", fontsize=18)

        ax1.set_title("Terminverschiebungen (TIME_CREEP)")
        ax1.scatter(creep_dates, [0]*len(creep_dates), marker='x', color='red', s=100, label='TIME_CREEP Event')
        ax1.yaxis.set_visible(False)
        ax1.spines[['left', 'right', 'top']].set_visible(False)
        ax1.set_ylim(-0.5, 0.5)

        ax2.set_title("Monatliche Projektaktivität")
        ax2.bar(monthly_counts.index, monthly_counts.values, width=20, color='skyblue', label='Anzahl Aktivitäten')
        ax2.set_ylabel("Anzahl Aktivitäten pro Monat")
        ax2.grid(axis='y', linestyle='--', alpha=0.7)
        ax2.spines[['right', 'top']].set_visible(False)

        ax2.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
        ax2.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
        plt.setp(ax2.get_xticklabels(), rotation=30, ha="right")

        output_path = os.path.join(ISSUE_TREES_DIR, f"{self.epic_id}_activity_creep_dashboard.png")
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        logger.info(f"Aktivitäts-Dashboard-Grafik gespeichert unter: {output_path}")
        plt.close(fig)


# Angepasste Hauptausführung
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Führt alle Analysen für ein JIRA Business Epic aus.")
    parser.add_argument("epic_id", type=str, help="Die ID des Business Epics (z.B. BEB2B-259).")
    args = parser.parse_args()

    analyzer = ProjectAnalyzer(epic_id=args.epic_id)

    print("\n--- Analyse der Projektdynamik ---")
    dynamics_result = analyzer.analyze_dynamics()
    if dynamics_result:
        output_filename = f"activity_analysis_{args.epic_id}.json"
        with open(output_filename, 'w', encoding='utf-8') as f: json.dump(dynamics_result, f, indent=4)
        print(f"Dynamik-Analyse in '{output_filename}' gespeichert.")
        print(json.dumps(dynamics_result['analysis_metadata'], indent=4))
    else: print("Keine Daten für die Dynamik-Analyse gefunden.")

    print("\n--- Analyse der Statuswechsel ---")
    status_result = analyzer.analyze_status()
    if status_result.get("all_status_changes"):
        all_status_changes = status_result['all_status_changes']
        print(f"\n--- Verweildauer des Epics '{args.epic_id}' in den Ziel-Status ---")
        for status, duration in status_result['epic_status_durations'].items():
            if duration.total_seconds() > 0: print(f"- {status:<25}: {analyzer._format_timedelta(duration)}")
        print("\n--- Projektlaufzeiten ---")
        if len(all_status_changes) > 1:
            real_start_time = datetime.fromisoformat(all_status_changes[0]['timestamp'])
            real_end_time = datetime.fromisoformat(all_status_changes[-1]['timestamp'])
            print(f"- Business Epic Laufzeit (real): {analyzer._format_timedelta(real_end_time - real_start_time)}")
        else: print("- Business Epic Laufzeit (real): Nicht genügend Daten für Berechnung.")
        epic_activities_only = [act for act in analyzer.all_activities if act.get('issue_key') == args.epic_id]
        if epic_activities_only:
            start_time = datetime.fromisoformat(epic_activities_only[0]['zeitstempel_iso'])
            epic_only_changes = [c for c in all_status_changes if c['issue'] == args.epic_id]
            closed_change = next((c for c in epic_only_changes if c['to_status'] == 'CLOSED'), None)
            if closed_change:
                end_time = datetime.fromisoformat(closed_change['timestamp']); end_text = " (bis zum Status 'CLOSED')"
            else:
                end_time = datetime.now().astimezone(); end_text = " (bis heute)"
            print(f"- Business Epic Laufzeit (Jira): {analyzer._format_timedelta(end_time - start_time)}{end_text}")
        else: print("- Business Epic Laufzeit (Jira): Keine Aktivitäten für das Epic gefunden.")
        analyzer.create_status_timeline_plot(all_status_changes)
    else: print("Keine Statuswechsel für die Analyse gefunden.")

    print("\n--- Analyse der Terminverschiebungen (TIME_CREEP) ---")
    time_creep_events = analyzer.analyze_time_creep()
    if time_creep_events:
        for event in time_creep_events:
            print(f"{event['timestamp'][:10]} | {event['issue']:<15} | {event['event_type']:<12} | {event['details']}")
    else:
        print("Keine relevanten Terminänderungen gefunden.")

    analyzer.create_activity_and_creep_plot(time_creep_events)
