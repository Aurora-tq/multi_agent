# Multi-Modal Retrieval Augmented Agent Pipeline

This project implements a multi-agent system designed to search the web, analyze text and images (using VLM), and generate comprehensive reports with visualizations.

## Architecture

The system consists of four specialized agents coordinated by a Manager (main.py):

1. **Search Agent**: Finds relevant URLs based on user queries.
2. **Retrieval & Parsing Agent**: Scrapes web content and uses VLM (Vision Language Model) to analyze images found on pages.
3. **Analyst Agent**: Aggregates data, calculates statistics, and predicts trends.
4. **Reporter Agent**: Generates a markdown report with matplotlib visualizations.

## Setup

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt