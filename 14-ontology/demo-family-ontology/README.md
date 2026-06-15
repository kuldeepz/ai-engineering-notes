# Family Ontology — a tiny, runnable demo

A minimal OWL ontology that demonstrates the one thing that makes ontologies
different from a database: **a reasoner infers facts you never stated.**

We assert only `hasParent` relationships and each person's gender. After running
an OWL reasoner, the graph also "knows" grandparents, ancestors (transitively),
children, and who counts as a `Parent` — none of which appear in the data.

## What it demonstrates

| Ontology concept            | Where it lives                                          | What you see |
|-----------------------------|---------------------------------------------------------|--------------|
| Class hierarchy             | `Man ⊑ Person`, `Woman ⊑ Person`                        | gender classes |
| Defined (equivalent) class  | `Parent ≡ hasChild some Person`                         | Alice/Bob/Carol auto-typed `:Parent` |
| Inverse property            | `hasChild owl:inverseOf hasParent`                      | children derived from parents |
| Transitive property         | `hasAncestor a owl:TransitiveProperty`                  | great-grandparents inferred |
| Property chain              | `hasGrandparent ← hasParent ∘ hasParent`                | grandparents inferred |
| Query-time derivation       | SPARQL for `sibling` (shared parent)                    | siblings without storing them |

## Files

- `family.ttl` — the ontology (TBox = schema) + individuals (ABox = data), in Turtle.
- `reason.py` — loads the graph, prints counts *before* reasoning, runs the
  OWL-RL reasoner, then prints the *inferred* grandparents, ancestors, parents,
  and (query-time) siblings.
- `requirements.txt` — `rdflib` (graph + SPARQL) and `owlrl` (the OWL-RL reasoner).

## Run it

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python reason.py
```

## Expected output (abridged)

```
Asserted triples (before reasoning): 38
  Grandparent links asserted: 0
  Ancestor links asserted:    0
  Individuals typed :Parent:  0

Reasoning complete. Triples now: 249  (+211 inferred)

Inferred GRANDPARENTS (child  ->  grandparent):
  Eve      ->  Alice
  Eve      ->  Bob
  ...
Individuals the reasoner classified as :Parent:
  Alice / Bob / Carol
```

The key line is `Grandparent links asserted: 0` → after reasoning, four exist.
That gap is the ontology doing its job.

## The family modelled

```
        Alice (Woman)──────Bob (Man)          <- generation 1
                  │
        ┌─────────┴─────────┐
     Carol (Woman)      Dave (Man)             <- generation 2
        │
   ┌────┴────┐
  Eve     Frank                                <- generation 3
(Woman)   (Man)
```

So `Eve`'s grandparents (`Alice`, `Bob`) and `Eve`'s ancestor `Alice` are all
*derived*, never written down.

## Where to take it next

- Add `married` (symmetric property) → infer spouse both ways.
- Add a `disjointWith` between `Man` and `Woman` → the reasoner will flag a
  contradiction if anyone is typed as both (consistency checking).
- Swap `owlrl` for **Protégé + HermiT** to explore the same `.ttl` in a GUI.
