DROP TABLE IF EXISTS videos;

CREATE TABLE videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user TEXT NOT NULL,
    created TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    title TEXT NOT NULL,
    desc TEXT,
    subtitle_lang TEXT,
    save_path TEXT NOT NULL,
    save_srt TEXT,
    save_cover TEXT,
    origin_id TEXT NOT NULL,
    origin_url TEXT NOT NULL,
    size INTEGER,
    tid INTEGER,
    tags TEXT,
    status TEXT CHECK(status IN ('pending', 'downloading', 'downloaded', 'uploading', 'uploaded')) DEFAULT 'pending'
);
