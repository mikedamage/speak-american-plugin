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

    def test_inline_code_span_wrapping_across_lines(self):
        """A wrapped span must not mispair the backticks after it."""
        text = "Prefixes `un re mis\nover pre` then `colour` and colour.\n"
        out = translate(text)
        self.assertIn("`un re mis\nover pre`", out)
        self.assertIn("`colour`", out, "the span after a wrapped one is protected")
        self.assertTrue(out.rstrip().endswith("and color."))

    def test_wrapped_span_does_not_invert_the_spans_after_it(self):
        """The failure mode is inversion, not loss.

        When an opening span wraps, the spans on the continuation line pair off
        by one: the code fragments get exposed while the prose between them is
        protected. Shapes taken from a real hard-wrapped technical corpus.
        """
        text = (
            "Components are `Improved\n"
            "bermudagrass`, `Pasture` and `Tall fescue` in the centre column.\n"
        )
        out = translate(text)
        # Every code fragment survives verbatim...
        for fragment in ["`Improved\nbermudagrass`", "`Pasture`", "`Tall fescue`"]:
            self.assertIn(fragment, out, f"{fragment} must stay protected")
        # ...and the prose between them is still translated.
        self.assertIn("in the center column", out)

    def test_wrapped_span_holding_a_json_payload(self):
        text = (
            'The payload is `{"error":{"code":400,"message":"Pagination is not\n'
            'supported."}}` which the analyser returns with a grey flag.\n'
        )
        out = translate(text)
        self.assertIn('"Pagination is not\nsupported."}}`', out)
        self.assertIn("the analyzer returns with a gray flag", out)

    def test_wrapped_span_holding_a_shell_invocation(self):
        text = (
            "Run `parcels --county\n"
            "TN` then find `/parcel.json` for the colour data.\n"
        )
        out = translate(text)
        self.assertIn("`parcels --county\nTN`", out)
        self.assertIn("`/parcel.json`", out)
        self.assertIn("for the color data", out)

    def test_blank_line_ends_an_unclosed_span(self):
        text = "An unclosed ` tick.\n\nA colour after.\n"
        self.assertIn("A color after.", translate(text))

    def test_fence_backticks_do_not_pair_with_prose(self):
        text = "```\ncode ` tick\n```\n\nA colour after.\n"
        out = translate(text)
        self.assertIn("code ` tick", out)
        self.assertIn("A color after.", out)

    # --- fenced block / wrapped span interaction -------------------------
    # Block regions are blanked before the document-wide backtick scan. These
    # cover the ways a fence and an inline span can collide; shapes suggested
    # by a review of a real hard-wrapped corpus.

    def test_wrapped_span_immediately_followed_by_a_fence(self):
        text = (
            'The payload is `{"error":{"code":400,"message":"not\n'
            'supported"}}` and the colour is grey.\n'
            "```json\n"
            '{"colour": "grey"}\n'
            "```\n"
            "Trailing colour prose.\n"
        )
        out = translate(text)
        self.assertIn('"not\nsupported"}}`', out, "wrapped span must survive")
        self.assertIn('{"colour": "grey"}', out, "fence body must survive")
        self.assertIn("the color is gray", out)
        self.assertIn("Trailing color prose.", out)

    def test_unclosed_tick_then_blank_line_then_a_fence(self):
        """A fence's own backticks must not close an earlier unclosed run."""
        text = (
            "An unclosed ` tick in prose.\n\n"
            "Some colour prose here.\n\n"
            "```python\n"
            "colour = 1  # centre\n"
            "```\n\n"
            "Final grey line.\n"
        )
        out = translate(text)
        self.assertIn("colour = 1  # centre", out, "fence body must survive")
        self.assertIn("Some color prose here.", out)
        self.assertIn("Final gray line.", out)

    def test_unclosed_tick_with_fence_on_the_very_next_line(self):
        text = "Use `foo\n```python\ncolour = 1\n```\nmore colour\n"
        out = translate(text)
        self.assertIn("colour = 1", out)
        self.assertTrue(out.rstrip().endswith("more color"))

    def test_fence_body_with_an_odd_backtick_count(self):
        """The classic way a fence leaks a backtick into prose pairing."""
        text = "```\n` ` `\n```\nA `colour` and colour.\n"
        out = translate(text)
        self.assertIn("` ` `", out)
        self.assertIn("`colour`", out, "inline span after the fence stays paired")
        self.assertTrue(out.rstrip().endswith("and color."))

    def test_two_wrapped_spans_separated_by_a_fence(self):
        text = ("A `one\ntwo` mid colour.\n```\ncolour\n```\n"
                "B `three\nfour` end colour.\n")
        out = translate(text)
        self.assertIn("`one\ntwo`", out)
        self.assertIn("`three\nfour`", out)
        self.assertIn("```\ncolour\n```", out)
        self.assertEqual(out.count("mid color."), 1)
        self.assertEqual(out.count("end color."), 1)

    def test_span_wrapping_over_three_lines(self):
        text = "A `aa\nbb\ncc` then colour.\n"
        out = translate(text)
        self.assertIn("`aa\nbb\ncc`", out)
        self.assertIn("then color.", out)

    def test_stray_backtick_inside_a_tilde_fence(self):
        text = "~~~\na ` tick and colour\n~~~\nmore colour\n"
        out = translate(text)
        self.assertIn("a ` tick and colour", out)
        self.assertTrue(out.rstrip().endswith("more color"))

    def test_stray_backtick_inside_an_indented_block(self):
        text = "text\n\n    a ` tick colour\n\nmore colour\n"
        out = translate(text)
        self.assertIn("    a ` tick colour", out)
        self.assertTrue(out.rstrip().endswith("more color"))

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


class TestWordListIntegrity(unittest.TestCase):
    """Guards on the data file itself, where the columns can silently swap."""

    DATA = ROOT / "skills" / "speak-american" / "data"

    # UK -> US morphological transforms, used to detect a row whose columns
    # are backwards.
    RULES = [
        (r"ise$", "ize"), (r"ised$", "ized"), (r"ises$", "izes"),
        (r"ising$", "izing"), (r"isation$", "ization"), (r"iser$", "izer"),
        (r"isable$", "izable"), (r"yse$", "yze"), (r"ysed$", "yzed"),
        (r"our$", "or"), (r"ours$", "ors"), (r"oured$", "ored"),
        (r"tre$", "ter"), (r"tres$", "ters"), (r"bre$", "ber"),
        (r"ogue$", "og"), (r"ogues$", "ogs"), (r"ence$", "ense"),
        (r"^ae", "e"), (r"^oe", "e"), (r"eable$", "able"), (r"mme$", "m"),
        (r"lling$", "ling"), (r"lled$", "led"), (r"l$", "ll"),
    ]

    def rows(self):
        import csv
        out = []
        for name in ("words.tsv", "words-extra.tsv", "words-review.tsv"):
            path = self.DATA / name
            with path.open(encoding="utf8") as handle:
                for number, line in enumerate(handle, 1):
                    line = line.rstrip("\n")
                    if not line.strip() or line.lstrip().startswith("#"):
                        continue
                    self.assertIn("\t", line, f"{name}:{number} has no tab")
                    a, b = (x.strip() for x in line.split("\t", 1))
                    out.append((name, number, a, b))
        return out

    def test_no_reversed_columns(self):
        """No row may have the American spelling in column 1."""
        import re
        reversed_rows = []
        for name, number, uk, us in self.rows():
            forward = any(
                re.search(p, uk) and re.sub(p, r, uk, count=1) == us
                for p, r in self.RULES
            )
            backward = any(
                re.search(p, us) and re.sub(p, r, us, count=1) == uk
                for p, r in self.RULES
            )
            if backward and not forward:
                reversed_rows.append(f"{name}:{number} {uk} -> {us}")
        self.assertEqual(reversed_rows, [], "columns are swapped")

    def test_sources_are_plain_lowercase_words(self):
        """A source with punctuation or spaces can never match [A-Za-z]+."""
        for name, number, uk, _ in self.rows():
            self.assertTrue(uk.isalpha(), f"{name}:{number} source {uk!r} is not alphabetic")
            self.assertEqual(uk, uk.lower(), f"{name}:{number} source {uk!r} is not lowercase")

    def test_targets_are_alphabetic(self):
        for name, number, _, us in self.rows():
            self.assertTrue(us.isalpha(), f"{name}:{number} target {us!r} is not alphabetic")

    def test_no_redundant_duplicate_sources(self):
        """words-extra.tsv may override words.tsv, but not merely repeat it."""
        seen = {}
        for name, number, uk, us in self.rows():
            if uk in seen:
                prior_where, prior_us = seen[uk]
                self.assertNotEqual(
                    us, prior_us,
                    f"{name}:{number} repeats {uk!r} from {prior_where} with no change",
                )
            seen[uk] = (f"{name}:{number}", us)

    def test_no_duplicates_within_a_single_file(self):
        per_file = {}
        for name, number, uk, _ in self.rows():
            key = (name, uk)
            if key in per_file:
                self.fail(f"{name}:{number} duplicates {uk!r} from line {per_file[key]}")
            per_file[key] = number

    def test_source_never_equals_target(self):
        for name, number, uk, us in self.rows():
            self.assertNotEqual(uk.lower(), us.lower(), f"{name}:{number} is a no-op")

    def test_correct_american_words_are_never_translated(self):
        """Regression: the list must not rewrite already-correct prose."""
        for word in [
            "usable", "vectorization", "buses", "busing", "minibuses", "gases",
            "lit", "vice", "dealt", "knelt", "globally", "simultaneous",
            "cancellation", "curricula", "antennae", "bingeing", "unfeasible",
            "sanatorium", "jewelry", "color", "center", "gray",
            # Standard American English; Merriam-Webster's main entries.
            "aesthetic", "aesthetics", "aesthetically", "aesthete",
            "fillet", "filleted", "filleting", "fillets", "woolly", "woollies",
            # Inflected forms of entries dropped earlier; the singular going
            # without its plural is an easy miss.
            "cancellations", "philtres",
        ]:
            self.assertNotIn(word, VOCAB, f"{word!r} is correct American English")

    def test_dropped_entries_left_no_inflected_survivors(self):
        """Dropping a singular must take its plural and participles with it."""
        for stem in ["cancellation", "philtre", "fillet", "woolly", "aesthet",
                     "antenna", "minibus", "sanatorium"]:
            survivors = [k for k in VOCAB if k.startswith(stem)]
            self.assertEqual(survivors, [], f"{stem}: {survivors}")

    def test_double_l_entries_respect_the_stress_rule(self):
        """American doubles the l only when the final syllable is stressed.

        So the list may de-double LA-belled but must never touch con-TROLLED,
        which is correct in both dialects. This is the distinction no suffix
        rule can make, and the reason the list is curated by hand.

        The stress marks are hyphenated so this docstring does not trip the
        very rule it documents.
        """
        for word in ["controlled", "controlling", "uncontrolled", "installed",
                     "compelled", "expelled", "rebelled", "patrolled",
                     "propelled", "excelled", "enrolled", "annulled"]:
            self.assertIsNone(sa.resolve(word, VOCAB)[0],
                              f"{word!r} is correct American double-l")
        for word in ["labelled", "travelled", "modelled", "cancelled"]:
            self.assertIsNotNone(sa.resolve(word, VOCAB)[0],
                                 f"{word!r} is British and should be fixed")

    def test_corrected_pairs(self):
        for uk, us in [
            ("useable", "usable"),
            ("vectorisation", "vectorization"),
            ("jewellery", "jewelry"),
            ("pummelled", "pummeled"),
            ("pummelling", "pummeling"),
            ("snowploughs", "snowplows"),
            ("anaesthetist", "anesthetist"),
        ]:
            self.assertEqual(VOCAB.get(uk), us, f"{uk} should map to {us}")

    def test_vocabulary_file_is_not_loaded(self):
        """Register swaps live in a separate file and must stay opt-in."""
        self.assertTrue((self.DATA / "words-vocabulary.tsv").is_file())
        for word in ["petrol", "film", "rubbish", "pavement", "disc", "quarter"]:
            self.assertNotIn(word, VOCAB, f"{word!r} is vocabulary, not spelling")

    def test_usable_is_left_alone_end_to_end(self):
        text = "A usable feature after vectorization.\n"
        self.assertEqual(translate(text), text)


class TestReviewTier(unittest.TestCase):
    """Ambiguous pairs are reported but never auto-applied."""

    REVIEW = sa.load_review_vocabulary("us")

    def test_analyses_is_in_the_review_tier_not_the_main_list(self):
        self.assertNotIn("analyses", VOCAB)
        self.assertEqual(self.REVIEW.get("analyses"), "analyzes")

    def test_unambiguous_siblings_stay_auto_applied(self):
        """The -yse verb forms are always British; only the plural noun is not."""
        self.assertEqual(VOCAB.get("analyse"), "analyze")
        self.assertEqual(VOCAB.get("analysed"), "analyzed")
        self.assertEqual(VOCAB.get("analysing"), "analyzing")

    def _run(self, text, *args):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "f.md"
            path.write_text(text, encoding="utf-8")
            code = sa.main([str(path), "--no-gitignore", *args])
            return code, path.read_text(encoding="utf-8")

    def test_write_does_not_apply_a_review_hit(self):
        text = "The symbols these analyses use.\n"
        code, after = self._run(text, "--write")
        self.assertEqual(after, text, "review hit must not be rewritten")
        self.assertEqual(code, sa.EXIT_FOUND, "pending review should exit 1")

    def test_write_still_applies_normal_hits_on_the_same_line(self):
        text = "These analyses use a grey colour.\n"
        code, after = self._run(text, "--write")
        self.assertEqual(after, "These analyses use a gray color.\n")
        self.assertEqual(code, sa.EXIT_FOUND)

    def test_write_exits_clean_when_nothing_pending(self):
        code, after = self._run("A grey colour.\n", "--write")
        self.assertEqual(after, "A gray color.\n")
        self.assertEqual(code, sa.EXIT_CLEAN)

    def test_review_flag_appears_in_change_records(self):
        text = "These analyses use a grey colour.\n"
        spans = sa.spans_for(Path("f.md"), text)
        lookup = dict(VOCAB)
        lookup.update(self.REVIEW)
        changes = sa.find_changes(text, spans, lookup, frozenset(self.REVIEW))
        by_word = {c.old: c.review for c in changes}
        self.assertTrue(by_word["analyses"])
        self.assertFalse(by_word["grey"])
        self.assertFalse(by_word["colour"])

    def test_aesthetic_is_left_alone(self):
        for text in ["The aesthetic of it.\n", "Its aesthetics matter.\n",
                     "Aesthetically pleasing.\n"]:
            self.assertEqual(translate(text), text)

    def test_reusable_and_unusable_are_not_matched(self):
        """The word regex matches maximal letter runs, so an embedded word
        is never seen as a separate token."""
        text = "A reusable analysis helper; cover triage - unusable.\n"
        self.assertEqual(translate(text), text)


class TestPrefixResolution(unittest.TestCase):
    """A prefixed derivative is its own token, so the stem is resolved."""

    REVIEW = sa.load_review_vocabulary("us")

    def resolve(self, word, ignored=frozenset()):
        lookup = dict(VOCAB)
        lookup.update(self.REVIEW)
        return sa.resolve(word, lookup, frozenset(self.REVIEW), ignored)

    def test_reported_miss_is_caught(self):
        text = "# a mislabelled file is the failure this module catches\n"
        self.assertEqual(
            translate(text, ".py"),
            "# a mislabeled file is the failure this module catches\n",
        )

    def test_common_derivatives(self):
        for word, expected in [
            ("mislabelled", "mislabeled"),
            ("unfavourable", "unfavorable"),
            ("reorganised", "reorganized"),
            ("unrecognised", "unrecognized"),
            ("overemphasised", "overemphasized"),
            ("remould", "remold"),
            ("demould", "demold"),
            ("uncatalogued", "uncataloged"),
            ("oversceptical", "overskeptical"),
        ]:
            self.assertEqual(self.resolve(word)[0], expected, word)

    def test_does_not_fire_on_coincidental_splits(self):
        """The stem must be a listed word, not just a leftover string."""
        for word in [
            "reusable", "unusable", "revise", "research", "release", "reuse",
            "misuse", "demise", "precise", "concise", "interest", "understand",
            "subtle", "coverage", "recover", "discover", "proper", "content",
            "cover", "region", "designed", "detail", "resource", "internal",
        ]:
            self.assertIsNone(self.resolve(word)[0], f"{word!r} should not match")

    def test_short_stems_are_refused(self):
        """A stem below MIN_STEM_LENGTH is too short to trust."""
        self.assertGreaterEqual(sa.MIN_STEM_LENGTH, 4)
        lookup = {"abc": "xyz"}
        self.assertIsNone(sa.resolve("reabc", lookup)[0])

    def test_longest_prefix_wins(self):
        self.assertEqual(sa.PREFIXES[0], max(sa.PREFIXES, key=len))
        self.assertLess(sa.PREFIXES.index("under"), sa.PREFIXES.index("un"))

    def test_case_is_preserved_on_a_derivative(self):
        self.assertEqual(translate("Mislabelled files.\n"), "Mislabeled files.\n")
        self.assertEqual(translate("MISLABELLED FILES.\n"), "MISLABELED FILES.\n")

    def test_review_flag_propagates_through_a_prefix(self):
        replacement, review = self.resolve("reanalyses")
        self.assertEqual(replacement, "reanalyzes")
        self.assertTrue(review, "a derivative of a review word stays review")

    def test_exclusion_applies_to_the_whole_word(self):
        self.assertIsNone(self.resolve("mislabelled", frozenset({"mislabelled"}))[0])
        self.assertEqual(self.resolve("mislabelled")[0], "mislabeled")

    def test_derivative_is_not_applied_when_stem_is_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "f.md"
            path.write_text("The reanalyses run nightly.\n", encoding="utf-8")
            code = sa.main([str(path), "--no-gitignore", "--write"])
            self.assertEqual(path.read_text(encoding="utf-8"),
                             "The reanalyses run nightly.\n")
            self.assertEqual(code, sa.EXIT_FOUND)

    def test_identifier_guard_still_applies_to_derivatives(self):
        self.assertEqual(translate("The mislabelled_file var.\n"),
                         "The mislabelled_file var.\n")


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
