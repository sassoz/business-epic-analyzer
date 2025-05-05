# JIRA Business Epic Analyzer and Reporter

A comprehensive tool that automates JIRA issue extraction, visualization, and reporting. This project scrapes JIRA issues, analyzes their relationships, generates visual representations, and creates HTML summaries enhanced by AI.

## 📋 Features

- 🔐 Automated JIRA login and issue extraction
- 🔄 Recursive traversal of "is-realized-by" relationships and child issues
- 📊 Issue hierarchy visualization with GraphViz
- 🤖 AI-powered business value extraction and summary generation
- 📝 HTML report generation
- 📈 LLM token usage tracking and reporting

## 🛠️ Technologies

- Python 3.10+
- Selenium for web scraping
- NetworkX and Matplotlib for graph visualization
- BeautifulSoup for HTML parsing
- LiteLLM/Anthropic Claude API for AI analysis
- Pandas for data processing

## 📁 Repository Structure

```
business-epic-analyzer/
├── src/
│   ├── utils/
│   │   ├── business_impact_api.py
│   │   ├── claude_api_integration.py
│   │   ├── cleanup_story_json.py
│   │   ├── data_extractor.py
│   │   ├── epic_html_generator.py
│   │   ├── file_exporter.py
│   │   ├── jira_tree_classes.py
│   │   ├── jira_scraper.py
│   │   ├── login_handler.py
│   │   ├── logger_config.py
│   │   └── token_usage_class.py
│   └── main_scraper.py
├── logs/
├── data/
│   ├── html_reports/
│   ├── issue_trees/
│   ├── jira_issues/
│   └── json_summary/
└── templates/
    └── epic-html_template.html
```

## 🚀 Usage

1. Create a text file (`BE_Liste.txt`) with JIRA Business Epic keys (one per line):
```
BEMABU-1825
BEMABU-1844
```

2. Run the main script:
```bash
python src/main_scraper.py
```

3. The script will:
   - Log into JIRA with windows account credentials using chrome browser (not JIRA API)
   - Scrape data from each Business Epic and related issues
   - Generate visualization graphs
   - Create context files for AI processing
   - Generate AI summaries
   - Create HTML reports in the `data` directory

### Configuring Models

You can configure which AI models to use by modifying these variables in `main_scraper.py`:

```python
LLM_MODEL_HTML_GENERATOR = "gpt-4.1-mini"
LLM_MODEL_BUSINESS_VALUE = "claude-3-7-sonnet-latest"
LLM_MODEL_SUMMARY = "gpt-4.1"
```

## 📊 Output Files

The script generates several output files:

- `data/issue_trees/[EPIC-KEY]_issue_tree.png` - Visualization of issue relationships
- `data/json_summary/[EPIC-KEY]_json_summary.json` - AI-generated summary in JSON format
- `data/html_reports/[EPIC-KEY]_summary.html` - Final HTML report with embedded visualizations
