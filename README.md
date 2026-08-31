# speak-american

Lately I've noticed Claude's prose composition lapsing into UK/Commonwealth spelling conventions. I got tired of reminding it that this is the land of the free and to drop all the extraneous u's, that it's "center" not "cent-reeeee," and to use z's because that's literally the sound at the end of "analyze." It's costing me too much in tokens, Busch Lights, and Marlboro Reds.

So this Claude Code plugin does the reminding for me. It converts
British/Commonwealth spellings to American English in Markdown, prose, and code
comments — deterministically, from a static word-pair list. No model in the
loop, no judgment calls, no re-reading a doc and hoping you spot every `colour`.
Just a lookup table doing its patriotic duty.

## Install

```
/plugin marketplace add mikedamage/speak-american-plugin
/plugin install speak-american
```

Or point the marketplace at a local clone:

```
/plugin marketplace add /path/to/speak-american-plugin
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

Ambiguous hits are reported but never applied, and each one carries the sentence
it sits in — reassembled across line wraps, so hard-wrapped prose still yields a
whole sentence. That is enough to decide from without opening the file:

```
  127:12  analyses -> analyzes   [review - ambiguous, not applied]
          those collide when two analyses run at once
```

`--json` puts the same text in a `context` field. `--context` extends it to
every hit, which helps when screening for proper nouns.

## What makes it safe to run

It is structure-aware. In Markdown it translates prose and skips fenced code,
indented code, inline code spans, link and image destinations, reference labels,
footnote markers, autolinks, raw HTML tags, and front matter keys. In source
files it translates comments and Python docstrings only — never identifiers,
never arbitrary string literals — using a string-aware scanner, so a `#` or `//`
inside a string is not mistaken for a comment. Backticks inside a comment or
docstring protect what they wrap, because a backticked token there is nearly
always an identifier or an external field name.

Because the matcher works on maximal letter runs, a prefixed derivative is its
own token — `mislabelled` does not match the listed stem `labelled`. So one
leading prefix (`un`, `re`, `mis`, `over`, and eleven more) is resolved against
the list. It is still deterministic: prefix plus a *listed* stem of at least
four characters, never a guess. `reusable` and `revise` do not match, because
`usable` and `vise` are not in the list.

Everywhere, it preserves capitalization (`COLOUR` → `COLOR`, not `color`),
leaves URLs and email addresses alone, and refuses to touch words welded into
identifiers (`colour_name`, `myColour`, `colour2`).

Comment syntax is recognized for `#`, `//`, `/* */`, `--`, `--[[ ]]`, and
`<!-- -->` across roughly fifty file extensions.

The bias throughout is toward under-translating rather than over-translating.
In a source tree a bad rewrite usually breaks the build; in a docs corpus
nothing catches it. A document that quotes an external string is correct only
insofar as it matches, so "fixing" the spelling of a value you do not control
makes the document wrong by definition, however much better it reads. A missed
British spelling is cosmetic; a rewritten external string is a wrong document
that looks right.

Writes are atomic and per-file. A file that fails to parse is reported and
skipped; it does not abort the run or leave a half-written tree.

## Customizing the word list

- `skills/speak-american/data/words-extra.tsv` — extra `british<TAB>american`
  pairs. Overrides the base list on collisions.
- `skills/speak-american/data/words-ignore.list` — words to never translate, one
  per line. Use it for proper nouns (`Labour Party`, `Ministry of Defence`) and
  third-party API fields that legitimately use British spelling.
- `skills/speak-american/data/words-review.tsv` — ambiguous pairs that are
  reported but **never applied** by `--write`. A word belongs here when the
  British form is also correct American English under another reading, so no
  lexical rule can decide it. `analyses` is the plural of `analysis` in both
  dialects *and* the British verb; only the verb is wrong.
- `skills/speak-american/data/words-vocabulary.tsv` — vocabulary and register
  swaps (`petrol` → `gasoline`), **not loaded by default**. This tool fixes
  spelling; changing the words an author chose is a different job. Append these
  to `words-extra.tsv` if you want them, but read them first — several are
  context-dependent.

The upstream list was audited before use: two rows had their columns swapped,
five had a misspelled or wrongly-inflected replacement, and twenty would have
rewritten already-correct American English (`buses` → `busses`, `lit` →
`lighted`, `vice` → `vise`). See `data/PROVENANCE.md` for the full record.
`tests/test_speak_american.py` fails the suite if any of them return.

Both are plain text with `#` comments and no rebuild step. Leave
`data/words.tsv` alone so it can be re-imported from upstream.

## Publishing a change

Bump `version` in `.claude-plugin/plugin.json` for every published change.
Claude Code caches an installed plugin in a version-pinned directory
(`~/.claude/plugins/cache/speak-american/speak-american/<version>/`), so
`/plugin marketplace update` followed by `/reload-plugins` will happily re-read
the old directory and serve the previous word list. A new version number forces
a new directory.

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
