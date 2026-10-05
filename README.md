# LLM-Alpha-Forecasting

This project collects daily market data and alternative data for one or more
assets. Each asset has its own directory under `data/<ticker>/` so the same
collection scripts can be reused for TSLA, SPY, AAPL, or another supported
ticker.

## Project Structure

```text
LLM-Alpha-Forecasting/
├── data/
│   └── <ticker>/
│       ├── daily_finance_metrics.csv
│       ├── news.csv
│       ├── sec_filings.csv
│       └── twitter.csv
├── src/
│   ├── data_collection/
│   ├── sentiment/
│   ├── features/
│   ├── models/
│   └── evaluation/
├── outputs/
└── requirements.txt
```

Install dependencies into the existing project environment:

```powershell
.\LLMAFvenv\Scripts\python.exe -m pip install -r requirements.txt
```

## Collection Scripts

All collectors take the asset identity as an input and default their output to
`data/<ticker>/`. Override `--output` when a different location is required.

### Daily Prices

Yahoo Finance data includes daily OHLCV, adjusted close, dividends, split
ratios, currency, and provenance fields.

```powershell
.\LLMAFvenv\Scripts\python.exe src/data_collection/collect_prices.py `
    --ticker TSLA `
    --start-date 2015-01-01 `
    --end-date 2020-12-31
```

Output: `data/tsla/daily_finance_metrics.csv`. Use the same command with another ticker
to create its parallel asset directory.

### SEC Filings

Set `SEC_USER_AGENT` in `.env`, then provide the ticker and its SEC CIK:

```powershell
.\LLMAFvenv\Scripts\python.exe src/data_collection/ingest_sec_filings.py sec `
    --ticker TSLA `
    --cik 1318605 `
    --forms 10-K 10-Q 8-K `
    --start-date 2015-01-01 `
    --end-date 2020-12-31 `
    --max-records 0
```

Output: `data/tsla/sec_filings.csv`. The collector follows SEC archived
submission files and recent filings, but stores metadata and document URLs;
filing text can be downloaded and parsed separately.

### Historical News

The News Category Dataset contains headlines and short descriptions. The
importer receives the ticker and matching company terms explicitly, then keeps
only matching records within the requested date range.

```powershell
.\LLMAFvenv\Scripts\python.exe -c "import kagglehub; print(kagglehub.dataset_download('rmisra/news-category-dataset'))"
.\LLMAFvenv\Scripts\python.exe src/data_collection/ingest_news_category.py `
    --input 'path\to\News_Category_Dataset_v3.json' `
    --ticker TSLA `
    --terms Tesla TSLA 'Elon Musk' `
    --start-date 2016-01-01 `
    --end-date 2020-04-02 `
    --limit 0
```

Output: `data/tsla/news.csv`. The dataset is licensed CC BY 4.0; retain its
attribution when using it.

### Historical Tweets

The Kaggle NASDAQ tweet dataset contains relational `Company_Tweet.csv` and
`Tweet.csv` files. The importer joins them, selects the requested ticker, and
preserves tweet text, timestamps, authors, and engagement counts.

```powershell
.\LLMAFvenv\Scripts\python.exe -c "import kagglehub; print(kagglehub.dataset_download('omermetinn/tweets-about-the-top-companies-from-2015-to-2020'))"
.\LLMAFvenv\Scripts\python.exe src/data_collection/ingest_tweets.py `
    --input 'path\to\kaggle\dataset\folder' `
    --ticker TSLA `
    --start-date 2015-01-01 `
    --end-date 2020-12-31 `
    --limit 0
```

Output: `data/tsla/twitter.csv`. Sentiment scoring is intentionally separate
from ingestion and belongs in the sentiment/features stages.
