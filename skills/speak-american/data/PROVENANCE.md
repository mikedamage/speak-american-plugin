# Word list provenance

`words.tsv` is derived from the [`eng`](https://github.com/orsinium-labs/eng) project
by Gram (orsinium), used under the MIT License. The full license text is in
`LICENSE-eng.txt` in this directory.

- Source file: `eng/words.txt`
- Upstream commit: `9246ed362343a3685d7d9ff7cc9edb8bba28b9de` (2025-05-30)
- Retrieved: 2026-08-28

## Modifications

The list was normalized on import. No pairs were edited in substance:

- Stripped stray leading/trailing whitespace on fields (`metre` mapped to `" meter"`
  upstream; now `"meter"`).
- Dropped duplicate left-hand keys and any rows where both sides were identical.
- Sorted by the British spelling.

1872 pairs after normalization (1878 rows upstream).

Only the data file was taken. None of `eng`'s Python source is vendored here — the
translation engine in `scripts/speak_american.py` is original work.

## Local additions

Additions and exclusions live in `words-extra.tsv` and `words-ignore.list` so that
`words.tsv` can be re-imported from upstream without losing local edits.
