import discord
from discord.ext import commands
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Create a bot instance with a command prefix
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
# bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())

# Event: When the bot is ready
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

# Command: When someone types !hi
@bot.command()
async def hi(ctx):
    await ctx.send("Hello! 👋 I'm your friendly Discord bot.")

# Run the bot with token from .env file
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
if not DISCORD_TOKEN:
    raise ValueError("DISCORD_TOKEN not found in environment variables!")
bot.run(DISCORD_TOKEN)