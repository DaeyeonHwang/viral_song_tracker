"""Last.fm API - chart.getTopTracks(글로벌) 또는 geo.getTopTracks(국가별)로
인기곡 차트를 가져오고, track.getTopTags로 장르 태그도 조회한다.
문서: https://www.last.fm/api
"""
import time

import requests

API_URL = "https://ws.audioscrobbler.com/2.0/"
_TAG_REQUEST_INTERVAL = 0.25  # 장르 태그는 곡 수만큼 호출하니 과도한 트래픽 방지용으로 살짝 텀을 둔다
_last_tag_request_time = 0.0


def fetch_top_tracks(api_key: str, country: str = "", limit: int = 50) -> list[dict]:
    if not api_key:
        raise ValueError("LASTFM_API_KEY가 설정되어 있지 않습니다. .env 파일을 확인하세요.")

    if country:
        method = "geo.gettoptracks"
        params = {"method": method, "country": country, "limit": limit}
    else:
        method = "chart.gettoptracks"
        params = {"method": method, "limit": limit}

    params.update({"api_key": api_key, "format": "json"})
    resp = requests.get(API_URL, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    root_key = "tracks" if country else "tracks"
    raw_tracks = data.get(root_key, {}).get("track", [])

    items = []
    for rank, track in enumerate(raw_tracks, start=1):
        artist = track.get("artist", {})
        artist_name = artist.get("name", "") if isinstance(artist, dict) else str(artist)
        items.append({
            "source": "lastfm",
            "region": country or "global",
            "rank": rank,
            "title": track.get("name", ""),
            "artist": artist_name,
            "playcount": int(track.get("playcount", 0) or 0),
            "published_at": "",  # Last.fm은 발매일 정보를 제공하지 않는다
            "url": track.get("url", ""),
        })
    return items


def fetch_top_tags(api_key: str, artist: str, title: str, limit: int = 5) -> list[str]:
    """곡의 장르/무드 태그(예: 'pop', 'hip hop')를 가져온다. Last.fm 이용자들이
    직접 붙인 태그라 곡마다 정확도가 다를 수 있고, 아주 최신곡은 태그가
    아직 없을 수도 있다. 실패하거나 결과가 없으면 빈 리스트를 반환한다."""
    global _last_tag_request_time
    if not api_key or not artist or not title:
        return []

    elapsed = time.time() - _last_tag_request_time
    if elapsed < _TAG_REQUEST_INTERVAL:
        time.sleep(_TAG_REQUEST_INTERVAL - elapsed)
    _last_tag_request_time = time.time()

    params = {
        "method": "track.gettoptags", "artist": artist, "track": title,
        "api_key": api_key, "format": "json",
    }
    try:
        resp = requests.get(API_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError):
        return []

    raw_tags = data.get("toptags", {}).get("tag", [])
    names = [t.get("name", "").strip().lower() for t in raw_tags if isinstance(t, dict) and t.get("name")]
    return names[:limit]
