import asyncio, imaplib, email, re
import os, imaplib, email, re, tempfile, discord
from discord.ext import commands
from email.header import decode_header, make_header
from bs4 import BeautifulSoup
import requests

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())

# ==== CONFIG ====
IMAP_HOST   = "imap.gmail.com"   # e.g. imap.gmail.com
IMAP_USER   = "discordemailbot.2025@gmail.com"
IMAP_PASS = os.getenv("IMAP_PASS")
IMAP_FOLDER = "INBOX"
POLL_SECS   = 30

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
DISCORD_CHANNEL = int(os.getenv('DISCORD_CHANNEL'))  # channel ID (int)

# ==== DISCORD BOT ====
def _decode_header_value(value: str) -> str:
    try:
        return str(make_header(decode_header(value or "")))
    except Exception:
        return value or ""


def parse_email_to_discord_payload(msg):
    """
    Takes an email.message.Message and returns:
    subject, sender, text_snippet, image_file_paths
    (image_file_paths are local temp file paths ready to send)
    """
    subject = _decode_header_value(msg.get("Subject", "(no subject)"))
    sender  = _decode_header_value(msg.get("From", "(unknown)"))

    html_body = None
    text_body = None
    image_paths = []

    # 1) First pass: walk MIME parts
    for part in msg.walk():
        ctype = part.get_content_type()
        disp  = str(part.get("Content-Disposition") or "").lower()

        # Capture HTML / plain text
        if ctype == "text/html" and html_body is None:
            payload = part.get_payload(decode=True)
            if payload:
                html_body = payload.decode(errors="replace")

        elif ctype == "text/plain" and text_body is None:
            payload = part.get_payload(decode=True)
            if payload:
                text_body = payload.decode(errors="replace")

        # Capture inline + attached images, OR attachments with image-like filenames
        elif ctype.startswith("image/") or ("attachment" in disp and part.get_filename()):
            filename = part.get_filename()
            cid = (part.get("Content-ID") or "").strip("<>")

            if not filename:
                # Guess from type or CID
                ext = ctype.split("/")[-1] if "/" in ctype else "bin"
                base = cid or "image"
                filename = f"{base}.{ext}"

            file_data = part.get_payload(decode=True)
            if not file_data:
                continue

            tmp_path = os.path.join(tempfile.gettempdir(), filename)
            with open(tmp_path, "wb") as f:
                f.write(file_data)
            image_paths.append(tmp_path)

    # 2) Prefer HTML for text, and also mine external image URLs from it
    if html_body:
        soup = BeautifulSoup(html_body, "html.parser")

        # Remove script/style
        for tag in soup(["script", "style"]):
            tag.decompose()

        # Text content
        text = soup.get_text(" ", strip=True)

        # External images: <img src="https://...">
        img_tags = soup.find_all("img")
        for img in img_tags[:3]:  # limit to first 3 images
            src = img.get("src") or ""
            if src.startswith("http://") or src.startswith("https://"):
                try:
                    r = requests.get(src, timeout=5)
                    r.raise_for_status()
                    # derive filename from URL
                    name = src.split("/")[-1] or "image_from_url"
                    if not any(name.lower().endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".gif", ".webp"]):
                        name += ".png"
                    tmp_path = os.path.join(tempfile.gettempdir(), name)
                    with open(tmp_path, "wb") as f:
                        f.write(r.content)
                    image_paths.append(tmp_path)
                except Exception as e:
                    print("Failed to fetch external image:", src, e)
    else:
        text = text_body or ""

    snippet = re.sub(r"\s+", " ", text).strip()[:1500] or "(no text)"

    return subject, sender, snippet, image_paths

async def poll_and_forward():
    await bot.wait_until_ready()
    channel = await bot.fetch_channel(DISCORD_CHANNEL)
    while not bot.is_closed():
        try:
            with imaplib.IMAP4_SSL(IMAP_HOST) as M:
                M.login(IMAP_USER, IMAP_PASS)
                M.select(IMAP_FOLDER)
                typ, data = M.search(None, "(UNSEEN)")
                for num in data[0].split():
                    typ, msg_data = M.fetch(num, "(RFC822)")
                    msg = email.message_from_bytes(msg_data[0][1])

                    # NEW: parse HTML, text, images
                    subject, sender, desc, image_paths = parse_email_to_discord_payload(msg)

                    embed = discord.Embed(title=subject, description=desc)
                    embed.add_field(name="From", value="Anonymous", inline=False)

                    files = []
                    try:
                        if image_paths:
                            # First image shown inside the embed
                            first = image_paths[0]
                            first_name = os.path.basename(first)
                            files.append(discord.File(first, filename=first_name))
                            embed.set_image(url=f"attachment://{first_name}")

                            # Remaining images as attachments
                            for extra in image_paths[1:]:
                                files.append(
                                    discord.File(extra, filename=os.path.basename(extra))
                                )

                        if files:
                            await channel.send(embed=embed, files=files)
                        else:
                            await channel.send(embed=embed)

                    finally:
                        # Clean up temp files
                        for fp in image_paths:
                            if os.path.exists(fp):
                                os.remove(fp)

                    M.store(num, "+FLAGS", "\\Seen")
                M.logout()
        except Exception as e:
            print("Poll error:", e)

        await asyncio.sleep(POLL_SECS)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    bot.loop.create_task(poll_and_forward())

bot.run(DISCORD_TOKEN)