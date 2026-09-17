import logging
import asyncio
import os
import time
import json
import random
import urllib.parse
import yt_dlp
from concurrent.futures import ThreadPoolExecutor
from pyrogram import Client, filters, idle
from pyrogram.types import (InlineKeyboardMarkup, InlineKeyboardButton, BotCommand, 
                            InlineQueryResultArticle, InputTextMessageContent, InlineQueryResultCachedPhoto)
from pyrogram.enums import ChatMembersFilter
from pytgcalls import PyTgCalls
from pytgcalls import filters as ptc_filters
from pytgcalls.types import MediaStream, Update
from motor.motor_asyncio import AsyncIOMotorClient

# ==========================================
# ⚙️ CONFIG & MONGODB SETUP
# ==========================================
from config import API_ID, API_HASH, BOT_TOKEN, SESSION_STRING, OWNER_ID
try: from config import MONGO_URL
except ImportError: MONGO_URL = ""

logging.basicConfig(level=logging.INFO)
try: OWNER_ID = int(OWNER_ID)
except Exception: OWNER_ID = 0

if MONGO_URL:
    mongo_client = AsyncIOMotorClient(MONGO_URL)
    db = mongo_client["MusicBotDB"]
    playlist_col = db["user_playlists"]
    uno_stats_col = db["uno_stats"]  
    uno_cards_col = db["uno_cards"] 
    print("✅ MongoDB Connected Successfully!")
else: 
    print("⚠️ MONGO_URL not found! Cloud features won't work.")

# ==========================================
# 🤖 BOT CLIENTS & GLOBALS
# ==========================================
app = Client("MusicBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
assistant = Client("Assistant", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING)
call_py = PyTgCalls(assistant)

thread_pool = ThreadPoolExecutor(max_workers=5) 
chat_queue, is_playing, current_playing, admin_cache = {}, {}, {}, {}
uno_games = {} 
cards_cache = {} 
DEFAULT_THUMB = "https://telegra.ph/file/b9e289456ceb4249a5b06.png" 
BOT_USERNAME, ASSISTANT_ID = "", 0  

# --- DB FUNCTIONS ---
async def add_to_db(user_id, song_dict):
    user_data = await playlist_col.find_one({"user_id": user_id})
    if user_data: await playlist_col.update_one({"user_id": user_id}, {"$push": {"songs": song_dict}})
    else: await playlist_col.insert_one({"user_id": user_id, "songs": [song_dict]})

async def get_db_playlist(user_id):
    user_data = await playlist_col.find_one({"user_id": user_id})
    return user_data["songs"] if user_data else []

async def remove_from_db(user_id, index):
    user_data = await playlist_col.find_one({"user_id": user_id})
    if user_data and "songs" in user_data and 0 <= index < len(user_data["songs"]):
        user_data["songs"].pop(index)
        await playlist_col.update_one({"user_id": user_id}, {"$set": {"songs": user_data["songs"]}})
        return True
    return False

async def clear_db_playlist(user_id):
    await playlist_col.delete_one({"user_id": user_id})

async def add_win(user_id, name):
    if not MONGO_URL: return
    stats = await uno_stats_col.find_one({"user_id": user_id})
    if stats:
        await uno_stats_col.update_one({"user_id": user_id}, {"$inc": {"wins": 1}, "$set": {"name": name}})
    else:
        await uno_stats_col.insert_one({"user_id": user_id, "name": name, "wins": 1})

async def load_cards_to_cache():
    if not MONGO_URL: return
    async for card in uno_cards_col.find():
        cards_cache[card["card_name"]] = card["file_id"]
    print(f"✅ Loaded {len(cards_cache)} UNO Cards from MongoDB to Cache!")

def add_chat(chat_id):
    try:
        if not os.path.exists("chats.txt"): open("chats.txt", "w").close()
        with open("chats.txt", "r") as f: chats = f.read().splitlines()
        if str(chat_id) not in chats:
            with open("chats.txt", "a") as f: f.write(str(chat_id) + "\n")
    except: pass

def get_chats():
    try:
        with open("chats.txt", "r") as f: return f.read().splitlines()
    except: return []

START_CONFIG_FILE = "start_config.json"

def load_start_config():
    if os.path.exists(START_CONFIG_FILE):
        try:
            with open(START_CONFIG_FILE, "r") as f: return json.load(f)
        except: return None
    return None

def save_start_config(data):
    with open(START_CONFIG_FILE, "w") as f: json.dump(data, f, indent=4)

def to_small_caps(text):
    normal = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    small_caps = "ᴀʙᴄᴅᴇꜰɢʜɪᴊᴋʟᴍɴᴏᴘǫʀꜱᴛᴜᴠᴡxʏᴢᴀʙᴄᴅᴇꜰɢʜɪᴊᴋʟᴍɴᴏᴘǫʀꜱᴛᴜᴠᴡxʏᴢ"
    return str(text).translate(str.maketrans(normal, small_caps))

def format_broadcast_text(text):
    if not text: return text
    final_lines = []
    for line in text.split('\n'):
        final_words = []
        for word in line.split(' '):
            if word.startswith(('http://', 'https://', 't.me/', 'www.', '@')): final_words.append(word)
            else: final_words.append(to_small_caps(word))
        final_lines.append(" ".join(final_words))
    return "\n".join(final_lines)

async def reload_admins(chat_id):
    admin_cache[chat_id] = []
    async for member in app.get_chat_members(chat_id, filter=ChatMembersFilter.ADMINISTRATORS):
        admin_cache[chat_id].append(member.user.id)
    return len(admin_cache[chat_id])

async def delayed_delete(message, delay=5):
    await asyncio.sleep(delay)
    try: await message.delete()
    except: pass


# ==========================================
# 🖼️ UNO CARDS IMAGE AUTO-UPLOADER
# ==========================================
def card_to_filename(card):
    if "Wild +4" in card: return "Wild_Card_Draw_4"
    if "Wild" in card: return "Wild_Card_Change_Colour"
    parts = card.split(" ")
    color = parts[1] 
    v = " ".join(parts[2:])
    if "Skip" in v: return f"{color}_Skip"
    if "Reverse" in v: return f"{color}_Reverse"
    if "➕2" in v or "+2" in v: return f"{color}_Draw_2"
    return f"{color}_{parts[2]}"

@app.on_message(filters.command("uploadcards") & filters.user(OWNER_ID))
async def upload_cards_cmd(client, message):
    if not MONGO_URL: return await message.reply("⚠️ MongoDB connected nahi hai!")
    folder = "uno_images"
    if not os.path.exists(folder):
        return await message.reply(f"⚠️ `{folder}` naam ka folder nahi mila! Usko bana kar images usme daal do.")
    
    m = await message.reply("⏳ **Cards ko MongoDB me secure kar raha hu... Kripya 1-2 minute rukiye.**")
    uploaded = 0
    
    for root_dir, sub_dirs, files in os.walk(folder):
        for file in files:
            name_without_ext = os.path.splitext(file)[0]
            if name_without_ext not in cards_cache and file.lower().endswith((".png", ".jpg", ".jpeg")):
                file_path = os.path.join(root_dir, file)
                try:
                    msg = await client.send_photo(message.chat.id, file_path)
                    file_id = msg.photo.file_id
                    
                    cards_cache[name_without_ext] = file_id
                    await uno_cards_col.update_one(
                        {"card_name": name_without_ext}, 
                        {"$set": {"file_id": file_id}}, 
                        upsert=True
                    )
                    
                    uploaded += 1
                    await asyncio.sleep(1.5) 
                except Exception as e:
                    print(f"Error uploading {file_path}: {e}")
                    
    await m.edit(f"✅ **Upload Complete!**\nNaye images Cloud me add hue: `{uploaded}`\nTotal Database Cards: `{len(cards_cache)}`")


# ==========================================
# 🏆 UNO LEADERBOARD COMMANDS
# ==========================================
@app.on_message(filters.command("topplayers"))
async def top_players_cmd(client, message):
    if not MONGO_URL: return await message.reply("⚠️ Database is not connected!")
    
    m = await message.reply("🏆 Fetching Leaderboard...")
    top_players = await uno_stats_col.find().sort("wins", -1).limit(10).to_list(10)
    
    if not top_players:
        return await m.edit("😔 Abhi tak kisi ne UNO game nahi jeeta hai!")
        
    text = "🔥 **UNO GLOBAL LEADERBOARD** 🔥\n\n"
    
    for i, p in enumerate(top_players, start=1):
        name = p.get("name", "Unknown Player")
        wins = p.get("wins", 0)
        user_id = p.get("user_id")
        
        if i <= 3:
            text += f"{i}. 🌟 **[Ultra Pro Player - {name}](tg://user?id={user_id})** ➣ `{wins}` Wins 👑\n"
        elif i <= 6:
            text += f"{i}. 🎖 **[Pro Player - {name}](tg://user?id={user_id})** ➣ `{wins}` Wins\n"
        else:
            text += f"{i}. 🔰 **[Beginner Pro - {name}](tg://user?id={user_id})** ➣ `{wins}` Wins\n"
            
    await m.edit(text)

@app.on_message(filters.command("setposition") & filters.user(OWNER_ID))
async def set_position_cmd(client, message):
    if not MONGO_URL: return await message.reply("⚠️ Database connected nahi hai!")
    
    args = message.command
    if len(args) != 3:
        return await message.reply("⚠️ Sahi format use kar: `/setposition <user_id> <wins>`")
        
    try:
        user_id = int(args[1])
        wins = int(args[2])
        
        try:
            user = await app.get_users(user_id)
            name = user.first_name
        except:
            name = "Hidden Player"
            
        await uno_stats_col.update_one(
            {"user_id": user_id},
            {"$set": {"wins": wins, "name": name}},
            upsert=True
        )
        await message.reply(f"✅ Position Update Hogyi!\n👤 **Player:** {name}\n🏆 **Wins Set To:** `{wins}`")
        
    except ValueError:
        await message.reply("⚠️ User ID aur Wins numbers me hone chahiye!")


# ==========================================
# 🎵 MUSIC ENGINE UTILS
# ==========================================
async def get_fresh_url(song_dict):
    url = song_dict.get("url", "")
    if "googlevideo.com" in url:
        try:
            parsed = urllib.parse.urlparse(url)
            qs = urllib.parse.parse_qs(parsed.query)
            if 'expire' in qs:
                expire_time = int(qs['expire'][0])
                if time.time() > (expire_time - 600): 
                    loop = asyncio.get_event_loop()
                    fresh_data = await loop.run_in_executor(thread_pool, get_yt_info, song_dict["title"], song_dict.get("is_video", False))
                    return fresh_data["url"]
        except: pass
    return url

def get_yt_info(query, is_video=False):
    fmt = 'best[height=720][ext=mp4]/best[height<=720][ext=mp4]/best' if is_video else 'bestaudio/best'
    ydl_opts = {'format': fmt, 'noplaylist': True, 'quiet': True, 'no_warnings': True, 'ignoreerrors': True, 'simulate': True, 'extractor_args': {'youtube': {'player_client': ['android', 'web']}}}
    search_query = query if "youtube.com" in query or "youtu.be" in query else f"ytsearch:{query}"
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(search_query, download=False)
        if 'entries' in info: info = info['entries'][0]
        duration_sec = int(info.get('duration', 0) or 0)
        m, s = divmod(duration_sec, 60)
        h, m = divmod(m, 60)
        duration_str = f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
        return {"title": info.get('title', 'Unknown Title'), "url": info.get('url'), "thumbnail": f"https://img.youtube.com/vi/{info.get('id')}/hqdefault.jpg" if info.get('id') else DEFAULT_THUMB, "duration": duration_str, "duration_sec": duration_sec, "is_video": is_video}

def get_music_panel(title, duration_str, requester, is_queue=False, pos=0, played_sec=0, total_sec=0):
    title_caps = to_small_caps(title)
    caption = f"> ➲ {'ᴀᴅᴅᴇᴅ ᴛᴏ ǫᴜᴇᴜᴇ ᴀᴛ #' + str(pos) if is_queue else 'ꜱᴛᴀʀᴛᴇᴅ ꜱᴛʀᴇᴀᴍɪɴɢ'} | ❞\n>\n> ▶ ᴛɪᴛʟᴇ : [{title_caps}](https://t.me/{BOT_USERNAME})\n> ▶ ᴅᴜʀᴀᴛɪᴏɴ : {duration_str} ᴍɪɴᴜᴛᴇꜱ\n> ▶ ʀᴇǫᴜᴇꜱᴛᴇᴅ ʙʏ : {requester}"
    
    bar, played_str = "◉───────────", "00:00"
    if total_sec > 0:
        percentage = max(0.0, min(1.0, played_sec / total_sec))
        filled_len = int(percentage * 12)
        bar = "─" * filled_len + "◉" + "─" * (11 - filled_len)
        p_m, p_s = divmod(int(played_sec), 60); p_h, p_m = divmod(p_m, 60)
        played_str = f"{p_h:02d}:{p_m:02d}:{p_s:02d}" if p_h else f"{p_m:02d}:{p_s:02d}"

    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{played_str} | {bar} | {duration_str}", callback_data="progress_bar")],
        [InlineKeyboardButton("▷", callback_data="resume_cb"), InlineKeyboardButton("II", callback_data="pause_cb"), InlineKeyboardButton("↻", callback_data="replay_cb"), InlineKeyboardButton("⏭", callback_data="skip_cb"), InlineKeyboardButton("▢", callback_data="stop_cb")],
        [InlineKeyboardButton("🔄 Refresh", callback_data="refresh_cb"), InlineKeyboardButton("⚡ Reload", callback_data="reload_cb")],
        [InlineKeyboardButton("❌ Close", callback_data="close_msg")]
    ])
    return caption, buttons

# ==========================================
# 🃏 UNO ENGINE (MAU MAU STYLE)
# ==========================================
def get_uno_deck():
    colors = ["🔴 Red", "🔵 Blue", "🟢 Green", "🟡 Yellow"]
    values = ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "⏭ Skip", "🔄 Reverse", "➕2"]
    wilds = ["🌈 Wild", "💥 Wild +4"]
    deck = []
    for c in colors:
        for v in values:
            deck.append(f"{c} {v}")
            if v != "0": deck.append(f"{c} {v}")
    for w in wilds:
        for _ in range(4): deck.append(w)
    random.shuffle(deck)
    return deck

def is_playable(card, top_card, current_color):
    if "Wild" in card: return True
    card_color = card.split(" ")[1] if card.startswith(("🔴", "🔵", "🟢", "🟡")) else None
    card_val = " ".join(card.split(" ")[2:]) if card_color else None
    top_val = " ".join(top_card.split(" ")[2:]) if top_card.startswith(("🔴", "🔵", "🟢", "🟡")) else top_card
    if card_color == current_color: return True
    if card_val and top_val and card_val == top_val: return True
    return False

def get_next_turn(game):
    game["turn_index"] = (game["turn_index"] + game["direction"]) % len(game["players"])
    return game["turn_index"]

async def send_uno_table(chat_id):
    game = uno_games.get(chat_id)
    if not game: return
    current_player = game["players"][game["turn_index"]]
    players_text = "\n".join([f"{'👉' if p['id'] == current_player['id'] else '👤'} {p['name']} - {len(p['cards'])} cards" for p in game["players"]])
    
    text = (f"🃏 **UNO TABLE**\n\n"
            f"🎨 **Current Color:** {game['current_color']}\n"
            f"🎯 **Top Card:** {game['top_card']}\n\n"
            f"👥 **Players:**\n{players_text}\n")
            
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🃏 Play Card", switch_inline_query_current_chat="")],
        [InlineKeyboardButton("👀 Show Cards", callback_data="show_uno_cards"), InlineKeyboardButton("📥 Draw", callback_data="uno_draw")]
    ])
    
    if "table_msg" in game:
        try: await game["table_msg"].delete()
        except: pass

    file_key = card_to_filename(game["top_card"])
    file_id = cards_cache.get(file_key)

    if file_id:
        game["table_msg"] = await app.send_photo(chat_id, photo=file_id, caption=text, reply_markup=kb)
    else:
        game["table_msg"] = await app.send_message(chat_id, text, reply_markup=kb)
    
    ping = await app.send_message(chat_id, f"🎯 **Teri baari hai:** [{current_player['name']}](tg://user?id={current_player['id']})")
    asyncio.create_task(delayed_delete(ping, 7))

@app.on_message(filters.command("startgame") & filters.group)
async def start_uno_game(client, message):
    chat_id = message.chat.id
    if chat_id in uno_games and uno_games[chat_id]['status'] != 'finished':
        return await message.reply("⚠️ Ek game pehle se active hai ya lobby open hai!")
    player = {"id": message.from_user.id, "name": message.from_user.first_name, "cards": []}
    uno_games[chat_id] = {"status": "lobby", "players": [player], "lobby_msg": None}
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🎮 Join Game", callback_data="join_uno")]])
    m = await message.reply(f"🃏 **UNO GAME LOBBY STARTED!**\n\n👑 **Host:** {player['name']}\n⏳ **Time left:** 30 seconds\n\n👥 **Players Joined (1):**\n- {player['name']}", reply_markup=kb)
    uno_games[chat_id]["lobby_msg"] = m
    asyncio.create_task(uno_lobby_timer(chat_id))

@app.on_callback_query(filters.regex("^join_uno$"))
async def join_uno_cb(client, callback_query):
    chat_id = callback_query.message.chat.id
    user = callback_query.from_user
    if chat_id not in uno_games or uno_games[chat_id]["status"] != "lobby":
        return await callback_query.answer("⚠️ Lobby band ho chuki hai!", show_alert=True)
    players = uno_games[chat_id]["players"]
    if any(p["id"] == user.id for p in players): return await callback_query.answer("Tu pehle se game me hai!", show_alert=True)
    players.append({"id": user.id, "name": user.first_name, "cards": []})
    await callback_query.answer("✅ Game joined!", show_alert=False)
    players_text = "\n".join([f"- {p['name']}" for p in players])
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(f"🎮 Join Game ({len(players)})", callback_data="join_uno")]])
    try: await callback_query.message.edit_text(f"🃏 **UNO GAME LOBBY STARTED!**\n\n⏳ **Time left:** Less than 30s\n\n👥 **Players Joined ({len(players)}):**\n{players_text}", reply_markup=kb)
    except: pass

async def uno_lobby_timer(chat_id):
    await asyncio.sleep(10)
    if chat_id in uno_games and uno_games[chat_id]["status"] == "lobby":
        rem = await app.send_message(chat_id, "⏳ **20 seconds left!** Join fast!")
    await asyncio.sleep(20)
    if chat_id in uno_games and uno_games[chat_id]["status"] == "lobby":
        game = uno_games[chat_id]
        try: await rem.delete()
        except: pass
        if len(game["players"]) < 2:
            uno_games.pop(chat_id, None)
            return await app.send_message(chat_id, "⚠️ Kam se kam 2 players chahiye. **Game Cancelled!**")
        
        game["status"] = "playing"
        deck = get_uno_deck()
        for p in game["players"]: p["cards"] = [deck.pop() for _ in range(7)]
        top_card = deck.pop()
        while "Wild" in top_card or "Reverse" in top_card or "Skip" in top_card or "➕2" in top_card:
            deck.append(top_card)
            random.shuffle(deck)
            top_card = deck.pop()
        
        game["deck"] = deck
        game["top_card"] = top_card
        game["current_color"] = top_card.split(" ")[1]
        game["turn_index"] = 0
        game["direction"] = 1
        await send_uno_table(chat_id)

@app.on_callback_query(filters.regex("^show_uno_cards$"))
async def show_uno_cards_cb(client, cb):
    chat_id = cb.message.chat.id
    if chat_id not in uno_games or uno_games[chat_id]["status"] != "playing":
        return await cb.answer("Game active nahi hai!", show_alert=True)
    player = next((p for p in uno_games[chat_id]["players"] if p["id"] == cb.from_user.id), None)
    if not player: 
        return await cb.answer("Tu is game me nahi khel raha bhai!", show_alert=True)
    cards_text = "\n".join(player["cards"])
    await cb.answer(f"🃏 TERE CARDS:\n\n{cards_text}", show_alert=True)

@app.on_inline_query()
async def inline_uno_cards(client, query):
    user_id = query.from_user.id
    results = []
    
    active_chat, player_data = None, None
    for chat_id, game in uno_games.items():
        if game["status"] == "playing":
            for p in game["players"]:
                if p["id"] == user_id:
                    active_chat, player_data = chat_id, p
                    break
        if active_chat: break

    if not active_chat:
        results.append(InlineQueryResultArticle(
            id="not_in_game",
            title="Not playing UNO!", 
            input_message_content=InputTextMessageContent("I tried to play but I'm not in a game!")
        ))
        return await query.answer(results, cache_time=0, is_personal=True)

    game = uno_games[active_chat]
    is_my_turn = game["players"][game["turn_index"]]["id"] == user_id
    
    for i, card in enumerate(player_data["cards"]):
        playable = is_playable(card, game["top_card"], game["current_color"])
        title = f"{'✅ Play' if playable and is_my_turn else '❌ Cannot play'} {card}"
        payload = f"🃏 [UNO] Played: {card}\n\nChatID: {active_chat}\nCardIndex: {i}"
        if not playable or not is_my_turn: payload = f"I tried to cheat and play {card}! 🤡"
        
        file_key = card_to_filename(card)
        file_id = cards_cache.get(file_key) 
        
        if file_id:
            results.append(InlineQueryResultCachedPhoto(
                photo_file_id=file_id,
                id=f"card_{i}_{time.time()}",
                title=title,
                description="Tap to play this card!" if playable and is_my_turn else "Invalid move",
                input_message_content=InputTextMessageContent(payload)
            ))
        else:
            results.append(InlineQueryResultArticle(
                id=f"card_{i}_{time.time()}",
                title=title, 
                description="Tap to play!" if playable and is_my_turn else "Not your turn or invalid card.", 
                input_message_content=InputTextMessageContent(payload)
            ))
            
    await query.answer(results, cache_time=0, is_personal=True)

@app.on_message(filters.regex(r"I tried to cheat and play (.*)! 🤡"))
async def catch_cheat(client, message):
    try: await message.delete()
    except: pass
    m = await message.reply(f"🚫 [{message.from_user.first_name}](tg://user?id={message.from_user.id}), wo card valid nahi hai ya teri baari nahi hai!")
    asyncio.create_task(delayed_delete(m, 4))

@app.on_message(filters.regex(r"🃏 \[UNO\] Played: (.*)\n\nChatID: (-\d+)\nCardIndex: (\d+)"))
async def catch_uno_play(client, message):
    try: await message.delete()
    except: pass
    match = message.matches[0]
    card, chat_id, card_index = match.group(1), int(match.group(2)), int(match.group(3))
    user_id = message.from_user.id

    if chat_id not in uno_games or uno_games[chat_id]["status"] != "playing": return
    game = uno_games[chat_id]
    
    if game["players"][game["turn_index"]]["id"] != user_id:
        m = await app.send_message(chat_id, f"⚠️ Teri baari nahi hai [{message.from_user.first_name}](tg://user?id={message.from_user.id})!")
        return asyncio.create_task(delayed_delete(m, 4))

    player = game["players"][game["turn_index"]]
    if card_index >= len(player["cards"]) or player["cards"][card_index] != card: return

    player["cards"].pop(card_index)
    game["top_card"] = card

    if "Wild" in card:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔴 Red", callback_data="unocolor_🔴 Red"), InlineKeyboardButton("🔵 Blue", callback_data="unocolor_🔵 Blue")],
            [InlineKeyboardButton("🟢 Green", callback_data="unocolor_🟢 Green"), InlineKeyboardButton("🟡 Yellow", callback_data="unocolor_🟡 Yellow")]
        ])
        game["status"] = "waiting_color"
        game["pending_effect"] = "+4" if "+4" in card else "none"
        if "table_msg" in game:
            try: await game["table_msg"].delete()
            except: pass
        game["table_msg"] = await app.send_message(chat_id, f"🌈 **WILD CARD PLAYED by {player['name']}!**\nChoose a new color:", reply_markup=kb)
        return

    game["current_color"] = card.split(" ")[1] if card.startswith(("🔴", "🔵", "🟢", "🟡")) else game["current_color"]
    if "Reverse" in card:
        game["direction"] *= -1
        if len(game["players"]) == 2: get_next_turn(game)
    elif "Skip" in card: get_next_turn(game)
    elif "➕2" in card:
        victim = game["players"][(game["turn_index"] + game["direction"]) % len(game["players"])]
        for _ in range(2):
            if not game["deck"]: game["deck"] = get_uno_deck()
            victim["cards"].append(game["deck"].pop())
        get_next_turn(game)

    if len(player["cards"]) == 0:
        winner_name = player['name']
        winner_id = player['id']
        uno_games.pop(chat_id, None)
        await add_win(winner_id, winner_name) 
        return await app.send_message(chat_id, f"🎉 **[{winner_name}](tg://user?id={winner_id}) HAS WON UNO!** 🏆")

    get_next_turn(game)
    await send_uno_table(chat_id)

@app.on_callback_query(filters.regex(r"^unocolor_(.*)$"))
async def choose_color_cb(client, cb):
    chat_id = cb.message.chat.id
    if chat_id not in uno_games or uno_games[chat_id]["status"] != "waiting_color": return
    game = uno_games[chat_id]
    if game["players"][game["turn_index"]]["id"] != cb.from_user.id:
        return await cb.answer("Wait!", show_alert=True)
        
    game["current_color"] = cb.data.split("_")[1].split(" ")[1]
    if game["pending_effect"] == "+4":
        victim = game["players"][(game["turn_index"] + game["direction"]) % len(game["players"])]
        for _ in range(4):
            if not game["deck"]: game["deck"] = get_uno_deck()
            victim["cards"].append(game["deck"].pop())
        get_next_turn(game)

    game["status"] = "playing"
    game["pending_effect"] = "none"
    
    if len(game["players"][game["turn_index"]]["cards"]) == 0:
        winner = game["players"][game["turn_index"]]["name"]
        winner_id = game["players"][game["turn_index"]]["id"]
        uno_games.pop(chat_id, None)
        await add_win(winner_id, winner) 
        return await app.send_message(chat_id, f"🎉 **[{winner}](tg://user?id={winner_id}) HAS WON UNO!** 🏆")
        
    get_next_turn(game)
    await cb.message.delete()
    await send_uno_table(chat_id)

@app.on_callback_query(filters.regex("^uno_draw$"))
async def uno_draw_cb(client, cb):
    chat_id = cb.message.chat.id
    if chat_id not in uno_games or uno_games[chat_id]["status"] != "playing": return
    game = uno_games[chat_id]
    if game["players"][game["turn_index"]]["id"] != cb.from_user.id:
        return await cb.answer("Wait for your turn!", show_alert=True)
        
    if not game["deck"]: game["deck"] = get_uno_deck()
    drawn = game["deck"].pop()
    game["players"][game["turn_index"]]["cards"].append(drawn)
    await cb.answer(f"📥 You drew a card!", show_alert=True)
    get_next_turn(game)
    await send_uno_table(chat_id)


# ==========================================
# ☁️ CLOUD PLAYLIST COMMANDS 
# ==========================================
@app.on_message(filters.command("save"))
async def save_song(client, message):
    if not MONGO_URL: return await message.reply("⚠️ Cloud database connected nahi hai!")
    if len(message.command) < 2: return await message.reply("⚠️ Kisko save karu bhai? Aise likh: `/save Faded`")
    query = " ".join(message.command[1:])
    m = await message.reply("🔍 Searching to save in your playlist...")
    loop = asyncio.get_event_loop()
    try:
        yt_data = await loop.run_in_executor(thread_pool, get_yt_info, query, False)
        song_dict = {"title": yt_data["title"], "url": yt_data["url"], "thumbnail": yt_data["thumbnail"], "duration": yt_data["duration"], "duration_sec": yt_data["duration_sec"], "is_video": False}
        await add_to_db(message.from_user.id, song_dict)
        await m.edit(f"✅ **{yt_data['title']}** teri Cloud Playlist me save ho gaya!\n\nCheck karne ke liye `/mypl` daba.")
    except Exception as e: await m.edit(f"❌ Error: `{e}`")

@app.on_message(filters.command("mypl"))
async def show_playlist(client, message):
    if not MONGO_URL: return await message.reply("⚠️ Cloud database connected nahi hai!")
    songs = await get_db_playlist(message.from_user.id)
    if not songs: return await message.reply("📂 Teri playlist abhi khali hai. Pehle `/save <song>` se gaane add kar!")
    text = f"☁️ **{message.from_user.first_name}'s Cloud Playlist**\n\n"
    for i, s in enumerate(songs): text += f"**{i+1}.** {s['title']} (`{s['duration']}`)\n"
    text += "\n💡 *Playlist play karne ke liye `/play mypl` type kar!*"
    kb = [[InlineKeyboardButton("🗑️ Manage/Delete Songs", callback_data="manage_pl")]]
    await message.reply(text, reply_markup=InlineKeyboardMarkup(kb))

@app.on_callback_query(filters.regex("^(manage_pl|back_pl|clear_pl)$") | filters.regex(r"^delpl_(\d+)$"))
async def playlist_callbacks(client, callback_query):
    data = callback_query.data
    user_id = callback_query.from_user.id
    if data in ["manage_pl", "back_pl"]:
        songs = await get_db_playlist(user_id)
        if not songs: return await callback_query.answer("Playlist is empty!", show_alert=True)
        kb = [[InlineKeyboardButton(f"❌ Delete: {s['title'][:20]}...", callback_data=f"delpl_{i}")] for i, s in enumerate(songs)]
        kb.append([InlineKeyboardButton("🔙 Close", callback_data="close_msg"), InlineKeyboardButton("🗑️ Clear All", callback_data="clear_pl")])
        await callback_query.message.edit("🗑️ **Select a song to delete from your playlist:**", reply_markup=InlineKeyboardMarkup(kb))
    elif data == "clear_pl":
        await clear_db_playlist(user_id)
        await callback_query.message.edit("✅ Teri puri playlist delete kar di gayi hai!")
    elif data.startswith("delpl_"):
        await remove_from_db(user_id, int(data.split("_")[1]))
        await callback_query.answer("✅ Song deleted from playlist!", show_alert=False)
        callback_query.data = "manage_pl"; await playlist_callbacks(client, callback_query)


# ==========================================
# 👑 OWNER COMMANDS & UTILS
# ==========================================
@app.on_message(filters.command("setstart") & filters.user(OWNER_ID))
async def set_start_cmd(client, message):
    replied = message.reply_to_message
    if not replied or not replied.photo:
        return await message.reply("⚠️ **Galat Format!**\nEk Photo bhejo jisme caption likha ho (buttons bhi laga sakte ho), aur us message ko reply karke `/setstart` likho.")
    
    file_id = replied.photo.file_id
    text = replied.caption.markdown if replied.caption else "Hello {mention}! Bot is ready. 🤖"
    
    raw_btns = []
    if replied.reply_markup and replied.reply_markup.inline_keyboard:
        for row in replied.reply_markup.inline_keyboard:
            for btn in row:
                if btn.url:
                    raw_btns.append({"name": btn.text, "url": btn.url})
                    
    config_data = {
        "text": text,
        "photo": file_id,
        "buttons": raw_btns
    }
    
    save_start_config(config_data)
    await message.reply("✅ **Naya Start Message Set Ho Gaya Hai!**\n\nAb koi bhi `/start` dabayega toh yahi mast photo aur text aayega.")

@app.on_message(filters.command("id"))
async def get_id(client, message):
    await message.reply(f"👤 **Your User ID is:** `{message.from_user.id}`\n🛠 **System Owner ID:** `{OWNER_ID}`")

@app.on_message(filters.command("users") & filters.user(OWNER_ID))
async def users_cmd(client, message):
    await message.reply(f"📊 **Bot Statistics:**\n\n👤 Total Users & Groups: `{len(get_chats())}`")

@app.on_message(filters.command("gcast") & filters.user(OWNER_ID))
async def gcast_cmd(client, message):
    replied = message.reply_to_message
    if not replied: return await message.reply("⚠️ Reply to a message!")
    chats = get_chats()
    if not chats: return await message.reply("❌ Database is empty!")
    m = await message.reply(f"🚀 **Broadcasting to {len(chats)} chats...**")
    success, failed = 0, 0
    formatted_text = format_broadcast_text(replied.text) if replied.text else None
    formatted_caption = format_broadcast_text(replied.caption) if replied.caption else None
    for chat in chats:
        try:
            if replied.text: await client.send_message(int(chat), formatted_text)
            else: await replied.copy(int(chat), caption=formatted_caption if formatted_caption else "")
            success += 1; await asyncio.sleep(0.2)
        except: failed += 1
    await m.edit(f"✅ **Broadcast Completed!**\n\n🎯 Success: `{success}`\n❌ Failed: `{failed}`")


# ==========================================
# 🎵 MUSIC PLAYBACK LOGIC & COMMANDS
# ==========================================
async def progress_updater():
    while True:
        await asyncio.sleep(10)
        for chat_id, data in list(current_playing.items()):
            if not data['is_paused'] and is_playing.get(chat_id):
                played_sec = time.time() - data['start_time']
                if played_sec > data['song']['duration_sec']: continue
                _, buttons = get_music_panel(data['song']['title'], data['song']['duration'], data['song']['requester'], played_sec=played_sec, total_sec=data['song']['duration_sec'])
                try: await data['panel_msg'].edit_reply_markup(reply_markup=buttons)
                except: pass

async def process_play(client, message, is_video=False, force_play=False):
    add_chat(message.chat.id)
    try: await message.delete()
    except: pass
    chat_id = message.chat.id
    
    try:
        chat_member = await app.get_chat_member(chat_id, ASSISTANT_ID)
        if str(chat_member.status) in ["ChatMemberStatus.BANNED", "ChatMemberStatus.KICKED"]:
            m = await message.reply("⚠️ **Assistant is BANNED!** Unban it first.")
            return asyncio.create_task(delayed_delete(m))
    except Exception:
        try:
            join_msg = await message.reply("⏳ **Assistant is joining...**")
            if message.chat.username: await assistant.join_chat(message.chat.username)
            else: await assistant.join_chat(await app.export_chat_invite_link(chat_id))
            await join_msg.edit("✅ **Assistant joined!**")
            await asyncio.sleep(2); await join_msg.delete()
        except Exception as e:
            m = await message.reply(f"❌ **Make Bot Admin to add Assistant!**\n`{e}`")
            return asyncio.create_task(delayed_delete(m, 10))

    replied = message.reply_to_message
    is_tg_media = bool(replied and (replied.audio or replied.video or replied.document or replied.voice))
    query = " ".join(message.command[1:])

    if not is_tg_media and not query: return await message.reply("Provide a song name!")
    requester = message.from_user.mention
    
    if not is_tg_media and query.lower() == "mypl":
        songs = await get_db_playlist(message.from_user.id)
        if not songs: return await message.reply("⚠️ Teri playlist khali hai! `/save` kar pehle.")
        loading_m = await message.reply(f"🚀 Loading {len(songs)} songs...")
        if chat_id not in chat_queue: chat_queue[chat_id] = []
        for song in songs: song["requester"] = requester; chat_queue[chat_id].append(song)
        if not is_playing.get(chat_id):
            is_playing[chat_id] = True
            first_song = chat_queue[chat_id].pop(0)
            fresh_url = await get_fresh_url(first_song)
            first_song["url"] = fresh_url
            stream = MediaStream(fresh_url) if first_song.get('is_video') else MediaStream(fresh_url, video_flags=MediaStream.Flags.IGNORE)
            await call_py.play(chat_id, stream)
            cap, rm = get_music_panel(first_song['title'], first_song['duration'], requester, played_sec=0, total_sec=first_song['duration_sec'])
            try: m_panel = await message.reply_photo(photo=first_song["thumbnail"], caption=cap, reply_markup=rm)
            except: m_panel = await message.reply_photo(photo=DEFAULT_THUMB, caption=cap, reply_markup=rm)
            current_playing[chat_id] = {'song': first_song, 'start_time': time.time(), 'panel_msg': m_panel, 'is_paused': False, 'pause_time': 0}
        await loading_m.delete()
        return

    try:
        if is_tg_media:
            m = await message.reply("📥 Downloading...")
            file_path = await replied.download()
            obj = replied.audio or replied.video or replied.document or replied.voice
            dur = int(getattr(obj, 'duration', 0) or 0)
            m_, s_ = divmod(dur, 60); h_, m_ = divmod(m_, 60)
            dur_str = f"{h_:02d}:{m_:02d}:{s_:02d}" if h_ else f"{m_:02d}:{s_:02d}"
            yt_data = {"title": getattr(obj, 'title', None) or getattr(obj, 'file_name', "Telegram Media"), "url": file_path, "thumbnail": DEFAULT_THUMB, "duration": dur_str, "duration_sec": dur}
        else:
            m = await message.reply("🔍 Searching...")
            yt_data = await asyncio.get_event_loop().run_in_executor(thread_pool, get_yt_info, query, is_video)

        yt_data["is_video"] = is_video; yt_data["requester"] = requester
        if chat_id not in chat_queue: chat_queue[chat_id] = []
        if is_playing.get(chat_id) and not force_play:
            chat_queue[chat_id].append(yt_data)
            cap, rm = get_music_panel(yt_data['title'], yt_data['duration'], requester, is_queue=True, pos=len(chat_queue[chat_id]))
            try: await message.reply_photo(photo=yt_data["thumbnail"], caption=cap, reply_markup=rm)
            except: await message.reply_photo(photo=DEFAULT_THUMB, caption=cap, reply_markup=rm)
        else:
            is_playing[chat_id] = True
            stream = MediaStream(yt_data["url"]) if is_video else MediaStream(yt_data["url"], video_flags=MediaStream.Flags.IGNORE)
            await call_py.play(chat_id, stream)
            cap, rm = get_music_panel(yt_data['title'], yt_data['duration'], requester, played_sec=0, total_sec=yt_data['duration_sec'])
            try: m_panel = await message.reply_photo(photo=yt_data["thumbnail"], caption=cap, reply_markup=rm)
            except: m_panel = await message.reply_photo(photo=DEFAULT_THUMB, caption=cap, reply_markup=rm)
            current_playing[chat_id] = {'song': yt_data, 'start_time': time.time(), 'panel_msg': m_panel, 'is_paused': False, 'pause_time': 0}
        await m.delete()
    except Exception as e:
        await m.edit(f"❌ Error: `{e}`"); asyncio.create_task(delayed_delete(m, 7))

@app.on_message(filters.command(["play", "vplay", "fplay", "fvplay"]) & filters.group)
async def music_cmds(client, message):
    cmd = message.command[0]
    await process_play(client, message, is_video=("vplay" in cmd), force_play=("fplay" in cmd))

@app.on_message(filters.command("skip") & filters.group)
async def skip_cmd(client, message):
    try: await message.delete()
    except: pass
    chat_id = message.chat.id
    if chat_id in chat_queue and chat_queue[chat_id]:
        next_song = chat_queue[chat_id].pop(0)
        fresh_url = await get_fresh_url(next_song)
        stream = MediaStream(fresh_url) if next_song.get('is_video') else MediaStream(fresh_url, video_flags=MediaStream.Flags.IGNORE)
        await call_py.play(chat_id, stream)
        cap, rm = get_music_panel(next_song['title'], next_song['duration'], next_song['requester'], played_sec=0, total_sec=next_song['duration_sec'])
        m_panel = await message.reply_photo(photo=next_song["thumbnail"] or DEFAULT_THUMB, caption=cap, reply_markup=rm)
        current_playing[chat_id] = {'song': next_song, 'start_time': time.time(), 'panel_msg': m_panel, 'is_paused': False, 'pause_time': 0}
    else:
        is_playing[chat_id] = False; current_playing.pop(chat_id, None); await call_py.leave_call(chat_id)
        m = await app.send_message(chat_id, "⏭️ Queue empty, left VC."); asyncio.create_task(delayed_delete(m))

@app.on_message(filters.command("pause") & filters.group)
async def pause_cmd(client, message):
    try: await message.delete()
    except: pass
    chat_id = message.chat.id
    await call_py.pause(chat_id)
    if chat_id in current_playing: current_playing[chat_id].update({'is_paused': True, 'pause_time': time.time()})
    m = await message.reply("⏸ Paused."); asyncio.create_task(delayed_delete(m, 5))

@app.on_message(filters.command("resume") & filters.group)
async def resume_cmd(client, message):
    try: await message.delete()
    except: pass
    chat_id = message.chat.id
    await call_py.resume(chat_id)
    if chat_id in current_playing and current_playing[chat_id]['is_paused']:
        current_playing[chat_id]['start_time'] += time.time() - current_playing[chat_id]['pause_time']
        current_playing[chat_id]['is_paused'] = False
    m = await message.reply("▶ Resumed."); asyncio.create_task(delayed_delete(m, 5))

@app.on_message(filters.command("stop") & filters.group)
async def stop_cmd(client, message):
    try: await message.delete()
    except: pass
    chat_id = message.chat.id
    if chat_id in chat_queue: chat_queue[chat_id].clear()
    is_playing[chat_id] = False; current_playing.pop(chat_id, None)
    await call_py.leave_call(chat_id)
    m = await message.reply("🛑 Stopped & Left VC."); asyncio.create_task(delayed_delete(m, 5))

@app.on_message(filters.command("reload") & filters.group)
async def reload_cmd(client, message):
    try: await message.delete()
    except: pass
    count = await reload_admins(message.chat.id)
    m = await message.reply(f"⚡ **Admin cache refreshed!** `{count}` admins loaded.")
    asyncio.create_task(delayed_delete(m))

@app.on_message(filters.command("refresh") & filters.group)
async def refresh_cmd(client, message):
    try: await message.delete()
    except: pass
    chat_id = message.chat.id
    if chat_id in current_playing and is_playing.get(chat_id):
        dt = current_playing[chat_id]
        played_sec = time.time() - dt['start_time'] if not dt['is_paused'] else dt['pause_time'] - dt['start_time']
        _, buttons = get_music_panel(dt['song']['title'], dt['song']['duration'], dt['song']['requester'], played_sec=played_sec, total_sec=dt['song']['duration_sec'])
        try: await dt['panel_msg'].edit_reply_markup(reply_markup=buttons)
        except: pass
        m = await message.reply("🔄 **Panel Refreshed!**")
    else: m = await message.reply("ℹ️ **No active stream.**")
    asyncio.create_task(delayed_delete(m))

@app.on_callback_query(filters.regex("^(pause_cb|resume_cb|skip_cb|stop_cb|progress_bar|replay_cb|refresh_cb|reload_cb|close_msg)$"))
async def panel_callbacks(client, cb):
    data = cb.data; chat_id = cb.message.chat.id
    if data == "close_msg": return await cb.message.delete()
    if data == "progress_bar": return await cb.answer("🔄 Progress Synced!", show_alert=False)
    if data == "refresh_cb":
        if chat_id in current_playing: await cb.answer("🔄 Panel Synced!", show_alert=False)
        else: await cb.answer("ℹ️ No stream.", show_alert=True)
    elif data == "reload_cb":
        count = await reload_admins(chat_id)
        await cb.answer(f"⚡ Admin cache updated! ({count} admins)", show_alert=False)
    elif data == "pause_cb":
        await call_py.pause(chat_id)
        if chat_id in current_playing: current_playing[chat_id].update({'is_paused': True, 'pause_time': time.time()})
        await cb.answer("⏸ Paused", show_alert=False)
    elif data == "resume_cb":
        await call_py.resume(chat_id)
        if chat_id in current_playing and current_playing[chat_id]['is_paused']:
            current_playing[chat_id]['start_time'] += time.time() - current_playing[chat_id]['pause_time']
            current_playing[chat_id]['is_paused'] = False
        await cb.answer("▶ Resumed", show_alert=False)
    elif data == "stop_cb":
        if chat_id in chat_queue: chat_queue[chat_id].clear()
        is_playing[chat_id] = False; current_playing.pop(chat_id, None)
        await call_py.leave_call(chat_id); await cb.message.delete(); await cb.answer("🛑 Stopped", show_alert=False)
    elif data == "replay_cb":
        if chat_id in current_playing:
            song = current_playing[chat_id]['song']
            fresh_url = await get_fresh_url(song); song["url"] = fresh_url
            stream = MediaStream(fresh_url) if song.get('is_video') else MediaStream(fresh_url, video_flags=MediaStream.Flags.IGNORE)
            await call_py.play(chat_id, stream)
            current_playing[chat_id].update({'start_time': time.time(), 'is_paused': False})
            _, buttons = get_music_panel(song['title'], song['duration'], song['requester'], played_sec=0, total_sec=song['duration_sec'])
            try: await cb.message.edit_reply_markup(reply_markup=buttons)
            except: pass
            await cb.answer("↻ Replaying!", show_alert=False)
    elif data == "skip_cb":
        if chat_id in chat_queue and chat_queue[chat_id]:
            next_song = chat_queue[chat_id].pop(0)
            fresh_url = await get_fresh_url(next_song)
            stream = MediaStream(fresh_url) if next_song.get('is_video') else MediaStream(fresh_url, video_flags=MediaStream.Flags.IGNORE)
            await call_py.play(chat_id, stream)
            cap, rm = get_music_panel(next_song['title'], next_song['duration'], next_song['requester'], played_sec=0, total_sec=next_song['duration_sec'])
            m_panel = await cb.message.reply_photo(photo=next_song["thumbnail"] or DEFAULT_THUMB, caption=cap, reply_markup=rm)
            current_playing[chat_id] = {'song': next_song, 'start_time': time.time(), 'panel_msg': m_panel, 'is_paused': False, 'pause_time': 0}
            await cb.message.delete(); await cb.answer("⏭ Skipped", show_alert=False)
        else:
            is_playing[chat_id] = False; current_playing.pop(chat_id, None); await call_py.leave_call(chat_id); await cb.message.delete()
            m = await app.send_message(chat_id, "⏭️ Queue empty, left VC."); asyncio.create_task(delayed_delete(m))

@call_py.on_update(ptc_filters.stream_end)
async def on_stream_end_handler(client: PyTgCalls, update: Update):
    chat_id = update.chat_id
    if chat_id in chat_queue and chat_queue[chat_id]:
        next_song = chat_queue[chat_id].pop(0)
        fresh_url = await get_fresh_url(next_song)
        stream = MediaStream(fresh_url) if next_song.get('is_video') else MediaStream(fresh_url, video_flags=MediaStream.Flags.IGNORE)
        await client.play(chat_id, stream)
        cap, rm = get_music_panel(next_song['title'], next_song['duration'], next_song['requester'], played_sec=0, total_sec=next_song['duration_sec'])
        m_panel = await app.send_photo(chat_id=chat_id, photo=next_song["thumbnail"] or DEFAULT_THUMB, caption=cap, reply_markup=rm)
        current_playing[chat_id] = {'song': next_song, 'start_time': time.time(), 'panel_msg': m_panel, 'is_paused': False, 'pause_time': 0}
    else:
        is_playing[chat_id] = False; current_playing.pop(chat_id, None)
        try: await client.leave_call(chat_id); m = await app.send_message(chat_id, "🛑 Queue empty, left VC."); asyncio.create_task(delayed_delete(m))
        except: pass

@app.on_message(filters.command("start"))
async def start_cmd(client, message):
    add_chat(message.chat.id)
    config = load_start_config()
    if config:
        final_text = config["text"].replace("{mention}", message.from_user.mention)
        raw_btns = config["buttons"]
        kb = []
        if len(raw_btns) > 0: kb.append([InlineKeyboardButton(raw_btns[0]["name"], url=raw_btns[0]["url"])])
        if len(raw_btns) > 1: kb.append([InlineKeyboardButton(b["name"], url=b["url"]) for b in raw_btns[1:3]])
        if len(raw_btns) > 3: kb.append([InlineKeyboardButton(b["name"], url=b["url"]) for b in raw_btns[3:5]])
        try: return await message.reply_photo(photo=config["photo"], caption=final_text, reply_markup=InlineKeyboardMarkup(kb) if kb else None)
        except: pass

    await message.reply(
        f"Hello {message.from_user.mention}! Music + UNO Bot is ready. 🤖\n\n"
        "**🎶 MUSIC:** `/play`, `/vplay`, `/pause`, `/resume`, `/skip`, `/stop`\n"
        "**☁️ PLAYLIST:** `/save`, `/mypl`\n"
        "**🃏 UNO:** `/startgame`, `/topplayers`\n"
        "**⚡ UTILS:** `/refresh`, `/reload`"
    )

# ==========================================
# 🚀 MAIN LOOP
# ==========================================
async def main():
    print("⏳ Connecting Bot and Assistant...")
    await app.start()
    await call_py.start() 
    global BOT_USERNAME, ASSISTANT_ID
    BOT_USERNAME = (await app.get_me()).username
    ASSISTANT_ID = (await assistant.get_me()).id
    
    await load_cards_to_cache()
    asyncio.create_task(progress_updater())
    
    try:
        await app.set_bot_commands([
            BotCommand("play", "Play Audio"),
            BotCommand("vplay", "Play Video"),
            BotCommand("startgame", "Start UNO lobby"),
            BotCommand("topplayers", "UNO Leaderboard"),
            BotCommand("save", "Save song to Playlist"),
            BotCommand("mypl", "Manage Playlist"),
            BotCommand("skip", "Skip Track"), 
            BotCommand("pause", "Pause stream"),
            BotCommand("resume", "Resume stream"), 
            BotCommand("stop", "Stop stream"),
            BotCommand("refresh", "Sync player")
        ])
    except: pass
    
    print("=========================================")
    print("✅ FULL CLOUD (DB + CACHE) UNO ENGINE IS LIVE!")
    print("=========================================")
    await idle()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())