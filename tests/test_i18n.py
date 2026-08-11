"""Application-wide language catalogue and negotiation regression tests."""

from __future__ import annotations

import unittest
from html import unescape
from types import SimpleNamespace

from fasthtml.common import Div, Input, P

from graph.clinic_assistant import _language_message
from scripts.update_i18n import _fields, _markup_signature, source_strings
from web.i18n import (
    LANGUAGES, catalog, detect_language, format_currency, format_date, get_lang,
    localize_tree, preserve, safe_return_path, set_lang, t, using_lang,
)
from web.layout import page
from web.compliance import compliance_page


class LanguageCatalogueTests(unittest.TestCase):
    def test_catalogues_exactly_cover_application_copy(self):
        expected = source_strings()
        for lang in LANGUAGES:
            if lang == "en":
                continue
            with self.subTest(lang=lang):
                translations = catalog(lang)
                self.assertEqual(set(translations), expected)
                self.assertTrue(all(value.strip() for value in translations.values()))
                for source, translated in translations.items():
                    self.assertEqual(_fields(source), _fields(translated))
                    self.assertEqual(_markup_signature(source), _markup_signature(translated))

    def test_english_is_the_source_and_unknown_languages_fall_back(self):
        text = "Modern clinical care, made personal."
        self.assertEqual(t(text, "en"), text)
        self.assertEqual(t(text, "xx"), text)

    def test_every_language_translates_the_primary_heading(self):
        text = "Modern clinical care, made personal."
        for lang in LANGUAGES:
            if lang != "en":
                with self.subTest(lang=lang):
                    self.assertNotEqual(t(text, lang), text)

    def test_compliance_page_is_complete_in_every_language(self):
        heading = "Compliance & Trust for European Private Clinics"
        for lang in LANGUAGES:
            with self.subTest(lang=lang):
                rendered = unescape(str(compliance_page(lang)))
                self.assertIn(t(heading, lang), rendered)
                self.assertIn('href="/compliance"', rendered)
                self.assertIn('href="/developers"', rendered)
                self.assertIn('compliance@fastclinic.dev', rendered)
                self.assertNotIn("Traceback", rendered)

    def test_request_context_is_isolated_and_supports_interpolation(self):
        with using_lang("de"):
            self.assertEqual(t("Invoices ({count})", count=3), "Rechnungen (3)")
        self.assertEqual(t("Invoices ({count})", count=3), "Invoices (3)")

    def test_tree_localisation_changes_ui_but_not_unknown_clinical_data(self):
        clinical_note = "Patient reports bespoke symptom wording"
        tree = Div(P("Overview"), P(clinical_note), P(preserve("Overview")),
                   Input(placeholder="Search"))
        rendered = str(localize_tree(tree, "de"))
        self.assertIn(t("Overview", "de"), rendered)
        self.assertIn(t("Search", "de"), rendered)
        self.assertIn(clinical_note, rendered)
        self.assertIn(">Overview<", rendered)

    def test_authenticated_shell_embeds_language_and_browser_catalogue(self):
        with using_lang("de"):
            rendered = str(page("dashboard", "FastClinic", "user@example.com", "thread",
                                Div("Clinic Overview"), lang="de"))
        self.assertIn(t("Clinic Overview", "de"), rendered)
        self.assertIn("window.FASTCLINIC_I18N=", rendered)
        self.assertIn('value="de" selected', rendered)

    def test_locale_formatters_and_model_language_contract(self):
        self.assertEqual(format_currency(1234.5, "GBP", "de", 2), "1\u00a0234,50\u00a0£")
        self.assertEqual(format_date("2026-08-10", "de"), "10.08.2026")
        prompt = _language_message("Show patient ABC-123", "de")
        self.assertIn("Reply entirely in German", prompt)
        self.assertIn("Preserve patient names", prompt)
        self.assertIn("Show patient ABC-123", prompt)


class LanguageNegotiationTests(unittest.TestCase):
    @staticmethod
    def request(header: str):
        return SimpleNamespace(headers={"accept-language": header})

    def test_region_and_quality_are_respected(self):
        request = self.request("en-US;q=0.4, et-EE;q=0.9, de;q=0.7")
        self.assertEqual(detect_language(request), "et")

    def test_zero_quality_is_not_selected(self):
        self.assertEqual(detect_language(self.request("et;q=0")), "en")

    def test_session_selection_wins_over_browser_preference(self):
        session = {"lang": "fi"}
        self.assertEqual(get_lang(session, self.request("fr")), "fi")

    def test_browser_selection_is_persisted(self):
        session = {}
        self.assertEqual(get_lang(session, self.request("lt-LT")), "lt")
        self.assertEqual(session["lang"], "lt")

    def test_invalid_selection_does_not_replace_session(self):
        session = {"lang": "no"}
        self.assertEqual(set_lang(session, "xx"), "no")

    def test_safe_local_return_path_is_preserved(self):
        self.assertEqual(safe_return_path("/developers?view=all"), "/developers?view=all")

    def test_external_and_encoded_open_redirects_are_rejected(self):
        for target in ("https://example.com", "//example.com", "/%2fexample.com", "/\\example.com"):
            with self.subTest(target=target):
                self.assertEqual(safe_return_path(target), "/")


if __name__ == "__main__":
    unittest.main()
