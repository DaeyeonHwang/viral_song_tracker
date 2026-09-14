# 바이럴 음악 트래커 (개인용)

YouTube Trending Music과 Last.fm 차트를 교차 비교해서, 여러 소스에서 동시에
뜨고 있는 곡에 더 높은 점수를 주는 개인용 스크립트입니다.

## 1. 먼저 API 키 없이 테스트해보기

API 키가 없어도 샘플 데이터로 전체 파이프라인(수집 → 정규화 → 매칭 →
스코어링 → 저장 → 리포트)이 동작하는 걸 바로 확인할 수 있습니다.

```bash
pip install -r requirements.txt --break-system-packages   # 또는 가상환경에서 pip install -r requirements.txt
python main.py --demo
```

`reports/오늘날짜.md` 파일에 순위표가 생성됩니다. 같은 명령을 다른 날짜로
한 번 더 돌려보면(`python main.py --demo --date 2026-09-15`) 전일 대비
순위 변동(▲▼)이 어떻게 표시되는지도 볼 수 있어요.

## 2. 실제 API 키 발급받기

### YouTube Data API v3
1. https://console.cloud.google.com 접속 후 새 프로젝트 생성
2. 왼쪽 메뉴 "API 및 서비스" → "라이브러리"에서 "YouTube Data API v3" 검색 후 활성화
3. "사용자 인증 정보" → "사용자 인증 정보 만들기" → "API 키" 선택
4. 생성된 키를 복사 (필요하면 "키 제한"에서 YouTube Data API로 제한해두면 더 안전합니다)

무료 할당량은 하루 10,000 유닛이고, 이 스크립트가 쓰는 호출은 1회에 1유닛만
쓰므로 개인용으로는 사실상 무제한이라고 봐도 됩니다.

### Last.fm API
1. https://www.last.fm/api/account/create 접속 (last.fm 계정 필요, 없으면 먼저 가입)
2. Application name 등 간단한 정보 입력 후 제출
3. 발급된 API key 복사 (Shared secret은 이 스크립트에서는 필요 없습니다)

## 3. .env 파일 만들기

```bash
cp .env.example .env
```

`.env` 파일을 열어 두 키를 채워 넣으세요.

```
YOUTUBE_API_KEY=여기에_키_붙여넣기
LASTFM_API_KEY=여기에_키_붙여넣기
YOUTUBE_REGIONS=US
LASTFM_COUNTRY=
EXCLUDE_KOREAN=true
```

- `YOUTUBE_REGIONS`: 첫 번째 값만 사용됩니다. 한국 차트를 보고 싶으면 `KR`로 바꾸세요.
- `LASTFM_COUNTRY`: 비워두면 글로벌 차트, `south korea`처럼 국가명을 넣으면 해당 국가 차트를 봅니다.
- `EXCLUDE_KOREAN`: `true`면 제목/아티스트에 한글이 포함된 곡을 결과에서 제외합니다 (해외 곡만 보고 싶을 때). 한국 곡도 같이 보고 싶으면 `false`로 바꾸세요.
- `RECENT_SONG_DAYS`: 리포트의 "태그" 컬럼에서 신곡/역주행을 가르는 기준일수입니다. 기본 90일(약 3개월) 이내에 유튜브에 업로드됐으면 "신곡", 그보다 오래됐으면 "역주행"으로 표시됩니다. Last.fm에서만 잡힌 곡은 발매일 정보가 없어 "정보없음"으로 표시됩니다.
- `USE_MUSICBRAINZ`: `true`면 [MusicBrainz](https://musicbrainz.org)에서 곡의 공식 식별자(MBID)를 찾아 매칭 정확도를 높입니다. 문자열 유사도만으로는 표기가 많이 다른 같은 곡을 놓치거나, 제목이 비슷한 다른 곡을 잘못 합칠 수 있는데 MBID가 일치하면 확실하게 같은 곡으로 판단합니다. 조회 결과는 `tracker.db`에 캐싱되므로 처음 보는 곡만 새로 조회하고(초당 1건 제한이라 곡이 많으면 첫 실행이 다소 느릴 수 있음), 다음날부터는 캐시 덕분에 빨라집니다. `--demo` 모드에서는 네트워크를 타지 않도록 자동으로 꺼집니다.
- `FILTER_DERIVATIVE`: `true`면 제목에 "reaction", "cover", "sped up", "nightcore" 같은 표현이 들어간, 팬메이드 파생 콘텐츠로 보이는 영상을 결과에서 제외합니다.
- `USE_REDDIT`: `true`면 이미 찾은 곡들이 최근 Reddit(r/music, r/popheads 등)에서 얼마나 언급되고 있는지 조회해서 점수에 보너스로 반영합니다. Reddit은 자체 인기차트가 없어서 독립 소스가 아니라, YouTube/Last.fm에서 이미 찾은 곡을 검증·보강하는 용도로만 씁니다.

  **주의**: Reddit이 2026년 5월 28일부터 비인증(.json) 요청을 차단하고 있어서, `REDDIT_CLIENT_ID`/`REDDIT_CLIENT_SECRET` 없이는 대부분 실패합니다. 실패하면 조용히 넘어가지 않고 콘솔에 "Reddit 언급량 조회 건너뜀: ..." 이유가 뜨고, 점수에는 영향을 주지 않습니다. 정식으로 쓰려면 아래 안내대로 Reddit 개발자 앱을 등록하고 `.env`에 두 값을 채워 넣으세요 — 다만 2025년 말부터 신규 앱은 수동 승인이 필요하고, 개인 프로젝트는 반려되거나 응답이 아예 없는 경우가 흔합니다. 신청은 무료이니 밑져야 본전으로 넣어보되, 승인을 전제로 계획하지는 마세요.

  1. https://www.reddit.com/prefs/apps 에서 "create another app" 클릭
  2. 이름을 정하고 앱 유형은 **script** 선택
  3. redirect URI는 아무 값이나(예: `http://localhost:8080`) 입력 (실제로 쓰이진 않지만 필수 입력값)
  4. "create app" 클릭 후, 앱 이름 바로 아래 짧은 문자열이 client ID, 그 옆이 client secret
  5. 이후 접근 승인 신청 절차(Reddit이 요구하는 별도 양식)를 진행 — 승인되면 두 값을 `.env`의 `REDDIT_CLIENT_ID`/`REDDIT_CLIENT_SECRET`에 넣기만 하면 자동으로 정식 API로 전환됩니다 (코드 수정 불필요)

- `REDDIT_SUBREDDITS`: 언급량을 확인할 서브레딧 목록 (콤마 구분)
- `REDDIT_WEIGHT`: 언급 1건당 보너스 점수의 세기 (log 스케일로 더해짐, 값을 낮추면 영향이 줄어듦)
- `REDDIT_CHECK_TOP_N`: 상위 몇 곡까지만 Reddit 조회를 할지 (많을수록 정확하지만 실행 시간이 늘어남)

리포트의 "등장 소스" 칸에 `reddit`이 같이 뜨면 실제로 언급이 확인된 곡입니다.

- `WATCHLIST_ARTISTS`: 관심 아티스트 이름을 콤마로 나열하세요 (예: `Adele,IVE,Bruno Mars`). 대소문자나 표기가 살짝 달라도 웬만하면 잡아냅니다. 이 아티스트의 곡이 오늘 트렌딩 목록 안에 있으면, 전체 순위와 상관없이 리포트 맨 위 "관심 아티스트 소식" 섹션에 따로 나옵니다. 단, 그 아티스트가 오늘 YouTube/Last.fm 트렌딩에 아예 안 잡혔으면(신곡을 안 냈거나 화제가 안 됐으면) 워치리스트에도 뜨지 않습니다 — 이 스크립트는 특정 채널을 감시하는 게 아니라 "오늘의 트렌딩 목록 안에서" 찾는 방식이라서요.
- `GENRE_INCLUDE` / `GENRE_EXCLUDE`: Last.fm 태그(예: `pop`, `hip hop`, `k-pop`, `edm`) 기준으로 장르를 거릅니다. `GENRE_INCLUDE`에 값을 넣으면 그 장르만 남기고, `GENRE_EXCLUDE`에 값을 넣으면 그 장르는 항상 뺍니다. 둘 다 설정하면 "포함 목록에는 있으면서 제외 목록에는 없는" 곡만 남습니다. Last.fm 태그는 이용자들이 직접 붙인 것이라 정확도가 들쭉날쭉하고, 아주 최근 곡은 태그가 아직 없을 수 있는데 — 이 경우 무작정 걸러내지 않고 일단 통과시킵니다 (모르는 걸 틀렸다고 판단하지 않기 위함). `GENRE_CHECK_TOP_N`으로 태그 조회할 곡 수(=실행 시간)를 조절할 수 있습니다.

## 4. 실제로 실행하기

```bash
python main.py
```

## 5. 주간 급상승 리포트 보기

새로 데이터를 수집하지 않고, 그동안 쌓인 데이터만으로 "최근 며칠 사이 새로 진입한 곡"과
"순위가 가장 많이 오른 곡"을 뽑아볼 수 있습니다.

```bash
python main.py --weekly              # 최근 7일 비교 (기본값)
python main.py --weekly --days 14    # 최근 14일 비교
```

`reports/weekly_YYYY-MM-DD.md`로 저장됩니다. 데이터가 이틀 이상 쌓이기 전까지는
"비교할 과거 데이터가 부족합니다"라는 안내만 나옵니다 — `python main.py`를 매일(또는
며칠에 한 번) 돌려서 스냅샷을 먼저 쌓아두세요.

## 6. 매일 자동 실행하기 (선택)

macOS/Linux는 cron으로 매일 아침 실행하도록 등록할 수 있습니다.

```bash
crontab -e
# 매일 오전 9시에 실행
0 9 * * * cd /경로/viral_song_tracker && /usr/bin/python3 main.py >> run.log 2>&1
```

## 참고: 같은 날짜에 다시 실행하면?

하루에 여러 번 실행해도(예: `--demo`로 테스트해본 뒤 실제로 다시 실행) 문제없습니다.
저장 직전에 그날 날짜의 기존 데이터를 지우고 새로 쓰기 때문에, 항상 가장 최근 실행
결과만 그날의 스냅샷으로 남습니다. 전날과의 순위 비교(▲▼)는 날짜가 다른 스냅샷끼리만
비교하므로 영향받지 않습니다.

## 폴더 구조

```
config.py         환경변수 로드, 소스 가중치 설정
normalize.py       제목/아티스트 정규화, 같은 곡 판별
sources/youtube.py  YouTube 트렌딩 음악 수집
sources/lastfm.py   Last.fm 인기곡 차트 수집
score.py            소스 교차 매칭 + 가중 스코어링
db.py               SQLite 저장/조회
report.py           마크다운 리포트 생성
main.py             전체 파이프라인 실행 진입점
sample_data/        --demo 모드용 가짜 데이터 (실제 차트 아님)
```

## 나중에 확장하고 싶다면

- Spotify의 "Today's Top Hits" 같은 공식 플레이리스트를 카테고리 조회로 추가
- YOUTUBE_REGIONS의 여러 국가를 동시에 수집해 지역별 비교

Spotify나 TikTok은 2026년 기준 개인 개발자가 트렌드/바이럴 데이터에 접근하기
까다로워진 상태라(Spotify는 상세 데이터가 승인제로 바뀌었고, TikTok은 공식
API에 트렌딩 사운드 자체가 없음) 이번 버전에는 넣지 않았습니다.
