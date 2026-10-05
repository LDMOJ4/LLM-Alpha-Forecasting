"""Import asset-related headlines and summaries from News Category Dataset."""

from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FIELDS = (
    "source_type",
    "ticker",
    "source_id",
    "published_at_utc",
    "title",
    "text",
    "url",
    "source_name",
    "collected_at_utc",
    "category",
    "authors",
)


def matches_terms(title: str, summary: str, terms: tuple[str, ...]) -> bool:
    searchable = f"{title} {summary}"
    return any(
        re.search(rf"(?<!\w){re.escape(term)}(?!\w)", searchable, re.IGNORECASE)
        for term in terms
    )


def import_news(
    input_path: Path,
    output_path: Path,
    *,
    start_date: date,
    end_date: date,
    terms: tuple[str, ...],
    limit: int,
    ticker: str,
) -> tuple[int, int]:
    rows_read = 0
    rows_written = 0
    seen_urls: set[str] = set()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with input_path.open("r", encoding="utf-8", errors="replace") as source, output_path.open(
        "w", encoding="utf-8", newline=""
    ) as destination:
        writer = csv.DictWriter(destination, fieldnames=FIELDS)
        writer.writeheader()
        for line in source:
            if not line.strip():
                continue
            rows_read += 1
            article = json.loads(line)
            published_date = date.fromisoformat(article["date"])
            title = article.get("headline", "")
            summary = article.get("short_description", "")
            if not start_date <= published_date <= end_date:
                continue
            if not matches_terms(title, summary, terms):
                continue

            url = article.get("link", "")
            if url and url in seen_urls:
                continue
            if url:
                seen_urls.add(url)
            writer.writerow(
                {
                    "source_type": "news",
                    "ticker": ticker.upper(),
                    "source_id": url or f"news-category-{rows_read}",
                    "published_at_utc": datetime.combine(
                        published_date, datetime.min.time(), timezone.utc
                    ).isoformat(),
                    "title": title,
                    "text": summary,
                    "url": url,
                    "source_name": "HuffPost News Category Dataset",
                    "collected_at_utc": "",
                    "category": article.get("category", ""),
                    "authors": article.get("authors", ""),
                }
            )
            rows_written += 1
            if limit and rows_written >= limit:
                break

    return rows_read, rows_written


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="News_Category_Dataset_v3.json")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--ticker", required=True, help="Ticker symbol for the output asset folder")
    parser.add_argument("--start-date", type=date.fromisoformat, required=True)
    parser.add_argument("--end-date", type=date.fromisoformat, required=True)
    parser.add_argument("--terms", nargs="+", required=True, help="Company names, tickers, or people to match")
    parser.add_argument("--limit", type=int, default=0, help="Maximum matching rows; 0 means all")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.limit < 0:
        parser.error("--limit must be zero or greater")
    if args.start_date > args.end_date:
        parser.error("--start-date must be on or before --end-date")
    try:
        output_path = args.output or ROOT / "data" / args.ticker.lower() / "news.csv"
        rows_read, rows_written = import_news(
            args.input,
            output_path,
            start_date=args.start_date,
            end_date=args.end_date,
            terms=tuple(args.terms),
            limit=args.limit,
            ticker=args.ticker,
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))
    print(f"Read {rows_read} articles and wrote {rows_written} {args.ticker.upper()} records to {output_path}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())