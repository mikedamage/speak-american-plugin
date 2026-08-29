#!/usr/bin/env python3
"""Translate British English spellings to American English in prose and comments.

Deterministic: every change comes from a static word-pair list. No heuristics
about meaning, no model in the loop.

Structure-aware, so it does not corrupt what it walks over:
  * Markdown  - skips fenced and indented code, inline code spans, link and
                image destinations, reference labels, autolinks, raw HTML tags,
                and front matter keys.
  * Source    - translates comments only (plus Python docstrings), never
                identifiers or arbitrary string literals.
  * Plain text- translates everything except URLs and email addresses.

Standard library only. No install step, no virtualenv, no network.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

EXIT_CLEAN = 0
EXIT_FOUND = 1
EXIT_ERROR = 2

# ---------------------------------------------------------------------------
# Word list
# ---------------------------------------------------------------------------


def _read_pairs(path):
    pairs = {}
    if not path.is_file():
        return pairs
    with path.open(encoding="utf8") as handle:
        for line in handle:
            line = line.split("#", 1)[0].strip() if line.lstrip().startswith("#") else line.rstrip("\n")
            if not line.strip() or "\t" not in line:
                continue
            left, right = (part.strip() for part in line.split("\t", 1))
            if left and right and left != right:
                pairs[left.lower()] = right
    return pairs


def _read_ignores(path):
    words = set()
    if not path.is_file():
        return words
    with path.open(encoding="utf8") as handle:
        for line in handle:
            line = line.split("#", 1)[0].strip()
            if line:
                words.add(line.lower())
    return words


def _finalize(pairs, target, data_dir, extra_ignores):
    ignores = _read_ignores(data_dir / "words-ignore.list")
    ignores.update(word.lower() for word in extra_ignores)

    if target == "uk":
        flipped = {}
        for uk, us in pairs.items():
            # Two British forms can share one American form. Keep the
            # first, so the reverse mapping stays a function.
            flipped.setdefault(us.lower(), uk)
        pairs = flipped

    return {k: v for k, v in pairs.items() if k not in ignores}


def load_vocabulary(target="us", data_dir=DATA_DIR, extra_ignores=()):
    """Return {source_word: replacement} for the requested target dialect."""
    pairs = _read_pairs(data_dir / "words.tsv")
    pairs.update(_read_pairs(data_dir / "words-extra.tsv"))
    return _finalize(pairs, target, data_dir, extra_ignores)


def load_ignores(data_dir=DATA_DIR, extra_ignores=()):
    """Words never to translate, including as a prefixed derivative's stem."""
    ignores = _read_ignores(data_dir / "words-ignore.list")
    ignores.update(word.lower() for word in extra_ignores)
    return ignores


def load_review_vocabulary(target="us", data_dir=DATA_DIR, extra_ignores=()):
    """Ambiguous pairs: reported, but never applied by --write.

    A word belongs here when the British form is also correct American English
    under another reading, so no lexical rule can decide it. `analyses` is the
    plural of `analysis` in both dialects and separately the British verb; only
    the verb is wrong in American English, and telling them apart is a
    grammatical judgment this tool deliberately does not make.
    """
    pairs = _read_pairs(data_dir / "words-review.tsv")
    return _finalize(pairs, target, data_dir, extra_ignores)


# ---------------------------------------------------------------------------
# Case preservation
# ---------------------------------------------------------------------------


def match_case(original, replacement):
    """Reshape `replacement` to carry the capitalization pattern of `original`."""
    if original.isupper() and len(original) > 1:
        return replacement.upper()
    if original[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    if original.islower():
        return replacement
    # Mixed-case oddity (mIxEd). Preserve only the leading character's case.
    if original[:1].islower():
        return replacement[:1].lower() + replacement[1:]
    return replacement


# ---------------------------------------------------------------------------
# Span helpers
# ---------------------------------------------------------------------------


def invert_spans(spans, length):
    """Complement of `spans` across [0, length)."""
    result = []
    cursor = 0
    for start, end in merge_spans(spans):
        if start > cursor:
            result.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < length:
        result.append((cursor, length))
    return result


def merge_spans(spans):
    ordered = sorted(s for s in spans if s[0] < s[1])
    merged = []
    for start, end in ordered:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def subtract_spans(spans, holes):
    """Remove `holes` from `spans`."""
    holes = merge_spans(holes)
    result = []
    for start, end in merge_spans(spans):
        cursor = start
        for hole_start, hole_end in holes:
            if hole_end <= cursor or hole_start >= end:
                continue
            if hole_start > cursor:
                result.append((cursor, hole_start))
            cursor = max(cursor, hole_end)
            if cursor >= end:
                break
        if cursor < end:
            result.append((cursor, end))
    return result


# ---------------------------------------------------------------------------
# Universally protected content
# ---------------------------------------------------------------------------

URL_RE = re.compile(r"""(?:[a-z][a-z0-9+.-]*://|www\.|mailto:)[^\s<>"'`\])}]+""", re.I)
EMAIL_RE = re.compile(r"[^\s<>()\[\]{}\"'`,;:]+@[^\s<>()\[\]{}\"'`,;:]+\.[a-z]{2,}", re.I)


def universal_holes(text):
    holes = [m.span() for m in URL_RE.finditer(text)]
    holes += [m.span() for m in EMAIL_RE.finditer(text)]
    return holes


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------

FENCE_RE = re.compile(r"^(\s{0,3})(`{3,}|~{3,})(.*)$")
LIST_ITEM_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s")
FRONTMATTER_DELIM_RE = re.compile(r"^(---|\+\+\+)\s*$")

# Link/image destination: the (...) half of [text](dest) and ![alt](dest).
LINK_DEST_RE = re.compile(r"\]\(([^()]*(?:\([^()]*\)[^()]*)*)\)")
# Reference label: the [ref] half of [text][ref], and footnote markers [^id].
REF_LABEL_RE = re.compile(r"\](\[[^\]]*\])")
FOOTNOTE_RE = re.compile(r"\[\^[^\]]*\]")
# Link reference definition: [id]: https://... "Title"
REF_DEF_RE = re.compile(r"^(\s{0,3}\[[^\]]+\]:\s*)(\S+)")
# Raw HTML tag or autolink.
HTML_TAG_RE = re.compile(r"<[^>\s][^>]*>")


def _inline_code_spans(text, offset=0):
    """CommonMark-ish inline code: a run of N backticks closed by a run of N.

    Scanned over the whole document, not line by line, because a code span may
    wrap across lines. Getting this wrong mispairs every later backtick on the
    line and silently leaves real code unprotected. A span cannot contain a
    blank line, since that ends the paragraph.
    """
    spans = []
    index = 0
    length = len(text)
    while index < length:
        if text[index] != "`":
            index += 1
            continue
        run_start = index
        while index < length and text[index] == "`":
            index += 1
        run_len = index - run_start
        # Look for a closing run of exactly the same length.
        search = index
        closed = False
        while search < length:
            if text[search] != "`":
                search += 1
                continue
            close_start = search
            while search < length and text[search] == "`":
                search += 1
            if search - close_start == run_len:
                if "\n\n" in text[run_start:search]:
                    break       # paragraph ended; the run was never closed
                spans.append((offset + run_start, offset + search))
                closed = True
                break
        if not closed:
            # Unclosed run; protect the backticks themselves and move past them.
            spans.append((offset + run_start, offset + index))
            continue
        index = search
    return spans


def markdown_translatable_spans(text):
    """Spans of a Markdown document that hold translatable prose."""
    protected = []
    lines = text.split("\n")
    offsets = []
    cursor = 0
    for line in lines:
        offsets.append(cursor)
        cursor += len(line) + 1

    fence_char = None
    fence_len = 0
    in_frontmatter = False
    in_list = False
    prev_blank = True

    for index, line in enumerate(lines):
        start = offsets[index]
        end = start + len(line)
        stripped = line.strip()

        # --- YAML/TOML front matter -----------------------------------------
        if index == 0 and FRONTMATTER_DELIM_RE.match(line):
            in_frontmatter = True
            protected.append((start, end))
            continue
        if in_frontmatter:
            if FRONTMATTER_DELIM_RE.match(line):
                in_frontmatter = False
                protected.append((start, end))
            else:
                # Protect the key; the value is prose worth fixing.
                colon = line.find(":")
                protected.append((start, start + colon + 1) if colon != -1 else (start, end))
            continue

        # --- Fenced code ----------------------------------------------------
        if fence_char is not None:
            protected.append((start, end + 1))
            closing = FENCE_RE.match(line)
            if closing and closing.group(2)[0] == fence_char and len(closing.group(2)) >= fence_len:
                if not closing.group(3).strip():
                    fence_char = None
            prev_blank = False
            continue

        opening = FENCE_RE.match(line)
        if opening:
            fence_char = opening.group(2)[0]
            fence_len = len(opening.group(2))
            protected.append((start, end + 1))
            prev_blank = False
            continue

        # --- Indented code blocks -------------------------------------------
        if not stripped:
            prev_blank = True
            continue
        if LIST_ITEM_RE.match(line):
            in_list = True
        elif not line.startswith((" ", "\t")):
            in_list = False

        indent = len(line) - len(line.lstrip(" \t"))
        if indent >= 4 and prev_blank and not in_list:
            protected.append((start, end))
            prev_blank = False
            continue
        prev_blank = False

        # --- Inline constructs ----------------------------------------------
        ref_def = REF_DEF_RE.match(line)
        if ref_def:
            protected.append((start, start + ref_def.end()))

        for match in LINK_DEST_RE.finditer(line):
            protected.append((start + match.start(1), start + match.end(1)))
        for match in REF_LABEL_RE.finditer(line):
            protected.append((start + match.start(1), start + match.end(1)))
        for match in FOOTNOTE_RE.finditer(line):
            protected.append((start + match.start(), start + match.end()))
        for match in HTML_TAG_RE.finditer(line):
            protected.append((start + match.start(), start + match.end()))

    # Inline code is scanned document-wide so a span may wrap across lines.
    # Blank out the block-level protected regions first (preserving offsets and
    # newlines) so backticks inside fenced code cannot pair with prose.
    #
    # This step was distrusted when written and then probed: eight adversarial
    # fence/span interactions in TestMarkdownStructure, including a fence body
    # with an odd backtick count, a fence on the line directly after an
    # unclosed run, and two wrapped spans separated by a fence. All hold. The
    # masking is load-bearing rather than incidental -- do not simplify it away
    # without re-running those tests.
    masked = list(text)
    for start, end in merge_spans(protected):
        for index in range(start, min(end, len(masked))):
            if masked[index] != "\n":
                masked[index] = " "
    protected.extend(_inline_code_spans("".join(masked)))

    protected.extend(universal_holes(text))
    return invert_spans(protected, len(text))


# ---------------------------------------------------------------------------
# Plain text
# ---------------------------------------------------------------------------


def text_translatable_spans(text):
    return subtract_spans([(0, len(text))], universal_holes(text))


# ---------------------------------------------------------------------------
# Source code comments
# ---------------------------------------------------------------------------


class CommentSyntax:
    def __init__(self, line=(), block=(), strings=('"', "'"), raw_strings=()):
        self.line = tuple(line)
        self.block = tuple(block)
        self.strings = tuple(strings)
        self.raw_strings = tuple(raw_strings)


C_LIKE = CommentSyntax(line=("//",), block=(("/*", "*/"),), strings=('"', "'", "`"))
HASH = CommentSyntax(line=("#",), strings=('"', "'"))
SQL_LIKE = CommentSyntax(line=("--",), block=(("/*", "*/"),), strings=("'", '"'))
LUA = CommentSyntax(line=("--",), block=(("--[[", "]]"),), strings=('"', "'"))
XML_LIKE = CommentSyntax(line=(), block=(("<!--", "-->"),), strings=())
CSS = CommentSyntax(line=(), block=(("/*", "*/"),), strings=('"', "'"))

SYNTAX_BY_EXT = {}
for _exts, _syntax in [
    ((".c", ".h", ".cc", ".cpp", ".cxx", ".hpp", ".hh", ".m", ".mm",
      ".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".java", ".go",
      ".rs", ".swift", ".kt", ".kts", ".scala", ".cs", ".php", ".dart",
      ".groovy", ".proto", ".jsonc", ".zig"), C_LIKE),
    ((".py", ".pyi", ".rb", ".sh", ".bash", ".zsh", ".fish", ".pl", ".pm",
      ".r", ".jl", ".ex", ".exs", ".nim", ".cr", ".tf", ".yaml", ".yml",
      ".toml", ".ini", ".cfg", ".conf", ".mk", ".dockerfile", ".gitignore"), HASH),
    ((".sql", ".psql", ".hql"), SQL_LIKE),
    ((".lua",), LUA),
    ((".html", ".htm", ".xml", ".svg", ".vue", ".svelte"), XML_LIKE),
    ((".css", ".scss", ".sass", ".less"), CSS),
]:
    for _ext in _exts:
        SYNTAX_BY_EXT[_ext] = _syntax


def comment_spans(text, syntax):
    """Scan `text`, returning spans that are comments.

    String-aware, so a `#` or `//` inside a string literal is not mistaken for
    the start of a comment, and a URL inside a string stays intact.
    """
    spans = []
    index = 0
    length = len(text)
    while index < length:
        char = text[index]

        # Escape inside nothing - only relevant within strings, handled below.
        if char == "\\":
            index += 2
            continue

        # String literals: skip over them wholesale.
        matched_string = None
        for quote in syntax.strings:
            triple = quote * 3
            if text.startswith(triple, index):
                matched_string = triple
                break
            if text.startswith(quote, index):
                matched_string = quote
                break
        if matched_string:
            index += len(matched_string)
            while index < length:
                if text[index] == "\\":
                    index += 2
                    continue
                if text.startswith(matched_string, index):
                    index += len(matched_string)
                    break
                # A single-quote string never spans lines; bail at newline so a
                # stray apostrophe (don't) cannot swallow the rest of the file.
                if len(matched_string) == 1 and text[index] == "\n":
                    break
                index += 1
            continue

        # Block comments.
        block_hit = False
        for opener, closer in syntax.block:
            if text.startswith(opener, index):
                close_at = text.find(closer, index + len(opener))
                stop = length if close_at == -1 else close_at + len(closer)
                spans.append((index, stop))
                index = stop
                block_hit = True
                break
        if block_hit:
            continue

        # Line comments.
        line_hit = False
        for opener in syntax.line:
            if text.startswith(opener, index):
                newline = text.find("\n", index)
                stop = length if newline == -1 else newline
                spans.append((index, stop))
                index = stop
                line_hit = True
                break
        if line_hit:
            continue

        index += 1

    return spans


def _inline_code_holes(text, spans):
    """Inline code spans occurring inside `spans`, for subtraction.

    Comments and docstrings routinely carry markdown, and a backticked token in
    one is usually an identifier or an external field name -- exactly the thing
    that must not be rewritten. Scanned per span, so a run cannot pair across
    the boundary out of a comment and into code.

    ORDERING INVARIANT: `spans` must be the RAW comment/docstring spans, before
    URL and email holes are subtracted. A backticked URL is ordinary in a
    docstring:

        The viewer at `https://example.com/{site}` is both page and API,
        and its JavaScript reads `var session` out of the HTML

    Cutting the URL hole first would split that region in two, leaving an odd
    backtick count on each side, and the runs would pair off by one exactly as
    they did across a wrapped Markdown span. Compute these holes from the whole
    region and let subtract_spans() take the union.
    """
    holes = []
    for start, end in spans:
        holes.extend(_inline_code_spans(text[start:end], start))
    return holes


def python_translatable_spans(text):
    """Python comments plus docstrings, via tokenize when it works.

    Falls back to the generic scanner if the file does not parse, so a syntax
    error degrades to comments-only rather than aborting.
    """
    import io
    import tokenize

    offsets = []
    cursor = 0
    for line in text.split("\n"):
        offsets.append(cursor)
        cursor += len(line) + 1

    def to_offset(row, col):
        return offsets[row - 1] + col

    spans = []
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError, ValueError):
        fallback = comment_spans(text, HASH)
        return subtract_spans(
            fallback,
            universal_holes(text) + _inline_code_holes(text, fallback),
        )

    prev_meaningful = None
    for token in tokens:
        if token.type == tokenize.COMMENT:
            spans.append((to_offset(*token.start), to_offset(*token.end)))
        elif token.type == tokenize.STRING:
            # Docstring proxy: a triple-quoted string in statement position.
            is_triple = token.string.lstrip("rRbBuUfF")[:3] in ('"""', "'''")
            at_statement_start = prev_meaningful in (
                None, tokenize.NEWLINE, tokenize.NL, tokenize.INDENT, tokenize.DEDENT,
            )
            if is_triple and at_statement_start:
                spans.append((to_offset(*token.start), to_offset(*token.end)))
        if token.type not in (tokenize.COMMENT,):
            prev_meaningful = token.type

    # Both hole sets are computed from the raw spans; see the ordering
    # invariant in _inline_code_holes before reordering this.
    return subtract_spans(
        spans, universal_holes(text) + _inline_code_holes(text, spans)
    )


def code_translatable_spans(text, syntax):
    spans = comment_spans(text, syntax)
    # Both hole sets are computed from the raw spans; see the ordering
    # invariant in _inline_code_holes before reordering this.
    return subtract_spans(
        spans, universal_holes(text) + _inline_code_holes(text, spans)
    )


# ---------------------------------------------------------------------------
# File dispatch
# ---------------------------------------------------------------------------

PROSE_EXTS = {".md", ".markdown", ".mdown", ".mkd", ".mdx", ".rst", ".adoc", ".asciidoc"}
PLAIN_EXTS = {".txt", ".text"}


def spans_for(path, text):
    suffix = path.suffix.lower()
    if suffix in PROSE_EXTS:
        return markdown_translatable_spans(text)
    if suffix in PLAIN_EXTS:
        return text_translatable_spans(text)
    if suffix in (".py", ".pyi"):
        return python_translatable_spans(text)
    syntax = SYNTAX_BY_EXT.get(suffix)
    if syntax is not None:
        return code_translatable_spans(text, syntax)
    return None


def is_supported(path):
    suffix = path.suffix.lower()
    return (
        suffix in PROSE_EXTS
        or suffix in PLAIN_EXTS
        or suffix in SYNTAX_BY_EXT
    )


# ---------------------------------------------------------------------------
# Translation
# ---------------------------------------------------------------------------

WORD_RE = re.compile(r"[A-Za-z]+")

# The word pattern matches maximal letter runs, so a prefixed derivative is its
# own token and never matches the bare stem: a listed word carrying a mis- or
# un- prefix would sail through untouched. Resolving one leading prefix against
# the list closes that gap. This stays deterministic -- it is a prefix plus a
# listed stem, not a guess about the word.
#
# Longest first, so `under` is tried before `un`.
PREFIXES = tuple(sorted(
    ("un", "re", "mis", "non", "over", "under", "pre", "dis", "de", "inter",
     "semi", "sub", "co", "anti", "multi"),
    key=len, reverse=True,
))

# A stem shorter than this invites a coincidental split. Every listed stem of
# four or more characters was checked against /usr/share/dict/words across all
# prefixes above: of 27450 combinations, 79 are real words and none is a false
# decomposition.
MIN_STEM_LENGTH = 4


def resolve(word_lower, vocabulary, review_words=frozenset(), ignored=frozenset()):
    """Map a lowercased word to its replacement, or (None, False).

    Returns (replacement, needs_review). Tries the word itself, then the word
    with one recognized prefix removed.
    """
    if word_lower in ignored:
        return None, False
    replacement = vocabulary.get(word_lower)
    if replacement is not None:
        return replacement, word_lower in review_words
    for prefix in PREFIXES:
        if not word_lower.startswith(prefix):
            continue
        stem = word_lower[len(prefix):]
        if len(stem) < MIN_STEM_LENGTH:
            continue
        replacement = vocabulary.get(stem)
        if replacement is not None:
            return prefix + replacement, stem in review_words
    return None, False


class Change:
    __slots__ = ("offset", "line", "column", "old", "new", "review")

    def __init__(self, offset, line, column, old, new, review=False):
        self.offset = offset
        self.line = line
        self.column = column
        self.old = old
        self.new = new
        self.review = review

    def as_dict(self):
        return {
            "line": self.line,
            "column": self.column,
            "from": self.old,
            "to": self.new,
            "review": self.review,
        }


def _line_index(text):
    starts = [0]
    for match in re.finditer("\n", text):
        starts.append(match.end())
    return starts


def _locate(line_starts, offset):
    low, high = 0, len(line_starts) - 1
    while low < high:
        mid = (low + high + 1) // 2
        if line_starts[mid] <= offset:
            low = mid
        else:
            high = mid - 1
    return low + 1, offset - line_starts[low] + 1


def find_changes(text, spans, vocabulary, review_words=frozenset(),
                 ignored=frozenset()):
    """Locate every replaceable word inside `spans`."""
    line_starts = _line_index(text)
    changes = []
    for start, end in spans:
        for match in WORD_RE.finditer(text, start, end):
            if match.start() < start or match.end() > end:
                continue
            word = match.group(0)
            replacement, needs_review = resolve(
                word.lower(), vocabulary, review_words, ignored
            )
            if replacement is None:
                continue
            # Refuse to touch a word welded into an identifier: colour_name,
            # sha256colour, colour2. The letter run itself is maximal, so this
            # only fires on adjacent underscores or digits.
            before = text[match.start() - 1] if match.start() > 0 else ""
            after = text[match.end()] if match.end() < len(text) else ""
            if before == "_" or after == "_" or before.isdigit() or after.isdigit():
                continue
            line, column = _locate(line_starts, match.start())
            changes.append(Change(
                match.start(), line, column, word,
                match_case(word, replacement),
                review=needs_review,
            ))
    return changes


def apply_changes(text, changes):
    out = []
    cursor = 0
    for change in sorted(changes, key=lambda c: c.offset):
        out.append(text[cursor:change.offset])
        out.append(change.new)
        cursor = change.offset + len(change.old)
    out.append(text[cursor:])
    return "".join(out)


# ---------------------------------------------------------------------------
# File collection
# ---------------------------------------------------------------------------

SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv",
    ".env", "dist", "build", "target", "vendor", ".tox", ".mypy_cache",
    ".pytest_cache", ".ruff_cache", ".next", ".nuxt", "site-packages",
    ".terraform", "coverage", ".gradle", ".idea", ".claude",
}


def _git_ignored(paths):
    """Ask git which of `paths` are ignored. Empty set if git is unavailable."""
    if not paths:
        return set()
    try:
        result = subprocess.run(
            ["git", "check-ignore", "--stdin"],
            input="\n".join(str(p) for p in paths),
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return set()
    if result.returncode not in (0, 1):
        return set()
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def collect(roots, use_gitignore=True, follow_hidden=False):
    found = []
    for root in roots:
        path = Path(root)
        if path.is_file():
            found.append(path)
            continue
        if not path.is_dir():
            raise FileNotFoundError(f"no such file or directory: {root}")
        for dirpath, dirnames, filenames in os.walk(path):
            dirnames[:] = [
                d for d in sorted(dirnames)
                if d not in SKIP_DIRS and (follow_hidden or not d.startswith("."))
            ]
            for name in sorted(filenames):
                if not follow_hidden and name.startswith("."):
                    continue
                candidate = Path(dirpath) / name
                if is_supported(candidate):
                    found.append(candidate)
    if use_gitignore and found:
        ignored = _git_ignored(found)
        if ignored:
            found = [p for p in found if str(p) not in ignored]
    return found


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def render_text_report(results, write_mode, errors):
    lines = []
    total = 0
    pending = 0
    for path, changes in results:
        if not changes:
            continue
        lines.append(f"{path}")
        for change in changes:
            if change.review:
                pending += 1
                lines.append(
                    f"  {change.line}:{change.column}  {change.old} -> {change.new}"
                    f"   [review - ambiguous, not applied]"
                )
            else:
                total += 1
                lines.append(
                    f"  {change.line}:{change.column}  {change.old} -> {change.new}"
                )
        lines.append("")
    if errors:
        lines.append("Errors:")
        for path, message in errors:
            lines.append(f"  {path}: {message}")
        lines.append("")

    files = sum(1 for _, c in results if any(not x.review for x in c))
    if total:
        verb = "Fixed" if write_mode else "Found"
        noun = "replacement" if total == 1 else "replacements"
        where = "file" if files == 1 else "files"
        lines.append(f"{verb} {total} {noun} in {files} {where}.")
        if not write_mode:
            lines.append("Re-run with --write to apply.")
    elif not pending:
        lines.append("No British spellings found.")

    if pending:
        noun = "hit needs" if pending == 1 else "hits need"
        lines.append(
            f"{pending} ambiguous {noun} review and were not applied. "
            f"Read the sentence: the British and American forms are both valid "
            f"words here."
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser():
    parser = argparse.ArgumentParser(
        prog="speak_american.py",
        description="Translate British English spellings to American English.",
    )
    parser.add_argument("paths", nargs="+", help="files or directories to scan")
    parser.add_argument(
        "--write", action="store_true",
        help="apply the changes (default is a dry run that only reports them)",
    )
    parser.add_argument(
        "--target", choices=("us", "uk"), default="us",
        help="dialect to convert to (default: us)",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON instead of text")
    parser.add_argument(
        "--exclude", action="append", default=[], metavar="WORD",
        help="never translate this word (repeatable)",
    )
    parser.add_argument(
        "--no-gitignore", action="store_true",
        help="do not skip files ignored by git",
    )
    parser.add_argument(
        "--hidden", action="store_true",
        help="include dotfiles and dot-directories",
    )
    parser.add_argument("--encoding", default="utf-8", help="file encoding (default: utf-8)")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)

    try:
        vocabulary = load_vocabulary(args.target, extra_ignores=args.exclude)
        review = load_review_vocabulary(args.target, extra_ignores=args.exclude)
    except OSError as exc:
        print(f"error: cannot load word list: {exc}", file=sys.stderr)
        return EXIT_ERROR
    if not vocabulary:
        print("error: word list is empty", file=sys.stderr)
        return EXIT_ERROR

    # Review pairs are matched too, but flagged rather than applied.
    review_words = frozenset(review)
    lookup = dict(vocabulary)
    lookup.update(review)
    ignored = frozenset(load_ignores(extra_ignores=args.exclude))

    try:
        paths = collect(args.paths, not args.no_gitignore, args.hidden)
    except (OSError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    results = []
    errors = []
    for path in paths:
        try:
            text = _read(path, args.encoding)
        except (OSError, UnicodeDecodeError) as exc:
            errors.append((path, str(exc)))
            continue
        try:
            spans = spans_for(path, text)
            if spans is None:
                continue
            changes = find_changes(text, spans, lookup, review_words, ignored)
        except Exception as exc:  # one bad file must not sink the run
            errors.append((path, f"{type(exc).__name__}: {exc}"))
            continue

        applicable = [c for c in changes if not c.review]
        if applicable and args.write:
            try:
                updated = apply_changes(text, applicable)
                _atomic_write(path, updated, args.encoding)
            except OSError as exc:
                errors.append((path, str(exc)))
                continue
        results.append((path, changes))

    if args.json:
        payload = {
            "target": args.target,
            "applied": args.write,
            "files": [
                {"path": str(p), "changes": [c.as_dict() for c in ch]}
                for p, ch in results if ch
            ],
            "total_changes": sum(len(ch) for _, ch in results),
            "files_scanned": len(results),
            "errors": [{"path": str(p), "error": m} for p, m in errors],
        }
        print(json.dumps(payload, indent=2))
    else:
        print(render_text_report(results, args.write, errors))

    if errors:
        return EXIT_ERROR
    pending = any(c.review for _, ch in results for c in ch)
    if args.write:
        # Ambiguous hits were deliberately not applied; say so with exit 1.
        return EXIT_FOUND if pending else EXIT_CLEAN
    if any(ch for _, ch in results):
        return EXIT_FOUND
    return EXIT_CLEAN


def _read(path, encoding):
    """Read preserving original line endings (newline="" disables translation)."""
    with open(path, "r", encoding=encoding, newline="") as stream:
        return stream.read()


def _atomic_write(path, text, encoding):
    directory = path.parent
    handle, temp_name = tempfile.mkstemp(dir=str(directory), prefix=".speak-american-")
    try:
        with os.fdopen(handle, "w", encoding=encoding, newline="") as stream:
            stream.write(text)
        os.replace(temp_name, path)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


if __name__ == "__main__":
    sys.exit(main())
