import os
import json
import random
import asyncio
import discord
from discord.ext import commands
from discord import app_commands
from keep_alive import keep_alive
from dotenv import load_dotenv, dotenv_values

load_dotenv()

TOKEN = os.environ['DISCORD_TOKEN']
CHANNEL_FILE = "selected_channels.json"
SOUNDS_DIR = "sounds"  # Directory to store sound files

# Consider moving these to a separate file if they grow too large
messages = []
with open("messages.json", "r") as f:
    content = f.read()
    import re
    messages = re.findall(r'"([^"]*)"', content)

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True  # Enable voice state updates
bot = commands.Bot(command_prefix='!', intents=intents)

channel_map = {}  # guild_id: {"channel_id": channel_id, "interval": interval}
message_tasks = {}  # guild_id: asyncio.Task
voice_clients = {}  # guild_id: discord.VoiceClient


def load_channels():
    global channel_map
    try:
        with open(CHANNEL_FILE, "r") as f:
            channel_map = json.load(f)
    except FileNotFoundError:
        channel_map = {}  # Start with an empty dict if the file doesn't exist
        print(
            f"Channel file '{CHANNEL_FILE}' not found. Starting with empty channel map."
        )
    except json.JSONDecodeError:
        channel_map = {}  # Start with an empty dict if the json is invalid
        print(
            f"Channel file '{CHANNEL_FILE}' contains invalid JSON. Starting with empty channel map."
        )


def save_channels():
    with open(CHANNEL_FILE, "w") as f:
        json.dump(channel_map, f, indent=2)


async def send_message(guild_id):
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
        print(
            f"Missing permissions to send message in channel {data['channel_id']}"
        )
    except Exception as e:
        print(f"Error sending to {data['channel_id']}: {e}")


async def message_loop(guild_id, interval):
    await bot.wait_until_ready()
    while True:
        await asyncio.sleep(interval * 3600)
        await send_message(guild_id)


def start_message_task(guild_id, interval):
    # Cancel existing task if any
    if guild_id in message_tasks:
        message_tasks[guild_id].cancel()

    message_tasks[guild_id] = bot.loop.create_task(
        message_loop(guild_id, interval))


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
    """Loop to continuously play random sounds every 5 seconds."""
    while True:
        await asyncio.sleep(30)
        await play_random_sound(guild_id)


async def leave_voice_channel(guild_id):
    """Leaves the voice channel and cleans up."""
    if guild_id in voice_clients and voice_clients[guild_id]:
        vc = voice_clients[guild_id]
        await vc.disconnect()
        del voice_clients[guild_id]
        print(f"Left voice channel in guild {guild_id}")


@bot.event
async def on_ready():
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
    # Send a message to the first text channel in the server
    for channel in guild.text_channels:
        try:
            await channel.send(
                "hello,this magenta nicolas cage official brand account,verified"
            )
            break  # Only send to the first available channel
        except discord.errors.Forbidden:
            print(
                f"Missing permissions to send message in channel {channel.id} in guild {guild.id}"
            )
        except Exception as e:
            print(
                f"Error sending message to channel {channel.id} in guild {guild.id}: {e}"
            )


@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    guild_id = str(message.guild.id)  # Get guild ID

    # "Hop off" command
    if "leave" in message.content.lower(
    ) or "hop off" in message.content.lower() or (
            message.reference and message.reference.resolved
            and message.reference.resolved.author == bot.user) or str(
                bot.user.id) in message.content.lower(
                ) and "hop off" in message.content.lower():
        if guild_id in voice_clients and voice_clients[guild_id]:
            await leave_voice_channel(guild_id)
            return

    if "hop on" in message.content.lower() or "call" in message.content.lower(
    ):
        if message.author.voice and message.author.voice.channel:
            channel = message.author.voice.channel
            try:
                if guild_id in voice_clients and voice_clients[guild_id]:
                    await voice_clients[guild_id].move_to(channel)
                else:
                    vc = await channel.connect()
                    voice_clients[guild_id] = vc
                    bot.loop.create_task(
                        soundboard_loop(guild_id))  # Start the soundboard loop
            except Exception as e:
                await message.channel.send(f"Error joining voice channel: {e}")

    if "magenta" in message.content.lower(
    ) or "nicolas" in message.content.lower(
    ) or "cage" in message.content.lower() or str(
            bot.user.id) in message.content or (
                message.reference and message.reference.resolved
                and message.reference.resolved.author == bot.user):
        try:
            await message.channel.send(random.choice(messages),
                                       reference=message)
        except discord.errors.Forbidden:
            print(
                f"Missing permissions to send message in channel {message.channel.id}"
            )
        except Exception as e:
            print(
                f"Error sending message to channel {message.channel.id}: {e}")

    # Check if bot is in a voice channel and if it's the only one there
    if guild_id in voice_clients and voice_clients[guild_id]:
        vc = voice_clients[guild_id]
        if len(vc.channel.members) == 1:  # Only the bot is in the channel
            await asyncio.sleep(60)  #Wait 60 seconds to see if someone joins
            if len(vc.channel.members) == 1:
                await leave_voice_channel(guild_id)


@bot.tree.command(
    name="set_channel",
    description=
    "Set this channel for random messages, optionally specify interval in hours"
)
@app_commands.describe(
    interval="Number of hours between messages (default 1.0)")
async def set_channel(interaction: discord.Interaction, interval: float = 1.0):
    if not interaction.guild or not interaction.channel:
        await interaction.response.send_message(
            "Use this command in a server channel.")
        return

    if interval <= 0:
        await interaction.response.send_message(
            "❌ Interval must be greater than 0.")
        return

    guild_id = str(interaction.guild_id)
    channel_map[guild_id] = {
        "channel_id": interaction.channel.id,
        "interval": interval
    }
    save_channels()
    start_message_task(guild_id, interval)
    await interaction.response.send_message(
        f"✅ This channel is set for random messages every {interval} hour(s).")


@bot.tree.command(name="remove_channel",
                  description="Remove this channel from random messages")
async def remove_channel(interaction: discord.Interaction):
    if not interaction.guild:
        await interaction.response.send_message(
            "Use this command in a server channel.")
        return

    guild_id = str(interaction.guild_id)
    if guild_id in channel_map:
        del channel_map[guild_id]
        save_channels()
        if guild_id in message_tasks:
            message_tasks[guild_id].cancel()
            del message_tasks[guild_id]
        await interaction.response.send_message(
            "✅ This channel is no longer set for random messages.")
    else:
        await interaction.response.send_message(
            "❌ This channel was not set for random messages.")


@bot.tree.command(name="random_message", description="Send a random message")
async def random_message(interaction: discord.Interaction):
    await interaction.response.send_message(random.choice(messages))


keep_alive()
bot.run(TOKEN)
