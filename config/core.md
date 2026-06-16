# Mission Canvas — Tier 1 Immutable Rules

These rules CANNOT be auto-modified. They require human approval + commit.
They are the constitution of the Governed Agent OS.

---

## Rule 1: Every query is classified before any model fires.
No exceptions. The ontology classification determines governance rules,
model routing, and lens activation BEFORE reasoning begins.

## Rule 2: Sensitive classification blocks external routing architecturally.
When `blocks_external = True`, it is not a suggestion. It is a gate in the
pipeline code. No amount of model confidence overrides it.

## Rule 3: Every completed query produces a path record.
Memory compounds with every use. Step 6 (STORE) always fires.
Even failed queries produce a gap signal. No silent degradation.

## Rule 4: Self-modification is tiered.
- Tier 3 (observations): automated, reversible, append-only
- Tier 2 (assumptions): human review, reversible
- Tier 1 (these rules): human approval + commit required

## Rule 5: The ontology is the source of truth for all routing decisions.
Not model confidence. Not user intent. The ontology.
If the ontology says it's privileged, it's privileged.

## Rule 6: Glass-box architecture.
Every decision must be traceable through path records.
No black boxes. No opaque routing. Every step logged.

## Rule 7: Evidence-based only.
No unsourced claims in the knowledge library.
Tier 1: primary sources. Tier 2: secondary. Tier 3: community (vetted).

## Rule 8: Privacy by design.
PII is stripped before any external call. No exceptions.
No PII in path records. No PII in gap signals. No PII in community contributions.

---

## Retrieval Principles (enforced by rules above)

These three principles from the Vector Space Day research (2026-06-11) are
already architecturally enforced by MC's rules. Named here for explicitness:

- **Retrieval ≠ Authorization** → Rules 2, 5, 8. The entry gate + blocks_external
  ensures retrieved content passes authorization before surfacing.
- **Memory ≠ Retrieval** → Rule 3. Path records compound behavioral improvement;
  they are not a retrieval cache.
- **Similarity ≠ Relevance** → Rules 1, 5. Ontology classification (not vector
  similarity) determines routing. The ontology IS the relevance signal.

---

*These rules are load-bearing walls. Touch them and the building falls.*
