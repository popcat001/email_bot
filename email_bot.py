# bot_email_forwarder.py
import asyncio, imaplib, email, re
from email.header import decode_header, make_header
from discord.ext import commands
import discord
import os

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ==== CONFIG ====
IMAP_HOST   = "imap.gmail.com"   # e.g. imap.gmail.com
IMAP_USER   = "discordemailbot.2025@gmail.com"
IMAP_PASS   = os.getenv('IMAP_PASS')  # app password
IMAP_FOLDER = "INBOX"
POLL_SECS   = 30

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
DISCORD_CHANNEL = int(os.getenv('DISCORD_CHANNEL'))  # channel ID (int)

# ==== DISCORD BOT ====
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

def _decode(s):
    try:
        return str(make_header(decode_header(s)))
    except:
        return s or ""

def fetch_unseen_messages():
    """Return a list of (subject, from_, body_text) for UNSEEN mail and mark them seen."""
    msgs = []
    with imaplib.IMAP4_SSL(IMAP_HOST) as M:
        M.login(IMAP_USER, IMAP_PASS)
        M.select(IMAP_FOLDER)
        typ, data = M.search(None, '(UNSEEN)')
        if typ != 'OK':
            return msgs

        for num in data[0].split():
            typ, msg_data = M.fetch(num, '(RFC822)')
            if typ != 'OK':
                continue
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)

            subject = _decode(msg.get('Subject', ''))
            from_   = _decode(msg.get('From', ''))

            # get a short text snippet
            body_text = ""
            if msg.is_multipart():
                for part in msg.walk():
                    ctype = part.get_content_type()
                    disp  = str(part.get("Content-Disposition", ""))
                    if ctype == "text/plain" and "attachment" not in disp:
                        body_text = part.get_payload(decode=True).decode(errors="replace")
                        break
            else:
                body_text = msg.get_payload(decode=True).decode(errors="replace") if msg.get_payload() else ""

            # condense whitespace and trim
            body_snippet = re.sub(r"\s+", " ", body_text).strip()[:500]

            msgs.append((subject, from_, body_snippet))

            # mark seen
            M.store(num, '+FLAGS', '\\Seen')
        M.close()
        M.logout()
    return msgs

async def poll_and_forward():
    await bot.wait_until_ready()
    channel = bot.get_channel(DISCORD_CHANNEL)
    while not bot.is_closed():
        try:
            for subject, from_, snippet in fetch_unseen_messages():
                embed = discord.Embed(
                    title=_decode(subject) or "(no subject)",
                    description=snippet or " ",
                )
                embed.add_field(name="From", value=from_ or "(unknown)", inline=False)
                await channel.send(embed=embed)
        except Exception as e:
            # log the error; keep running
            print("Poll error:", e)
        await asyncio.sleep(POLL_SECS)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    bot.loop.create_task(poll_and_forward())

bot.run(DISCORD_TOKEN)