-- Climate feed store.
-- One row per *work* (a preprint and its published version collapse into one row).

PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS works (
    id                INTEGER PRIMARY KEY,

    -- Identity / dedup keys
    doi               TEXT UNIQUE,          -- normalised: "10.1029/2024gl108123", no prefix
    arxiv_id          TEXT UNIQUE,          -- "2504.01234" (no version suffix)
    openalex_id       TEXT UNIQUE,          -- "W2741809807"
    title_key         TEXT NOT NULL,        -- normalised title, used for fuzzy collapse
    block_key         TEXT,                 -- first-author-surname + year, cheap blocking

    -- Content
    title             TEXT NOT NULL,
    abstract          TEXT,
    authors           TEXT,                 -- JSON array of strings
    venue             TEXT,
    published_date    TEXT,                 -- ISO date, best known
    url               TEXT,
    pdf_url           TEXT,
    is_oa             INTEGER DEFAULT 0,

    -- Provenance & classification
    sources           TEXT NOT NULL,        -- JSON array, e.g. ["arxiv","openalex"]
    kind              TEXT NOT NULL DEFAULT 'research',  -- 'research' | 'policy'
    topics            TEXT,                 -- JSON array of topic labels
    score             REAL,                 -- relevance 0-1 from classifier
    tier              TEXT,                 -- 'accept' | 'uncertain' | 'reject'

    first_seen        TEXT NOT NULL,
    last_updated      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_works_title_key ON works(title_key);
CREATE INDEX IF NOT EXISTS idx_works_block     ON works(block_key);
CREATE INDEX IF NOT EXISTS idx_works_date      ON works(published_date DESC);
CREATE INDEX IF NOT EXISTS idx_works_tier      ON works(tier, published_date DESC);

-- Full-text search. Contentless-delta table synced by triggers.
CREATE VIRTUAL TABLE IF NOT EXISTS works_fts USING fts5(
    title, abstract, authors,
    content='works', content_rowid='id', tokenize='porter unicode61'
);

CREATE TRIGGER IF NOT EXISTS works_ai AFTER INSERT ON works BEGIN
    INSERT INTO works_fts(rowid, title, abstract, authors)
    VALUES (new.id, new.title, new.abstract, new.authors);
END;

CREATE TRIGGER IF NOT EXISTS works_ad AFTER DELETE ON works BEGIN
    INSERT INTO works_fts(works_fts, rowid, title, abstract, authors)
    VALUES ('delete', old.id, old.title, old.abstract, old.authors);
END;

CREATE TRIGGER IF NOT EXISTS works_au AFTER UPDATE ON works BEGIN
    INSERT INTO works_fts(works_fts, rowid, title, abstract, authors)
    VALUES ('delete', old.id, old.title, old.abstract, old.authors);
    INSERT INTO works_fts(rowid, title, abstract, authors)
    VALUES (new.id, new.title, new.abstract, new.authors);
END;

-- Per-source incremental state. This is the whole low-carbon story:
-- never re-fetch what we already have.
CREATE TABLE IF NOT EXISTS source_state (
    source       TEXT PRIMARY KEY,
    last_run     TEXT,
    watermark    TEXT,   -- highest date/id successfully ingested
    etag         TEXT,
    last_modified TEXT,
    notes        TEXT
);

-- Append-only run log, so the site can show freshness and footprint.
CREATE TABLE IF NOT EXISTS runs (
    id            INTEGER PRIMARY KEY,
    started_at    TEXT NOT NULL,
    finished_at   TEXT,
    http_requests INTEGER DEFAULT 0,
    bytes_in      INTEGER DEFAULT 0,
    new_works     INTEGER DEFAULT 0,
    merged_works  INTEGER DEFAULT 0,
    energy_kwh    REAL,
    co2e_g        REAL
);
