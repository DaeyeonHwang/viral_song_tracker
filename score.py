"""여러 소스에서 모은 곡 목록을 같은 곡끼리 묶고(clustering),
소스별 가중치 + 순위를 반영해 최종 '바이럴 스코어'를 계산한다."""
from normalize import is_same_song, match_key, normalize_text


def _rank_score(rank: int, total: int) -> float:
    """1위에 가까울수록 1.0에 가깝고, 꼴찌에 가까울수록 0에 가까운 점수."""
    if total <= 0:
        return 0.0
    return max(0.0, (total - rank + 1) / total)


def cluster_songs(items: list[dict], threshold: float) -> list[list[dict]]:
    """단순 그리디 클러스터링: 기존 클러스터의 대표곡과 비교해 같은 곡이면 합친다.
    개인용 스케일(소스당 수십 곡)에서는 이 정도로 충분히 빠르고 정확하다."""
    clusters: list[list[dict]] = []
    for item in items:
        placed = False
        for cluster in clusters:
            if is_same_song(item, cluster[0], threshold):
                cluster.append(item)
                placed = True
                break
        if not placed:
            clusters.append([item])
    return clusters


def score_songs(items_by_source: dict, weights: dict, threshold: float) -> list[dict]:
    """items_by_source: {"youtube": [...], "lastfm": [...]} 형태.
    각 아이템은 artist, title, rank, url 키를 가지고 있어야 한다."""
    max_rank_by_source = {src: len(lst) for src, lst in items_by_source.items()}

    flat_items = []
    for source, lst in items_by_source.items():
        for it in lst:
            flat_items.append({**it, "source": source})

    clusters = cluster_songs(flat_items, threshold)

    results = []
    for cluster in clusters:
        total_score = 0.0
        sources_seen = {}
        best_url = ""
        published_candidates = []
        for it in cluster:
            src = it["source"]
            rs = _rank_score(it["rank"], max_rank_by_source.get(src, 1))
            weighted = rs * weights.get(src, 0.5)
            total_score += weighted
            # 소스당 가장 좋은(순위가 높은) 항목 정보를 대표값으로 남긴다
            if src not in sources_seen or it["rank"] < sources_seen[src]["rank"]:
                sources_seen[src] = it
            if not best_url and it.get("url"):
                best_url = it["url"]
            if it.get("published_at"):
                published_candidates.append(it["published_at"])

        # 여러 소스에 동시에 등장할수록 보너스 (진짜 '크로스 플랫폼 바이럴'에 가점)
        source_count = len(sources_seen)
        if source_count > 1:
            total_score *= 1 + 0.25 * (source_count - 1)

        representative = cluster[0]
        results.append({
            "norm_key": match_key(representative["artist"], representative["title"]),
            "artist": representative["artist"],
            "title": representative["title"],
            "score": round(total_score, 4),
            "source_count": source_count,
            "sources": {
                src: {"rank": it["rank"], "url": it.get("url", "")}
                for src, it in sources_seen.items()
            },
            "best_url": best_url,
            # 같은 곡이 여러 번 업로드됐을 수 있으니 가장 이른(원본에 가까운) 날짜를 쓴다
            "published_at": min(published_candidates) if published_candidates else "",
        })

    results.sort(key=lambda r: r["score"], reverse=True)
    return results
