"""Database schema migrations for SQLite.

SQLite doesn't support full ALTER TABLE, so we use a simple approach:
- Check which columns exist
- Add missing columns with ALTER TABLE ADD COLUMN

This runs automatically during application startup.
"""
import logging
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncConnection

logger = logging.getLogger(__name__)

# Define expected columns for each table
# Format: {table_name: [(column_name, column_type, default_value), ...]}
EXPECTED_SCHEMA = {
    "nodes": [
        ("health_status", "VARCHAR(20)", "'unknown'"),
        ("health_score", "INTEGER", "100"),
        ("boot_count", "INTEGER", "0"),
        ("last_boot_at", "DATETIME", None),
        ("last_ip_change_at", "DATETIME", None),
        ("previous_ip_address", "VARCHAR(45)", None),
        ("pi_model", "VARCHAR(20)", None),
        ("home_site_id", "VARCHAR(36)", None),
        ("disk_scan_requested_at", "DATETIME", None),
        ("pending_command", "VARCHAR(50)", None),
    ],
    "node_health_snapshots": [
        # This table should be created by create_all, but list columns for completeness
    ],
    "node_health_alerts": [
        # This table should be created by create_all
    ],
}

# Indexes to create if missing
EXPECTED_INDEXES = [
    ("ix_nodes_health_status", "nodes", "health_status"),
]


async def get_existing_columns(conn: AsyncConnection, table_name: str) -> set[str]:
    """Get existing column names for a table."""
    result = await conn.execute(text(f"PRAGMA table_info({table_name})"))
    rows = result.fetchall()
    return {row[1] for row in rows}  # column name is at index 1


async def get_existing_indexes(conn: AsyncConnection) -> set[str]:
    """Get existing index names."""
    result = await conn.execute(
        text("SELECT name FROM sqlite_master WHERE type='index'")
    )
    rows = result.fetchall()
    return {row[0] for row in rows}


async def add_column(
    conn: AsyncConnection,
    table_name: str,
    column_name: str,
    column_type: str,
    default_value: str | None,
) -> None:
    """Add a column to an existing table."""
    if default_value is not None:
        sql = f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type} DEFAULT {default_value}"
    else:
        sql = f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"

    await conn.execute(text(sql))
    logger.info(f"Added column {table_name}.{column_name}")


async def create_index(
    conn: AsyncConnection,
    index_name: str,
    table_name: str,
    column_name: str,
) -> None:
    """Create an index if it doesn't exist."""
    sql = f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name}({column_name})"
    await conn.execute(text(sql))
    logger.info(f"Created index {index_name}")


async def run_migrations(conn: AsyncConnection) -> None:
    """Run all pending migrations.

    This checks each table for missing columns and adds them.
    Safe to run multiple times - only adds what's missing.
    """
    logger.info("Checking database schema...")

    migrations_applied = 0

    for table_name, columns in EXPECTED_SCHEMA.items():
        # Check if table exists
        result = await conn.execute(
            text(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'")
        )
        if not result.fetchone():
            # Table doesn't exist, will be created by create_all
            continue

        existing_columns = await get_existing_columns(conn, table_name)

        for column_name, column_type, default_value in columns:
            if column_name not in existing_columns:
                await add_column(conn, table_name, column_name, column_type, default_value)
                migrations_applied += 1

    # Create missing indexes
    existing_indexes = await get_existing_indexes(conn)
    for index_name, table_name, column_name in EXPECTED_INDEXES:
        if index_name not in existing_indexes:
            await create_index(conn, index_name, table_name, column_name)
            migrations_applied += 1

    if migrations_applied > 0:
        logger.info(f"Applied {migrations_applied} schema migrations")
    else:
        logger.info("Database schema is up to date")