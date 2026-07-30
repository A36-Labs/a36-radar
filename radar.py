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

STATE_FILE = Path("seen_articles.json")

MAX_POSTS_PER_RUN = 2
MAX_HISTORY = 5000
ARTICLE_MAX_AGE_HOURS = 36

FEEDS = [
    {
        "name": "TechCrunch Startups",
        "url": "https://techcrunch.com/category/startups/feed/",
        "category": "Startups & Funding",
    },
    {
        "name": "CoinDesk",
        "url": "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "category": "Web3 & Crypto",
    },
    {
        "name": "Cointelegraph",
        "url": "https://cointelegraph.com/rss",
        "category": "Web3 & Crypto",
    },
    {
        "name": "Decrypt",
        "url": "https://decrypt.co/feed",
        "category": "Web3 & Crypto",
    },
]

IMPORTANT_KEYWORDS = {
    # Funding and startups
    "raises",
    "raised",
    "funding",
    "fundraise",
    "fundraising",
    "seed round",
    "series a",
    "series b",
    "series c",
    "venture capital",
    "valuation",
    "invests",
    "investment",
    "backed by",
    "acquires",
    "acquisition",
    "merger",
    "launches",
    "startup",

    # Public markets and IPOs
    "ipo",
    "initial public offering",
    "public listing",
    "files for ipo",
    "stock exchange",
    "nasdaq",
    "nyse",
    "earnings",
    "market cap",

    # AI and frontier technology
    "artificial intelligence",
    "generative ai",
    "foundation model",
    "large language model",
    "open source",
    "developer tools",
    "developer platform",
    "robotics",
    "semiconductor",
    "quantum",
    "cloud infrastructure",

    # Web3 and crypto
    "bitcoin",
    "ethereum",
    "crypto",
    "cryptocurrency",
    "blockchain",
    "web3",
    "stablecoin",
    "tokenization",
    "defi",
    "layer 2",
    "layer-2",
    "mainnet",
    "protocol",
    "wallet",
    "exchange",
    "digital assets",
    "institutional adoption",
    "crypto regulation",
    "sec",
    "etf",
}

HIGH_PRIORITY_KEYWORDS = {
    "raises",
    "raised",
    "funding",
    "acquisition",
    "acquires",
    "merger",
    "ipo",
    "files for ipo",
    "valuation",
    "bitcoin",
    "ethereum",
    "stablecoin",
    "regulation",
    "developer platform",
    "open source",
    "artificial intelligence",
    "foundation model",
}

BLOCKED_KEYWORDS = {
    # Consumer product noise
    "keyboard",
    "mouse",
    "headphones",
    "earbuds",
    "smartwatch",
    "gaming chair",
    "phone case",
    "laptop review",
    "product review",
    "buying guide",
    "discount",
    "coupon",
    "deal of the day",
    "best price",

    # Entertainment and lifestyle
    "celebrity",
    "movie review",
    "tv show",
    "streaming series",
    "trailer",
    "gaming review",
    "video game review",

    # Low-quality crypto content
    "price prediction",
    "could reach",
    "next 100x",
    "moonshot",
    "presale",
    "airdrop guide",
    "buy now",
    "sponsored",
    "partner content",
}

SOURCE_PRIORITY = {
    "TechCrunch Startups": 4,
    "CoinDesk": 5,
    "Cointelegraph": 3,
    "Decrypt": 3,
}


def validate_environment() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is missing.")

    if not CHAT_ID:
        raise RuntimeError("TELEGRAM_CHAT_ID is missing.")


def load_seen_articles() -> set[str]:
    if not STATE_FILE.exists():
        return set()

    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return set(data.get("seen", []))
    except (json.JSONDecodeError, OSError):
        return set()


def save_seen_articles(seen: set[str]) -> None:
    limited_seen = list(seen)[-MAX_HISTORY:]

    STATE_FILE.write_text(
        json.dumps({"seen": limited_seen}, indent=2),
        encoding="utf-8",
    )


def article_id(entry: Any) -> str:
    value = (
        entry.get("link")
        or entry.get("id")
        or entry.get("title", "")
    )

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def publication_timestamp(entry: Any) -> float:
    parsed_time = (
        entry.get("published_parsed")
        or entry.get("updated_parsed")
    )

    if parsed_time:
        return time.mktime(parsed_time)

    return time.time()


def strip_html(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    return " ".join(value.split())


def clean_summary(entry: Any, maximum_length: int = 230) -> str:
    raw_summary = (
        entry.get("summary", "")
        or entry.get("description", "")
    )

    summary = strip_html(raw_summary)

    if len(summary) > maximum_length:
        summary = summary[: maximum_length - 1].rstrip() + "…"

    return summary


def article_text(article: dict[str, Any]) -> str:
    return (
        f"{article['title']} "
        f"{article['summary']} "
        f"{article['category']}"
    ).lower()


def calculate_relevance(article: dict[str, Any]) -> int:
    text = article_text(article)

    if any(keyword in text for keyword in BLOCKED_KEYWORDS):
        return -100

    matches = {
        keyword
        for keyword in IMPORTANT_KEYWORDS
        if keyword in text
    }

    if not matches:
        return -100

    score = len(matches) * 2
    score += SOURCE_PRIORITY.get(article["source"], 0)

    for keyword in HIGH_PRIORITY_KEYWORDS:
        if keyword in text:
            score += 4

    # Prioritise clearly reported deals with numbers.
    if re.search(r"\$\s?\d+|\d+\s?(million|billion)", text):
        score += 3

    # Prefer regulation, institutional adoption and infrastructure.
    strategic_terms = {
        "regulation",
        "institutional",
        "infrastructure",
        "developer",
        "open source",
        "mainnet",
        "sec",
        "etf",
    }

    score += sum(
        2 for term in strategic_terms if term in text
    )

    return score


def is_recent(article: dict[str, Any]) -> bool:
    age_seconds = time.time() - article["timestamp"]
    maximum_age = ARTICLE_MAX_AGE_HOURS * 60 * 60

    return 0 <= age_seconds <= maximum_age


def build_message(article: dict[str, Any]) -> str:
    title = html.escape(article["title"])
    source = html.escape(article["source"])
    category = html.escape(article["category"])
    link = html.escape(article["link"], quote=True)
    summary = html.escape(article["summary"])

    summary_section = f"\n\n{summary}" if summary else ""

    return (
        "📡 <b>A36 RADAR</b>\n\n"
        f"<b>{title}</b>"
        f"{summary_section}\n\n"
        f"◉ {category}\n"
        f"Source: {source}\n\n"
        f'<a href="{link}">Read the full story ↗</a>'
    )


def send_to_telegram(message: str) -> None:
    endpoint = (
        f"https://api.telegram.org/"
        f"bot{BOT_TOKEN}/sendMessage"
    )

    response = requests.post(
        endpoint,
        json={
            "chat_id": CHAT_ID,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        },
        timeout=30,
    )

    response.raise_for_status()

    result = response.json()

    if not result.get("ok"):
        raise RuntimeError(
            f"Telegram rejected the message: {result}"
        )


def collect_articles() -> list[dict[str, Any]]:
    articles: list[dict[str, Any]] = []

    for feed_config in FEEDS:
        print(f"Checking {feed_config['name']}...")

        feed = feedparser.parse(
            feed_config["url"],
            request_headers={
                "User-Agent": "A36Radar/1.0"
            },
        )

        if feed.bozo:
            print(
                f"Feed warning for {feed_config['name']}: "
                f"{feed.bozo_exception}"
            )

        for entry in feed.entries[:15]:
            title = " ".join(
                entry.get("title", "Untitled").split()
            )

            link = entry.get("link", "").strip()

            if not link:
                continue

            article = {
                "id": article_id(entry),
                "title": title,
                "link": link,
                "summary": clean_summary(entry),
                "source": feed_config["name"],
                "category": feed_config["category"],
                "timestamp": publication_timestamp(entry),
            }

            article["score"] = calculate_relevance(article)
            articles.append(article)

    articles.sort(
        key=lambda item: (
            item["score"],
            item["timestamp"],
        ),
        reverse=True,
    )

    return articles


def main() -> None:
    validate_environment()

    seen = load_seen_articles()
    articles = collect_articles()

    eligible_articles = [
        article
        for article in articles
        if article["id"] not in seen
        and article["score"] > 0
        and is_recent(article)
    ]

    print(
        f"Found {len(eligible_articles)} "
        "relevant new article(s)."
    )

    # Mark everything fetched as processed so rejected articles
    # do not repeatedly return during future runs.
    for article in articles:
        seen.add(article["id"])

    posts = eligible_articles[:MAX_POSTS_PER_RUN]

    for article in posts:
        print(
            f"Publishing score {article['score']}: "
            f"{article['title']}"
        )

        send_to_telegram(build_message(article))
        time.sleep(2)

    save_seen_articles(seen)

    print(f"Published {len(posts)} article(s).")


if __name__ == "__main__":
    main()
