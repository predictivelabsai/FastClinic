"""Public-language catalogue and negotiation regression tests."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from scripts.update_i18n import source_strings
from web.i18n import LANGUAGES, catalog, detect_language, get_lang, safe_return_path, set_lang, t


class LanguageCatalogueTests(unittest.TestCase):
    def test_catalogues_exactly_cover_public_copy(self):
        expected = source_strings()
        for lang in LANGUAGES:
            if lang == "en":
                continue
            with self.subTest(lang=lang):
                translations = catalog(lang)
                self.assertEqual(set(translations), expected)
                self.assertTrue(all(value.strip() for value in translations.values()))

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
