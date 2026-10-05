"""Collect raw news and SEC records for later sentiment scoring.

This module intentionally does not call an LLM. Keep collection and labeling
separate so raw inputs can be inspected and the scoring prompt can evolve.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
DEFAULT_START_DATE = date(2016, 1, 1)
DEFAULT_END_DATE = date.today()
COMMON_FIELDS = (
    "source_type",
    "ticker",
    "source_id",
    "published_at_utc",
    "title",
    "text",
    "url",
    "source_name",
    "collected_at_utc",
)
load_dotenv(ROOT / ".env")
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
    extra_fields = sorted(
        {key for record in records for key in record}.difference(COMMON_FIELDS)
    )
    fieldnames = [*COMMON_FIELDS, *extra_fields]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)


def collect_sec(
    cik: str,
    forms: set[str],
    max_records: int,
    ticker: str,
    start_date: date,
    end_date: date,
) -> list[dict[str, Any]]:
    """Collect SEC filing metadata from recent and archived submissions."""
    normalized_cik = cik.strip().zfill(10)
    payload = request_json(
        f"https://data.sec.gov/submissions/CIK{normalized_cik}.json",
        headers={"User-Agent": SEC_USER_AGENT},
    )
    records = []

    submissions = [payload.get("filings", {}).get("recent", {})]
    for archive in payload.get("filings", {}).get("files", []):
        archive_date = archive.get("filingTo", "")
        if archive_date and archive_date < start_date.isoformat():
            continue
        archive_payload = request_json(
            f"https://data.sec.gov/submissions/{archive['name']}",
            headers={"User-Agent": SEC_USER_AGENT},
        )
        submissions.append(archive_payload)

    seen_accessions: set[str] = set()
    for submission in submissions:
        filing_dates = submission.get("filingDate", [])
        for index, form in enumerate(submission.get("form", [])):
            filing_date = date.fromisoformat(filing_dates[index])
            if form not in forms or not start_date <= filing_date <= end_date:
                continue
            accession = submission["accessionNumber"][index]
            if accession in seen_accessions:
                continue
            seen_accessions.add(accession)
            accession_path = accession.replace("-", "")
            primary_document = submission["primaryDocument"][index]
            items = submission.get("items", [])
            records.append(
                {
                    "source_type": "sec",
                    "ticker": ticker.upper(),
                    "source_id": accession,
                    "published_at_utc": filing_date.isoformat(),
                    "title": f"{form} filing",
                    "description": items[index] if index < len(items) else "",
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
            if max_records and len(records) >= max_records:
                return records[:max_records]
    records.sort(key=lambda record: (record["published_at_utc"], record["source_id"]))
    return records


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="source", required=True)

    sec = subparsers.add_parser("sec", help="Collect SEC filing metadata")
    sec.add_argument("--ticker", required=True, help="Ticker symbol for the output asset folder")
    sec.add_argument(
        "--cik",
        required=True,
        help="SEC CIK, with or without leading zeroes",
    )
    sec.add_argument("--forms", nargs="+", default=["10-K", "10-Q", "8-K"])
    sec.add_argument("--start-date", type=date.fromisoformat, default=DEFAULT_START_DATE)
    sec.add_argument("--end-date", type=date.fromisoformat, default=DEFAULT_END_DATE)
    sec.add_argument("--max-records", type=int, default=0, help="0 means all available records")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.max_records < 0:
        parser.error("--max-records must be zero or greater")
    if args.start_date > args.end_date:
        parser.error("--start-date must be on or before --end-date")
    if args.source == "sec":
        records = collect_sec(
            args.cik,
            set(args.forms),
            args.max_records,
            args.ticker,
            args.start_date,
            args.end_date,
        )
        output_path = DATA_DIR / args.ticker.lower() / "sec_filings.csv"
        write_csv(output_path, records)
    print(f"Collected {len(records)} {args.source} records to {output_path}.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except requests.HTTPError as error:
        print(f"HTTP request failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error