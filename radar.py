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
    "RSS_USER_AGENT",
    "A36 Radar/1.0 (+https://a36labs.com)",
).strip()

STATE_FILE = Path("seen_articles.json")

MAX_POSTS_PER_RUN = 2
MAX_AI_CANDIDATES = 20
MAX_HISTORY = 7000
ARTICLE_MAX_AGE_HOURS = 24
REQUEST_TIMEOUT_SECONDS = 35
MIN_RELEVANCE_SCORE = 8

AI_MODEL = "openai/gpt-4o-mini"
AI_ENDPOINT = "https://models.github.ai/inference/chat/completions"


# mode controls the hard scope rules applied to each feed.
FEEDS = [
    {
        "name": "TechCrunch Startups",
        "url": "https://techcrunch.com/category/startups/feed/",
        "category": "Tech Funding",
        "mode": "startup",
    },
    {
        "name": "TechCrunch AI",
        "url": "https://techcrunch.com/category/artificial-intelligence/feed/",
        "category": "AI & Frontier Tech",
        "mode": "tech",
    },
    {
        "name": "Crunchbase News",
        "url": "https://news.crunchbase.com/feed/",
        "category": "Tech Funding",
        "mode": "startup",
    },
    {
        "name": "VentureBeat AI",
        "url": "https://venturebeat.com/category/ai/feed/",
        "category": "AI & Frontier Tech",
        "mode": "tech",
    },
    {
        "name": "a16z",
        "url": "https://a16z.com/feed/",
        "category": "VC & Accelerators",
        "mode": "vc",
    },
    {
        "name": "Y Combinator",
        "url": "https://www.ycombinator.com/blog/rss",
        "category": "VC & Accelerators",
        "mode": "vc",
    },
    {
        "name": "CoinDesk",
        "url": "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "category": "Web3 & Crypto",
        "mode": "crypto",
    },
    {
        "name": "Cointelegraph",
        "url": "https://cointelegraph.com/rss",
        "category": "Web3 & Crypto",
        "mode": "crypto",
    },
    {
        "name": "Decrypt",
        "url": "https://decrypt.co/feed",
        "category": "Web3 & Crypto",
        "mode": "crypto",
    },
    {
        "name": "BBC Business",
        "url": "https://feeds.bbci.co.uk/news/business/rss.xml",
        "category": "Global Tech Markets",
        "mode": "tech_market",
    },
    {
        "name": "The Guardian Business",
        "url": "https://www.theguardian.com/business/rss",
        "category": "Global Tech Markets",
        "mode": "tech_market",
    },
    {
        "name": "SEC Press Releases",
        "url": "https://www.sec.gov/news/pressreleases.rss",
        "category": "Markets & Regulation",
        "mode": "regulation",
    },
    {
        "name": "HKEX News Releases",
        "url": "https://www.hkexgroup.com/Global/RSS-Feed/NewsRelease?sc_lang=en",
        "category": "Global Tech Markets",
        "mode": "exchange",
    },
    {
        "name": "Nasdaq Europe Main Markets",
        "url": "https://api.news.eu.nasdaq.com/news/rss/mainMarketNotices",
        "category": "Global Tech Markets",
        "mode": "exchange",
    },
]

SOURCE_PRIORITY = {
    "TechCrunch Startups": 8,
    "TechCrunch AI": 7,
    "Crunchbase News": 9,
    "VentureBeat AI": 7,
    "a16z": 9,
    "Y Combinator": 9,
    "CoinDesk": 8,
    "Cointelegraph": 4,
    "Decrypt": 5,
    "BBC Business": 5,
    "The Guardian Business": 4,
    "SEC Press Releases": 7,
    "HKEX News Releases": 5,
    "Nasdaq Europe Main Markets": 5,
}

CATEGORY_EMOJIS = {
    "Tech Funding": "💸",
    "VC & Accelerators": "🛰️",
    "AI & Frontier Tech": "🧠",
    "Web3 & Crypto": "⛓️",
    "Global Tech Markets": "📈",
    "Markets & Regulation": "🏛️",
}


def terms(value: str) -> set[str]:
    return {
        item.strip().lower()
        for item in value.split("|")
        if item.strip()
    }


TECH_KEYWORDS = terms(
    "technology|tech company|software|saas|enterprise software|artificial intelligence|"
    "generative ai|foundation model|large language model|ai model|machine learning|"
    "developer platform|developer tools|devtools|open source|cybersecurity|fintech|"
    "healthtech|biotech|climate tech|cleantech|deep tech|defense tech|space tech|"
    "robotics|automation|semiconductor|chipmaker|chips|quantum computing|cloud|"
    "cloud infrastructure|data center|data infrastructure|database|api|payments|"
    "digital health|mobility|autonomous vehicles|electric vehicle|startup"
)

FUNDING_KEYWORDS = terms(
    "raises|raised|funding|fundraise|fundraising|seed round|pre-seed|series a|"
    "series b|series c|series d|growth round|venture capital|vc funding|valuation|"
    "investment|invests|invested|backed by|lead investor|strategic investment|"
    "acquisition|acquires|acquired|merger|takeover|buyout|exit|new fund|venture fund|"
    "fund close|capital raise|portfolio company"
)

ACCELERATOR_KEYWORDS = terms(
    "accelerator|incubator|demo day|startup batch|batch|cohort|startup school|"
    "y combinator|yc|a16z|andreessen horowitz|sequoia|accel|techstars|antler|"
    "500 global|founders fund|general catalyst|lightspeed|index ventures|"
    "venture partner|general partner|portfolio|investment thesis"
)

CRYPTO_KEYWORDS = terms(
    "bitcoin|ethereum|crypto|cryptocurrency|blockchain|web3|stablecoin|tokenization|"
    "defi|layer 2|layer-2|mainnet|protocol|wallet|digital assets|crypto exchange|"
    "institutional adoption|crypto regulation|spot etf|etf|staking|rollup|"
    "real-world assets|rwa|onchain|on-chain"
)

MARKET_EVENT_KEYWORDS = terms(
    "earnings|revenue|profit|guidance|forecast|ipo|initial public offering|"
    "ipo filing|files for ipo|public listing|market debut|new listing|secondary offering|"
    "shares|stock|equities|public markets|market cap|acquisition|merger|investment|"
    "stake|buyback|strategic review|spin-off|spinoff|sec filing|regulation|"
    "rate cut|rate hike|central bank|antitrust"
)

REGULATION_KEYWORDS = terms(
    "sec|regulation|regulator|policy|law|legislation|enforcement|approval|approved|"
    "filing|disclosure|compliance|antitrust|competition authority|etf"
)

HIGH_PRIORITY_KEYWORDS = terms(
    "raises|raised|funding|seed round|series a|series b|series c|valuation|"
    "acquisition|acquires|merger|ipo|ipo filing|market debut|public listing|"
    "new fund|fund close|demo day|startup batch|stablecoin|institutional adoption|"
    "developer platform|open source|foundation model|earnings|guidance"
)

BLOCKED_KEYWORDS = terms(
    "keyboard|gaming mouse|headphones|earbuds|smartwatch|phone case|product review|"
    "buying guide|discount|coupon|deal of the day|best price|celebrity|movie review|"
    "tv show|trailer|video game review|gaming review|price prediction|could reach|"
    "next 100x|moonshot|presale|airdrop guide|buy now|sponsored|partner content|"
    "stock picks|stocks to buy|analyst picks|daily price|price target|technical analysis|"
    "top gainers|top losers|market live|live updates|should you buy|buy sell or hold"
)

STOP_WORDS = terms(
    "a|an|and|are|as|at|be|by|for|from|has|have|in|is|it|its|of|on|or|"
    "that|the|this|to|with"
)


def contains_any(text: str, keywords: set[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def validate_environment() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is missing.")
    if not CHAT_ID:
        raise RuntimeError("TELEGRAM_CHAT_ID is missing.")


def load_seen_articles() -> dict[str, float]:
    if not STATE_FILE.exists():
        return {}

    try:
        stored = json.loads(
            STATE_FILE.read_text(encoding="utf-8")
        ).get("seen", {})

        if isinstance(stored, dict):
            return {
                str(key): float(value)
                for key, value in stored.items()
            }

        if isinstance(stored, list):
            return {
                str(item): 0.0
                for item in stored
            }

    except (
        OSError,
        ValueError,
        TypeError,
        json.JSONDecodeError,
    ) as error:
        print(
            f"State warning: {error}. "
            "Starting with an empty history."
        )

    return {}


def save_seen_articles(seen: dict[str, float]) -> None:
    newest = sorted(
        seen.items(),
        key=lambda item: item[1],
        reverse=True,
    )[:MAX_HISTORY]

    STATE_FILE.write_text(
        json.dumps(
            {"seen": dict(newest)},
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def stable_article_id(entry: Any) -> str:
    value = (
        entry.get("link")
        or entry.get("id")
        or entry.get("title", "")
    )

    return hashlib.sha256(
        str(value).encode("utf-8")
    ).hexdigest()


def publication_timestamp(entry: Any) -> float:
    parsed = (
        entry.get("published_parsed")
        or entry.get("updated_parsed")
    )

    return (
        float(calendar.timegm(parsed))
        if parsed
        else time.time()
    )


def strip_html(value: str) -> str:
    value = re.sub(
        r"<script\b[^>]*>.*?</script>",
        " ",
        value,
        flags=re.I | re.S,
    )
    value = re.sub(
        r"<style\b[^>]*>.*?</style>",
        " ",
        value,
        flags=re.I | re.S,
    )
    value = re.sub(r"<[^>]+>", " ", value)

    return " ".join(
        html.unescape(value).split()
    )


def clean_summary(
    entry: Any,
    maximum_length: int = 1000,
) -> str:
    summary = strip_html(
        str(
            entry.get("summary", "")
            or entry.get("description", "")
        )
    )

    if len(summary) <= maximum_length:
        return summary

    return (
        summary[: maximum_length - 1].rstrip()
        + "…"
    )


def normalize_title(value: str) -> str:
    value = re.sub(
        r"[^a-z0-9\s]",
        " ",
        html.unescape(value).lower(),
    )

    return " ".join(value.split())


def title_tokens(value: str) -> set[str]:
    return {
        token
        for token in normalize_title(value).split()
        if len(token) > 2
        and token not in STOP_WORDS
    }


def titles_are_similar(
    first: str,
    second: str,
    threshold: float = 0.62,
) -> bool:
    first_tokens = title_tokens(first)
    second_tokens = title_tokens(second)

    if not first_tokens or not second_tokens:
        return False

    return (
        len(first_tokens & second_tokens)
        / len(first_tokens | second_tokens)
        >= threshold
    )


def limit_words(
    value: str,
    maximum_words: int,
) -> str:
    words = " ".join(value.split()).split()

    if len(words) <= maximum_words:
        return " ".join(words)

    return (
        " ".join(words[:maximum_words])
        .rstrip(".,:;")
        + "…"
    )


def fallback_summary(value: str) -> str:
    if not value:
        return ""

    first_sentence = re.split(
        r"(?<=[.!?])\s+",
        value,
        maxsplit=1,
    )[0]

    return limit_words(
        first_sentence,
        18,
    )


def passes_editorial_scope(
    article: dict[str, Any],
) -> bool:
    text = (
        f"{article['title']} "
        f"{article['summary']}"
    ).lower()

    if contains_any(text, BLOCKED_KEYWORDS):
        return False

    mode = article["mode"]

    has_tech = contains_any(text, TECH_KEYWORDS)
    has_funding = contains_any(text, FUNDING_KEYWORDS)
    has_accelerator = contains_any(
        text,
        ACCELERATOR_KEYWORDS,
    )
    has_crypto = contains_any(text, CRYPTO_KEYWORDS)
    has_market_event = contains_any(
        text,
        MARKET_EVENT_KEYWORDS,
    )
    has_regulation = contains_any(
        text,
        REGULATION_KEYWORDS,
    )

    if mode == "startup":
        return has_funding and has_tech

    if mode == "tech":
        return has_tech and (
            has_funding
            or has_market_event
            or has_accelerator
        )

    if mode == "vc":
        return has_accelerator and (
            has_funding
            or has_tech
            or has_crypto
        )

    if mode == "crypto":
        return has_crypto and (
            has_funding
            or has_market_event
            or has_regulation
            or has_tech
        )

    if mode == "tech_market":
        return (
            (has_tech or has_crypto)
            and has_market_event
        )

    if mode == "regulation":
        return (
            has_regulation
            and (has_tech or has_crypto)
        )

    if mode == "exchange":
        return (
            (has_tech or has_crypto)
            and (
                has_market_event
                or has_funding
            )
        )

    return False


def calculate_relevance(
    article: dict[str, Any],
) -> int:
    if not passes_editorial_scope(article):
        return -100

    text = (
        f"{article['title']} "
        f"{article['summary']} "
        f"{article['category']}"
    ).lower()

    score = SOURCE_PRIORITY.get(
        article["source"],
        0,
    )

    score += sum(
        2
        for keyword in TECH_KEYWORDS
        if keyword in text
    )

    score += sum(
        3
        for keyword in FUNDING_KEYWORDS
        if keyword in text
    )

    score += sum(
        3
        for keyword in ACCELERATOR_KEYWORDS
        if keyword in text
    )

    score += sum(
        3
        for keyword in CRYPTO_KEYWORDS
        if keyword in text
    )

    score += sum(
        2
        for keyword in MARKET_EVENT_KEYWORDS
        if keyword in text
    )

    score += sum(
        4
        for keyword in HIGH_PRIORITY_KEYWORDS
        if keyword in text
    )

    if re.search(
        r"\$\s?\d+|"
        r"\d+(?:\.\d+)?\s?"
        r"(?:million|billion|trillion)",
        text,
    ):
        score += 5

    return score


def is_recent(
    article: dict[str, Any],
) -> bool:
    age = (
        time.time()
        - float(article["timestamp"])
    )

    return (
        0
        <= age
        <= ARTICLE_MAX_AGE_HOURS * 3600
    )


def fetch_feed(
    feed_config: dict[str, str],
) -> list[dict[str, Any]]:
    headers = {
        "User-Agent": RSS_USER_AGENT,
        "Accept": (
            "application/rss+xml, "
            "application/atom+xml, "
            "application/xml, "
            "text/xml, */*"
        ),
    }

    try:
        response = requests.get(
            feed_config["url"],
            headers=headers,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()

    except requests.RequestException as error:
        print(
            f"Feed skipped "
            f"({feed_config['name']}): {error}"
        )
        return []

    parsed = feedparser.parse(
        response.content
    )

    if parsed.bozo:
        print(
            f"Feed warning "
            f"({feed_config['name']}): "
            f"{getattr(parsed, 'bozo_exception', 'unknown parse issue')}"
        )

    articles: list[dict[str, Any]] = []

    for entry in parsed.entries[:25]:
        title = " ".join(
            str(
                entry.get(
                    "title",
                    "Untitled",
                )
            ).split()
        )

        link = str(
            entry.get("link", "")
        ).strip()

        if not link or title == "Untitled":
            continue

        article = {
            "id": stable_article_id(entry),
            "title": title,
            "link": link,
            "summary": clean_summary(entry),
            "source": feed_config["name"],
            "category": feed_config["category"],
            "mode": feed_config["mode"],
            "timestamp": publication_timestamp(
                entry
            ),
        }

        article["score"] = (
            calculate_relevance(article)
        )

        articles.append(article)

    return articles


def collect_articles() -> list[dict[str, Any]]:
    combined: list[dict[str, Any]] = []

    for feed_config in FEEDS:
        print(
            f"Checking "
            f"{feed_config['name']}..."
        )

        combined.extend(
            fetch_feed(feed_config)
        )

    combined.sort(
        key=lambda item: (
            item["score"],
            item["timestamp"],
        ),
        reverse=True,
    )

    accepted: list[dict[str, Any]] = []
    seen_links: set[str] = set()

    for article in combined:
        if article["link"] in seen_links:
            continue

        if any(
            titles_are_similar(
                article["title"],
                existing["title"],
            )
            for existing in accepted
        ):
            continue

        accepted.append(article)
        seen_links.add(article["link"])

    return accepted


def parse_ai_json(
    content: str,
) -> dict[str, Any]:
    content = re.sub(
        r"^```(?:json)?\s*",
        "",
        content.strip(),
    )
    content = re.sub(
        r"\s*```$",
        "",
        content,
    )

    return json.loads(content)


def fallback_editorial(
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            "index": index,
            "headline": limit_words(
                article["title"],
                10,
            ),
            "summary": fallback_summary(
                article["summary"]
            ),
        }
        for index, article
        in enumerate(
            candidates[:MAX_POSTS_PER_RUN]
        )
    ]


def edit_batch_with_ai(
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    fallback = fallback_editorial(
        candidates
    )

    if not candidates:
        return []

    if not GITHUB_TOKEN:
        print(
            "GITHUB_TOKEN unavailable. "
            "Using the fallback editor."
        )
        return fallback

    system_prompt = """
You are the editor of A36 Radar, a global tech, venture and digital-assets news feed.

Select at most two extremely recent, high-signal stories.

A story should normally fall into one of these areas:
1. Technology startup funding, valuations, acquisitions, mergers or IPOs.
2. Investments, funds, demo days or portfolio announcements from firms such as
   a16z, Y Combinator, Accel, Sequoia, Techstars, Antler, General Catalyst,
   Lightspeed, Index Ventures, Founders Fund and other major accelerators or VCs.
3. Important AI, developer tools, open source, cybersecurity, fintech, robotics,
   cloud, semiconductors, biotech, climate tech, space tech or deep-tech developments.
4. Web3 and crypto funding, infrastructure, stablecoins, tokenization,
   institutional adoption, regulation, ETFs, protocols or major acquisitions.
5. Material stock-market developments involving technology or crypto companies,
   including earnings, guidance, listings, IPO filings, strategic investments and M&A.

Reject:
- general politics, lifestyle, entertainment and unrelated business news
- ordinary market moves, daily price updates and live market blogs
- stock tips, analyst picks, price targets and investment recommendations
- token-price predictions, airdrop promotions and sponsored content
- minor product launches, reviews, gadgets and consumer deals
- routine exchange notices with no clear technology or investment significance
- opinion pieces without a concrete new development
- duplicate coverage of the same event

Prefer different categories and different publications when two stories are selected.
Use only supplied facts. Never invent details or give investment advice.

Return JSON only:
{
  "stories": [
    {
      "index": 0,
      "headline": "maximum 10 words",
      "summary": "one factual sentence, maximum 18 words"
    }
  ]
}

Return an empty stories array when nothing is strong enough.
""".strip()

    candidates_payload = [
        {
            "index": index,
            "title": article["title"],
            "summary": article["summary"],
            "source": article["source"],
            "category": article["category"],
            "score": article["score"],
        }
        for index, article
        in enumerate(candidates)
    ]

    try:
        response = requests.post(
            AI_ENDPOINT,
            headers={
                "Accept": (
                    "application/vnd.github+json"
                ),
                "Authorization": (
                    f"Bearer {GITHUB_TOKEN}"
                ),
                "X-GitHub-Api-Version": (
                    "2022-11-28"
                ),
                "Content-Type": (
                    "application/json"
                ),
            },
            json={
                "model": AI_MODEL,
                "temperature": 0.1,
                "max_tokens": 450,
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
                            {
                                "candidates":
                                    candidates_payload
                            },
                            ensure_ascii=False,
                        ),
                    },
                ],
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )

        response.raise_for_status()

        content = (
            response.json()
            ["choices"][0]
            ["message"]["content"]
        )

        stories = parse_ai_json(
            content
        ).get("stories", [])

        if not isinstance(stories, list):
            raise ValueError(
                "AI response did not "
                "contain a stories list."
            )

        results: list[dict[str, Any]] = []
        used_indices: set[int] = set()

        for story in stories:
            if len(results) >= MAX_POSTS_PER_RUN:
                break

            index = int(
                story.get("index", -1)
            )

            if (
                index < 0
                or index >= len(candidates)
                or index in used_indices
            ):
                continue

            headline = limit_words(
                str(
                    story.get(
                        "headline",
                        "",
                    )
                ),
                10,
            )

            summary = limit_words(
                str(
                    story.get(
                        "summary",
                        "",
                    )
                ),
                18,
            )

            if not headline:
                headline = limit_words(
                    candidates[index]["title"],
                    10,
                )

            if not summary:
                summary = fallback_summary(
                    candidates[index]["summary"]
                )

            results.append(
                {
                    "index": index,
                    "headline": headline,
                    "summary": summary,
                }
            )
            used_indices.add(index)

        return results

    except (
        requests.RequestException,
        KeyError,
        IndexError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) as error:
        print(
            f"AI editor unavailable: "
            f"{error}. "
            "Using the fallback editor."
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

    emoji = CATEGORY_EMOJIS.get(
        article["category"],
        "📡",
    )

    summary_line = (
        f"\n{summary}"
        if summary
        else ""
    )

    return (
        "⚡️ <b>A36 RADAR</b>\n\n"
        f"<b>{headline}</b>"
        f"{summary_line}\n\n"
        f"{emoji} {category} · "
        f'<a href="{link}">'
        f"{source} ↗"
        "</a>"
    )


def send_to_telegram(
    message: str,
    link: str,
) -> None:
    response = requests.post(
        (
            "https://api.telegram.org/"
            f"bot{BOT_TOKEN}/sendMessage"
        ),
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
        raise RuntimeError(
            f"Telegram rejected "
            f"the message: {result}"
        )


def unpin_automatic_discussion_post(
    max_attempts: int = 5,
    delay_seconds: int = 4,
) -> None:
    """Unpin a linked-channel forward while preserving manual pins."""
    if not DISCUSSION_CHAT_ID:
        print(
            "TELEGRAM_DISCUSSION_CHAT_ID "
            "is missing. Skipping unpin."
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
                json={
                    "chat_id":
                        DISCUSSION_CHAT_ID
                },
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            payload = response.json()

            if not payload.get("ok"):
                print(
                    "Could not read "
                    f"discussion group: {payload}"
                )
                return

            pinned_message = (
                payload.get("result", {})
                .get("pinned_message")
            )

            if not pinned_message:
                print(
                    "No pinned message found "
                    "in the discussion group."
                )
                return

            if pinned_message.get(
                "is_automatic_forward",
                False,
            ):
                message_id = (
                    pinned_message.get(
                        "message_id"
                    )
                )

                if not message_id:
                    print(
                        "Automatic forward has "
                        "no message_id."
                    )
                    return

                unpin_response = requests.post(
                    unpin_url,
                    json={
                        "chat_id":
                            DISCUSSION_CHAT_ID,
                        "message_id":
                            message_id,
                    },
                    timeout=REQUEST_TIMEOUT_SECONDS,
                )
                unpin_response.raise_for_status()
                unpin_payload = (
                    unpin_response.json()
                )

                if unpin_payload.get("ok"):
                    print(
                        "Unpinned the "
                        "automatically forwarded "
                        "channel post."
                    )
                else:
                    print(
                        "Could not unpin "
                        f"discussion post: "
                        f"{unpin_payload}"
                    )
                return

            if attempt == max_attempts - 1:
                print(
                    "Current pinned message is "
                    "manual. Leaving it pinned."
                )

        except requests.RequestException as error:
            if attempt == max_attempts - 1:
                print(
                    "Discussion unpin check "
                    f"failed: {error}"
                )


def main() -> None:
    validate_environment()

    unpin_automatic_discussion_post(
        max_attempts=1,
        delay_seconds=0,
    )

    seen = load_seen_articles()
    articles = collect_articles()

    candidates = [
        article
        for article in articles
        if article["id"] not in seen
        and article["score"] >= MIN_RELEVANCE_SCORE
        and is_recent(article)
    ][:MAX_AI_CANDIDATES]

    print(
        f"Found {len(candidates)} "
        "relevant new candidate(s)."
    )

    editorial_results = (
        edit_batch_with_ai(candidates)
    )

    published = 0

    for editorial in editorial_results:
        article = candidates[
            editorial["index"]
        ]

        article["headline"] = (
            editorial["headline"]
        )
        article["short_summary"] = (
            editorial["summary"]
        )
        article[
            "published_successfully"
        ] = False

        print(
            f"Publishing: "
            f"{article['headline']}"
        )

        try:
            send_to_telegram(
                build_message(article),
                article["link"],
            )

            article[
                "published_successfully"
            ] = True
            published += 1

            unpin_automatic_discussion_post()
            time.sleep(2)

        except (
            requests.RequestException,
            RuntimeError,
        ) as error:
            print(
                "Telegram post failed for "
                f"{article['title']}: "
                f"{error}"
            )

    processed_at = time.time()

    selected_candidate_ids = {
        candidates[
            result["index"]
        ]["id"]
        for result in editorial_results
    }

    successfully_posted_ids = {
        article["id"]
        for article in candidates
        if article.get(
            "published_successfully",
            False,
        )
    }

    for article in articles:
        if (
            article["score"] < MIN_RELEVANCE_SCORE
            or not is_recent(article)
        ):
            seen[article["id"]] = processed_at

    for article in candidates:
        if (
            article["id"]
            not in selected_candidate_ids
            or article["id"]
            in successfully_posted_ids
        ):
            seen[article["id"]] = processed_at

    save_seen_articles(seen)

    print(
        f"Published {published} article(s)."
    )


if __name__ == "__main__":
    main()
