# speak-american

Lately I've noticed Claude's prose composition lapsing into UK/Commonwealth spelling conventions. I got tired of reminding it that this is the land of the free and to drop all the extraneous u's, that it's "center" not "cent-reeeee," and to use z's because that's literally the sound at the end of "analyze." It's costing me too much in tokens, Busch Lights, and Marlboro Reds.

---

This Claude Code plugin converts British/Commonwealth English spellings to
American English in Markdown, prose, and code comments — deterministically, from
a static word-pair list.

It exists because Claude Code sessions randomly decide that they want to seem more
smart and sophisticated sometimes: a doc comes back with `centre` for `center`, `colour` for `color`,
`capitalisation` for `capitalization`. Catching that by re-reading the document
costs tokens and misses things. This catches it with a list lookup.

## Install

```
/plugin marketplace add mikeisgreen/speak-american
/plugin install speak-american
```

Or point the marketplace at a local clone:

```
/plugin marketplace add /path/to/speak-american
```

## Requirements

`python3` on PATH. That is the whole list.

The script is standard-library only. It does not create a virtualenv, does not
install anything, does not touch the host project's dependencies, and does not
reach the network. It works fine in a repository that has nothing to do with
Python.

## Usage

As a slash command:

```
/speak-american                    # check files changed in the working tree
/speak-american docs/              # check a directory
/speak-american README.md --write  # apply
```

The skill also triggers on its own when you ask Claude to fix British spellings,
and after Claude writes or edits prose.

Directly:

```bash
python3 skills/speak-american/scripts/speak_american.py docs/
python3 skills/speak-american/scripts/speak_american.py docs/ --write
python3 skills/speak-american/scripts/speak_american.py docs/ --json
```

Exit codes: `0` clean, `1` British spellings found (dry run), `2` error.

## What makes it safe to run

It is structure-aware. In Markdown it translates prose and skips fenced code,
indented code, inline code spans, link and image destinations, reference labels,
footnote markers, autolinks, raw HTML tags, and front matter keys. In source
files it translates comments and Python docstrings only — never identifiers,
never arbitrary string literals — using a string-aware scanner, so a `#` or `//`
inside a string is not mistaken for a comment.

Everywhere, it preserves capitalization (`COLOUR` → `COLOR`, not `color`),
leaves URLs and email addresses alone, and refuses to touch words welded into
identifiers (`colour_name`, `myColour`, `colour2`).

Comment syntax is recognized for `#`, `//`, `/* */`, `--`, `--[[ ]]`, and
`<!-- -->` across roughly fifty file extensions.

Writes are atomic and per-file. A file that fails to parse is reported and
skipped; it does not abort the run or leave a half-written tree.

## Customizing the word list

- `skills/speak-american/data/words-extra.tsv` — extra `british<TAB>american`
  pairs. Overrides the base list on collisions.
- `skills/speak-american/data/words-ignore.list` — words to never translate, one
  per line. Use it for proper nouns (`Labour Party`, `Ministry of Defence`) and
  third-party API fields that legitimately use British spelling.

Both are plain text with `#` comments and no rebuild step. Leave
`data/words.tsv` alone so it can be re-imported from upstream.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

No test dependencies.

Running the tool on this repository reports five hits in the skill's own
`description` field. Those are deliberate — the description lists British
spellings so the skill matches when you mention one. Leave them.

## Attribution

The base word list in `skills/speak-american/data/words.tsv` is derived from
[`eng`](https://github.com/orsinium-labs/eng) by Gram (orsinium), used under the
MIT License. The full license text is in
`skills/speak-american/data/LICENSE-eng.txt`, and import details and
modifications are recorded in `skills/speak-american/data/PROVENANCE.md`.

Only the data file was taken. The translation engine here is original work —
`eng` rewrites Markdown code blocks and URLs, lowercases all-caps words, and
aborts mid-run on an unparseable Python file, which is why this plugin does not
depend on it.

## License

MIT. See `LICENSE`.
