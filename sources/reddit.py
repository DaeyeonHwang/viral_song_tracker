"""Reddit에는 '인기곡 차트'가 없으므로, 독립된 소스가 아니라 이미
YouTube/Last.fm에서 찾은 곡이 최근 특정 서브레딧들에서 얼마나 언급되고 있는지
세어보는 보조 신호로만 쓴다.

2026년 5월 28일부터 Reddit이 비인증 .json 요청을 차단했다(HTTP 403). 그래서
REDDIT_CLIENT_ID/REDDIT_CLIENT_SECRET이 .env에 설정돼 있으면 정식 OAuth
(client_credentials, 로그인 불필요)로 시도하고, 없으면 예전 방식(비인증)을
시도는 하되 - 대부분 막혀 있을 것이므로 - 실패를 조용히 숨기지 않고 명확한
이유와 함께 건너뛴다."""
import time

import requests

USER_AGENT = "python:viral-song-tracker:v1.0 (personal use script)"
TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
UNAUTH_SEARCH_URL = "https://www.reddit.com/r/{subs}/search.json"
OAUTH_SEARCH_URL = "https://oauth.reddit.com/r/{subs}/search"
REQUEST_INTERVAL = 2.0

_last_request_time = 0.0
_access_token = None
_token_expires_at = 0.0


def _throttle() -> None:
    global _last_request_time
    elapsed = time.time() - _last_request_time
    if elapsed < REQUEST_INTERVAL:
        time.sleep(REQUEST_INTERVAL - elapsed)
    _last_request_time = time.time()


def _time_filter(days: int) -> str:
    if days <= 1:
        return "day"
    if days <= 7:
        return "week"
    if days <= 31:
        return "month"
    return "year"


def _get_oauth_token(client_id: str, client_secret: str) -> str:
    """client_credentials 방식(=사용자 로그인 없이 앱 자격증명만으로) 토큰을 발급받는다.
    토큰은 약 1시간 유효하므로 만료 전까지는 캐싱해서 재사용한다."""
    global _access_token, _token_expires_at
    if _access_token and time.time() < _token_expires_at:
        return _access_token

    auth = requests.auth.HTTPBasicAuth(client_id, client_secret)
    resp = requests.post(
        TOKEN_URL,
        auth=auth,
        data={"grant_type": "client_credentials"},
        headers={"User-Agent": USER_AGENT},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    _access_token = data["access_token"]
    _token_expires_at = time.time() + data.get("expires_in", 3600) - 60
    return _access_token


def _search(combined_subs: str, params: dict, client_id: str, client_secret: str):
    """OAuth 자격증명이 있으면 정식 API로, 없으면 예전 비인증 경로로 요청한다."""
    if client_id and client_secret:
        token = _get_oauth_token(client_id, client_secret)
        url = OAUTH_SEARCH_URL.format(subs=combined_subs)
        headers = {"User-Agent": USER_AGENT, "Authorization": f"bearer {token}"}
    else:
        url = UNAUTH_SEARCH_URL.format(subs=combined_subs)
        headers = {"User-Agent": USER_AGENT}
    return requests.get(url, params=params, headers=headers, timeout=10)


def check_access(client_id: str = "", client_secret: str = "") -> tuple[bool, str]:
    """본격적으로 여러 곡을 조회하기 전에, 가벼운 요청 한 번으로 실제 접근이
    되는지부터 확인한다. 막혀 있으면 이유를 설명하고 전체 조회를 건너뛰게 한다."""
    _throttle()
    try:
        resp = _search("music", {"q": "test", "limit": 1}, client_id, client_secret)
    except requests.RequestException as e:
        return False, f"Reddit 연결 실패: {e}"

    if resp.status_code == 403:
        if client_id and client_secret:
            return False, "Reddit이 이 앱의 OAuth 접근을 거부했습니다 (403). 앱이 승인됐는지 확인하세요."
        return False, (
            "Reddit이 2026년 5월부터 비인증(.json) 요청을 차단하고 있습니다 (HTTP 403). "
            "REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET을 .env에 넣으면 정식 API로 시도합니다."
        )
    if resp.status_code == 401:
        return False, "Reddit 인증 실패 (401). REDDIT_CLIENT_ID/REDDIT_CLIENT_SECRET 값을 확인하세요."
    if resp.status_code >= 400:
        return False, f"Reddit 요청 실패 (HTTP {resp.status_code})"

    try:
        resp.json()
    except ValueError:
        return False, "Reddit 응답을 해석할 수 없습니다 (접근이 막혔을 가능성이 있습니다)."

    return True, "ok"


def count_mentions(
    artist: str, title: str, subreddits: list[str], days: int = 7,
    client_id: str = "", client_secret: str = "",
) -> int:
    """subreddits를 하나로 묶어, 최근 `days`일 동안 이 곡을 언급한 게시물 수를 센다.
    실패하면 조용히 0을 반환한다 (전체 여부는 check_access로 미리 확인했다는 전제)."""
    if not artist or not title or not subreddits:
        return 0

    combined = "+".join(subreddits)
    query = f'"{artist}" "{title}"'
    params = {"q": query, "restrict_sr": 1, "sort": "new", "t": _time_filter(days), "limit": 25}

    _throttle()
    try:
        resp = _search(combined, params, client_id, client_secret)
        if resp.status_code == 429:
            time.sleep(5)
            resp = _search(combined, params, client_id, client_secret)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError):
        return 0

    return len(data.get("data", {}).get("children", []))
