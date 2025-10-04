

# bot.py
import os
import json
import asyncio
from discord.ext import commands
import discord
from aiohttp import web

# --- Environment Variables ---
TOKEN = os.getenv("DISCORD_TOKEN")
STAFF_CHANNEL_ID = os.getenv("STAFF_CHANNEL_ID")
SUGGESTIONS_CHANNEL_ID = os.getenv("SUGGESTIONS_CHANNEL_ID")
PENDING_FILE = "pending.json"

# --- Check Environment Variables ---
if not TOKEN:
    print("❌ DISCORD_TOKEN not found! Bot will not start.")
    TOKEN = None  # verhindert Absturz
if not STAFF_CHANNEL_ID or not SUGGESTIONS_CHANNEL_ID:
    print("⚠️ Channel IDs missing! Bot may not work properly.")
    
try:
    STAFF_CHANNEL_ID = int(STAFF_CHANNEL_ID)
    SUGGESTIONS_CHANNEL_ID = int(SUGGESTIONS_CHANNEL_ID)
except Exception:
    print("⚠️ Channel IDs must be integers!")

# --- Discord Intents ---
intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

# --- Pending Suggestions ---
def load_pending():
    try:
        with open(PENDING_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
            return {int(k): v for k, v in raw.items()}
    except FileNotFoundError:
        return {}

def save_pending(data):
    with open(PENDING_FILE, "w", encoding="utf-8") as f:
        json.dump({str(k): v for k, v in data.items()}, f, ensure_ascii=False, indent=2)

pending = load_pending()

# --- Keep-Alive Webserver for Railway ---
async def handle(request):
    return web.Response(text="OK")

async def start_webserver():
    app = web.Application()
    app.add_routes([web.get("/", handle)])
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()
    print("✅ Keep-alive webserver running on port 8080")

asyncio.get_event_loop().create_task(start_webserver())

# --- Events ---
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print("Suggestion bot ready.")

# --- Commands ---
@bot.command(name="suggest")
async def suggest(ctx, *, suggestion: str):
    staff_channel = bot.get_channel(STAFF_CHANNEL_ID)
    if not staff_channel:
        await ctx.send("⚠️ Staff channel not found.")
        return

    staff_msg = await staff_channel.send(f"📝 **New Suggestion** from {ctx.author.mention}:\n{suggestion}")
    pending[staff_msg.id] = {"author": ctx.author.id, "suggestion": suggestion}
    save_pending(pending)
    await ctx.send("✅ Your suggestion has been sent to staff for review.")

@commands.has_permissions(manage_messages=True)
@bot.command(name="approve")
async def approve(ctx, message_id: int):
    if message_id not in pending:
        await ctx.send("❌ Suggestion ID not found.")
        return

    data = pending.pop(message_id)
    save_pending(pending)

    suggestions_channel = bot.get_channel(SUGGESTIONS_CHANNEL_ID)
    if not suggestions_channel:
        await ctx.send("⚠️ Suggestions channel not found.")
        return

    public_msg = await suggestions_channel.send(f"💡 **Suggestion by <@{data['author']}>:**\n{data['suggestion']}")
    await public_msg.add_reaction("✅")
    await public_msg.add_reaction("❌")

    try:
        user = await bot.fetch_user(data["author"])
        await user.send(f"✅ Your suggestion was approved and posted: {public_msg.jump_url}")
    except Exception:
        pass

    await ctx.send("✅ Suggestion approved and posted publicly.")

@commands.has_permissions(manage_messages=True)
@bot.command(name="deny")
async def deny(ctx, message_id: int, *, reason: str = None):
    if message_id not in pending:
        await ctx.send("❌ Suggestion ID not found.")
        return

    data = pending.pop(message_id)
    save_pending(pending)

    try:
        user = await bot.fetch_user(data["author"])
        text = "❌ Your suggestion was denied."
        if reason:
            text += f"\nReason: {reason}"
        await user.send(text)
    except Exception:
        pass

    await ctx.send("✅ Suggestion denied and (if possible) user notified.")

@commands.has_permissions(manage_messages=True)
@bot.command(name="list_pending")
async def list_pending(ctx):
    if not pending:
        await ctx.send("There are no pending suggestions.")
        return

    lines = []
    for mid, data in list(pending.items())[:10]:
        snippet = data["suggestion"]
        if len(snippet) > 150:
            snippet = snippet[:147] + "..."
        lines.append(f"ID: `{mid}` — from <@{data['author']}> — {snippet}")
    await ctx.send("\n".join(lines))

# --- Run Bot ---
if TOKEN:
    bot.run(TOKEN)
else:
    print("❌ DISCORD_TOKEN not set. Bot cannot start.")
