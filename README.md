<p align="center">
  <a href="https://a36labs.com">
    <img src="https://github.com/A36Labs.png?size=160" width="110" alt="A36 Labs">
  </a>
</p>

<h1 align="center">⚡ A36 Radar</h1>

<p align="center">
  Always-on global technology and ecosystem intelligence for the A36 Labs community.
</p>

<p align="center">
  <a href="https://github.com/A36Labs/a36-radar/actions/workflows/radar.yml">
    <img src="https://github.com/A36Labs/a36-radar/actions/workflows/radar.yml/badge.svg" alt="Workflow Status">
  </a>
  <img src="https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/GitHub_Actions-Automated-2088FF?logo=githubactions&logoColor=white" alt="GitHub Actions">
  <a href="https://t.me/A36Labs">
    <img src="https://img.shields.io/badge/Telegram-A36_Labs-26A5E4?logo=telegram&logoColor=white" alt="Telegram">
  </a>
  <img src="https://img.shields.io/badge/License-MIT-green" alt="MIT License">
</p>

---

## About

**A36 Radar** is an open-source news automation system built by [A36 Labs](https://a36labs.com).

It scans trusted global sources, filters recent high-signal stories, prevents duplicates, and publishes concise updates directly to Telegram.

No AI API, external server, or Cloudflare deployment is required. The system runs entirely through GitHub Actions.

## Coverage

- 🤖 AI, agents, and frontier technology
- 🚀 Startups, funding, acquisitions, and IPOs
- 🛰️ Venture capital and accelerators
- 🧑‍💻 Open source and developer tools
- ⛓️ Web3, blockchain, and digital assets
- 🛡️ Cybersecurity, cloud, and infrastructure
- 🦾 Robotics, semiconductors, quantum, and space
- 💳 Fintech, payments, and financial infrastructure
- 📈 Public markets and major technology deals
- 🏛️ Technology policy and regulation
- 🏗️ Grants, hackathons, and builder ecosystems

## How it works

```text
Trusted news sources
        ↓
Freshness and relevance filters
        ↓
Duplicate detection
        ↓
Category rotation
        ↓
Telegram publishing
        ↓
History saved in seen_articles.json
```

The workflow:

- Checks for recent news every 15 minutes
- Publishes approximately one normal story per hour
- Publishes only one story at a time
- Can publish major breaking news between normal posts
- Rejects stale, promotional, and low-quality stories
- Runs continuously through GitHub Actions

## Setup

### Repository secrets

Go to:

`Settings → Secrets and variables → Actions → Secrets`

Add:

```text
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
```

### Repository variables

Go to:

`Settings → Secrets and variables → Actions → Variables`

Add:

```text
RSS_USER_AGENT
TELEGRAM_DISCUSSION_CHAT_ID
```

Example RSS user agent:

```text
A36 Radar/2.0 (+https://a36labs.com; contact: hello@a36labs.com)
```

`TELEGRAM_DISCUSSION_CHAT_ID` is optional and only needed for a linked Telegram discussion group.

## Run manually

Open:

`Actions → A36 Radar → Run workflow`

For a safe test:

- Enable **Ignore the hourly cooldown**
- Enable **Build a post without publishing it**

For a real Telegram post, keep only the first option enabled.

## Project structure

```text
a36-radar/
├── .github/
│   └── workflows/
│       └── radar.yml
├── radar.py
├── requirements.txt
├── seen_articles.json
├── LICENSE
└── README.md
```

## Article previews

Telegram generates previews from each article page’s Open Graph metadata.

A preview image may not appear when the publisher blocks Telegram, has no accessible `og:image`, or Telegram has cached an older preview.

## Security

Never commit Telegram bot tokens or private credentials.

Store all sensitive values in GitHub Actions repository secrets.

## Community

- 🌐 [Website](https://a36labs.com)
- 📡 [Telegram Channel](https://t.me/A36Labs)
- 💬 [Global Community](https://t.me/A36Global)
- 𝕏 [X](https://x.com/A36Labs)
- 💼 [LinkedIn](https://www.linkedin.com/company/a36labs)
- 📸 [Instagram](https://www.instagram.com/a36labs)

---

<p align="center">
  Built, connected, and launched by <strong>A36 Labs</strong>.
</p>
