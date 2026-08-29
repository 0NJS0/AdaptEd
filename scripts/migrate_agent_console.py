"""Additive, idempotent migration for the Agent Console feature.

Adds the token-usage / cost / human-in-the-loop columns to ``agent_tasks`` on an
existing database. Safe to run repeatedly (uses ``ADD COLUMN IF NOT EXISTS``) and
non-destructive (existing rows get the column defaults).

Run it once after switching to the ``feat/agent-console`` branch on a database
that already has an ``agent_tasks`` table:

    uv run python scripts/migrate_agent_console.py

A brand-new database needs nothing — the columns are created automatically.
"""

from __future__ import annotations

from sqlalchemy import text

from adapted.database.session import engine

STATEMENTS = [
    "ALTER TABLE agent_tasks ADD COLUMN IF NOT EXISTS prompt_tokens INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE agent_tasks ADD COLUMN IF NOT EXISTS completion_tokens INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE agent_tasks ADD COLUMN IF NOT EXISTS llm_calls INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE agent_tasks ADD COLUMN IF NOT EXISTS cost_usd DOUBLE PRECISION NOT NULL DEFAULT 0",
    "ALTER TABLE agent_tasks ADD COLUMN IF NOT EXISTS control VARCHAR(12) NOT NULL DEFAULT 'run'",
]


def main() -> None:
    with engine.begin() as conn:
        for stmt in STATEMENTS:
            conn.execute(text(stmt))
            print("applied:", stmt.split("ADD COLUMN IF NOT EXISTS ")[-1])
    print("Agent Console migration complete.")


if __name__ == "__main__":
    main()
