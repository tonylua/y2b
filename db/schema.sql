DROP TABLE IF EXISTS videos;

CREATE TABLE videos (
    id TEXT PRIMARY KEY NOT NULL,
    user TEXT PRIMARY KEY NOT NULL,
    created TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    title TEXT NOT NULL,
    desc TEXT,
    save_path TEXT NOT NULL,
    save_srt TEXT,
    save_cover,
    origin_url TEXT NOT NULL,
    size INTEGER,
    tid INTEGER,
    tags TEXT,
    uploaded BOOLEAN DEFAULT FALSE
);