"""
Module for cleaning up and filtering Story and Task type issues from JIRA data.

This module helps improve data quality by identifying and removing Story and Task
type issues from the JIRA data set. Since Stories and Tasks often represent
implementation details rather than business requirements, they can clutter
the visualization and business analysis.

The module processes JSON files containing JIRA issue data, identifies issues
of type "Story" or "Task", removes references to these issues from other issues'
"realized_by" lists, and optionally deletes the Story/Task JSON files.

This cleanup step helps focus the analysis on the core business requirements and
improves the quality of visualizations and summaries.
"""

import json
import os
import glob
from utils.config import JIRA_ISSUES_DIR

def read_jira_json(file_path):
    """Read a Jira issue JSON file and return the data."""
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            return json.load(file)
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return None

def save_jira_json(file_path, data):
    """Save Jira issue data back to JSON file."""
    try:
        with open(file_path, 'w', encoding='utf-8') as file:
            json.dump(data, file, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Error saving {file_path}: {e}")
        return False

def cleanup_story_issues(json_dir):
    """
    Processes all JSON files in the specified directory to clean up Story/Task issues.

    This function:
    1. Identifies all issues of type "Story" and "Task"
    2. Removes references to these issues from "realized_by" lists in other issues
    3. Deletes the Story/Task JSON files

    This cleanup helps focus on business-oriented issues rather than implementation
    details, improving visualizations and making business analysis clearer.

    Args:
        json_dir (str): Directory containing JIRA issue JSON files

    Returns:
        None
    """

    # Step 1: Load all JSON files and identify Story issues
    all_files = glob.glob(os.path.join(json_dir, "*.json"))
    issues_data = {}
    story_keys = []

    for file_path in all_files:
        data = read_jira_json(file_path)
        if data:
            key = data.get("key")
            if key:
                issues_data[key] = {
                    "path": file_path,
                    "data": data,
                    "issue_type": data.get("issue_type", "")
                }
                if (data.get("issue_type") == "Story") or (data.get("issue_type") == "Task"):
                    story_keys.append(key)

    if not story_keys:
        print("No Story issues found.")
        return

    # Step 2: Display found Story issues and request confirmation
    print(f"Found {len(story_keys)} Story/Task issues:")
    for key in story_keys:
        print(f"  - {key}")

    # Step 3: Process realized_by lists to remove references to Story issues
    modifications_made = 0
    for key, issue in issues_data.items():
        if key not in story_keys and "realized_by" in issue["data"]:
            original_length = len(issue["data"]["realized_by"])
            # Filter out any realized_by entries with keys in story_keys
            issue["data"]["realized_by"] = [
                item for item in issue["data"]["realized_by"]
                if item.get("key") not in story_keys
            ]
            new_length = len(issue["data"]["realized_by"])

            # Save the file if changes were made
            if original_length != new_length:
                print(f"Removing {original_length - new_length} Story/Task references from {key}")
                save_jira_json(issue["path"], issue["data"])
                modifications_made += 1

    print(f"\nUpdated {modifications_made} files to remove Story/Task references.")

    # Step 4: Delete Story JSON files
    for key in story_keys:
        if key in issues_data:
            file_path = issues_data[key]["path"]
            try:
                os.remove(file_path)
                print(f"Deleted Story/Task file: {file_path}")
            except Exception as e:
                print(f"Error deleting {file_path}: {e}")

if __name__ == "__main__":
    json_dir = JIRA_ISSUES_DIR
    cleanup_story_issues(json_dir)
