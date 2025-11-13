# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Discord bot that forwards email messages from Gmail to a Discord channel. The bot polls an IMAP inbox for unseen messages and posts them as Discord embeds.

## Core Architecture

### Bot Files
- **bot.py**: Simple Discord bot template with basic command functionality (!hi command)
- **email_bot.py**: Basic email forwarding bot with IMAP polling functionality
- **email_bot_3.py**: Enhanced email forwarding bot with image handling and HTML parsing
- **email_bot_pdf.py**: Advanced bot that renders HTML emails as PDFs using Playwright

Each bot file represents an evolution in functionality, with email_bot_3.py and email_bot_pdf.py being the most feature-rich options.

### Email Forwarding Flow (email_bot_3.py)
1. Bot starts and waits until Discord connection is ready
2. Background task `poll_and_forward()` runs every 30 seconds (configurable via POLL_SECS)
3. Connects to Gmail via IMAP and retrieves UNSEEN messages
4. Messages are marked as SEEN to prevent duplicate forwarding
5. Email is parsed using `parse_email_to_discord_payload()`:
   - Extracts subject, sender (masked as "Anonymous"), HTML/text body
   - Downloads inline images and attachments from MIME parts
   - Fetches external images from HTML (up to 3, saved to temp files)
   - Converts HTML to text using BeautifulSoup, removes scripts/styles
6. Creates Discord embed with subject, body snippet (up to 1500 chars), and "From: Anonymous"
7. Attaches images: first image embedded in Discord, remaining as file attachments
8. Sends to configured Discord channel and cleans up temp files

### PDF Rendering Flow (email_bot_pdf.py)
1. Bot starts and waits until Discord connection is ready
2. Background task `poll_and_forward()` runs every 30 seconds (configurable via POLL_SECS)
3. Connects to Gmail via IMAP and retrieves UNSEEN messages
4. Email is parsed using `extract_email_html_and_snippet()`:
   - Extracts subject, sender, HTML body, and text snippet
   - Collects inline images with Content-ID (cid:) references
   - Converts inline images to base64 data URLs
   - Rewrites `cid:` image references in HTML to embedded `data:` URLs
5. If no HTML body exists, wraps plain text in simple HTML
6. Uses Playwright (Chromium) to render HTML email as PDF:
   - Launches headless browser with sandboxing disabled
   - Loads HTML content and waits for network idle
   - Renders to A4 PDF with background graphics enabled
   - Saves to temp file with sanitized filename (derived from subject)
7. Creates Discord embed with subject, snippet (up to 1500 chars), and "From: Anonymous"
8. Attaches rendered PDF to Discord message
9. Marks email as SEEN and cleans up temp PDF file
10. On PDF rendering errors, falls back to text-only embed

### Key Implementation Details

**Common to all bots:**
- Uses synchronous IMAP (imaplib) within async context - IMAP operations run in the main thread
- Email headers are decoded to handle various encodings (UTF-8, quoted-printable, etc.)
- Sender information is always masked as "Anonymous" for privacy
- Error handling allows the polling loop to continue on failures
- Temp files saved to `tempfile.gettempdir()` and cleaned up after sending

**email_bot_3.py specific:**
- Email body extraction handles both multipart and simple messages, prioritizing HTML over plain text
- BeautifulSoup parses HTML to extract text and find external image URLs
- External images fetched via HTTP requests (up to 3 images)
- First image embedded in Discord embed, remaining as file attachments

**email_bot_pdf.py specific:**
- Inline images (cid:) converted to base64 data URLs for self-contained HTML
- Playwright's Chromium engine renders HTML with full CSS/layout support
- Browser launched with `--no-sandbox --disable-setuid-sandbox` for compatibility
- Waits for "networkidle" before PDF generation to ensure all resources loaded
- PDF filename sanitized from email subject (removes special chars, limits to 50 chars)
- Falls back to text-only embed if PDF rendering fails

## Environment Configuration

Required environment variables in `.env`:
- `DISCORD_TOKEN`: Discord bot token
- `DISCORD_CHANNEL`: Channel ID (integer) where emails will be forwarded
- `IMAP_PASS`: Gmail app password (not regular password)
- `IMAP_USER`: Gmail email address (required for email_bot_pdf.py)

Hard-coded configuration:
- `IMAP_HOST`: imap.gmail.com
- `IMAP_USER`: discordemailbot.2025@gmail.com (hardcoded in email_bot.py and email_bot_3.py)
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
# Run the PDF rendering bot (best for preserving email layout)
python email_bot_pdf.py

# Run the enhanced image-forwarding bot
python email_bot_3.py

# Run the basic email forwarding bot
python email_bot.py

# Run the simple test bot
python bot.py
```

### Dependencies
- **discord.py**: Discord API wrapper (all bots)
- **python-dotenv**: Environment variable loading (all bots)
- **beautifulsoup4**: HTML parsing (email_bot_3.py, email_bot_pdf.py)
- **requests**: HTTP requests for external images (email_bot_3.py)
- **playwright**: Browser automation for PDF rendering (email_bot_pdf.py)
  - After installing, run: `playwright install chromium`

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

## Troubleshooting

### Discord Channel Access Errors
**Error: `discord.errors.NotFound: 404 Not Found (error code: 10003): Unknown Channel`**

This error occurs when the bot cannot access the specified channel. Common causes:
1. **Bot not added to server**: Generate an invite URL with proper permissions and add the bot to the server
   - Required permissions: View Channels, Send Messages, Embed Links, Attach Files
2. **Wrong channel ID**: Right-click the channel in Discord > Copy ID (requires Developer Mode enabled)
3. **Bot lacks permissions**: Check the bot has permission to view and send messages in that specific channel
4. **Private/thread channels**: Ensure bot has access to private channels or threads

To debug channel access, you can temporarily add code to list all accessible channels:
```python
for guild in bot.guilds:
    print(f"Server: {guild.name}")
    for channel in guild.text_channels:
        print(f"  - #{channel.name} (ID: {channel.id})")
```

### Sender Still Showing Email Address
If sender email is visible after updating code, restart the bot process. Python loads code into memory at startup, so changes require a restart to take effect.

### Playwright/PDF Rendering Issues (email_bot_pdf.py)
**Error: `playwright._impl._api_types.Error: Executable doesn't exist`**

This means Chromium browser is not installed. After installing the playwright package, run:
```bash
playwright install chromium
```

**PDF rendering fails on some systems:**
- The bot uses `--no-sandbox --disable-setuid-sandbox` flags for compatibility
- On restricted environments (containers, some cloud hosts), you may need additional setup
- Check system has sufficient resources (memory) for browser rendering
- Verify chromium can launch: `playwright install --with-deps chromium`

**Inline images not showing in PDF:**
- Check that emails have proper Content-ID headers for inline images
- Verify base64 encoding is working correctly
- Some email clients use different methods for embedding images
