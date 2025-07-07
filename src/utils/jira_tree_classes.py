# src/utils/jira_tree_classes.py
"""
Module for building, visualizing, and processing JIRA issue relationship trees.
This module provides functionality to construct, visualize, and generate context from
JIRA issue trees based on 'realized_by' relationships.
"""

import json
import os
import networkx as nx
import matplotlib.pyplot as plt
from pathlib import Path
import glob
from collections import defaultdict
import matplotlib.patches as mpatches
from utils.logger_config import logger
from utils.config import JIRA_ISSUES_DIR, ISSUE_TREES_DIR, JSON_SUMMARY_DIR, LOGS_DIR


class JiraTreeGenerator:
    """
    Generates NetworkX graphs from JIRA issues, filtered by specific hierarchy types.
    Builds directed graphs representing JIRA issue hierarchies based on
    'realized_by' relationships, but only includes allowed issue types
    (e.g., Epics, Initiatives) to maintain a clean hierarchical structure.
    """

    def __init__(self, json_dir=JIRA_ISSUES_DIR):
        """Initializes the JiraTreeGenerator.

        Args:
            json_dir (str): Directory containing the JSON files for Jira issues.
        """
        self.json_dir = json_dir
        # ANPASSUNG: Definieren der erlaubten Issue-Typen für die Hierarchie
        self.ALLOWED_HIERARCHY_TYPES = {'Business Initiative', 'Business Epic', 'Portfolio Epic', 'Epic'}

    def read_jira_issue(self, file_path):
        """Reads a Jira issue from a JSON file."""
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                return json.load(file)
        except FileNotFoundError:
            logger.error(f"Warning: File {file_path} not found")
            return None
        except json.JSONDecodeError:
            logger.error(f"Error: File {file_path} contains invalid JSON")
            return None

    def find_json_for_key(self, key):
        """Finds the JSON file for a specific Jira key."""
        exact_path = os.path.join(self.json_dir, f"{key}.json")
        if os.path.exists(exact_path):
            return exact_path
        json_files = glob.glob(os.path.join(self.json_dir, "*.json"))
        for file_path in json_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as file:
                    data = json.load(file)
                    if data.get("key") == key:
                        return file_path
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
        return None

    def build_issue_tree(self, root_key):
        """Builds a directed graph from Jira issues, filtering by allowed types.

        Args:
            root_key (str): The key of the root issue.

        Returns:
            nx.DiGraph or None: A directed graph representing the filtered tree
                                structure, or None if an error occurs.
        """
        logger.info(f"Building issue tree for root issue: {root_key}")
        G = nx.DiGraph()
        file_path = self.find_json_for_key(root_key)
        if not file_path:
            logger.error(f"Error: No JSON file found for root key {root_key}")
            return None

        root_data = self.read_jira_issue(file_path)
        if not root_data:
            logger.error(f"Error: The JSON file for root key {root_key} could not be read")
            return None

        # ANPASSUNG: Prüfung, ob der Root-Issue selbst ein erlaubter Typ ist
        root_issue_type = root_data.get('issue_type', '')
        if root_issue_type not in self.ALLOWED_HIERARCHY_TYPES:
            logger.error(f"Error: Root issue {root_key} is of type '{root_issue_type}', which is not allowed in the hierarchy. Aborting tree build.")
            return None

        G.add_node(root_key, **root_data)
        visited = set()

        def _add_children(parent_key):
            """Recursive helper to add children, respecting the type filter."""
            if parent_key in visited:
                return
            visited.add(parent_key)

            parent_data = G.nodes[parent_key]
            if 'realized_by' not in parent_data or not parent_data['realized_by']:
                return

            for child in parent_data['realized_by']:
                child_key = child['key']
                child_file_path = self.find_json_for_key(child_key)

                if not child_file_path:
                    logger.warning(f"Skipping child {child_key}: JSON file not found.")
                    continue

                child_data = self.read_jira_issue(child_file_path)
                if not child_data:
                    logger.warning(f"Skipping child {child_key}: JSON file could not be read.")
                    continue

                # ANPASSUNG: Füge den Child-Knoten nur hinzu, wenn sein Typ erlaubt ist
                child_issue_type = child_data.get('issue_type', '')
                if child_issue_type in self.ALLOWED_HIERARCHY_TYPES:
                    G.add_node(child_key, **child_data)
                    G.add_edge(parent_key, child_key)
                    _add_children(child_key) # Rekursion nur für gültige Kinder
                else:
                    logger.info(f"Skipping issue {child_key} of type '{child_issue_type}' - not an allowed hierarchy type.")

        _add_children(root_key)

        if G.number_of_nodes() <= 1 and not root_data.get('realized_by'):
            logger.info(f"Warning: The root issue {root_key} has no 'realized_by' entries")

        logger.info(f"Filtered tree built. Number of nodes: {G.number_of_nodes()}")
        return G


class JiraTreeVisualizer:
    """Class for visualizing a Jira issue tree graph."""
    # ... (Rest dieser Klasse bleibt unverändert)
    def __init__(self, output_dir=ISSUE_TREES_DIR, format='png'):
        self.output_dir = output_dir
        self.format = format
        self.status_colors = {'Funnel': 'lightgray', 'Backlog for Analysis': 'lightgray', 'Analysis': 'lemonchiffon', 'Backlog': 'lemonchiffon', 'Review': 'lemonchiffon', 'Waiting': 'lightblue', 'In Progress': 'lightgreen', 'Deployment': 'lightgreen', 'Validation': 'lightgreen', 'Resolved': 'green', 'Closed': 'green'}

    def _determine_node_size_and_font(self, G):
        if G.number_of_nodes() > 20: return 2000, 8, (20, 12)
        elif G.number_of_nodes() > 10: return 3000, 8, (16, 12)
        else: return 4000, 9, (12, 12)

    def visualize(self, G, root_key, output_file=None):
        if G is None or not isinstance(G, nx.DiGraph) or G.number_of_nodes() <= 1:
            if G is None or not isinstance(G, nx.DiGraph): logger.error("Error: Invalid graph provided.")
            else: logger.info(f"Warning: The graph contains only the root node {root_key}.")
            return False

        if output_file is None:
            os.makedirs(self.output_dir, exist_ok=True)
            output_file = os.path.join(self.output_dir, f"{root_key}_issue_tree.{self.format}")

        pos = nx.nx_agraph.graphviz_layout(G, prog='dot')
        NODE_SIZE, FONT_SIZE, figure_size = self._determine_node_size_and_font(G)
        plt.figure(figsize=figure_size)

        nodes_by_status = defaultdict(list)
        for node, attrs in G.nodes(data=True):
            nodes_by_status[attrs.get('status', '')].append(node)

        for status, nodes in nodes_by_status.items():
            nx.draw_networkx_nodes(G, pos, nodelist=nodes, node_size=NODE_SIZE, node_color=self.status_colors.get(status, 'peachpuff'), alpha=0.8)

        labels = {}
        for node, attrs in G.nodes(data=True):
            fix_versions = attrs.get('fix_versions', [])
            fix_versions_string = "\n".join(fix_versions) if isinstance(fix_versions, list) else str(fix_versions)
            labels[node] = f"{node.split('-')[0]}-\n{node.split('-')[1]}\n{fix_versions_string}"

        nx.draw_networkx_edges(G, pos, width=1.0, alpha=0.5, arrows=True, arrowstyle='->', arrowsize=15)
        nx.draw_networkx_labels(G, pos, labels=labels, font_size=FONT_SIZE, font_family='sans-serif', verticalalignment='center')

        legend_patches = [mpatches.Patch(color=color, label=status) for status, color in self.status_colors.items() if status and any(node for node in nodes_by_status.get(status, []))]
        plt.legend(handles=legend_patches, loc='upper right', title='Status')

        title = G.nodes[list(G.nodes())[0]].get("title", '')
        plt.title(f"{root_key} Jira Hierarchy\n{title}", fontsize=16)
        plt.axis('off')

        try:
            plt.tight_layout()
            plt.savefig(output_file, dpi=100, bbox_inches='tight')
            plt.close()
            logger.info(f"Issue Tree saved: {output_file}")
            return True
        except Exception as e:
            logger.error(f"Error saving visualization: {e}")
            return False


class JiraContextGenerator:
    """Class for generating structured context data from JIRA issue trees for AI processing."""
    # ... (Rest dieser Klasse bleibt unverändert)
    def __init__(self, output_dir=JSON_SUMMARY_DIR):
        self.output_dir = output_dir

    def generate_context(self, G, root_key, output_file=None):
        if G is None or not isinstance(G, nx.DiGraph):
            logger.error("Error: Invalid graph provided.")
            return "{}"
        if root_key not in G:
            logger.error(f"Error: Root node {root_key} not found in the graph.")
            return "{}"

        issues_data = []
        for node in nx.bfs_tree(G, source=root_key):
            node_attrs = G.nodes[node]
            issue_data = {"key": node, "title": node_attrs.get('title', 'No title'), "issue_type": node_attrs.get('issue_type', 'Unknown'), "status": node_attrs.get('status', 'Unknown')}

            # Add optional fields
            for field in ['assignee', 'priority', 'target_start', 'target_end', 'description']:
                if value := node_attrs.get(field): issue_data[field] = value

            if fix_versions := node_attrs.get('fix_versions'):
                issue_data["fix_versions"] = fix_versions if isinstance(fix_versions, list) else str(fix_versions).split(', ')

            if business_value := node_attrs.get('business_value', {}):
                issue_data["business_value"] = business_value # Assuming structure is fine

            if acceptance_criteria := node_attrs.get('acceptance_criteria', []):
                issue_data["acceptance_criteria"] = acceptance_criteria if isinstance(acceptance_criteria, list) else [acceptance_criteria]

            if realized_by := node_attrs.get('realized_by', []):
                issue_data["realized_by"] = [{"key": child.get('key', 'Unknown'), **({k: v for k, v in child.items() if k != 'key'})} for child in realized_by]

            if predecessors := list(G.predecessors(node)):
                issue_data["realizes"] = [{"key": parent, "title": G.nodes[parent].get('title', 'No title')} for parent in predecessors]

            issues_data.append(issue_data)

        context_json = {"root": root_key, "issues": issues_data}
        json_str = json.dumps(context_json, indent=2, ensure_ascii=False)

        context_file = os.path.join(LOGS_DIR, f"{root_key}_context.json")
        with open(context_file, 'w', encoding='utf-8') as file:
            file.write(json_str)
            logger.info(f"Context saved to file: {context_file}")

        return json_str
