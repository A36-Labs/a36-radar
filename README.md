A36 Radar

A36 Radar is an open-source Telegram news automation system for the A36 Labs community. It monitors global technology news, filters weak or stale stories, rotates coverage across A36 Labs topics, and publishes one concise post at a time.

What version 2 fixes

Checks for news every 15 minutes, 24/7.

Publishes at most one story per run.

Limits normal publishing to roughly one post per hour.

Allows a genuinely urgent story to publish between normal hourly posts.

Rotates categories and publishers so the feed does not become crypto-only.

Rejects entries that do not provide a trustworthy publication time.

Uses multi-source coverage as a signal for major news.

Keeps working when optional AI editing is unavailable.

Removes broken a16z and HKEX RSS endpoints used by the earlier version.

Serializes workflow runs and retries state pushes to reduce seen_articles.json conflicts.

A36 Labs coverage

A36 Radar covers:

AI, models and agents

Startups and funding

Venture capital and accelerators

Open source and developer tools

Web3 and digital assets

Cybersecurity and cloud

Robotics, semiconductors, quantum, space, biotech and climate tech

Fintech and payments

Public markets, IPOs, earnings and M&A

Technology policy and regulation

Builder programs, grants, hackathons and developer ecosystems

Publishing logic

The GitHub Actions workflow runs at minutes 07, 22, 37 and 52 of every hour.

Routine story: no more than one about every 55 minutes.

Urgent story: may bypass the routine cooldown, but the bot still enforces a minimum gap, limits urgent bursts, and publishes only one story in that run.

Freshness: routine stories must normally be under 14 hours old; urgent stories must be under 4 hours old.

No filler: when nothing current and credible passes the filters, the bot publishes nothing instead of recycling stale news.

This is near-real-time monitoring, not guaranteed instant delivery. GitHub Actions schedules can occasionally be delayed.

Project structure

a36-radar/
├── .github/
│   └── workflows/
│       └── radar.yml
├── .env.example
├── .gitignore
├── LICENSE
├── README.md
├── radar.py
├── requirements.txt
└── seen_articles.json

Setup

1. Replace old files

Keep only one A36 Radar workflow:

.github/workflows/radar.yml

Delete older Radar YAML files so two workflows cannot publish or update state at the same time.

Replace these files with the version in this package:

radar.py
.github/workflows/radar.yml
requirements.txt
seen_articles.json
README.md
.gitignore
.env.example

2. Add required GitHub Actions secrets

Open:

Repository Settings
→ Secrets and variables
→ Actions
→ Secrets

Add:

TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID

TELEGRAM_CHAT_ID is normally the A36 Labs channel ID, such as a value beginning with -100.

3. Add optional AI editing

A36 Radar does not require AI to run. It has a deterministic headline and summary fallback.

For optional Gemini editing, add this repository secret:

GEMINI_API_KEY

Optionally add this repository variable:

GEMINI_MODEL=gemini-3.1-flash-lite

Never commit API keys or Telegram credentials into the repository.

4. Add optional repository variables

Open:

Repository Settings
→ Secrets and variables
→ Actions
→ Variables

Optional variables:

TELEGRAM_DISCUSSION_CHAT_ID
RSS_USER_AGENT
GEMINI_MODEL

Recommended RSS_USER_AGENT:

A36 Radar/2.0 (+https://a36labs.com; contact: hello@a36labs.com)

TELEGRAM_DISCUSSION_CHAT_ID is needed only when the channel is linked to a discussion group and the bot should remove Telegram's automatic forward pin while preserving manual pins.

5. Check workflow permissions

The workflow requests:

permissions:
  contents: write

This is needed only to update seen_articles.json. If an organization policy blocks write access, open:

Repository Settings
→ Actions
→ General
→ Workflow permissions

Allow the workflow to write repository contents.

6. Test safely

Open the repository's Actions tab, choose A36 Radar, and click Run workflow.

Recommended first test:

force_post: true
dry_run: true

The workflow will show the selected Telegram message in the logs without publishing it or changing state.

Second test:

force_post: true
dry_run: false

This publishes the best unseen current story immediately.

After the manual test succeeds, scheduled runs continue automatically.

Local test

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

Export the environment variables, then run:

DRY_RUN=true FORCE_POST=true python radar.py

Telegram permissions

The bot needs permission to post messages in the channel.

For automatic discussion-post unpinning, the bot also needs permission to manage or pin messages in the linked discussion group. Failure to unpin is logged but does not stop publishing.

State and duplicate prevention

seen_articles.json stores:

published article IDs

the last normal or urgent publishing time

recent categories

recent publishers

recent headlines

Only successfully published stories are marked as seen. Unselected stories remain eligible until they become too old.

Do not manually edit this file while a workflow is running. The workflow uses concurrency and retry logic to reduce merge conflicts.

Customization

Main controls are near the top of radar.py:

ROUTINE_MAX_AGE_HOURS = 14
URGENT_MAX_AGE_HOURS = 4
ROUTINE_COOLDOWN_SECONDS = 55 * 60
MINIMUM_POST_GAP_SECONDS = 10 * 60
MIN_ROUTINE_SCORE = 34
MIN_URGENT_SCORE = 72

Feeds are defined in FEEDS. Categories and topic keywords are defined in CATEGORY_RULES.

Troubleshooting

The workflow does not appear

The workflow file must exist on the repository's default branch at:

.github/workflows/radar.yml

The run succeeds but publishes zero stories

Read the final log message. Common reasons:

the hourly cooldown is active

every story is already seen

feeds returned no recent entries

available stories failed the quality filter

Use a manual run with force_post: true to ignore only the cooldown. It does not disable freshness or duplicate checks.

403 or 404 from a feed

A single broken feed is skipped. The remaining direct feeds and Google News topic feeds continue working. Remove or replace a source only when it fails consistently.

Gemini fails

The bot automatically uses deterministic editing. Publishing should continue. Check the API key, model variable and quota separately.

State push conflict

Confirm that only one Radar workflow exists. The included workflow serializes runs and retries a rebase before pushing state.

Security

Do not commit:

TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
GEMINI_API_KEY
private group IDs
other API credentials

Rotate any credential that is accidentally exposed.

License

This project uses the license included in the repository.

Credits

An open-source project by A36 Labs.

Built by Laksh Dilliwal.

Website: https://a36labs.com

Telegram: https://t.me/A36Labs

Community: https://t.me/A36Global

X: https://x.com/A36Labs

GitHub: https://github.com/A36Labs

Build. Connect. Launch.
