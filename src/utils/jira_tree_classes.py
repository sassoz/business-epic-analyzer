"""
Module for building, visualizing, and processing JIRA issue relationship trees.

This module provides functionality to construct, visualize, and generate context from
JIRA issue trees based on 'realized_by' relationships. It leverages NetworkX for graph
representation and Matplotlib for visualization of issue hierarchies.

The module contains three main classes:
- JiraTreeGenerator: Builds directed graphs from JIRA issues and their relationships
- JiraTreeVisualizer: Creates visual representations of issue trees with status coloring
- JiraContextGenerator: Extracts structured context data from issue trees for AI processing

Key features:
- Graph-based representation of issue relationships
- Color-coded visualizations based on issue status
- Hierarchical tree layouts using Graphviz
- JSON context generation for AI processing
- Support for deep issue hierarchies and relationship traversal
- Comprehensive metadata extraction from issue attributes
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
    Class for generating NetworkX graphs from JIRA issues and their relationships.

    This class builds directed graphs representing JIRA issue hierarchies based on
    'realized_by' relationships. It reads issue data from JSON files, establishes
    parent-child relationships, and constructs a complete graph representation that
    preserves all issue attributes and relationships.

    The generator handles recursive traversal of issue hierarchies, maintaining the
    full metadata of each issue node including title, status, type, descriptions,
    business value data, and temporal information. It implements cycle detection to
    prevent infinite recursion in complex relationship networks.

    Key features:
    - Builds directed graphs from JSON issue data
    - Preserves all issue attributes as node properties
    - Handles recursive traversal of 'realized_by' relationships
    - Supports flexible JSON file location and naming conventions
    - Implements robust error handling for missing or invalid files
    - Provides detailed logging of graph construction process

    The resulting graph structure is suitable for visualization, analysis, and
    context generation for AI-powered summaries.
    """

    def __init__(self, json_dir=JIRA_ISSUES_DIR):
        """
        Initialize the JiraTreeGenerator.

        Args:
            json_dir (str): Directory containing JSON files
        """
        self.json_dir = json_dir

    def read_jira_issue(self, file_path):
        """
        Read a Jira issue from a JSON file.

        Args:
            file_path (str): Path to the JSON file

        Returns:
            dict: The JSON data of the Jira issue
        """
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
        """
        Find a JSON file for a specific Jira key.

        Args:
            key (str): The Jira key

        Returns:
            str or None: The found file path or None if no file was found
        """
        # First look for exact match
        exact_path = os.path.join(self.json_dir, f"{key}.json")
        if os.path.exists(exact_path):
            return exact_path

        # If not found, search all JSON files and check content
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
        """
        Build a directed graph from Jira issues based on 'realized_by' relationships.

        Args:
            root_key (str): The key of the root issue

        Returns:
            nx.DiGraph or None: A directed graph representing the tree structure, or None on errors
        """

        logger.info(f"Building issue tree for root issue: {root_key}")
        logger.info(f"Searching JSON files in: {self.json_dir}")

        # Create a directed graph
        G = nx.DiGraph()

        # Check if the root JSON file exists
        file_path = self.find_json_for_key(root_key)
        if not file_path:
            logger.error(f"Error: No JSON file found for root key {root_key}")
            return None

        # Try to read the root JSON file
        root_data = self.read_jira_issue(file_path)
        if not root_data:
            logger.error(f"Error: The JSON file for root key {root_key} could not be read")
            return None

        # Add the root node with all available fields
        G.add_node(
            root_key,
            title=root_data.get('title', ''),
            status=root_data.get('status', ''),
            issue_type=root_data.get('issue_type', ''),
            fix_versions=root_data.get('fix_versions', []),
            description=root_data.get('description', ''),
            acceptance_criteria=root_data.get('acceptance_criteria', []),
            business_value=root_data.get('business_value', {}),
            assignee=root_data.get('assignee', ''),
            target_start=root_data.get('target_start', ''),
            target_end=root_data.get('target_end', ''),
            attachments=root_data.get('attachments', []),
            realized_by=root_data.get('realized_by', [])
        )

        # Dictionary to store already visited nodes (avoids cycles)
        visited = set()

        # Recursive helper function to build the tree
        def _add_children(parent_key):
            if parent_key in visited:
                return

            visited.add(parent_key)
            file_path = self.find_json_for_key(parent_key)

            if not file_path:
                logger.error(f"Warning: No JSON file found for key {parent_key}")
                return

            parent_data = self.read_jira_issue(file_path)

            if not parent_data:
                logger.error(f"Warning: The JSON file for key {parent_key} could not be read")
                return

            if 'realized_by' not in parent_data or not parent_data['realized_by']:
                return

            for child in parent_data['realized_by']:
                child_key = child['key']

                # Try to get more information about the child
                child_file_path = self.find_json_for_key(child_key)
                # Initialize all fields
                title = ""
                status = ""
                issue_type = ""
                fix_versions = []
                description = ""
                acceptance_criteria = []
                business_value = {}
                assignee = ""
                target_start = ""
                target_end = ""
                attachments = []
                realized_by = []

                if child_file_path:
                    child_data = self.read_jira_issue(child_file_path)
                    if child_data:
                        title = child_data.get('title', '')
                        status = child_data.get('status', '')
                        issue_type = child_data.get('issue_type', '')
                        fix_versions = child_data.get('fix_versions', [])
                        description = child_data.get('description', '')
                        acceptance_criteria = child_data.get('acceptance_criteria', [])
                        business_value = child_data.get('business_value', {})
                        assignee = child_data.get('assignee', '')
                        target_start = child_data.get('target_start', '')
                        target_end = child_data.get('target_end', '')
                        attachments = child_data.get('attachments', [])
                        realized_by = child_data.get('realized_by', [])

                G.add_node(
                    child_key,
                    title=title,
                    status=status,
                    issue_type=issue_type,
                    fix_versions=fix_versions,
                    description=description,
                    acceptance_criteria=acceptance_criteria,
                    business_value=business_value,
                    assignee=assignee,
                    target_start=target_start,
                    target_end=target_end,
                    attachments=attachments,
                    realized_by=realized_by
                )

                # Add edge
                G.add_edge(parent_key, child_key)

                # Continue recursively for child node
                _add_children(child_key)

        # Start the recursion
        _add_children(root_key)

        # Check if the graph contains more than just the root node
        if G.number_of_nodes() <= 1 and not root_data.get('realized_by'):
            logger.info(f"Warning: The root issue {root_key} has no 'realized_by' entries")

        # Show graph statistics
        logger.info(f"Number of nodes: {G.number_of_nodes()}")
        logger.info(f"Number of edges: {G.number_of_edges()}")

        return G


class JiraTreeVisualizer:
    """
    Class for visualizing a Jira issue tree graph.
    """

    def __init__(self, output_dir=ISSUE_TREES_DIR, format='png'):
        """
        Initialize the JiraTreeVisualizer.

        Args:
            output_dir (str): Directory to save visualizations
            format (str): Output format (png, svg, pdf)
        """
        self.output_dir = output_dir
        self.format = format

        # Status colors
        self.status_colors = {
            'Funnel': 'lightgray',
            'Backlog for Analysis': 'lightgray',
            'Analysis': 'lightyellow',
            'Backlog': 'lightyellow',
            'Review': 'lightyellow',
            'In Progress': 'lightgreen',
            'Deployment': 'lightgreen',
            'Validation': 'lightgreen',
            'Resolved': 'green',
            'Closed': 'green',
        }

    def _determine_node_size_and_font(self, G):
        """
        Determine appropriate node size and font size based on graph size.

        Args:
            G (nx.DiGraph): The graph

        Returns:
            tuple: (node_size, font_size, figure_size)
        """
        if G.number_of_nodes() > 20:
            return 2000, 8, (20, 12)
        elif G.number_of_nodes() > 10:
            return 3000, 8, (16, 12)
        else:
            return 4000, 9, (12, 12)

    def visualize(self, G, root_key, output_file=None):
        """
        Visualize a graph as a tree diagram and save it as an image.

        Args:
            G (nx.DiGraph): The graph to visualize
            root_key (str): The root key of the graph
            output_file (str): Optional output file path

        Returns:
            bool: True on success, False on error
        """
        if G is None or not isinstance(G, nx.DiGraph):
            logger.error("Error: Invalid graph provided.")
            return False

        if G.number_of_nodes() <= 1:
            logger.info(f"Warning: The graph contains only the root node {root_key}.")
            return False

        # Determine output file path if not provided
        if output_file is None:
            os.makedirs(self.output_dir, exist_ok=True)
            output_file = os.path.join(self.output_dir, f"{root_key}_issue_tree.{self.format}")

        # Hierarchical layout for the tree
        pos = nx.nx_agraph.graphviz_layout(G, prog='dot')

        # Set node size and font size
        NODE_SIZE, FONT_SIZE, figure_size = self._determine_node_size_and_font(G)
        plt.figure(figsize=figure_size)

        # Group nodes by status
        nodes_by_status = defaultdict(list)
        for node, attrs in G.nodes(data=True):
            status = attrs.get('status', '')
            nodes_by_status[status].append(node)

        # Draw nodes grouped by status
        for status, nodes in nodes_by_status.items():
            color = self.status_colors.get(status, 'lightcyan')
            nx.draw_networkx_nodes(G, pos, nodelist=nodes, node_size=NODE_SIZE, node_color=color, alpha=0.8)

        # Create labels with key
        labels = {}
        for node, attrs in G.nodes(data=True):
            node_parts = node.split("-")
            fix_versions = attrs.get('fix_versions', [])

            if isinstance(fix_versions, list):
                fix_versions_string = "\n".join(fix_versions)
            else:
                fix_versions_string = str(fix_versions)

            labels[node] = f"{node_parts[0]}-\n{node_parts[1]}\n{fix_versions_string}"

        # Draw edges
        nx.draw_networkx_edges(G, pos, width=1.0, alpha=0.5, arrows=True, arrowstyle='->', arrowsize=15)

        # Draw labels
        nx.draw_networkx_labels(G, pos, labels=labels, font_size=FONT_SIZE, font_family='sans-serif', verticalalignment='center')

        # Add legend
        legend_patches = []
        for status, color in self.status_colors.items():
            if status and any(node for node in nodes_by_status[status]):  # Only show statuses that appear in the graph
                legend_patches.append(mpatches.Patch(color=color, label=status))

        plt.legend(handles=legend_patches, loc='upper right', title='Status')

        # Add title
        first_node = list(G.nodes())[0]
        node_attrs = G.nodes[first_node]
        title = node_attrs.get("title", '')
        plt.title(f"{first_node} Jira Hierarchy\n{title}", fontsize=16)

        # Remove axes
        plt.axis('off')

        # Save the visualization
        try:
            plt.tight_layout()
            plt.savefig(output_file, dpi=100, bbox_inches='tight')
            plt.close()  # Close the figure to free memory
            logger.info(f"Issue Tree saved: {output_file}")
            return True
        except Exception as e:
            logger.error(f"Error saving visualization: {e}")
            return False


class JiraContextGenerator:
    """
    Class for generating structured context data from JIRA issue trees for AI processing.

    This class extracts and formats data from NetworkX graphs of JIRA issues into a
    structured JSON format optimized for language model processing. It traverses the
    graph in breadth-first order, extracting detailed information about each issue and
    preserving relationship hierarchies.

    The generator handles complex issue metadata including business value metrics,
    acceptance criteria, temporal data, and relationship links. It produces a comprehensive
    JSON representation that includes all relevant business and technical details needed
    for generating summaries and reports.

    Key features:
    - Produces structured JSON formatted for AI consumption
    - Preserves complete issue hierarchies and relationships
    - Processes complex nested attributes like business value metrics
    - Handles breadth-first traversal to maintain logical issue ordering
    - Maps parent-child relationships in both directions
    - Formats temporal and versioning information consistently
    - Creates a complete context model suitable for LLM-based summarization

    The output JSON includes a root identifier and detailed information about all
    connected issues, making it ideal for generating human-readable summaries that
    accurately represent the JIRA issue structure.
    """

    def __init__(self, output_dir=JSON_SUMMARY_DIR):
        """
        Initialize the JiraContextGenerator.

        Args:
            output_dir (str): Directory to save context files
        """
        self.output_dir = output_dir

    def generate_context(self, G, root_key, output_file=None):
        """
        Generate context as JSON from a graph and optionally save it to a file.

        Args:
            G (nx.DiGraph): The graph
            root_key (str): The root key of the graph
            output_file (str): Optional output file path

        Returns:
            str: The generated context as JSON string
        """
        if G is None or not isinstance(G, nx.DiGraph):
            logger.error("Error: Invalid graph provided.")
            return "{}"

        if root_key not in G:
            logger.error(f"Error: Root node {root_key} not found in the graph.")
            return "{}"

        # Create a list to hold all the issue data
        issues_data = []

        # Process nodes in a BFS manner to maintain hierarchy
        for node in nx.bfs_tree(G, source=root_key):
            node_attrs = G.nodes[node]

            # Create a dictionary for this issue
            issue_data = {
                "key": node,
                "title": node_attrs.get('title', 'No title'),
                "issue_type": node_attrs.get('issue_type', 'Unknown'),
                "status": node_attrs.get('status', 'Unknown')
            }

            # Add optional fields if they exist
            if assignee := node_attrs.get('assignee'):
                issue_data["assignee"] = assignee

            if priority := node_attrs.get('priority'):
                issue_data["priority"] = priority

            if target_start := node_attrs.get('target_start'):
                issue_data["target_start"] = target_start

            if target_end := node_attrs.get('target_end'):
                issue_data["target_end"] = target_end

            if fix_versions := node_attrs.get('fix_versions'):
                if isinstance(fix_versions, list):
                    issue_data["fix_versions"] = fix_versions
                else:
                    issue_data["fix_versions"] = str(fix_versions).split(', ')

            if description := node_attrs.get('description'):
                issue_data["description"] = description

            # Process business value if available
            if business_value := node_attrs.get('business_value', {}):
                issue_data["business_value"] = {}

                # Business impact
                if 'business_impact' in business_value:
                    bi = business_value['business_impact']
                    issue_data["business_value"]["business_impact"] = {
                        "scale": bi.get('scale', '')
                    }

                    if revenue := bi.get('revenue'):
                        issue_data["business_value"]["business_impact"]["revenue"] = revenue

                    if cost_saving := bi.get('cost_saving'):
                        issue_data["business_value"]["business_impact"]["cost_saving"] = cost_saving

                    if risk_loss := bi.get('risk_loss'):
                        issue_data["business_value"]["business_impact"]["risk_loss"] = risk_loss

                    if justification := bi.get('justification'):
                        issue_data["business_value"]["business_impact"]["justification"] = justification

                # Strategic enablement
                if 'strategic_enablement' in business_value:
                    se = business_value['strategic_enablement']
                    issue_data["business_value"]["strategic_enablement"] = {
                        "scale": se.get('scale', '')
                    }

                    if risk_minimization := se.get('risk_minimization'):
                        issue_data["business_value"]["strategic_enablement"]["risk_minimization"] = risk_minimization

                    if strat_enablement := se.get('strat_enablement'):
                        issue_data["business_value"]["strategic_enablement"]["strat_enablement"] = strat_enablement

                    if justification := se.get('justification'):
                        issue_data["business_value"]["strategic_enablement"]["justification"] = justification

                # Time criticality
                if 'time_criticality' in business_value:
                    tc = business_value['time_criticality']
                    issue_data["business_value"]["time_criticality"] = {
                        "scale": tc.get('scale', '')
                    }

                    if time := tc.get('time'):
                        issue_data["business_value"]["time_criticality"]["time"] = time

                    if justification := tc.get('justification'):
                        issue_data["business_value"]["time_criticality"]["justification"] = justification

            # Add acceptance criteria if available
            if acceptance_criteria := node_attrs.get('acceptance_criteria', []):
                if isinstance(acceptance_criteria, list):
                    issue_data["acceptance_criteria"] = acceptance_criteria
                else:
                    issue_data["acceptance_criteria"] = [acceptance_criteria]

            # Add realized_by information if available
            if realized_by := node_attrs.get('realized_by', []):
                issue_data["realized_by"] = []
                for child in realized_by:
                    child_data = {
                        "key": child.get('key', 'Unknown')
                    }

                    if child_title := child.get('title'):
                        child_data["title"] = child_title

                    if child_summary := child.get('summary'):
                        child_data["summary"] = child_summary

                    issue_data["realized_by"].append(child_data)

            # For non-root nodes, add information about which node it realizes
            predecessors = list(G.predecessors(node))
            if predecessors:
                issue_data["realizes"] = []
                for parent in predecessors:
                    parent_attrs = G.nodes[parent]
                    issue_data["realizes"].append({
                        "key": parent,
                        "title": parent_attrs.get('title', 'No title')
                    })

            # Add this issue to our collection
            issues_data.append(issue_data)

        # Create the final JSON structure
        context_json = {
            "root": root_key,
            "issues": issues_data
        }

        # Convert to JSON string with proper formatting
        json_str = json.dumps(context_json, indent=2, ensure_ascii=False)

        # If an output file is specified, save the context
        #if output_file is None and self.output_dir:
        #    os.makedirs(self.output_dir, exist_ok=True)
        #    output_file = os.path.join(self.output_dir, f"{root_key}_context.json")
        #
        #if output_file:
        #    # Ensure the output directory exists
        #    os.makedirs(os.path.dirname(output_file), exist_ok=True)

        # Write the context to a file
        context_file = os.path.join(LOGS_DIR, f"{root_key}_context.json")
        with open(context_file, 'w', encoding='utf-8') as file:
            file.write(json_str)
            logger.info(f"Context saved to file: {context_file}")

        return json_str
