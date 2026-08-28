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

## Curation

The upstream list contains rows that would corrupt correct American prose. These
were audited and fixed on 2026-08-28; 1804 pairs remain in `words.tsv`.

**Columns swapped** (column 1 held the American spelling, so the tool proposed
replacing a correct word with a British one):

- `usable -> useable` became `useable -> usable`
- `vectorization -> vectorisation` became `vectorisation -> vectorization`

**Wrong replacement corrected** (misspelling or wrong inflection in column 2):

| Was | Now |
|-----|-----|
| `jewellery -> jewelery` | `jewellery -> jewelry` |
| `pummelled -> pummel` | `pummelled -> pummeled` |
| `pummelling -> pummeled` | `pummelling -> pummeling` |
| `snowploughs -> snowplow` | `snowploughs -> snowplows` |
| `anaesthetist -> anesthesiologist` | `anaesthetist -> anesthetist` |

**Dropped, 20 rows** — column 1 is already correct American English, or column 2
is not a word. Keeping them means rewriting correct prose into incorrect prose:
`buses`, `busing`, `minibuses`, `gases` (American English uses these forms;
`busses` means kisses), `lit`, `vice` (as in *vice versa*), `dealt`, `knelt`,
`lept`, `globally` (mapped to the misspelling `globaly`), `simultaneous`
(mapped to `simultanous`), `cancellation`, `curricula`, `antennae`, `bingeing`,
`unfeasible`, `sanatorium`, `philtre` (a love potion, not a `filter`), `discy`,
and `tranquilly` (an adverb mapped to the noun `tranquility`).

**Dropped, 20 rows** — the source contains punctuation, a space, a slash, or an
accent, so it can never match the word pattern `[A-Za-z]+`. These were dead
entries: `catalogue.`, `disc,`, `disc-`, `disc.`, `disc;`, `flyer/flier`,
`co-operate`, `co-ordinate`, `anti-aliased`, `anti-aliasing`,
`case-insensitive`, `case-sensitive`, `colour-key`, `colour-space`, `any more`,
`car park`, `number plate`, `sailing boat`, `tea towel`, `anti-clockwise`.

**Moved to `words-vocabulary.tsv`, 28 rows** — vocabulary and register
differences rather than spelling (`petrol -> gasoline`, `film -> movie`,
`pavement -> sidewalk`). That file is not loaded. Several are context-dependent:
`disc` is correct American English in *compact disc* and *disc brake*, and
`quarter -> fourth` would mangle any financial document. One row,
`orch -> flashlight`, was a corrupted `torch`.

`tests/test_speak_american.py` enforces this: `TestWordListIntegrity` fails the
suite on a reversed row, a non-alphabetic source or target, a duplicate, a
no-op pair, or the reappearance of any of the dropped words.

Only the data file was taken. None of `eng`'s Python source is vendored here — the
translation engine in `scripts/speak_american.py` is original work.

## Local additions

Additions and exclusions live in `words-extra.tsv` and `words-ignore.list` so that
`words.tsv` can be re-imported from upstream without losing local edits.
