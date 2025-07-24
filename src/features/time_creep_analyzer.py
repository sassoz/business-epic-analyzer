# src/features/time_creep_analyzer.py
import re
from datetime import datetime, date
from collections import OrderedDict
from src.utils.project_data_provider import ProjectDataProvider
from utils.logger_config import logger
import networkx as nx

class TimeCreepAnalyzer:
    """
    Führt eine detaillierte, zustandsbasierte Analyse von Terminänderungen durch.

    Diese Klasse analysiert die Änderungshistorie der Felder 'Target end' und
    'Fix Version/s' für strategische Jira-Issues. Die Logik wurde iterativ
    verfeinert, um eine präzise und kontextsensitive Auswertung zu ermöglichen,
    die typische Jira-Workflows wie das Klonen von Issues oder die Planung in
    Program-Inkrementen berücksichtigt.

    Die Kernmerkmale der Analyse sind:
    - **Getrennte Zustandsverwaltung**: 'Target end' und 'Fix Version/s' werden als
      unabhängige Zeitlinien mit jeweils eigenem Zustand behandelt.
    - **Tagesbasierte Konsolidierung**: Alle Änderungen an einem Tag werden zu einem
      einzigen Netto-Ereignis zusammengefasst.
    - **Kontext-Logik für Fix Versions**: Eine 'Fix Version' wird als Zeitraum
      interpretiert. Eine Änderung der 'Fix Version' erzeugt kein 'TIME_CREEP',
      wenn das 'Target end'-Datum innerhalb dieses Zeitraums liegt.
    - **Ignorieren von UNSETs**: Das Leeren eines Datumsfeldes führt zu keinem
      Ereignis und der letzte gültige Termin bleibt für die historische
      Kontinuität erhalten.
    - **Normalisierte Ausgabe**: Die angezeigten 'Fix Version'-Strings werden für
      eine bessere Lesbarkeit auf ihr Kernformat (z.B. 'Q1_25') bereinigt.
    """

    def _normalize_fix_version_string(self, raw_str: str) -> str:
        """
        Extrahiert den kanonischen 'PIxx' oder 'Qx_yy' Teil aus einem String.

        Args:
            raw_str (str): Der ursprüngliche String aus dem Jira-Feld.
                           z.B. 'PrioQ1_25' oder '2025-1_PSB_PI06'.

        Returns:
            str: Der bereinigte String, z.B. 'Q1_25' oder 'PI06', oder der
                 Originalstring, wenn kein Muster passt.
        """
        if not raw_str:
            return raw_str

        # Suche zuerst nach dem spezifischeren PI-Muster
        pi_match = re.search(r'(PI\d+)', raw_str)
        if pi_match:
            return pi_match.group(1)

        # Suche danach nach dem Quartals-Muster
        q_match = re.search(r'(Q\d_\d{2})', raw_str)
        if q_match:
            return q_match.group(1)

        return raw_str # Fallback, falls kein Muster erkannt wird

    def _parse_any_date_string(self, date_str: str) -> tuple[date, date] | None:
        """
        Parst ein Datum aus verschiedenen Jira-Formaten.

        Gibt das Datum als (start, end) Zeitraum-Tupel zurück, um eine konsistente
        Datenstruktur für alle Datumsfelder zu gewährleisten. Für ein einzelnes
        Datum sind Start- und End-Datum identisch.

        Args:
            date_str (str): Der Datumsstring aus Jira.

        Returns:
            tuple[date, date] | None: Ein Tupel mit Start- und End-Datum oder None.
        """
        if not date_str: return None
        parsed_date = None
        try:
            # Standard ISO-Format
            parsed_date = datetime.fromisoformat(date_str).date()
        except ValueError:
            try:
                # Benutzerdefiniertes Format wie 'New:dd/Mon/YYYY'
                cleaned_str = date_str.split(':')[-1].strip()
                parsed_date = datetime.strptime(cleaned_str, '%d/%b/%Y').date()
            except (ValueError, IndexError):
                logger.warning(f"Konnte Datum nicht aus String parsen: '{date_str}'")

        return (parsed_date, parsed_date) if parsed_date else None

    def _parse_fix_version_to_date(self, version_string: str) -> tuple[date, date] | None:
        """
        Wandelt eine 'Fix Version' (PI oder Quartal) in einen exakten Zeitraum um.

        Args:
            version_string (str): Der String der Fix Version, z.B. 'PI29' oder 'Q1_25'.

        Returns:
            tuple[date, date] | None: Ein Tupel mit dem Start- und End-Datum des
                                      entsprechenden Quartals oder None.
        """
        if not version_string: return None

        year, quarter = None, None

        # Logik für Program Increments (PI)
        pi_match = re.search(r'PI(\d+)', version_string)
        if pi_match:
            pi_number = int(pi_match.group(1))
            # Referenzpunkt: PI27 wird als Q1/2025 angenommen
            base_pi_for_q1, base_year_short = 27, 25
            pi_offset = pi_number - base_pi_for_q1
            year_offset = pi_offset // 4
            quarter = (pi_offset % 4) + 1
            year = 2000 + base_year_short + year_offset
        else:
            # Fallback-Logik für Quartale (Q)
            q_match = re.search(r'Q(\d)_(\d{2})', version_string)
            if q_match:
                quarter, year_short = map(int, q_match.groups())
                year = 2000 + year_short

        if year and quarter:
            start_month = (quarter - 1) * 3 + 1
            end_month = start_month + 2
            # Korrekten letzten Tag des Monats bestimmen (Schaltjahre berücksichtigt)
            end_day = 31 if end_month in [1, 3, 5, 7, 8, 10, 12] else (30 if end_month in [4, 6, 9, 11] else (29 if year % 4 == 0 else 28))
            start_date = date(year, start_month, 1)
            end_date = date(year, end_month, end_day)
            return (start_date, end_date)

        return None

    def _compare_dates(self, issue_key, field, old_date, new_date, old_value_str, new_value_str):
        """
        Vergleicht zwei Daten, klassifiziert die Änderung und erstellt ein Event-Dictionary.

        Die Funktion formatiert die Ausgabe-Details kontextabhängig: Für 'Fix Version/s'
        werden die sprechenden Namen (z.B. 'Q1_25') verwendet, für 'Target end'
        die exakten Daten.

        Args:
            issue_key (str): Der Key des betroffenen Issues.
            field (str): Das betroffene Feld ('Target end' oder 'Fix Version/s').
            old_date (date): Das vorherige Datum.
            new_date (date): Das neue Datum.
            old_value_str (str): Der ursprüngliche Text des alten Wertes.
            new_value_str (str): Der ursprüngliche Text des neuen Wertes.

        Returns:
            dict | None: Ein Dictionary, das das Ereignis beschreibt, oder None.
        """
        event_type, details = None, ""

        # Wähle den anzuzeigenden Wert: Original-Text für Fix Version, sonst das Datum.
        if field == 'Fix Version/s':
            old_display = old_value_str if old_value_str else "None"
            new_display = new_value_str if new_value_str else "None"
        else:
            old_display = old_date.strftime('%Y-%m-%d') if old_date else "None"
            new_display = new_date.strftime('%Y-%m-%d') if new_date else "None"

        if old_date is None and new_date is not None:
            event_type, details = "TIME_SET", f"Termin '{field}' gesetzt auf: {new_display}"
        elif old_date is not None and new_date is None:
            # Das Leeren eines Datums wird ignoriert und erzeugt kein Event mehr.
            pass
        elif old_date is not None and new_date is not None and new_date != old_date:
            if new_date > old_date:
                event_type, details = "TIME_CREEP", f"Termin '{field}' verschoben von {old_display} auf {new_display}"
            else:
                event_type, details = "TIME_PULL_IN", f"Termin '{field}' vorgezogen von {old_display} auf {new_display}"

        return {"issue": issue_key, "event_type": event_type, "details": details} if event_type else None

    def analyze(self, data_provider: ProjectDataProvider) -> nx.DiGraph:
        """
        Führt die Hauptanalyse der Terminänderungen durch.

        Diese Methode orchestriert den gesamten Prozess, von der Datenaufbereitung
        über die zustandsbasierte, tagesweise Analyse bis hin zum Anhängen der
        Ergebnisse an den Issue-Graphen.

        Args:
            data_provider (ProjectDataProvider): Das Objekt, das alle Projektdaten
                                                 (Issues, Aktivitäten) bereitstellt.

        Returns:
            nx.DiGraph: Der `issue_tree`-Graph, bei dem relevante Knoten um das
                        Attribut `time_creep_events` mit einer Liste von
                        Ereignissen ergänzt wurden.
        """
        issue_tree = data_provider.issue_tree
        all_activities = data_provider.all_activities
        issue_details = data_provider.issue_details
        ALLOWED_TYPES = {'Business Epic', 'Portfolio Epic', 'Initiative', 'Epic'}
        ALLOWED_FIELDS = {'Target end', 'Fix Version/s'}

        # 1. Alle Aktivitäten pro Issue gruppieren
        activities_by_issue = {}
        for activity in all_activities:
            key = activity.get('issue_key')
            if key:
                activities_by_issue.setdefault(key, []).append(activity)

        # 2. Jedes Issue einzeln verarbeiten
        for issue_key, issue_activities in activities_by_issue.items():
            if issue_details.get(issue_key, {}).get('type') not in ALLOWED_TYPES or not issue_tree.has_node(issue_key):
                continue

            # Nur relevante Aktivitäten filtern und chronologisch sortieren
            relevant_activities = sorted([a for a in issue_activities if a.get('feld_name') in ALLOWED_FIELDS], key=lambda x: x['zeitstempel_iso'])
            if not relevant_activities: continue

            # Das Erstellungsdatum des Issues ist der Zeitstempel der allerersten Aktivität
            creation_date_str = min(act['zeitstempel_iso'] for act in issue_activities)[:10]

            # Alle relevanten Aktivitäten des Issues nach Tagen gruppieren
            activities_by_day = OrderedDict()
            for activity in relevant_activities:
                activities_by_day.setdefault(activity['zeitstempel_iso'][:10], []).append(activity)

            events = []
            # Pro Feld wird der Zustand als (normalisierter_string, zeitraum_tuple) gespeichert
            current_known_states = {'Target end': None, 'Fix Version/s': None}

            # 3. Tagesbasierte, zustandsorientierte Analyse
            for day_str, daily_activities in activities_by_day.items():
                # Finde die letzte relevante Aktivität für jedes Feld an diesem Tag
                last_activities = {f: next((a for a in reversed(daily_activities) if a.get('feld_name') == f), None) for f in ALLOWED_FIELDS}

                # Verarbeite jedes Feld ('Target end', 'Fix Version/s') an diesem Tag unabhängig
                for field, activity in last_activities.items():
                    if not activity: continue

                    raw_new_str = activity.get('neuer_wert')
                    parse_func = self._parse_any_date_string if field == 'Target end' else self._parse_fix_version_to_date
                    new_range = parse_func(raw_new_str)

                    old_state = current_known_states[field]
                    # Am Erstellungstag ist der vorherige Zustand immer 'None'
                    start_of_day_state = None if day_str == creation_date_str else old_state

                    event_data = None
                    raw_old_str = start_of_day_state[0] if start_of_day_state else None

                    # Normalisiere die Strings für eine saubere Ausgabe
                    norm_new_str = self._normalize_fix_version_string(raw_new_str)
                    norm_old_str = self._normalize_fix_version_string(raw_old_str)

                    old_range = start_of_day_state[1] if start_of_day_state else None
                    old_end_date = old_range[1] if old_range else None
                    new_end_date = new_range[1] if new_range else None

                    # 4. Kernlogik: Entscheide, ob ein Event generiert werden soll
                    if field == 'Fix Version/s':
                        target_end_state = current_known_states['Target end']
                        target_end_date = target_end_state[1][1] if target_end_state else None

                        # Kontext-Check: Kein Event, wenn Target End in Fix Version liegt
                        if new_range and target_end_date and new_range[0] <= target_end_date <= new_range[1]:
                            pass
                        else: # Ansonsten normal vergleichen
                            if old_end_date != new_end_date:
                                event_data = self._compare_dates(issue_key, field, old_end_date, new_end_date, norm_old_str, norm_new_str)
                    else: # Logik für 'Target end' ist immer ein direkter Vergleich
                        if old_end_date != new_end_date:
                            event_data = self._compare_dates(issue_key, field, old_end_date, new_end_date, norm_old_str, norm_new_str)

                    if event_data:
                        event_data['timestamp'] = day_str
                        events.append(event_data)

                    # 5. Zustand aktualisieren: Nur wenn ein neues gültiges Datum gesetzt wurde
                    if new_range is not None:
                        current_known_states[field] = (norm_new_str, new_range)
                    # Ansonsten wird der alte Zustand beibehalten (ignoriert UNSET)

            # 6. Ergebnisse an den Graphen anhängen
            if events:
                events.sort(key=lambda x: x['timestamp'])
                issue_tree.nodes[issue_key]['time_creep_events'] = events

        return issue_tree
