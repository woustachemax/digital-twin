# Twin

A tiny, local-first AI buddy that lives on your Mac.

Twin floats on your desktop in a small widget, pops up with a global hotkey (`Cmd+Shift+Space`), and chats with you in one of five personas. It builds a rough picture of your day from your own Mac, reading bank SMS that arrive through Messages and events from the Calendar app, and keeps that data in a DuckDB file on your machine. Twin has no server of its own. The only network traffic is the chat request sent directly to the Anthropic API, and that request is scrubbed before it leaves.

This started as a hackathon project. It works, it's small (about 1,600 lines of Python), and it's meant for anyone to install and hack on.

## Contents

- [How it works](#how-it-works)
- [Repository layout](#repository-layout)
- [Requirements](#requirements)
- [Installation](#installation)
- [Usage](#usage)
- [Personas](#personas)
- [Configuration](#configuration)
- [macOS permissions](#macos-permissions)
- [Privacy](#privacy)
- [Local data monitor](#local-data-monitor)
- [Database schema](#database-schema)
- [Components in detail](#components-in-detail)
- [Landing page](#landing-page)
- [Troubleshooting](#troubleshooting)
- [Limitations](#limitations)

## How it works

```
 ~/Library/Messages/chat.db                     Calendar.app
            |                                         |
            v                                         v
 packages/ingest/imessage_export.py        packages/ingest/calendar_reader.py
            |                                         |
            v                                         |
 packages/parse/sms_parser.py                         |
            |                                         |
            v                                         |
 packages/db/db.py -> ~/.twin/twin.duckdb             |
            ^               |                         |
            |               v                         v
    run_pipeline.py      buddy.py  <------------------+
                            |
                            |  scrubbed request only
                            v
                    api.anthropic.com
```

1. **Ingest.** `run_pipeline.py` copies your Messages database to a temp folder, reads the last 200 messages, and deletes the copy.
2. **Parse.** Each message goes through a regex parser that picks out bank transaction SMS: debit or credit, amount, merchant or UPI handle, and reference number. Everything else is ignored.
3. **Store.** Parsed transactions go into `~/.twin/twin.duckdb`. Every insert also writes a row to an `access_log` table that records what was read and when. Messages already stored are skipped.
4. **Chat.** `buddy.py` reads the five most recent transactions, turns them into vague phrases like "spent money on food and dining earlier this week", adds today's calendar events, and sends that with your message to Claude. The reply appears in the widget.

## Repository layout

```
digital-twin/
├── buddy.py                    desktop widget: UI, personas, hotkey, prompt building, request scrubbing
├── run_pipeline.py             one-shot ingest: Messages -> parser -> twin.duckdb
├── packages/
│   ├── ingest/
│   │   ├── imessage_export.py  reads recent messages from ~/Library/Messages/chat.db
│   │   └── calendar_reader.py  reads today's and tomorrow's events from Calendar via AppleScript
│   ├── parse/
│   │   └── sms_parser.py       regex parser for bank transaction SMS (Rs / INR, UPI)
│   ├── db/
│   │   └── db.py               DuckDB schema, inserts, dedup check, access log
│   └── ui/
│       └── app.py              Streamlit monitor for everything in twin.duckdb
├── landing/
│   ├── index.html              static landing page (single file, no build step)
│   └── package.json            Vercel CLI for deploying the page (the page itself has no dependencies)
└── .env                        your ANTHROPIC_API_KEY (git-ignored, you create this)
```

Your data lives outside the repo, in `~/.twin/`:

```
~/.twin/
├── twin.duckdb                 your transactions and access log (created on first run)
└── config.json                 your name and onboarding state
```

## Requirements

- **macOS.** Twin reads the Messages database, talks to Calendar through `osascript`, and uses AppKit for the translucent window. It won't work on Linux or Windows.
- **Python 3 with Tk.** Developed on Python 3.12. The python.org installer includes Tk. With Homebrew, also run `brew install python-tk`.
- **An Anthropic API key.** Get one from the [Anthropic Console](https://console.anthropic.com/).

Python packages:

| Package | Used by | Why |
|---|---|---|
| `anthropic` | `buddy.py` | Claude API client |
| `duckdb` | `buddy.py`, `packages/db`, `packages/ui` | local database |
| `python-dotenv` | `buddy.py` | loads `.env` |
| `pynput` | `buddy.py` | global hotkey |
| `pyobjc-framework-Cocoa`, `pyobjc-framework-Quartz` | `buddy.py` | translucent window and app focus (optional, Twin falls back to a plain window without them) |
| `streamlit`, `pandas` | `packages/ui/app.py` | data monitor (optional) |

## Installation

```bash
git clone https://github.com/woustachemax/digital-twin.git
cd digital-twin

python3 -m venv .venv
source .venv/bin/activate

pip install anthropic duckdb python-dotenv pynput pyobjc-framework-Cocoa pyobjc-framework-Quartz
pip install streamlit pandas
```

The second `pip install` is only needed for the data monitor.

Create a `.env` file in the repo root with your key:

```bash
echo 'ANTHROPIC_API_KEY=sk-ant-...' > .env
```

`.env` is git-ignored. You can also export `ANTHROPIC_API_KEY` in your shell instead.

## Usage

### 1. Index your activity

```bash
python3 run_pipeline.py
```

You'll see something like `Inserted 12 transactions (3 duplicates skipped)`. Run it again whenever you want Twin to catch up. It only adds messages it hasn't stored before.

Transactions go into `~/.twin/twin.duckdb`. The folder and file are created if they don't exist yet, with the folder readable only by you (mode `700`). You can run the pipeline from any directory.

You can skip this step. Twin still works, it just won't know anything about your spending.

### 2. Start Twin

```bash
python3 buddy.py
```

On first launch Twin explains what it reads and what it sends, then asks for your name. Once you answer, it creates your database at `~/.twin/twin.duckdb` (or tells you it found an existing one) and saves your name to `~/.twin/config.json` (file mode `600`) so it only asks once.

### 3. Talk to it

| Action | How |
|---|---|
| Show or hide Twin | `Cmd+Shift+Space` from anywhere |
| Ask something | Type in the box and press Return |
| Move the widget | Drag it |
| List personas | `/persona` |
| Switch persona live | `/persona <key>`, for example `/persona gengar` |

Twin fills in context on its own. Ask "what should I be doing?" and it may mention your next calendar event. Ask "have I been spending a lot?" and it answers from the vague summary, never with amounts.

## Personas

Pick one at launch with the `PERSONA` environment variable, or switch live with `/persona <key>`. Both take the **key** in the first column, not the display name.

| Key | Name | Avatar | Personality | Background | Accent | Text |
|---|---|---|---|---|---|---|
| `twin` | Twin | bun | Warm, cheerful, easygoing. The default. | `#0E0D12` | `#C6FF4A` | `#F7F2E8` |
| `gengar` | Shade | ghost | Mischievous shadow-ghost, sly and teasing. Eyes `#FF4F6E`. | `#17111F` | `#A77BFF` | `#EEE8F7` |
| `ember` | Ember | ghost | Bright, energetic spark who hypes you up. Eyes `#FFD166`. | `#1E120D` | `#FF7A3D` | `#FFEDE4` |
| `calm` | Luna | ghost | Gentle, patient, soothing. | `#141828` | `#A5B4FF` | `#E7EBFA` |
| `plain` | Assistant | monogram | Neutral and professional, no quirks. | `#1E1E20` | `#8E8E93` | `#F2F2F7` |

```bash
PERSONA=calm python3 buddy.py
```

An unknown key prints a warning and falls back to `twin`. Every other widget color (border, bubble, input field, muted text, avatar) comes from these three palette values through `theme_for()` in `buddy.py`.

To add your own persona, add an entry to the `PERSONAS` dict with `name`, `avatar` (`bun`, `ghost`, or `monogram`), `system_prompt`, `palette`, `greeting` (may use `{name}`), `idle`, `busy`, and `done`.

## Configuration

| Variable | Default | Effect |
|---|---|---|
| `ANTHROPIC_API_KEY` | none | Required for chat. Without it Twin opens but only shows a reminder to set it. |
| `PERSONA` | `twin` | Persona key to start with. |
| `TWIN_DB_PATH` | `~/.twin/twin.duckdb` | Database used by the pipeline, `buddy.py`, and the monitor. |
| `TWIN_CONFIG_PATH` | `~/.twin/config.json` | Where your name and onboarding state are saved. |
| `BUDDY_DEBUG` | off | Set to `1` to print every outgoing API request to stderr. See [Privacy](#privacy). |

Constants near the top of `buddy.py` cover the rest: `MODEL` (`claude-sonnet-4-6`), `MAX_TOKENS`, `HOTKEY`, widget size, and how often the calendar is refreshed (every 5 minutes, or 30 seconds after an error).

## macOS permissions

macOS asks for these the first time each feature runs. Grant them to the app you launch Twin from (Terminal, iTerm, VS Code, and so on).

| Permission | Needed for | Where to grant it |
|---|---|---|
| Full Disk Access | `run_pipeline.py` reading `~/Library/Messages/chat.db` | System Settings > Privacy & Security > Full Disk Access |
| Accessibility and Input Monitoring | the global hotkey (`pynput`) | System Settings > Privacy & Security > Accessibility / Input Monitoring |
| Automation: Calendar | reading calendar events | Allow when prompted, or System Settings > Privacy & Security > Automation |

If the calendar isn't allowed yet, Twin says so in the widget and keeps working without it.

## Privacy

### What stays on your Mac

- `~/.twin/twin.duckdb`, which holds the parsed transactions and the full raw SMS text.
- `~/.twin/config.json`, which holds your name.
- The temporary copy of the Messages database, which is deleted right after reading.

There are no accounts, no sync, no analytics, and no Twin server. Everyone who installs Twin gets their own fresh `twin.duckdb`, created in their own home folder on first run. It lives outside the repo, so it never ends up in git. Nothing is shared or pooled between users.

### What is sent to Anthropic

Each chat message makes one request to the Anthropic API containing:

- your message
- your name, if you gave one
- the current time and day of the week
- the titles and times of today's calendar events
- a vague summary of up to five recent transactions, such as `- received a payment yesterday`

It never includes amounts, balances, account numbers, reference numbers, merchant names, UPI handles, or raw SMS text.

### How that's enforced

`buddy.py` doesn't rely on the prompt alone. It checks each request in several layers:

1. **Allowlisted vocabulary.** Each line of the transaction summary must exactly match a fixed list of phrases (an activity like "spent money on groceries" plus a time phrase like "earlier this week"). Any line that doesn't match is dropped.
2. **Scrubbing.** Before sending, the system prompt and every message are scrubbed. Sentences that look like bank SMS are replaced with `[removed: SMS text]`. Currency amounts, account numbers, email or UPI handles, long IDs, and numbers are replaced with `[amount]`, `[account]`, `[id]`, and `[number]`. Calendar titles are cut to 80 characters and scrubbed too.
3. **Field allowlist.** Only `model`, `max_tokens`, `system`, and `messages` are sent. Any other field is dropped.

To see exactly what leaves your machine, run:

```bash
BUDDY_DEBUG=1 python3 buddy.py
```

Every request is printed to stderr before it's sent, along with a list of what was redacted.

## Local data monitor

A Streamlit dashboard that shows everything in `~/.twin/twin.duckdb`: parsed transactions next to the access log. It refreshes every 3 seconds, so you can watch rows appear while the pipeline runs.

```bash
streamlit run packages/ui/app.py --browser.gatherUsageStats false
```

It opens the database read-only and respects `TWIN_DB_PATH`. The dashboard's own code makes no network calls. Streamlit itself collects anonymous usage statistics by default, which the flag above turns off. To turn them off permanently, add `gatherUsageStats = false` under `[browser]` in `~/.streamlit/config.toml`.

## Database schema

`~/.twin/twin.duckdb` has two tables, created by `packages/db/db.py` if they don't exist yet.

**`transactions`**

| Column | Type | Notes |
|---|---|---|
| `id` | VARCHAR | UUID, primary key |
| `timestamp` | TIMESTAMP | when the SMS arrived |
| `type` | VARCHAR | `debited` or `credited` |
| `amount` | DOUBLE | |
| `merchant` | VARCHAR | merchant name or UPI handle, may be null |
| `ref_number` | VARCHAR | bank reference, may be null |
| `raw_text` | VARCHAR | full SMS text, also used to skip duplicates |

**`access_log`**

| Column | Type | Notes |
|---|---|---|
| `id` | VARCHAR | UUID, primary key |
| `timestamp` | TIMESTAMP | UTC |
| `source` | VARCHAR | for example `imessage_pipeline` |
| `action` | VARCHAR | for example `insert_transaction` |
| `data_touched` | VARCHAR | human-readable summary of what was written |

To look at it yourself:

```bash
python3 -c "import duckdb, os; print(duckdb.connect(os.path.expanduser('~/.twin/twin.duckdb'), read_only=True).sql('SELECT * FROM transactions'))"
```

## Components in detail

### `buddy.py`

The desktop app. A borderless Tk window, made translucent through AppKit when PyObjC is available, with an animated avatar, a speech bubble, and an input field. The global hotkey listener runs in a separate process and sends toggle events through a queue. Calendar events are fetched in a background thread and cached. Claude calls also run in a background thread so the widget never freezes.

### `run_pipeline.py`

Ties the pipeline together: fetch messages, parse them, skip anything already stored, and insert the rest with `source="imessage_pipeline"`. Prints a count when done.

### `packages/ingest/imessage_export.py`

Copies `chat.db` (plus its `-wal` and `-shm` files) to a temp folder so it never touches the live database, opens the copy read-only, and returns the most recent messages oldest first. Newer macOS versions store some message text only in the `attributedBody` blob, so it decodes that too, with `plutil` as a fallback. Timestamps are converted from Apple's 2001 epoch.

Run it on its own to check access:

```bash
python3 packages/ingest/imessage_export.py
```

### `packages/ingest/calendar_reader.py`

Runs an AppleScript through `osascript` that collects every event starting today or tomorrow across all calendars. It returns the title, start time, all-day flag, and calendar name. Permission errors and timeouts become a readable `CalendarAccessError`.

```bash
python3 packages/ingest/calendar_reader.py
```

### `packages/parse/sms_parser.py`

Regex parser for bank transaction SMS in the formats Indian banks commonly use: `Rs.`, `Rs`, or `INR` amounts, `debited`/`credited`/`spent` keywords, UPI handles like `name@upi`, merchants in "at SWIGGY using UPI" phrasing, and `Ref No`, `RRN`, `UPI Ref`, or `Txn ID` references. A message is only kept if it has both a transaction type and an amount.

Running it directly prints the parsed result for three sample messages:

```bash
python3 packages/parse/sms_parser.py
```

### `packages/db/db.py`

Opens the database, creates the schema, and provides `insert_transaction`, `transaction_exists`, `insert_access_log`, and `get_recent_access_log`. Every transaction insert writes an access log entry.

### `packages/ui/app.py`

The Streamlit monitor described [above](#local-data-monitor).

## Landing page

`landing/index.html` is the project's marketing page: one static HTML file with inline CSS and vanilla JS, no build step, and no runtime dependencies. `package.json` only pulls in the Vercel CLI for deploying. Open the file directly in a browser or deploy the `landing/` folder to any static host.

```bash
open landing/index.html
```

It covers the pitch, the "why local" explanation, an animated features grid, persona preview cards, and install steps with copy buttons. Animations respect the "reduce motion" system setting.

## Troubleshooting

| Problem | Fix |
|---|---|
| `unable to open database file` or permission error from the pipeline | Give your terminal Full Disk Access, then restart it. |
| Hotkey does nothing | Grant Accessibility and Input Monitoring to your terminal and restart Twin. |
| Twin says it can't reach Claude yet | Add `ANTHROPIC_API_KEY` to `.env` in the repo root, or export it in your shell, then restart Twin. |
| "Calendar access isn't allowed yet" | Allow the Automation prompt, or enable Calendar for your terminal under Privacy & Security > Automation. |
| Twin knows nothing about your spending | Run `python3 run_pipeline.py`, and make sure `TWIN_DB_PATH` (if set) is the same for the pipeline and for Twin. |
| `ModuleNotFoundError: No module named '_tkinter'` | Install a Python with Tk (python.org installer, or `brew install python-tk`). |
| Plain opaque window instead of a translucent one | Install `pyobjc-framework-Cocoa` and `pyobjc-framework-Quartz`. |
| Pipeline inserts 0 transactions | It only reads the last 200 messages, and only bank SMS in the supported formats count. |

## Limitations

- macOS only.
- The SMS parser targets Indian bank and UPI message formats. Other formats are ignored until someone adds patterns for them.
- The pipeline reads only the 200 most recent messages per run and doesn't run on a schedule.
- Twin only looks at the five most recent transactions when chatting.
- Each chat message is answered on its own. Twin doesn't remember earlier turns of the conversation.
- There's no packaged `.app` yet. You run it from a terminal.
- No license file yet. Until one is added, default copyright applies.
