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
    {"inn": "Empagliflozin", "latam_term": "EMPAGLIFLOZINA", "ema_term": "empagliflozin", "fda_term": "empagliflozin", "aliases": ["EMPAGLIFLOZIN"], "post_filter": "MONOTHERAPY", "notes": "Solo molécula única — se excluyen las combinaciones a dosis fija"},
    {"inn": "Sotagliflozin", "latam_term": "SOTAGLIFLOZINA", "ema_term": "sotagliflozin", "fda_term": "sotagliflozin", "aliases": ["SOTAGLIFLOZIN"], "post_filter": None, "notes": ""},
    {"inn": "Riociguat", "latam_term": "RIOCIGUAT", "ema_term": "riociguat", "fda_term": "riociguat", "aliases": [], "post_filter": None, "notes": ""},
    {"inn": "Macitentan", "latam_term": "MACITENTAN", "ema_term": "macitentan", "fda_term": "macitentan", "aliases": [], "post_filter": None, "notes": ""},
    {"inn": "Sotatercept", "latam_term": "SOTATERCEPT", "ema_term": "sotatercept", "fda_term": "sotatercept", "aliases": [], "post_filter": None, "notes": ""},
    {"inn": "Treprostinil", "latam_term": "TREPROSTINIL", "ema_term": "treprostinil", "fda_term": "treprostinil", "aliases": [], "post_filter": None, "notes": ""},
    {"inn": "Selexipag", "latam_term": "SELEXIPAG", "ema_term": "selexipag", "fda_term": "selexipag", "aliases": [], "post_filter": None, "notes": ""},
    {"inn": "Ranibizumab (biosimilar)", "latam_term": "RANIBIZUMAB", "ema_term": "ranibizumab", "fda_term": "ranibizumab", "aliases": [], "post_filter": "BIOSIMILAR", "notes": "Post-filter: biosimilar flag in product name"},
    {"inn": "Bevacizumab (ophthalmic)", "latam_term": "BEVACIZUMAB", "ema_term": "bevacizumab", "fda_term": "bevacizumab", "aliases": [], "post_filter": "OPHTHALMIC", "notes": "Post-filter: ophthalmic / oftálmico indication"},
    # ── Factor VIII / hemofilia A ────────────────────────────────────────────
    # Tres entradas, y el ORDEN IMPORTA: gana la primera coincidencia, así que las
    # moléculas concretas van antes que la entrada de clase del final. Antes las dos
    # buscaban "RFVIII" y se quedaban con todo el mercado: de 32 filas etiquetadas
    # como turoctocog, 14 eran en realidad octocog alfa (KOVALTRY, ADVATE, KOGENATE)
    # o turoctocog SIN pegol (NOVOEIGHT) — moléculas distintas de otros fabricantes.
    # "TUROCTOCOG" a secas tampoco sirve: NOVOEIGHT lo lleva en su principio activo.
    {"inn": "Turoctocog alfa pegol", "latam_term": "TUROCTOCOG ALFA PEGOL", "ema_term": "turoctocog alfa pegol", "fda_term": "turoctocog alfa pegol", "aliases": [], "post_filter": None, "notes": "ESPEROCT — el 'pegol' lo distingue de NOVOEIGHT"},
    {"inn": "Marstacimab", "latam_term": "MARSTACIMAB", "ema_term": "marstacimab", "fda_term": "marstacimab", "aliases": ["MARSTICIMAB", "ANTI-TFPI"], "post_filter": None, "notes": ""},
    {"inn": "Valoctocogene roxaparvovec", "latam_term": "VALOCTOCOGENE ROXAPARVOVEC", "ema_term": "valoctocogene roxaparvovec", "fda_term": "valoctocogene roxaparvovec", "aliases": [], "post_filter": None, "notes": "Gene therapy — expect 0 results in LATAM"},
    {"inn": "Efanesoctocog alfa", "latam_term": "EFANESOCTOCOG", "ema_term": "efanesoctocog alfa", "fda_term": "efanesoctocog alfa", "aliases": ["FC-VWF-XTEN"], "post_filter": None, "notes": "ALTUVIIIO / Altuvoct — nombre propio, sin colisión con turoctocog"},
    # Llegaron por la lista de productos del PO de Guatemala (21/08/2026) y se
    # promovieron al panel global para vigilarlos en los 9 países: mientras vivían solo
    # en la lista de GT, la matriz Molécula×País los mostraba como si se hubieran
    # buscado en todas partes y solo existieran allí.
    # Las marcas de aflibercept que aportó el PO son todas biosimilares de Eylea; se
    # dejan en GT_SEARCH_PRODUCTS y aquí se busca el INN, que es lo que publican los
    # registros del resto de países.
    {"inn": "Aflibercept", "latam_term": "AFLIBERCEPT", "ema_term": "aflibercept", "fda_term": "aflibercept", "aliases": ["EYLEA"], "post_filter": None, "notes": "Anti-VEGF oftálmico; el PO de GT sigue sus biosimilares"},
    # "RIVAROXABÁN" acentuado se busca aparte: los extractores comparan el texto crudo
    # del portal, así que la forma sin tilde no lo encontraría.
    {"inn": "Rivaroxaban", "latam_term": "RIVAROXABAN", "ema_term": "rivaroxaban", "fda_term": "rivaroxaban", "aliases": ["RIVAROXABÁN", "XARELTO"], "post_filter": None, "notes": ""},
    # La red de seguridad: recoge todo Factor VIII que no sea una de las dos anteriores.
    # Es como los registros LATAM etiquetan de verdad a la competencia — "FACTOR VIII
    # RECOMBINANTE (RFVIII)", "FACTOR ANTIHEMOFÍLICO (RECOMBINANTE)" — sin nombrar el
    # INN. Va AL FINAL para no robarle filas a las moléculas concretas de arriba.
    {"inn": "Factor VIII (clase)", "latam_term": "FACTOR VIII", "ema_term": "coagulation factor viii", "fda_term": "antihemophilic factor", "aliases": ["RFVIII", "FACTOR ANTIHEMOFILICO", "OCTOCOG"], "post_filter": None, "notes": "Vigilancia del mercado de hemofilia A: octocog, damoctocog, efmoroctocog, rurioctocog y genéricos"},
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
    "MONOTHERAPY": {  # Empagliflozin
        "label": "Solo molécula única — sin combinaciones a dosis fija",
        # No keyword list: this filter works by exclusion, in postfilter._is_combination.
        # A LATAM registry reports the same active ingredient ("EMPAGLIFLOZINA") for a
        # monotherapy and for a metformin combination alike, so the decision comes from
        # the product name — two strengths, a partner INN, or a combination brand line.
    },
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
# "FACTOR VIII" ya NO se excluye: dejó de ser un alias suelto que contaminaba a
# turoctocog y pasó a ser el término propio de la entrada de clase, que va al final
# de MOLECULES y por tanto solo recoge lo que las moléculas concretas no reclamaron.
BROAD_LATAM_TERMS = {"ANTI-TFPI", "FC-VWF-XTEN"}


# ── Guatemala: búsqueda por producto, no por molécula ─────────────────────────
# El portal de MSPAS consulta por NOMBRE DE PRODUCTO (su columna de principio activo
# viene vacía del servidor), así que buscar el INN solo encuentra los genéricos que lo
# llevan en el nombre — "ENZALUTAMIDA Lotus 40mg" aparece, IZABAN o YESAFILI no.
# Esta lista la aporta el PO de Guatemala: cada marca comercializada allí, con la
# molécula a la que pertenece, para que las filas consoliden con el resto de países.
#
# Cada entrada es (molécula canónica, [términos a buscar]). La molécula es la que
# termina en `molecule_search_term`, de modo que un producto de marca queda agrupado
# con sus equivalentes de otros países.
GT_SEARCH_PRODUCTS = [
    ("Regorafenib",   ["REGORAFENIB", "REZITIX"]),
    ("Sorafenib",     ["SORAFENIB", "ZORAFRED", "SORAVITAE", "SOXANIB", "ZORACORD",
                       "REXANIB", "AFENIB", "SONIB", "SARONIF", "SORAGLOB"]),
    ("Apalutamide",   ["APALUTAMIDA", "PROSMID"]),
    ("Enzalutamide",  ["ENZALUTAMIDA", "XALUT", "MIDALUNE", "ENZACORD"]),
    ("Fezolinetant",  ["VEOZAH", "VEOZA"]),
    # El PO escribe "DAPAGLIFOZINA"/"EMPAGLIFOZINA" sin la primera L; se buscan ambas
    # grafías porque cualquiera de las dos puede ser la registrada en el portal.
    ("Dapagliflozin", ["DAPAGLIFOZINA", "DAPAGLIFLOZINA", "DAPHA", "DAPAGLIX",
                       "PAZIGLIP", "DAPAGET", "DAPAGLICIN", "FANTER"]),
    ("Empagliflozin", ["EMPAGLIFOZINA", "EMPAGLIFLOZINA", "EMPAFLOX", "IZABAN",
                       "GLUCONIL"]),
    ("Sotagliflozin", ["ZYNQUISTA"]),
    ("Riociguat",     ["PULLMOGUAT", "RIOCI"]),
    ("Treprostinil",  ["TYVASO", "ORENITRAM"]),
    # Aflibercept y Rivaroxaban entraron al panel global el 21/08/2026, así que ya se
    # buscan en los 9 países. Aquí quedan sus marcas, que es lo único que encuentra el
    # portal guatemalteco cuando el nombre del producto no lleva el INN.
    ("Aflibercept",   ["AFLIBERCEPT", "YESAFILI", "AHZANTIVE", "OPUVIZ", "PAVBLU",
                       "EYDENZELT"]),
    # "RANI" a secas está descartado a propósito: el portal devuelve 10 RANITIDINAS.
    ("Ranibizumab (biosimilar)", ["RANIVISIO"]),
    ("Bevacizumab (ophthalmic)", ["LYTENAVA"]),
    ("Turoctocog alfa pegol",    ["ESPEROCT"]),
    ("Rivaroxaban",   ["RIVAROXABAN", "XAROBAN", "TROMBOPROF", "RIVACRIST", "ROTHROM",
                       "ASARAP", "RIVAX", "ORTACTA", "RIVOXA", "RIBEX", "RIVOXVITAE",
                       "ROXAR"]),
    # El PO listó estas marcas sin indicar molécula. Son sistemas intrauterinos de
    # LEVONORGESTREL: confirmado para ASERTIA, ELOIRA, LILETTA, MIA CARE (52 mg,
    # 20 µg/24 h), MAHELY (Gynopharm, RD) y ENGYNO (Gedeon Richter, Perú). EMILY y
    # FIONA no aparecen en fuentes públicas — se agrupan aquí por pertenecer a la
    # misma lista y categoría; conviene que el PO lo confirme.
    ("Levonorgestrel (DIU)", ["ASERTIA", "ELOIRA", "ENGYNO", "EMILY",
                              "MAHELY", "LILETTA", "FIONA", "MIA CARE"]),
]


def gt_search_products(molecules: list[dict] | None = None) -> list[tuple]:
    """GT's (molecule, terms) pairs, narrowed to the molecules being run.

    With the full panel every entry is searched, including the GT-only molecules that
    are absent from MOLECULES. Under ``--molecule`` only the matching entry runs, so a
    single-molecule run stays fast.
    """
    if not molecules or len(molecules) == len(MOLECULES):
        return GT_SEARCH_PRODUCTS

    def _key(value) -> str:
        return (canonical_inn(value) or str(value or "").strip().upper())

    # A caller may pass an ad-hoc molecule dict without an `inn`; fall back to the
    # LATAM term so a narrowed run still resolves instead of raising.
    wanted = {_key(m.get("inn") or m.get("latam_term")) for m in molecules}
    return [(inn, terms) for inn, terms in GT_SEARCH_PRODUCTS if _key(inn) in wanted]


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
