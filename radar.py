from __future__ import annotations

import calendar
import hashlib
import html
import json
import os
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import feedparser
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

def env_text(name: str, default: str = "") -> str:
    return os.getenv(name, "").strip() or default


def env_int(name: str, default: int, minimum: int) -> int:
    try:
        value = int(os.getenv(name, "").strip() or default)
    except ValueError:
        value = default
    return max(minimum, value)


# Required secrets
BOT_TOKEN = env_text("TELEGRAM_BOT_TOKEN")
CHAT_ID = env_text("TELEGRAM_CHAT_ID")
GITHUB_TOKEN = env_text("GITHUB_TOKEN")

# Optional configuration
AI_MODEL = env_text("AI_MODEL", "openai/gpt-4o-mini")
AI_ENDPOINT = "https://models.github.ai/inference/chat/completions"
RSS_USER_AGENT = env_text("RSS_USER_AGENT", "A36Radar/1.0 (+https://a36labs.com)")
MAX_POSTS = env_int("MAX_POSTS_PER_RUN", 2, 1)
MAX_CANDIDATES = max(MAX_POSTS, env_int("MAX_AI_CANDIDATES", 10, 1))
MAX_AGE_HOURS = env_int("ARTICLE_MAX_AGE_HOURS", 36, 1)
STATE_LIMIT = env_int("MAX_STATE_ITEMS", 5000, 100)
STATE_FILE = Path("seen_articles.json")

FEEDS = [
    ("TechCrunch Startups", "https://techcrunch.com/category/startups/feed/", "Startups & Funding", 6),
    ("TechCrunch AI", "https://techcrunch.com/category/artificial-intelligence/feed/", "AI & Frontier Tech", 6),
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/", "Web3 & Crypto", 6),
    ("Cointelegraph", "https://cointelegraph.com/rss", "Web3 & Crypto", 4),
    ("Decrypt", "https://decrypt.co/feed", "Web3 & Crypto", 4),
    ("BBC Business", "https://feeds.bbci.co.uk/news/business/rss.xml", "Global Markets", 5),
    ("The Guardian Business", "https://www.theguardian.com/business/rss", "Global Markets", 4),
    ("Nasdaq IPOs", "https://www.nasdaq.com/feed/rssoutbound?category=IPOs", "IPOs & Public Markets", 6),
    ("SEC Press Releases", "https://www.sec.gov/news/pressreleases.rss", "Markets & Regulation", 6),
]

IMPORTANT = {
    "startup", "funding", "fundraise", "raised", "raises", "seed round",
    "series a", "series b", "series c", "venture capital", "valuation",
    "investment", "acquisition", "acquires", "merger", "takeover",
    "artificial intelligence", "generative ai", "foundation model",
    "large language model", "developer platform", "developer tools",
    "open source", "robotics", "semiconductor", "quantum",
    "cloud infrastructure", "data center", "bitcoin", "ethereum", "crypto",
    "cryptocurrency", "blockchain", "web3", "stablecoin", "tokenization",
    "defi", "layer 2", "layer-2", "mainnet", "protocol", "wallet",
    "digital assets", "institutional adoption", "crypto regulation", "etf",
    "ipo", "initial public offering", "files for ipo", "ipo filing",
    "public listing", "market debut", "new listing", "stock market", "stocks",
    "shares", "equities", "public markets", "public company", "earnings",
    "revenue", "profit", "guidance", "nasdaq", "nyse", "stock exchange",
    "market rally", "market selloff", "interest rates", "rate cut",
    "rate hike", "central bank", "sec",
}

HIGH_PRIORITY = {
    "funding", "raised", "raises", "acquisition", "acquires", "merger",
    "ipo", "initial public offering", "files for ipo", "ipo filing",
    "market debut", "valuation", "stablecoin", "regulation",
    "institutional adoption", "developer platform", "open source",
    "foundation model", "earnings", "guidance", "rate cut", "rate hike",
}

BLOCKED = {
    "keyboard review", "gaming mouse", "headphones review", "earbuds review",
    "smartwatch review", "phone case", "buying guide", "coupon",
    "deal of the day", "movie review", "tv show", "celebrity", "trailer",
    "video game review", "price prediction", "could reach", "next 100x",
    "moonshot", "presale", "airdrop guide", "buy now", "sponsored",
    "partner content", "analyst picks", "stock picks",
}

TRACKING_KEYS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "gclid", "fbclid", "mc_cid", "mc_eid",
}
STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
    "in", "is", "it", "of", "on", "or", "that", "the", "this", "to", "with",
}


def validate_environment() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is missing.")
    if not CHAT_ID:
        raise RuntimeError("TELEGRAM_CHAT_ID is missing.")


def make_session() -> requests.Session:
    retry = Retry(
        total=2,
        connect=2,
        read=2,
        backoff_factor=1,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.mount("http://", HTTPAdapter(max_retries=retry))
    session.headers.update({"User-Agent": RSS_USER_AGENT})
    return session


def clean_url(url: str) -> str:
    try:
        parts = urlsplit(url.strip())
        query = [
            (key, value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
            if key.lower() not in TRACKING_KEYS
        ]
        return urlunsplit(
            (parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/") or "/", urlencode(query), "")
        )
    except ValueError:
        return url.strip()


def strip_html(value: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", value or "")).split())


def limit_words(value: str, maximum: int) -> str:
    words = " ".join(value.split()).split()
    if len(words) <= maximum:
        return " ".join(words)
    return " ".join(words[:maximum]).rstrip(".,:;-") + "…"


def first_sentence(value: str) -> str:
    if not value.strip():
        return ""
    sentence = re.split(r"(?<=[.!?])\s+", " ".join(value.split()), maxsplit=1)[0]
    return limit_words(sentence, 24)


def timestamp(entry: Any) -> float:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    return float(calendar.timegm(parsed)) if parsed else time.time()


def identifier(url: str, title: str) -> str:
    return hashlib.sha256((clean_url(url) or title.lower()).encode()).hexdigest()


def title_tokens(title: str) -> set[str]:
    return {
        token for token in re.findall(r"[a-z0-9]+", title.lower())
        if len(token) > 2 and token not in STOP_WORDS
    }


def similar_titles(left: str, right: str) -> bool:
    a, b = title_tokens(left), title_tokens(right)
    return bool(a and b) and len(a & b) / len(a | b) >= 0.72


def load_state() -> dict[str, float]:
    if not STATE_FILE.exists():
        return {}
    try:
        raw = json.loads(STATE_FILE.read_text(encoding="utf-8")).get("seen", {})
    except (OSError, json.JSONDecodeError):
        return {}
    if isinstance(raw, list):
        return {str(item): time.time() for item in raw}
    if isinstance(raw, dict):
        result = {}
        for key, value in raw.items():
            try:
                result[str(key)] = float(value)
            except (TypeError, ValueError):
                result[str(key)] = time.time()
        return result
    return {}


def save_state(seen: dict[str, float]) -> None:
    newest = sorted(seen.items(), key=lambda item: item[1], reverse=True)[:STATE_LIMIT]
    STATE_FILE.write_text(
        json.dumps({"seen": dict(newest)}, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def score(article: dict[str, Any]) -> int:
    text = f"{article['title']} {article['summary']} {article['category']}".lower()
    if any(term in text for term in BLOCKED):
        return -100
    matches = {term for term in IMPORTANT if term in text}
    if not matches:
        return -100
    result = article["priority"] + len(matches) * 2
    result += sum(4 for term in HIGH_PRIORITY if term in text)
    if re.search(r"\$\s?\d+|\d+(?:\.\d+)?\s?(?:million|billion|trillion)", text):
        result += 3
    return result


def fetch_feed(session: requests.Session, name: str, url: str) -> Any | None:
    try:
        response = session.get(
            url,
            headers={"Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*"},
            timeout=25,
        )
        response.raise_for_status()
    except requests.RequestException as error:
        print(f"Feed unavailable: {name}: {error}")
        return None

    parsed = feedparser.parse(response.content)
    if parsed.bozo and not parsed.entries:
        print(f"Feed parse failed: {name}: {getattr(parsed, 'bozo_exception', 'unknown error')}")
        return None
    if parsed.bozo:
        print(f"Feed warning: {name}: {getattr(parsed, 'bozo_exception', 'unknown warning')}")
    return parsed


def collect_articles(session: requests.Session) -> list[dict[str, Any]]:
    articles: list[dict[str, Any]] = []
    for name, url, category, priority in FEEDS:
        print(f"Checking {name}...")
        feed = fetch_feed(session, name, url)
        if feed is None:
            continue
        for entry in feed.entries[:20]:
            title = " ".join(str(entry.get("title", "Untitled")).split())
            link = clean_url(str(entry.get("link", "")).strip())
            if not link:
                continue
            summary = strip_html(str(entry.get("summary", "") or entry.get("description", "")))
            if len(summary) > 900:
                summary = summary[:899].rstrip() + "…"
            article = {
                "id": identifier(link, title),
                "title": title,
                "link": link,
                "summary": summary,
                "source": name,
                "category": category,
                "priority": priority,
                "timestamp": timestamp(entry),
            }
            article["score"] = score(article)
            articles.append(article)

    articles.sort(key=lambda item: (item["score"], item["timestamp"]), reverse=True)
    unique: list[dict[str, Any]] = []
    for article in articles:
        if not any(similar_titles(article["title"], existing["title"]) for existing in unique):
            unique.append(article)
    return unique


def parse_json_object(value: str) -> dict[str, Any]:
    cleaned = value.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    parsed = json.loads(cleaned)
    if not isinstance(parsed, dict):
        raise ValueError("AI response is not a JSON object.")
    return parsed


def fallback(candidates: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            "id": article["id"],
            "headline": limit_words(article["title"], 12),
            "summary": first_sentence(article["summary"]),
        }
        for article in candidates[:MAX_POSTS]
    ]


def edit_with_ai(
    session: requests.Session,
    candidates: list[dict[str, Any]],
) -> list[dict[str, str]]:
    if not candidates:
        return []
    if not GITHUB_TOKEN:
        print("GitHub Models unavailable; using fallback editing.")
        return fallback(candidates)

    supplied = [
        {
            "id": item["id"],
            "title": item["title"],
            "summary": item["summary"],
            "source": item["source"],
            "category": item["category"],
            "score": item["score"],
        }
        for item in candidates[:MAX_CANDIDATES]
    ]

    prompt = f"""
You edit A36 Radar, a global frontier-technology and markets feed.
Select at most {MAX_POSTS} high-signal stories.

Prioritize major funding, acquisitions, IPOs, AI and developer-platform news,
Web3 infrastructure and regulation, important public-company news, earnings,
market debuts, and major central-bank decisions.

Reject reviews, buying guides, minor gadgets, entertainment, sponsored posts,
rumours, price predictions, stock tips, token promotions, routine notices,
ordinary price movements, and duplicate stories.

Use only supplied facts. Do not invent context or numbers.
Return one JSON object only:
{{"items":[{{"id":"candidate id","headline":"max 12 words","summary":"one factual sentence, max 24 words"}}]}}
Return {{"items":[]}} if nothing is strong enough.
""".strip()

    try:
        response = session.post(
            AI_ENDPOINT,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {GITHUB_TOKEN}",
                "X-GitHub-Api-Version": "2026-03-10",
                "Content-Type": "application/json",
            },
            json={
                "model": AI_MODEL,
                "temperature": 0.1,
                "max_tokens": 500,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": json.dumps({"candidates": supplied}, ensure_ascii=False)},
                ],
            },
            timeout=45,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        raw_items = parse_json_object(str(content)).get("items", [])
    except (requests.RequestException, KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as error:
        print(f"AI editor unavailable ({error}); using fallback editing.")
        return fallback(candidates)

    by_id = {article["id"]: article for article in candidates}
    selected: list[dict[str, str]] = []
    used: set[str] = set()
    if not isinstance(raw_items, list):
        return fallback(candidates)

    for item in raw_items:
        if len(selected) >= MAX_POSTS or not isinstance(item, dict):
            break
        item_id = str(item.get("id", ""))
        article = by_id.get(item_id)
        if article is None or item_id in used:
            continue
        selected.append(
            {
                "id": item_id,
                "headline": limit_words(str(item.get("headline", "")) or article["title"], 12),
                "summary": limit_words(str(item.get("summary", "")) or first_sentence(article["summary"]), 24),
            }
        )
        used.add(item_id)
    return selected


def build_message(article: dict[str, Any], editorial: dict[str, str]) -> str:
    headline = html.escape(editorial["headline"])
    summary = html.escape(editorial["summary"])
    category = html.escape(article["category"])
    source = html.escape(article["source"])
    link = html.escape(article["link"], quote=True)
    summary_line = f"\n{summary}" if summary else ""
    return (
        "📡 <b>A36 RADAR</b>\n\n"
        f"<b>{headline}</b>{summary_line}\n\n"
        f"{category} · {source}\n"
        f'<a href="{link}">Read ↗</a>'
    )


def send_message(
    session: requests.Session,
    message: str,
    article_url: str,
) -> bool:
    try:
        response = session.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={
                "chat_id": CHAT_ID,
                "text": message,
                "parse_mode": "HTML",
                "link_preview_options": {
                    "is_disabled": False,
                    "url": article_url,
                    "prefer_small_media": True,
                    "prefer_large_media": False,
                    "show_above_text": False,
                },
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as error:
        print(f"Telegram send failed: {error}")
        return False
    if not payload.get("ok"):
        print(f"Telegram rejected the message: {payload}")
        return False
    return True


def main() -> None:
    validate_environment()
    session = make_session()
    seen = load_state()
    articles = collect_articles(session)
    cutoff = time.time() - MAX_AGE_HOURS * 3600
    candidates = [
        article for article in articles
        if article["id"] not in seen
        and article["score"] > 0
        and cutoff <= article["timestamp"] <= time.time()
    ]

    print(f"Collected {len(articles)} unique article(s).")
    print(f"Found {len(candidates)} relevant unseen candidate(s).")

    editorial = edit_with_ai(session, candidates)
    by_id = {article["id"]: article for article in candidates}
    published = 0
    for item in editorial:
        article = by_id.get(item["id"])
        if article is None:
            continue
        print(f"Publishing: {item['headline']}")
        if send_message(session, build_message(article, item), article["link"]):
            published += 1
        time.sleep(2)

    processed_at = time.time()
    for article in articles:
        seen[article["id"]] = processed_at
    save_state(seen)
    print(f"Published {published} article(s).")


if __name__ == "__main__":
    main()
