<p align="center">
  <a href="https://a36labs.com">
    <img src="https://github.com/A36Labs.png?size=160" width="120" alt="A36 Labs">
  </a>
</p>

<h1 align="center">⚡ A36 Radar</h1>

<p align="center">
  Always-on global technology and ecosystem intelligence for the A36 Labs community.
</p>

<p align="center">
  <a href="https://github.com/A36Labs/a36-radar/actions/workflows/radar.yml">
    <img src="https://github.com/A36Labs/a36-radar/actions/workflows/radar.yml/badge.svg" alt="A36 Radar Workflow">
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

It scans trusted global sources, filters recent high-signal stories, prevents duplicates and publishes concise updates directly to Telegram.

No AI API, server or Cloudflare deployment is required. The complete system runs through GitHub Actions.

## Coverage

A36 Radar covers:

- 🤖 AI, agents and frontier technology
- 🚀 Startups, funding and acquisitions
- 🛰️ Venture capital and accelerators
- 🧑‍💻 Open source and developer tools
- ⛓️ Web3, blockchain and digital assets
- 🛡️ Cybersecurity, cloud and infrastructure
- 🤖 Robotics, chips, quantum and space
- 💳 Fintech, payments and financial infrastructure
- 📈 IPOs, public markets and major technology deals
- 🏛️ Technology policy and regulation
- 🏗️ Grants, hackathons and builder ecosystems

The bot rotates categories and publishers to avoid repetitive coverage.

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

The workflow:

Scans for news every 15 minutes
Publishes a maximum of one normal story per hour
Publishes only one story at a time
Can publish urgent major news between scheduled posts
Rejects stale, promotional and low-quality stories
Runs continuously through GitHub Actions
Repository setup
Required repository secrets

Open:

Settings → Secrets and variables → Actions → Secrets

Add:

TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
Repository variables

Open:

Settings → Secrets and variables → Actions → Variables

Add:

RSS_USER_AGENT
TELEGRAM_DISCUSSION_CHAT_ID

Example user agent:

A36 Radar/2.0 (+https://a36labs.com; contact: hello@a36labs.com)

TELEGRAM_DISCUSSION_CHAT_ID is optional and is only required when the Telegram channel has a linked discussion group.

Run manually

Open:

Actions → A36 Radar → Run workflow

Available options:

Ignore the hourly cooldown to test the best unseen story
Build a post without publishing it for a safe dry run

For the first test, enable both options.

For a real Telegram post, enable only the first option.

Project structure
a36-radar/
├── .github/
│   └── workflows/
│       └── radar.yml
├── radar.py
├── requirements.txt
├── seen_articles.json
├── LICENSE
└── README.md
Link previews

Telegram generates article previews using the source page’s Open Graph metadata.

A preview image may not appear when:

The publisher blocks Telegram
The article has no accessible og:image
The image URL has expired
Telegram has cached an older preview
The source only provides text in its feed

The article link will still work normally.

Security

Never commit Telegram bot tokens or private credentials to the repository.

Store sensitive values only in GitHub Actions repository secrets.

Community
🌐 Website
📡 Telegram Channel
💬 Global Community
𝕏 X / Twitter
💼 LinkedIn
📸 Instagram
<p align="center"> Built, connected and launched by <strong>A36 Labs</strong>. </p> ```
