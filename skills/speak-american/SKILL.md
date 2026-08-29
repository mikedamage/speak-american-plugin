---
name: speak-american
description: Convert British/Commonwealth English spellings to American English in Markdown, prose, and code comments — deterministically, from a static word list. Use when the user asks to Americanize spelling, fix British spellings, check for Commonwealth/UK spellings, or mentions specific slips like "colour" vs "color", "centre" vs "center", "capitalisation" vs "capitalization", "grey" vs "gray", "behaviour" vs "behavior". Also use as a self-check after writing or editing any Markdown document, README, changelog, docstring, or code comment.
---

# Speak American

Replace British English spellings with American English using a fixed word-pair
list. No judgment calls, no re-reading the document, no ad-hoc scripts.

## When to use this

- The user asks to fix British spellings, "Americanize", or check spelling conventions.
- **Proactively, after you write or edit prose**: any Markdown file, README, changelog,
  doc comment, or docstring. Run the check, then act on the result. This is cheap —
  it costs one Bash call and no reasoning.

## Usage

The script is stdlib-only. It needs `python3` on PATH and nothing else — no
virtualenv, no `pip install`, no network. Never create a venv for it, and never
add it to the project's dependencies.

Check (default — reports, changes nothing):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/speak-american/scripts/speak_american.py" <paths>
```

Apply:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/speak-american/scripts/speak_american.py" --write <paths>
```

If `${CLAUDE_PLUGIN_ROOT}` is not set, use the path to this skill directory.

`<paths>` is any mix of files and directories. Directories are walked
recursively; files ignored by git, hidden files, and vendor directories
(`node_modules`, `.venv`, `dist`, …) are skipped.

### Exit codes

| Code | Meaning |
|------|---------|
| `0`  | Clean — nothing to change, or `--write` applied everything |
| `1`  | British spellings found, or ambiguous hits are awaiting review |
| `2`  | An error occurred; see stderr |

Exit `1` on a dry run is the normal "found something" signal, not a failure.
Exit `1` *after* `--write` means some hits were flagged for review and
deliberately left alone — read them yourself.

### Options

| Flag | Effect |
|------|--------|
| `--write` | Apply changes. Default is a dry run. |
| `--json` | Machine-readable output. Use when you need to reason about specific hits. |
| `--target uk` | Reverse direction: American to British. |
| `--exclude WORD` | Never translate this word. Repeatable. |
| `--no-gitignore` | Do not skip git-ignored files. |
| `--hidden` | Include dotfiles and dot-directories. |
| `--encoding ENC` | File encoding. Default `utf-8`. |

## Recommended workflow

1. Run the check on the files you just touched — pass explicit paths, not `.`,
   so you only see your own changes.
2. Read the reported hits. They are `line:column  from -> to`.
3. If every hit is a genuine spelling slip, re-run with `--write`.
4. If a hit is a proper noun or an external identifier (`Labour Party`, a
   third-party API field named `behaviour`, a quoted book title), do **not**
   apply it. Add it to `data/words-ignore.list` or pass `--exclude`, then re-run.
5. Hits marked `[review - ambiguous, not applied]` are never applied by
   `--write`. Read the sentence and edit by hand if the change is right.

Prefer running the check on specific files over the whole repository. A
repo-wide `--write` can touch files unrelated to the current task.

## What it will and will not touch

It is structure-aware, so it does not corrupt what it walks over.

**Markdown / MDX / RST** — translates prose only. Skips fenced code blocks,
indented code blocks, inline code spans, link and image destinations, reference
labels and their definitions, footnote markers, autolinks, raw HTML tags, and
front matter keys. Front matter *values* are translated; keys are not.

**Source files** — translates comments only, never identifiers or arbitrary
string literals. Python docstrings are included. The scanner is string-aware, so
a `#` or `//` inside a string literal is not mistaken for a comment.

Comment syntax is recognized for `#` (Python, Ruby, shell, YAML, TOML, …),
`//` and `/* */` (C, C++, JS, TS, Java, Go, Rust, C#, PHP, …), `--` and
`/* */` (SQL), `--` and `--[[ ]]` (Lua), `<!-- -->` (HTML, XML, Vue, Svelte),
and `/* */` (CSS, SCSS).

**Plain text** — translates everything except URLs and email addresses.

**Anything else** — skipped entirely. Unknown extensions are never modified.

Across every file type it also leaves alone:

- URLs and email addresses, anywhere they appear, including inside comments.
- Words welded into identifiers: `colour_name`, `myColour`, `colour2`.
- Capitalization: `COLOUR` becomes `COLOR`, `Colour` becomes `Color`.

## Ambiguous words

Some words are correct American English under one reading and British under
another, so no word list can decide them. These live in `data/words-review.tsv`:
the tool reports them and never applies them.

`analyses` is the only one so far. It is the plural of `analysis` in **both**
dialects, and separately the British third-person verb. Only the verb is wrong:

- "the symbols these analyses use" — plural noun, **correct**, leave it.
- "two analyses run at once" — plural noun, **correct**, leave it.
- "the script analyses the parcel" — third-person verb, **wrong**, should be
  `analyzes`.

The tell is grammatical: a determiner (`these`, `two`, `the`) followed by an
uninflected verb forces the noun reading. The sibling forms `analyse`,
`analysed` and `analysing` are unambiguously British and are applied normally.

When you see a review hit, read the sentence and decide. Do not apply it blindly.

## Known limits

- An indented code block *inside a list item* is treated as prose, because
  4-space indentation is ambiguous there. Fence such blocks with backticks to
  protect them.
- The word list is static. It will not catch a British spelling that is not in
  it. Add missing pairs to `data/words-extra.tsv`.
- Dialect words that are not spelling differences (`whilst`, `amongst`, `lorry`)
  are deliberately absent. This tool fixes spelling, not register.

## Extending the word list

- `data/words-extra.tsv` — additional `british<TAB>american` pairs. Overrides
  `words.tsv` on key collisions.
- `data/words-ignore.list` — words to never translate, one per line.
- `data/words-review.tsv` — ambiguous pairs: reported, never auto-applied.
- `data/words-vocabulary.tsv` — register swaps. Not loaded.

Both are plain TSV/text with `#` comments. Edit them directly; no rebuild step.
Keep `data/words.tsv` untouched so it can be re-imported from upstream.
