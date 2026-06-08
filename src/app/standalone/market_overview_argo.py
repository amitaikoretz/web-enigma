from __future__ import annotations

import json
import shlex
import sys
from datetime import UTC, datetime
from pathlib import Path

import typer

from app.backtests.argo_step_errors import run_typer_app_with_argo_error_outputs

app = typer.Typer(add_completion=False, no_args_is_help=True)


def _write_text(path: str | None, text: str) -> None:
    if not path:
        return
    Path(path).write_text(text, encoding="utf-8")


def _terminal_command(argv: list[str]) -> str:
    return " ".join(shlex.quote(arg) for arg in argv)


@app.command(help="Generate a market-overview snapshot artifact for Argo.")
def main(
    snapshot_id: str = typer.Option(..., "--snapshot-id"),
    output_path: str = typer.Option(..., "--output-path"),
    terminal_command_out: str = typer.Option("/tmp/terminal-command.txt", "--terminal-command-out"),
) -> None:
    _write_text(terminal_command_out, _terminal_command(sys.argv))
    now = datetime.now(UTC)
    payload = {
        "snapshot_id": snapshot_id,
        "status": "completed",
        "top_regime": "Narrow risk-on / fragile bull",
        "probabilities": {
            "Narrow risk-on / fragile bull": 0.71,
            "Goldilocks risk-on": 0.12,
            "Late-cycle risk-on": 0.09,
            "Range / neutral": 0.08,
        },
        "confidence": 71.0,
        "fragility": 64.0,
        "contradiction_score": 18.0,
        "market_indicators": [
            {
                "key": "spx",
                "label": "S&P 500",
                "value": "+0.8%",
                "change": "+1.2% 1D",
                "tone": "positive",
                "category": "equities",
                "note": "Above 50D and 200D moving averages.",
                "explanation": {
                    "summary": "Headline equity trend gauge built from the S&P 500 cash index and its relationship to medium- and long-term trend filters.",
                    "inputs": ["S&P 500 close", "Prior close", "50-day moving average", "200-day moving average"],
                    "calculation_steps": [
                        "Measure the latest session return from the index close-to-close move.",
                        "Compare spot price with the 50D and 200D moving averages to classify trend alignment.",
                        "Assign a positive tone when price is above both averages and the daily move is constructive.",
                    ],
                    "interpretation": "This stays positive when the broad U.S. equity benchmark is trending higher and holding its long-term trend structure.",
                    "freshness": "Uses the most recent daily close; confidence should be discounted if the market close is stale.",
                    "caveats": ["A strong headline index can still hide weak internal breadth or concentrated leadership."],
                },
            },
            {
                "key": "ndx",
                "label": "Nasdaq 100",
                "value": "+1.1%",
                "change": "+1.5% 1D",
                "tone": "positive",
                "category": "equities",
                "note": "Leadership remains concentrated in long-duration growth.",
                "explanation": {
                    "summary": "Growth-heavy equity leadership signal that highlights how much of the tape is still being carried by large-cap technology and communications names.",
                    "inputs": ["Nasdaq 100 close", "Prior close", "Sector contribution mix", "Large-cap growth relative strength"],
                    "calculation_steps": [
                        "Compute the daily index return and relative strength versus the S&P 500.",
                        "Check whether the move is concentrated in growth-heavy sectors or supported broadly.",
                        "Classify the tone as positive when growth leadership is still driving index gains.",
                    ],
                    "interpretation": "Positive readings mean growth leadership is still supporting risk appetite and keeping the benchmark in a constructive trend.",
                    "freshness": "Based on the latest market close and updated whenever constituent pricing refreshes.",
                    "caveats": ["Concentrated leadership can improve index returns while increasing regime fragility."],
                },
            },
            {
                "key": "rut",
                "label": "Russell 2000",
                "value": "-0.2%",
                "change": "-0.4% 1D",
                "tone": "negative",
                "category": "equities",
                "note": "Small caps lag broader equity benchmarks.",
                "explanation": {
                    "summary": "Small-cap barometer used to show whether domestic risk appetite is broadening beyond the mega-cap complex.",
                    "inputs": ["Russell 2000 close", "Prior close", "Relative performance versus S&P 500", "Small-cap leadership trend"],
                    "calculation_steps": [
                        "Measure the daily Russell 2000 return.",
                        "Compare performance to the S&P 500 to detect leadership breadth.",
                        "Flag a negative tone when small caps lag while the larger cap benchmark is firmer.",
                    ],
                    "interpretation": "Weakness here usually means participation is narrow and the market may be relying on a smaller set of large-cap winners.",
                    "freshness": "Uses the latest close; a lagging small-cap tape becomes more meaningful when it persists across several sessions.",
                    "caveats": ["One-day weakness can be noise, but repeated underperformance is a breadth warning."],
                },
            },
            {
                "key": "ew-vs-cap",
                "label": "Equal-weight vs cap-weight",
                "value": "-0.6%",
                "change": "-0.3% 1D",
                "tone": "warning",
                "category": "breadth",
                "note": "Breadth is narrowing as the index advances.",
                "explanation": {
                    "summary": "Breadth proxy that compares equal-weight performance against cap-weight performance to show whether gains are broad or concentrated.",
                    "inputs": ["Equal-weight index close", "Cap-weight index close", "Relative return spread", "Trend of the spread"],
                    "calculation_steps": [
                        "Compute the return of the equal-weight basket and the cap-weight index over the same lookback.",
                        "Take the spread between the two returns to isolate participation breadth.",
                        "Label the indicator warning when cap-weight outperforms consistently.",
                    ],
                    "interpretation": "A negative spread means a narrow rally where the biggest names are doing more of the lifting.",
                    "freshness": "Best interpreted with fresh closes and a short rolling window so the spread reflects recent participation.",
                    "caveats": ["This can lag intraday leadership changes and should be checked alongside advance/decline data."],
                },
            },
            {
                "key": "advance-decline",
                "label": "Advance / decline",
                "value": "1.2x",
                "change": "Improving",
                "tone": "positive",
                "category": "breadth",
                "note": "Participation is still positive, but less broad than price action.",
                "explanation": {
                    "summary": "Classic breadth ratio showing how many constituents are advancing versus declining across the tracked universe.",
                    "inputs": ["Advancers count", "Decliners count", "Universe membership", "Session change"],
                    "calculation_steps": [
                        "Count the number of advancing and declining securities in the universe.",
                        "Form the advance/decline ratio and compare it with recent sessions.",
                        "Classify the tone as positive when advancers outnumber decliners and the ratio is improving.",
                    ],
                    "interpretation": "Positive breadth means participation is healthy; a weakening ratio warns that the rally may be losing internal support.",
                    "freshness": "Should be refreshed each trading session; stale breadth data can lag the tape by one day.",
                    "caveats": ["The ratio can look healthy even when a few large names dominate index performance."],
                },
            },
            {
                "key": "new-highs-lows",
                "label": "New highs / lows",
                "value": "84 / 21",
                "change": "+11 net",
                "tone": "positive",
                "category": "breadth",
                "note": "New highs remain firm despite weaker small-cap follow-through.",
                "explanation": {
                    "summary": "Breadth momentum indicator that counts the number of securities making new highs versus new lows over the lookback window.",
                    "inputs": ["52-week highs count", "52-week lows count", "Universe definition", "Lookback window"],
                    "calculation_steps": [
                        "Count new highs and new lows over the chosen window.",
                        "Subtract lows from highs to create a net breadth reading.",
                        "Reward positive tones when highs expand faster than lows.",
                    ],
                    "interpretation": "A wide margin of new highs over lows confirms participation; a shrinking margin often precedes regime fatigue.",
                    "freshness": "Should be computed from the latest daily listing so the net breadth read is current.",
                    "caveats": ["The indicator can be noisy around rebalance periods or holiday-shortened sessions."],
                },
            },
            {
                "key": "vix",
                "label": "VIX",
                "value": "13.9",
                "change": "-0.8 pts",
                "tone": "positive",
                "category": "volatility",
                "note": "Volatility is contained, consistent with a risk-on backdrop.",
                "explanation": {
                    "summary": "Implied-volatility stress gauge derived from S&P 500 option pricing and used as a proxy for market fear and uncertainty.",
                    "inputs": ["VIX index level", "Near-term SPX option implied vol", "Term structure trend", "Recent volatility change"],
                    "calculation_steps": [
                        "Take the market-implied forward volatility embedded in S&P 500 options.",
                        "Compare the level against recent history and the term structure.",
                        "Mark the tone positive when implied volatility is compressed and declining.",
                    ],
                    "interpretation": "Low or falling VIX usually confirms calm risk sentiment; rising VIX is an early warning that the tape is getting nervous.",
                    "freshness": "Should track real-time option market pricing; stale readings can understate intraday stress.",
                    "caveats": ["A low VIX can reflect complacency rather than durable stability."],
                },
            },
            {
                "key": "two-year-yield",
                "label": "2Y Treasury",
                "value": "4.58%",
                "change": "+6 bps",
                "tone": "warning",
                "category": "rates",
                "note": "Short rates are repricing higher.",
                "explanation": {
                    "summary": "Front-end rates signal for Fed expectations and funding conditions, using the two-year Treasury yield as the benchmark.",
                    "inputs": ["2Y Treasury yield", "Daily yield change", "Recent policy repricing", "Short-rate trend"],
                    "calculation_steps": [
                        "Read the latest 2Y Treasury yield and day-over-day move.",
                        "Map the change to rate repricing pressure on discount rates and funding conditions.",
                        "Apply a warning tone when the front end rises quickly.",
                    ],
                    "interpretation": "Rising short rates usually tighten financial conditions and can pressure rate-sensitive risk assets.",
                    "freshness": "Should be refreshed with the most recent Treasury market close or intraday quote where available.",
                    "caveats": ["The two-year can rise for healthy growth reasons, so context matters."],
                },
            },
            {
                "key": "ten-year-yield",
                "label": "10Y Treasury",
                "value": "4.19%",
                "change": "+4 bps",
                "tone": "warning",
                "category": "rates",
                "note": "Higher real yields are pressuring long-duration assets.",
                "explanation": {
                    "summary": "Longer-duration discount-rate benchmark used to gauge the pressure that rates place on equity valuations and growth expectations.",
                    "inputs": ["10Y Treasury yield", "Daily yield change", "Real-yield trend", "Curve context"],
                    "calculation_steps": [
                        "Track the latest 10Y Treasury yield and its daily move.",
                        "Compare the change to recent real-yield and curve dynamics.",
                        "Warn when longer-duration rates are repricing higher in a way that can compress valuations.",
                    ],
                    "interpretation": "A rising 10Y yield often tightens valuation support for duration-heavy growth stocks and other long-duration assets.",
                    "freshness": "Use the latest Treasury data and update quickly when the market is repricing real rates.",
                    "caveats": ["The effect depends on whether the move is driven by growth optimism or inflation pressure."],
                },
            },
            {
                "key": "credit-spreads",
                "label": "Credit spreads",
                "value": "284 bps",
                "change": "Flat",
                "tone": "positive",
                "category": "credit",
                "note": "Credit remains orderly and supportive of risk assets.",
                "explanation": {
                    "summary": "Credit stress proxy that tracks investment-grade and high-yield spread behavior as a funding and default-risk signal.",
                    "inputs": ["HY spread", "IG spread", "Spread change", "Relative credit trend"],
                    "calculation_steps": [
                        "Measure the current credit spread level against benchmark Treasury yields.",
                        "Blend high-yield and investment-grade moves into a broad credit stress read.",
                        "Mark the tone positive when spreads are stable or tightening.",
                    ],
                    "interpretation": "Tight spreads usually support risk assets; widening spreads often lead equity stress when the market starts to worry about funding or defaults.",
                    "freshness": "Should reflect the most recent credit-market close and intraday moves when available.",
                    "caveats": ["Credit can stay calm even while equities get fragile, so it is one piece of the full picture."],
                },
            },
            {
                "key": "dxy",
                "label": "DXY",
                "value": "104.2",
                "change": "+0.2%",
                "tone": "neutral",
                "category": "fx",
                "note": "Dollar strength is not yet overriding equity momentum.",
                "explanation": {
                    "summary": "U.S. dollar index used as a cross-asset liquidity and global financial-conditions indicator.",
                    "inputs": ["DXY index level", "Daily return", "Trend versus recent range", "Dollar strength regime"],
                    "calculation_steps": [
                        "Track the dollar index relative to its recent trend and daily move.",
                        "Interpret strength as tighter global financial conditions and weakness as a supportive liquidity tailwind.",
                        "Classify neutral when the move is small and not decisive versus recent trend.",
                    ],
                    "interpretation": "A rising dollar can tighten conditions for risk assets and international liquidity; a steady dollar is usually less disruptive.",
                    "freshness": "Should be updated with the latest FX close or real-time quote when available.",
                    "caveats": ["The dollar’s impact depends on the broader macro regime and whether U.S. growth is outperforming."],
                },
            },
            {
                "key": "sector-leadership",
                "label": "Sector leadership",
                "value": "Tech / Comm. Services",
                "change": "Rotating",
                "tone": "warning",
                "category": "leadership",
                "note": "Leadership remains narrow and concentrated.",
                "explanation": {
                    "summary": "Sector rotation read that highlights which groups are leading the tape and whether participation is broadening or staying concentrated.",
                    "inputs": ["Sector relative strength", "Top sector contribution", "Breadth by sector", "Recent rotation changes"],
                    "calculation_steps": [
                        "Rank sector returns and relative strength over the chosen window.",
                        "Identify the sectors carrying the most index-level performance.",
                        "Treat concentrated leadership as a warning when only a few sectors dominate gains.",
                    ],
                    "interpretation": "Rotating leadership is healthier than a single crowded trade; persistent concentration raises fragility even when the index is rising.",
                    "freshness": "Best updated daily, with intraday changes useful for identifying whether leadership is broadening or narrowing.",
                    "caveats": ["Leadership can change quickly around earnings and macro releases."],
                },
            },
        ],
        "pillar_scores": {
            "trend": 1.0,
            "breadth": -1.0,
            "volatility": 0.5,
            "credit": 1.0,
            "rates": -1.0,
            "macro": 0.0,
            "earnings": 0.5,
        },
        "developments": [
            {
                "category": "policy repricing",
                "title": "Rates moved higher",
                "importance_score": 0.82,
                "market_reaction": {"rates": "up", "growth": "mixed"},
            },
            {
                "category": "breadth divergence",
                "title": "Participation weakened",
                "importance_score": 0.76,
                "market_reaction": {"breadth": "down", "equities": "stable"},
            },
        ],
        "freshness": {"market": now.isoformat(), "news": now.isoformat()},
        "summary_text": (
            "Equities remain in an uptrend and credit is calm, but participation is narrowing "
            "and higher yields are increasing vulnerability to a negative macro or policy surprise."
        ),
        "watch_next": [
            "Watch whether equal-weight breadth starts to confirm the cap-weight rally.",
            "Monitor the 2Y yield and VIX for signs that rate repricing is feeding into risk appetite.",
            "Track credit spreads for early signs that calm equity tape is losing support.",
        ],
        "methodology": {
            "summary": (
                "The overview blends cross-asset market indicators, breadth, volatility, credit, rates, "
                "macro, and earnings signals into a weighted regime read."
            ),
            "inputs": [
                "Major equity indices and relative breadth",
                "Volatility, credit, rates, and FX context",
                "Pillar scores for trend, breadth, and macro regime",
                "Recent developments ranked by market impact",
            ],
            "scoring": [
                "Each pillar contributes a normalized score that maps into the regime candidate set.",
                "Probability weights reflect agreement between price action, breadth, and cross-asset signals.",
                "Confidence rises when the top regime leads by a wide margin and freshness is good.",
                "Fragility rises when breadth narrows, yields rise, or the market becomes more concentrated.",
            ],
            "freshness": "Stale inputs reduce confidence and trigger the stale indicator when the last refresh ages out.",
            "caveats": [
                "The label is probabilistic, not deterministic.",
                "A strong index can still be fragile when participation is narrow.",
            ],
        },
        "evidence": {
            "trend": ["S&P 500 above 50D/200D"],
            "breadth": ["equal-weight lagging cap-weight"],
        },
        "params": {},
        "error_message": None,
        "name": None,
        "argo_namespace": None,
        "argo_workflow_name": None,
        "as_of": now.isoformat(),
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    typer.echo(json.dumps(payload))


if __name__ == "__main__":
    run_typer_app_with_argo_error_outputs(app)
