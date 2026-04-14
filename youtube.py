from __future__ import annotations

import html
import re
from urllib.parse import quote_plus
from urllib.request import Request, urlopen


YOUTUBE_SEARCH_URL = "https://www.youtube.com/results?search_query={query}"
DUCKDUCKGO_SEARCH_URL = "https://html.duckduckgo.com/html/?q={query}"
VIDEO_URL_TEMPLATE = "https://www.youtube.com/watch?v={video_id}"


def _deduplicate(items: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    unique: list[dict[str, str]] = []
    for item in items:
        video_id = item.get("video_id", "")
        if not video_id or video_id in seen:
            continue
        seen.add(video_id)
        unique.append(item)
    return unique


def recommend_videos(query: str, top_k: int = 3) -> list[dict[str, str]]:
    videos = _search_youtube(query)
    if videos:
        return videos[:top_k]
    return _search_duckduckgo(query, top_k=top_k)


def _fetch_html(url: str) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            )
        },
    )

    try:
        with urlopen(request, timeout=20) as response:
            return response.read().decode("utf-8", errors="ignore")
    except Exception:
        return ""


def _search_youtube(query: str) -> list[dict[str, str]]:
    html_text = _fetch_html(YOUTUBE_SEARCH_URL.format(query=quote_plus(query)))
    if not html_text:
        return []

    videos: list[dict[str, str]] = []
    pattern = re.compile(
        r'"videoId":"(?P<id>[^"]+)".*?"title":\{"runs":\[\{"text":"(?P<title>.*?)"',
        flags=re.DOTALL,
    )
    for match in pattern.finditer(html_text):
        video_id = match.group("id").strip()
        title = match.group("title").strip()
        videos.append(
            {
                "video_id": video_id,
                "title": title.encode("utf-8").decode("unicode_escape"),
                "url": VIDEO_URL_TEMPLATE.format(video_id=video_id),
            }
        )

    return _deduplicate(videos)


def _search_duckduckgo(query: str, top_k: int = 3) -> list[dict[str, str]]:
    search_query = quote_plus(f"site:youtube.com/watch {query}")
    html_text = _fetch_html(DUCKDUCKGO_SEARCH_URL.format(query=search_query))
    if not html_text:
        return []

    matches = re.findall(
        r'<a[^>]+class="result__a"[^>]+href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>',
        html_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    videos: list[dict[str, str]] = []
    for href, raw_title in matches:
        url = html.unescape(href)
        match = re.search(r"(https?://www\.youtube\.com/watch\?v=[^&\"']+)", url)
        if not match:
            continue
        clean_title = re.sub(r"<.*?>", "", raw_title)
        clean_title = html.unescape(clean_title).strip()
        video_url = match.group(1)
        video_id_match = re.search(r"v=([^&]+)", video_url)
        videos.append(
            {
                "video_id": video_id_match.group(1) if video_id_match else video_url,
                "title": clean_title or "YouTube video",
                "url": video_url,
            }
        )
    return _deduplicate(videos)[:top_k]
