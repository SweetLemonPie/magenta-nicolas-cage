# === Imports ===
import os
import json
import random
import asyncio
import discord
import re
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
from keep_alive import keep_alive


# === Environment Setup ===
load_dotenv()
TOKEN = os.environ['DISCORD_TOKEN']

# === File and Directory Constants ===
CHANNEL_FILE = "selected_channels.json"
SOUNDS_DIR = "sounds"
MESSAGES_FILE = "messages.json"

# === Load Messages ===
messages = []
with open(MESSAGES_FILE, "r") as f:
    content = f.read()
    messages = re.findall(r'"([^"]*)"', content)

# === Intents and Bot Setup ===
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix='!', intents=intents)

# === Global Storage ===
channel_map = {}       # guild_id: {channel_id, interval}
message_tasks = {}     # guild_id: asyncio.Task
voice_clients = {}     # guild_id: discord.VoiceClient


# === Channel Data Persistence ===
def load_channels():
    """Load the configured channel settings from file."""
    global channel_map
    try:
        with open(CHANNEL_FILE, "r") as f:
            channel_map = json.load(f)
    except FileNotFoundError:
        channel_map = {}
        print(f"Channel file '{CHANNEL_FILE}' not found. Using empty map.")
    except json.JSONDecodeError:
        channel_map = {}
        print(f"Invalid JSON in '{CHANNEL_FILE}'. Using empty map.")


def save_channels():
    """Save the configured channel settings to file."""
    with open(CHANNEL_FILE, "w") as f:
        json.dump(channel_map, f, indent=2)


# === Message System ===
async def send_message(guild_id):
    """Send a random message to the configured channel for a guild."""
    data = channel_map.get(guild_id)
    if not data:
        print(f"No channel configured for guild {guild_id}.")
        return

    channel = bot.get_channel(data["channel_id"])
    if not channel:
        print(f"Channel {data['channel_id']} not found.")
        return

    try:
        message = random.choice(messages)
        if isinstance(channel, discord.ForumChannel):
            await channel.create_thread(name="Random Message", content=message)
        elif isinstance(channel, (discord.TextChannel, discord.Thread)):
            await channel.send(message)
        else:
            print(f"Channel {data['channel_id']} is not a text-based channel.")
    except discord.errors.Forbidden:
        print(f"Missing permissions to send message in channel {data['channel_id']}")
    except Exception as e:
        print(f"Error sending message to channel {data['channel_id']}: {e}")


async def message_loop(guild_id, interval):
    """Loop that sends a message at every interval (in hours)."""
    await bot.wait_until_ready()
    while True:
        await asyncio.sleep(interval * 3600)
        await send_message(guild_id)

def start_message_task(guild_id, interval):
    """Start or restart the message loop for a guild."""
    if guild_id in message_tasks:
        message_tasks[guild_id].cancel()

    message_tasks[guild_id] = bot.loop.create_task(
        message_loop(guild_id, interval)
    )


# === Soundboard System ===
async def play_random_sound(guild_id):
    """Plays a random sound from the sounds directory in the voice channel."""
    if guild_id not in voice_clients or not voice_clients[guild_id]:
        return

    vc = voice_clients[guild_id]
    sound_files = [
        f for f in os.listdir(SOUNDS_DIR)
        if f.endswith(('.mp3', '.wav', '.ogg'))
    ]
    if not sound_files:
        print("No sound files found in the sounds directory.")
        return

    sound_file = random.choice(sound_files)
    sound_path = os.path.join(SOUNDS_DIR, sound_file)

    try:
        vc.play(discord.FFmpegPCMAudio(executable="ffmpeg", source=sound_path),
                after=lambda e: print(f"Finished playing: {sound_file}"))
    except Exception as e:
        print(f"Error playing sound {sound_file}: {e}")


async def soundboard_loop(guild_id):
    """Loop to continuously play random sounds every 120 seconds."""
    while True:
        await asyncio.sleep(random.randint(30, 300))
        await play_random_sound(guild_id)


async def leave_voice_channel(guild_id):
    """Leaves the voice channel and removes the client from tracking."""
    if guild_id in voice_clients and voice_clients[guild_id]:
        vc = voice_clients[guild_id]
        await vc.disconnect()
        del voice_clients[guild_id]
        print(f"Left voice channel in guild {guild_id}")


# === Bot Event Handlers ===
@bot.event
async def on_ready():
    """Triggered when the bot connects and is ready."""
    print(f'Logged in as {bot.user}')
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Command sync failed: {e}")

    load_channels()
    for guild_id, data in channel_map.items():
        start_message_task(guild_id, data["interval"])


@bot.event
async def on_guild_join(guild):
    """Send a welcome message to the first available text channel."""
    for channel in guild.text_channels:
        try:
            await channel.send("hello,this magenta nicolas cage official brand account,verified")
            break
        except discord.errors.Forbidden:
            print(f"Missing permissions to send message in channel {channel.id} in guild {guild.id}")
        except Exception as e:
            print(f"Error sending message to channel {channel.id} in guild {guild.id}: {e}")


@bot.event
async def on_message(message):
    """Respond to keywords or commands in messages."""
    if message.author == bot.user:
        return

    guild_id = str(message.guild.id)

    # Leave voice channel if requested
    if ("leave" in message.content.lower() or "hop off" in message.content.lower()) and bot.user in message.mentions:

        if guild_id in voice_clients:
            await leave_voice_channel(guild_id)
            return

    # Join voice channel if requested
    if "hop on" in message.content.lower() or "call" in message.content.lower():
        if message.author.voice and message.author.voice.channel:
            channel = message.author.voice.channel
            try:
                if guild_id in voice_clients:
                    await voice_clients[guild_id].move_to(channel)
                else:
                    vc = await channel.connect()
                    voice_clients[guild_id] = vc
                    bot.loop.create_task(soundboard_loop(guild_id))
            except Exception as e:
                await message.channel.send(f"Error joining voice channel: {e}")

    # Respond to mentions or keywords
    if any(word in message.content.lower() for word in ["magenta", "nicolas", "cage"]) or \
        bot.user in message.mentions or \
        (message.reference and message.reference.resolved and message.reference.resolved.author == bot.user):
        try:
            await message.channel.send(random.choice(messages), reference=message)
        except discord.errors.Forbidden:
            print(f"Missing permissions to send message in channel {message.channel.id}")
        except Exception as e:
            print(f"Error sending message to channel {message.channel.id}: {e}")

    # Leave voice if alone for 60 seconds
    if guild_id in voice_clients and voice_clients[guild_id]:
        vc = voice_clients[guild_id]
        if len(vc.channel.members) == 1:
            await asyncio.sleep(10)
            if len(vc.channel.members) == 1:
                await leave_voice_channel(guild_id)


# === Slash Commands ===
@bot.tree.command(
    name="set_channel",
    description="Set this channel for random messages, optionally specify interval in hours"
)
@app_commands.describe(interval="Number of hours between messages (default 1.0)")
async def set_channel(interaction: discord.Interaction, interval: float = 1.0):
    """Set a channel to receive random messages."""
    if not interaction.guild or not interaction.channel:
        await interaction.response.send_message("Use this command in a server channel.")
        return

    if interval <= 0:
        await interaction.response.send_message("❌ Interval must be greater than 0.")
        return

    guild_id = str(interaction.guild_id)
    channel_map[guild_id] = {
        "channel_id": interaction.channel.id,
        "interval": interval
    }
    save_channels()
    start_message_task(guild_id, interval)
    await interaction.response.send_message(
        f"✅ This channel is set for random messages every {interval} hour(s)."
    )


@bot.tree.command(name="remove_channel", description="Remove this channel from random messages")
async def remove_channel(interaction: discord.Interaction):
    """Remove a channel from the message loop."""
    if not interaction.guild:
        await interaction.response.send_message("Use this command in a server channel.")
        return

    guild_id = str(interaction.guild_id)
    if guild_id in channel_map:
        del channel_map[guild_id]
        save_channels()
        if guild_id in message_tasks:
            message_tasks[guild_id].cancel()
            del message_tasks[guild_id]
        await interaction.response.send_message("✅ This channel is no longer set for random messages.")
    else:
        await interaction.response.send_message("❌ This channel was not set for random messages.")


@bot.tree.command(name="random_message", description="Send a random message")
async def random_message(interaction: discord.Interaction):
    """Manually send a random message from the list."""
    await interaction.response.send_message(random.choice(messages))


# === Start Bot ===
keep_alive()
bot.run(TOKEN)
