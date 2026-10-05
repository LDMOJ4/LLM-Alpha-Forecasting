"""Import ticker-specific tweets from the Kaggle NASDAQ tweet dataset."""

from __future__ import annotations

import argparse
import csv
import re
from datetime import date, datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FIELDS = (
    "source_type", "ticker", "source_id", "published_at_utc", "title", "text",
    "url", "source_name", "collected_at_utc", "author", "likes", "retweets", "replies",
)


def normalize_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def first_value(row: dict[str, str], names: tuple[str, ...]) -> str:
    for name in names:
        value = row.get(name, "").strip()
        if value:
            return value
    return ""


def parse_timestamp(value: str) -> datetime:
    value = value.strip()
    if value.replace(".", "", 1).isdigit():
        timestamp = float(value)
        if timestamp > 10_000_000_000:
            timestamp /= 1000
        return datetime.fromtimestamp(timestamp, timezone.utc)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def parse_integer(value: str) -> int | str:
    if not value:
        return ""
    try:
        return int(float(value.replace(",", "")))
    except ValueError:
        return value


def write_tweet(
    writer: csv.DictWriter[str],
    row: dict[str, str],
    source_id: str,
    published_at: datetime,
    ticker: str,
) -> None:
    writer.writerow({
        "source_type": "twitter", "ticker": ticker.upper(), "source_id": source_id,
        "published_at_utc": published_at.isoformat(), "title": "",
        "text": first_value(row, ("text", "tweet", "tweet_text", "body", "content")),
        "url": first_value(row, ("link", "url")),
        "source_name": "Kaggle NASDAQ tweets 2015-2020", "collected_at_utc": "",
        "author": first_value(row, ("author", "writer", "username", "user_name")),
        "likes": parse_integer(first_value(row, ("likes", "like_num", "nlikes", "like_count"))),
        "retweets": parse_integer(first_value(row, ("retweets", "retweet_num", "nretweets", "retweet_count"))),
        "replies": parse_integer(first_value(row, ("replies", "comment_num", "nreplies", "comments", "comment_count"))),
    })


def import_relational_dataset(
    input_dir: Path,
    output_path: Path,
    start_date: date,
    end_date: date,
    limit: int,
    ticker: str,
) -> tuple[int, int]:
    company_tweets_path = input_dir / "Company_Tweet.csv"
    tweets_path = input_dir / "Tweet.csv"
    if not company_tweets_path.is_file() or not tweets_path.is_file():
        raise ValueError("Input directory must contain Company_Tweet.csv and Tweet.csv")
    tweet_ids = set()
    with company_tweets_path.open(encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            if row.get("ticker_symbol", "").upper() == ticker.upper():
                tweet_ids.add(row.get("tweet_id", ""))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rows_read = rows_written = 0
    with tweets_path.open(encoding="utf-8-sig", newline="") as source, output_path.open("w", encoding="utf-8", newline="") as destination:
        writer = csv.DictWriter(destination, fieldnames=FIELDS)
        writer.writeheader()
        for raw_row in csv.DictReader(source):
            rows_read += 1
            source_id = raw_row.get("tweet_id", "")
            if source_id not in tweet_ids:
                continue
            published_at = parse_timestamp(raw_row.get("post_date", ""))
            if not start_date <= published_at.date() <= end_date:
                continue
            write_tweet(writer, raw_row, source_id, published_at, ticker)
            rows_written += 1
            if limit and rows_written >= limit:
                break
    return rows_read, rows_written


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Kaggle dataset directory")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--ticker", required=True, help="Ticker symbol to extract")
    parser.add_argument("--start-date", type=date.fromisoformat, required=True)
    parser.add_argument("--end-date", type=date.fromisoformat, required=True)
    parser.add_argument("--limit", type=int, default=0)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.limit < 0 or args.start_date > args.end_date:
        parser.error("Invalid limit or date range")
    output_path = args.output or ROOT / "data" / args.ticker.lower() / "twitter.csv"
    try:
        rows_read, rows_written = import_relational_dataset(
            args.input, output_path, args.start_date, args.end_date, args.limit, args.ticker
        )
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(f"Read {rows_read} rows and wrote {rows_written} {args.ticker.upper()} tweets to {output_path}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())