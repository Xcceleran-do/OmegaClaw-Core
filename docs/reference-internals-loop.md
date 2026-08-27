# Internals — `src/loop.metta`

The heart of OmegaClaw. One function, `omegaclaw`, tail-recurses forever.

## Entry

```metta
(= (omegaclaw) (omegaclaw 1))
```

Outer `run.metta` simply calls `(omegaclaw)`.

## On turn 1 (`$k == 1`)

Initializes state:

- `(initLoop)` — configures all loop parameters (see [reference-configuration.md](./reference-configuration.md)).
- `(initMemory)` — configures memory parameters and loads the embedding model.
- `(initChannels)` — opens the active communication channel.

Also initializes runtime state:

- `&prevmsg` — last received human message.
- `evidence` — ordered skill-result records retained for the active input.
- `&loops` — countdown until the agent goes idle.

## Every turn

1. **Decrement `&loops`** (turns > 1 only).
2. **Receive** — `(receive)` via the active channel.
3. **Detect new input** — compare against `&prevmsg`. If different and non-empty, reset the evidence module and restore `&loops` to `maxNewInputLoops`.
4. **Compile model context** — after input detection, `ContextCompiler` ranks stable instructions, task evidence, and complete history records; reserves `maxOutputToken`; and emits included/omitted record IDs plus candidate, rendered, and omitted size measurements. Omitted generic tool results leave exact-recall receipts. URL-scoped chunks share one deterministic source card, which lists visible and hidden chunk IDs instead of emitting one receipt per hidden chunk. History is selected as a contiguous recent suffix. The compiler produces a typed request with trusted instructions in `system` and task/evidence/history data in `user`.
5. **Set next wake** — `&nextWakeAt := now + wakeupInterval`.
6. **Call the LLM** — emit the single-line `CHARS_SENT` trace, then dispatch the typed `ModelRequest` through the selected provider adapter and retain typed usage, finish-reason, reasoning, and tool-call metadata in `ModelResponse`. Context compilation is caught at the loop boundary so an impossible budget cannot terminate the process.
7. **Repair parentheses** — `helper.balance_parentheses` fixes common mismatches before parsing.
8. **Parse** — `sread` on the repaired string; if it does not start with `(`, the loop feeds back a reminder prompt.
9. **Dispatch skills** — `(superpose $sexpr)` runs each skill, capturing errors via `HandleError`.
10. **Record** — `addToHistory` appends human message + response + any errors to `memory/history.metta`, provided something new happened.
11. **Append evidence** — when the turn parsed actionable input, retain its results in execution order until task reset. Recognized bulk web results are separated by URL and split at paragraph, heading, or sentence boundaries into approximately 800–1,200-token chunks. Complete cleaned source text remains in task memory; no authoritative record is character-truncated.
12. **Sleep** — `(sleep (sleepInterval))`.
13. **Recurse** — `(omegaclaw (+ 1 $k))`.

## Idle behavior

When `&loops` hits zero and no new message has arrived, the loop skips the LLM call. When `now > &nextWakeAt`, it clears both task evidence and the completed input before granting `maxWakeLoops + 1` extra turns for self-initiated work (cleanup, summarization, etc.).

## Error handling

Two kinds of error are reported back into `&error`:

- **Parse failure** (`MULTI_COMMAND_FAILURE_...`) — the LLM did not produce a valid s-expression.
- **Per-skill failure** (`SINGLE_COMMAND_FORMAT_ERROR_...`) — one skill call failed.

Errors are appended to the episodic trace so the agent sees them and can self-correct.

## Baseline telemetry

Each provider interaction emits a single-line `TASK_TELEMETRY` JSON object.
`task_generation` changes whenever evidence is reset, while `interaction`
counts model calls within that generation. The payload contains:

- current and appended evidence characters and records, including source/chunk counts;
- recall calls, requested IDs, exact hits, and misses;
- candidate, included, omitted, and rendered context sizes in characters and
  estimated tokens;
- the resolved context window, output reserve, input budget, and utilization.

`CONTEXT_BUDGET_PRESSURE` is logged when estimated input reaches 90% of the
available input budget. `CHANNEL_SEND` records whether the selected channel
adapter accepted or raised while dispatching a message; it does not claim
downstream delivery by asynchronous channel infrastructure.

## See also

- [introduction.md#architecture](./introduction.md#architecture) — the architecture diagram.
- [reference-internals-skill-dispatch.md](./reference-internals-skill-dispatch.md) — how individual skills resolve.
