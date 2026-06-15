# End-to-End Documentation — Family Ontology Demo

This document explains the project top to bottom: what each file does, how data
flows through the system, exactly which reasoning rules fire and why, how the
tests are structured, and how to extend or debug it.

If you only read one section, read **2. The end-to-end flow**.

---

## 1. Project layout

```
demo-family-ontology/
├── family.ttl          # The ontology: schema (TBox) + data (ABox), in Turtle
├── reason.py           # The program: load → reason → query → print
├── test_family.py      # pytest suite asserting the entailments
├── requirements.txt    # rdflib, owlrl, pytest
├── README.md           # Quick start + the "why"
└── DOCUMENTATION.md    # This file
```

Two libraries do all the work:

| Library  | Role                                                              |
|----------|-------------------------------------------------------------------|
| `rdflib` | In-memory RDF graph, Turtle parser, SPARQL query engine           |
| `owlrl`  | An **OWL-RL reasoner** that materialises entailed triples in place |

---

## 2. The end-to-end flow

```
   family.ttl                  reason.py                         stdout
 ┌────────────┐   parse    ┌─────────────────┐   query     ┌──────────────┐
 │  Turtle    │ ─────────▶ │  rdflib.Graph   │ ──────────▶ │  "before"    │
 │  text      │            │  (38 triples)   │   (SPARQL)  │  counts = 0  │
 └────────────┘            └────────┬────────┘             └──────────────┘
                                    │
                                    │  owlrl.DeductiveClosure(...).expand(g)
                                    │  ── forward-chaining: apply OWL-RL rules
                                    │     repeatedly until no new triples appear
                                    ▼
                           ┌─────────────────┐   query     ┌──────────────┐
                           │  rdflib.Graph   │ ──────────▶ │  "after":    │
                           │  (249 triples)  │   (SPARQL)  │  grandparents│
                           │  +211 inferred  │             │  ancestors…  │
                           └─────────────────┘             └──────────────┘
```

Step by step, as executed by `reason.main()`:

1. **Load** — `load_graph()` calls `Graph().parse("family.ttl", format="turtle")`.
   The Turtle text becomes an in-memory set of `(subject, predicate, object)`
   triples. At this point the graph holds **only** what we typed: gender types
   and `hasParent` links (plus the schema axioms). → **38 triples.**

2. **Query "before"** — the same SPARQL queries we'll use later are run now to
   prove the derived facts are genuinely absent: `0` grandparents, `0`
   ancestors, `0` individuals typed `:Parent`.

3. **Reason** — `owlrl.DeductiveClosure(owlrl.OWLRL_Semantics).expand(g)`.
   This is the heart of the demo. The reasoner does **forward chaining**: it
   scans the graph, applies every OWL-RL inference rule whose preconditions
   match, adds the resulting triples, and repeats until a full pass adds
   nothing new (a *fixed point*). The graph is mutated **in place** — `g` now
   contains both asserted and entailed triples. → **249 triples.**

4. **Query "after"** — the identical SPARQL queries now return the inferred
   grandparents, ancestors, parents, and (computed at query time) siblings.

5. **Print** — `short()` trims the namespace IRI to a readable local name
   (`http://example.org/family#Eve` → `Eve`) for the console output.

The single most important observation: **the queries never change between steps
2 and 4.** Only the graph changes — because the reasoner added facts. That gap
is the entire point of an ontology.

---

## 3. The ontology (`family.ttl`) explained

An ontology has two layers. Both live in this one file.

- **TBox** ("terminology") = the schema: classes and property definitions.
- **ABox** ("assertions") = the data: the actual individuals and their links.

### 3.1 Classes (TBox)

```turtle
:Person a owl:Class .
:Man   rdfs:subClassOf :Person .
:Woman rdfs:subClassOf :Person .
```

`Man` and `Woman` are *kinds of* `Person`. Because of this, anything typed
`:Man` is also entailed to be a `:Person` (rule **cax-sco**, below).

```turtle
:Parent a owl:Class ;
    owl:equivalentClass [
        a owl:Restriction ;
        owl:onProperty :hasChild ;
        owl:someValuesFrom :Person
    ] .
```

This is a **defined class**: "a Parent is *exactly* anything that `hasChild`
some `Person`." We never tag anyone `:Parent` in the data — the reasoner
classifies Alice, Bob, and Carol into it because they each have a child.

### 3.2 Properties (TBox)

```turtle
:hasParent owl:inverseOf :hasChild .          # state one direction, get the other
:hasAncestor a owl:TransitiveProperty .        # A→B, B→C  ⇒  A→C
:hasParent rdfs:subPropertyOf :hasAncestor .   # every parent is an ancestor
:hasGrandparent owl:propertyChainAxiom ( :hasParent :hasParent ) .  # parent-of-parent
```

These four axioms are what generate almost all the inferred triples.

### 3.3 Individuals (ABox)

We assert only gender and `hasParent`:

```turtle
:Carol a :Woman . :Carol :hasParent :Alice . :Carol :hasParent :Bob .
:Eve   a :Woman . :Eve   :hasParent :Carol .
...
```

The family tree (3 generations):

```
        Alice ───── Bob
                │
          ┌─────┴─────┐
        Carol       Dave
          │
       ┌──┴──┐
      Eve   Frank
```

---

## 4. Which reasoning rules fire (and the proof for one fact)

`owlrl` implements the standard **OWL 2 RL/RDF rules**. The ones relevant here:

| Rule       | Meaning                                                      | Triggered by             |
|------------|--------------------------------------------------------------|--------------------------|
| `cax-sco`  | `X subClassOf Y`, `a type X` ⇒ `a type Y`                    | Man/Woman ⊑ Person       |
| `prp-inv1` | `inverseOf(p,q)`, `a p b` ⇒ `b q a`                          | hasChild ⇔ hasParent     |
| `prp-spo1` | `p subPropertyOf q`, `a p b` ⇒ `a q b`                       | hasParent ⊑ hasAncestor  |
| `prp-trp`  | `p` transitive, `a p b`, `b p c` ⇒ `a p c`                   | hasAncestor transitive   |
| `prp-spo2` | property chain `p1∘p2`, `a p1 x`, `x p2 b` ⇒ `a p b`         | hasGrandparent chain     |
| `cls-svf2` | `C ≡ ∃p.D`, `a p b` ⇒ `a type C`                             | Parent defined class     |

**Worked example — why `Eve hasGrandparent Alice` is entailed:**

```
Asserted:   Eve   hasParent Carol
Asserted:   Carol hasParent Alice
Rule prp-spo2 (chain hasParent ∘ hasParent → hasGrandparent):
            Eve hasParent Carol  AND  Carol hasParent Alice
        ⇒   Eve hasGrandparent Alice          ✓ inferred, never written down
```

And `Alice` becomes a `:Parent`:

```
Asserted:   Carol hasParent Alice
Rule prp-inv1 (hasChild inverseOf hasParent):
        ⇒   Alice hasChild Carol
Rule cls-svf2 (Parent ≡ hasChild some Person), and Carol is a Person:
        ⇒   Alice type Parent                  ✓ inferred classification
```

---

## 5. `reason.py` walkthrough

| Function              | Responsibility                                                       |
|-----------------------|----------------------------------------------------------------------|
| `load_graph(path)`    | Parse a Turtle file into an `rdflib.Graph`.                          |
| `count_triples(g)`    | `len(g)` — number of triples; used to show the before/after growth.  |
| `grandparent_query`   | SPARQL for `?child :hasGrandparent ?gp`.                            |
| `ancestor_query`      | SPARQL for `?person :hasAncestor ?anc` (transitive closure).        |
| `parents_query`       | SPARQL for `?p a :Parent` (the inferred classification).            |
| `sibling_query`       | SPARQL computing siblings from a shared parent **at query time**.   |
| `short(term)`         | IRI → readable local name for printing.                              |
| `main()`              | Orchestrates: load → count/query before → reason → query/print after.|

Note the design choice: **grandparent/ancestor/parent are materialised by the
reasoner** (stored in the graph), while **sibling is derived in SPARQL** and
never stored. Both are valid "inference" — the demo shows the two styles side
by side. Sibling is done in SPARQL because expressing "shares a parent but is
not self" in OWL-RL cleanly requires negation/`hasSelf` that the RL profile
doesn't fully support.

---

## 6. Testing

`test_family.py` is a `pytest` suite with two fixtures and eight tests.

### 6.1 Fixtures

```python
@pytest.fixture
def asserted():            # the graph BEFORE reasoning
    return reason.load_graph("family.ttl")

@pytest.fixture
def inferred(asserted):    # the same graph AFTER reasoning
    owlrl.DeductiveClosure(owlrl.OWLRL_Semantics).expand(asserted)
    return asserted
```

The `inferred` fixture depends on `asserted`, so pytest builds the base graph
then expands it — each test gets a fresh graph (no cross-test contamination).

### 6.2 What each test guards

| Test                                   | Guarantees                                                |
|----------------------------------------|-----------------------------------------------------------|
| `test_no_grandparents_before_reasoning`| Derived facts are NOT smuggled into the data.             |
| `test_no_parents_typed_before_reasoning`| `:Parent` membership is genuinely inferred, not asserted. |
| `test_grandparents_inferred`           | The property-chain rule produced all 4 grandparent links. |
| `test_ancestor_is_transitive`          | Transitivity reaches Alice from Eve (Eve→Carol→Alice).    |
| `test_parent_class_inferred`           | Exactly {Alice, Bob, Carol} classified as Parent.         |
| `test_inverse_property_gives_children` | `inverseOf` produced `Alice hasChild Carol`.              |
| `test_siblings_from_shared_parent`     | Query-time sibling derivation works.                      |
| `test_reasoning_grows_the_graph`       | Reasoning strictly adds triples.                          |

The "before" tests matter as much as the "after" tests: together they prove the
facts are *entailed*, not pre-loaded. A test that only checked the final graph
couldn't tell the difference between reasoning and cheating.

### 6.3 Running the tests

```bash
source .venv/bin/activate        # or use ./.venv/bin/python directly
pytest -v
```

Expected: `8 passed`.

### 6.4 How to add a test for a new fact

1. Add the data/axiom to `family.ttl`.
2. Add a query helper to `reason.py` if needed.
3. Add a test using the `inferred` fixture asserting the new entailment, and
   ideally a "before" test against `asserted` proving it wasn't pre-stated.

---

## 7. Setup & run (full)

```bash
cd ai-engineering-notes/14-ontology/demo-family-ontology

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python reason.py        # see the inferred facts
pytest -v               # run the test suite
```

> **VS Code hint:** if the editor flags `rdflib`/`owlrl` as "not installed",
> it's pointing at the wrong interpreter. Select the `.venv` one via
> *Python: Select Interpreter* → `.venv/bin/python`. The packages are installed
> there (the tests prove it); the hint is an editor-config issue, not a code bug.

---

## 8. Troubleshooting

| Symptom                                   | Cause / fix                                                        |
|-------------------------------------------|--------------------------------------------------------------------|
| `ModuleNotFoundError: rdflib`             | venv not activated, or deps not installed (`pip install -r ...`).  |
| Reasoning adds 0 triples                  | `family.ttl` failed to parse — check for Turtle syntax errors.     |
| Grandparents not inferred                 | The `owl:propertyChainAxiom` list got malformed; it must be `( :hasParent :hasParent )`. |
| Everyone is their own sibling             | Missing `FILTER (?a != ?b)` in `sibling_query`.                    |
| Tests can't import `reason`               | Run pytest from inside the project dir so `reason.py` is on the path.|

---

## 9. Glossary

- **Triple** — the atom of RDF: `(subject, predicate, object)`.
- **TBox / ABox** — schema (classes, properties) vs. data (individuals).
- **Entailment** — a fact that logically follows from stated facts + axioms.
- **Materialisation** — storing entailed triples in the graph (what `owlrl` does).
- **Forward chaining** — repeatedly applying rules to derive new facts until a fixed point.
- **OWL-RL** — a rule-based, computationally cheap profile of OWL 2; scales well, trades away some expressivity.
- **SPARQL** — the query language for RDF graphs.
