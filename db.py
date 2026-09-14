"""SQLite에 수집 원본과 스코어링 결과를 날짜별 스냅샷으로 저장한다.
파일 하나(tracker.db)에 전부 들어있어서 백업/이동이 쉽다."""
import json
import sqlite3
from contextlib import contextmanager

from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS raw_items (
    date TEXT NOT NULL,
    source TEXT NOT NULL,
    region TEXT,
    rank INTEGER,
    artist TEXT,
    title TEXT,
    url TEXT
);

CREATE TABLE IF NOT EXISTS song_scores (
    date TEXT NOT NULL,
    norm_key TEXT NOT NULL,
    artist TEXT,
    title TEXT,
    score REAL,
    source_count INTEGER,
    sources TEXT,
    best_url TEXT,
    published_at TEXT,
    tag TEXT,
    PRIMARY KEY (date, norm_key)
);

CREATE TABLE IF NOT EXISTS mb_cache (
    norm_key TEXT PRIMARY KEY,
    mbid TEXT,
    checked_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_raw_items_date ON raw_items(date);
CREATE INDEX IF NOT EXISTS idx_song_scores_date ON song_scores(date);
"""


@contextmanager
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(SCHEMA)
        _migrate_song_scores(conn)


def _migrate_song_scores(conn: sqlite3.Connection) -> None:
    """이 업데이트 이전에 만들어진 tracker.db에는 published_at/tag 컬럼이
    없을 수 있으므로, 없으면 추가해준다 (기존 데이터는 유지됨)."""
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(song_scores)")}
    if "published_at" not in existing:
        conn.execute("ALTER TABLE song_scores ADD COLUMN published_at TEXT")
    if "tag" not in existing:
        conn.execute("ALTER TABLE song_scores ADD COLUMN tag TEXT")


def clear_date(date: str) -> None:
    """해당 날짜의 raw_items/song_scores를 모두 지운다.
    같은 날짜에 여러 번 실행해도(예: 데모 테스트 후 실제 실행) 이전 실행의
    데이터가 새 데이터와 섞이지 않도록, 저장 전에 항상 그날 데이터를 초기화한다."""
    with get_connection() as conn:
        conn.execute("DELETE FROM raw_items WHERE date = ?", (date,))
        conn.execute("DELETE FROM song_scores WHERE date = ?", (date,))


def save_raw_items(date: str, items: list[dict]) -> None:
    with get_connection() as conn:
        conn.executemany(
            "INSERT INTO raw_items (date, source, region, rank, artist, title, url) "
            "VALUES (:date, :source, :region, :rank, :artist, :title, :url)",
            [
                {
                    "date": date,
                    "source": it["source"],
                    "region": it.get("region", ""),
                    "rank": it.get("rank", 0),
                    "artist": it.get("artist", ""),
                    "title": it.get("title", ""),
                    "url": it.get("url", ""),
                }
                for it in items
            ],
        )


def save_song_scores(date: str, songs: list[dict]) -> None:
    with get_connection() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO song_scores "
            "(date, norm_key, artist, title, score, source_count, sources, best_url, published_at, tag) "
            "VALUES (:date, :norm_key, :artist, :title, :score, :source_count, :sources, :best_url, :published_at, :tag)",
            [
                {
                    "date": date,
                    "norm_key": s["norm_key"],
                    "artist": s["artist"],
                    "title": s["title"],
                    "score": s["score"],
                    "source_count": s["source_count"],
                    "sources": json.dumps(s["sources"], ensure_ascii=False),
                    "best_url": s.get("best_url", ""),
                    "published_at": s.get("published_at", ""),
                    "tag": s.get("tag", ""),
                }
                for s in songs
            ],
        )


def get_scores_for_date(date: str) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM song_scores WHERE date = ? ORDER BY score DESC", (date,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_cached_mbid(norm_key: str):
    """캐시 조회 결과. 반환값 의미가 세 가지로 나뉜다:
    None      -> 아직 한 번도 조회한 적 없음 (MusicBrainz에 물어봐야 함)
    ""        -> 이미 조회했는데 못 찾았음 (다시 물어보지 않음)
    "mbid..." -> 찾은 MBID"""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT mbid FROM mb_cache WHERE norm_key = ?", (norm_key,)
        ).fetchone()
        return row["mbid"] if row else None


def set_cached_mbid(norm_key: str, mbid: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO mb_cache (norm_key, mbid, checked_at) VALUES (?, ?, datetime('now'))",
            (norm_key, mbid or ""),
        )


def get_recent_dates(end_date: str, count: int) -> list[str]:
    """end_date 이하로 저장된 날짜들 중 최신 count개를 오래된 순으로 반환한다
    (매일 안 돌려도 실제 저장된 날짜 기준으로 동작한다)."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT DISTINCT date FROM song_scores WHERE date <= ? ORDER BY date DESC LIMIT ?",
            (end_date, count),
        ).fetchall()
        return list(reversed([r["date"] for r in rows]))


def get_previous_rank_map(date: str) -> dict:
    """해당 날짜보다 이전의 가장 최근 스냅샷에서 곡별 순위를 가져온다.
    (전일 대비 순위 변화를 보여주기 위함)"""
    with get_connection() as conn:
        prev_date_row = conn.execute(
            "SELECT DISTINCT date FROM song_scores WHERE date < ? ORDER BY date DESC LIMIT 1",
            (date,),
        ).fetchone()
        if not prev_date_row:
            return {}
        prev_date = prev_date_row["date"]
        rows = conn.execute(
            "SELECT norm_key, score FROM song_scores WHERE date = ? ORDER BY score DESC",
            (prev_date,),
        ).fetchall()
        return {row["norm_key"]: idx + 1 for idx, row in enumerate(rows)}
