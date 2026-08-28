"""Tests for the speak-american translation engine.

Run with: python3 -m unittest discover -s tests -v
"""

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "skills" / "speak-american" / "scripts"))

import speak_american as sa  # noqa: E402


VOCAB = sa.load_vocabulary("us")


def translate(text, suffix=".md"):
    """Run the full pipeline on a string and return the rewritten string."""
    path = Path("sample" + suffix)
    spans = sa.spans_for(path, text)
    if spans is None:
        return text
    return sa.apply_changes(text, sa.find_changes(text, spans, VOCAB))


class TestCasePreservation(unittest.TestCase):
    def test_lowercase(self):
        self.assertEqual(sa.match_case("colour", "color"), "color")

    def test_title_case(self):
        self.assertEqual(sa.match_case("Colour", "color"), "Color")

    def test_all_caps(self):
        self.assertEqual(sa.match_case("COLOUR", "color"), "COLOR")

    def test_single_letter_upper_is_title_not_caps(self):
        self.assertEqual(sa.match_case("A", "b"), "B")

    def test_mixed_case_keeps_leading_case(self):
        self.assertEqual(sa.match_case("cOLOUR", "color"), "color")

    def test_end_to_end_caps(self):
        self.assertEqual(translate("The COLOUR is GREY."), "The COLOR is GRAY.")

    def test_end_to_end_title(self):
        self.assertEqual(translate("A Colour and a Grey."), "A Color and a Gray.")


class TestMarkdownStructure(unittest.TestCase):
    def test_fenced_code_is_untouched(self):
        text = "Colour here.\n\n```python\ncolour = 1  # colour\n```\n\nAnd colour.\n"
        out = translate(text)
        self.assertIn("colour = 1  # colour", out)
        self.assertTrue(out.startswith("Color here."))
        self.assertTrue(out.rstrip().endswith("And color."))

    def test_tilde_fence(self):
        text = "~~~\ncolour\n~~~\ncolour\n"
        out = translate(text)
        self.assertIn("~~~\ncolour\n~~~", out)
        self.assertTrue(out.rstrip().endswith("color"))

    def test_nested_longer_fence_not_closed_early(self):
        text = "````\n```\ncolour\n```\n````\ncolour\n"
        out = translate(text)
        self.assertIn("```\ncolour\n```", out)
        self.assertTrue(out.rstrip().endswith("color"))

    def test_inline_code(self):
        self.assertEqual(translate("Use `colour` for colour."), "Use `colour` for color.")

    def test_inline_code_double_backtick(self):
        self.assertEqual(translate("``a ` colour`` colour"), "``a ` colour`` color")

    def test_indented_code_block(self):
        text = "Text.\n\n    colour_thing = 1\n\nMore colour.\n"
        out = translate(text)
        self.assertIn("    colour_thing = 1", out)
        self.assertIn("More color.", out)

    def test_list_continuation_is_not_code(self):
        text = "- item\n\n    a colour in a list\n"
        self.assertIn("a color in a list", translate(text))

    def test_link_destination_preserved(self):
        text = "[analyse docs](https://x.com/analyse-behaviour)"
        self.assertEqual(translate(text), "[analyze docs](https://x.com/analyse-behaviour)")

    def test_reference_label_preserved_both_ends(self):
        text = "See [the centre][centre-ref].\n\n[centre-ref]: https://x.com/centre\n"
        out = translate(text)
        self.assertIn("[the center][centre-ref]", out)
        self.assertIn("[centre-ref]: https://x.com/centre", out)

    def test_bare_url_preserved(self):
        self.assertEqual(
            translate("Visit https://x.com/colour now."),
            "Visit https://x.com/colour now.",
        )

    def test_email_preserved(self):
        self.assertEqual(
            translate("Mail colour@grey.com about colour."),
            "Mail colour@grey.com about color.",
        )

    def test_html_tag_attributes_preserved(self):
        text = '<div class="colour">colour</div>'
        out = translate(text)
        self.assertIn('class="colour"', out)
        self.assertIn(">color<", out)

    def test_frontmatter_key_preserved_value_translated(self):
        text = "---\ncolour: the colour\n---\n\nBody colour.\n"
        out = translate(text)
        self.assertIn("colour: the color", out)
        self.assertIn("Body color.", out)

    def test_frontmatter_delimiters_intact(self):
        out = translate("---\ntitle: colour\n---\n")
        self.assertTrue(out.startswith("---\n"))
        self.assertIn("\n---\n", out)

    def test_footnote_marker_preserved(self):
        text = "A colour[^centre-note].\n\n[^centre-note]: A centre.\n"
        out = translate(text)
        self.assertIn("[^centre-note]", out)
        self.assertIn("A color", out)


class TestCodeComments(unittest.TestCase):
    def test_python_identifiers_and_strings_untouched(self):
        text = 'colour_x = "grey"  # the colour\n'
        self.assertEqual(translate(text, ".py"), 'colour_x = "grey"  # the color\n')

    def test_python_docstring_translated(self):
        text = '"""Normalise the colour."""\n'
        self.assertEqual(translate(text, ".py"), '"""Normalize the color."""\n')

    def test_python_non_docstring_string_untouched(self):
        text = 'x = """SELECT colour"""\n'
        self.assertEqual(translate(text, ".py"), text)

    def test_python_syntax_error_falls_back(self):
        text = "def f(:\n  # the colour\n"
        self.assertEqual(translate(text, ".py"), "def f(:\n  # the color\n")

    def test_c_line_and_block_comments(self):
        text = 'const colour = "colour"; // the colour\n/* a colour */\n'
        out = translate(text, ".ts")
        self.assertIn('const colour = "colour";', out)
        self.assertIn("// the color", out)
        self.assertIn("/* a color */", out)

    def test_hash_inside_string_is_not_a_comment(self):
        text = 'x = "a # colour"  # real colour\n'
        out = translate(text, ".py")
        self.assertIn('"a # colour"', out)
        self.assertIn("# real color", out)

    def test_double_slash_inside_string_is_not_a_comment(self):
        text = 'const u = "https://x.com/colour"; // fix colour\n'
        out = translate(text, ".ts")
        self.assertIn('"https://x.com/colour"', out)
        self.assertIn("// fix color", out)

    def test_apostrophe_does_not_swallow_file(self):
        text = "// don't break the colour\n// second colour\n"
        out = translate(text, ".ts")
        self.assertIn("don't break the color", out)
        self.assertIn("second color", out)

    def test_sql_comments(self):
        text = "SELECT colour FROM t; -- the colour\n"
        out = translate(text, ".sql")
        self.assertIn("SELECT colour FROM t;", out)
        self.assertIn("-- the color", out)

    def test_lua_block_comment(self):
        text = "local colour = 1\n--[[ the colour ]]\n"
        out = translate(text, ".lua")
        self.assertIn("local colour = 1", out)
        self.assertIn("--[[ the color ]]", out)

    def test_url_in_comment_preserved(self):
        text = "# see https://x.com/colour for colour\n"
        out = translate(text, ".py")
        self.assertIn("https://x.com/colour", out)
        self.assertIn("for color", out)

    def test_unknown_extension_is_skipped(self):
        self.assertIsNone(sa.spans_for(Path("x.bin"), "colour"))


class TestIdentifierGuard(unittest.TestCase):
    def test_snake_case_in_prose_untouched(self):
        self.assertEqual(translate("The colour_name field."), "The colour_name field.")

    def test_trailing_underscore(self):
        self.assertEqual(translate("A colour_ thing."), "A colour_ thing.")

    def test_digit_adjacent(self):
        self.assertEqual(translate("Use colour2 and sha256colour."),
                         "Use colour2 and sha256colour.")

    def test_camel_case_untouched(self):
        self.assertEqual(translate("The myColour value."), "The myColour value.")

    def test_hyphenated_prose_is_translated(self):
        self.assertEqual(translate("A colour-coded chart."), "A color-coded chart.")


class TestVocabulary(unittest.TestCase):
    def test_base_list_loaded(self):
        self.assertGreater(len(VOCAB), 1800)

    def test_known_pairs(self):
        for uk, us in [
            ("colour", "color"), ("centre", "center"), ("grey", "gray"),
            ("capitalisation", "capitalization"), ("behaviour", "behavior"),
            ("artefact", "artifact"), ("licence", "license"),
        ]:
            self.assertEqual(VOCAB.get(uk), us, f"{uk} -> {us}")

    def test_extras_are_merged(self):
        self.assertEqual(VOCAB.get("parameterise"), "parameterize")
        self.assertEqual(VOCAB.get("tokeniser"), "tokenizer")

    def test_no_identity_pairs(self):
        for source, target in VOCAB.items():
            self.assertNotEqual(source, target.lower())

    def test_exclusions_are_honoured(self):
        vocab = sa.load_vocabulary("us", extra_ignores=["colour"])
        self.assertNotIn("colour", vocab)
        self.assertIn("centre", vocab)

    def test_uk_target_is_a_function(self):
        vocab = sa.load_vocabulary("uk")
        self.assertEqual(vocab.get("color"), "colour")
        self.assertEqual(vocab.get("center"), "centre")


class TestSpanArithmetic(unittest.TestCase):
    def test_merge_overlapping(self):
        self.assertEqual(sa.merge_spans([(0, 5), (3, 8), (10, 12)]), [(0, 8), (10, 12)])

    def test_invert(self):
        self.assertEqual(sa.invert_spans([(2, 4)], 10), [(0, 2), (4, 10)])

    def test_invert_empty(self):
        self.assertEqual(sa.invert_spans([], 5), [(0, 5)])

    def test_subtract_middle(self):
        self.assertEqual(sa.subtract_spans([(0, 10)], [(3, 5)]), [(0, 3), (5, 10)])

    def test_subtract_everything(self):
        self.assertEqual(sa.subtract_spans([(0, 10)], [(0, 10)]), [])


class TestReportingAndIO(unittest.TestCase):
    def test_line_and_column_are_one_based(self):
        text = "ok\nthe colour\n"
        changes = sa.find_changes(text, [(0, len(text))], VOCAB)
        self.assertEqual((changes[0].line, changes[0].column), (2, 5))

    def test_idempotent(self):
        text = "The COLOUR is grey.\n\n```\ncolour\n```\n"
        once = translate(text)
        self.assertEqual(translate(once), once)

    def test_atomic_write_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "f.md"
            path.write_text("The colour.\n", encoding="utf-8")
            rc = sa.main([str(path), "--write", "--no-gitignore"])
            self.assertEqual(rc, sa.EXIT_CLEAN)
            self.assertEqual(path.read_text(encoding="utf-8"), "The color.\n")

    def test_dry_run_does_not_modify(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "f.md"
            path.write_text("The colour.\n", encoding="utf-8")
            rc = sa.main([str(path), "--no-gitignore"])
            self.assertEqual(rc, sa.EXIT_FOUND)
            self.assertEqual(path.read_text(encoding="utf-8"), "The colour.\n")

    def test_clean_file_exits_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "f.md"
            path.write_text("The color.\n", encoding="utf-8")
            self.assertEqual(sa.main([str(path), "--no-gitignore"]), sa.EXIT_CLEAN)

    def test_crlf_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "f.md"
            path.write_bytes(b"The colour.\r\nMore grey.\r\n")
            sa.main([str(path), "--write", "--no-gitignore"])
            self.assertEqual(path.read_bytes(), b"The color.\r\nMore gray.\r\n")


if __name__ == "__main__":
    unittest.main(verbosity=2)
