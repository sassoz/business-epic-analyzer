import os

# Base paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC_DIR = os.path.join(BASE_DIR, 'src')
LOGS_DIR = os.path.join(BASE_DIR, 'logs')
DATA_DIR = os.path.join(BASE_DIR, 'data')
TEMPLATES_DIR = os.path.join(BASE_DIR, 'templates')

# Data subdirectories
JIRA_ISSUES_DIR = os.path.join(DATA_DIR, 'jira_issues')
HTML_REPORTS_DIR = os.path.join(DATA_DIR, 'html_reports')
ISSUE_TREES_DIR = os.path.join(DATA_DIR, 'issue_trees')
JSON_SUMMARY_DIR = os.path.join(DATA_DIR, 'json_summary')

# Ensure directories exist
for directory in [LOGS_DIR, JIRA_ISSUES_DIR, HTML_REPORTS_DIR, ISSUE_TREES_DIR, JSON_SUMMARY_DIR]:
    os.makedirs(directory, exist_ok=True)

# Template file
EPIC_HTML_TEMPLATE = os.path.join(TEMPLATES_DIR, 'epic-html_template.html')
