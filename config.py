"""공통 설정: .env 파일을 읽어 환경변수로 로드하고, 소스별 가중치를 정의한다."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
DB_PATH = BASE_DIR / "tracker.db"
REPORTS_DIR = BASE_DIR / "reports"


def load_env_file(path: Path = ENV_PATH) -> None:
    """python-dotenv 없이 .env 파일을 읽어 os.environ에 채워 넣는다.
    이미 설정된 환경변수는 덮어쓰지 않는다.
    - 여러 인코딩(UTF-8 BOM, cp949=한국어 윈도우 기본, UTF-8)을 순서대로 시도해서
      메모장 등에서 어떤 인코딩으로 저장했든 최대한 깨지지 않게 읽는다.
    - 값 양쪽에 따옴표(' 또는 ")를 감싸서 적었어도 벗겨준다."""
    if not path.exists():
        return

    raw_bytes = path.read_bytes()
    text = None
    for encoding in ("utf-8-sig", "cp949", "utf-8"):
        try:
            text = raw_bytes.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        text = raw_bytes.decode("utf-8", errors="replace")
        print(
            "경고: .env 파일의 인코딩을 확실히 알 수 없어 일부 문자가 깨졌을 수 있습니다. "
            "메모장/VS Code에서 '인코딩: UTF-8'로 다시 저장해보세요. "
            "(단, key=value 형태의 줄은 대부분 ASCII라 값 자체는 보통 문제없이 읽힙니다.)"
        )

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value


load_env_file()

YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "")
LASTFM_API_KEY = os.environ.get("LASTFM_API_KEY", "")
# 첫 번째 값만 실제로 사용된다 (main.py 참고). 해외 차트를 보고 싶으면 US, GB 등으로.
YOUTUBE_REGIONS = [r.strip() for r in os.environ.get("YOUTUBE_REGIONS", "US").split(",") if r.strip()]
# 비워두면 Last.fm 글로벌 차트(chart.gettoptracks)를 사용한다.
LASTFM_COUNTRY = os.environ.get("LASTFM_COUNTRY", "").strip()
# true면 제목/아티스트에 한글이 포함된 곡을 결과에서 제외한다 (해외 곡만 보고 싶을 때).
EXCLUDE_KOREAN = os.environ.get("EXCLUDE_KOREAN", "true").strip().lower() in ("1", "true", "yes")
# 유튜브 업로드일이 이 값(일) 이내면 '신곡', 아니면 '역주행'으로 표시한다.
RECENT_SONG_DAYS = int(os.environ.get("RECENT_SONG_DAYS", "90"))
# true면 MusicBrainz로 곡을 식별해 더 정확하게 매칭한다 (첫 실행은 느릴 수 있음, 이후엔 캐싱됨).
USE_MUSICBRAINZ = os.environ.get("USE_MUSICBRAINZ", "true").strip().lower() in ("1", "true", "yes")
# true면 리액션/커버/스페드업 등 파생 콘텐츠로 보이는 제목을 결과에서 제외한다.
FILTER_DERIVATIVE = os.environ.get("FILTER_DERIVATIVE", "true").strip().lower() in ("1", "true", "yes")
# true면 Reddit에서 곡 언급량을 조회해 보조 점수로 반영 (--demo에서는 자동으로 꺼짐).
USE_REDDIT = os.environ.get("USE_REDDIT", "true").strip().lower() in ("1", "true", "yes")
# Reddit 공식 OAuth 앱을 승인받았다면 여기 채워 넣으세요 (비워두면 비인증 방식을 시도합니다.
# 단, Reddit이 2026년 5월부터 비인증 요청을 막고 있어 대부분 실패할 수 있습니다).
REDDIT_CLIENT_ID = os.environ.get("REDDIT_CLIENT_ID", "").strip()
REDDIT_CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET", "").strip()
REDDIT_SUBREDDITS = [s.strip() for s in os.environ.get(
    "REDDIT_SUBREDDITS", "music,popheads,hiphopheads,indieheads"
).split(",") if s.strip()]
REDDIT_LOOKBACK_DAYS = int(os.environ.get("REDDIT_LOOKBACK_DAYS", "7"))
REDDIT_WEIGHT = float(os.environ.get("REDDIT_WEIGHT", "0.3"))
# 상위 몇 곡까지만 Reddit 조회를 할지 (많을수록 정확하지만 실행 시간이 늘어남)
REDDIT_CHECK_TOP_N = int(os.environ.get("REDDIT_CHECK_TOP_N", "30"))

# 관심 아티스트 목록 (콤마 구분). 이 아티스트의 곡이 발견되면 순위와 상관없이
# 리포트 맨 위에 따로 보여준다.
WATCHLIST_ARTISTS = [s.strip() for s in os.environ.get("WATCHLIST_ARTISTS", "").split(",") if s.strip()]

# 장르 필터: 둘 다 비워두면 필터링 안 함. GENRE_INCLUDE에 값이 있으면 그 장르만 남기고,
# GENRE_EXCLUDE에 있는 장르는 항상 제외한다 (Last.fm 태그 기준, 소문자로 비교).
GENRE_INCLUDE = [g.strip().lower() for g in os.environ.get("GENRE_INCLUDE", "").split(",") if g.strip()]
GENRE_EXCLUDE = [g.strip().lower() for g in os.environ.get("GENRE_EXCLUDE", "").split(",") if g.strip()]
# 상위 몇 곡까지만 장르 태그를 조회할지
GENRE_CHECK_TOP_N = int(os.environ.get("GENRE_CHECK_TOP_N", "40"))

# 소스별 신뢰 가중치. 값이 클수록 최종 스코어에 더 크게 반영된다.
# 취향에 따라 자유롭게 조정하면 된다.
SOURCE_WEIGHTS = {
    "youtube": 1.0,
    "lastfm": 0.8,
}

# 같은 곡으로 판단할 정규화 문자열 유사도 임계값 (0~1)
MATCH_THRESHOLD = 0.82
