# Reference — `lib_pln.metta`

Probabilistic Logic Networks (PLN) — a higher-order probabilistic reasoning framework compatible with the AtomSpace. PLN is the engine to reach for when a problem is best expressed as **property-based categorical inference** rather than the asymmetric inheritance chains NAL specializes in.

---

## Relations

| Atom | Meaning |
|---|---|
| `Inheritance` | Probabilistic "is-a" relation. |
| `Implication` | Conditional probability — `(Implication P Q)` ≈ `P(Q | P)`. |
| `IntSet` | Intensional set — members share a property. |
| `Product` | Ordered tuple for binary relations, e.g. `(Inheritance (Product anna bob) friend)`. |
| `Evaluation` | Predicate application, normally with `(Predicate p)` and `(List (Concept x) ...)`. |

Truth values share NAL's `(stv frequency confidence)` format, interpreted probabilistically.

---

## The `|~` operator

`|~` applies one PLN step over two truth-valued premises:

```metta
(|~ ((premise-1) (stv f1 c1))
    ((premise-2) (stv f2 c2)))
```

OmegaClaw's bundled `lib_pln.metta` exposes this local two-premise operator. Newer upstream TrueAGI PLN examples often use `PLN.Query` over a `Sentence` knowledge base; that is useful reference material, but it is a different interface from OmegaClaw's stock skill surface.

If the raw evaluator returns a value beginning with `(partial |~ ...)`, the call had only one premise. If it returns `()`, the premises did not match any supported PLN rule. Neither is a PLN conclusion and neither should be treated as evidence.

---

## Rule catalogue — confirmed

### Modus Ponens

**Primary PLN inference.**

**Shape:** `(Implication P Q)` and `P` ⊢ `Q`.

**Truth function:**

```
f = f₁ × f₂
c = f₁ × f₂ × c₁ × c₂
```

Same shape as NAL deduction — confidence decays linearly.

For rules with more than one antecedent, prefer nested implications:

```metta
((Implication P (Implication Q R)) (stv 1.0 0.8))
```

Do not use `(And P Q)` as the antecedent in OmegaClaw's executable PLN calls. The bundled `|~` modus ponens rule consumes one antecedent per step.

### Abduction (on Inheritance premises)

**Shape:** supports abduction over `Inheritance` premises.

**Empirical check:** `(Inheritance bird flyer)` + `(Inheritance robin flyer)` ⊢ `(Inheritance robin bird) (stv 0.767 0.422)`.

Note the output confidence `0.422` — comparable to NAL's abduction ceiling (~0.45). Abduction produces *hypotheses worth testing*, not *actionable conclusions*.

### Revision

**Shape:** two beliefs about the same statement.

**Truth function:** identical to NAL revision.

```
w = c / (1 - c)
w_total = Σ w_i
c_out = w_total / (w_total + 1)
f_out = weighted average of f_i by w_i
```

Use revision to merge evidence across PLN conclusions, across NAL conclusions, or across both — the math is the same.

---

## What does NOT work in PLN (current deployment)

| Pattern | Status |
|---|---|
| **PLN abduction** (general case beyond confirmed shapes) | Returns empty in practice despite theoretical support. |
| **Backward inference** | Forward inference only. |

If PLN returns empty, reformulate as NAL or try a different premise shape. See recovery guidance in [reference-orchestration.md](./reference-orchestration.md).

---

## Invocation

Through the `(metta ...)` skill. Variables use `$1`, `$2`, …

### Modus Ponens example

```metta
(metta (|~ ((Implication (Inheritance $1 (IntSet feathered))
                         (Inheritance $1 bird)) (stv 1.0 0.9))
           ((Inheritance pingu (IntSet feathered)) (stv 1.0 0.9))))
```

Conclusion: `(Inheritance pingu bird)` with a derived `(stv ...)`.

### Two-condition rule

Run one `|~` step per antecedent:

```metta
(metta (|~ ((Implication (Inheritance $1 (IntSet small_length))
                         (Implication (Inheritance $1 (IntSet ai_topic))
                                      (Inheritance $1 (IntSet high_engagement)))) (stv 1.0 0.75))
           ((Inheritance article_1 (IntSet small_length)) (stv 1.0 0.8))))
```

Then use the returned implication with the second fact:

```metta
(metta (|~ ((Implication (Inheritance article_1 (IntSet ai_topic))
                         (Inheritance article_1 (IntSet high_engagement))) (stv 1.0 0.6))
           ((Inheritance article_1 (IntSet ai_topic)) (stv 1.0 0.8))))
```

### Binary relation fact

Use `Product` for relation arguments:

```metta
(metta (|~ ((Implication (Inheritance (Product $1 $2) friend)
                         (Implication (Inheritance $1 (IntSet smokes))
                                      (Inheritance $2 (IntSet smokes)))) (stv 0.4 0.9))
           ((Inheritance (Product anna bob) friend) (stv 1.0 0.9))))
```

### Predicate evaluation form

Use `Evaluation` for predicate-as-predicate rules, especially when using the dedicated evaluation/inheritance rules:

```metta
(metta (|~ ((Evaluation (Predicate is_really_fat)
                        (List (Concept cat))) (stv 1.0 0.9))
           ((Implication (Predicate is_really_fat)
                         (Predicate is_fat)) (stv 1.0 0.9))))
```

For ordinary natural-language properties such as "high engagement", prefer `Inheritance article_1 (IntSet high_engagement)` instead of `Evaluation`.

### Abduction example

```metta
(metta (|~ ((Inheritance bird flyer)  (stv 1.0 0.9))
           ((Inheritance robin flyer) (stv 1.0 0.9))))
```

Conclusion: `(Inheritance robin bird) (stv 0.767 0.422)`.

---

## NAL vs. PLN — which to use

| Situation | Engine |
|---|---|
| Asymmetric chain `A → B → C` | NAL `\|-` |
| Observed effect, seeking cause (simple) | NAL `\|-` abduction |
| Merging independent evidence | Either (identical formula) |
| Property-based categorical inference | PLN `\|~` |
| Higher-order structures (`Implication` over `Inheritance`) | PLN `\|~` |
| Real-time or temporal reasoning | Not served by a stock engine — ONA is the planned future target (see [reference-lib-ona.md](./reference-lib-ona.md), experimental, not installed). Current fallback: NAL with external temporal grounding. |

When in doubt, try NAL first; PLN shines on `Implication` over `Inheritance` chains.

---

## See also

- [reference-lib-nal.md](./reference-lib-nal.md) — sibling symbolic engine.
- [reference-lib-ona.md](./reference-lib-ona.md) — planned temporal engine (experimental, not installed).
- [reference-orchestration.md](./reference-orchestration.md) — engine selection.
- [tutorial-05-reasoning-with-nal-pln.md](./tutorial-05-reasoning-with-nal-pln.md) — worked examples.
