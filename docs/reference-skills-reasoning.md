# Reference — Reasoning Skill

Defined in `src/skills.metta`. Backed by two reasoning engines in `lib_nal.metta` and `lib_pln.metta`.

---

## `extract-metadata`

### Signature
```metta
(extract-metadata text)
```

### Purpose
Extract article-level inference metadata from a whole text using DSPy with Gemini. This is not page/layout metadata; it summarizes the article's topic, sentiment, tone, style, domain, scope, temporal framing, main claim, claim type, and evidence quality.

### Returns
A JSON string with an `article` object. `evidence_quality` includes a label, score, evidence types, and a `suggested_truth_confidence` value that can be used as a starting confidence prior before atomizing claims into NAL or PLN.

Requires `GEMINI_API_KEY` or `GOOGLE_API_KEY`. Override the default Gemini model with `GEMINI_MODEL`.

Inputs shorter than article/corpus length are skipped without a Gemini call. The current guard requires at least 320 characters and 3 sentence-like spans.

---

## `atomize`

### Signature
```metta
(atomize text)
```

### Purpose
Parse natural-language facts, rules, and questions into a staged semantic workspace plus a structured JSON IR with rendered NAL and PLN forms using DSPy with Gemini. Use this before `metta` when a question needs explicit premises rather than raw text.

### Returns
A JSON string using `omegaclaw.semantic_parser.v3`. It includes a compact `workspace` and `items`.

The `workspace` is the parser's internal seven-stage hypothesis trail, inspired by the parsing architecture discussed in the PLN channel:

```text
normalization -> pos_tagging -> pos_coherence -> logical_form -> reference_resolution -> time_modality -> semantic_binding
```

The workspace is compact by default for cost control. The LLM is not asked to narrate every stage on every call; the runtime attaches the stage skeleton cheaply and only keeps reported stage diagnostics when an ambiguity, repair, or unresolved issue materially affects the final binding. These stage hypotheses are not claims to execute. Final `items` are exported only from the `semantic_binding` stage after it maps the selected logical form to OmegaClaw's NAL/PLN dialect.

Each item is a `fact`, `rule`, or `query`, and includes `nal` and `pln` renderings when the parser can recognize the pattern.

`items[].nal` and `items[].pln` are renderings for inspection and composition. They are not skill calls. The OmegaClaw agent composes `metta` calls from these returned atoms after it has seen the atomize result.

Fact and rule atoms are rendered in the engine-ready truth-value shape:

```metta
((Inheritance pingu (IntSet feathered)) (stv 1.0 0.78))
```

The inverse wrapper shape is invalid and should not be emitted:

```metta
(stv 1.0 0.78 (Inheritance pingu (IntSet feathered)))
```

Requires `GEMINI_API_KEY` or `GOOGLE_API_KEY`. Override the default Gemini model with `GEMINI_MODEL`.

For short non-propositional text, such as greetings or acknowledgements, the parser should return an empty `items` list.

For logical reasoning, pass the premises and target question together to `atomize`. Do not send the target question to the memory `query` skill; `query` only performs long-term embedding-memory recall.

Because command results are only visible on the next loop, a reasoning cycle should not call `atomize`, then invent intermediate atoms, a `metta` expression, or a final answer in the same response. The agent should call `atomize` on the exact text it wants converted, inspect the returned `items`, then compose the next `metta` call itself.

For PLN, use only link forms consumed by `lib_pln.metta`: `Inheritance`, `Implication`, `Similarity`, `IntentionalSimilarity`, `ExtensionalSimilarity`, `Equivalence`, `Not`, `Member`, and `Evaluation`. Terms such as `(IntSet property)` and `(Product subject object)` may appear as ordinary arguments inside those links, but `lib_pln.metta` has no special rule for `IntSet` or `Product`. Reserve `Evaluation`/`Predicate`/`List (Concept ...)` for predicate-evaluation rules.

To execute a PLN inference, compose a two-premise call from returned `items[].pln` values:

```metta
(metta "(|~ ((Implication (Inheritance $1 (IntSet feathered)) (Inheritance $1 bird)) (stv 1.0 0.74)) ((Inheritance pingu (IntSet feathered)) (stv 1.0 0.78)))")
```

Do not pass a single `item.pln` rule to `metta`. A unary `(|~ rule)` evaluates to a partial function, not a PLN conclusion.
Do not use PLN `And` in executable calls; encode multi-condition rules as nested implications and run one `|~` step per antecedent.

---

## `metta`

### Signature
```metta
(metta sexpression)
```

### Purpose
Evaluate an arbitrary MeTTa s-expression in the agent's AtomSpace. Primary use is to invoke **NAL** (`|-`) or **PLN** (`|~`) inference from within the agent loop.

### Parameters
- `sexpression` — a MeTTa s-expression. Read by `sread`, evaluated by `eval`.

### Returns
Whatever the inner expression returns. For NAL/PLN calls, this is a conclusion atom paired with an `(stv frequency confidence)` truth value.

### Examples

**NAL — deduction:**
```metta
(metta (|- ((--> (× sam garfield) friend) (stv 1.0 0.9))
           ((--> garfield animal)         (stv 1.0 0.9))))
```

**NAL — implication with a variable (note `$1`):**
```metta
(metta (|- ((==> (--> (× $1 elephant) eat) (--> $1 ([] dangerous))) (stv 1.0 0.9))
           ((--> (× tiger elephant) eat)                            (stv 1.0 0.9))))
```

**NAL — revision** (same term, two sources): `|-` merges the evidence.

**PLN — forward chaining:**
```metta
(metta (|~ ((Implication (Inheritance $1 (IntSet feathered))
                         (Inheritance $1 bird)) (stv 1.0 0.9))
           ((Inheritance pingu (IntSet feathered)) (stv 1.0 0.9))))
```

---

## Engine selection, stopping criteria, action thresholds

These are policy decisions, not part of the `metta` skill's API. See [reference-orchestration.md](./reference-orchestration.md) for the full tables and rationale (pattern → engine mapping, halt conditions, ACT / HYPOTHESIZE / IGNORE tiers).

---

## Notes / limits

- Independent variables are written `$1`, `$2`, …
- Negated knowledge uses `(stv 0.0 c)`.
- `metta` evaluates **any** MeTTa expression, not just reasoning calls. Malformed input reports errors through `&error` on the next turn.
- For `|~`, pass exactly two supported truth-valued premises.
- Confidence decays ~10% per deduction hop. Chains past 3 hops usually fall below the ACT threshold — see [tutorial-08-reliable-reasoning.md](./tutorial-08-reliable-reasoning.md).
- Premise formulation is the primary failure surface. Verify term order, copula, and granularity before trusting a conclusion. See [reference-failure-modes.md](./reference-failure-modes.md).

---

## See also

- [reference-lib-nal.md](./reference-lib-nal.md) — NAL rule catalogue.
- [reference-lib-pln.md](./reference-lib-pln.md) — PLN rule catalogue.
- [reference-lib-ona.md](./reference-lib-ona.md) — ONA temporal reasoning (experimental, not installed).
- [reference-orchestration.md](./reference-orchestration.md) — full orchestration policy.
- [tutorial-05-reasoning-with-nal-pln.md](./tutorial-05-reasoning-with-nal-pln.md) — worked examples.
