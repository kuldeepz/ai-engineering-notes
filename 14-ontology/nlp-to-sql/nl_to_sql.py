"""
NLP-to-SQL — Phase-2 POC (vector retrieval + semantic layer).

Pipeline (see README for the full architecture):

    question
      -> 1. RETRIEVAL      : rank tables by vector similarity, take the best
                            (scales to 500 tables; see retrieval.py)
      -> 2. SEMANTIC LAYER : expand value phrases (open -> status IN (...))
      -> 3. SCHEMA SLICE   : serialize ONLY the chosen table's columns
      -> 4. GENERATE SQL   : Claude (claude-opus-4-8), or --mock rule-based
      -> 5. VALIDATE        : SELECT-only, known tables, auto-LIMIT (sqlglot)
      -> 6. EXECUTE         : run against the SQLite stand-in, print rows

Run:
    python nl_to_sql.py "show me any open issues"            # uses Claude (needs ANTHROPIC_API_KEY)
    python nl_to_sql.py --mock "show me any open issues"     # no API key needed
"""

import argparse
import json
import re
import sys

import sqlglot
import sqlglot.expressions as exp
import yaml

from retrieval import TableRetriever
from schema import build_db

MODEL = "claude-opus-4-8"


# --------------------------------------------------------------------------- #
# 0. Load the semantic layer
# --------------------------------------------------------------------------- #
def load_semantic_layer(path: str = "semantic_layer.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


# --------------------------------------------------------------------------- #
# 1. RETRIEVAL + SEMANTIC LAYER — resolve business words to the schema
# --------------------------------------------------------------------------- #
def resolve_value_hints(question: str, table: str, layer: dict) -> list[str]:
    """
    Turn phrases like 'open' / 'unresolved' into concrete value mappings for
    this table's columns, e.g.  status IN ('active','new','in_progress').
    """
    q = question.lower()
    hints: list[str] = []
    for col_key, mapping in layer.get("value_synonyms", {}).items():
        col_table, column = col_key.split(".")
        if col_table != table:
            continue
        for phrase, group in mapping["phrases"].items():
            if re.search(rf"\b{re.escape(phrase)}\b", q):
                values = mapping["groups"][group]
                rendered = ", ".join(f"'{v}'" for v in values)
                hints.append(f"\"{phrase}\" on {column} means {column} IN ({rendered})")
    # de-dup while preserving order
    return list(dict.fromkeys(hints))


# --------------------------------------------------------------------------- #
# 2. SCHEMA SLICE — serialize only the relevant table
# --------------------------------------------------------------------------- #
def schema_slice(table: str, layer: dict) -> str:
    meta = layer["tables"][table]
    lines = [f"TABLE {table}  -- {meta['description']}"]
    for col, info in meta["columns"].items():
        lines.append(f"  {col} {info['type']}  -- {info['description']}")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# 3a. GENERATE SQL — Claude
# --------------------------------------------------------------------------- #
SYSTEM_PROMPT = """You translate a natural-language question into a single \
SQLite SELECT statement.

Rules:
- Use ONLY the table and columns provided in the schema.
- Apply the value mappings exactly as given (they encode business synonyms).
- Generate a read-only SELECT. Never write INSERT/UPDATE/DELETE/DROP.
- Return only the SQL via the structured output; no commentary."""

SQL_SCHEMA = {
    "type": "object",
    "properties": {"sql": {"type": "string", "description": "The SQLite SELECT statement"}},
    "required": ["sql"],
    "additionalProperties": False,
}


def generate_sql_claude(question: str, schema_txt: str, hints: list[str]) -> str:
    import anthropic  # imported lazily so --mock works without the package configured

    client = anthropic.Anthropic()
    hint_block = "\n".join(f"- {h}" for h in hints) or "- (none)"
    user = (
        f"Schema:\n{schema_txt}\n\n"
        f"Value mappings to apply:\n{hint_block}\n\n"
        f"Question: {question}"
    )
    resp = client.messages.create(
        model=MODEL,
        max_tokens=2000,
        thinking={"type": "adaptive"},
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user}],
        output_config={"format": {"type": "json_schema", "schema": SQL_SCHEMA}},
    )
    text = next(b.text for b in resp.content if b.type == "text")
    return json.loads(text)["sql"]


# --------------------------------------------------------------------------- #
# 3b. GENERATE SQL — mock (deterministic, no API key) so the pipeline is testable
# --------------------------------------------------------------------------- #
def generate_sql_mock(question: str, table: str, hints: list[str]) -> str:
    """A tiny rule-based stand-in for Claude. Handles the demo questions only."""
    where = []
    for h in hints:
        # hints look like:  "open" on status means status IN ('active', ...)
        m = re.search(r"means (.+)$", h)
        if m:
            where.append(m.group(1))
    clause = f" WHERE {' AND '.join(where)}" if where else ""
    return f"SELECT * FROM {table}{clause}"


# --------------------------------------------------------------------------- #
# 4. VALIDATE — SELECT-only, known tables, auto-LIMIT
# --------------------------------------------------------------------------- #
def validate_sql(sql: str, allowed_tables: set[str], limit: int = 100) -> str:
    try:
        tree = sqlglot.parse_one(sql, read="sqlite")
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"SQL did not parse: {e}") from e

    if not isinstance(tree, exp.Select):
        raise ValueError("Only SELECT statements are allowed (read-only guard).")

    used = {t.name for t in tree.find_all(exp.Table)}
    unknown = used - allowed_tables
    if unknown:
        raise ValueError(f"Query references unknown tables: {sorted(unknown)}")

    if not tree.args.get("limit"):
        tree = tree.limit(limit)
    return tree.sql(dialect="sqlite")


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def answer(question: str, layer: dict, conn, retriever: TableRetriever, use_mock: bool) -> None:
    print(f"Q: {question}")

    # 1. RETRIEVAL — rank tables by similarity, take the best (scales to 500 tables)
    table, ranked = retriever.top_table(question)
    top3 = ", ".join(f"{t}={s:.2f}" for t, s in ranked[:3])
    print(f"  retrieval      -> candidates: {top3}")
    if not table:
        print("  ✗ No table scored above threshold (extend the semantic layer / descriptions).")
        return

    # then the SEMANTIC LAYER expands value phrases for the chosen table
    hints = resolve_value_hints(question, table, layer)
    print(f"  chosen table   -> '{table}'")
    for h in hints:
        print(f"  value mapping  -> {h}")

    schema_txt = schema_slice(table, layer)
    if use_mock:
        raw_sql = generate_sql_mock(question, table, hints)
    else:
        raw_sql = generate_sql_claude(question, schema_txt, hints)
    print(f"  generated SQL  -> {raw_sql}")

    sql = validate_sql(raw_sql, allowed_tables=set(layer["tables"]))
    print(f"  validated SQL  -> {sql}")

    rows = conn.execute(sql).fetchall()
    cols = [d[0] for d in conn.execute(sql).description]
    print(f"  results ({len(rows)} rows): {cols}")
    for r in rows:
        print(f"    {r}")
    print()


DEMO_QUESTIONS = [
    "show me any open issues",          # -> incident
    "list retired hardware",            # -> asset
    "show pending changes",             # -> change_request
    "list all employees",               # -> app_user
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("question", nargs="?", help="natural-language question")
    ap.add_argument("--mock", action="store_true", help="use the rule-based generator (no API key)")
    args = ap.parse_args()

    layer = load_semantic_layer()
    conn = build_db()
    retriever = TableRetriever(layer)

    questions = [args.question] if args.question else DEMO_QUESTIONS
    for q in questions:
        try:
            answer(q, layer, conn, retriever, use_mock=args.mock)
        except ValueError as e:
            print(f"  ✗ {e}\n", file=sys.stderr)


if __name__ == "__main__":
    main()
