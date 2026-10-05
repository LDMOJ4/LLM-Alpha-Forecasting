"""Collect daily OHLCV data from Yahoo Finance's chart endpoint."""

from __future__ import annotations

import argparse
import csv
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
SOURCE_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
FIELDS = (
    "date",
    "ticker",
    "open",
    "high",
    "low",
    "close",
    "adjusted_close",
    "volume",
    "dividend",
    "split_ratio",
    "currency",
    "source",
    "collected_at_utc",
)


def date_to_epoch(value: date) -> int:
    return int(datetime.combine(value, datetime.min.time(), timezone.utc).timestamp())


def request_chart(
    ticker: str,
    start_date: date,
    end_date: date,
    timeout: int = 30,
) -> dict[str, Any]:
    response = requests.get(
        SOURCE_URL.format(ticker=ticker),
        params={
            "period1": date_to_epoch(start_date),
            "period2": date_to_epoch(end_date + timedelta(days=1)),
            "interval": "1d",
            "events": "div,splits",
            "includeAdjustedClose": "true",
        },
        headers={"User-Agent": "LLM-Alpha-Forecasting/0.1"},
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    chart = payload.get("chart", {})
    if chart.get("error"):
        raise RuntimeError(f"Yahoo Finance returned an error: {chart['error']}")
    results = chart.get("result") or []
    if not results:
        raise RuntimeError(f"Yahoo Finance returned no data for {ticker}")
    return results[0]


def corporate_actions(result: dict[str, Any]) -> tuple[dict[int, float], dict[int, str]]:
    events = result.get("events", {})
    dividends = {
        int(timestamp): float(event.get("amount", 0))
        for timestamp, event in events.get("div", {}).items()
    }
    splits = {}
    for timestamp, event in events.get("splits", {}).items():
        numerator = event.get("numerator")
        denominator = event.get("denominator")
        if numerator is not None and denominator is not None:
            splits[int(timestamp)] = f"{numerator}:{denominator}"
    return dividends, splits


def build_records(
    result: dict[str, Any],
    ticker: str,
    collected_at_utc: str,
) -> list[dict[str, Any]]:
    timestamps = result.get("timestamp") or []
    indicators = result.get("indicators", {})
    quote = (indicators.get("quote") or [{}])[0]
    adjusted = (indicators.get("adjclose") or [{}])[0].get("adjclose", [])
    dividends, splits = corporate_actions(result)
    currency = result.get("meta", {}).get("currency", "")
    records = []

    for index, timestamp in enumerate(timestamps):
        values = {
            "open": quote.get("open", [])[index],
            "high": quote.get("high", [])[index],
            "low": quote.get("low", [])[index],
            "close": quote.get("close", [])[index],
            "volume": quote.get("volume", [])[index],
        }
        if any(value is None for value in values.values()):
            continue
        trading_timestamp = int(timestamp)
        trading_date = datetime.fromtimestamp(trading_timestamp, timezone.utc).date()
        records.append(
            {
                "date": trading_date.isoformat(),
                "ticker": ticker.upper(),
                "open": values["open"],
                "high": values["high"],
                "low": values["low"],
                "close": values["close"],
                "adjusted_close": adjusted[index] if index < len(adjusted) else values["close"],
                "volume": values["volume"],
                "dividend": dividends.get(trading_timestamp, 0),
                "split_ratio": splits.get(trading_timestamp, ""),
                "currency": currency,
                "source": "Yahoo Finance chart API",
                "collected_at_utc": collected_at_utc,
            }
        )
    return records


def collect_prices(
    ticker: str,
    start_date: date,
    end_date: date,
    timeout: int = 30,
) -> list[dict[str, Any]]:
    ticker = ticker.upper()
    if start_date > end_date:
        raise ValueError("Start date must be on or before end date")
    result = request_chart(ticker, start_date, end_date, timeout)
    return build_records(result, ticker, datetime.now(timezone.utc).isoformat())


def write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(records)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", required=True, help="Ticker symbol for the output asset folder")
    parser.add_argument("--start-date", type=date.fromisoformat, required=True)
    parser.add_argument(
        "--end-date",
        type=date.fromisoformat,
        default=date.today(),
        help="Inclusive date; defaults to today",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--pause", type=float, default=0.0, help="Pause after the request, in seconds")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.start_date > args.end_date:
        parser.error("--start-date must be on or before --end-date")
    if args.timeout <= 0:
        parser.error("--timeout must be greater than zero")
    if args.pause < 0:
        parser.error("--pause cannot be negative")

    output_path = args.output or DATA_DIR / args.ticker.lower() / "daily_finance_metrics.csv"
    try:
        records = collect_prices(args.ticker, args.start_date, args.end_date, args.timeout)
        if args.pause:
            time.sleep(args.pause)
        write_csv(output_path, records)
    except (OSError, requests.RequestException, RuntimeError, ValueError) as error:
        parser.error(str(error))

    print(f"Wrote {len(records)} daily {args.ticker.upper()} records to {output_path}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())