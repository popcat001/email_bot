import os
import asyncio
import imaplib
import email
import re
import tempfile

import discord
from discord.ext import commands
from email.header import decode_header, make_header
import base64
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ========== CONFIG ==========

IMAP_HOST = "imap.gmail.com"
IMAP_USER = os.getenv("IMAP_USER")       # e.g. your Gmail address
IMAP_PASS = os.getenv("IMAP_PASS")       # Gmail App Password
IMAP_FOLDER = "INBOX"
POLL_SECS = 30                           # how often to poll

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
DISCORD_CHANNEL = int(os.getenv("DISCORD_CHANNEL"))  # channel ID as int

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)


# ========== HELPERS ==========

def _decode_header_value(value: str) -> str:
    try:
        return str(make_header(decode_header(value or "")))
    except Exception:
        return value or ""


def extract_email_html_and_snippet(msg):
    """
    Returns (subject, sender, html_body_with_inlined_images, text_snippet)
    - Rewrites cid:... image srcs into data: URLs so Playwright can render them.
    """
    subject = _decode_header_value(msg.get("Subject", "(no subject)"))
    sender = _decode_header_value(msg.get("From", "(unknown)"))

    html_body_raw = None
    text_body = None
    cid_images = {}  # cid -> data URL

    # First pass: collect HTML/text and cid images
    for part in msg.walk():
        ctype = part.get_content_type()
        disp = str(part.get("Content-Disposition") or "").lower()

        # HTML part
        if ctype == "text/html" and html_body_raw is None:
            payload = part.get_payload(decode=True)
            if payload:
                html_body_raw = payload.decode(errors="replace")

        # Plain-text part
        elif ctype == "text/plain" and text_body is None and "attachment" not in disp:
            payload = part.get_payload(decode=True)
            if payload:
                text_body = payload.decode(errors="replace")

        # Inline/attached images with Content-ID
        elif ctype.startswith("image/"):
            cid = part.get("Content-ID")
            if not cid:
                continue
            cid = cid.strip("<>")

            data = part.get_payload(decode=True)
            if not data:
                continue

            b64 = base64.b64encode(data).decode()
            data_url = f"data:{ctype};base64,{b64}"
            cid_images[cid] = data_url

    html_body = html_body_raw

    # Second pass: rewrite cid: references in HTML to data URLs
    if html_body and cid_images:
        for cid, data_url in cid_images.items():
            # handle both single and double quotes
            html_body = html_body.replace(f'src="cid:{cid}"',  f'src="{data_url}"')
            html_body = html_body.replace(f"src='cid:{cid}'",  f"src='{data_url}'")
            # just in case there is src=cid:cid without quotes
            html_body = html_body.replace(f"src=cid:{cid}", f'src="{data_url}"')

    # Build a text snippet for the embed
    if html_body:
        soup = BeautifulSoup(html_body, "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        text = soup.get_text(" ", strip=True)
    else:
        text = text_body or ""

    snippet = re.sub(r"\s+", " ", text).strip()[:1500] or "(no text)"

    return subject, sender, html_body, snippet


async def html_to_pdf(html_content: str, output_path: str):
    """
    Use Playwright (Chromium) to render HTML and save as PDF.
    """
    # Ensure we have a full HTML document
    if "<html" not in html_content.lower():
        html_content = f"""
        <html>
          <head>
            <meta charset="utf-8">
            <style>
              body {{ font-family: sans-serif; }}
            </style>
          </head>
          <body>{html_content}</body>
        </html>
        """

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            args=["--no-sandbox", "--disable-setuid-sandbox"]  # helpful on some hosts
        )
        page = await browser.new_page()
        await page.set_content(html_content, wait_until="networkidle")
        await page.pdf(path=output_path, format="A4", print_background=True)
        await browser.close()


def safe_filename_from_subject(subject: str) -> str:
    # Simple safe filename: strip bad chars and limit length
    base = re.sub(r"[^\w\-]+", "_", subject)[:50] or "email"
    return f"{base}.pdf"


# ========== POLLING LOOP ==========

async def poll_and_forward():
    await bot.wait_until_ready()
    channel = await bot.fetch_channel(DISCORD_CHANNEL)
    print(f"Forwarding emails to channel: {channel} ({channel.id})")

    while not bot.is_closed():
        try:
            with imaplib.IMAP4_SSL(IMAP_HOST) as M:
                M.login(IMAP_USER, IMAP_PASS)
                M.select(IMAP_FOLDER)
                typ, data = M.search(None, "(UNSEEN)")
                if typ != "OK":
                    print("IMAP search error:", typ, data)
                    M.logout()
                    await asyncio.sleep(POLL_SECS)
                    continue

                for num in data[0].split():
                    typ, msg_data = M.fetch(num, "(RFC822)")
                    if typ != "OK":
                        print("IMAP fetch error:", typ, msg_data)
                        continue

                    raw = msg_data[0][1]
                    msg = email.message_from_bytes(raw)

                    subject, sender, html_body, snippet = extract_email_html_and_snippet(msg)

                    # Fallback: if no HTML, wrap text snippet into simple HTML
                    if not html_body:
                        html_body = f"<html><body><pre>{snippet}</pre></body></html>"

                    # Create temp PDF file
                    safe_name = safe_filename_from_subject(subject)
                    pdf_path = os.path.join(tempfile.gettempdir(), safe_name)

                    print(f"Rendering email '{subject}' to PDF...")
                    try:
                        await html_to_pdf(html_body, pdf_path)
                    except Exception as e:
                        print("PDF render error:", e)
                        # fallback: just send text without PDF
                        embed = discord.Embed(title=subject, description=snippet)
                        # anonymize sender if you want:
                        embed.add_field(name="From", value="Anonymous", inline=False)
                        await channel.send(embed=embed)
                        # mark as seen and continue
                        M.store(num, "+FLAGS", "\\Seen")
                        continue

                    # Build Discord embed
                    embed = discord.Embed(title=subject, description=snippet)
                    # anonymize sender:
                    embed.add_field(name="From", value="Anonymous", inline=False)

                    try:
                        await channel.send(
                            embed=embed,
                            file=discord.File(pdf_path, filename=safe_name)
                        )
                    finally:
                        # cleanup temp file
                        if os.path.exists(pdf_path):
                            os.remove(pdf_path)

                    # Mark email as seen
                    M.store(num, "+FLAGS", "\\Seen")

                M.logout()

        except Exception as e:
            print("Poll error:", e)

        await asyncio.sleep(POLL_SECS)


# ========== BOT EVENTS ==========

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} (id={bot.user.id})")
    # Start polling loop
    bot.loop.create_task(poll_and_forward())


# ========== ENTRYPOINT ==========

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        raise RuntimeError("DISCORD_TOKEN env var not set")
    if not IMAP_USER or not IMAP_PASS:
        raise RuntimeError("IMAP_USER / IMAP_PASS env vars not set")

    bot.run(DISCORD_TOKEN)