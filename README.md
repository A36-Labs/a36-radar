# A36 Radar

> Automated technology, startup, AI, Web3 and market intelligence for the A36 Labs community.

[![A36 Radar](https://github.com/A36Labs/a36-radar/actions/workflows/radar.yml/badge.svg)](https://github.com/A36Labs/a36-radar/actions/workflows/radar.yml)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![GitHub Actions](https://img.shields.io/badge/GitHub-Actions-2088FF?logo=githubactions&logoColor=white)](https://github.com/features/actions)
[![License](https://img.shields.io/github/license/A36Labs/a36-radar)](LICENSE)

**A36 Radar** is an open-source Telegram news automation system built by A36 Labs.

It collects updates from selected RSS feeds, filters relevant stories, creates concise AI-assisted summaries and publishes them directly to Telegram.

## Features

- Collects news from multiple RSS feeds
- Filters stories using topics and keywords
- Creates short summaries with Google Gemini
- Prevents duplicate posts
- Supports images and Telegram link previews
- Runs automatically through GitHub Actions
- Tracks previously published articles
- Works without a dedicated server

## Topics

A36 Radar focuses on:

- Artificial intelligence
- Startups and funding
- Venture capital
- Web3 and crypto
- Open source
- Developer tools
- Public markets and IPOs
- Global technology news

## How it works

```text
RSS feeds
   ↓
Story filtering
   ↓
Duplicate detection
   ↓
AI-assisted summary
   ↓
Telegram publishing
   ↓
Update seen_articles.json
```

## Project structure

```text
a36-radar/
├── .github/
│   └── workflows/
│       └── radar.yml
├── radar.py
├── requirements.txt
├── seen_articles.json
├── README.md
└── LICENSE
```

## Setup

### 1. Fork or clone the repository

```bash
git clone https://github.com/A36Labs/a36-radar.git
cd a36-radar
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Add GitHub Actions secrets

Open:

```text
Repository Settings
→ Secrets and variables
→ Actions
→ New repository secret
```

Add:

```text
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
GEMINI_API_KEY
```

Optional:

```text
RSS_USER_AGENT
```

Never commit real API keys or Telegram credentials to the repository.

### 4. Run the workflow

Open the repository’s **Actions** tab, select the A36 Radar workflow and click:

```text
Run workflow
```

The workflow will also run automatically according to the schedule configured in:

```text
.github/workflows/radar.yml
```

## Run locally

Configure the required environment variables and run:

```bash
python radar.py
```

Use a test Telegram bot and test channel during development.

## Customization

You can customize:

- RSS feeds
- Topics and keywords
- Story filters
- AI summary instructions
- Posting frequency
- Telegram formatting
- Maximum stories per run

The publishing schedule can be changed inside:

```text
.github/workflows/radar.yml
```

## Duplicate prevention

Published article identifiers are stored in:

```text
seen_articles.json
```

The GitHub Actions workflow updates this file after successful runs to prevent the same story from being published repeatedly.

## Contributing

Community contributions are welcome.

You can contribute by:

- Adding reliable news sources
- Improving filtering
- Improving summary quality
- Adding tests
- Improving documentation
- Optimizing performance
- Fixing bugs

Open an issue before making major architectural changes.

## Security

Do not commit:

```text
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
GEMINI_API_KEY
API credentials
Private channel information
```

Immediately rotate any credential that is accidentally exposed.

## License

This project is distributed under the license included in the [LICENSE](LICENSE) file.

## Credits

An open-source project by **A36 Labs**.

Built by **Laksh Dilliwal**  
https://x.com/LakshDilliwal

## A36 Labs

- Website: https://a36labs.com
- Telegram: https://t.me/A36Labs
- Community: https://t.me/A36Global
- X: https://x.com/A36Labs
- GitHub: https://github.com/A36Labs

---

**Build. Connect. Launch.**
