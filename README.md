# Energy Target Finder

A Streamlit app for TimeX-style energy and infrastructure origination.

## Features

- Limited filters: vertical, geography, target angle
- Company/project discovery through public-source search queries
- Optional live web search with `SERPAPI_KEY` or `BRAVE_API_KEY`
- Company/project sponsor scoring
- Banking-angle classification
- Public LinkedIn search-query generation
- Optional people-discovery pass if search API key is available
- CSV export
- "Send Results to TimeX Gmail" button
- Apollo API key placeholder for future contact enrichment

## Files

Your GitHub repo should include:

```text
app.py
requirements.txt
README.md
```

## Streamlit setup

Main file path:

```text
app.py
```

## Optional Streamlit secrets

In Streamlit Cloud, add secrets like this:

```toml
SERPAPI_KEY = "your_serpapi_key"
BRAVE_API_KEY = "your_brave_key"
APOLLO_API_KEY = "your_apollo_key"
```

You do not need keys to deploy. Without keys, the app generates manual search links.

## Local run

```bash
pip install -r requirements.txt
streamlit run app.py
```
