from datetime import date
from pathlib import Path
from django.test import SimpleTestCase
from imports.parser import CsvImportError, parse_cashbook_csv

FIXTURE = Path(__file__).parent / "fixtures" / "cashbook_july_synthetic.csv"


class CashbookParserTests(SimpleTestCase):
    def content(self):
        return FIXTURE.read_bytes()

    def test_realistic_metadata_footer_money_dates_and_normalization(self):
        parsed = parse_cashbook_csv(self.content())
        self.assertEqual(parsed.errors, [])
        self.assertEqual(parsed.period, date(2026, 7, 1))
        self.assertEqual(len(parsed.valid_rows), 19)
        self.assertEqual(sum(row.classification == "TAXABLE" for row in parsed.valid_rows), 13)
        self.assertEqual(sum(row.classification == "EXEMPT" for row in parsed.valid_rows), 6)
        self.assertEqual(parsed.totals, {"net": 546034, "vat": 72966, "total": 619000})
        self.assertEqual(
            (parsed.declared_net, parsed.declared_vat, parsed.declared_total),
            (546034, 72966, 619000),
        )
        self.assertEqual(parsed.valid_rows[0].normalized["issue_date"], "2026-07-01")
        self.assertEqual(parsed.valid_rows[0].normalized["money_layout"], "HISTORICAL_INVERTED")
        self.assertEqual(parsed.valid_rows[-1].normalized["money_layout"], "CANONICAL")
        self.assertEqual(sum(row.status == "IGNORED" for row in parsed.rows), 7)

    def test_utf8_bom_is_supported(self):
        parsed = parse_cashbook_csv(b"\xef\xbb\xbf" + self.content())
        self.assertEqual(len(parsed.valid_rows), 19)

    def test_taxable_canonical_money_layout_is_supported(self):
        content = self.content().replace(
            b'"$35,000","$5,588","$29,412"',
            b'"$29,412","$5,588","$35,000"',
            1,
        )
        parsed = parse_cashbook_csv(content)
        self.assertEqual(parsed.errors, [])
        self.assertEqual(parsed.valid_rows[0].normalized["money_layout"], "CANONICAL")
        self.assertEqual(parsed.totals, {"net": 546034, "vat": 72966, "total": 619000})

    def test_size_and_row_limits_are_enforced(self):
        with self.assertRaises(CsvImportError):
            parse_cashbook_csv(b"a" * (2 * 1024 * 1024 + 1))
        many_rows = b"a,b\n" * 501
        with self.assertRaises(CsvImportError):
            parse_cashbook_csv(many_rows)

    def test_inconsistent_footer_blocks(self):
        content = self.content().replace(b'"$619,000"', b'"$620,000"')
        parsed = parse_cashbook_csv(content)
        self.assertIn("Totales declarados inválidos", " ".join(parsed.errors))

    def test_invalid_encoding_and_binary_content_are_rejected(self):
        with self.assertRaises(CsvImportError):
            parse_cashbook_csv(b"\xff\xfeinvalid")
        with self.assertRaises(CsvImportError):
            parse_cashbook_csv(b"a,b\x00c")

    def test_formula_prefix_is_flagged_without_changing_original(self):
        content = self.content().replace(b"Servicio sint\xc3\xa9tico 01", b"=2+2", 1)
        parsed = parse_cashbook_csv(content)
        row = parsed.valid_rows[0]
        self.assertEqual(row.normalized["detail"], "=2+2")
        self.assertIn("prefijo de fórmula", " ".join(row.warnings))
