"""
postfilter.py — Indication / sub-type post-filters (molecules.md strategy notes).

A few monitored molecules must be narrowed AFTER extraction to a specific
indication or sub-type:

    Tadalafil   (PAH_OR_OPHTHALMIC)  keep PAH / ophthalmic, drop ED/BPH
    Bevacizumab (OPHTHALMIC)         keep ophthalmic, drop systemic oncology
    Ranibizumab (BIOSIMILAR)         keep biosimilars, drop the originator

The canonical schema has no indication column, so each row is judged from the text
fields we have plus an optional ``_indication_hint`` that indication-bearing
extractors thread through (it is never written to the CSV — the writer ignores
extra keys). For biologics, "applicant is not the originator" is itself decisive,
since you cannot make a generic (non-biosimilar) copy of a biologic.

Public API:
    apply_post_filters(rows, molecules) -> (kept_rows, dropped_counts)
        dropped_counts maps molecule_search_term -> number of rows removed.
"""

from __future__ import annotations

import re
import unicodedata

import config

# Text fields consulted when judging a row's indication / sub-type.
_TEXT_FIELDS = ["product_name", "api", "dosage_form", "concentration",
                "applicant", "_indication_hint"]


def _fold(value) -> str:
    """Lowercase and strip accents so 'oftálmico' matches 'oftalmico'."""
    if not value:
        return ""
    decomposed = unicodedata.normalize("NFKD", str(value))
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def _haystack(row: dict) -> str:
    return " ".join(_fold(row.get(f)) for f in _TEXT_FIELDS)


# A fixed-dose combination advertises itself with two strengths in the product name
# — "JARDIANCE DUO 12.5 MG / 1000 MG", "Efimax Dúo 12.5 / 850", "EMADIAN MET 5/1000".
# That pattern is the reliable tell in LATAM, because those registries normalize the
# active-ingredient column to the single INN that was searched ("EMPAGLIFLOZINA")
# whether the product is a monotherapy or a combination.
_DUAL_STRENGTH = re.compile(r"\d+([.,]\d+)?\s*(mg|mcg|g|ui|u)?\s*/\s*\d+", re.I)


def _is_combination(row: dict) -> bool:
    """True when the row is a fixed-dose combination rather than a single agent."""
    name = _fold(row.get("product_name"))
    api = _fold(row.get("api"))

    # FDA lists every ingredient, so a joined api is conclusive on its own.
    if " + " in api or ";" in api:
        return True
    # A second INN named outright, in either field.
    if any(partner in f"{name} {api}" for partner in _COMBINATION_PARTNERS):
        return True
    # Two strengths in the name.
    if _DUAL_STRENGTH.search(name):
        return True
    # Brand words registries use for their combination lines.
    return any(word in name for word in _COMBINATION_WORDS)


# Partners that appear alongside an SGLT2 inhibitor in marketed fixed-dose products.
_COMBINATION_PARTNERS = ("metformin", "linaglipt", "sitaglipt", "saxaglipt",
                         "glimepirid", "pioglitazon")
# Combination-line markers. Kept narrow: "duo", "complex" and "met" as a separate
# word, never a loose substring that would swallow ordinary brand names.
_COMBINATION_WORDS = (" duo", "duo ", " complex", "complex ", " met ", " met/",
                      "glyxambi", "synjardy", "trijardy", "xigduo", "qtern", "ebymect")


def row_passes(row: dict, ftype: str, spec: dict) -> bool:
    """True if *row* belongs to the indication/sub-type the filter keeps."""
    hay = _haystack(row)
    name = _fold(row.get("product_name"))

    if ftype == "MONOTHERAPY":
        # Inverted default: everything is kept unless it looks like a combination.
        # The others answer "can we confirm the required use?"; this one answers
        # "is anything else in the tablet?", so absence of evidence keeps the row.
        return not _is_combination(row)

    if any(_fold(kw) in hay for kw in spec.get("keywords", [])):
        return True
    if any(_fold(b) in name for b in spec.get("brands", [])):
        return True

    if ftype == "BIOSIMILAR":
        applicant = _fold(row.get("applicant"))
        if any(_fold(o) in applicant for o in spec.get("originator_applicants", [])):
            return False
        if any(_fold(ob) in name for ob in spec.get("originator_brands", [])):
            return False
        # A non-originator ranibizumab biologic is, by definition, a biosimilar.
        return True

    # PAH/OPHTHALMIC: with no positive indication signal we cannot confirm the
    # required use, so the row is excluded (this is the intended noise reduction).
    return False


def _term_to_filter(molecules: list[dict]) -> dict:
    """Map every search term that can appear in a row to its post_filter type."""
    mapping: dict[str, str] = {}
    for m in molecules:
        pf = m.get("post_filter")
        if not pf:
            continue
        # `inn` first: normalize.py rewrites every row's molecule_search_term to the
        # canonical INN, so that is the value these rows actually carry. The
        # source-specific terms stay mapped too, for callers that filter raw rows
        # before normalization.
        terms = [m.get("inn", ""), m.get("latam_term", ""),
                 m.get("ema_term", ""), m.get("fda_term", "")]
        terms += list(m.get("aliases", []))
        for t in terms:
            if t:
                mapping[t.upper()] = pf
    return mapping


def apply_post_filters(rows: list[dict], molecules: list[dict]) -> tuple[list[dict], dict]:
    """Drop rows that fail their molecule's indication/sub-type post-filter.

    Rows whose molecule has no post_filter pass through untouched. Returns
    ``(kept_rows, dropped_counts)``.
    """
    term_filter = _term_to_filter(molecules)
    if not term_filter:
        return rows, {}

    kept: list[dict] = []
    dropped: dict[str, int] = {}
    for row in rows:
        term = (row.get("molecule_search_term") or "").upper()
        ftype = term_filter.get(term)
        if not ftype:
            kept.append(row)
            continue
        spec = config.POST_FILTERS.get(ftype)
        if not spec:
            kept.append(row)
            continue
        if row_passes(row, ftype, spec):
            kept.append(row)
        else:
            dropped[term] = dropped.get(term, 0) + 1
    return kept, dropped
