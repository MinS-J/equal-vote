from __future__ import annotations

import argparse
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


REQUIRED_PATHS = [
    "/",
    "/docs.html",
    "/docs.js",
    "/styles.css",
    "/app.js",
    "/assets/chart1_scope.png",
    "/assets/chart6_nearmatch4.png",
    "/assets/data/site-data.js",
    "/assets/data/equal_pair_counts.csv",
    "/assets/data/pair_counts.csv",
    "/assets/data/DATA_DICTIONARY.md",
    "/assets/data/README.md",
    "/assets/data/equal_vote_probability_summary.md",
    "/QA_REPORT.md",
    "/assets/data/integrity-manifest.json",
    "/robots.txt",
    "/site.webmanifest",
]

REQUIRED_HOME_MARKERS = [
    "후보별 동일득표 분석",
    "쌍둥이 득표수 일치, 정말 가능한 확률일까?",
    "광주·전남 5쌍",
    "관측 구조를 조건으로 두고",
    "각 사건은 얼마나 자주 나오고, 둘은 얼마나 자주 함께 나오나",
    "P(B|A)",
    "모델 2(Model 2): 지역적응형 사후예측",
    "한 줄 요약: 실제 선거 데이터의 지역별 쏠림 특성을 시뮬레이션 프로그램에 넣고 같은 조건의 가상 선거를 20만 번 다시 치러 본 것이다.",
    "같은 조건의 가상 선거를 20만 번 다시 치렀다",
    "이 말은 이미 관측된 지역 구조를 받아들였을 때 비슷한 일이 얼마나 다시 생기는지 보는 검증이라는 뜻이다.",
    "모델 검증: 근접 일치는 맞는데, 정확 일치는 높다",
    "50,000회 반복",
    "이 분석은 희귀성과 재현성을 평가할 뿐",
    "놀라운 관측과 부정의 증거는 같은 말이 아니다",
    "자료와 재현성",
    "./docs.html?file=guide",
    "공개 재현 패키지",
    "https://github.com/MinS-J/equal-vote",
    "https://github.com/MinS-J/equal-vote/releases/tag/v2026-06-10",
    "equal-vote-inputs.zip",
    "/_vercel/insights/script.js",
]

REQUIRED_DOC_MARKERS = [
    "재현성 문서",
    'id="doc-body"',
    "docs.js",
    "재현 가이드",
    "데이터 사전",
    "/_vercel/insights/script.js",
]

REQUIRED_DOC_JS_MARKERS = [
    "DOCS",
    "./assets/data/README.md",
    "./assets/data/DATA_DICTIONARY.md",
    "./assets/data/equal_vote_probability_summary.md",
    "renderMarkdown",
]

REQUIRED_DATA_MARKERS = [
    '"focusDataset": "지선9회(2026)·사전투표"',
    '"label": "광역권"',
    '"regionalThresholds"',
    '"thresholdProbabilities"',
    '"jointProbabilities"',
    '"pAText": "0.587%"',
    '"pBText": "0.825%"',
    '"pABText": "0.0110%"',
    '"iterations": 50000',
    '"region": "대구"',
    '"region": "경상북"',
    '"nearMatch"',
    '"label": "분할동"',
    '"value": "1"',
    '"value": "8"',
    '"value": "10"',
    '"ratesPerMillion"',
]

REQUIRED_MANIFEST_MARKERS = [
    '"algorithm": "sha256"',
    '"path": "assets/data/equal_pair_counts.csv"',
    '"path": "docs.html"',
    '"path": "docs.js"',
    '"path": "assets/data/README.md"',
    '"path": "assets/chart1_scope.png"',
    '"path": "assets/chart6_nearmatch4.png"',
]


def normalize_base_url(value: str) -> str:
    url = value.strip().rstrip("/")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("base URL must be an absolute http(s) URL")
    return url


def fetch(base_url: str, path: str) -> tuple[int, bytes, str]:
    url = urljoin(base_url + "/", path.lstrip("/"))
    request = Request(url, headers={"User-Agent": "equal-vote-site-check/1.0"})
    with urlopen(request, timeout=15) as response:
        body = response.read()
        content_type = response.headers.get("content-type", "")
        return response.status, body, content_type


def require_text_markers(body: bytes, markers: list[str], label: str) -> None:
    text = body.decode("utf-8", errors="replace")
    missing = [marker for marker in markers if marker not in text]
    if missing:
        raise AssertionError(f"{label} missing markers: {missing}")


def require_text_order(body: bytes, markers: list[str], label: str) -> None:
    text = body.decode("utf-8", errors="replace")
    positions = [text.find(marker) for marker in markers]
    if any(position < 0 for position in positions) or positions != sorted(positions):
        raise AssertionError(f"{label} markers out of order: {markers}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify a deployed production URL.")
    parser.add_argument("--base-url", required=True, help="Production URL, for example https://example.vercel.app")
    args = parser.parse_args()
    base_url = normalize_base_url(args.base_url)

    responses: dict[str, tuple[int, bytes, str]] = {}
    for path in REQUIRED_PATHS:
        status, body, content_type = fetch(base_url, path)
        if status != 200 or not body:
            raise AssertionError(f"{path} failed: status={status}, bytes={len(body)}")
        responses[path] = (status, body, content_type)
        print(f"ok {path} {status} {len(body)} bytes")

    require_text_markers(responses["/"][1], REQUIRED_HOME_MARKERS, "home page")
    require_text_order(
        responses["/"][1],
        ['<section id="history"', '<section id="simulation"', '<section id="regional"'],
        "home page section order",
    )
    require_text_order(
        responses["/"][1],
        [
            '<a href="#history">전국데이터</a>',
            '<a href="#simulation">시뮬레이션</a>',
            '<a href="#regional">지역분석</a>',
        ],
        "home page nav order",
    )
    require_text_markers(responses["/docs.html"][1], REQUIRED_DOC_MARKERS, "docs.html")
    require_text_markers(responses["/docs.js"][1], REQUIRED_DOC_JS_MARKERS, "docs.js")
    require_text_markers(responses["/assets/data/site-data.js"][1], REQUIRED_DATA_MARKERS, "site-data.js")
    require_text_markers(
        responses["/assets/data/integrity-manifest.json"][1],
        REQUIRED_MANIFEST_MARKERS,
        "integrity-manifest.json",
    )
    print(f"production URL verified: {base_url}")


if __name__ == "__main__":
    main()
