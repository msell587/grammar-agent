# Grammar review report

- **Source:** `sample.txt`
- **Model:** `mock:mock`, explanation level: intermediate
- **Generated:** 2026-11-07T20:03:41+00:00

## Summary

| | |
|---|---|
| Sentences checked | 5 |
| Changes proposed | 7 (in 3 sentences) |
| Sentences flagged for manual review | 1 |

Flagged sentences (2) are left exactly as written. Check them yourself.

Nothing has been changed yet. To accept or reject each numbered change, run:

```bash
grammar-agent apply examples/sample_run
```

## Sentences

### Sentence 1: 3 changes

**Original:**

> Their going to the libary tomorow.

**Corrected:**

> They're going to the library tomorrow.

**Changes:** ~~Their~~**They're**<sup>[1.1]</sup> going to the ~~libary~~**library**<sup>[1.2]</sup> ~~tomorow~~**tomorrow**<sup>[1.3]</sup>.

- **[1.1]** *grammar*: `Their` → `They're`. 'Their' means 'belonging to them'. Here you need 'they're', which is short for 'they are'.
- **[1.2]** *spelling*: `libary` → `library`. 'Library' has an 'r' after the 'b'. Many people forget it because it is often not pronounced clearly.
- **[1.3]** *spelling*: `tomorow` → `tomorrow`. 'Tomorrow' is spelled with one 'm' and two 'r's.

### Sentence 2: needs manual review

**Original (kept unchanged):**

> Me and him has finished the report, but we forgot to sent it.

**Model suggestion (rejected, not offered for approval):**

> He and I have completed the report, but we neglected to send it.

**Why it was flagged:**

- the listed changes do not produce the model's corrected sentence (the model made edits it did not explain)

### Sentence 3: no changes

> The meeting is on Tuesday.

### Sentence 4: 2 changes

**Original:**

> Its a good idea, isnt it?

**Corrected:**

> It's a good idea, isn't it?

**Changes:** ~~Its~~**It's**<sup>[4.1]</sup> a good idea, ~~isnt~~**isn't**<sup>[4.2]</sup> it?

- **[4.1]** *punctuation*: `Its` → `It's`. 'It's' with an apostrophe is short for 'it is'. 'Its' without one means 'belonging to it'.
- **[4.2]** *punctuation*: `isnt` → `isn't`. 'Isn't' is short for 'is not', so it needs an apostrophe where the letter 'o' was removed.

### Sentence 5: 2 changes

**Original:**

> The results was better then we expected.

**Corrected:**

> The results were better than we expected.

**Changes:** The ~~results was~~**results were**<sup>[5.1]</sup> better ~~then~~**than**<sup>[5.2]</sup> we expected.

- **[5.1]** *grammar*: `results was` → `results were`. 'Results' is plural, so the verb must be 'were', not 'was'.
- **[5.2]** *spelling*: `then` → `than`. Use 'than' to compare things. 'Then' is about time, as in 'first this, then that'.
