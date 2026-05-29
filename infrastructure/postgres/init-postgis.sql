-- ============================================================
-- RoadSide Agent — PostgreSQL initialization
-- Runs once when the postgres container starts on a fresh volume.
-- ============================================================

-- Enable PostGIS for geospatial nearest-provider queries
CREATE EXTENSION IF NOT EXISTS postgis;

-- Enable pgcrypto for gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Enable trigram search for future fuzzy name lookups
CREATE EXTENSION IF NOT EXISTS pg_trgm;
