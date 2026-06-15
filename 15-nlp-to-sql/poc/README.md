# NLP-to-SQL — Phase-1 POC

Turn natural-language questions like *"show me any open issues"* into SQL and
run them — using a **semantic layer (ontology)** to bridge how people talk and
how the database is actually built.

> "open issues" → the `incident` table, `status IN ('active','new','in_progress')`
> "unresolved tickets" → the same thing. "pending changes" → the `change_request` table.

That mapping is the whole point: it's business knowledge that lives in
[semantic_layer.yaml](semantic_layer.yaml), not in the database schema and not
in the LLM's head.

## Why this design (and not "dump the schema into an LLM")

The target is a real warehouse: ~500 tables, 200–250 columns each. That's
~112,000 columns — it **cannot** fit in any LLM prompt. So the LLM never sees
the whole schema. Instead:

```
 "show me any open issues"
        │
        ▼
 1. SEMANTIC LAYER     issues  -> incident table
    (the ontology)     open    -> status IN ('active','new','in_progress')
        │
        ▼
 2. SCHEMA SLICE        serialize ONLY the incident table (not all 500)
        │
        ▼
 3. GENERATE SQL        Claude (claude-opus-4-8) — or --mock rule-based
        │
        ▼
 4. VALIDATE            SELECT-only, known tables only, auto-LIMIT (sqlglot)
        │
        ▼
 5. EXECUTE             run against SQLite, return rows
```

## Files

| File | Role |
|---|---|
| [semantic_layer.yaml](semantic_layer.yaml) | **The ontology.** Concept→table synonyms + phrase→value mappings. The most important file. |
| [schema.py](schema.py) | An in-memory SQLite stand-in for the real warehouse (so the POC runs without a DB). |
| [nl_to_sql.py](nl_to_sql.py) | The pipeline: resolve → slice → generate → validate → execute. |
| [requirements.txt](requirements.txt) | `anthropic`, `pyyaml`, `sqlglot`. |

## Run it

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# No API key needed — rule-based generator proves the pipeline end-to-end:
python nl_to_sql.py --mock

# Real LLM SQL generation with Claude (needs ANTHROPIC_API_KEY):
export ANTHROPIC_API_KEY=sk-ant-...
python nl_to_sql.py "show me any open issues"
```

`--mock` swaps step 3 (the LLM) for a small deterministic generator so the
semantic layer, validation, and execution are all testable without a key. The
real path uses `claude-opus-4-8` with adaptive thinking and **structured
outputs** (forces the model to return `{ "sql": "..." }`, so it's always
parseable).

## Sample output (`--mock`)

```
Q: show me any open issues
  semantic layer -> table 'incident'
  value mapping  -> "open" on status means status IN ('active', 'new', 'in_progress')
  generated SQL  -> SELECT * FROM incident WHERE status IN ('active', 'new', 'in_progress')
  validated SQL  -> SELECT * FROM incident WHERE status IN ('active', 'new', 'in_progress') LIMIT 100
  results (4 rows): ['id', 'title', 'status', 'priority', 'assignee', 'created_at']
    (1, 'Email server down', 'active', 'P1', 'Priya', '2026-06-10T09:00')
    ...
```

## How the semantic layer resolves a question

1. **Table pick** — scan the question for any table's synonyms (`issue`,
   `ticket`, `problem` … → `incident`). Plurals are handled (`issues`→`issue`).
2. **Value mapping** — scan for phrases tied to a column's values: `open`,
   `unresolved`, `in progress` all expand to the raw `status` values that mean
   "active". This is what a plain LLM cannot know.
3. The picked table's columns + the value mappings are the *only* schema the
   LLM sees.

## What this POC deliberately leaves out (later phases)

| Phase | Adds |
|---|---|
| **2 — Retrieval** | Embeddings + vector search over table/column descriptions, so table-picking scales past synonym lists to all 500 tables. |
| **3 — Guardrails** | Column-existence checks, row caps, an error-correction loop (feed SQL errors back to Claude to self-fix). |
| **4 — Hardening** | Few-shot NL→SQL examples, an evaluation set, multi-table JOINs, caching. |

The semantic layer is the part you grow first: every new business term users
say ("P1", "major incident", "my tickets") becomes an entry here.
