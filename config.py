"""
config.py — Static configuration for the RPI_Cluster extraction run.

Exposes:
    MOLECULES        list[dict]  — target INN list with per-portal search terms
    COUNTRY_META     dict        — country_code -> {health_authority, source_url}
    SOURCE_URLS      dict        — per-extractor base portal URL
    OUTPUT_FILES     dict        — per-extractor canonical CSV filename
    CANONICAL_FIELDS list[str]   — re-exported from normalize for convenience
    build_session()              — configured requests.Session (lazy import)

Nothing here imports a third-party package at module load time, so the file is
safe to import in a bare-stdlib environment (the orchestrator relies on this when
``--no-selenium`` or a missing dependency would otherwise break import).
"""

from __future__ import annotations

import os

# Re-export the canonical field order so callers can `from config import CANONICAL_FIELDS`.
from normalize import CANONICAL_FIELDS  # noqa: F401  (stdlib-only module)

# ── Defaults ──────────────────────────────────────────────────────────────────
DEFAULT_OUTPUT_DIR = os.environ.get("RPI_OUTPUT_DIR", os.path.join(".", "output"))

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/csv, text/html, */*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
}

# Ecuador's portal prefers an Ecuadorian locale header.
EC_HEADERS = dict(DEFAULT_HEADERS, **{"Accept-Language": "es-EC,es;q=0.9,en;q=0.8"})


# ── Target molecules (schema §6 / molecules.md) ───────────────────────────────
# `latam_term`  : substring used on Spanish-language LATAM portals
# `ema_term`    : INN string used to filter the EMA JSON
# `fda_term`    : INN string used in the OpenFDA query
# `aliases`     : extra terms to also try (reversed word order, brand, INN variants)
# `post_filter` : optional indication/flag keyword that surviving rows must match
MOLECULES = [
    {"inn": "Regorafenib", "latam_term": "REGORAFENIB", "ema_term": "regorafenib", "fda_term": "regorafenib", "aliases": [], "post_filter": None, "notes": ""},
    {"inn": "Sorafenib", "latam_term": "SORAFENIB", "ema_term": "sorafenib", "fda_term": "sorafenib", "aliases": [], "post_filter": None, "notes": ""},
    {"inn": "Lenvatinib", "latam_term": "LENVATINIB", "ema_term": "lenvatinib", "fda_term": "lenvatinib", "aliases": [], "post_filter": None, "notes": ""},
    {"inn": "Larotrectinib", "latam_term": "LAROTRECTINIB", "ema_term": "larotrectinib", "fda_term": "larotrectinib", "aliases": [], "post_filter": None, "notes": ""},
    {"inn": "Repotrectinib", "latam_term": "REPOTRECTINIB", "ema_term": "repotrectinib", "fda_term": "repotrectinib", "aliases": [], "post_filter": None, "notes": ""},
    {"inn": "Darolutamide", "latam_term": "DAROLUTAMIDA", "ema_term": "darolutamide", "fda_term": "darolutamide", "aliases": ["DAROLUTAMIDE"], "post_filter": None, "notes": ""},
    {"inn": "Apalutamide", "latam_term": "APALUTAMIDA", "ema_term": "apalutamide", "fda_term": "apalutamide", "aliases": ["APALUTAMIDE"], "post_filter": None, "notes": ""},
    {"inn": "Enzalutamide", "latam_term": "ENZALUTAMIDA", "ema_term": "enzalutamide", "fda_term": "enzalutamide", "aliases": ["ENZALUTAMIDE"], "post_filter": None, "notes": ""},
    {"inn": "Trastuzumab deruxtecan", "latam_term": "TRASTUZUMAB DERUXTECAN", "ema_term": "trastuzumab deruxtecan", "fda_term": "trastuzumab deruxtecan", "aliases": ["DERUXTECAN TRASTUZUMAB", "DERUXTECAN"], "post_filter": None, "notes": "Search both word orders"},
    {"inn": "Zongertinib", "latam_term": "ZONGERTINIB", "ema_term": "zongertinib", "fda_term": "zongertinib", "aliases": [], "post_filter": None, "notes": ""},
    {"inn": "Fezolinetant", "latam_term": "FEZOLINETANT", "ema_term": "fezolinetant", "fda_term": "fezolinetant", "aliases": [], "post_filter": None, "notes": ""},
    {"inn": "Finerenone", "latam_term": "FINERENONA", "ema_term": "finerenone", "fda_term": "finerenone", "aliases": ["FINERENONE"], "post_filter": None, "notes": ""},
    {"inn": "Vericiguat", "latam_term": "VERICIGUAT", "ema_term": "vericiguat", "fda_term": "vericiguat", "aliases": [], "post_filter": None, "notes": ""},
    {"inn": "Dapagliflozin", "latam_term": "DAPAGLIFLOZINA", "ema_term": "dapagliflozin", "fda_term": "dapagliflozin", "aliases": ["DAPAGLIFLOZIN"], "post_filter": None, "notes": ""},
    {"inn": "Empagliflozin", "latam_term": "EMPAGLIFLOZINA", "ema_term": "empagliflozin", "fda_term": "empagliflozin", "aliases": ["EMPAGLIFLOZIN"], "post_filter": None, "notes": ""},
    {"inn": "Sotagliflozin", "latam_term": "SOTAGLIFLOZINA", "ema_term": "sotagliflozin", "fda_term": "sotagliflozin", "aliases": ["SOTAGLIFLOZIN"], "post_filter": None, "notes": ""},
    {"inn": "Riociguat", "latam_term": "RIOCIGUAT", "ema_term": "riociguat", "fda_term": "riociguat", "aliases": [], "post_filter": None, "notes": ""},
    {"inn": "Macitentan", "latam_term": "MACITENTAN", "ema_term": "macitentan", "fda_term": "macitentan", "aliases": [], "post_filter": None, "notes": ""},
    {"inn": "Sotatercept", "latam_term": "SOTATERCEPT", "ema_term": "sotatercept", "fda_term": "sotatercept", "aliases": [], "post_filter": None, "notes": ""},
    {"inn": "Treprostinil", "latam_term": "TREPROSTINIL", "ema_term": "treprostinil", "fda_term": "treprostinil", "aliases": [], "post_filter": None, "notes": ""},
    {"inn": "Selexipag", "latam_term": "SELEXIPAG", "ema_term": "selexipag", "fda_term": "selexipag", "aliases": [], "post_filter": None, "notes": ""},
    {"inn": "Ranibizumab (biosimilar)", "latam_term": "RANIBIZUMAB", "ema_term": "ranibizumab", "fda_term": "ranibizumab", "aliases": [], "post_filter": "BIOSIMILAR", "notes": "Post-filter: biosimilar flag in product name"},
    {"inn": "Bevacizumab (ophthalmic)", "latam_term": "BEVACIZUMAB", "ema_term": "bevacizumab", "fda_term": "bevacizumab", "aliases": [], "post_filter": "OPHTHALMIC", "notes": "Post-filter: ophthalmic / oftálmico indication"},
    {"inn": "Turoctocog alfa pegol", "latam_term": "RFVIII", "ema_term": "turoctocog alfa pegol", "fda_term": "turoctocog alfa pegol", "aliases": ["FACTOR VIII", "TUROCTOCOG"], "post_filter": None, "notes": ""},
    {"inn": "Marstacimab", "latam_term": "MARSTACIMAB", "ema_term": "marstacimab", "fda_term": "marstacimab", "aliases": ["MARSTICIMAB", "ANTI-TFPI"], "post_filter": None, "notes": ""},
    {"inn": "Valoctocogene roxaparvovec", "latam_term": "VALOCTOCOGENE ROXAPARVOVEC", "ema_term": "valoctocogene roxaparvovec", "fda_term": "valoctocogene roxaparvovec", "aliases": [], "post_filter": None, "notes": "Gene therapy — expect 0 results in LATAM"},
    {"inn": "Efanesoctocog alfa", "latam_term": "RFVIII PROTEINA FUSION", "ema_term": "efanesoctocog alfa", "fda_term": "efanesoctocog alfa", "aliases": ["FC-VWF-XTEN", "EFANESOCTOCOG"], "post_filter": None, "notes": ""},
]


# Novel molecules expected to have ~0 LATAM registrations (molecules.md: gene
# therapy / first-in-class). For these we emit a NULL-filled "presence" row per
# successfully-searched country that returned no real record, so the report shows
# the molecule WAS checked rather than silently missing. Toggle with
# EMIT_PRESENCE_ROWS.
EMIT_PRESENCE_ROWS = True
_TRACK_IF_ABSENT = {"Valoctocogene roxaparvovec", "Marstacimab", "Efanesoctocog alfa"}
for _m in MOLECULES:
    _m["track_if_absent"] = _m["inn"] in _TRACK_IF_ABSENT


# ── Country metadata (schema §1 / §4) ─────────────────────────────────────────
COUNTRY_META = {
    "PE": {"health_authority": "DIGEMID", "source_url": "https://www.digemid.minsa.gob.pe"},
    "EC": {"health_authority": "ARCSA", "source_url": "https://aplicaciones.controlsanitario.gob.ec/publico/consultas/index"},
    "CO": {"health_authority": "INVIMA", "source_url": "https://www.datos.gov.co"},
    "CR": {"health_authority": "MCCSS-DRTM", "source_url": "https://registrelo.go.cr"},
    "SV": {"health_authority": "SRS", "source_url": "https://expedientes.srs.gob.sv"},
    "GT": {"health_authority": "MSPAS", "source_url": "https://regsanitario.mspas.gob.gt"},
    "HN": {"health_authority": "ARSA", "source_url": "https://sicreb.arsa.hn"},
    "DO": {"health_authority": "DIGEMAPS", "source_url": "https://consultas.digemaps.gob.do"},
    "EU": {"health_authority": "EMA", "source_url": "https://www.ema.europa.eu"},
    "US": {"health_authority": "FDA", "source_url": "https://api.fda.gov"},
}

# ── Per-extractor portal endpoints ────────────────────────────────────────────
SOURCE_URLS = {
    # EMA retired the per-report JSON feeds (2026 site redesign → 404). The current
    # public feed is one XLSX, "Medicine" output, covering Human + Veterinary with a
    # Medicine status column we split into APPROVAL vs SUBMISSION.
    "ema_report": "https://www.ema.europa.eu/en/documents/report/medicines-output-medicines-report_en.xlsx",
    "ema": "https://www.ema.europa.eu",
    "fda": "https://api.fda.gov/drug/drugsfda.json",
    "co_approvals": "https://www.datos.gov.co/resource/i7cb-raxc.json",
    "co_submissions": "https://enlinea.invima.gov.co/TransparenciaWeb/",
    "hn": "https://sicreb.arsa.hn/Servicios/Medicamentos?NombrePestania=MRS&NombreServicio=Medicamentos%20de%20uso%20Humano",
    "sv": "https://expedientes.srs.gob.sv/productos/buscarProducto",
    "gt": "https://regsanitario.mspas.gob.gt/reg_sanitario/Vigentes.php",
    "do": "https://consultas.digemaps.gob.do/registrosanitario",
    "cr": "https://registrelo.go.cr/reports/12",
    "pe_approvals": "https://www.digemid.minsa.gob.pe/rsProductosFarmaceuticos/",
    "pe_submissions": "https://www.digemid.minsa.gob.pe/solicitudesRs/",
    "ec": "https://aplicaciones.controlsanitario.gob.ec/publico/consultas/index",
}

# ── Output CSV filenames (schema §8) ──────────────────────────────────────────
OUTPUT_FILES = {
    "pe_approvals": "RPIPE_aprob_canonical.csv",
    "pe_submissions": "RPIPE_solicit_canonical.csv",
    "sv": "RPISV_canonical.csv",
    "gt": "RPIGT_canonical.csv",
    "do": "RPIDO_canonical.csv",
    "hn": "RPIHN_canonical.csv",
    "cr": "RPICR_canonical.csv",
    "co_approvals": "RPICO_aprob_canonical.csv",
    "co_submissions": "RPICO_solicit_canonical.csv",
    "ec": "RPIEC_canonical.csv",
    "ema": "RPIEMA_canonical.csv",
    "fda": "RPIFDA_canonical.csv",
}

# ── Post-filters (molecules.md "Search Strategy Notes") ───────────────────────
# Some molecules must be narrowed to a specific indication after extraction:
#   Bevacizumab -> keep only ophthalmic use (exclude systemic oncology)
#   Ranibizumab -> keep only biosimilars (exclude the originator, Lucentis)
# (PAH_OR_OPHTHALMIC is retained as a template — its molecule, Tadalafil, was
#  dropped from the panel as low market relevance; no active molecule selects it.)
#
# The canonical schema has no indication column, so a row is judged from the text
# we DO have — product_name / api / dosage_form / concentration / applicant — plus
# an optional `_indication_hint` that indication-bearing sources thread through
# (CO ATC description, SV indicaciones, HN grupo terapéutico, GT clase terapéutica).
# A molecule's `post_filter` key (set in MOLECULES) selects one of these specs.
# Keyword/brand lists are deliberately easy to tune as registries evolve.
POST_FILTERS = {
    "PAH_OR_OPHTHALMIC": {  # template — no active molecule (Tadalafil removed)
        "label": "Tadalafil — PAH/ophthalmic only",
        "keywords": ["pulmonar", "pulmonary", "hipertension pulmonar", "arterial pulmonar",
                     "hipertension arterial pulmonar", " pah", "oftalmic", "ophthalmic",
                     "intravitre", "retina", "ocular"],
        "brands": ["adcirca", "alyq", "tadliq"],
    },
    "OPHTHALMIC": {  # Bevacizumab
        "label": "Bevacizumab — ophthalmic only",
        "keywords": ["oftalmic", "ophthalmic", "intravitre", "ocular", "retina", "macular",
                     "degeneracion macular", "edema macular", "rvo", "amd", "dme"],
        "brands": ["avzivi", "lytenava"],
    },
    "BIOSIMILAR": {  # Ranibizumab
        "label": "Ranibizumab — biosimilar only",
        "keywords": ["biosimilar", "biocomparable", "generico biologico"],
        "brands": ["ranivisio", "ximluci", "byooviz", "cimerli", "ongavia", "ranopto",
                   "ranibiz", "ranivix"],
        "originator_applicants": ["novartis", "genentech", "roche"],
        "originator_brands": ["lucentis"],
    },
}


# ── HTTP session factory (lazy import so config stays stdlib-safe) ─────────────
def build_session(headers: dict | None = None, total_retries: int = 3,
                  backoff_factor: float = 1.0):
    """Return a configured ``requests.Session`` with retries on 429/5xx.

    Imports ``requests``/``urllib3`` lazily so this module can be imported in an
    environment where those packages are not installed.
    """
    import requests
    from requests.adapters import HTTPAdapter

    try:
        from urllib3.util.retry import Retry
    except Exception:  # pragma: no cover
        from requests.packages.urllib3.util.retry import Retry  # type: ignore

    session = requests.Session()
    session.headers.update(headers or DEFAULT_HEADERS)
    retry = Retry(
        total=total_retries,
        backoff_factor=backoff_factor,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET", "POST"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


# Alias terms too broad/technical for a substring search on LATAM portals: they
# would mislabel unrelated products (every Factor VIII → "turoctocog") or never
# match a product/ingredient name. They stay in MOLECULES["aliases"] for reference
# but are NOT expanded into live LATAM search queries.
BROAD_LATAM_TERMS = {"FACTOR VIII", "ANTI-TFPI", "FC-VWF-XTEN"}


def search_terms(molecule: dict) -> list[str]:
    """Unique uppercase LATAM search terms: latam_term + its safe aliases.

    Lets Spanish-language portals catch a molecule registered under an INN variant
    — e.g. Tadalafil's LATAM term is ``TADAFILO`` but it is registered as
    ``TADALAFILO`` — without losing it. Broad class/mechanism aliases are excluded
    (see :data:`BROAD_LATAM_TERMS`). Rows found under any of these terms should be
    tagged with the molecule's canonical ``latam_term`` so reporting stays grouped.
    """
    terms = [molecule.get("latam_term", "")] + list(molecule.get("aliases", []))
    seen: set[str] = set()
    out: list[str] = []
    for t in terms:
        u = (t or "").strip().upper()
        if u and u not in seen and u not in BROAD_LATAM_TERMS:
            seen.add(u)
            out.append(u)
    return out


def _build_term_index() -> dict[str, str]:
    """Map every per-source search term to its molecule's canonical INN (uppercase).

    Each source tags rows with its own vocabulary — LATAM portals use ``latam_term``
    ("DAPAGLIFLOZINA"), EMA/FDA use their INN spelling ("DAPAGLIFLOZIN") — so the same
    molecule ended up under two labels and the molecule x country matrix split it into
    two rows. This index is how a row gets one identity regardless of where it came from.
    """
    index: dict[str, str] = {}
    for m in MOLECULES:
        canonical = m["inn"].upper()
        variants = [m["inn"], m.get("latam_term"), m.get("ema_term"), m.get("fda_term")]
        variants += list(m.get("aliases", []))
        for v in variants:
            key = (v or "").strip().upper()
            if key:
                index.setdefault(key, canonical)
    return index


_TERM_TO_INN = _build_term_index()


def canonical_inn(term) -> str | None:
    """Resolve a source-specific search term to the canonical INN, or ``None``.

    Unknown terms return ``None`` so the caller can keep the original value — an
    ad-hoc ``--molecule`` search must not be silently relabelled.
    """
    key = (term or "").strip().upper()
    return _TERM_TO_INN.get(key)


def molecules_for(single_molecule: str | None = None) -> list[dict]:
    """Return the full molecule list, or a single-entry list when filtered.

    *single_molecule* matches case-insensitively against the INN, the LATAM term,
    or any alias.
    """
    if not single_molecule:
        return MOLECULES
    needle = single_molecule.strip().upper()
    hits = []
    for m in MOLECULES:
        haystack = [m["inn"].upper(), m["latam_term"].upper(), m["ema_term"].upper(),
                    m["fda_term"].upper()] + [a.upper() for a in m.get("aliases", [])]
        if any(needle in h or h in needle for h in haystack):
            hits.append(m)
    return hits or [
        # Allow an ad-hoc term not in the master list.
        {"inn": single_molecule, "latam_term": needle, "ema_term": single_molecule.lower(),
         "fda_term": single_molecule.lower(), "aliases": [], "post_filter": None, "notes": "ad-hoc"}
    ]
