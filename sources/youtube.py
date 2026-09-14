"""YouTube Data API v3 - videos.list(chart=mostPopular, videoCategoryId=10) 로
지역별 음악 트렌딩을 가져온다. 문서: https://developers.google.com/youtube/v3/docs/videos/list
"""
import requests

API_URL = "https://www.googleapis.com/youtube/v3/videos"
MUSIC_CATEGORY_ID = "10"


def fetch_trending(api_key: str, region: str = "KR", limit: int = 50) -> list[dict]:
    if not api_key:
        raise ValueError("YOUTUBE_API_KEY가 설정되어 있지 않습니다. .env 파일을 확인하세요.")

    params = {
        "part": "snippet,statistics",
        "chart": "mostPopular",
        "videoCategoryId": MUSIC_CATEGORY_ID,
        "regionCode": region,
        "maxResults": min(limit, 50),
        "key": api_key,
    }
    resp = requests.get(API_URL, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    items = []
    for rank, item in enumerate(data.get("items", []), start=1):
        snippet = item.get("snippet", {})
        stats = item.get("statistics", {})
        items.append({
            "source": "youtube",
            "region": region,
            "rank": rank,
            "raw_title": snippet.get("title", ""),
            "channel_title": snippet.get("channelTitle", ""),
            "published_at": snippet.get("publishedAt", ""),
            "view_count": int(stats.get("viewCount", 0) or 0),
            "video_id": item.get("id", ""),
            "url": f"https://youtu.be/{item.get('id', '')}",
        })
    return items
