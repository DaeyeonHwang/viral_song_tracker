"""MusicBrainz에서 (아티스트, 곡명)에 해당하는 recording의 MBID를 찾는다.
문자열 유사도만으로는 다른 곡을 같은 곡으로 잘못 합치거나, 표기가 많이 다른
같은 곡을 놓칠 수 있는데, 공식 식별자(MBID)가 일치하면 확실하게 같은 곡으로
판단할 수 있다. 조회에 실패하거나 결과가 불확실하면 None을 반환하고,
이 경우 score.py가 기존 문자열 유사도 매칭으로 대체한다.

문서: https://musicbrainz.org/doc/MusicBrainz_API
"""
import time

import requests

API_URL = "https://musicbrainz.org/ws/2/recording"
# MusicBrainz는 User-Agent에 앱 이름/버전/연락처를 넣도록 권장한다 (없으면 차단될 수 있음)
USER_AGENT = "ViralSongTracker/1.0 (personal use script)"
MIN_SCORE = 85  # MusicBrainz가 매기는 검색 신뢰도(0~100). 이 이상만 신뢰한다.
REQUEST_INTERVAL = 1.05  # 초당 1건 제한을 지키기 위한 최소 호출 간격(초)

_last_request_time = 0.0


def _throttle() -> None:
    global _last_request_time
    elapsed = time.time() - _last_request_time
    if elapsed < REQUEST_INTERVAL:
        time.sleep(REQUEST_INTERVAL - elapsed)
    _last_request_time = time.time()


def lookup_mbid(artist: str, title: str) -> str | None:
    """(artist, title)에 가장 가까운 recording의 MBID를 반환한다.
    실패/결과없음/신뢰도 낮음이면 None."""
    if not artist or not title:
        return None

    query = f'artist:"{artist}" AND recording:"{title}"'
    params = {"query": query, "fmt": "json", "limit": 1}

    _throttle()
    try:
        resp = requests.get(
            API_URL, params=params, headers={"User-Agent": USER_AGENT}, timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError):
        # 네트워크 오류, 타임아웃, JSON 파싱 실패 등 - 조용히 포기하고 폴백시킨다
        return None

    recordings = data.get("recordings") or []
    if not recordings:
        return None

    top = recordings[0]
    if top.get("score", 0) < MIN_SCORE:
        return None
    return top.get("id")
