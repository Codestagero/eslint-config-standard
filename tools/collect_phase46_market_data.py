#!/usr/bin/env python3
from __future__ import annotations

import csv
import gzip
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

PRIMARY_BASE = "https://api.pipai.org"
FALLBACK_BASE = "https://fapi.binance.com"
START_DAY = "2026-08-01T00:00:00+00:00"
COMPLETE_BEFORE = "2026-08-21T00:00:00+00:00"
PARTIAL_START = "2026-08-17T00:00:00+00:00"
USER_AGENT = "FABLE-phase46-aug21-market-collector/1.0"
_LOCAL = threading.local()


class ApiError(RuntimeError):
    pass


def to_ms(value: str | datetime) -> int:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return int(value.timestamp() * 1000)


def iso_ms(value: Any) -> str:
    return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc).isoformat()


def session() -> requests.Session:
    if not hasattr(_LOCAL, "session"):
        s = requests.Session()
        s.headers.update({"User-Agent": USER_AGENT})
        _LOCAL.session = s
    return _LOCAL.session


def request_json(path: str, params: dict[str, Any] | None = None, attempts: int = 6) -> tuple[Any, str]:
    last: str | None = None
    for base in (PRIMARY_BASE, FALLBACK_BASE):
        for attempt in range(attempts):
            try:
                response = session().get(f"{base}{path}", params=params, timeout=(15, 75))
                text = response.text[:500]
                if response.status_code in (418, 429, 500, 502, 503, 504):
                    last = f"{base} HTTP {response.status_code}: {text}"
                    response.close()
                    time.sleep(min(12.0, 0.5 * (2**attempt)))
                    continue
                if response.status_code in (400, 404):
                    response.close()
                    raise ApiError(f"{base} HTTP {response.status_code}: {text}")
                response.raise_for_status()
                payload = response.json()
                response.close()
                if isinstance(payload, dict) and isinstance(payload.get("code"), int) and payload.get("code", 0) < 0:
                    raise ApiError(f"{base}: {payload}")
                return payload, base
            except ApiError:
                raise
            except Exception as exc:
                last = f"{base}: {exc!r}"
                time.sleep(min(12.0, 0.5 * (2**attempt)))
    raise RuntimeError(last or f"all bases failed for {path}")


def fetch_premium() -> tuple[list[dict[str, Any]], str]:
    payload, source = request_json("/fapi/v1/premiumIndex")
    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        raise RuntimeError(f"unexpected premium payload: {payload!r}")
    rows = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol", ""))
        try:
            mark = float(item.get("markPrice"))
            stamp = int(item.get("time"))
        except Exception:
            continue
        if symbol.endswith("USDT") and mark > 0:
            normalized = dict(item)
            normalized["symbol"] = symbol
            normalized["markPrice"] = mark
            normalized["time"] = stamp
            rows.append(normalized)
    if not rows:
        raise RuntimeError("premium snapshot returned no USDT contracts")
    return sorted(rows, key=lambda row: row["symbol"]), source


def fetch_daily(symbol: str) -> dict[str, Any]:
    try:
        payload, source = request_json(
            "/fapi/v1/klines",
            {
                "symbol": symbol,
                "interval": "1d",
                "startTime": to_ms(START_DAY),
                "endTime": to_ms(COMPLETE_BEFORE) - 1,
                "limit": 50,
            },
        )
        rows = []
        if not isinstance(payload, list):
            raise RuntimeError(f"unexpected payload type {type(payload).__name__}")
        for item in payload:
            if not isinstance(item, list) or len(item) < 8:
                continue
            open_ms = int(item[0])
            if open_ms < to_ms(START_DAY) or open_ms >= to_ms(COMPLETE_BEFORE):
                continue
            rows.append(
                {
                    "symbol": symbol,
                    "timestamp": iso_ms(open_ms),
                    "open": float(item[1]),
                    "close": float(item[4]),
                    "quote_volume": float(item[7]),
                }
            )
        return {"symbol": symbol, "success": True, "source": source, "rows": rows}
    except Exception as exc:
        return {"symbol": symbol, "success": False, "error": repr(exc), "rows": []}


def fetch_funding(symbol: str, capture_ms: int) -> dict[str, Any]:
    try:
        payload, source = request_json(
            "/fapi/v1/fundingRate",
            {
                "symbol": symbol,
                "startTime": to_ms(START_DAY),
                "endTime": capture_ms,
                "limit": 1000,
            },
        )
        if not isinstance(payload, list):
            raise RuntimeError(f"unexpected payload type {type(payload).__name__}")
        rows = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            raw_time = item.get("fundingTime", item.get("timestamp", item.get("time")))
            raw_rate = item.get("fundingRate", item.get("rate"))
            if raw_time is None or raw_rate is None:
                continue
            stamp = int(raw_time)
            if stamp < to_ms(START_DAY) or stamp > capture_ms:
                continue
            rows.append(
                {
                    "symbol": symbol,
                    "timestamp": iso_ms(stamp),
                    "funding": float(raw_rate),
                }
            )
        return {"symbol": symbol, "success": True, "source": source, "rows": rows}
    except Exception as exc:
        return {"symbol": symbol, "success": False, "error": repr(exc), "rows": []}


def fetch_btc_hourly(capture_ms: int) -> tuple[list[dict[str, Any]], str]:
    payload, source = request_json(
        "/fapi/v1/klines",
        {
            "symbol": "BTCUSDT",
            "interval": "1h",
            "startTime": to_ms(PARTIAL_START),
            "endTime": capture_ms,
            "limit": 1000,
        },
    )
    if not isinstance(payload, list):
        raise RuntimeError(f"unexpected BTC hourly payload: {payload!r}")
    rows = []
    for item in payload:
        if not isinstance(item, list) or len(item) < 8:
            continue
        rows.append(
            {
                "timestamp": iso_ms(item[0]),
                "open": float(item[1]),
                "high": float(item[2]),
                "low": float(item[3]),
                "close": float(item[4]),
                "quote_volume": float(item[7]),
            }
        )
    return rows, source


def run_parallel(symbols: list[str], function: Any, workers: int, label: str, *args: Any) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(function, symbol, *args): symbol for symbol in symbols}
        for index, future in enumerate(as_completed(futures), 1):
            results.append(future.result())
            if index % 100 == 0 or index == len(futures):
                print(
                    json.dumps(
                        {
                            "phase": label,
                            "completed": index,
                            "total": len(futures),
                            "success": sum(item["success"] for item in results),
                            "rows": sum(len(item["rows"]) for item in results),
                        }
                    ),
                    flush=True,
                )
    return sorted(results, key=lambda item: item["symbol"])


def write_csv_gz(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", newline="", mtime=0) as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column) for column in columns})


def main() -> None:
    root = Path(os.environ.get("OUTPUT_ROOT", "market_data"))
    root.mkdir(parents=True, exist_ok=True)
    symbols_file = Path(os.environ.get("SYMBOLS_FILE", "phase46_symbols.txt"))
    panel_symbols = sorted({line.strip() for line in symbols_file.read_text().splitlines() if line.strip()})

    premium, premium_source = fetch_premium()
    current_symbols = sorted({row["symbol"] for row in premium})
    symbols = sorted(set(panel_symbols) | set(current_symbols))
    capture_ms = max(int(row["time"]) for row in premium)

    price_results = run_parallel(symbols, fetch_daily, int(os.environ.get("PRICE_WORKERS", "10")), "prices")
    price_rows = [row for result in price_results for row in result["rows"]]
    recent_symbols = sorted({row["symbol"] for row in price_rows})
    required_current = sorted(set(current_symbols) & set(panel_symbols))
    missing_required_prices = sorted(symbol for symbol in required_current if symbol not in recent_symbols)
    if missing_required_prices:
        raise RuntimeError(f"current panel symbols missing recent prices: {missing_required_prices[:30]}")

    sleep_seconds = int(os.environ.get("RATE_LIMIT_PAUSE_SECONDS", "70"))
    print(json.dumps({"phase": "rate_limit_pause", "seconds": sleep_seconds}), flush=True)
    time.sleep(sleep_seconds)

    funding_results = run_parallel(recent_symbols, fetch_funding, int(os.environ.get("FUNDING_WORKERS", "8")), "funding", capture_ms)
    funding_rows = [row for result in funding_results for row in result["rows"]]
    btc_hourly, btc_hourly_source = fetch_btc_hourly(capture_ms)

    write_csv_gz(root / "recent_prices.csv.gz", price_rows, ["symbol", "timestamp", "open", "close", "quote_volume"])
    write_csv_gz(root / "recent_funding.csv.gz", funding_rows, ["symbol", "timestamp", "funding"])
    write_csv_gz(root / "btc_1h.csv.gz", btc_hourly, ["timestamp", "open", "high", "low", "close", "quote_volume"])
    (root / "premium_index.json").write_text(json.dumps(premium, indent=2, sort_keys=True) + "\n")

    audit = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "start_day": START_DAY,
        "complete_before": COMPLETE_BEFORE,
        "partial_start": PARTIAL_START,
        "premium_source": premium_source,
        "btc_hourly_source": btc_hourly_source,
        "capture_time": iso_ms(capture_ms),
        "panel_symbols": len(panel_symbols),
        "current_symbols": len(current_symbols),
        "queried_symbols": len(symbols),
        "recent_price_symbols": len(recent_symbols),
        "price_rows": len(price_rows),
        "funding_symbols_queried": len(recent_symbols),
        "funding_rows": len(funding_rows),
        "btc_hourly_rows": len(btc_hourly),
        "price_failures": [
            {"symbol": item["symbol"], "error": item.get("error")}
            for item in price_results
            if not item["success"]
        ],
        "funding_failures": [
            {"symbol": item["symbol"], "error": item.get("error")}
            for item in funding_results
            if not item["success"]
        ],
        "missing_required_current_prices": missing_required_prices,
    }
    (root / "audit.json").write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: value for key, value in audit.items() if key not in ("price_failures", "funding_failures")}, indent=2))


if __name__ == "__main__":
    main()
