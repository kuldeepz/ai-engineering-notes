"""
Builds a small in-memory SQLite database that stands in for the real 500-table
warehouse. The POC runs queries against this so the whole pipeline is testable
end-to-end without a production DB.
"""

import sqlite3

DDL = """
CREATE TABLE incident (
    id         INTEGER PRIMARY KEY,
    title      TEXT,
    status     TEXT,
    priority   TEXT,
    assignee   TEXT,
    created_at TEXT
);

CREATE TABLE change_request (
    id        INTEGER PRIMARY KEY,
    title     TEXT,
    status    TEXT,
    risk      TEXT,
    requester TEXT
);

CREATE TABLE asset (
    id    INTEGER PRIMARY KEY,
    name  TEXT,
    kind  TEXT,
    state TEXT,
    owner TEXT
);

CREATE TABLE app_user (
    id         INTEGER PRIMARY KEY,
    name       TEXT,
    department TEXT,
    email      TEXT
);
"""

INCIDENTS = [
    (1, "Email server down",        "active",      "P1", "Priya",   "2026-06-10T09:00"),
    (2, "VPN intermittent",         "in_progress", "P2", "Sam",     "2026-06-11T14:20"),
    (3, "Printer offline",          "new",         "P4", "Sam",     "2026-06-14T08:05"),
    (4, "Password reset request",   "resolved",    "P3", "Priya",   "2026-06-09T11:30"),
    (5, "Laptop won't boot",        "closed",      "P2", "Alex",    "2026-06-08T16:45"),
    (6, "Slow database queries",    "active",      "P2", "Alex",    "2026-06-13T10:10"),
]

CHANGES = [
    (1, "Upgrade mail cluster",  "scheduled",   "high",   "Priya"),
    (2, "Patch VPN gateway",     "in_review",   "medium", "Sam"),
    (3, "Rotate TLS certs",      "implemented", "low",    "Alex"),
]

ASSETS = [
    (1, "LT-1001",   "laptop",  "in_use",        "Priya"),
    (2, "LT-1002",   "laptop",  "retired",       "Sam"),
    (3, "MON-22",    "monitor", "in_use",        "Alex"),
    (4, "SRV-prod1", "server",  "in_use",        "ops"),
    (5, "LT-0007",   "laptop",  "decommissioned","Alex"),
]

USERS = [
    (1, "Priya Nair",   "IT Operations", "priya@example.com"),
    (2, "Sam Okoro",    "Service Desk",  "sam@example.com"),
    (3, "Alex Romano",  "Engineering",   "alex@example.com"),
]


def build_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript(DDL)
    conn.executemany("INSERT INTO incident VALUES (?,?,?,?,?,?)", INCIDENTS)
    conn.executemany("INSERT INTO change_request VALUES (?,?,?,?,?)", CHANGES)
    conn.executemany("INSERT INTO asset VALUES (?,?,?,?,?)", ASSETS)
    conn.executemany("INSERT INTO app_user VALUES (?,?,?,?)", USERS)
    conn.commit()
    return conn
