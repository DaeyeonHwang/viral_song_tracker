"""당일 스코어 결과를 마크다운 리포트로 저장한다. 전일 스냅샷이 있으면
순위 변화(신규 진입 / 상승 / 하락)도 함께 표시한다."""
import json
from pathlib import Path

from config import REPORTS_DIR
from db import get_previous_rank_map, get_recent_dates, get_scores_for_date


def _rank_change_label(current_rank: int, prev_rank: int | None) -> str:
    if prev_rank is None:
        return "신규"
    diff = prev_rank - current_rank
    if diff > 0:
        return f"▲{diff}"
    if diff < 0:
        return f"▼{abs(diff)}"
    return "-"


def build_report(date: str, top_n: int = 20, watchlist_songs: list[dict] | None = None) -> str:
    scores = get_scores_for_date(date)[:top_n]
    prev_ranks = get_previous_rank_map(date)

    lines = [f"# {date} 바이럴 음악 리포트", ""]

    if watchlist_songs:
        lines.append("## 관심 아티스트 소식")
        lines.append("| 곡 | 아티스트 | 태그 | 등장 소스 | 스코어 |")
        lines.append("|---|---|---|---|---|")
        for row in watchlist_songs:
            sources = ", ".join(row["sources"].keys())
            tag = row.get("tag") or "정보없음"
            lines.append(f"| {row['title']} | {row['artist']} | {tag} | {sources} | {row['score']:.2f} |")
        lines.append("")
        lines.append("## 전체 순위")
        lines.append("")

    if not scores:
        lines.append("해당 날짜에 저장된 데이터가 없습니다.")
        return "\n".join(lines)

    lines.append("| 순위 | 변동 | 곡 | 아티스트 | 태그 | 등장 소스 | 스코어 |")
    lines.append("|---|---|---|---|---|---|---|")
    for idx, row in enumerate(scores, start=1):
        prev_rank = prev_ranks.get(row["norm_key"])
        change = _rank_change_label(idx, prev_rank)
        sources = ", ".join(json.loads(row["sources"]).keys())
        tag = row["tag"] or "정보없음"
        lines.append(
            f"| {idx} | {change} | {row['title']} | {row['artist']} | {tag} | {sources} | {row['score']:.2f} |"
        )

    return "\n".join(lines)


def save_report(date: str, top_n: int = 20, watchlist_songs: list[dict] | None = None) -> Path:
    REPORTS_DIR.mkdir(exist_ok=True)
    content = build_report(date, top_n, watchlist_songs=watchlist_songs)
    path = REPORTS_DIR / f"{date}.md"
    path.write_text(content, encoding="utf-8")
    return path


def build_weekly_report(end_date: str, days: int = 7, top_n: int = 15) -> str:
    """최근 저장된 날짜들 중 최신 `days`개를 비교해서, 그 사이 새로 진입한 곡과
    순위가 가장 많이 오른 곡을 뽑는다. 매일 실행 안 해도 실제 저장된 날짜 기준으로
    동작하므로 하루이틀 걸러도 문제없다."""
    dates = get_recent_dates(end_date, days)
    if len(dates) < 2:
        return (
            f"# {end_date} 기준 주간 급상승 리포트\n\n"
            f"비교할 과거 데이터가 아직 부족합니다 (저장된 날짜 {len(dates)}개). "
            f"스크립트를 며칠 더 실행한 뒤 다시 확인해보세요."
        )

    earliest_date, latest_date = dates[0], dates[-1]
    earliest_scores = get_scores_for_date(earliest_date)
    latest_scores = get_scores_for_date(latest_date)

    earliest_rank = {row["norm_key"]: idx + 1 for idx, row in enumerate(earliest_scores)}
    latest_rank = {row["norm_key"]: idx + 1 for idx, row in enumerate(latest_scores)}

    new_entries = []
    risers = []
    for idx, row in enumerate(latest_scores):
        norm_key = row["norm_key"]
        cur_rank = idx + 1
        prev_rank = earliest_rank.get(norm_key)
        if prev_rank is None:
            new_entries.append((cur_rank, row))
        else:
            climb = prev_rank - cur_rank
            if climb > 0:
                risers.append((climb, prev_rank, cur_rank, row))

    new_entries.sort(key=lambda x: x[0])
    risers.sort(key=lambda x: x[0], reverse=True)

    lines = [f"# {earliest_date} → {latest_date} 주간 급상승 리포트", ""]

    lines.append(f"## 이 기간에 새로 진입한 곡 (상위 {top_n})")
    if new_entries:
        lines.append("| 현재 순위 | 곡 | 아티스트 | 태그 |")
        lines.append("|---|---|---|---|")
        for cur_rank, row in new_entries[:top_n]:
            lines.append(f"| {cur_rank} | {row['title']} | {row['artist']} | {row['tag'] or '정보없음'} |")
    else:
        lines.append("이 기간에 새로 진입한 곡이 없습니다.")

    lines.append("")
    lines.append(f"## 순위가 가장 많이 오른 곡 (상위 {top_n})")
    if risers:
        lines.append(f"| 상승폭 | {earliest_date} 순위 | {latest_date} 순위 | 곡 | 아티스트 |")
        lines.append("|---|---|---|---|---|")
        for climb, prev_rank, cur_rank, row in risers[:top_n]:
            lines.append(f"| ▲{climb} | {prev_rank} | {cur_rank} | {row['title']} | {row['artist']} |")
    else:
        lines.append("이 기간에 뚜렷하게 순위가 오른 곡이 없습니다.")

    return "\n".join(lines)


def save_weekly_report(end_date: str, days: int = 7, top_n: int = 15) -> Path:
    REPORTS_DIR.mkdir(exist_ok=True)
    content = build_weekly_report(end_date, days=days, top_n=top_n)
    path = REPORTS_DIR / f"weekly_{end_date}.md"
    path.write_text(content, encoding="utf-8")
    return path
