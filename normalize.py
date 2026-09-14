"""소스마다 제목·아티스트 표기가 달라서, 비교 가능한 형태로 정규화하는 모듈."""
import re
from difflib import SequenceMatcher

# 제목에서 흔히 붙는 잡음성 표현들 (대소문자 무시하고 제거)
NOISE_PATTERNS = [
    r"\(official\s*(music\s*)?video\)",
    r"\(official\s*audio\)",
    r"\(official\s*lyric\s*video\)",
    r"\(lyrics?\)",
    r"\(m/?v\)",
    r"\(audio\)",
    r"\(visualizer\)",
    r"\(4k\)",
    r"\[.*?\]",
    r"\bofficial\s*(music\s*)?video\b",
    r"\bofficial\s*audio\b",
    r"\bmv\b",
    r"\blyrics?\b",
]

FEAT_PATTERN = re.compile(r"\b(feat\.?|featuring|ft\.?)\b.*", re.IGNORECASE)
SPLIT_DELIMS = [" - ", " – ", " — ", " | "]


def strip_noise(text: str) -> str:
    result = text
    for pattern in NOISE_PATTERNS:
        result = re.sub(pattern, " ", result, flags=re.IGNORECASE)
    return result


TOPIC_SUFFIX_PATTERN = re.compile(r"\s*-\s*topic\s*$", re.IGNORECASE)


def strip_topic_suffix(artist: str) -> str:
    """유튜브 자동 생성 공식 오디오 채널은 이름 끝에 '- Topic'이 붙는다.
    이건 채널 네이밍 규칙일 뿐 아티스트 이름의 일부가 아니므로 제거한다."""
    return TOPIC_SUFFIX_PATTERN.sub("", artist).strip()


DERIVATIVE_KEYWORDS = [
    "reaction", "reacts to",
    "cover", "acoustic cover", "piano cover", "guitar cover", "dance cover",
    "sped up", "speed up", "slowed", "slowed + reverb", "slowed and reverb",
    "nightcore", "8d audio", "karaoke", "instrumental", "type beat",
    "audio visualizer", "tiktok remix", "fan edit",
]


def is_derivative_content(title: str) -> bool:
    """리액션 영상, 팬메이드 커버, 배속/피치 변형(스페드업·슬로우드) 등
    원곡이 아닌 파생 콘텐츠로 보이는 제목이면 True를 반환한다."""
    lowered = (title or "").lower()
    return any(kw in lowered for kw in DERIVATIVE_KEYWORDS)


def matches_watchlist(artist: str, watchlist: list[str], threshold: float = 0.85) -> bool:
    """워치리스트에 있는 아티스트 이름과 (표기가 살짝 달라도) 일치하는지 확인한다."""
    norm_artist = normalize_text(artist)
    if not norm_artist:
        return False
    for name in watchlist:
        norm_name = normalize_text(name)
        if not norm_name:
            continue
        if norm_name == norm_artist or norm_name in norm_artist or norm_artist in norm_name:
            return True
        if similarity(norm_artist, norm_name) >= threshold:
            return True
    return False


def contains_hangul(text: str) -> bool:
    """제목/아티스트명에 한글이 포함돼 있는지 확인한다 (해외 곡만 걸러볼 때 사용)."""
    return bool(re.search(r"[가-힣]", text or ""))


def normalize_text(text: str) -> str:
    """비교용으로 대소문자, 특수문자, 공백을 정리한 문자열을 반환한다."""
    if not text:
        return ""
    text = strip_noise(text)
    text = FEAT_PATTERN.sub("", text)
    text = text.lower()
    text = re.sub(r"[^\w\s가-힣]", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def guess_artist_title(raw_title: str, fallback_artist: str = "") -> tuple[str, str]:
    """유튜브처럼 '아티스트 - 제목' 형태로 합쳐진 문자열에서 아티스트/제목을 분리 시도.
    구분자가 없으면 채널명(fallback_artist)을 아티스트로 사용한다."""
    cleaned = strip_noise(raw_title).strip()
    for delim in SPLIT_DELIMS:
        if delim in cleaned:
            left, right = cleaned.split(delim, 1)
            # 보통 왼쪽이 아티스트, 오른쪽이 제목인 경우가 많다.
            return strip_topic_suffix(left.strip()), right.strip()
    return strip_topic_suffix(fallback_artist.strip()), cleaned


def match_key(artist: str, title: str) -> str:
    """1차 매칭용 키. 완전히 같은 곡이면 이 값도 같아야 이상적이다."""
    return f"{normalize_text(artist)}::{normalize_text(title)}"


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def is_same_song(item_a: dict, item_b: dict, threshold: float) -> bool:
    """두 아이템이 같은 곡인지 판단한다.
    둘 다 MBID가 있으면 그 값이 일치하는지로 확실하게 판단하고,
    하나라도 MBID가 없으면(조회 실패/미조회) 제목·아티스트 유사도로 대체한다."""
    mbid_a = item_a.get("mbid")
    mbid_b = item_b.get("mbid")
    if mbid_a and mbid_b:
        return mbid_a == mbid_b

    # 제목 유사도와 아티스트 유사도를 함께 봐서 같은 곡인지 판단.
    title_sim = similarity(normalize_text(item_a["title"]), normalize_text(item_b["title"]))
    artist_sim = similarity(normalize_text(item_a["artist"]), normalize_text(item_b["artist"]))
    # 아티스트가 너무 다르면(예: 전혀 다른 사람) 제목만 비슷해도 다른 곡으로 취급
    if artist_sim < 0.4:
        return False
    return title_sim >= threshold
