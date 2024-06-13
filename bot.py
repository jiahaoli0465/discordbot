import discord
from discord.ext import commands, tasks
import openai
import yt_dlp as youtube_dl
import os
import asyncio
from googleapiclient.discovery import build
import nacl  
from collections import deque
# Intents are required for some functionalities
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True  # Ensure this is enabled to use voice channel features


# Create a bot instance
bot = commands.Bot(command_prefix='!', intents=intents)

# OpenAI API key
openai.api_key = "key"
client = openai.Client(api_key=openai.api_key)

# Use an Assistant
assistant_id = 'id'

# Global variable to keep track of the task
kyle_task = None

# YouTube API key
youtube_api_key = 'key'
youtube = build('youtube', 'v3', developerKey=youtube_api_key)

# Store search results and the queue
search_results = {}
queues = {}

async def new_thread():
    thread = client.beta.threads.create()
    return thread.id

@bot.event
async def on_ready():
    print(f'We have logged in as {bot.user}')

@bot.command()
async def hello(ctx):
    await ctx.send('Hello!')

kyle_id = 681648144517300300

@bot.command()
async def startkyle(ctx):
    global kyle_task
    if kyle_task is None:
        await ctx.send('Kyle reminder started!')
        kyle_task = ctx
        kyle_reminder.start(ctx)
    else:
        await ctx.send('Kyle reminder is already running!')

@bot.command()
async def stopkyle(ctx):
    global kyle_task
    if kyle_task is not None:
        await ctx.send('Kyle reminder stopped!')
        kyle_reminder.cancel()
        kyle_task = None
    else:
        await ctx.send('Kyle reminder is not running!')

@bot.command()
async def ask(ctx, *, question: str):
    if question.lower() == "does kyle get hoes":
        await ctx.send('Kyle get no hoes')
    else:
        await ctx.send('Let me think...')
        response = await get_openai_response(ctx.author.id, question)
        await ctx.send(response)

async def get_openai_response(user_id, question):
    # Assuming a session per user
    if not hasattr(bot, 'sessions'):
        bot.sessions = {}
    
    if user_id not in bot.sessions:
        bot.sessions[user_id] = await new_thread()

    thread_id = bot.sessions[user_id]

    # Add the user's message to the Thread
    client.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=question
    )

    # Run the Assistant to process the conversation
    run = client.beta.threads.runs.create(
        thread_id=thread_id,
        assistant_id=assistant_id
    )

    # Wait for the Run to complete
    while True:
        run_status = client.beta.threads.runs.retrieve(
            thread_id=thread_id,
            run_id=run.id
        )
        if run_status.status == 'completed':
            break
        await asyncio.sleep(1)

    # Retrieve the latest messages
    messages = client.beta.threads.messages.list(
        thread_id=thread_id
    )

    # Find the index of the latest user message
    latest_user_msg_index = next(
        (i for i, m in enumerate(reversed(messages.data)) if m.role == 'user'),
        None
    )

    # Assuming messages are in chronological order, find the first assistant message after the latest user message
    reply = None
    if latest_user_msg_index is not None:
        for message in messages.data[-latest_user_msg_index:]:
            if message.role == 'assistant':
                reply = message.content[0].text.value
                break

    if reply is None:
        reply = "No response."
    return reply

@tasks.loop(minutes=30)
async def kyle_reminder(ctx):
    await ctx.send(f'Reminder: <@{kyle_id}> dont get no bitch!')

# Music player commands
@bot.command()
async def join(ctx):
    if not ctx.author.voice:
        await ctx.send("You are not connected to a voice channel.")
        return
    channel = ctx.author.voice.channel
    await channel.connect()

@bot.command()
async def leave(ctx):
    if ctx.voice_client:
        await ctx.guild.voice_client.disconnect()
        await ctx.send("Disconnected from the voice channel.")
    else:
        await ctx.send("I'm not connected to a voice channel.")

@bot.command()
async def jp(ctx, *, search):
    if not ctx.voice_client:
        await ctx.send("I am not connected to a voice channel.")
        await join(ctx)
        
    
    # Perform YouTube search
    search_response = youtube.search().list(
        q=search,
        part='id,snippet',
        maxResults=5,
        type='video'
    ).execute()

    search_results[ctx.guild.id] = search_response['items']

    response = "Top 5 results:\n"
    for i, item in enumerate(search_response['items']):
        response += f"{i+1}. {item['snippet']['title']}\n"

    await ctx.send(response + "\nPlease choose a number from 1 to 5 to play the corresponding video.")

@bot.command()
async def choose(ctx, number: int):
    if not ctx.voice_client:
        await ctx.send("I am not connected to a voice channel.")
        return

    if ctx.guild.id not in search_results:
        await ctx.send("No search results found. Please use the !play command to search for a video first.")
        return

    if not (1 <= number <= 5):
        await ctx.send("Please choose a number between 1 and 5.")
        return

    video = search_results[ctx.guild.id][number - 1]
    url = f"https://www.youtube.com/watch?v={video['id']['videoId']}"
    await ctx.send("added to jiahao's queue")
    if ctx.guild.id not in queues:
        queues[ctx.guild.id] = deque()

    queues[ctx.guild.id].append((video['snippet']['title'], url))
    
    if not ctx.voice_client.is_playing():
        await play_next(ctx)

async def play_next(ctx):
    if ctx.guild.id not in queues or len(queues[ctx.guild.id]) == 0:
        return

    title, url = queues[ctx.guild.id].popleft()

    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'quiet': True
    }

    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        audio_url = next((f['url'] for f in info['formats'] if f['ext'] == 'm4a'), None)
        if not audio_url:
            await ctx.send("Could not extract audio from the video.")
            return

    ffmpeg_options = {
        'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
        'options': '-vn'
    }

    def after_playing(error):
        if error:
            print(f'Error occurred: {error}')
        future = asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop)
        try:
            future.result()
        except Exception as e:
            print(f'Error occurred while handling after_playing: {e}')

    player = discord.FFmpegOpusAudio(audio_url, **ffmpeg_options)
    ctx.voice_client.play(player, after=after_playing)
    await ctx.send(f'Now playing: {title}')

@bot.command()
async def pause(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.send("Paused the music.")
    else:
        await ctx.send("No music is playing.")

@bot.command()
async def resume(ctx):
    if ctx.voice_client and ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await ctx.send("Resumed the music.")
    else:
        await ctx.send("The music is not paused.")

@bot.command()
async def skip(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send("Skipped the current song.")
        await play_next(ctx)
    else:
        await ctx.send("No music is playing.")

@bot.command()
async def queue(ctx):
    if ctx.guild.id not in queues or len(queues[ctx.guild.id]) == 0:
        await ctx.send("The queue is empty.")
    else:
        response = "Queue:\n"
        for i, (title, url) in enumerate(queues[ctx.guild.id]):
            response += f"{i+1}. {title}\n"
        await ctx.send(response)
bot.run('discord key')
