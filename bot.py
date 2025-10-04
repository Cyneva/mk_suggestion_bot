# bot.py
import os
import json
from dotenv import load_dotenv
import discord
from discord.ext import commands

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
STAFF_CHANNEL_ID = int(os.getenv("STAFF_CHANNEL_ID"))
SUGGESTIONS_CHANNEL_ID = int(os.getenv("SUGGESTIONS_CHANNEL_ID"))
PENDING_FILE = "pending.json"

intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
intents.reactions = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

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

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print("Suggestion bot ready.")

@bot.command(name="suggest")
async def suggest(ctx, *, suggestion: str):
    """User submits a suggestion; it is sent to staff channel for review."""
    staff_channel = bot.get_channel(STAFF_CHANNEL_ID)
    if staff_channel is None:
        await ctx.send("⚠️ Staff channel not found. Check the STAFF_CHANNEL_ID in .env.")
        return

    staff_msg = await staff_channel.send(
        f"📝 **New Suggestion** from {ctx.author.mention}:\n{suggestion}"
    )
    pending[staff_msg.id] = {"author": ctx.author.id, "suggestion": suggestion}
    save_pending(pending)
    await ctx.send("✅ Your suggestion has been sent to staff for review. Thank you!")

@commands.has_permissions(manage_messages=True)
@bot.command(name="approve")
async def approve(ctx, message_id: int):
    """Staff: approve a pending suggestion by the STAFF channel message ID."""
    if message_id not in pending:
        await ctx.send("❌ Suggestion ID not found in pending list.")
        return

    data = pending.pop(message_id)
    save_pending(pending)

    suggestions_channel = bot.get_channel(SUGGESTIONS_CHANNEL_ID)
    if suggestions_channel is None:
        await ctx.send("⚠️ Suggestions channel not found. Check SUGGESTIONS_CHANNEL_ID.")
        return

    public_msg = await suggestions_channel.send(
        f"💡 **Suggestion by <@{data['author']}>:**\n{data['suggestion']}"
    )
    # add ✅ (upvote) and ❌ (downvote)
    await public_msg.add_reaction("✅")
    await public_msg.add_reaction("❌")

    # try to notify the author
    try:
        user = await bot.fetch_user(data["author"])
        await user.send(f"✅ Your suggestion was approved and posted: {public_msg.jump_url}")
    except Exception:
        # user may have DMs closed; ignore
        pass

    await ctx.send("✅ Suggestion approved and posted publicly.")

@commands.has_permissions(manage_messages=True)
@bot.command(name="deny")
async def deny(ctx, message_id: int, *, reason: str = None):
    """Staff: deny a pending suggestion by the STAFF channel message ID (optional reason)."""
    if message_id not in pending:
        await ctx.send("❌ Suggestion ID not found.")
        return

    data = pending.pop(message_id)
    save_pending(pending)

    # notify user if possible
    try:
        user = await bot.fetch_user(data["author"])
        text = "❌ Your suggestion was denied."
        if reason:
            text += f"\nReason: {reason}"
        await user.send(text)
    except Exception:
        pass

    await ctx.send("✅ Suggestion denied and (if possible) the user was notified.")

@commands.has_permissions(manage_messages=True)
@bot.command(name="list_pending")
async def list_pending(ctx):
    """Staff helper: list pending suggestions (shows up to 10). Staff can copy the IDs from here."""
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

# run
if not TOKEN:
    print("No BOT_TOKEN found in environment. Exiting.")
else:
    bot.run(TOKEN)
