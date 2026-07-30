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
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()

STATE_FILE = Path("seen_articles.json")

MAX_POSTS_PER_RUN = 2
MAX_AI_CANDIDATES = 6
ARTICLE_MAX_AGE_HOURS = 36
MAX_HISTORY = 5000

AI_MODEL = "openai/gpt-4o-mini"
AI_ENDPOINT = "https://models.github.ai/inference/chat/completions"


FEEDS = [
    {
        "name": "TechCrunch Startups",
        "url": "https://techcrunch.com/category/startups/feed/",
        "category": "Startups & Funding",
    },
    {
        "name": "TechCrunch AI",
        "url": "https://techcrunch.com/category/artificial-intelligence/feed/",
        "category": "AI & Frontier Tech",
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
    # Startups and capital
    "raises",
    "raised",
    "funding",
    "fundraise",
    "seed round",
    "series a",
    "series b",
    "series c",
    "venture capital",
    "valuation",
    "investment",
    "invests",
    "acquisition",
    "acquires",
    "merger",
    "startup",

    # IPOs and public markets
    "ipo",
    "initial public offering",
    "public listing",
    "files for ipo",
    "nasdaq",
    "nyse",
    "earnings",
    "stock market",
    "public company",

    # AI and technology
    "artificial intelligence",
    "generative ai",
    "foundation model",
    "large language model",
    "developer platform",
    "developer tools",
    "open source",
    "robotics",
    "semiconductor",
    "quantum computing",
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
    "digital assets",
    "crypto regulation",
    "institutional adoption",
    "exchange",
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
    "stablecoin",
    "regulation",
    "institutional adoption",
    "developer platform",
    "open source",
    "foundation model",
}


BLOCKED_KEYWORDS = {
    # Consumer-product noise
    "keyboard",
    "gaming mouse",
    "headphones",
    "earbuds",
    "smartwatch",
    "phone case",
    "product review",
    "buying guide",
    "discount",
    "coupon",
    "deal of the day",

    # Entertainment
    "celebrity",
    "movie review",
    "tv show",
    "trailer",
    "video game review",

    # Low-quality financial content
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
    "TechCrunch Startups": 5,
    "TechCrunch AI": 5,
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
    limited_seen = sorted(seen)[-MAX_HISTORY:]

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

    return hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()


def publication_timestamp(entry: Any) -> float:
    parsed_time = (
        entry.get("published_parsed")
        or entry.get("updated_parsed")
    )

    if parsed_time:
        return float(calendar.timegm(parsed_time))

    return time.time()


def strip_html(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    return " ".join(value.split())


def clean_summary(
    entry: Any,
    maximum_length: int = 900,
) -> str:
    raw_summary = (
        entry.get("summary", "")
        or entry.get("description", "")
    )

    summary = strip_html(raw_summary)

    if len(summary) > maximum_length:
        summary = (
            summary[: maximum_length - 1].rstrip()
            + "…"
        )

    return summary


def limit_words(
    value: str,
    maximum_words: int,
) -> str:
    words = " ".join(value.split()).split()

    if len(words) <= maximum_words:
        return " ".join(words)

    return " ".join(words[:maximum_words]).rstrip(".,:;") + "…"


def fallback_summary(value: str) -> str:
    if not value:
        return ""

    first_sentence = re.split(
        r"(?<=[.!?])\s+",
        value,
        maxsplit=1,
    )[0]

    return limit_words(first_sentence, 24)


def article_text(article: dict[str, Any]) -> str:
    return (
        f"{article['title']} "
        f"{article['summary']} "
        f"{article['category']}"
    ).lower()


def calculate_relevance(
    article: dict[str, Any],
) -> int:
    text = article_text(article)

    if any(
        keyword in text
        for keyword in BLOCKED_KEYWORDS
    ):
        return -100

    matches = {
        keyword
        for keyword in IMPORTANT_KEYWORDS
        if keyword in text
    }

    if not matches:
        return -100

    score = len(matches) * 2
    score += SOURCE_PRIORITY.get(
        article["source"],
        0,
    )

    for keyword in HIGH_PRIORITY_KEYWORDS:
        if keyword in text:
            score += 4

    if re.search(
        r"\$\s?\d+|\d+\s?(million|billion)",
        text,
    ):
        score += 3

    return score


def is_recent(article: dict[str, Any]) -> bool:
    age_seconds = time.time() - article["timestamp"]
    maximum_age = ARTICLE_MAX_AGE_HOURS * 3600

    return 0 <= age_seconds <= maximum_age


def parse_ai_json(content: str) -> dict[str, Any]:
    cleaned = content.strip()

    if cleaned.startswith("```"):
        cleaned = re.sub(
            r"^```(?:json)?\s*",
            "",
            cleaned,
        )
        cleaned = re.sub(
            r"\s*```$",
            "",
            cleaned,
        )

    return json.loads(cleaned)


def fallback_editorial(
    article: dict[str, Any],
) -> dict[str, Any]:
    return {
        "publish": True,
        "headline": limit_words(
            article["title"],
            12,
        ),
        "summary": fallback_summary(
            article["summary"]
        ),
    }


def edit_with_ai(
    article: dict[str, Any],
) -> dict[str, Any] | None:
    """
    Ask GitHub Models to filter and shorten a story.

    Falls back to deterministic shortening if GitHub Models
    is unavailable or rate-limited.
    """
    fallback = fallback_editorial(article)

    if not GITHUB_TOKEN:
        print(
            "GITHUB_TOKEN unavailable. "
            "Using fallback editor."
        )
        return fallback

    system_prompt = """
You are the editor of A36 Radar, a global frontier-technology
news feed.

Decide whether the supplied story is important enough to publish.

Publish stories involving:
- meaningful startup funding or valuations
- acquisitions, mergers or IPOs
- major AI, developer-platform or open-source developments
- Web3 infrastructure, stablecoins or institutional adoption
- significant crypto or technology regulation
- major developments involving public technology companies

Reject:
- product reviews and buying guides
- gaming accessories and minor consumer devices
- entertainment and celebrity stories
- sponsored content
- rumours and unsupported claims
- token promotions, price predictions and investment advice
- minor daily market-price movements

Use only facts explicitly included in the supplied title and summary.
Do not invent names, numbers, context or conclusions.

Return one JSON object only:

{
  "publish": true,
  "headline": "maximum 12 words",
  "summary": "one factual sentence, maximum 24 words"
}

When the story should be rejected, return:

{
  "publish": false,
  "headline": "",
  "summary": ""
}
""".strip()

    article_input = {
        "title": article["title"],
        "summary": article["summary"],
        "source": article["source"],
        "category": article["category"],
    }

    try:
        response = requests.post(
            AI_ENDPOINT,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": (
                    f"Bearer {GITHUB_TOKEN}"
                ),
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
            },
            json={
                "model": AI_MODEL,
                "temperature": 0.1,
                "max_tokens": 140,
                "response_format": {
                    "type": "json_object"
                },
                "messages": [
                    {
                        "role": "system",
                        "content": system_prompt,
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            article_input,
                            ensure_ascii=False,
                        ),
                    },
                ],
            },
            timeout=45,
        )

        response.raise_for_status()
        result = response.json()

        content = (
            result["choices"][0]
            ["message"]["content"]
        )

        editorial = parse_ai_json(content)

        publish = editorial.get("publish")

        if publish is False:
            print(
                f"AI rejected: {article['title']}"
            )
            return None

        if publish is not True:
            raise ValueError(
                "AI returned an invalid publish value."
            )

        headline = limit_words(
            str(editorial.get("headline", "")),
            12,
        )

        summary = limit_words(
            str(editorial.get("summary", "")),
            24,
        )

        if not headline:
            headline = fallback["headline"]

        if not summary:
            summary = fallback["summary"]

        return {
            "publish": True,
            "headline": headline,
            "summary": summary,
        }

    except (
        requests.RequestException,
        KeyError,
        IndexError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) as error:
        print(
            f"AI editor unavailable: {error}. "
            "Using fallback editor."
        )
        return fallback


def build_message(
    article: dict[str, Any],
) -> str:
    headline = html.escape(
        article["headline"]
    )

    summary = html.escape(
        article["short_summary"]
    )

    category = html.escape(
        article["category"]
    )

    source = html.escape(
        article["source"]
    )

    link = html.escape(
        article["link"],
        quote=True,
    )

    summary_line = (
        f"\n{summary}"
        if summary
        else ""
    )

    return (
        "📡 <b>A36 RADAR</b>\n\n"
        f"<b>{headline}</b>"
        f"{summary_line}\n\n"
        f"{category} · {source}\n"
        f'<a href="{link}">Read ↗</a>'
    )


def send_to_telegram(message: str, link: str) -> None:
    endpoint = (
        "https://api.telegram.org/"
        f"bot{BOT_TOKEN}/sendMessage"
    )

    response = requests.post(
        endpoint,
        json={
            "chat_id": CHAT_ID,
            "text": message,
            "parse_mode": "HTML",

            # Keep Telegram posts compact by removing
            # the large image and article preview card.
            "link_preview_options": {
    "is_disabled": False,
    "url": link,
    "prefer_small_media": True,
    "prefer_large_media": False,
    "show_above_text": False,
},
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
        print(
            f"Checking {feed_config['name']}..."
        )

        feed = feedparser.parse(
            feed_config["url"],
            request_headers={
                "User-Agent": "A36Radar/2.0"
            },
        )

        if feed.bozo:
            print(
                f"Feed warning for "
                f"{feed_config['name']}: "
                f"{feed.bozo_exception}"
            )

        for entry in feed.entries[:15]:
            title = " ".join(
                entry.get(
                    "title",
                    "Untitled",
                ).split()
            )

            link = entry.get(
                "link",
                "",
            ).strip()

            if not link:
                continue

            article = {
                "id": article_id(entry),
                "title": title,
                "link": link,
                "summary": clean_summary(entry),
                "source": feed_config["name"],
                "category": feed_config["category"],
                "timestamp": publication_timestamp(
                    entry
                ),
            }

            article["score"] = (
                calculate_relevance(article)
            )

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

    candidates = [
        article
        for article in articles
        if article["id"] not in seen
        and article["score"] > 0
        and is_recent(article)
    ]

    print(
        f"Found {len(candidates)} "
        "relevant new candidate(s)."
    )

    # Mark fetched articles as processed so rejected stories
    # do not return during every future workflow run.
    for article in articles:
        seen.add(article["id"])

    published = 0

    for article in candidates[:MAX_AI_CANDIDATES]:
        if published >= MAX_POSTS_PER_RUN:
            break

        editorial = edit_with_ai(article)

        if editorial is None:
            continue

        article["headline"] = editorial["headline"]
        article["short_summary"] = editorial["summary"]

        print(
            f"Publishing: "
            f"{article['headline']}"
        )

       send_to_telegram(
    build_message(article),
    article["link"],
)

        published += 1
        time.sleep(2)

    save_seen_articles(seen)

    print(
        f"Published {published} article(s)."
    )


if __name__ == "__main__":
    main()
