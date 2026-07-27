-- Runs once on first container start, before Alembic. Alembic owns the schema;
-- this file only guarantees the extension exists so migrations can call
-- create_hypertable().
CREATE EXTENSION IF NOT EXISTS timescaledb;
