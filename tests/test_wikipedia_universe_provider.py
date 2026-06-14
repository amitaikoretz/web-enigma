from __future__ import annotations

from types import SimpleNamespace

import httpx

from app.universes.providers import WikipediaUniverseProvider


class _FakeClient:
    def __init__(self, responses: list[httpx.Response]) -> None:
        self._responses = list(responses)
        self.urls: list[str] = []
        self.headers: list[dict[str, str] | None] = []

    def __enter__(self) -> "_FakeClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        return None

    def get(  # noqa: ARG002
        self,
        url: str,
        *,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        self.urls.append(url)
        self.headers.append(headers)
        if not self._responses:
            raise AssertionError("No fake responses left")
        return self._responses.pop(0)


def test_wikipedia_provider_parses_symbol_column_and_normalizes(monkeypatch) -> None:
    provider = WikipediaUniverseProvider()

    wiki_html = """
    <html><body>
      <table class="wikitable">
        <tr><th>Company</th><th>Symbol</th></tr>
        <tr><td>Apple</td><td>aapl</td></tr>
        <tr><td>Berkshire</td><td>BRK.B</td></tr>
      </table>
    </body></html>
    """.strip()
    wiki_200 = httpx.Response(200, text=wiki_html)
    fake_client = _FakeClient([wiki_200])

    def _fake_httpx_client(*, timeout: float) -> _FakeClient:  # noqa: ARG001
        return fake_client

    monkeypatch.setattr(httpx, "Client", _fake_httpx_client)

    universe = SimpleNamespace(provider_ref={"kind": "dow30"}, key="dow30")
    members = provider.fetch_membership(universe, as_of=None)  # type: ignore[arg-type]

    assert members == {"AAPL", "BRK.B"}
    assert fake_client.urls == ["https://en.wikipedia.org/wiki/Dow_Jones_Industrial_Average"]
    assert fake_client.headers and fake_client.headers[0] and fake_client.headers[0].get("User-Agent")


def test_wikipedia_provider_uses_configured_user_agent(monkeypatch) -> None:
    monkeypatch.setenv("BACKTEST_WIKIPEDIA_USER_AGENT", "bt-tests/1.0 (test)")
    provider = WikipediaUniverseProvider()

    wiki_html = """
    <html><body>
      <table class="wikitable">
        <tr><th>Symbol</th></tr>
        <tr><td>AAPL</td></tr>
      </table>
    </body></html>
    """.strip()
    wiki_200 = httpx.Response(200, text=wiki_html)
    fake_client = _FakeClient([wiki_200])

    def _fake_httpx_client(*, timeout: float) -> _FakeClient:  # noqa: ARG001
        return fake_client

    monkeypatch.setattr(httpx, "Client", _fake_httpx_client)

    universe = SimpleNamespace(provider_ref={"kind": "dow30"}, key="dow30")
    provider.fetch_membership(universe, as_of=None)  # type: ignore[arg-type]

    assert fake_client.headers and fake_client.headers[0] == {"User-Agent": "bt-tests/1.0 (test)"}


def test_wikipedia_provider_errors_when_no_symbols_found(monkeypatch) -> None:
    provider = WikipediaUniverseProvider()
    wiki_200 = httpx.Response(200, text="<html><body><p>no tables</p></body></html>")
    fake_client = _FakeClient([wiki_200])

    def _fake_httpx_client(*, timeout: float) -> _FakeClient:  # noqa: ARG001
        return fake_client

    monkeypatch.setattr(httpx, "Client", _fake_httpx_client)

    universe = SimpleNamespace(provider_ref={"kind": "dow30"}, key="dow30")
    try:
        provider.fetch_membership(universe, as_of=None)  # type: ignore[arg-type]
    except RuntimeError as exc:
        assert "Wikipedia constituents parse failed" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError")
