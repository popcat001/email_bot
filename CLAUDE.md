# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Discord bot that forwards email messages from Gmail to a Discord channel. The bot polls an IMAP inbox for unseen messages and posts them as Discord embeds.

## Core Architecture

### Two Bot Files
- **bot.py**: Simple Discord bot template with basic command functionality (!hi command)
- **email_bot.py**: Main email forwarding bot with IMAP polling functionality

The main application is `email_bot.py`, which combines Discord bot functionality with IMAP email polling in a single asyncio event loop.

### Email Forwarding Flow
1. Bot starts and waits until Discord connection is ready
2. Background task `poll_and_forward()` runs every 30 seconds (configurable via POLL_SECS)
3. `fetch_unseen_messages()` connects to Gmail via IMAP, retrieves UNSEEN messages
4. Messages are marked as SEEN to prevent duplicate forwarding
5. Email data (subject, from, body snippet) is formatted into Discord embeds
6. Embeds are sent to the configured Discord channel

### Key Implementation Details
- Uses synchronous IMAP (imaplib) within async context - IMAP operations run in the main thread
- Email body extraction handles both multipart and simple messages, prioritizing text/plain parts
- Body snippets are limited to 500 characters with whitespace condensed
- Email headers are decoded to handle various encodings (UTF-8, quoted-printable, etc.)
- Error handling allows the polling loop to continue on failures

## Environment Configuration

Required environment variables in `.env`:
- `DISCORD_TOKEN`: Discord bot token
- `DISCORD_CHANNEL`: Channel ID (integer) where emails will be forwarded
- `IMAP_PASS`: Gmail app password (not regular password)

Hard-coded configuration in `email_bot.py`:
- `IMAP_HOST`: imap.gmail.com
- `IMAP_USER`: discordemailbot.2025@gmail.com
- `IMAP_FOLDER`: INBOX
- `POLL_SECS`: 30 seconds

## Development Commands

### Setup
```bash
# Create virtual environment (Python 3.11+)
python -m venv .venv
source .venv/bin/activate  # or `.venv/bin/activate` on Windows

# Install dependencies
pip install -r requirements.txt
```

### Running
```bash
# Run the email forwarding bot
python email_bot.py

# Run the simple test bot
python bot.py
```

### Dependencies
- discord.py: Discord API wrapper
- python-dotenv: Environment variable loading

Project uses both pip (requirements.txt) and uv (pyproject.toml/uv.lock) for dependency management.

## Deployment

The project includes `render.yaml` for Render.com deployment:
- Configured as a worker (not a web service)
- Build: `pip install -r requirements.txt`
- Start: `python bot.py` (note: this may need to be changed to `email_bot.py` for email forwarding)
- Auto-deploy enabled

## Gmail Setup Requirements

The email bot requires:
1. Gmail account with IMAP enabled
2. App password (not regular password) for authentication
3. Less secure app access or app-specific password configured in Google account settings

When IMAP operations fail, check:
- App password is valid and set in .env
- IMAP is enabled in Gmail settings
- Account is not locked or requiring additional verification
