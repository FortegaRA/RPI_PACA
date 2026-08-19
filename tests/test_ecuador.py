"""
Ecuador bulk-report extractor (no network).

ARCSA's /reporte/1 is a single ~15k-row HTML dump that we download once and filter
in memory. The portal omits closing </tr> tags, so rows are sliced between <tr>
START tags — the key thing these tests pin down, plus the active-ingredient filter
and the HTTP-error path.
"""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

import _fakes as fk  # noqa: E402
from extractors import ec  # noqa: E402

HEADERS = [
    "Numero_registro_sanitario", "Fecha_recepcion_solicitud", "Numero_solicitud",
    "Estado_actual_vue", "Estado", "Institucion", "Fecha_emision_registro_sanitario",
    "Fecha_vigencia_registro_sanitario", "Nombre_razon_social_solicitante",
    "Titular_producto", "Nombre_fabricante", "Pais_fabricante", "Nombre_producto",
    "Forma_farmaceutica", "Concentracion_principio_activo", "Principios_activos",
]


def _row(reg, product, api, status="VIGENTE"):
    vals = [reg, "2025-09-03 19:44:23.83", "SOL1", "REGISTRADO", status, "ARCSA",
            "2024-01-15", "2029-01-15", "ACME SA", "ACME", "FAB SA", "INDIA",
            product, "TABLETA", "10 mg", api]
    # Deliberately NO </tr> — mirrors the real ARCSA report.
    return "<tr>" + "".join(f"<td>{v}</td>" for v in vals)


def _report(rows):
    thead = "<tr>" + "".join(f"<th>{h}</th>" for h in HEADERS) + "</tr>"
    return f"<html><body><table><thead>{thead}</thead><tbody>{''.join(rows)}</tbody></table></body></html>"


MOL = [{"latam_term": "REGORAFENIB", "ema_term": "regorafenib",
        "fda_term": "regorafenib", "aliases": []}]


class TestParseRows(unittest.TestCase):
    def test_slices_rows_without_closing_tr(self):
        html = _report([_row("R1", "STIVARGA", "REGORAFENIB"),
                        _row("R2", "PANADOL", "PARACETAMOL"),
                        _row("R3", "NEXAVAR", "SORAFENIB")])
        rows = list(ec._parse_rows(html))
        self.assertEqual(len(rows), 3, "all 3 data rows must be parsed despite missing </tr>")
        last_scanned, last_row = rows[-1]
        self.assertEqual(last_scanned, 3)
        self.assertEqual(last_row["principios_activos"], "SORAFENIB")

    def test_ignores_when_header_missing(self):
        self.assertEqual(list(ec._parse_rows("<table><tr><td>x</td></tr></table>")), [])


class TestClean(unittest.TestCase):
    def test_strips_tags_and_unescapes(self):
        self.assertEqual(ec._clean("<b>Paracetamol &amp; X</b>"), "Paracetamol & X")


class TestExtract(unittest.TestCase):
    def _session(self, html, status=200, per_report=None):
        """Fake ARCSA. *html* answers report 1; *per_report* overrides any report id.

        The portal serves a different dump per id (1 = Vigentes, 2 = Solicitudes
        Ingresadas), so the double has to distinguish them — otherwise every report
        returns the same rows and the counts are meaningless.
        """
        per_report = per_report or {}
        # A report the test does not care about still has to look like a real one:
        # a dump with zero data rows is treated as a structure change, not as
        # "nothing matched", so the filler carries an unrelated molecule.
        filler = _report([_row("OTRO", "PANADOL", "PARACETAMOL")])

        def handler(method, url, **kw):
            if url.rstrip("/").endswith("index"):
                return fk.FakeResponse(status_code=200, text="<html>ok</html>")
            rtype = int(url.rstrip("/").rsplit("/", 1)[-1])
            body = per_report.get(rtype, html if rtype == 1 else filler)
            return fk.FakeResponse(status_code=status, text=body)
        return fk.FakeSession(handler=handler)

    def test_filters_by_active_ingredient(self):
        html = _report([_row("R1", "STIVARGA", "REGORAFENIB MONOHIDRATO"),
                        _row("R2", "PANADOL", "PARACETAMOL")])
        c = {"partial_errors": [], "session_ec": self._session(html)}
        rows = ec.extract(MOL, c)
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r["registration_number"], "R1")
        self.assertEqual(r["product_name"], "STIVARGA")
        self.assertEqual(r["molecule_search_term"], "REGORAFENIB")
        self.assertEqual(r["approval_date"], "2024-01-15")
        self.assertEqual(r["expiration_date"], "2029-01-15")
        self.assertEqual(r["record_type"], "APPROVAL")
        self.assertEqual(c["partial_errors"], [])

    def test_no_match_is_clean_empty(self):
        html = _report([_row("R2", "PANADOL", "PARACETAMOL")])
        c = {"partial_errors": [], "session_ec": self._session(html)}
        self.assertEqual(ec.extract(MOL, c), [])
        self.assertEqual(c["partial_errors"], [])  # scanned rows, just no target match

    def test_api_cleaned_from_formulation_blurb(self):
        # ARCSA buries the INN in a "CADA … CONTIENE: <INN> *** 10,00 MG …" string;
        # the canonical api must come out as the clean ingredient, not the blurb.
        blurb = "CADA TABLETA RECUBIERTA CONTIENE: REGORAFENIB MONOHIDRATO *** 40,00 MG ......."
        html = _report([_row("R1", "STIVARGA", blurb)])
        c = {"partial_errors": [], "session_ec": self._session(html)}
        rows = ec.extract(MOL, c)
        self.assertEqual(rows[0]["api"], "REGORAFENIB MONOHIDRATO")
        self.assertNotIn("CONTIENE", rows[0]["api"])


    def test_approval_rows_carry_no_submission_date(self):
        """Report 1's `fecha_recepcion_solicitud` is a post-approval procedure date,
        not a filing date, so it must not populate `submission_date` — otherwise
        approvals leak into any view that keys off that field."""
        html = _report([_row("R1", "STIVARGA", "REGORAFENIB")])
        c = {"partial_errors": [], "session_ec": self._session(html)}
        rows = ec.extract(MOL, c)
        self.assertEqual(rows[0]["record_type"], "APPROVAL")
        self.assertIsNone(rows[0]["submission_date"])
        self.assertEqual(rows[0]["approval_date"], "2024-01-15")   # esta si es real

    def test_http_error_records_error(self):
        c = {"partial_errors": [], "session_ec": self._session("", status=500)}
        self.assertEqual(ec.extract(MOL, c), [])
        self.assertTrue(any("HTTP 500" in e for e in c["partial_errors"]))


class TestCleanApi(unittest.TestCase):
    M = MOL[0]

    def test_strips_preamble_and_strength(self):
        self.assertEqual(
            ec._clean_api("CADA COMPRIMIDO CONTIENE: REGORAFENIB 40 MG", self.M),
            "REGORAFENIB")

    def test_keeps_salt_form(self):
        self.assertEqual(
            ec._clean_api("REGORAFENIB MONOHIDRATO *** 40,00 MG", self.M),
            "REGORAFENIB MONOHIDRATO")

    def test_falls_back_to_canonical_when_no_inn(self):
        # No recognizable INN in the text -> canonical term, never noise.
        self.assertEqual(ec._clean_api("CADA TABLETA CONTIENE EXCIPIENTES CSP", self.M),
                         "REGORAFENIB")

    def test_empty_is_canonical(self):
        self.assertEqual(ec._clean_api("", self.M), "REGORAFENIB")



class TestSubmissionsReport(unittest.TestCase):
    """Report 2 ("Total de Solicitudes Ingresadas") is ARCSA's only filing stream.

    Report 1 lists granted registrations; its `fecha_recepcion_solicitud` column is
    NOT an original filing date (verified live: not one of 161 matched rows had it
    before its own approval date). Filings live in report 2, keyed by solicitud
    number and carrying no approval or expiry date because nothing was granted yet.
    """

    HEADERS_2 = ["Numero_registro_sanitario", "Institucion", "Numero_solicitud",
                 "Fecha_recepcion", "Nombre_razon_social_solicitante", "Titular_producto",
                 "Nombre_fabricante", "Pais_fabricante", "Estado_detalle_modificacion",
                 "Nombre_producto", "Principios_activos", "Concentracion_principio_activo",
                 "Forma_farmaceutica", "Presentacion_comercial", "Via_administracion",
                 "Tipo_producto", "Forma_venta", "Tipo_medicamento", "Condicion_conservacion"]

    def _report2(self, solicitud, product, api, recibida="2026-08-07"):
        vals = ["RS-EXISTENTE", "INH", solicitud, recibida, "ACME SA", "ACME",
                "FAB SA", "INDIA", "VIGENTE", product, api, "40 mg", "TABLETAS",
                "Caja x 30", "Oral", "Marca", "Libre", "Medicamento", "T < 30C"]
        thead = "<tr>" + "".join(f"<th>{h}</th>" for h in self.HEADERS_2) + "</tr>"
        body = "<tr>" + "".join(f"<td>{v}</td>" for v in vals)   # sin </tr>, como ARCSA
        return f"<html><body><table><thead>{thead}</thead><tbody>{body}</tbody></table></body></html>"

    def _run(self, html2):
        sess = TestExtract()._session(_report([_row("OTRO", "PANADOL", "PARACETAMOL")]),
                                      per_report={2: html2})
        c = {"partial_errors": [], "session_ec": sess}
        return ec.extract(MOL, c), c

    def test_filing_becomes_a_submission_row(self):
        rows, c = self._run(self._report2("SOL-123", "STIVARGA", "REGORAFENIB"))
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r["record_type"], "SUBMISSION")
        self.assertEqual(r["submission_date"], "2026-08-07")
        self.assertEqual(c["partial_errors"], [])

    def test_filing_is_keyed_by_solicitud_number(self):
        """The registration number may belong to the record being modified."""
        rows, _ = self._run(self._report2("SOL-123", "STIVARGA", "REGORAFENIB"))
        self.assertEqual(rows[0]["registration_number"], "SOL-123")

    def test_filing_carries_no_approval_or_expiry_date(self):
        """Nothing has been granted yet — those dates must stay empty."""
        rows, _ = self._run(self._report2("SOL-123", "STIVARGA", "REGORAFENIB"))
        self.assertIsNone(rows[0]["approval_date"])
        self.assertIsNone(rows[0]["expiration_date"])

    def test_filing_status_is_pending_not_the_registry_state(self):
        """The sheet says VIGENTE about the REGISTRATION, not about the filing."""
        rows, _ = self._run(self._report2("SOL-123", "STIVARGA", "REGORAFENIB"))
        self.assertEqual(rows[0]["status"], "PENDING")

    def test_unrelated_molecule_is_ignored(self):
        rows, c = self._run(self._report2("SOL-9", "PANADOL", "PARACETAMOL"))
        self.assertEqual(rows, [])
        self.assertEqual(c["partial_errors"], [])

    def test_only_the_two_tracked_reports_are_pulled(self):
        self.assertEqual(ec.DEFAULT_REPORT_TYPES, [1, 2])
        self.assertEqual(ec.REPORTS[1]["record_type"], "APPROVAL")
        self.assertEqual(ec.REPORTS[2]["record_type"], "SUBMISSION")


if __name__ == "__main__":
    unittest.main(verbosity=2)
