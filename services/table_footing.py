"""Financial-table footing verification for the Cachet deterministic engine.

Every detector shipped before this one compares TWO surfaces of one fact: a
spelled word against its numeral, a date range against a stated duration, one
binding of a defined term against another. This module is the engine's first
N-ARY primitive: given a textual table whose rows carry line items and whose
Total / Subtotal row states an aggregate, it verifies that the column FOOTS --
that the stated total equals the exact sum of its parts. Summing a dozen
figures is arithmetic an LLM does slowly and unreliably and a deterministic
engine does with certainty.

The precision contract mirrors the fact-ledger family exactly:

* EXACT ARITHMETIC ONLY. Figures parse to ``decimal.Decimal`` (never float),
  honoring thousands separators, currency symbols and codes, parenthesized
  negatives, and the k / M / mm / bn / thousand / million / billion magnitude
  suffixes -- each an exact closed-form multiplier, so ``$1.5M + $500k =
  $2,000,000`` is provable, not approximated. There is no division anywhere.
* CONTRADICTED ONLY WHEN PROVABLE. ``contradicted`` is emitted only when the
  line items and the stated total are unambiguously part of one contiguous
  table region, every involved figure parses exactly, all figures share one
  currency (one explicit currency plus bare numbers follows the standard
  accounting column convention and coalesces; two explicit currencies refuse),
  and EVERY defensible aggregation reading of the total yields the same sum,
  which provably differs from the stated figure. The finding names the stated
  total, the computed sum, and every line-item figure.
* REFUSE, NEVER GUESS. Mixed explicit currencies, an unparseable row inside
  the region, an elision marker (possible omitted line items), a subtotal
  chain whose defensible readings disagree, more than one numeric column, and
  a percentage row mixed into a monetary column each yield
  ``could_not_verify`` naming the specific reason. An all-percentage table is
  SILENT: percentage columns are rounded by convention (62.5 + 24.1 + 13.3
  printed against a stated 100), so a footing accusation there is never safe.
* ZERO GREEN. ``TableFootingFinding.__post_init__`` rejects any verdict
  outside {"contradicted", "could_not_verify"}; a table that foots produces
  NO output at all. Silence is the consistent-input output.
* NEVER ACCUSE A FAITHFUL COPY. When the source text carries the same broken
  table verbatim (or the caller passes ``verbatim_run_present=True``), the
  defect originates in the source, not the draft, and the verdict is
  ``could_not_verify`` locating it there, exactly like the sibling detectors.

Table detection is deliberately conservative. A row is a line whose trailing
cell -- set off by a tab, two-plus spaces, a dot leader glued to the label, or
markdown pipes -- parses IN FULL as a figure. Prose never qualifies: sentence
text separates words with single spaces, and a trailing cell that is not
exactly a figure is not a row, so a stray number in running text near a table
cannot join the column. A blank or prose line closes the region; an
all-dash / all-equals rule line is neutral, so a ruled-off total row stays
attached to its items. A total row separated from its items by a blank line
is deliberately NOT checked (a silent miss beats a mis-scoped accusation).

Aggregation semantics guard against the two classic false accusations:

* stacked tables with no blank line between them -- a plain ``Total`` after an
  earlier total row is additionally read as totalling only the rows since that
  earlier total, so two independent footing tables never merge into one wrong
  sum;
* subtotal chains -- a total following subtotals is read both as the sum of
  every leaf item and as the subtotal chain (prior totals plus trailing
  items). Only when every defensible reading agrees on one sum that differs
  from the stated figure does the engine accuse; readings that disagree yield
  a refusal naming each candidate sum. An explicit ``Grand Total`` drops the
  segment-only reading, because "grand" states document-wide scope.

Pure stdlib (``re``, ``decimal``, ``dataclasses``); no network, no LLM, no
I/O, no learned weights. Scanning regex quantifiers are bounded (CWE-1333
hardening). Standalone: no imports from any sibling detector, ZERO edits to
sealed surfaces.

    from services.table_footing import detect_footing_conflicts

    for f in detect_footing_conflicts(document_text):
        print(f["verdict"], f["detail"])
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from decimal import Decimal, localcontext

__all__ = [
    "ALLOWED_VERDICTS",
    "CONTRADICTED",
    "COULD_NOT_VERIFY",
    "Figure",
    "TableFootingFinding",
    "detect_footing_conflicts",
    "parse_figure",
]

# --- Verdict vocabulary (identical to the fact-ledger family; no green) -------

CONTRADICTED = "contradicted"
COULD_NOT_VERIFY = "could_not_verify"
ALLOWED_VERDICTS = frozenset({CONTRADICTED, COULD_NOT_VERIFY})

_MAX_TEXT = 2_000_000  # same input bound the fact-ledger family enforces
_PRECISION = 60  # Decimal context digits; all ops are + and *, so this is exact

# --- Figure grammar (bounded) --------------------------------------------------

_MAG = {
    "k": 1_000,
    "thousand": 1_000,
    "m": 1_000_000,
    "mm": 1_000_000,
    "million": 1_000_000,
    "b": 1_000_000_000,
    "bn": 1_000_000_000,
    "billion": 1_000_000_000,
}
_MAG_ALT = "thousand|million|billion|mm|bn|k|b|m"
# Bare (currency-less) numbers accept only the unambiguous full magnitude words:
# a bare "5 m" could be metres, but "$5m" and "5 million" cannot.
_WORD_MAG_ALT = "thousand|million|billion"

_SYM_TO_CCY = {"$": "usd", "US$": "usd", "€": "eur", "£": "gbp"}
_CCY_SYMBOL = {"usd": "$", "eur": "€", "gbp": "£"}
_WORD_TO_CCY = {"dollar": "usd", "euro": "eur", "pound": "gbp"}

_NUM_SRC = r"(?:\d{1,3}(?:,\d{3}){1,6}|\d{1,15})(?:\.\d{1,6})?"

_MONEY_RE = re.compile(
    rf"(?:(?P<sym>US\$|\$|€|£)|(?P<code>USD|EUR|GBP))\s{{0,2}}(?P<num>{_NUM_SRC})"
    rf"(?:\s{{0,1}}(?P<mag>{_MAG_ALT}))?"
    rf"|(?P<num2>{_NUM_SRC})(?:\s{{0,1}}(?P<mag2>{_MAG_ALT}))?"
    rf"\s{{1,2}}(?P<code2>USD|EUR|GBP|dollars?|euros?|pounds?)",
    re.IGNORECASE,
)
_PERCENT_RE = re.compile(rf"(?P<num>{_NUM_SRC})\s{{0,1}}(?:%|percent)", re.IGNORECASE)
_BARE_RE = re.compile(rf"(?P<num>{_NUM_SRC})(?:\s{{1,2}}(?P<mag>{_WORD_MAG_ALT}))?", re.IGNORECASE)
_PAREN_RE = re.compile(r"\((?P<inner>[^()]{1,60})\)")


@dataclass(frozen=True)
class Figure:
    """One table cell reduced to an exact Decimal value."""

    kind: str  # "money" | "bare" | "percent"
    currency: str | None  # ISO-ish lowercase code for money figures, else None
    value: Decimal  # exact; negative when parenthesized or minus-signed
    verbatim: str  # the cell text as written


def parse_figure(cell: str) -> Figure | None:
    """Parse one cell into an exact ``Figure``, or ``None`` when unparseable.

    Honors thousands separators, currency symbols / codes / words,
    parenthesized negatives, a leading minus, and magnitude suffixes with
    exact closed-form multipliers. Anything else -- malformed digit groups,
    stray letters, empty text -- returns ``None`` rather than a guess.
    """
    if not isinstance(cell, str):
        raise TypeError(f"cell must be str, got {type(cell).__name__}")
    verbatim = cell.strip()
    s = verbatim.rstrip(".:;,")
    neg = False
    paren = _PAREN_RE.fullmatch(s)
    if paren:
        neg = True
        s = paren.group("inner").strip()
    if s[:1] in {"-", "−"}:
        neg = not neg
        s = s[1:].lstrip()
    if not s:
        return None
    with localcontext() as ctx:
        ctx.prec = _PRECISION
        m = _MONEY_RE.fullmatch(s)
        if m:
            num = m.group("num") or m.group("num2")
            mag = m.group("mag") or m.group("mag2")
            value = Decimal(num.replace(",", ""))
            if mag:
                value *= _MAG[mag.lower()]
            if m.group("sym"):
                ccy = _SYM_TO_CCY[m.group("sym").upper()]
            elif m.group("code"):
                ccy = m.group("code").lower()
            else:
                word = m.group("code2").lower()
                ccy = word if word in {"usd", "eur", "gbp"} else _WORD_TO_CCY[word.rstrip("s")]
            return Figure("money", ccy, -value if neg else value, verbatim)
        m = _PERCENT_RE.fullmatch(s)
        if m:
            value = Decimal(m.group("num").replace(",", ""))
            return Figure("percent", None, -value if neg else value, verbatim)
        m = _BARE_RE.fullmatch(s)
        if m:
            value = Decimal(m.group("num").replace(",", ""))
            if m.group("mag"):
                value *= _MAG[m.group("mag").lower()]
            return Figure("bare", None, -value if neg else value, verbatim)
    return None


# --- Line grammar ---------------------------------------------------------------

# Cell separator: a tab, a run of two-plus spaces, or a dot leader GLUED to the
# label ("Travel....$2,500"). The glue requirement (lookbehind for non-space)
# keeps a prose ellipsis (" ... ") from splitting a sentence into fake cells.
_SEP_SPLIT = re.compile(r"\t|[ ]{2,}|(?<=\S)\.{2,80}\s{0,2}")
_ELISION_RE = re.compile(
    r"\.{3,80}|…|\[\s?\.{3,10}\s?\]|\[…\]|\(continued\)|continued|\(cont'd\)|etc\.?",
    re.IGNORECASE,
)
_RULE_CHARS = frozenset("-=_ ")
_MDSEP_CHARS = frozenset("|-:+= ")

_SUBTOTAL_ANY = re.compile(r"\bsub[\s-]{0,1}totals?\b", re.IGNORECASE)
_GRAND_ANY = re.compile(r"\bgrand\s{1,3}totals?\b", re.IGNORECASE)
_TOTAL_ANY = re.compile(r"\btotals?\b", re.IGNORECASE)
_SUM_LEAD = re.compile(r"^[\W_]{0,6}sum(?![A-Za-z])", re.IGNORECASE)


def _total_kind(label: str) -> str | None:
    """Classify a row label as subtotal / grand / total, or None for an item."""
    if _SUBTOTAL_ANY.search(label):
        return "subtotal"
    if _GRAND_ANY.search(label):
        return "grand"
    if _TOTAL_ANY.search(label):
        return "total"
    if _SUM_LEAD.match(label):
        return "total"
    return None


@dataclass
class _Row:
    label: str
    figure: Figure
    extra_numeric: int  # figure-parseable cells besides the label and the summed cell
    total_kind: str | None  # None | "subtotal" | "total" | "grand"
    line_no: int
    raw: str


@dataclass
class _Region:
    rows: list[_Row]
    bad: list[tuple[int, str]]  # rowlike lines whose trailing cell failed to parse
    elisions: list[int]  # line numbers of elision markers touching this region
    start: int


def _scan_regions(lines: list[str]) -> list[_Region]:
    """Group contiguous table rows into regions, tracking poison markers.

    Blank and prose lines close the current region. Rule lines (all dashes /
    equals) and markdown separators are neutral. An elision marker keeps the
    region open but flags it incomplete. A row-shaped line whose trailing cell
    contains digits but fails to parse stays in the region as a poison marker
    (splitting there could detach items from their total and mis-scope a sum).
    """
    regions: list[_Region] = []
    cur: _Region | None = None
    pending_elision = False

    def close() -> None:
        nonlocal cur
        if cur is not None and cur.rows:
            regions.append(cur)
        cur = None

    def open_or_get(line_no: int) -> _Region:
        nonlocal cur, pending_elision
        if cur is None:
            cur = _Region(rows=[], bad=[], elisions=[], start=line_no)
            if pending_elision:
                cur.elisions.append(line_no)
            pending_elision = False
        return cur

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            close()  # a blank breaks the region; a pending elision survives it
            continue
        chars = set(stripped)
        if chars <= _RULE_CHARS:
            continue  # ruled-off separator line: neutral
        if _ELISION_RE.fullmatch(stripped):
            if cur is not None:
                cur.elisions.append(i)
            else:
                pending_elision = True
            continue
        if "|" in stripped:
            if chars <= _MDSEP_CHARS and "-" in chars:
                continue  # markdown header separator: neutral
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            cells = [c for c in cells if c]
            if not cells:
                continue
            fig = parse_figure(cells[-1])
            if fig is None:
                if cur is not None:
                    cur.bad.append((i, line))  # a non-figure pipe row mid-table poisons
                continue  # before any row it is a header; skip
        else:
            cells = [c.strip() for c in _SEP_SPLIT.split(stripped)]
            cells = [c for c in cells if c]
            if len(cells) < 2:
                close()
                pending_elision = False
                continue
            fig = parse_figure(cells[-1])
            if fig is None:
                if cur is not None and any(ch.isdigit() for ch in cells[-1]):
                    cur.bad.append((i, line))
                    continue
                close()
                pending_elision = False
                continue
        label = " ".join(cells[:-1])
        extra = sum(1 for c in cells[1:-1] if parse_figure(c) is not None)
        region = open_or_get(i)
        region.rows.append(_Row(label, fig, extra, _total_kind(label), i, line))
    close()
    return regions


# --- Finding shape ---------------------------------------------------------------


@dataclass(frozen=True)
class TableFootingFinding:
    """One verdict this detector adds. Never a green one.

    ``__post_init__`` makes the zero-green invariant structural: constructing a
    finding with any verdict outside ``ALLOWED_VERDICTS`` raises.
    """

    verdict: str  # "contradicted" | "could_not_verify"
    kind: str
    total_label: str  # label of the stated-total row
    stated_total: str  # verbatim figure text of the stated total
    computed_sum: str | None  # rendered exact sum, None when no single sum is provable
    detail: str
    rows: tuple  # per-row dicts: label, figure, value, line, role

    def __post_init__(self) -> None:
        if self.verdict not in ALLOWED_VERDICTS:
            raise ValueError(
                f"table_footing can only emit {sorted(ALLOWED_VERDICTS)}; "
                f"got {self.verdict!r}. It has no green output state by design."
            )


def _fmt_amount(value: Decimal, currency: str | None) -> str:
    """Render an exact Decimal with thousands separators and a currency symbol."""
    if value == value.to_integral_value():
        value = value.quantize(Decimal(1))
    else:
        value = value.normalize()
    body = format(abs(value), ",f")
    sign = "-" if value < 0 else ""
    sym = _CCY_SYMBOL.get(currency or "", "")
    return f"{sign}{sym}{body}"


def _payloads(rows: list[_Row]) -> tuple:
    return tuple(
        {
            "label": r.label,
            "figure": r.figure.verbatim,
            "value": _fmt_amount(r.figure.value, None),
            "line": r.line_no,
            "role": r.total_kind or "item",
        }
        for r in rows
    )


def _figure_phrase(rows: list[_Row]) -> str:
    return "; ".join(f"'{r.figure.verbatim}' ({r.label or 'unlabelled'})" for r in rows)


def _sum(rows: list[_Row]) -> Decimal:
    with localcontext() as ctx:
        ctx.prec = _PRECISION
        total = Decimal(0)
        for r in rows:
            total += r.figure.value
        return total


def _ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


# --- Disposition -------------------------------------------------------------------


def _refusal(kind: str, t: _Row, rows: list[_Row], detail: str) -> TableFootingFinding:
    return TableFootingFinding(
        verdict=COULD_NOT_VERIFY,
        kind=kind,
        total_label=t.label,
        stated_total=t.figure.verbatim,
        computed_sum=None,
        detail=detail,
        rows=_payloads(rows),
    )


def _check_region(
    region: _Region,
    lines: list[str],
    source: str,
    verbatim_override: bool | None,
) -> list[TableFootingFinding]:
    rows = region.rows
    totals = [r for r in rows if r.total_kind is not None]
    if not totals:
        return []
    if all(r.figure.kind == "percent" for r in rows):
        # Percentage tables are rounded by convention; a footing accusation
        # there can never be safe. Deliberate scope-out: silent.
        return []
    findings: list[TableFootingFinding] = []
    for t in totals:
        prior = [r for r in rows if r.line_no < t.line_no]
        items = [r for r in prior if r.total_kind is None]
        prior_totals = [r for r in prior if r.total_kind is not None]
        if not items:
            continue
        item_figs = _figure_phrase(items)
        stated_txt = t.figure.verbatim

        bad_before = [b for b in region.bad if b[0] < t.line_no]
        if bad_before:
            bad_txt = "; ".join(f"'{raw.strip()}' (line {ln + 1})" for ln, raw in bad_before)
            findings.append(
                _refusal(
                    "table_footing_unparseable_row",
                    t,
                    items + [t],
                    f"A row inside this table region cannot be parsed as a figure: {bad_txt}. "
                    f"The line items therefore cannot be summed against the stated total "
                    f"'{stated_txt}'. Parseable line items: {item_figs}. The engine refuses "
                    "rather than guess.",
                )
            )
            break
        if any(e < t.line_no for e in region.elisions):
            findings.append(
                _refusal(
                    "table_footing_possible_omission",
                    t,
                    items + [t],
                    "An elision marker inside this table region means line items may be "
                    f"omitted, so the stated total '{stated_txt}' cannot be checked against a "
                    f"provably complete set of line items. Visible line items: {item_figs}. "
                    "The engine refuses rather than guess.",
                )
            )
            break
        if any(r.extra_numeric >= 1 for r in items + [t]):
            findings.append(
                _refusal(
                    "table_footing_multi_column",
                    t,
                    items + [t],
                    "Rows in this table carry more than one numeric column, and the engine "
                    f"cannot prove which column the stated total '{stated_txt}' aggregates "
                    "(a quantity or unit-price column summed as amounts would mint a false "
                    f"accusation). Line items seen: {item_figs}. The engine refuses rather "
                    "than guess.",
                )
            )
            break

        kinds = {r.figure.kind for r in items} | {t.figure.kind}
        if "percent" in kinds:
            if kinds == {"percent"}:
                continue  # an all-percent segment: same rounding scope-out, silent
            findings.append(
                _refusal(
                    "table_footing_mixed_kinds",
                    t,
                    items + [t],
                    "This table mixes percentage figures into a monetary column, so the "
                    f"stated total '{stated_txt}' is not the sum of comparable figures (a "
                    "percentage's base amount is not stated). Line items: "
                    f"{item_figs}. The engine refuses rather than guess.",
                )
            )
            continue
        currencies = {r.figure.currency for r in items + [t] if r.figure.currency}
        if len(currencies) >= 2:
            names = ", ".join(sorted(c.upper() for c in currencies))
            findings.append(
                _refusal(
                    "table_footing_mixed_currency",
                    t,
                    items + [t],
                    f"This table mixes currencies ({names}), and no exact conversion exists, "
                    f"so the line items cannot be summed against the stated total "
                    f"'{stated_txt}'. Line items: {item_figs}. The engine refuses rather "
                    "than guess.",
                )
            )
            continue
        currency = next(iter(currencies)) if currencies else None

        # Defensible aggregation readings of this total row.
        last_total_ln = max((p.line_no for p in prior_totals), default=-1)
        segment = [r for r in items if r.line_no > last_total_ln]
        readings: dict[Decimal, str] = {}
        if t.total_kind == "subtotal" or not prior_totals:
            if len(segment) < 2:
                continue  # a totalling claim over fewer than two rows is not provable
            named = segment
            readings[_sum(segment)] = "the line items above"
        else:
            named = items
            readings[_sum(items)] = "the sum of every line item"
            readings.setdefault(
                _sum(prior_totals) + _sum(segment),
                "the prior subtotal/total rows plus the items after them",
            )
            if t.total_kind == "total" and segment:
                readings.setdefault(_sum(segment), "the items since the previous total row")

        stated = t.figure.value
        if stated in readings:
            continue  # the table foots under a defensible reading: SILENT
        if len(readings) > 1:
            candidates = "; ".join(
                f"{desc} = {_fmt_amount(total, currency)}" for total, desc in readings.items()
            )
            findings.append(
                _refusal(
                    "table_footing_ambiguous_aggregation",
                    t,
                    items + prior_totals + [t],
                    f"The stated total '{stated_txt}' matches none of the defensible "
                    f"aggregation readings of this table, and the readings disagree with each "
                    f"other: {candidates}. The subtotal chain is ambiguous, so no single "
                    "computed sum is provable. The engine names each candidate and refuses "
                    "rather than guess.",
                )
            )
            continue

        computed = next(iter(readings))
        involved = named + prior_totals + [t]
        span = "\n".join(lines[min(r.line_no for r in involved) : t.line_no + 1])
        verbatim = verbatim_override
        if verbatim is None:
            verbatim = bool(source) and _ws(span) in _ws(source)
        if verbatim:
            findings.append(
                TableFootingFinding(
                    verdict=COULD_NOT_VERIFY,
                    kind="table_footing_source_defect",
                    total_label=t.label,
                    stated_total=stated_txt,
                    computed_sum=_fmt_amount(computed, currency),
                    detail=(
                        f"This table's stated total '{stated_txt}' does not equal the sum of "
                        f"its line items ({_fmt_amount(computed, currency)}), but the source "
                        "carries the same table verbatim, so the footing defect originates in "
                        "the source, not the draft. Line items: "
                        f"{_figure_phrase(named)}. Review which figure was intended.",
                    ),
                    rows=_payloads(involved),
                )
            )
            continue
        findings.append(
            TableFootingFinding(
                verdict=CONTRADICTED,
                kind="table_footing_mismatch",
                total_label=t.label,
                stated_total=stated_txt,
                computed_sum=_fmt_amount(computed, currency),
                detail=(
                    f"This table does not foot: the stated total '{stated_txt}' in row "
                    f"'{t.label}' equals {_fmt_amount(stated, currency)}, but the line items "
                    f"sum to {_fmt_amount(computed, currency)} (difference "
                    f"{_fmt_amount(stated - computed, currency)}). Line items summed: "
                    f"{_figure_phrase(named)}. Every figure parses exactly and shares one "
                    "currency convention, so the arithmetic is provable; the engine does not "
                    "decide which figure is wrong."
                ),
                rows=_payloads(involved),
            )
        )
    return findings


def detect_footing_conflicts(
    text: str,
    source: str = "",
    *,
    verbatim_run_present: bool | None = None,
) -> list[dict]:
    """Check every table region's stated totals; return non-green findings only.

    Returns ``[]`` when every detected table foots, when no table-like region
    with a total row exists, and for all-percentage tables (rounding
    scope-out). Otherwise each finding is exactly one of:

    * ``contradicted`` -- the region is unambiguous, every figure parses, one
      currency governs, every defensible aggregation reading yields the same
      exact sum, and that sum provably differs from the stated total. The
      detail names the stated total, the computed sum, and every line item.
    * ``could_not_verify`` -- something blocks proof (mixed currencies, an
      unparseable row, a possible omitted line item, an ambiguous subtotal
      chain, a multi-numeric-column layout, percentages mixed into money, or
      a source that carries the same broken table verbatim), named
      specifically. Never a guess, never a green.

    Deterministic: same input, same output, byte for byte.
    """
    if not isinstance(text, str):
        raise TypeError(f"text must be str, got {type(text).__name__}")
    if not isinstance(source, str):
        raise TypeError(f"source must be str, got {type(source).__name__}")
    if len(text) > _MAX_TEXT:
        raise ValueError(f"text exceeds the {_MAX_TEXT}-char table-footing bound")
    lines = text.splitlines()
    findings: list[TableFootingFinding] = []
    for region in _scan_regions(lines):
        findings.extend(_check_region(region, lines, source, verbatim_run_present))
    return [asdict(f) for f in findings]
