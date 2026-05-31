from __future__ import annotations

import re
from datetime import date
from html.parser import HTMLParser
import logging
import os
from typing import Protocol

import httpx

from app.db.models import SymbolUniverse


logger = logging.getLogger(__name__)


class SymbolUniverseProvider(Protocol):
    def fetch_membership(self, universe: SymbolUniverse, *, as_of: date) -> set[str]:
        raise NotImplementedError


class WikipediaUniverseProvider:
    def _user_agent(self) -> str:
        configured = os.environ.get("BACKTEST_WIKIPEDIA_USER_AGENT")
        if configured and configured.strip():
            return configured.strip()
        # Wikimedia requests a descriptive UA; keep a sensible default but allow overriding via env.
        return "bt-symbol-universe/1.0 (local)"

    def _wikipedia_url_for_kind(self, kind: str) -> str:
        normalized = kind.strip().lower()
        urls = {
            "dow30": "https://en.wikipedia.org/wiki/Dow_Jones_Industrial_Average",
            "sp500": "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
            "nasdaq100": "https://en.wikipedia.org/wiki/Nasdaq-100",
        }
        if normalized not in urls:
            raise RuntimeError(f"Unsupported Wikipedia universe kind {kind!r}")
        return urls[normalized]

    def _fetch_membership_from_wikipedia(self, kind: str) -> set[str]:
        url = self._wikipedia_url_for_kind(kind)
        logger.info("Universe provider wikipedia: fetching kind=%s url=%s", kind, url)

        class _WikiTableParser(HTMLParser):
            def __init__(self) -> None:
                super().__init__()
                self._in_table = False
                self._in_row = False
                self._in_cell = False
                self._cell_text: list[str] = []
                self._tables: list[list[list[str]]] = []
                self._table_rows: list[list[str]] = []
                self._row: list[str] = []

            def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
                if tag == "table":
                    self._in_table = True
                    self._table_rows = []
                    return
                if not self._in_table:
                    return
                if tag == "tr":
                    self._in_row = True
                    self._row = []
                elif self._in_row and tag in {"td", "th"}:
                    self._in_cell = True
                    self._cell_text = []

            def handle_endtag(self, tag: str) -> None:
                if tag == "table" and self._in_table:
                    self._in_table = False
                    if self._table_rows:
                        self._tables.append(self._table_rows)
                    self._table_rows = []
                    return
                if not self._in_table:
                    return
                if tag == "tr" and self._in_row:
                    self._in_row = False
                    if self._row:
                        self._table_rows.append(self._row)
                elif tag in {"td", "th"} and self._in_cell:
                    self._in_cell = False
                    text = "".join(self._cell_text).strip()
                    text = re.sub(r"\s+", " ", text)
                    self._row.append(text)

            def handle_data(self, data: str) -> None:
                if self._in_cell:
                    self._cell_text.append(data)

        headers = {"User-Agent": self._user_agent()}
        with httpx.Client(timeout=30.0) as client:
            response = client.get(url, headers=headers)
        if response.status_code >= 400:
            logger.error(
                "Universe provider wikipedia: request failed kind=%s status=%s body_prefix=%r",
                kind,
                response.status_code,
                (response.text or "").strip()[:200],
            )
            raise RuntimeError(f"Wikipedia request failed: {response.status_code} {response.text.strip()[:500]}")

        parser = _WikiTableParser()
        parser.feed(response.text)
        logger.info(
            "Universe provider wikipedia: fetched kind=%s status=%s bytes=%s tables=%s",
            kind,
            response.status_code,
            len(response.content or b""),
            len(parser._tables),
        )

        header_candidates = {
            "symbol",
            "ticker",
            "tickers",
            "ticker symbol",
            "ticker symbols",
            "ticker symbol(s)",
            "ticker(s)",
            "ticker symbol (nyse)",
            "ticker symbol (nasdaq)",
        }
        best_symbols: set[str] = set()
        scanned_headers = 0
        matched_header: tuple[int, int, int, str] | None = None

        def _normalize_header(text: str) -> str:
            normalized = text.strip().lower()
            normalized = re.sub(r"\s+", " ", normalized)
            normalized = re.sub(r"\[[0-9]+\]", "", normalized).strip()
            return normalized

        for table_index, table in enumerate(parser._tables):
            for row_index, row in enumerate(table):
                if not row:
                    continue
                # Heuristic: find a header row with a "symbol"/"ticker" column, then parse subsequent rows in that table.
                lowered = [_normalize_header(c) for c in row]
                scanned_headers += 1
                symbol_col = None
                for idx, header in enumerate(lowered):
                    if header in header_candidates:
                        symbol_col = idx
                        matched_header = (table_index, row_index, idx, header)
                        break
                if symbol_col is None:
                    continue

                for data_row in table[row_index + 1 :]:
                    if symbol_col >= len(data_row):
                        continue
                    raw = data_row[symbol_col]
                    if not raw:
                        continue
                    candidate = raw.strip()
                    candidate = re.sub(r"\[.*?\]", "", candidate).strip()
                    candidate = candidate.split()[0].strip()
                    candidate = candidate.replace(".", "-")
                    candidate = candidate.upper()
                    if re.fullmatch(r"[A-Z0-9][A-Z0-9-]{0,14}", candidate):
                        best_symbols.add(candidate)
                if best_symbols:
                    break
            if best_symbols:
                break

        if not best_symbols:
            logger.error(
                "Universe provider wikipedia: parse failed kind=%s tables=%s scanned_header_rows=%s",
                kind,
                len(parser._tables),
                scanned_headers,
            )
            raise RuntimeError("Wikipedia constituents parse failed: no symbols found")

        header_msg = None
        if matched_header is not None:
            table_index, row_index, col_index, header = matched_header
            header_msg = f"table={table_index} row={row_index} col={col_index} header={header!r}"
        logger.info(
            "Universe provider wikipedia: parsed kind=%s symbols=%s sample=%s header_match=%s",
            kind,
            len(best_symbols),
            ",".join(sorted(best_symbols)[:10]),
            header_msg,
        )
        return best_symbols

    def fetch_membership(self, universe: SymbolUniverse, *, as_of: date) -> set[str]:
        ref = universe.provider_ref or {}
        kind = ref.get("kind")
        if not isinstance(kind, str) or not kind.strip():
            # Backwards-compatible fallback for registry universes created before provider_ref.kind
            # was stored (kind matches the universe key for all built-in FMP universes).
            kind = getattr(universe, "key", None)
        if not isinstance(kind, str) or not kind.strip():
            raise RuntimeError("provider_ref.kind is required (e.g. {'kind':'sp500'})")
        return self._fetch_membership_from_wikipedia(kind)


class StaticListUniverseProvider:
    """Provider for development/testing.

    Expects provider_ref like {"symbols": ["AAPL", "MSFT"]}.
    """

    def fetch_membership(self, universe: SymbolUniverse, *, as_of: date) -> set[str]:
        raw = universe.provider_ref or {}
        symbols = raw.get("symbols")
        if not isinstance(symbols, list):
            return set()
        normalized: set[str] = set()
        for item in symbols:
            if not isinstance(item, str):
                continue
            symbol = item.strip().upper()
            if symbol:
                normalized.add(symbol)
        return normalized


def provider_for_universe(universe: SymbolUniverse) -> SymbolUniverseProvider:
    provider = (universe.provider or "").strip().lower()
    if provider == "wikipedia":
        return WikipediaUniverseProvider()
    if provider == "fmp":
        logger.warning(
            "Symbol universe provider 'fmp' is deprecated; treating as 'wikipedia' for universe key=%s",
            getattr(universe, "key", None),
        )
        return WikipediaUniverseProvider()
    if provider in {"static", "static_list", "static-list"}:
        return StaticListUniverseProvider()
    raise RuntimeError(
        f"Unknown symbol universe provider '{universe.provider}'. "
        "Supported providers: wikipedia, static"
    )
