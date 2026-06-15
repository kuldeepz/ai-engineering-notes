# NLP-to-SQL — POC (Phases 1 & 2)

Turn natural-language questions like *"show me any open issues"* into SQL and
run them — using **vector retrieval** to find the right table and a **semantic
layer (ontology)** to bridge how people talk and how the database is built.

> "open issues" → the `incident` table, `status IN ('active','new','in_progress')`
> "list retired hardware" → the `asset` table, `state IN ('retired','decommissioned',...)`
> "pending changes" → the `change_request` table. "list all employees" → `app_user`.

The table is chosen by similarity (not a hand-written rule), and the value
mapping is business knowledge that lives in
[semantic_layer.yaml](semantic_layer.yaml) — not in the database schema and not
in the LLM's head.

## Why this design (and not "dump the schema into an LLM")

The target is a real warehouse: ~500 tables, 200–250 columns each. That's
~112,000 columns — it **cannot** fit in any LLM prompt. So the LLM never sees
the whole schema. Instead:

```
 "show me any open issues"
        │
        ▼
 1. RETRIEVAL          rank ALL tables by similarity, take the best
    (vector search)    → incident (0.12)  vs  change_request/asset (0.00)
        │
        ▼
 2. SEMANTIC LAYER     open -> status IN ('active','new','in_progress')
    (the ontology)
        │
        ▼
 3. SCHEMA SLICE        serialize ONLY the incident table (not all 500)
        │
        ▼
 4. GENERATE SQL        Claude (claude-opus-4-8) — or --mock rule-based
        │
        ▼
 5. VALIDATE            SELECT-only, known tables only, auto-LIMIT (sqlglot)
        │
        ▼
 6. EXECUTE             run against SQLite, return rows
```

**Phase 1** picked the table with a synonym regex — fine for a few tables, but
you can't hand-author every phrasing for 500. **Phase 2** replaces that with
vector retrieval: each table is embedded as a "document" (description +
synonyms + columns), the question is embedded, and tables are ranked by cosine
similarity. Only the top table flows downstream.

## Files

| File | Role |
|---|---|
| [retrieval.py](retrieval.py) | **Phase 2.** Ranks tables by vector similarity. Pluggable embedder — TF-IDF locally, swap for Voyage AI / sentence-transformers in prod. |
| [semantic_layer.yaml](semantic_layer.yaml) | **The ontology.** Concept→table synonyms + phrase→value mappings. |
| [schema.py](schema.py) | In-memory SQLite stand-in for the warehouse (4 tables) so the POC runs without a DB. |
| [nl_to_sql.py](nl_to_sql.py) | The pipeline: retrieve → resolve → slice → generate → validate → execute. |
| [requirements.txt](requirements.txt) | `anthropic`, `pyyaml`, `sqlglot`, `scikit-learn`. |

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

`--mock` swaps the LLM step for a small deterministic generator so retrieval,
the semantic layer, validation, and execution are all testable without a key.
The real path uses `claude-opus-4-8` with adaptive thinking and **structured
outputs** (forces the model to return `{ "sql": "..." }`, so it's always
parseable).

## Sample output (`--mock`)

```
Q: show me any open issues
  retrieval      -> candidates: incident=0.12, change_request=0.00, asset=0.00
  chosen table   -> 'incident'
  value mapping  -> "open" on status means status IN ('active', 'new', 'in_progress')
  generated SQL  -> SELECT * FROM incident WHERE status IN ('active', 'new', 'in_progress')
  validated SQL  -> SELECT * FROM incident WHERE status IN ('active', 'new', 'in_progress') LIMIT 100
  results (4 rows): ['id', 'title', 'status', 'priority', 'assignee', 'created_at']
    (1, 'Email server down', 'active', 'P1', 'Priya', '2026-06-10T09:00')
    ...
```

## On the retriever (and its honest limitation)

The POC uses a **local TF-IDF embedder** — offline, deterministic, no API key,
no model download — so the whole thing runs anywhere. TF-IDF is *lexical*: it
matches words, not meaning. To make plural questions match singular synonyms
(`issues`→`issue`), `retrieval.py` does light singularization in its tokenizer.

In production you swap **only the embedder** for a real semantic embedding model
— Voyage AI (Anthropic's recommended provider) or a local sentence-transformers
model — and store vectors in a vector DB (pgvector, Qdrant, Chroma). The
ranking logic is identical; real embeddings generalize to phrasings the
synonyms never listed (e.g. "my machine is broken" → `asset`/`incident`)
without any tokenizer tricks.

## Build phases

| Phase | Status | Adds |
|---|---|---|
| **1 — Semantic layer** | ✅ done | YAML ontology: synonyms → tables, phrases → values; Claude SQL gen; sqlglot validation; SQLite execution. |
| **2 — Retrieval** | ✅ done | Vector search over table documents, so table-picking scales past synonym lists toward 500 tables. |
| **3 — Guardrails** | next | Column-existence checks, row caps, an error-correction loop (feed SQL errors back to Claude to self-fix). |
| **4 — Hardening** | later | Few-shot NL→SQL examples, an evaluation set, multi-table JOINs, caching. |

The semantic layer is the part you grow first: every new business term users
say ("P1", "major incident", "my tickets") becomes an entry there.
