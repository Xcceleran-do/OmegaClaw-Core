# Reference — Memory Skills

Defined in `src/memory.metta` and catalogued in `src/skills.metta`.

All five skills accept quoted string arguments. Variables are not permitted in LLM-generated calls.

---

## `remember`

### Signature
```metta
(remember "string")
```

### Purpose
Store a string in long-term embedding memory as the triplet `(timestamp, atom, embedding)`.

### Parameters
- `string` — the text to remember. Use short, self-contained phrases for best recall.

### Returns
The result of the ChromaDB write (internally). The agent treats a successful call as an effectful step.

### Examples
```metta
(remember "user prefers dark mode")
(remember "to deploy: run make release then docker push")
```

### Notes / Limits
- Text is passed through `string-safe` before embedding, which escapes newlines, quotes, and apostrophes.
- Embedding provider is selected by `embeddingprovider` (`Local` or `OpenAI`).
- Nothing deduplicates automatically — repeated `remember` calls store multiple items.

---

## `query`

### Signature
```metta
(query "string")
```

### Purpose
Return up to `maxRecallItems` memory entries whose embeddings are closest to the embedding of `string`.

### Parameters
- `string` — a short descriptive phrase. Over-long queries dilute similarity scores.

### Returns
A list-shaped result containing the nearest memory items.

### Examples
```metta
(query "deployment steps")
(query "user preferences")
```

### Notes / Limits
- `maxRecallItems` default is 20 (see `initMemory`).
- Similarity is purely embedding-based; exact string match is not guaranteed.

---

## `episodes`

### Signature
```metta
(episodes "YYYY-MM-DD HH:MM:SS")
```

### Purpose
Return `maxEpisodeRecallLines` lines of the episodic trace centered on the given timestamp.

### Parameters
- `timestamp` — must match the format produced by `get_time_as_string`.

### Returns
A block of lines from `memory/history.metta`.

### Examples
```metta
(episodes "2026-04-15 14:30:00")
```

### Notes / Limits
- Implemented by `helper.around_time`.
- Useful for answering questions like "what was I doing around X?"

---

## `pin`

### Signature
```metta
(pin "string")
```

### Purpose
Append a working-memory note to the episodic trace so the next turn can see it in `HISTORY`.

### Parameters
- `string` — the note. Typical uses: intermediate results, plans for the next turn, checklists.

### Returns
Success / failure of the append.

### Examples
```metta
(pin "candidates: A) Launch Day B) We're Live C) Out Now")
(pin "next step: pick best candidate and send")
```

### Notes / Limits
- `pin` is not semantically indexed — it influences later turns while its complete history record fits the context compiler's token budget.
- For anything you want to recall days later, use `remember` instead.

---

## `recall`

### Signature
```metta
(recall "source-1-chunk-2,source-3-chunk-1")
```

### Purpose
Prefer one or more exact task-evidence records for the next context compilation.
Recall assigns one-use priorities in the requested order without copying or
reordering the retained records.

### Parameters
- `ids` — one exact record ID or a comma/space-separated batch. A source ID expands to all of that source's chunks.

### Returns
A compact status that distinguishes records queued for the next compilation,
records deferred to another batch, records too large for the entire input
budget, and unavailable IDs. A partial batch includes the next exact recall
command, its minimum additional interaction count, and the current interaction
horizon. It never returns or duplicates the complete evidence as its own tool
result.

### Notes / Limits
- Recall is exact and task-local; it is not embedding search.
- `RECALL-QUEUED` means prioritized for the next compilation, not guaranteed
  visible. The compiler may still omit a queued record after required context is
  reserved; the next source card or omission receipt reports what actually fit.
- `RECALL-TOO-LARGE` is definitive: the record cannot fit even if it were the
  only evidence record in the configured input budget.
- Source cards show which chunks are visible and hidden and provide the exact batched recall command.
- Evidence is lost on task reset or process/container restart.
