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

import feedparser
import requests

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
DISCUSSION_CHAT_ID = os.environ.get("TELEGRAM_DISCUSSION_CHAT_ID", "").strip()
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
RSS_USER_AGENT = os.environ.get(
    "RSS_USER_AGENT", "A36 Radar/1.0 (+https://a36labs.com)"
).strip()

STATE_FILE = Path("seen_articles.json")
MAX_POSTS_PER_RUN = 2
MAX_AI_CANDIDATES = 16
MAX_HISTORY = 6000
ARTICLE_MAX_AGE_HOURS = 24
REQUEST_TIMEOUT_SECONDS = 35
AI_MODEL = "openai/gpt-4o-mini"
AI_ENDPOINT = "https://models.github.ai/inference/chat/completions"

FEEDS = [
    ("TechCrunch Startups", "https://techcrunch.com/category/startups/feed/", "Startups & Funding"),
    ("TechCrunch AI", "https://techcrunch.com/category/artificial-intelligence/feed/", "AI & Frontier Tech"),
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/", "Web3 & Crypto"),
    ("Cointelegraph", "https://cointelegraph.com/rss", "Web3 & Crypto"),
    ("Decrypt", "https://decrypt.co/feed", "Web3 & Crypto"),
    ("BBC Business", "https://feeds.bbci.co.uk/news/business/rss.xml", "Global Markets"),
    ("The Guardian Business", "https://www.theguardian.com/business/rss", "Global Markets"),
    ("SEC Press Releases", "https://www.sec.gov/news/pressreleases.rss", "Markets & Regulation"),
    ("HKEX News Releases", "https://www.hkexgroup.com/Global/RSS-Feed/NewsRelease?sc_lang=en", "Asia Markets & IPOs"),
    ("Nasdaq Europe Main Markets", "https://api.news.eu.nasdaq.com/news/rss/mainMarketNotices", "Europe Markets & Listings"),
    ("Nasdaq Nordic News", "https://api.news.eu.nasdaq.com/news/rss/nasdaqNordicNews", "Europe Markets & Listings"),
]

SOURCE_PRIORITY = {
    "TechCrunch Startups": 6,
    "TechCrunch AI": 6,
    "CoinDesk": 6,
    "Cointelegraph": 3,
    "Decrypt": 4,
    "BBC Business": 5,
    "The Guardian Business": 4,
    "SEC Press Releases": 6,
    "HKEX News Releases": 5,
    "Nasdaq Europe Main Markets": 4,
    "Nasdaq Nordic News": 4,
}

CATEGORY_EMOJIS = {
    "Startups & Funding": "🚀",
    "AI & Frontier Tech": "🧠",
    "Web3 & Crypto": "⛓️",
    "Global Markets": "📈",
    "Markets & Regulation": "🏛️",
    "Asia Markets & IPOs": "🌏",
    "Europe Markets & Listings": "🌍",
}


def terms(value: str) -> set[str]:
    return {item.strip().lower() for item in value.split("|") if item.strip()}


IMPORTANT_KEYWORDS = terms(
    "raises|raised|funding|fundraise|fundraising|seed round|series a|series b|series c|"
    "venture capital|valuation|investment|invests|backed by|acquisition|acquires|acquired|"
    "merger|startup|artificial intelligence|generative ai|foundation model|large language model|"
    "ai model|developer platform|developer tools|open source|robotics|semiconductor|chipmaker|"
    "quantum computing|cloud infrastructure|data center|bitcoin|ethereum|crypto|cryptocurrency|"
    "blockchain|web3|stablecoin|tokenization|defi|layer 2|layer-2|mainnet|protocol|wallet|"
    "digital assets|institutional adoption|crypto regulation|crypto exchange|etf|stock market|"
    "stocks|shares|equities|public markets|public company|earnings|revenue|profit|guidance|"
    "listing|listed|new listing|market debut|ipo|initial public offering|ipo filing|files for ipo|"
    "secondary offering|stock exchange|nasdaq|nyse|hkex|london stock exchange|market rally|"
    "market selloff|interest rates|rate cut|rate hike|central bank|sec|regulation"
)

HIGH_PRIORITY_KEYWORDS = terms(
    "raises|raised|funding|acquisition|acquires|merger|valuation|initial public offering|"
    "ipo filing|files for ipo|market debut|public listing|earnings|guidance|rate cut|rate hike|"
    "stablecoin|institutional adoption|regulation|developer platform|open source|foundation model"
)

BLOCKED_KEYWORDS = terms(
    "keyboard|gaming mouse|headphones|earbuds|smartwatch|phone case|product review|buying guide|"
    "discount|coupon|deal of the day|best price|celebrity|movie review|tv show|trailer|"
    "video game review|gaming review|price prediction|could reach|next 100x|moonshot|presale|"
    "airdrop guide|buy now|sponsored|partner content|stock picks|stocks to buy|analyst picks"
)

STOP_WORDS = terms(
    "a|an|and|are|as|at|be|by|for|from|has|have|in|is|it|its|of|on|or|that|the|this|to|with"
)


def validate_environment() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is missing.")
    if not CHAT_ID:
        raise RuntimeError("TELEGRAM_CHAT_ID is missing.")


def load_seen_articles() -> dict[str, float]:
    if not STATE_FILE.exists():
        return {}
    try:
        stored = json.loads(STATE_FILE.read_text(encoding="utf-8")).get("seen", {})
        if isinstance(stored, dict):
            return {str(k): float(v) for k, v in stored.items()}
        if isinstance(stored, list):
            return {str(item): 0.0 for item in stored}
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
        print(f"State warning: {error}. Starting with an empty history.")
    return {}


def save_seen_articles(seen: dict[str, float]) -> None:
    newest = sorted(seen.items(), key=lambda item: item[1], reverse=True)[:MAX_HISTORY]
    STATE_FILE.write_text(
        json.dumps({"seen": dict(newest)}, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def stable_article_id(entry: Any) -> str:
    value = entry.get("link") or entry.get("id") or entry.get("title", "")
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def publication_timestamp(entry: Any) -> float:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    return float(calendar.timegm(parsed)) if parsed else time.time()


def strip_html(value: str) -> str:
    value = re.sub(r"<script\b[^>]*>.*?</script>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<style\b[^>]*>.*?</style>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    return " ".join(html.unescape(value).split())


def clean_summary(entry: Any, maximum_length: int = 1000) -> str:
    summary = strip_html(str(entry.get("summary", "") or entry.get("description", "")))
    return summary if len(summary) <= maximum_length else summary[: maximum_length - 1].rstrip() + "…"


def normalize_title(value: str) -> str:
    value = re.sub(r"[^a-z0-9\s]", " ", html.unescape(value).lower())
    return " ".join(value.split())


def title_tokens(value: str) -> set[str]:
    return {
        token
        for token in normalize_title(value).split()
        if len(token) > 2 and token not in STOP_WORDS
    }


def titles_are_similar(first: str, second: str, threshold: float = 0.62) -> bool:
    first_tokens, second_tokens = title_tokens(first), title_tokens(second)
    if not first_tokens or not second_tokens:
        return False
    return len(first_tokens & second_tokens) / len(first_tokens | second_tokens) >= threshold


def limit_words(value: str, maximum_words: int) -> str:
    words = " ".join(value.split()).split()
    return " ".join(words) if len(words) <= maximum_words else " ".join(words[:maximum_words]).rstrip(".,:;") + "…"


def fallback_summary(value: str) -> str:
    if not value:
        return ""
    first_sentence = re.split(r"(?<=[.!?])\s+", value, maxsplit=1)[0]
    return limit_words(first_sentence, 18)


def calculate_relevance(article: dict[str, Any]) -> int:
    text = f"{article['title']} {article['summary']} {article['category']}".lower()
    if any(keyword in text for keyword in BLOCKED_KEYWORDS):
        return -100
    matches = {keyword for keyword in IMPORTANT_KEYWORDS if keyword in text}
    if not matches:
        return -100

    score = len(matches) * 2 + SOURCE_PRIORITY.get(article["source"], 0)
    score += sum(4 for keyword in HIGH_PRIORITY_KEYWORDS if keyword in text)
    if re.search(r"\$\s?\d+|\d+(?:\.\d+)?\s?(?:million|billion|trillion)", text):
        score += 4
    if any(term in text for term in ("regulation", "institutional", "infrastructure", "developer", "open source", "sec", "etf", "earnings", "ipo")):
        score += 3
    return score


def is_recent(article: dict[str, Any]) -> bool:
    age = time.time() - float(article["timestamp"])
    return 0 <= age <= ARTICLE_MAX_AGE_HOURS * 3600


def fetch_feed(name: str, url: str, category: str) -> list[dict[str, Any]]:
    headers = {
        "User-Agent": RSS_USER_AGENT,
        "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
    }
    try:
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
    except requests.RequestException as error:
        print(f"Feed skipped ({name}): {error}")
        return []

    parsed = feedparser.parse(response.content)
    if parsed.bozo:
        print(f"Feed warning ({name}): {getattr(parsed, 'bozo_exception', 'unknown parse issue')}")

    articles: list[dict[str, Any]] = []
    for entry in parsed.entries[:20]:
        title = " ".join(str(entry.get("title", "Untitled")).split())
        link = str(entry.get("link", "")).strip()
        if not link or title == "Untitled":
            continue

        article = {
            "id": stable_article_id(entry),
            "title": title,
            "link": link,
            "summary": clean_summary(entry),
            "source": name,
            "category": category,
            "timestamp": publication_timestamp(entry),
        }
        article["score"] = calculate_relevance(article)
        articles.append(article)
    return articles


def collect_articles() -> list[dict[str, Any]]:
    combined: list[dict[str, Any]] = []
    for name, url, category in FEEDS:
        print(f"Checking {name}...")
        combined.extend(fetch_feed(name, url, category))

    combined.sort(key=lambda item: (item["score"], item["timestamp"]), reverse=True)
    accepted: list[dict[str, Any]] = []
    seen_links: set[str] = set()

    for article in combined:
        if article["link"] in seen_links:
            continue
        if any(titles_are_similar(article["title"], existing["title"]) for existing in accepted):
            continue
        accepted.append(article)
        seen_links.add(article["link"])
    return accepted


def parse_ai_json(content: str) -> dict[str, Any]:
    content = re.sub(r"^```(?:json)?\s*", "", content.strip())
    content = re.sub(r"\s*```$", "", content)
    return json.loads(content)


def fallback_editorial(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "index": index,
            "headline": limit_words(article["title"], 10),
            "summary": fallback_summary(article["summary"]),
        }
        for index, article in enumerate(candidates[:MAX_POSTS_PER_RUN])
    ]


def edit_batch_with_ai(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fallback = fallback_editorial(candidates)
    if not candidates:
        return []
    if not GITHUB_TOKEN:
        print("GITHUB_TOKEN unavailable. Using the fallback editor.")
        return fallback

    system_prompt = """
You are the editor of A36 Radar, a global frontier-technology and markets news feed.
Select at most two meaningful, well-supported stories with global relevance.

Prioritise startup funding, M&A, IPOs, major AI and open-source developments,
Web3 infrastructure, stablecoins, institutional adoption, regulation, major
public-company earnings or guidance, important listings, and central-bank decisions.

Reject product reviews, minor gadgets, gaming accessories, entertainment,
sponsored content, rumours, token promotions, price predictions, stock tips,
routine exchange notices, ordinary price moves, and duplicate stories.

Use only supplied facts. Never invent details or give investment advice.
Return JSON only:
{"stories":[{"index":0,"headline":"maximum 10 words","summary":"one factual sentence, maximum 18 words"}]}
Return an empty stories array when nothing is strong enough.
""".strip()

    candidates_payload = [
        {
            "index": index,
            "title": article["title"],
            "summary": article["summary"],
            "source": article["source"],
            "category": article["category"],
        }
        for index, article in enumerate(candidates)
    ]

    try:
        response = requests.post(
            AI_ENDPOINT,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {GITHUB_TOKEN}",
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
            },
            json={
                "model": AI_MODEL,
                "temperature": 0.1,
                "max_tokens": 450,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": json.dumps({"candidates": candidates_payload}, ensure_ascii=False)},
                ],
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        stories = parse_ai_json(content).get("stories", [])
        if not isinstance(stories, list):
            raise ValueError("AI response did not contain a stories list.")

        results: list[dict[str, Any]] = []
        used_indices: set[int] = set()
        for story in stories:
            if len(results) >= MAX_POSTS_PER_RUN:
                break
            index = int(story.get("index", -1))
            if index < 0 or index >= len(candidates) or index in used_indices:
                continue

            headline = limit_words(str(story.get("headline", "")), 10) or limit_words(candidates[index]["title"], 10)
            summary = limit_words(str(story.get("summary", "")), 18) or fallback_summary(candidates[index]["summary"])
            results.append({"index": index, "headline": headline, "summary": summary})
            used_indices.add(index)
        return results

    except (requests.RequestException, KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as error:
        print(f"AI editor unavailable: {error}. Using the fallback editor.")
        return fallback


def build_message(article: dict[str, Any]) -> str:
    headline = html.escape(article["headline"])
    summary = html.escape(article["short_summary"])
    category = html.escape(article["category"])
    source = html.escape(article["source"])
    link = html.escape(article["link"], quote=True)
    emoji = CATEGORY_EMOJIS.get(article["category"], "📡")
    summary_line = f"\n{summary}" if summary else ""

    return (
        "⚡️ <b>A36 RADAR</b>\n\n"
        f"<b>{headline}</b>{summary_line}\n\n"
        f"{emoji} {category} · <a href=\"{link}\">{source} ↗</a>"
    )


def send_to_telegram(message: str, link: str) -> None:
    response = requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={
            "chat_id": CHAT_ID,
            "text": message,
            "parse_mode": "HTML",
            "link_preview_options": {
                "is_disabled": False,
                "url": link,
                "prefer_small_media": False,
                "prefer_large_media": True,
                "show_above_text": False,
            },
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    result = response.json()
    if not result.get("ok"):
        raise RuntimeError(f"Telegram rejected the message: {result}")


def unpin_automatic_discussion_post(
    max_attempts: int = 5,
    delay_seconds: int = 4,
) -> None:
    """Unpin the latest linked-channel forward while preserving manual pins."""
    if not DISCUSSION_CHAT_ID:
        print(
            "TELEGRAM_DISCUSSION_CHAT_ID is missing. "
            "Skipping discussion unpin."
        )
        return

    get_chat_url = (
        "https://api.telegram.org/"
        f"bot{BOT_TOKEN}/getChat"
    )
    unpin_url = (
        "https://api.telegram.org/"
        f"bot{BOT_TOKEN}/unpinChatMessage"
    )

    for attempt in range(max_attempts):
        if attempt > 0:
            time.sleep(delay_seconds)

        try:
            response = requests.post(
                get_chat_url,
                json={"chat_id": DISCUSSION_CHAT_ID},
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            payload = response.json()

            if not payload.get("ok"):
                print(f"Could not read discussion group: {payload}")
                return

            pinned_message = (
                payload.get("result", {})
                .get("pinned_message")
            )

            if not pinned_message:
                print("No pinned message found in the discussion group.")
                return

            if pinned_message.get("is_automatic_forward", False):
                message_id = pinned_message.get("message_id")
                if not message_id:
                    print("Automatic forward has no message_id.")
                    return

                unpin_response = requests.post(
                    unpin_url,
                    json={
                        "chat_id": DISCUSSION_CHAT_ID,
                        "message_id": message_id,
                    },
                    timeout=REQUEST_TIMEOUT_SECONDS,
                )
                unpin_response.raise_for_status()
                unpin_payload = unpin_response.json()

                if unpin_payload.get("ok"):
                    print(
                        "Unpinned the automatically forwarded "
                        "channel post from the discussion group."
                    )
                else:
                    print(f"Could not unpin discussion post: {unpin_payload}")
                return

            if attempt == max_attempts - 1:
                print(
                    "The current pinned message is manual, not an "
                    "automatic channel forward. Leaving it pinned."
                )

        except requests.RequestException as error:
            if attempt == max_attempts - 1:
                print(f"Discussion unpin check failed: {error}")


def main() -> None:
    validate_environment()

    # Remove any older automatically pinned channel post, even when
    # this run does not find a new story to publish.
    unpin_automatic_discussion_post(max_attempts=1, delay_seconds=0)
    seen = load_seen_articles()
    articles = collect_articles()
    candidates = [
        article
        for article in articles
        if article["id"] not in seen and article["score"] > 0 and is_recent(article)
    ][:MAX_AI_CANDIDATES]

    print(f"Found {len(candidates)} relevant new candidate(s).")
    editorial_results = edit_batch_with_ai(candidates)
    published = 0

    for editorial in editorial_results:
        article = candidates[editorial["index"]]
        article["headline"] = editorial["headline"]
        article["short_summary"] = editorial["summary"]
        print(f"Publishing: {article['headline']}")
        try:
            send_to_telegram(build_message(article), article["link"])

            # Telegram may need a few seconds to forward and auto-pin
            # the channel post in the linked discussion group.
            unpin_automatic_discussion_post()

            published += 1
            time.sleep(2)
        except requests.RequestException as error:
            print(f"Telegram post failed for {article['title']}: {error}")

    processed_at = time.time()
    for article in articles:
        seen[article["id"]] = processed_at
    save_seen_articles(seen)
    print(f"Published {published} article(s).")


if __name__ == "__main__":
    main()
