"""
Module-level token accumulator — one instance per Python process.
Call record() after every API response; call print_summary() at process exit.
"""
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List

# claude-sonnet-4-6 pricing (USD per token)
_PRICE_INPUT        = 3.00   / 1_000_000
_PRICE_OUTPUT       = 15.00  / 1_000_000
_PRICE_CACHE_WRITE  = 3.75   / 1_000_000
_PRICE_CACHE_READ   = 0.30   / 1_000_000

LOG_PATH = Path("data/token_usage_latest.jsonl")


@dataclass
class _Record:
    skill:          str
    input_tokens:   int
    output_tokens:  int
    cache_creation: int
    cache_read:     int
    ts:             float = field(default_factory=time.time)

    @property
    def cost_usd(self) -> float:
        billable_input = max(0, self.input_tokens - self.cache_read)
        return (
            billable_input      * _PRICE_INPUT
            + self.output_tokens   * _PRICE_OUTPUT
            + self.cache_creation  * _PRICE_CACHE_WRITE
            + self.cache_read      * _PRICE_CACHE_READ
        )


_records: List[_Record] = []


def record(skill: str, usage) -> None:
    """Append one API-call record. `usage` is the Anthropic Usage object."""
    r = _Record(
        skill          = skill,
        input_tokens   = getattr(usage, "input_tokens", 0),
        output_tokens  = getattr(usage, "output_tokens", 0),
        cache_creation = getattr(usage, "cache_creation_input_tokens", 0) or 0,
        cache_read     = getattr(usage, "cache_read_input_tokens", 0) or 0,
    )
    _records.append(r)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(r)) + "\n")


def print_summary(label: str = "") -> None:
    """Print a per-skill token and cost table to stdout."""
    if not _records:
        return

    # Aggregate by skill
    by_skill: dict = {}
    for r in _records:
        s = by_skill.setdefault(r.skill, dict(calls=0, inp=0, out=0, cw=0, cr=0, cost=0.0))
        s["calls"] += 1
        s["inp"]   += r.input_tokens
        s["out"]   += r.output_tokens
        s["cw"]    += r.cache_creation
        s["cr"]    += r.cache_read
        s["cost"]  += r.cost_usd

    title = f"Tokens API{' — ' + label if label else ''}"
    W = 84
    print(f"\n  ┌─ {title} {'─' * max(1, W - len(title) - 3)}┐")
    hdr = f"  {'Paso':<32} {'Calls':>5} {'Input':>9} {'Output':>8} {'Cache↑':>7} {'Cache↓':>7} {'USD':>8}"
    print(hdr)
    print("  " + "─" * W)

    total_cost  = 0.0
    total_calls = 0
    total_inp   = 0
    total_out   = 0

    for skill, s in by_skill.items():
        # Trim long class names gracefully
        name = skill if len(skill) <= 32 else skill[:29] + "..."
        print(
            f"  {name:<32} {s['calls']:>5} {s['inp']:>9,} {s['out']:>8,} "
            f"{s['cw']:>7,} {s['cr']:>7,} ${s['cost']:>7.4f}"
        )
        total_cost  += s["cost"]
        total_calls += s["calls"]
        total_inp   += s["inp"]
        total_out   += s["out"]

    print("  " + "─" * W)
    print(
        f"  {'TOTAL':<32} {total_calls:>5} {total_inp:>9,} {total_out:>8,} "
        f"{'':>7} {'':>7} ${total_cost:>7.4f}"
    )
    print(f"  └{'─' * W}┘")
