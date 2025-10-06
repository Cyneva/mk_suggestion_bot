# bot.py
import os
import json
import asyncio
import discord
from discord.ext import commands
from discord import app_commands
from aiohttp import web

TOKEN = os.getenv("DISCORD_TOKEN")
DATA_FILE = "suggestions_data.json"

# --- Keep-alive Webserver for Railway ---
async def start_webserver():
    app = web.Application()
    app.add_routes([web.get("/", lambda request: web.Response(text="OK"))])
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()
    print("✅ Keep-alive webserver running on port 8080")

asyncio.run(start_webserver())

# --- Bot Setup ---
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# --- Helper: Load/Save Data ---
def load_data():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

data = load_data()

def ensure_guild_data(guild_id):
    if str(guild_id) not in data:
        data[str(guild_id)] = {
            "channels": {"staff": None, "public": None, "suggestions": None},
            "pending": {},
            "next_staff_id": 1,
            "next_public_id": 1
        }

# --- UI Components ---
class SuggestionModal(discord.ui.Modal, title="Submit a Suggestion"):
    suggestion_text = discord.ui.TextInput(
        label="Your Suggestion",
        style=discord.TextStyle.paragraph,
        placeholder="your suggestion",
        required=True,
        max_length=1000
    )

    async def on_submit(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild_id)
        ensure_guild_data(guild_id)
        guild_data = data[guild_id]
        staff_channel_id = guild_data["channels"]["staff"]

        if not staff_channel_id:
            await interaction.response.send_message(
                "Setup is incomplete. Please contact staff.", ephemeral=True
            )
            return

        staff_channel = interaction.client.get_channel(staff_channel_id)
        if not staff_channel:
            await interaction.response.send_message(
                "Staff channel not found. Please contact an admin.", ephemeral=True
            )
            return

        suggestion_id = guild_data["next_staff_id"]
        guild_data["next_staff_id"] += 1

        staff_msg = await staff_channel.send(
            f"New suggestion (ID {suggestion_id}) from {interaction.user.mention}:\n> {self.suggestion_text.value}"
        )

        guild_data["pending"][str(suggestion_id)] = {
            "author_id": interaction.user.id,
            "text": self.suggestion_text.value,
            "staff_msg_id": staff_msg.id
        }
        save_data(data)

        await interaction.response.send_message(
            "Your suggestion has been sent to staff for review.", ephemeral=True
        )

class SuggestionButtonView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Make suggestion", style=discord.ButtonStyle.primary)
    async def create_suggestion(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SuggestionModal())

# --- Slash Commands ---
@tree.command(name="setup_suggestion_channel", description="Setup a channel for suggestions.")
@app_commands.checks.has_permissions(manage_guild=True)
@app_commands.describe(channel_type="Type of channel to set up (staff, public, suggestions)")
async def setup_suggestion_channel(interaction: discord.Interaction, channel_type: str):
    if channel_type not in ["staff", "public", "suggestions"]:
        await interaction.response.send_message(
            "Invalid channel type. Use 'staff', 'public' or 'suggestions'.", ephemeral=True
        )
        return

    ensure_guild_data(interaction.guild_id)
    data[str(interaction.guild_id)]["channels"][channel_type] = interaction.channel_id
    save_data(data)

    if channel_type == "suggestions":
        view = SuggestionButtonView()
        await interaction.channel.send("Submit a suggestion by clicking the button below:", view=view)

    await interaction.response.send_message(
        f"This channel has been set as the {channel_type} channel.", ephemeral=True
    )

@tree.command(name="approve_suggestion", description="Approve a suggestion by ID.")
@app_commands.checks.has_permissions(manage_messages=True)
async def approve_suggestion(interaction: discord.Interaction, suggestion_id: int):
    guild_id = str(interaction.guild_id)
    ensure_guild_data(guild_id)
    guild_data = data[guild_id]
    pending = guild_data["pending"]

    if str(suggestion_id) not in pending:
        await interaction.response.send_message("Suggestion ID not found.", ephemeral=True)
        return

    info = pending.pop(str(suggestion_id))
    save_data(data)

    # öffentliche ID nur für genehmigte Vorschläge
    public_id = guild_data.get("next_public_id", 1)
    guild_data["next_public_id"] = public_id + 1
    save_data(data)

    public_channel_id = guild_data["channels"]["public"]
    if not public_channel_id:
        await interaction.response.send_message("Public channel not set up.", ephemeral=True)
        return

    public_channel = interaction.client.get_channel(public_channel_id)
    if not public_channel:
        await interaction.response.send_message("Public channel not found.", ephemeral=True)
        return

    embed = discord.Embed(
        title=f"Suggestion #{public_id}",
        description=info["text"],
        color=discord.Color.blue()
    )
    public_msg = await public_channel.send(embed=embed)
    await public_msg.add_reaction("✅")
    await public_msg.add_reaction("❌")

    try:
        user = await interaction.client.fetch_user(info["author_id"])
        await user.send(f"Your suggestion was approved: {public_msg.jump_url}")
    except Exception:
        pass

    await interaction.response.send_message("Suggestion approved and posted publicly.", ephemeral=True)

@tree.command(name="deny_suggestion", description="Deny a suggestion by ID.")
@app_commands.checks.has_permissions(manage_messages=True)
@app_commands.describe(suggestion_id="The suggestion ID", reason="Reason for denial (optional)")
async def deny_suggestion(interaction: discord.Interaction, suggestion_id: int, reason: str = None):
    guild_id = str(interaction.guild_id)
    ensure_guild_data(guild_id)
    guild_data = data[guild_id]
    pending = guild_data["pending"]

    if str(suggestion_id) not in pending:
        await interaction.response.send_message("Suggestion ID not found.", ephemeral=True)
        return

    info = pending.pop(str(suggestion_id))
    save_data(data)

    try:
        user = await interaction.client.fetch_user(info["author_id"])
        msg = "Your suggestion was denied."
        if reason:
            msg += f"\nReason: {reason}"
        await user.send(msg)
    except Exception:
        pass

    await interaction.response.send_message("Suggestion denied and user notified (if possible).", ephemeral=True)

@tree.command(name="pending_suggestions", description="List all pending suggestions.")
@app_commands.checks.has_permissions(manage_messages=True)
async def pending_suggestions(interaction: discord.Interaction):
    guild_id = str(interaction.guild_id)
    ensure_guild_data(guild_id)
    guild_data = data[guild_id]
    pending = guild_data["pending"]

    if not pending:
        await interaction.response.send_message("There are no pending suggestions.", ephemeral=False)
        return

    embed = discord.Embed(
        title="Pending Suggestions",
        color=discord.Color.orange()
    )

    for sid, info in sorted(pending.items(), key=lambda x: int(x[0])):
        member = interaction.guild.get_member(info["author_id"])
        name = member.display_name if member else f"User ID {info['author_id']}"
        snippet = info["text"]
        if len(snippet) > 200:
            snippet = snippet[:197] + "..."
        embed.add_field(name=f"#{sid} — from {name}", value=snippet, inline=False)

    await interaction.response.send_message(embed=embed, ephemeral=False)

# --- Bot Events ---
@bot.event
async def on_ready():
    await tree.sync()
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print("Suggestion bot ready and slash commands synced.")

# --- Run Bot ---
if TOKEN:
    bot.run(TOKEN)
else:
    print("❌ DISCORD_TOKEN not set. Bot cannot start.")
