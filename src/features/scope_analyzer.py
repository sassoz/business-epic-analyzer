# src/features/scope_analyzer.py
import statistics
from src.utils.project_data_provider import ProjectDataProvider

class ScopeAnalyzer:
    """
    Analysiert den Umfang, die Struktur und den Aufwand eines Projekts.

    Diese Klasse berechnet Metriken zur Größe des Projekts, wie z.B. die Anzahl
    der Issues, die Verteilung auf verschiedene Jira-Projekte und die
    Gesamtsumme der Story Points.
    """

    def _clean_status_name(self, raw_name: str) -> str:
        """
        Extrahiert und bereinigt einen Status-Namen aus einem rohen String.

        Args:
            raw_name (str): Der rohe Status-String aus den Aktivitätsdaten.

        Returns:
            str: Der bereinigte, großgeschriebene Status-Name oder 'N/A'.
        """
        if not raw_name: return "N/A"
        if '[' in raw_name:
            try: return raw_name.split(':')[1].split('[')[0].strip().upper()
            except IndexError: return raw_name.strip().upper()
        return raw_name.strip().upper()

    def analyze(self, data_provider: ProjectDataProvider) -> dict:
        """
        Führt eine detaillierte Analyse des Projektumfangs und der Struktur durch.

        Diese Methode ermittelt Kennzahlen wie die Gesamtzahl der Issues, die
        Summe der Story Points und die Verteilung der Arbeit auf verschiedene
        Jira-Projekte und technische Epics.

        Args:
            data_provider (ProjectDataProvider): Ein Objekt, das alle notwendigen,
                vorgeladenen Projektdaten enthält.

        Returns:
            dict: Ein Dictionary mit den Analyseergebnissen, das folgende Schlüssel enthält:
                - 'total_issues' (int): Gesamtzahl aller Issues im Baum.
                - 'total_epics_found' (int): Anzahl der gefundenen technischen Epics.
                - 'total_stories_found' (int): Anzahl der gefundenen Stories.
                - 'total_story_points' (int): Gesamtsumme der Story Points.
                - 'stories_per_epic_counts' (list): Liste mit der Anzahl Stories pro Epic.
                - 'epic_breakdown' (dict): Aufschlüsselung, welches Epic welche Kinder hat.
                - 'project_count' (int): Anzahl der beteiligten Jira-Projekte nach Konsolidierung.
                - 'project_distribution' (dict): Verteilung der Issues auf die vollständigen Projektnamen.
        """
        # Mapping von Projekt-Abkürzung zu vollem Namen basierend auf Jira_Projects.txt
        project_name_map = {
            "MAGBUS": "Magenta Business", "ADCL": "API Decoupling Layer Standard Business",
            "BMC": "Billing Migration Center", "REO": "RechnungOnline", "MAB": "Massenmarkt Billing",
            "PSB": "Prepaid, Partner Services & Billing Hub", "SONAR": "SIRIUS (SONAR/MARS)",
            "BCCR": "Billing, Collection & Credit Risk", "CRMFN": "CRM Festnetz", "B2BCA": "B2B Classic Access",
            "TDGM": "TDG Massmarket (OneX, MAVI, DOT, ...)", "ONEX": "TDG Massmarket (OneX, MAVI, DOT, ...)",
            "CVS": "TDG Massmarket (OneX, MAVI, DOT, ...)", "MABUCPS": "TCMP/MBC Plattform",
            "COSM": "TCMP/MBC Plattform", "TCMPPF": "TCMP/MBC Plattform", "ECC": "TCMP/MBC Plattform",
            "ECCMST": "TCMP/MBC Plattform", "HPBXCC": "TCMP/MBC Plattform", "MOFUDHS": "Mobilfunk DigiHub",
            "OMSOE": "OMS/OE", "CC": "Carmen CRM", "BSP": "Business Service Portal", "DATAFAB": "Data Domain",
            "DATASAT": "Data Domain", "DATAAAA": "Data Domain", "BDI": "Data Domain", "SECEIT": "SeCe-IT",
            "EOS": "Eine Oberfläche Service", "DIGIVLEK": "D!VE", "TVPP": "T-VPP", "TF": "Tariffabrik",
            "SNOWTC": "SNow@TC", "SDX": "SNP Plattform", "SDN": "SNP Plattform", "SDLA": "SNP Plattform",
            "OMS": "SNP Plattform", "SCS": "SAP SCS", "POCONFIG": "Prima+", "ORCA": "Order2Cash",
            "DUD": "David & Doris", "DPM": "Digital Product Mgmt", "DMSDO": "DMS", "DHEI": "Tardis",
            "CANCAFLC": "Copper Access & Fixed Line CRM", "BCT": "B2B Classic TC"
        }

        issue_details = data_provider.issue_details
        issue_tree = data_provider.issue_tree
        root_epic_id = data_provider.epic_id

        total_issues = len(issue_details)

        epic_keys = [k for k, v in issue_details.items() if v.get('type') == 'Epic']
        story_keys = [k for k, v in issue_details.items() if v.get('type') == 'Story']

        epic_breakdown = {}
        if issue_tree:
            for epic_key in epic_keys:
                epic_breakdown[epic_key] = []
                if issue_tree.has_node(epic_key):
                    for child_key in issue_tree.successors(epic_key):
                        child_details = issue_details.get(child_key)
                        if child_details and child_details['type'] in ['Story', 'Bug']:
                                epic_breakdown[epic_key].append({
                                    "key": child_key,
                                    "type": child_details['type'],
                                    "points": child_details.get('points', 0),
                                    "resolution": child_details.get('resolution', 'N/A')
                                })

        total_story_points = sum(v.get('points', 0) for k, v in issue_details.items() if k in story_keys)
        stories_per_epic_counts = [
            len([c for c in epic_breakdown.get(epic_key, []) if c['type'] == 'Story'])
            for epic_key in epic_keys
        ]

        # 1. Zähle Issues pro Projekt-Abkürzung
        project_distribution_abbr = {}
        for key, details in issue_details.items():
            issue_type = details.get('type')
            if key == root_epic_id or issue_type in ['Business Epic', 'Bug']:
                continue
            prefix = key.split('-')[0]
            project_distribution_abbr[prefix] = project_distribution_abbr.get(prefix, 0) + 1

        # 2. Konsolidiere die Zählungen basierend auf dem vollen Projektnamen
        project_distribution_full = {}
        for abbr, count in project_distribution_abbr.items():
            # Finde den vollen Namen; nutze Abkürzung als Fallback
            full_name = project_name_map.get(abbr, abbr)
            project_distribution_full[full_name] = project_distribution_full.get(full_name, 0) + count

        # NEU: 3. Sortiere das Dictionary absteigend nach der Anzahl der Issues
        sorted_project_distribution = dict(sorted(
            project_distribution_full.items(),
            key=lambda item: item[1],
            reverse=True
        ))

        project_count = len(sorted_project_distribution)

        return {
            "total_issues": total_issues,
            "total_epics_found": len(epic_keys),
            "total_stories_found": len(story_keys),
            "total_story_points": total_story_points,
            "stories_per_epic_counts": stories_per_epic_counts,
            "epic_breakdown": epic_breakdown,
            "project_count": project_count,
            "project_distribution": sorted_project_distribution # Rückgabe der konsolidierten Liste
        }
