# -*- coding: utf-8 -*-
"""
Führt eine Scope- und Status-Analyse für Jira Business Epics durch.

Dieses Skript identifiziert relevante Business Epics aus einem lokalen
JSON-Datensatz, analysiert deren Umfang sowie Status-Laufzeiten, schreibt
die detaillierten Ergebnisse in eine CSV-Datei, gibt eine statistische
Zusammenfassung aus und erstellt Scatter-Plots inklusive Trendlinien und R²-Wert.
"""

import os
import json
import csv
import time
from typing import List, Dict, Any
import sys
import pandas as pd
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import numpy as np

# Fügt das Projekt-Root-Verzeichnis zum Python-Pfad hinzu
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Importiert notwendige Klassen aus dem Projekt
from utils.project_data_provider import ProjectDataProvider
from features.scope_analyzer import ScopeAnalyzer
from features.status_analyzer import StatusAnalyzer
from utils.logger_config import logger
from utils.config import JIRA_ISSUES_DIR, JIRA_TREE_FULL

# --- Globale Konfigurationen ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_CSV_FILE = os.path.join(BASE_DIR, 'scope_and_status_analysis_results.csv')


def load_and_filter_business_epics(target_statuses: List[str]) -> List[str]:
    # Unverändert
    filtered_epic_keys = []
    resolutions_to_skip = {'Withdrawn', 'Rejected'}
    logger.info(f"Durchsuche Verzeichnis: {JIRA_ISSUES_DIR}")
    if not os.path.isdir(JIRA_ISSUES_DIR):
        logger.error(f"Fehler: Das Verzeichnis '{JIRA_ISSUES_DIR}' wurde nicht gefunden.")
        return []
    for filename in os.listdir(JIRA_ISSUES_DIR):
        if not filename.endswith('.json'):
            continue
        file_path = os.path.join(JIRA_ISSUES_DIR, filename)
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if data.get('issue_type') == 'Business Epic':
                status = data.get('status')
                resolution = data.get('resolution')
                if status in target_statuses:
                    if status == "Closed" and resolution in resolutions_to_skip:
                        continue
                    filtered_epic_keys.append(data.get('key'))
        except Exception as e:
            logger.error(f"Fehler bei der Verarbeitung von {filename}: {e}")
    logger.info(f"{len(filtered_epic_keys)} Business Epics mit Status {target_statuses} zur Analyse gefunden.")
    return filtered_epic_keys


def write_results_to_csv(results: List[Dict[str, Any]], file_path: str):
    # Unverändert
    if not results:
        logger.warning("Keine Ergebnisse zum Schreiben in die CSV-Datei vorhanden.")
        return
    fieldnames_set = set()
    for row in results:
        fieldnames_set.update(row.keys())
    fieldnames = sorted(list(fieldnames_set))
    if 'business_epic_key' in fieldnames:
        fieldnames.remove('business_epic_key')
        fieldnames.insert(0, 'business_epic_key')
    try:
        with open(file_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames, extrasaction='ignore')
            writer.writeheader()
            for row in results:
                processed_row = {}
                for key, value in row.items():
                    if isinstance(value, (dict, list)):
                        processed_row[key] = json.dumps(value)
                    else:
                        processed_row[key] = value
                processed_row.pop('epic_breakdown', None)
                writer.writerow(processed_row)
        logger.info(f"Analyseergebnisse erfolgreich in '{file_path}' gespeichert.")
    except Exception as e:
        logger.error(f"Fehler beim Schreiben der CSV-Datei: {e}")


def print_quartile_analysis(results: List[Dict[str, Any]]):
    # Unverändert
    if not results:
        logger.info("Keine Daten für die statistische Analyse vorhanden.")
        return
    df = pd.DataFrame(results)
    columns_to_analyze = ['total_epics_found', 'total_stories_found', 'coding_duration_days']
    columns_to_analyze = [col for col in columns_to_analyze if col in df.columns]
    if not columns_to_analyze:
        logger.warning("Die für die Analyse benötigten Spalten wurden in den Ergebnissen nicht gefunden.")
        return
    print("\n" + "="*50)
    print("      Statistische Analyse der Ergebnisse")
    print("="*50)
    analysis = df[columns_to_analyze].describe(percentiles=[.25, .5, .75, .90])
    analysis = analysis.drop(['mean', 'std', 'min', 'max'])
    analysis_rounded = analysis.round(0).astype(int)
    print(analysis_rounded)
    print("="*50 + "\n")


# AKTUALISIERTE FUNKTION zum Erstellen der Plots mit R²
def create_scatter_plots(results: List[Dict[str, Any]]):
    """
    Erstellt und speichert zwei Scatter-Plots inklusive einer Regressionsgeraden
    und dem Bestimmtheitsmaß R².
    """
    logger.info("Erstelle Scatter-Plots mit Regressionsgeraden und R²-Werten...")
    if not results:
        logger.warning("Keine Daten zum Erstellen der Scatter-Plots vorhanden.")
        return

    df = pd.DataFrame(results)
    df_plottable = df.dropna(subset=['coding_duration_days', 'total_epics_found', 'total_stories_found'])

    if df_plottable.empty:
        logger.warning("Keine vollständigen Daten für die Plots gefunden (coding_duration, epics, stories).")
        return

    # --- Plot 1: Epics vs. Dauer ---
    try:
        plt.figure(figsize=(10, 6))
        y1 = df_plottable['coding_duration_days']
        x1 = df_plottable['total_epics_found']
        plt.xlim(right=25)

        plt.scatter(x1, y1, alpha=0.7, label='Business Epics')

        m1, b1 = np.polyfit(x1, y1, 1)

        # R²-Wert berechnen
        y1_pred = m1 * x1 + b1
        ss_res1 = np.sum((y1 - y1_pred)**2)
        ss_tot1 = np.sum((y1 - np.mean(y1))**2)
        r2_1 = 1 - (ss_res1 / ss_tot1)

        plt.plot(x1, m1*x1 + b1, color='red', linewidth=2, label=f'Trendlinie (y={m1:.2f}x + {b1:.2f})')

        # Titel mit R²-Wert aktualisieren
        plt.title(f'Anzahl technischer Epics vs. Coding-Dauer (R² = {r2_1:.2f})')
        plt.ylabel('Coding-Dauer [Tage]')
        plt.xlabel('Anzahl gefundener technischer Epics')
        plt.grid(True, which='both', linestyle='--', linewidth=0.5)
        plt.legend()

        plot_filename_1 = os.path.join(BASE_DIR, 'epics_vs_duration_scatter.png')
        plt.savefig(plot_filename_1)
        plt.close()
        logger.info(f"Scatter-Plot gespeichert: {plot_filename_1}")
    except Exception as e:
        logger.error(f"Fehler beim Erstellen des 'Epics vs. Dauer'-Plots: {e}")

    # --- Plot 2: Stories vs. Dauer ---
    try:
        plt.figure(figsize=(10, 6))
        y2 = df_plottable['coding_duration_days']
        x2 = df_plottable['total_stories_found']
        plt.xlim(right=150)

        plt.scatter(x2, y2, alpha=0.7, label='Business Epics')

        m2, b2 = np.polyfit(x2, y2, 1)

        # R²-Wert berechnen
        y2_pred = m2 * x2 + b2
        ss_res2 = np.sum((y2 - y2_pred)**2)
        ss_tot2 = np.sum((y2 - np.mean(y2))**2)
        r2_2 = 1 - (ss_res2 / ss_tot2)

        plt.plot(x2, m2*x2 + b2, color='red', linewidth=2, label=f'Trendlinie (y={m2:.2f}x + {b2:.2f})')

        # Titel mit R²-Wert aktualisieren
        plt.title(f'Anzahl Stories vs. Coding-Dauer (R² = {r2_2:.2f})')
        plt.ylabel('Coding-Dauer [Tage]')
        plt.xlabel('Anzahl gefundener Stories')
        plt.grid(True, which='both', linestyle='--', linewidth=0.5)
        plt.legend()

        plot_filename_2 = os.path.join(BASE_DIR, 'stories_vs_duration_scatter.png')
        plt.savefig(plot_filename_2)
        plt.close()
        logger.info(f"Scatter-Plot gespeichert: {plot_filename_2}")
    except Exception as e:
        logger.error(f"Fehler beim Erstellen des 'Stories vs. Dauer'-Plots: {e}")


def main():
    # Unverändert
    start_time = time.time()
    logger.info("Starte die Scope- und Status-Analyse für Business Epics.")

    target_statuses = ["In Progress", "Closed"]
    epics_to_analyze = load_and_filter_business_epics(target_statuses)
    if not epics_to_analyze:
        logger.info("Keine passenden Business Epics für die Analyse gefunden. Programm wird beendet.")
        return

    all_analysis_results = []
    scope_analyzer = ScopeAnalyzer()
    status_analyzer = StatusAnalyzer()
    for i, epic_key in enumerate(epics_to_analyze):
        logger.info(f"--- Verarbeite Epic {i+1}/{len(epics_to_analyze)}: {epic_key} ---")
        try:
            data_provider = ProjectDataProvider(epic_id=epic_key, hierarchy_config=JIRA_TREE_FULL)
            if not data_provider.is_valid():
                logger.warning(f"Überspringe Epic {epic_key}, da kein gültiger Daten-Provider erstellt werden konnte.")
                continue

            scope_result = scope_analyzer.analyze(data_provider)
            status_result = status_analyzer.analyze(data_provider)

            epic_status_durations_days = {
                status: round(duration.total_seconds() / (24 * 3600), 2)
                for status, duration in status_result.get('epic_status_durations', {}).items()
            }
            coding_start = status_result.get('coding_start_time')
            coding_end = status_result.get('coding_end_time')
            coding_duration_days = None
            if coding_start and coding_end:
                try:
                    start_dt = datetime.fromisoformat(coding_start)
                    end_dt = datetime.fromisoformat(coding_end)
                    duration_td = end_dt - start_dt
                    if duration_td.total_seconds() >= 0:
                         coding_duration_days = round(duration_td.total_seconds() / (24 * 3600), 2)
                except (ValueError, TypeError):
                    logger.warning(f"Konnte Coding-Dauer für Epic {epic_key} nicht berechnen.")

            combined_result = {**scope_result}
            combined_result['business_epic_key'] = epic_key
            combined_result['coding_start_time'] = coding_start
            combined_result['coding_end_time'] = coding_end
            combined_result['coding_duration_days'] = coding_duration_days
            combined_result['epic_status_durations'] = epic_status_durations_days

            all_analysis_results.append(combined_result)
        except Exception as e:
            logger.error(f"Ein unerwarteter Fehler ist bei der Analyse von {epic_key} aufgetreten: {e}", exc_info=True)

    write_results_to_csv(all_analysis_results, OUTPUT_CSV_FILE)

    results_for_analysis = [
        result for result in all_analysis_results
        if result.get('total_stories_found', 0) > 0
    ]
    logger.info(
        f"Für die Quartilsanalyse werden {len(results_for_analysis)} von "
        f"{len(all_analysis_results)} Business Epics berücksichtigt (gefiltert nach > 0 User Stories)."
    )

    print_quartile_analysis(results_for_analysis)

    create_scatter_plots(results_for_analysis)

    duration = time.time() - start_time
    logger.info(f"Analyse abgeschlossen. Gesamtdauer: {duration:.2f} Sekunden.")


if __name__ == "__main__":
    main()
