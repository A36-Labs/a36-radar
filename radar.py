from __future__ import annotations

import calendar
import hashlib
import html
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import feedparser
import requests


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
DISCUSSION_CHAT_ID = os.environ.get("TELEGRAM_DISCUSSION_CHAT_ID", "").strip()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = (
    os.environ.get("GEMINI_MODEL", "").strip() or "gemini-3.1-flash-lite"
)
RSS_USER_AGENT = (
    os.environ.get("RSS_USER_AGENT", "").strip()
    or "A36 Radar/2.0 (+https://a36labs.com; contact: hello@a36labs.com)"
)
FORCE_POST = os.environ.get("FORCE_POST", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
DRY_RUN = os.environ.get("DRY_RUN", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

STATE_FILE = Path("seen_articles.json")


# ---------------------------------------------------------------------------
# Operating rules
# ---------------------------------------------------------------------------

MAX_POSTS_PER_RUN = 1
MAX_ENTRIES_PER_FEED = 35
MAX_HISTORY = 9000
MAX_RECENT_TITLES = 120
MAX_RECENT_CATEGORIES = 18
MAX_RECENT_SOURCES = 18

REQUEST_TIMEOUT_SECONDS = 35
ROUTINE_MAX_AGE_HOURS = 14
URGENT_MAX_AGE_HOURS = 4
ROUTINE_COOLDOWN_SECONDS = 55 * 60
URGENT_COOLDOWN_SECONDS = 30 * 60
MINIMUM_POST_GAP_SECONDS = 12 * 60

MIN_ROUTINE_SCORE = 34
MIN_URGENT_SCORE = 70


# ---------------------------------------------------------------------------
# Feeds
# ---------------------------------------------------------------------------


def google_news_url(query: str) -> str:
    return "https://news.google.com/rss/search?" + urlencode(
        {
            "q": query,
            "hl": "en-US",
            "gl": "US",
            "ceid": "US:en",
        }
    )


# Direct publisher feeds provide depth. Google News topic feeds provide breadth
# and make the bot less dependent on any one publisher's RSS endpoint.
FEEDS: list[dict[str, Any]] = [
    {
        "name": "TechCrunch Startups",
        "url": "https://techcrunch.com/category/startups/feed/",
        "hint": "Startups & Funding",
        "priority": 8,
    },
    {
        "name": "TechCrunch AI",
        "url": "https://techcrunch.com/category/artificial-intelligence/feed/",
        "hint": "AI & Agents",
        "priority": 8,
    },
    {
        "name": "Crunchbase News",
        "url": "https://news.crunchbase.com/feed/",
        "hint": "Startups & Funding",
        "priority": 9,
    },
    {
        "name": "VentureBeat AI",
        "url": "https://venturebeat.com/category/ai/feed/",
        "hint": "AI & Agents",
        "priority": 7,
    },
    {
        "name": "Y Combinator",
        "url": "https://www.ycombinator.com/blog/rss",
        "hint": "VC & Accelerators",
        "priority": 8,
    },
    {
        "name": "MIT Technology Review",
        "url": "https://www.technologyreview.com/feed/",
        "hint": "Frontier Tech",
        "priority": 9,
    },
    {
        "name": "Ars Technica",
        "url": "https://feeds.arstechnica.com/arstechnica/index",
        "hint": "Frontier Tech",
        "priority": 8,
    },
    {
        "name": "GitHub Blog",
        "url": "https://github.blog/feed/",
        "hint": "Open Source & DevTools",
        "priority": 9,
    },
    {
        "name": "Stack Overflow Blog",
        "url": "https://stackoverflow.blog/feed/",
        "hint": "Open Source & DevTools",
        "priority": 7,
    },
    {
        "name": "BleepingComputer",
        "url": "https://www.bleepingcomputer.com/feed/",
        "hint": "Cybersecurity & Cloud",
        "priority": 8,
    },
    {
        "name": "The Hacker News",
        "url": "https://feeds.feedburner.com/TheHackersNews",
        "hint": "Cybersecurity & Cloud",
        "priority": 7,
    },
    {
        "name": "CoinDesk",
        "url": "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "hint": "Web3 & Digital Assets",
        "priority": 8,
    },
    {
        "name": "Decrypt",
        "url": "https://decrypt.co/feed",
        "hint": "Web3 & Digital Assets",
        "priority": 6,
    },
    {
        "name": "Cointelegraph",
        "url": "https://cointelegraph.com/rss",
        "hint": "Web3 & Digital Assets",
        "priority": 4,
    },
    {
        "name": "SEC Press Releases",
        "url": "https://www.sec.gov/news/pressreleases.rss",
        "hint": "Policy & Regulation",
        "priority": 8,
    },
    {
        "name": "Google News - AI",
        "url": google_news_url(
            '("artificial intelligence" OR "AI agents" OR "foundation model" OR LLM) '
            '(launch OR release OR funding OR acquisition OR open-source) when:1d'
        ),
        "hint": "AI & Agents",
        "priority": 5,
        "google_news": True,
    },
    {
        "name": "Google News - Startups",
        "url": google_news_url(
            '(startup OR "venture capital") '
            '(funding OR raises OR valuation OR acquisition OR "new fund") when:1d'
        ),
        "hint": "Startups & Funding",
        "priority": 5,
        "google_news": True,
    },
    {
        "name": "Google News - VC",
        "url": google_news_url(
            '(a16z OR Sequoia OR Accel OR Techstars OR Antler OR "Y Combinator" OR accelerator) '
            '(investment OR fund OR cohort OR "demo day") when:1d'
        ),
        "hint": "VC & Accelerators",
        "priority": 5,
        "google_news": True,
    },
    {
        "name": "Google News - Developers",
        "url": google_news_url(
            '("open source" OR GitHub OR "developer tools" OR devtools OR API OR database) '
            '(launch OR release OR funding OR acquisition OR security) when:1d'
        ),
        "hint": "Open Source & DevTools",
        "priority": 5,
        "google_news": True,
    },
    {
        "name": "Google News - Security",
        "url": google_news_url(
            '(cybersecurity OR ransomware OR "data breach" OR "zero-day" OR cloud security) '
            '(attack OR breach OR patch OR funding OR acquisition) when:1d'
        ),
        "hint": "Cybersecurity & Cloud",
        "priority": 5,
        "google_news": True,
    },
    {
        "name": "Google News - Frontier Tech",
        "url": google_news_url(
            '(robotics OR semiconductor OR quantum OR spacetech OR biotech OR climatetech) '
            '(launch OR breakthrough OR funding OR acquisition OR partnership) when:1d'
        ),
        "hint": "Frontier Tech",
        "priority": 5,
        "google_news": True,
    },
    {
        "name": "Google News - Web3",
        "url": google_news_url(
            '(Ethereum OR Bitcoin OR blockchain OR stablecoin OR tokenization OR DeFi OR Web3) '
            '(funding OR launch OR regulation OR acquisition OR partnership) when:1d'
        ),
        "hint": "Web3 & Digital Assets",
        "priority": 5,
        "google_news": True,
    },
    {
        "name": "Google News - Fintech",
        "url": google_news_url(
            '(fintech OR payments OR neobank OR digital banking) '
            '(funding OR launch OR acquisition OR regulation OR partnership) when:1d'
        ),
        "hint": "Fintech & Payments",
        "priority": 5,
        "google_news": True,
    },
    {
        "name": "Google News - Markets",
        "url": google_news_url(
            '(technology OR software OR AI OR crypto) '
            '(IPO OR acquisition OR merger OR earnings OR "public listing" OR bankruptcy) when:1d'
        ),
        "hint": "Markets, IPOs & M&A",
        "priority": 5,
        "google_news": True,
    },
    {
        "name": "Google News - Regulation",
        "url": google_news_url(
            '(AI OR technology OR crypto OR fintech) '
            '(regulation OR regulator OR antitrust OR approval OR ban OR enforcement) when:1d'
        ),
        "hint": "Policy & Regulation",
        "priority": 5,
        "google_news": True,
    },
    {
        "name": "Google News - Builder Ecosystem",
        "url": google_news_url(
            '(developer OR builders OR founders OR "open source") '
            '(hackathon OR grants OR accelerator OR fellowship OR "developer program") when:1d'
        ),
        "hint": "Builder Ecosystem",
        "priority": 5,
        "google_news": True,
    },
]


# ---------------------------------------------------------------------------
# Editorial taxonomy
# ---------------------------------------------------------------------------


def terms(value: str) -> set[str]:
    return {item.strip().lower() for item in value.split("|") if item.strip()}


CATEGORY_RULES: dict[str, set[str]] = {
    "AI & Agents": terms(
        "artificial intelligence|generative ai|genai|ai agent|ai agents|agentic ai|"
        "foundation model|large language model|llm|multimodal model|reasoning model|"
        "machine learning|openai|anthropic|gemini|deepmind|mistral|hugging face|"
        "computer vision|inference|model training|ai safety"
    ),
    "Startups & Funding": terms(
        "startup|startups|seed round|pre-seed|series a|series b|series c|series d|"
        "funding round|fundraise|fundraising|raises|raised|valuation|venture-backed|"
        "unicorn|bootstrapped|scaleup|scale-up"
    ),
    "VC & Accelerators": terms(
        "venture capital|vc firm|venture fund|new fund|fund close|investment fund|"
        "accelerator|incubator|demo day|startup batch|cohort|startup school|"
        "y combinator|a16z|andreessen horowitz|sequoia|accel|techstars|antler|"
        "500 global|founders fund|general catalyst|lightspeed|index ventures"
    ),
    "Open Source & DevTools": terms(
        "open source|open-source|github|gitlab|developer tools|devtools|developer platform|"
        "software development kit|sdk|api platform|database|programming language|"
        "framework|compiler|code editor|ide|observability|devops|developer experience|"
        "package manager|container platform|kubernetes"
    ),
    "Web3 & Digital Assets": terms(
        "bitcoin|ethereum|crypto|cryptocurrency|blockchain|web3|stablecoin|tokenization|"
        "defi|layer 2|layer-2|mainnet|protocol|wallet|digital assets|crypto exchange|"
        "staking|rollup|real-world assets|rwa|onchain|on-chain|solana|zk proof|"
        "zero-knowledge|smart contract"
    ),
    "Cybersecurity & Cloud": terms(
        "cybersecurity|cyber security|ransomware|malware|data breach|security breach|"
        "zero-day|vulnerability|exploit|phishing|cloud security|identity security|"
        "threat intelligence|ddos|supply chain attack|passwordless|cloud infrastructure|"
        "data center|edge computing"
    ),
    "Frontier Tech": terms(
        "robotics|robot|humanoid|semiconductor|chipmaker|chips|gpu|quantum computing|"
        "space tech|spacetech|satellite|rocket|biotech|synthetic biology|healthtech|"
        "climate tech|climatetech|cleantech|deep tech|deeptech|defense tech|"
        "autonomous vehicle|electric vehicle|battery technology|fusion energy"
    ),
    "Fintech & Payments": terms(
        "fintech|payments|payment network|neobank|digital bank|banking platform|"
        "cross-border payments|remittance|embedded finance|buy now pay later|bnpl|"
        "insurtech|wealthtech|open banking|financial infrastructure"
    ),
    "Markets, IPOs & M&A": terms(
        "ipo|initial public offering|ipo filing|files for ipo|public listing|market debut|"
        "acquisition|acquires|acquired|merger|merges|takeover|buyout|bankruptcy|"
        "earnings|revenue|guidance|public markets|shares|stock exchange|spin-off|spinoff|"
        "strategic investment"
    ),
    "Policy & Regulation": terms(
        "regulation|regulator|policy|law|legislation|enforcement|approval|approved|"
        "antitrust|competition authority|compliance|sec|ftc|eu commission|"
        "data protection|privacy law|executive order|licensing regime|sanctions"
    ),
    "Builder Ecosystem": terms(
        "hackathon|developer grant|grants program|builder program|developer program|"
        "fellowship|community program|open source grant|ecosystem fund|developer conference|"
        "startup competition|founder program|campus program|developer community"
    ),
}

CATEGORY_EMOJIS = {
    "AI & Agents": "🧠",
    "Startups & Funding": "🚀",
    "VC & Accelerators": "🛰️",
    "Open Source & DevTools": "🛠️",
    "Web3 & Digital Assets": "⛓️",
    "Cybersecurity & Cloud": "🛡️",
    "Frontier Tech": "🔬",
    "Fintech & Payments": "💳",
    "Markets, IPOs & M&A": "📈",
    "Policy & Regulation": "🏛️",
    "Builder Ecosystem": "🌐",
}

EVENT_KEYWORDS = terms(
    "launch|launches|launched|release|releases|released|announce|announces|announced|"
    "unveil|unveils|unveiled|introduce|introduces|introduced|raises|raised|funding|"
    "invests|invested|investment|acquire|acquires|acquired|acquisition|merge|merger|"
    "partner|partners|partnership|open sources|open-sources|files for|filing|approves|"
    "approved|rejects|rejected|sues|lawsuit|settles|settlement|bans|banned|regulation|"
    "breach|breached|attack|attacked|patch|patched|vulnerability|shutdown|shuts down|"
    "expands|expanded|appoints|appointed|wins|awarded|secures|secured|debuts|debut|"
    "surpasses|cuts|layoffs|bankruptcy|breakthrough|demonstrates|deploys|deployed"
)

HIGH_SIGNAL_KEYWORDS = terms(
    "series a|series b|series c|series d|valuation|acquisition|merger|ipo|ipo filing|"
    "public listing|bankruptcy|new fund|fund close|foundation model|reasoning model|"
    "open source|open-source|zero-day|data breach|ransomware|antitrust|regulatory approval|"
    "stablecoin|tokenization|mainnet|developer platform|breakthrough|strategic partnership"
)

URGENT_KEYWORDS = terms(
    "breaking|acquisition|acquires|merger|files for bankruptcy|bankruptcy|shutdown|"
    "shuts down|data breach|security breach|cyberattack|ransomware|zero-day|"
    "regulator approves|sec approves|sec sues|antitrust lawsuit|ban|banned|"
    "ipo filing|files for ipo|emergency patch|critical vulnerability|major outage|"
    "launches new model|releases new model|open sources model"
)

BLOCKED_KEYWORDS = terms(
    "keyboard|gaming mouse|headphones|earbuds|smartwatch|phone case|product review|"
    "buying guide|discount|coupon|deal of the day|best price|celebrity|movie review|"
    "tv show|trailer|video game review|gaming review|price prediction|could reach|"
    "next 100x|moonshot|presale|airdrop guide|buy now|sponsored|partner content|"
    "stock picks|stocks to buy|analyst picks|daily price|price target|technical analysis|"
    "top gainers|top losers|market live|live updates|should you buy|buy sell or hold|"
    "opinion:|op-ed|podcast transcript|weekly roundup|newsletter roundup|horoscope|"
    "deal alert|shopping guide"
)

STOP_WORDS = terms(
    "a|an|and|are|as|at|be|been|by|for|from|has|have|in|is|it|its|of|on|or|"
    "that|the|this|to|with|will|after|into|over|new|says|said"
)

# Publisher trust is deliberately broad but gives established outlets an edge.
SOURCE_PRIORITY = {
    "Reuters": 10,
    "Bloomberg": 10,
    "Financial Times": 10,
    "The Wall Street Journal": 10,
    "Associated Press": 9,
    "BBC": 8,
    "BBC News": 8,
    "CNBC": 8,
    "TechCrunch": 8,
    "TechCrunch Startups": 8,
    "TechCrunch AI": 8,
    "Crunchbase News": 9,
    "MIT Technology Review": 9,
    "Ars Technica": 8,
    "The Verge": 7,
    "VentureBeat": 7,
    "VentureBeat AI": 7,
    "GitHub Blog": 9,
    "Stack Overflow Blog": 7,
    "BleepingComputer": 8,
    "The Hacker News": 7,
    "CoinDesk": 8,
    "Decrypt": 6,
    "Cointelegraph": 4,
    "Y Combinator": 8,
    "SEC Press Releases": 8,
    "Fortune": 7,
    "Forbes": 5,
    "The Information": 9,
    "Wired": 7,
    "Axios": 8,
    "Nikkei Asia": 9,
    "South China Morning Post": 7,
    "The Economic Times": 6,
    "Business Standard": 6,
    "Inc42 Media": 6,
    "YourStory": 6,
}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class Article:
    article_id: str
    title: str
    link: str
    summary: str
    source: str
    feed_name: str
    hint: str
    timestamp: float
    age_hours: float
    category: str
    category_scores: dict[str, int]
    base_score: int
    urgent_score: int
    coverage_count: int = 1
    related_sources: tuple[str, ...] = ()

    @property
    def is_urgent(self) -> bool:
        return self.urgent_score >= MIN_URGENT_SCORE and self.age_hours <= URGENT_MAX_AGE_HOURS


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


def default_state() -> dict[str, Any]:
    return {
        "seen": {},
        "last_post_at": 0.0,
        "last_urgent_at": 0.0,
        "recent_categories": [],
        "recent_sources": [],
        "recent_titles": [],
    }


def load_state() -> dict[str, Any]:
    state = default_state()

    if not STATE_FILE.exists():
        return state

    try:
        stored = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
        print(f"State warning: {error}. Starting with a clean state.")
        return state

    if not isinstance(stored, dict):
        return state

    seen = stored.get("seen", {})
    if isinstance(seen, list):
        state["seen"] = {str(item): 0.0 for item in seen}
    elif isinstance(seen, dict):
        cleaned_seen: dict[str, float] = {}
        for key, value in seen.items():
            try:
                cleaned_seen[str(key)] = float(value)
            except (TypeError, ValueError):
                continue
        state["seen"] = cleaned_seen

    for key in ("last_post_at", "last_urgent_at"):
        try:
            state[key] = float(stored.get(key, 0.0))
        except (TypeError, ValueError):
            state[key] = 0.0

    for key in ("recent_categories", "recent_sources", "recent_titles"):
        value = stored.get(key, [])
        if isinstance(value, list):
            state[key] = [str(item) for item in value if str(item).strip()]

    return state


def prune_state(state: dict[str, Any]) -> None:
    now = time.time()
    retention_cutoff = now - 45 * 24 * 3600

    seen_items = [
        (str(key), float(value))
        for key, value in state.get("seen", {}).items()
        if float(value) >= retention_cutoff or float(value) == 0.0
    ]
    seen_items.sort(key=lambda item: item[1], reverse=True)
    state["seen"] = dict(seen_items[:MAX_HISTORY])
    state["recent_categories"] = state.get("recent_categories", [])[:MAX_RECENT_CATEGORIES]
    state["recent_sources"] = state.get("recent_sources", [])[:MAX_RECENT_SOURCES]
    state["recent_titles"] = state.get("recent_titles", [])[:MAX_RECENT_TITLES]


def save_state(state: dict[str, Any]) -> None:
    prune_state(state)
    temporary = STATE_FILE.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(state, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
    temporary.replace(STATE_FILE)


# ---------------------------------------------------------------------------
# Text and URL helpers
# ---------------------------------------------------------------------------


def strip_html(value: str) -> str:
    value = re.sub(r"<script\b[^>]*>.*?</script>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<style\b[^>]*>.*?</style>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    return " ".join(html.unescape(value).split())


def clean_summary(entry: Any, maximum_length: int = 1400) -> str:
    value = str(entry.get("summary", "") or entry.get("description", ""))
    summary = strip_html(value)
    if len(summary) <= maximum_length:
        return summary
    return summary[: maximum_length - 1].rstrip() + "…"


def normalize_title(value: str) -> str:
    value = re.sub(r"[^a-z0-9\s]", " ", html.unescape(value).lower())
    return " ".join(value.split())


def title_tokens(value: str) -> set[str]:
    return {
        token
        for token in normalize_title(value).split()
        if len(token) > 2 and token not in STOP_WORDS
    }


def titles_are_similar(first: str, second: str, threshold: float = 0.56) -> bool:
    first_tokens = title_tokens(first)
    second_tokens = title_tokens(second)
    if not first_tokens or not second_tokens:
        return False

    intersection = len(first_tokens & second_tokens)
    union = len(first_tokens | second_tokens)
    containment = intersection / max(1, min(len(first_tokens), len(second_tokens)))
    jaccard = intersection / max(1, union)
    return jaccard >= threshold or containment >= 0.72


def canonicalize_url(value: str) -> str:
    try:
        parts = urlsplit(value.strip())
    except ValueError:
        return value.strip()

    blocked_parameters = {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "gclid",
        "fbclid",
        "ref",
        "source",
    }
    query = urlencode(
        [(key, val) for key, val in parse_qsl(parts.query) if key.lower() not in blocked_parameters]
    )
    return urlunsplit((parts.scheme, parts.netloc.lower(), parts.path.rstrip("/"), query, ""))


def stable_article_id(title: str, link: str) -> str:
    title_key = " ".join(sorted(title_tokens(title)))
    raw = f"{title_key}|{canonicalize_url(link)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def has_keyword(text: str, keyword: str) -> bool:
    if len(keyword) <= 3 and keyword.isalnum():
        return re.search(rf"\b{re.escape(keyword)}\b", text) is not None
    return keyword in text


def contains_any(text: str, keywords: set[str]) -> bool:
    return any(has_keyword(text, keyword) for keyword in keywords)


def limit_words(value: str, maximum_words: int) -> str:
    words = " ".join(value.split()).split()
    if len(words) <= maximum_words:
        return " ".join(words)
    return " ".join(words[:maximum_words]).rstrip(".,:;") + "…"


def first_factual_sentence(value: str, maximum_words: int = 24) -> str:
    cleaned = " ".join(value.split())
    if not cleaned:
        return ""
    sentence = re.split(r"(?<=[.!?])\s+", cleaned, maxsplit=1)[0]
    return limit_words(sentence, maximum_words)


def split_google_news_title(title: str) -> tuple[str, str]:
    # Google News commonly formats entries as "Headline - Publisher".
    if " - " not in title:
        return title, ""
    headline, publisher = title.rsplit(" - ", 1)
    if 1 <= len(publisher.split()) <= 8:
        return headline.strip(), publisher.strip()
    return title, ""


def extract_source(entry: Any, feed: dict[str, Any], title: str) -> tuple[str, str]:
    source = feed["name"]
    clean_title = title

    source_object = entry.get("source")
    if isinstance(source_object, dict):
        candidate = str(source_object.get("title", "")).strip()
        if candidate:
            source = candidate

    if feed.get("google_news"):
        clean_title, title_source = split_google_news_title(title)
        if title_source:
            source = title_source

    return source, clean_title


def publication_timestamp(entry: Any) -> float | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed:
        try:
            return float(calendar.timegm(parsed))
        except (TypeError, ValueError, OverflowError):
            pass

    # Reject entries with no trustworthy publication time. Treating them as "now"
    # is how stale stories get reposted as fresh.
    return None


def publisher_priority(source: str, feed_priority: int) -> int:
    if source in SOURCE_PRIORITY:
        return SOURCE_PRIORITY[source]

    source_lower = source.lower()
    for known, score in SOURCE_PRIORITY.items():
        if known.lower() in source_lower or source_lower in known.lower():
            return score

    return feed_priority


def amount_in_usd(text: str) -> float:
    # Editorial signal only. This is not currency conversion and is intentionally
    # conservative: it recognizes dollar amounts already expressed in the story.
    matches = re.findall(
        r"\$\s?(\d+(?:\.\d+)?)\s?(trillion|billion|million|bn|m|b)?",
        text.lower(),
    )
    largest = 0.0
    for number_text, unit in matches:
        try:
            number = float(number_text)
        except ValueError:
            continue
        multiplier = 1.0
        if unit in {"million", "m"}:
            multiplier = 1_000_000
        elif unit in {"billion", "bn", "b"}:
            multiplier = 1_000_000_000
        elif unit == "trillion":
            multiplier = 1_000_000_000_000
        largest = max(largest, number * multiplier)
    return largest


# ---------------------------------------------------------------------------
# Classification and scoring
# ---------------------------------------------------------------------------


def keyword_score(title: str, summary: str, keywords: set[str]) -> int:
    title_lower = title.lower()
    summary_lower = summary.lower()
    score = 0
    for keyword in keywords:
        if has_keyword(title_lower, keyword):
            score += 5
        elif has_keyword(summary_lower, keyword):
            score += 2
    return score


def classify_article(title: str, summary: str, hint: str) -> tuple[str, dict[str, int]]:
    scores: dict[str, int] = {}
    for category, keywords in CATEGORY_RULES.items():
        scores[category] = keyword_score(title, summary, keywords)
        if category == hint:
            scores[category] += 5

    # Specific categories should win over generic funding language when both are
    # present, while funding remains visible for stories led by the financing event.
    title_lower = title.lower()
    if contains_any(title_lower, terms("raises|raised|funding|series a|series b|series c|seed round")):
        scores["Startups & Funding"] += 8
    if contains_any(title_lower, terms("ipo|acquires|acquisition|merger|bankruptcy")):
        scores["Markets, IPOs & M&A"] += 8
    if contains_any(title_lower, terms("regulator|regulation|sec|antitrust|ban|approval")):
        scores["Policy & Regulation"] += 7

    category = max(scores, key=scores.get)
    return category, scores


def passes_editorial_scope(title: str, summary: str, category_scores: dict[str, int]) -> bool:
    text = f"{title} {summary}".lower()
    if contains_any(text, BLOCKED_KEYWORDS):
        return False

    strongest_category_score = max(category_scores.values(), default=0)
    has_event = contains_any(text, EVENT_KEYWORDS)
    has_high_signal = contains_any(text, HIGH_SIGNAL_KEYWORDS)
    has_money = amount_in_usd(text) >= 5_000_000

    return strongest_category_score >= 7 and (has_event or has_high_signal or has_money)


def calculate_scores(
    title: str,
    summary: str,
    source: str,
    feed_priority: int,
    age_hours: float,
    category_scores: dict[str, int],
) -> tuple[int, int]:
    text = f"{title} {summary}".lower()
    source_score = publisher_priority(source, feed_priority)
    strongest_category = max(category_scores.values(), default=0)

    freshness_bonus = max(0, int(20 - age_hours * 1.6))
    event_bonus = min(16, sum(2 for keyword in EVENT_KEYWORDS if has_keyword(text, keyword)))
    high_signal_bonus = min(
        20,
        sum(4 for keyword in HIGH_SIGNAL_KEYWORDS if has_keyword(text, keyword)),
    )

    amount = amount_in_usd(text)
    money_bonus = 0
    if amount >= 1_000_000_000:
        money_bonus = 16
    elif amount >= 250_000_000:
        money_bonus = 12
    elif amount >= 100_000_000:
        money_bonus = 9
    elif amount >= 25_000_000:
        money_bonus = 6
    elif amount >= 5_000_000:
        money_bonus = 3

    base_score = (
        source_score * 2
        + min(strongest_category, 32)
        + freshness_bonus
        + event_bonus
        + high_signal_bonus
        + money_bonus
    )

    urgent_keyword_bonus = sum(
        10 for keyword in URGENT_KEYWORDS if has_keyword(text, keyword)
    )
    urgent_score = (
        source_score * 2
        + freshness_bonus
        + high_signal_bonus
        + money_bonus
        + min(50, urgent_keyword_bonus)
    )

    title_lower = title.lower()
    if age_hours <= 1:
        urgent_score += 8
    if amount >= 500_000_000:
        urgent_score += 10
    if (
        contains_any(title_lower, terms("launches|releases|unveils|open sources|open-sources"))
        and contains_any(title_lower, CATEGORY_RULES["AI & Agents"])
    ):
        urgent_score += 20
    if (
        contains_any(text, terms("critical|actively exploited|active exploitation|emergency patch"))
        and contains_any(text, CATEGORY_RULES["Cybersecurity & Cloud"])
    ):
        urgent_score += 22

    return base_score, urgent_score


# ---------------------------------------------------------------------------
# Feed collection
# ---------------------------------------------------------------------------


def fetch_feed(feed: dict[str, Any]) -> list[Article]:
    headers = {
        "User-Agent": RSS_USER_AGENT,
        "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
    }

    try:
        response = requests.get(
            feed["url"],
            headers=headers,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.RequestException as error:
        print(f"Feed skipped ({feed['name']}): {error}")
        return []

    parsed = feedparser.parse(response.content)
    if parsed.bozo:
        print(
            f"Feed warning ({feed['name']}): "
            f"{getattr(parsed, 'bozo_exception', 'unknown parse issue')}"
        )

    now = time.time()
    articles: list[Article] = []

    for entry in parsed.entries[:MAX_ENTRIES_PER_FEED]:
        raw_title = " ".join(str(entry.get("title", "")).split())
        link = str(entry.get("link", "")).strip()
        timestamp = publication_timestamp(entry)

        if not raw_title or not link or timestamp is None:
            continue

        age_seconds = now - timestamp
        if age_seconds < -15 * 60:
            # Bad future timestamps should not outrank genuine current stories.
            continue

        age_hours = max(0.0, age_seconds / 3600)
        if age_hours > ROUTINE_MAX_AGE_HOURS:
            continue

        source, title = extract_source(entry, feed, raw_title)
        summary = clean_summary(entry)
        category, category_scores = classify_article(title, summary, feed["hint"])

        if not passes_editorial_scope(title, summary, category_scores):
            continue

        base_score, urgent_score = calculate_scores(
            title,
            summary,
            source,
            int(feed.get("priority", 5)),
            age_hours,
            category_scores,
        )

        articles.append(
            Article(
                article_id=stable_article_id(title, link),
                title=title,
                link=link,
                summary=summary,
                source=source,
                feed_name=feed["name"],
                hint=feed["hint"],
                timestamp=timestamp,
                age_hours=age_hours,
                category=category,
                category_scores=category_scores,
                base_score=base_score,
                urgent_score=urgent_score,
            )
        )

    return articles


def collect_articles() -> list[Article]:
    combined: list[Article] = []
    for feed in FEEDS:
        print(f"Checking {feed['name']}...")
        combined.extend(fetch_feed(feed))

    # Cluster duplicate coverage. The best source becomes the representative and
    # multi-source coverage raises confidence for genuinely important stories.
    combined.sort(
        key=lambda article: (
            publisher_priority(article.source, 5),
            article.base_score,
            article.timestamp,
        ),
        reverse=True,
    )

    clusters: list[list[Article]] = []
    for article in combined:
        matching_cluster: list[Article] | None = None
        for cluster in clusters:
            if titles_are_similar(article.title, cluster[0].title):
                matching_cluster = cluster
                break
        if matching_cluster is None:
            clusters.append([article])
        else:
            matching_cluster.append(article)

    representatives: list[Article] = []
    for cluster in clusters:
        cluster.sort(
            key=lambda article: (
                publisher_priority(article.source, 5),
                article.base_score,
                article.timestamp,
            ),
            reverse=True,
        )
        representative = cluster[0]
        unique_sources = tuple(dict.fromkeys(article.source for article in cluster))
        representative.coverage_count = len(unique_sources)
        representative.related_sources = unique_sources[:5]
        coverage_bonus = min(18, max(0, representative.coverage_count - 1) * 5)
        representative.base_score += coverage_bonus
        representative.urgent_score += coverage_bonus
        representatives.append(representative)

    representatives.sort(
        key=lambda article: (article.base_score, article.timestamp),
        reverse=True,
    )
    return representatives


# ---------------------------------------------------------------------------
# Selection and rotation
# ---------------------------------------------------------------------------


def recently_seen_title(title: str, recent_titles: list[str]) -> bool:
    return any(titles_are_similar(title, old_title, threshold=0.50) for old_title in recent_titles)


def category_rotation_penalty(category: str, recent_categories: list[str]) -> int:
    penalty = 0
    for index, recent in enumerate(recent_categories[:12]):
        if recent == category:
            penalty += max(2, 14 - index)
    if category not in recent_categories[:5]:
        penalty -= 10
    return penalty


def source_rotation_penalty(source: str, recent_sources: list[str]) -> int:
    penalty = 0
    source_lower = source.lower()
    for index, recent in enumerate(recent_sources[:10]):
        if recent.lower() == source_lower:
            penalty += max(2, 10 - index)
    return penalty


def selection_score(article: Article, state: dict[str, Any]) -> int:
    return (
        article.base_score
        - category_rotation_penalty(article.category, state.get("recent_categories", []))
        - source_rotation_penalty(article.source, state.get("recent_sources", []))
    )


def select_article(articles: list[Article], state: dict[str, Any]) -> tuple[Article | None, str]:
    now = time.time()
    seen = state.get("seen", {})
    recent_titles = state.get("recent_titles", [])

    candidates = [
        article
        for article in articles
        if article.article_id not in seen
        and not recently_seen_title(article.title, recent_titles)
    ]

    print(f"Found {len(candidates)} unseen, fresh candidate(s).")
    if not candidates:
        return None, "No unseen fresh stories passed the editorial filter."

    seconds_since_last_post = now - float(state.get("last_post_at", 0.0))
    seconds_since_last_urgent = now - float(state.get("last_urgent_at", 0.0))

    urgent_candidates = [article for article in candidates if article.is_urgent]
    urgent_candidates.sort(
        key=lambda article: (
            article.urgent_score,
            article.coverage_count,
            article.timestamp,
        ),
        reverse=True,
    )

    urgent_allowed = (
        FORCE_POST
        or (
            seconds_since_last_post >= MINIMUM_POST_GAP_SECONDS
            and seconds_since_last_urgent >= URGENT_COOLDOWN_SECONDS
        )
    )

    if urgent_candidates and urgent_allowed:
        return urgent_candidates[0], "urgent"

    routine_allowed = FORCE_POST or seconds_since_last_post >= ROUTINE_COOLDOWN_SECONDS
    if not routine_allowed:
        remaining = max(0, ROUTINE_COOLDOWN_SECONDS - seconds_since_last_post)
        return None, f"Routine cooldown active for about {int(remaining // 60) + 1} more minute(s)."

    routine_candidates = [
        article for article in candidates if article.base_score >= MIN_ROUTINE_SCORE
    ]
    routine_candidates.sort(
        key=lambda article: (
            selection_score(article, state),
            article.timestamp,
        ),
        reverse=True,
    )

    if not routine_candidates:
        return None, "No story met the minimum routine score."

    return routine_candidates[0], "routine"


# ---------------------------------------------------------------------------
# Optional Gemini editing
# ---------------------------------------------------------------------------


def parse_json_text(value: str) -> dict[str, Any]:
    cleaned = re.sub(r"^```(?:json)?\s*", "", value.strip())
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return json.loads(cleaned)


def fallback_editorial(article: Article) -> tuple[str, str]:
    headline = limit_words(article.title, 12)
    summary = first_factual_sentence(article.summary, 24)
    if not summary:
        summary = limit_words(article.title, 24).rstrip(".!?") + "."
    return headline, summary


def edit_with_gemini(article: Article) -> tuple[str, str]:
    fallback = fallback_editorial(article)
    if not GEMINI_API_KEY:
        print("GEMINI_API_KEY is not configured. Using deterministic editing.")
        return fallback

    endpoint = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent"
    )
    prompt = f"""
You are editing one Telegram news alert for A36 Radar, the A36 Labs global frontier-technology community.

Use only the supplied facts. Do not add analysis, predictions, hype, investment advice, or unsupported details.
Return JSON only with this exact shape:
{{"headline":"maximum 12 words","summary":"one factual sentence, maximum 24 words"}}

Category: {article.category}
Publisher: {article.source}
Original headline: {article.title}
Feed summary: {article.summary}
""".strip()

    try:
        response = requests.post(
            endpoint,
            headers={
                "x-goog-api-key": GEMINI_API_KEY,
                "Content-Type": "application/json",
            },
            json={
                "contents": [
                    {
                        "role": "user",
                        "parts": [{"text": prompt}],
                    }
                ],
                "generationConfig": {
                    "temperature": 0.1,
                    "responseMimeType": "application/json",
                },
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
        content = payload["candidates"][0]["content"]["parts"][0]["text"]
        edited = parse_json_text(content)

        headline = limit_words(str(edited.get("headline", "")).strip(), 12)
        summary = limit_words(str(edited.get("summary", "")).strip(), 24)
        if not headline or not summary:
            raise ValueError("Gemini returned an incomplete editorial result.")

        return headline, summary
    except (
        requests.RequestException,
        KeyError,
        IndexError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) as error:
        print(f"Gemini editor unavailable: {error}. Using deterministic editing.")
        return fallback


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------


def relative_age(timestamp: float) -> str:
    seconds = max(0, time.time() - timestamp)
    if seconds < 3600:
        minutes = max(1, int(seconds // 60))
        return f"{minutes}m ago"
    hours = max(1, int(seconds // 3600))
    return f"{hours}h ago"


def build_message(
    article: Article,
    headline: str,
    short_summary: str,
    mode: str,
) -> str:
    safe_headline = html.escape(headline)
    safe_summary = html.escape(short_summary)
    safe_category = html.escape(article.category)
    safe_source = html.escape(article.source)
    safe_link = html.escape(article.link, quote=True)
    emoji = CATEGORY_EMOJIS.get(article.category, "📡")

    breaking = "🚨 <b>BREAKING</b>\n\n" if mode == "urgent" else ""
    coverage = ""
    if article.coverage_count >= 2:
        coverage = f" · {article.coverage_count} sources"

    return (
        "⚡️ <b>A36 RADAR</b>\n\n"
        f"{breaking}"
        f"<b>{safe_headline}</b>\n"
        f"{safe_summary}\n\n"
        f"{emoji} {safe_category}\n"
        f"🕒 {relative_age(article.timestamp)}{coverage} · {safe_source}\n"
        f'<a href="{safe_link}">Read source ↗</a>'
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
    payload = response.json()
    if not payload.get("ok"):
        raise RuntimeError(f"Telegram rejected the message: {payload}")


def unpin_automatic_discussion_post(max_attempts: int = 4, delay_seconds: int = 4) -> None:
    """Unpin only Telegram's automatic channel forward; preserve manual pins."""
    if not DISCUSSION_CHAT_ID:
        return

    get_chat_url = f"https://api.telegram.org/bot{BOT_TOKEN}/getChat"
    unpin_url = f"https://api.telegram.org/bot{BOT_TOKEN}/unpinChatMessage"

    for attempt in range(max_attempts):
        if attempt:
            time.sleep(delay_seconds)
        try:
            response = requests.post(
                get_chat_url,
                json={"chat_id": DISCUSSION_CHAT_ID},
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            payload = response.json()
            pinned = payload.get("result", {}).get("pinned_message")

            if not pinned:
                return
            if not pinned.get("is_automatic_forward", False):
                print("Current discussion pin is manual. Leaving it pinned.")
                return

            message_id = pinned.get("message_id")
            if not message_id:
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
                print("Unpinned the automatic discussion forward.")
            else:
                print(f"Discussion unpin was rejected: {unpin_payload}")
            return
        except requests.RequestException as error:
            if attempt == max_attempts - 1:
                print(f"Discussion unpin check failed: {error}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def validate_environment() -> None:
    if DRY_RUN:
        return
    if not BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is missing.")
    if not CHAT_ID:
        raise RuntimeError("TELEGRAM_CHAT_ID is missing.")


def update_state_after_post(
    state: dict[str, Any],
    article: Article,
    mode: str,
) -> None:
    now = time.time()
    state.setdefault("seen", {})[article.article_id] = now
    state["last_post_at"] = now
    if mode == "urgent":
        state["last_urgent_at"] = now

    state["recent_categories"] = [
        article.category,
        *state.get("recent_categories", []),
    ][:MAX_RECENT_CATEGORIES]
    state["recent_sources"] = [
        article.source,
        *state.get("recent_sources", []),
    ][:MAX_RECENT_SOURCES]
    state["recent_titles"] = [
        article.title,
        *state.get("recent_titles", []),
    ][:MAX_RECENT_TITLES]


def main() -> None:
    validate_environment()
    state = load_state()
    articles = collect_articles()

    print(f"Collected {len(articles)} distinct in-scope story cluster(s).")
    selected, mode = select_article(articles, state)

    if selected is None:
        print(mode)
        print("Published 0 article(s).")
        return

    headline, short_summary = edit_with_gemini(selected)
    message = build_message(selected, headline, short_summary, mode)

    print(
        "Selected: "
        f"[{mode}] {selected.category} | {selected.source} | "
        f"score={selected.base_score} urgent={selected.urgent_score} | "
        f"{selected.title}"
    )

    if DRY_RUN:
        print("\n--- DRY RUN MESSAGE ---\n")
        print(message)
        print("\nDry run complete. State was not changed.")
        return

    send_to_telegram(message, selected.link)
    update_state_after_post(state, selected, mode)
    save_state(state)
    unpin_automatic_discussion_post()
    print("Published 1 article(s).")


if __name__ == "__main__":
    main()
