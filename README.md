# LLM-Alpha-Forecasting

LLM-based sentiment signals from news, Reddit, and SEC filings are combined
with technical indicators (RSI, ADX, volatility, volume, and momentum) and
fed into tree-based models to generate buy/no-buy signals. Out-of-sample tests
assess whether this alternative data adds predictive power and produces alpha.

## Project Structure

```text
LLM-Alpha-Forecasting/
├── data/
│   ├── prices/
│   ├── reddit/
│   ├── sec/
│   └── news/
├── notebooks/
├── src/
│   ├── data_collection/
│   ├── sentiment/
│   ├── features/
│   ├── models/
│   └── evaluation/
├── outputs/
├── requirements.txt
└── README.md
```

## Data Collection

Install the dependency into the project environment:

```powershell
.\LLMAFvenv\Scripts\python.exe -m pip install -r requirements.txt
```

The collector in `src/data_collection/collect_sources.py` does not score text
with an LLM. It only downloads raw records so that collection, inspection, and
sentiment labeling remain separate.

### News

GDELT provides free news metadata without an API key. It includes titles,
URLs, source domains, timestamps, language, and an aggregate tone field. It
does not reliably provide full article text.

```powershell
.\LLMAFvenv\Scripts\python.exe src/data_collection/collect_sources.py news `
	--query '("Apple" OR AAPL) sourcelang:english' `
	--max-records 100
```

Output: `data/news/news.csv`

### SEC filings

SEC EDGAR is free. Set a descriptive contact address before making requests:

```powershell
$env:SEC_USER_AGENT = "Your Name research your-email@example.com"
.\LLMAFvenv\Scripts\python.exe src/data_collection/collect_sources.py sec `
	--cik 320193 `
	--forms 10-K 10-Q 8-K `
	--max-records 100
```

Output: `data/sec/filings.csv`. Each record includes a primary-document URL;
download and parse filing text separately so the raw URL and original metadata
remain available.

### Reddit

Reddit requires an OAuth application and credentials. Set these environment
variables in your shell rather than committing them:

```powershell
$env:REDDIT_CLIENT_ID = "..."
$env:REDDIT_CLIENT_SECRET = "..."
$env:REDDIT_USERNAME = "..."
$env:REDDIT_PASSWORD = "..."
.\LLMAFvenv\Scripts\python.exe src/data_collection/collect_sources.py reddit `
	--subreddit stocks `
	--query 'AAPL OR Apple' `
	--max-records 100
```

Output: `data/reddit/posts.jsonl`. Review Reddit's current API terms and rate
limits before collecting at scale.
