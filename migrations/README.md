# Database Migrations

This directory contains SQL migration scripts for schema changes.

## Current Status

PureBoot uses SQLAlchemy's `create_all()` for fresh database initialization. These SQL scripts are provided for:

1. **Production upgrades** - Apply schema changes to existing databases
2. **Documentation** - Track schema changes over time
3. **Future Alembic setup** - Reference for creating Alembic migrations

## Migration Scripts

| Version | Description | Date |
|---------|-------------|------|
| 001 | Multi-site management fields (Phase 1) | 2026-01-26 |

## Applying Migrations

### Fresh Installation

For new installations, the database is automatically created by `create_all()` when PureBoot starts. No manual migration is needed.

### Existing Installation

For existing databases, apply migrations in order:

```bash
# Connect to your PostgreSQL database
psql -U pureboot -d pureboot

# Apply migration
\i migrations/versions/001_add_site_fields.sql
```

Or via command line:

```bash
psql -U pureboot -d pureboot -f migrations/versions/001_add_site_fields.sql
```

### SQLite (Development)

For SQLite databases:

```bash
sqlite3 pureboot.db < migrations/versions/001_add_site_fields.sql
```

Note: Some PostgreSQL-specific syntax (like `DO $$ ... $$`) may need adjustment for SQLite.

## Writing Migrations

When adding new migrations:

1. Create a new file with format `NNN_description.sql`
2. Include clear comments explaining the changes
3. Add rollback commands at the bottom (commented out)
4. Update this README with the new migration

## Future: Alembic Setup

We plan to add Alembic for automated migrations. When that happens:

1. These SQL scripts will be archived
2. Alembic will handle version tracking automatically
3. Run migrations with `alembic upgrade head`
