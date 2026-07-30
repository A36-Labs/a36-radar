import hashlib
import html
import json
import os
import time
from pathlib import Path
from typing import Any

import feedparser
import requests


BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

STATE_FILE = Path("seen_articles.json")
MAX_POSTS_PER_RUN = 3

# Start with reliable, broad sources. More can be added later.
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
        "name": "The Verge",
        "url": "https://www.theverge.com/rss/index.xml",
        "category": "Technology",
    },
]


def validate_environment() -> None:
    """Stop safely when required GitHub Secrets are missing."""
    if not BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is missing.")
    if not CHAT_ID:
        raise RuntimeError("TELEGRAM_CHAT_ID is missing.")


def load_seen_articles() -> set[str]:
    """Load IDs of previously processed articles."""
    if not STATE_FILE.exists():
        return set()

    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return set(data.get("seen", []))
    except (json.JSONDecodeError, OSError):
        return set()


def save_seen_articles(seen: set[str]) -> None:
    """Keep a limited history so the state file stays small."""
    limited_seen = list(seen)[-3000:]
    STATE_FILE.write_text(
        json.dumps({"seen": limited_seen}, indent=2),
        encoding="utf-8",
    )


def article_id(entry: Any) -> str:
    """Create a stable ID from the article link or title."""
    value = entry.get("link") or entry.get("id") or entry.get("title", "")
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def publication_timestamp(entry: Any) -> float:
    """Return the article publication timestamp when available."""
    parsed_time = entry.get("published_parsed") or entry.get("updated_parsed")

    if parsed_time:
        return time.mktime(parsed_time)

    return 0.0


def clean_summary(entry: Any, maximum_length: int = 260) -> str:
    """Create a short plain-text summary from an RSS entry."""
    raw_summary = entry.get("summary", "") or entry.get("description", "")

    # Basic removal of HTML tags without adding another dependency.
    inside_tag = False
    characters: list[str] = []

    for character in raw_summary:
        if character == "<":
            inside_tag = True
            continue
        if character == ">":
            inside_tag = False
            continue
        if not inside_tag:
            characters.append(character)

    summary = html.unescape("".join(characters))
    summary = " ".join(summary.split())

    if len(summary) > maximum_length:
        summary = summary[: maximum_length - 1].rstrip() + "…"

    return summary


def build_message(article: dict[str, Any]) -> str:
    """Create the Telegram post."""
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
    """Publish one message through the Telegram Bot API."""
    endpoint = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

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
        raise RuntimeError(f"Telegram rejected the message: {result}")


def collect_articles() -> list[dict[str, Any]]:
    """Fetch and combine articles from all configured feeds."""
    articles: list[dict[str, Any]] = []

    for feed_config in FEEDS:
        print(f"Checking {feed_config['name']}...")

        feed = feedparser.parse(feed_config["url"])

        if feed.bozo:
            print(
                f"Warning: feed issue for {feed_config['name']}: "
                f"{feed.bozo_exception}"
            )

        for entry in feed.entries[:10]:
            title = " ".join(entry.get("title", "Untitled").split())
            link = entry.get("link", "").strip()

            if not link:
                continue

            articles.append(
                {
                    "id": article_id(entry),
                    "title": title,
                    "link": link,
                    "summary": clean_summary(entry),
                    "source": feed_config["name"],
                    "category": feed_config["category"],
                    "timestamp": publication_timestamp(entry),
                }
            )

    # Newest stories first.
    articles.sort(key=lambda item: item["timestamp"], reverse=True)
    return articles


def main() -> None:
    validate_environment()

    seen = load_seen_articles()
    articles = collect_articles()

    new_articles = [
        article for article in articles if article["id"] not in seen
    ]

    print(f"Found {len(new_articles)} new article(s).")

    # Mark every fetched article as seen, including stories beyond the posting
    # limit. This prevents an old backlog from being posted on later runs.
    for article in articles:
        seen.add(article["id"])

    posts = new_articles[:MAX_POSTS_PER_RUN]

    for article in posts:
        print(f"Publishing: {article['title']}")
        send_to_telegram(build_message(article))
        time.sleep(2)

    save_seen_articles(seen)
    print(f"Published {len(posts)} article(s).")


if __name__ == "__main__":
    main()
