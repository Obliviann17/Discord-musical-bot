import asyncio
import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import youtube_dl

load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents().all()
client = discord.Client(intents=intents)
bot = commands.Bot(command_prefix='-', intents=intents)

bot.voice_queues = {}  # Словарь для хранения очередей по голосовым каналам


youtube_dl.utils.bug_reports_message = lambda: ''

ytdl_format_options = {
    'format': 'bestaudio/best',
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
}

ffmpeg_options = {
    'options': '-vn -re',
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)


class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = ""

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
        if 'entries' in data:
            data = data['entries'][0]
        filename = data['title'] if stream else ytdl.prepare_filename(data)
        return filename


async def cleanup(ctx, filename):
    try:
        if os.path.exists(str(filename)):
            os.remove(str(filename))
    except PermissionError:
        print(f"Could not remove {filename} due to PermissionError.")


async def play_next(ctx):
    # Use bot.voice_clients to get active voice channels
    voice_channel = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    queue = bot.voice_queues.get(ctx.guild.id, [])

    if queue:
        next_url = queue.pop(0)
        filename = await YTDLSource.from_url(next_url, loop=bot.loop)
        audio_source = discord.FFmpegPCMAudio(executable='ffmpeg', source=filename)

        def after_playing(e):
            bot.loop.create_task(cleanup(ctx, filename))
            bot.loop.create_task(play_next(ctx))

        voice_channel.play(audio_source, after=after_playing)

        await ctx.send('**Now playing:** {}'.format(filename))

    else:
        bot.voice_queues.pop(ctx.guild.id, None)


@bot.command(name='play', help='To play song')
async def play(ctx, url):
    try:
        voice_channel = ctx.message.guild.voice_client

        if not voice_channel or not voice_channel.is_connected():
            voice_channel = await join(ctx)

        async with ctx.typing():
            filename = await YTDLSource.from_url(url, loop=bot.loop)
            queue = bot.voice_queues.get(ctx.guild.id, [])

            queue.append(url)
            bot.voice_queues[ctx.guild.id] = queue

            # If music is not playing, start playing
            if not voice_channel.is_playing() and not voice_channel.is_paused():
                await play_next(ctx)

            await ctx.send('**Added to queue:** {}'.format(filename))

    except:
        await ctx.send("The bot is not connected to a voice channel.")


@bot.command(name='join', help='Join a voice channel.')
async def join(ctx):
    if not ctx.message.author.voice:
        await ctx.send("{} is not connected to a voice channel".format(ctx.message.author.name))
        return None

    channel = ctx.message.author.voice.channel
    voice_channel = ctx.message.guild.voice_client

    if not voice_channel or not voice_channel.is_connected():
        voice_channel = await channel.connect()

    await ctx.send("Bot has joined the voice channel.")
    return voice_channel


@bot.command(name='leave', help='To make the bot leave the voice channel')
async def leave(ctx):
    voice_channel = ctx.message.guild.voice_client
    if voice_channel and voice_channel.is_connected():
        await voice_channel.disconnect()
        bot.voice_queues.pop(ctx.guild.id, None)
    else:
        await ctx.send("The bot is not connected to a voice channel.")


@bot.command(name='skip', help='Skips the current song and plays next in queue')
async def skip(ctx):
    voice_channel = ctx.message.guild.voice_client
    if voice_channel and voice_channel.is_playing():
        voice_channel.stop()
        await ctx.send("Skipped the current song.")
    await play_next(ctx)


@bot.event
async def on_ready():
    print('Running!')
    for guild in bot.guilds:
        for channel in guild.text_channels:
            if str(channel) == "general":
                await channel.send('Bot Activated..')
        print('Active in {}\n Member Count : {}'.format(guild.name, guild.member_count))


if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
