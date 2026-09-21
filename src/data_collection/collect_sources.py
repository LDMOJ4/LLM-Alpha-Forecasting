"""Collect raw news, Reddit, and SEC records for later sentiment scoring.

This module intentionally does not call an LLM. Keep collection and labeling
separate so raw inputs can be inspected and the scoring prompt can evolve.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
SEC_USER_AGENT = os.getenv(
    "SEC_USER_AGENT", "LLM-Alpha-Forecasting research contact@example.com"
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def request_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    timeout: int = 30,
) -> Any:
    response = requests.get(url, headers=headers, params=params, timeout=timeout)
    response.raise_for_status()
    return response.json()


def write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not records:
        return
    fieldnames = sorted({key for record in records for key in record})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def collect_news(query: str, max_records: int) -> list[dict[str, Any]]:
    """Collect article metadata from GDELT's free DOC 2.0 API.

    GDELT supplies title, URL, source, timestamp, language, and tone metadata.
    It generally does not provide article bodies, so ``text`` is left empty.
    """
    payload = request_json(
        "https://api.gdeltproject.org/api/v2/doc/doc",
        params={
            "query": query,
            "mode": "artlist",
            "maxrecords": min(max_records, 250),
            "format": "json",
            "sort": "datedesc",
        },
    )
    records = []
    for article in payload.get("articles", []):
        records.append(
            {
                "source_type": "news",
                "source_id": article.get("url"),
                "published_at_utc": article.get("seendate"),
                "title": article.get("title", ""),
                "description": "",
                "text": "",
                "url": article.get("url", ""),
                "source_name": article.get("domain", ""),
                "language": article.get("language", ""),
                "source_country": article.get("sourcecountry", ""),
                "gdelt_tone": article.get("tone", ""),
                "collected_at_utc": utc_now(),
            }
        )
    return records


def collect_sec(cik: str, forms: set[str], max_records: int) -> list[dict[str, Any]]:
    """Collect recent SEC filing metadata and optional primary document URLs."""
    normalized_cik = cik.strip().zfill(10)
    payload = request_json(
        f"https://data.sec.gov/submissions/CIK{normalized_cik}.json",
        headers={"User-Agent": SEC_USER_AGENT},
    )
    recent = payload.get("filings", {}).get("recent", {})
    records = []
    for index, form in enumerate(recent.get("form", [])):
        if form not in forms:
            continue
        accession = recent["accessionNumber"][index]
        accession_path = accession.replace("-", "")
        primary_document = recent["primaryDocument"][index]
        records.append(
            {
                "source_type": "sec",
                "source_id": accession,
                "published_at_utc": recent["filingDate"][index],
                "title": f"{form} filing",
                "description": recent.get("items", [""])[index],
                "text": "",
                "url": (
                    f"https://www.sec.gov/Archives/edgar/data/"
                    f"{int(normalized_cik)}/{accession_path}/{primary_document}"
                ),
                "source_name": "SEC EDGAR",
                "cik": normalized_cik,
                "form": form,
                "collected_at_utc": utc_now(),
            }
        )
        if len(records) >= max_records:
            break
    return records


def reddit_access_token() -> str:
    client_id = os.getenv("REDDIT_CLIENT_ID")
    client_secret = os.getenv("REDDIT_CLIENT_SECRET")
    username = os.getenv("REDDIT_USERNAME")
    password = os.getenv("REDDIT_PASSWORD")
    if not all((client_id, client_secret, username, password)):
        raise RuntimeError(
            "Set REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USERNAME, "
            "and REDDIT_PASSWORD before using the Reddit collector."
        )
    response = requests.post(
        "https://www.reddit.com/api/v1/access_token",
        auth=(client_id, client_secret),
        data={"grant_type": "password", "username": username, "password": password},
        headers={"User-Agent": "LLM-Alpha-Forecasting/0.1"},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def collect_reddit(subreddit: str, query: str, max_records: int) -> list[dict[str, Any]]:
    """Collect searchable Reddit submissions through Reddit OAuth."""
    token = reddit_access_token()
    payload = request_json(
        f"https://oauth.reddit.com/r/{quote(subreddit)}/search",
        headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": "LLM-Alpha-Forecasting/0.1",
        },
        params={"q": query, "restrict_sr": "on", "sort": "new", "limit": min(max_records, 100)},
    )
    records = []
    for child in payload.get("data", {}).get("children", []):
        post = child.get("data", {})
        records.append(
            {
                "source_type": "reddit",
                "source_id": post.get("id", ""),
                "published_at_utc": datetime.fromtimestamp(
                    post.get("created_utc", 0), tz=timezone.utc
                ).isoformat(),
                "title": post.get("title", ""),
                "description": "",
                "text": post.get("selftext", ""),
                "url": f"https://www.reddit.com{post.get('permalink', '')}",
                "source_name": f"r/{post.get('subreddit', subreddit)}",
                "author": post.get("author", ""),
                "score": post.get("score", 0),
                "num_comments": post.get("num_comments", 0),
                "collected_at_utc": utc_now(),
            }
        )
    return records


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="source", required=True)

    news = subparsers.add_parser("news", help="Collect GDELT news metadata")
    news.add_argument("--query", required=True)
    news.add_argument("--max-records", type=int, default=100)

    sec = subparsers.add_parser("sec", help="Collect SEC filing metadata")
    sec.add_argument("--cik", required=True, help="SEC CIK, with or without leading zeroes")
    sec.add_argument("--forms", nargs="+", default=["10-K", "10-Q", "8-K"])
    sec.add_argument("--max-records", type=int, default=100)

    reddit = subparsers.add_parser("reddit", help="Collect Reddit submissions")
    reddit.add_argument("--subreddit", required=True)
    reddit.add_argument("--query", required=True)
    reddit.add_argument("--max-records", type=int, default=100)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.source == "news":
        records = collect_news(args.query, args.max_records)
        write_csv(DATA_DIR / "news" / "news.csv", records)
    elif args.source == "sec":
        records = collect_sec(args.cik, set(args.forms), args.max_records)
        write_csv(DATA_DIR / "sec" / "filings.csv", records)
    else:
        records = collect_reddit(args.subreddit, args.query, args.max_records)
        write_jsonl(DATA_DIR / "reddit" / "posts.jsonl", records)
    print(f"Collected {len(records)} {args.source} records.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except requests.HTTPError as error:
        print(f"HTTP request failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error