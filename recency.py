"""곡이 최근 발매된 신곡인지, 예전 곡이 다시 주목받는 역주행인지 판별한다.
YouTube 영상의 publishedAt(업로드일)을 근사치로 사용한다 - 공식 오디오/뮤직비디오
채널은 보통 발매일에 맞춰 업로드하므로 발매일과 크게 다르지 않다."""
from datetime import datetime, timezone

NEW_SONG = "신곡"
RESURGENCE = "역주행"
UNKNOWN = "정보없음"


def _parse_iso(dt_str: str):
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except ValueError:
        return None


def classify(published_at: str, run_date: str, recent_days: int) -> str:
    """published_at: YouTube publishedAt(ISO8601) 문자열, 없으면 '정보없음'.
    run_date: 'YYYY-MM-DD' 형식의 스냅샷 날짜."""
    published = _parse_iso(published_at)
    if published is None:
        return UNKNOWN
    try:
        run_dt = datetime.strptime(run_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        run_dt = datetime.now(timezone.utc)
    days_since = (run_dt - published).days
    return NEW_SONG if days_since <= recent_days else RESURGENCE
