---
description: Check or fix British English spellings in Markdown, prose, and code comments
argument-hint: "[paths] [--write]"
allowed-tools: Bash, Read, Edit
---

Run the speak-american checker over `$ARGUMENTS`.

If `$ARGUMENTS` is empty, scan the files changed in the working tree
(`git diff --name-only HEAD` plus untracked files); if that is also empty, scan
the current directory.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/speak-american/scripts/speak_american.py" $ARGUMENTS
```

Exit code `1` means British spellings were found — that is the expected signal
on a dry run, not a failure. Exit code `2` is a real error.

Report the hits grouped by file. Then:

- If the user passed `--write`, the changes are already applied. Summarize them.
- Otherwise, show what would change and ask whether to apply it.

Flag any hit that looks like a proper noun or an external identifier rather than
a spelling slip (`Labour Party`, an API field named `behaviour`, a quoted
title). Recommend `--exclude` or an entry in `data/words-ignore.list` for those
instead of applying the change.
