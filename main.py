"""바이럴 음악 트래커 실행 스크립트.

사용법:
    python main.py --demo          # API 키 없이 샘플 데이터로 파이프라인 테스트
    python main.py                 # 실제 YouTube/Last.fm API 호출
    python main.py --top 10        # 리포트에 담을 곡 수 조정
"""
import argparse
import json
import math
from datetime import date as date_cls
from pathlib import Path

import config
import musicbrainz
from db import clear_date, get_cached_mbid, init_db, save_raw_items, save_song_scores, set_cached_mbid
from normalize import contains_hangul, guess_artist_title, is_derivative_content, match_key, matches_watchlist
from recency import classify as classify_recency
from report import save_report, save_weekly_report
from score import score_songs
from sources import lastfm, reddit, youtube

SAMPLE_DIR = Path(__file__).resolve().parent / "sample_data"


def load_demo_items() -> dict:
    yt_raw = json.loads((SAMPLE_DIR / "youtube_demo.json").read_text(encoding="utf-8"))
    lf_raw = json.loads((SAMPLE_DIR / "lastfm_demo.json").read_text(encoding="utf-8"))
    return {"youtube_raw": yt_raw, "lastfm": lf_raw}


def fetch_live_items() -> dict:
    region = config.YOUTUBE_REGIONS[0] if config.YOUTUBE_REGIONS else "KR"
    yt_raw = youtube.fetch_trending(config.YOUTUBE_API_KEY, region=region, limit=50)
    lf = lastfm.fetch_top_tracks(config.LASTFM_API_KEY, country=config.LASTFM_COUNTRY, limit=50)
    return {"youtube_raw": yt_raw, "lastfm": lf}


def unify_youtube(yt_raw: list[dict]) -> list[dict]:
    """유튜브는 제목이 '아티스트 - 제목' 식으로 뭉쳐 있으므로 분리해서
    artist/title 필드를 채워준다."""
    unified = []
    for it in yt_raw:
        artist, title = guess_artist_title(it["raw_title"], it.get("channel_title", ""))
        unified.append({
            "source": "youtube",
            "region": it.get("region", ""),
            "rank": it["rank"],
            "artist": artist or it.get("channel_title", "Unknown"),
            "title": title or it["raw_title"],
            "url": it.get("url", ""),
            "published_at": it.get("published_at", ""),
        })
    return unified


def filter_out_korean(items: list[dict]) -> list[dict]:
    """제목이나 아티스트명에 한글이 포함된 곡을 제외한다 (해외 곡만 보고 싶을 때 사용)."""
    return [it for it in items if not (contains_hangul(it["title"]) or contains_hangul(it["artist"]))]


def filter_out_derivative(items: list[dict]) -> list[dict]:
    """리액션/커버/스페드업 등 팬메이드 파생 콘텐츠로 보이는 항목을 제외한다."""
    return [it for it in items if not is_derivative_content(it["title"])]


def resolve_mbids(items: list[dict]) -> None:
    """각 아이템에 MusicBrainz MBID를 찾아 item['mbid']에 채워 넣는다 (제자리 수정).
    이미 캐시에 있으면 네트워크 호출 없이 바로 쓰고, 없을 때만 새로 조회해서 캐싱한다."""
    cache_hits = 0
    lookups = 0
    for it in items:
        norm_key = match_key(it["artist"], it["title"])
        cached = get_cached_mbid(norm_key)
        if cached is not None:
            it["mbid"] = cached or None
            cache_hits += 1
            continue
        mbid = musicbrainz.lookup_mbid(it["artist"], it["title"])
        set_cached_mbid(norm_key, mbid or "")
        it["mbid"] = mbid
        lookups += 1
    if items:
        print(f"MusicBrainz 조회: 캐시 재사용 {cache_hits}건, 새로 조회 {lookups}건")


def apply_reddit_signal(scored: list[dict]) -> None:
    """이미 계산된 상위 곡들에 대해서만 Reddit 언급량을 조회해 점수에 보너스를 더한다.
    (Reddit은 자체 차트가 없어서 독립 소스가 아니라 검증/보조 신호로만 쓴다.)
    본격 조회 전에 접근이 실제로 되는지부터 확인해서, 막혀 있으면 이유를 명확히
    보여주고 조용히 넘어가지 않는다. 언급이 많을수록 유리하되, 한 곡이 스코어를
    독식하지 않도록 log 스케일로 더한다. 보너스 반영 후 순서가 바뀔 수 있어 재정렬한다."""
    ok, message = reddit.check_access(config.REDDIT_CLIENT_ID, config.REDDIT_CLIENT_SECRET)
    if not ok:
        print(f"Reddit 언급량 조회 건너뜀: {message}")
        return

    checked = 0
    for song in scored[: config.REDDIT_CHECK_TOP_N]:
        mentions = reddit.count_mentions(
            song["artist"], song["title"], config.REDDIT_SUBREDDITS, config.REDDIT_LOOKBACK_DAYS,
            config.REDDIT_CLIENT_ID, config.REDDIT_CLIENT_SECRET,
        )
        song["reddit_mentions"] = mentions
        checked += 1
        if mentions > 0:
            song["score"] = round(song["score"] + config.REDDIT_WEIGHT * math.log1p(mentions), 4)
            song["sources"]["reddit"] = {"mentions": mentions}
    if checked:
        print(f"Reddit 언급량 조회: 상위 {checked}곡 확인")
    scored.sort(key=lambda s: s["score"], reverse=True)


def apply_genre_filter(scored: list[dict]) -> list[dict]:
    """GENRE_INCLUDE/GENRE_EXCLUDE 설정에 따라 곡을 거른다. 태그는 Last.fm에서
    가져오며, 태그가 아예 없는(신곡이라 아직 안 붙었거나 조회 실패) 곡은
    include 필터가 켜져 있어도 무작정 빼지 않고 일단 통과시킨다 (모르는 걸
    틀렸다고 판단하지 않기 위함)."""
    if not config.GENRE_INCLUDE and not config.GENRE_EXCLUDE:
        return scored

    include_set = set(config.GENRE_INCLUDE)
    exclude_set = set(config.GENRE_EXCLUDE)
    kept = []
    checked = 0
    for song in scored:
        if checked >= config.GENRE_CHECK_TOP_N:
            kept.append(song)  # 확인 한도를 넘은 곡은 필터링하지 않고 그대로 둔다
            continue
        tags = lastfm.fetch_top_tags(config.LASTFM_API_KEY, song["artist"], song["title"])
        checked += 1
        song["genres"] = tags
        tag_set = set(tags)

        if exclude_set and tag_set & exclude_set:
            continue
        if include_set and tags and not (tag_set & include_set):
            continue
        kept.append(song)

    if checked:
        print(f"장르 태그 조회: {checked}곡 확인, {len(scored) - len(kept)}곡 제외")
    return kept


def run(use_demo: bool, top_n: int, run_date: str) -> None:
    init_db()
    # 같은 날짜에 이전에 실행한 기록(특히 --demo 테스트)이 남아있으면 새 결과와
    # 섞이므로, 저장하기 전에 오늘 날짜 데이터를 항상 초기화한다.
    clear_date(run_date)

    raw = load_demo_items() if use_demo else fetch_live_items()
    youtube_items = unify_youtube(raw["youtube_raw"])
    lastfm_items = raw["lastfm"]

    if config.EXCLUDE_KOREAN:
        youtube_items = filter_out_korean(youtube_items)
        lastfm_items = filter_out_korean(lastfm_items)

    if config.FILTER_DERIVATIVE:
        youtube_items = filter_out_derivative(youtube_items)
        lastfm_items = filter_out_derivative(lastfm_items)

    if config.USE_MUSICBRAINZ and not use_demo:
        resolve_mbids(youtube_items)
        resolve_mbids(lastfm_items)

    items_by_source = {"youtube": youtube_items, "lastfm": lastfm_items}

    # 원본 수집 데이터도 그대로 저장해두면 나중에 소스별로 다시 분석할 수 있다
    for source_items in items_by_source.values():
        save_raw_items(run_date, source_items)

    scored = score_songs(items_by_source, config.SOURCE_WEIGHTS, config.MATCH_THRESHOLD)
    for song in scored:
        song["tag"] = classify_recency(song.get("published_at", ""), run_date, config.RECENT_SONG_DAYS)

    # 관심 아티스트 소식은 필터링 전 시점에서 미리 뽑아둔다 (장르 필터에 걸러져도
    # 리포트 상단 별도 섹션에는 항상 나오게 하기 위함). 오늘 수집된 트렌딩
    # 목록 안에 있는 곡만 잡을 수 있다는 한계는 있다 - 그 아티스트가 아예
    # 오늘 트렌딩에 없으면 워치리스트에도 뜨지 않는다.
    watchlist_songs = [
        s for s in scored if config.WATCHLIST_ARTISTS and matches_watchlist(s["artist"], config.WATCHLIST_ARTISTS)
    ]
    if watchlist_songs:
        print(f"관심 아티스트 소식: {len(watchlist_songs)}건 발견")

    if (config.GENRE_INCLUDE or config.GENRE_EXCLUDE) and not use_demo:
        scored = apply_genre_filter(scored)

    if config.USE_REDDIT and not use_demo:
        apply_reddit_signal(scored)

    save_song_scores(run_date, scored)

    report_path = save_report(run_date, top_n=top_n, watchlist_songs=watchlist_songs)

    print(f"[{run_date}] 수집 완료: youtube {len(youtube_items)}곡, lastfm {len(lastfm_items)}곡")
    print(f"교차 매칭 후 고유 곡 수: {len(scored)}")
    print(f"리포트 저장 위치: {report_path}")
    print()
    print(report_path.read_text(encoding="utf-8"))


def run_weekly(end_date: str, days: int, top_n: int) -> None:
    """새로 데이터를 수집하지 않고, 이미 저장된 스냅샷만으로 주간 급상승 리포트를 만든다."""
    init_db()
    report_path = save_weekly_report(end_date, days=days, top_n=top_n)
    print(f"주간 리포트 저장 위치: {report_path}")
    print()
    print(report_path.read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(description="여러 소스를 교차 검색해 바이럴 음악을 추적한다.")
    parser.add_argument("--demo", action="store_true", help="API 키 없이 샘플 데이터로 실행")
    parser.add_argument("--top", type=int, default=15, help="리포트에 담을 상위 곡 수")
    parser.add_argument("--date", type=str, default=str(date_cls.today()), help="스냅샷 날짜 (YYYY-MM-DD)")
    parser.add_argument(
        "--weekly", action="store_true",
        help="새로 수집하지 않고, 저장된 데이터로 주간 급상승 리포트만 생성"
    )
    parser.add_argument("--days", type=int, default=7, help="--weekly에서 비교할 기간(일). 기본 7일")
    args = parser.parse_args()

    if args.weekly:
        run_weekly(end_date=args.date, days=args.days, top_n=args.top)
        return

    if not args.demo and not (config.YOUTUBE_API_KEY and config.LASTFM_API_KEY):
        missing = []
        if not config.YOUTUBE_API_KEY:
            missing.append("YOUTUBE_API_KEY")
        if not config.LASTFM_API_KEY:
            missing.append("LASTFM_API_KEY")
        env_status = ".env 파일 있음" if config.ENV_PATH.exists() else ".env 파일 없음(!)"
        raise SystemExit(
            f"다음 키가 비어 있습니다: {', '.join(missing)}\n"
            f"확인한 .env 경로: {config.ENV_PATH} ({env_status})\n"
            f"해당 줄이 정확히 'YOUTUBE_API_KEY=키값' 형태인지, 키 이름에 오타나 공백이 없는지 확인해보세요."
        )

    run(use_demo=args.demo, top_n=args.top, run_date=args.date)


if __name__ == "__main__":
    main()
