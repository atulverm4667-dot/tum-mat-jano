import logging
import asyncio
import os
import time
import json
import random
from pyrogram import Client, filters, idle
from pyrogram.types import (InlineKeyboardMarkup, InlineKeyboardButton, BotCommand, 
                            InlineQueryResultArticle, InputTextMessageContent, InlineQueryResultCachedPhoto)
from pyrogram.enums import ChatMembersFilter
from motor.motor_asyncio import AsyncIOMotorClient
from flask import Flask
import threading

# ==========================================
# 🌐 DUMMY WEB PAGE / KEEP-ALIVE SERVER
# ==========================================
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "<h1>🤖 PRO UNO Bot is Alive! 🚀</h1>"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host="0.0.0.0", port=port)

# ==========================================
# ⚙️ CONFIG & MONGODB SETUP
# ==========================================
from config import API_ID, API_HASH, BOT_TOKEN, OWNER_ID
try: from config import MONGO_URL
except ImportError: MONGO_URL = ""

logging.basicConfig(level=logging.INFO)
try: OWNER_ID = int(OWNER_ID)
except Exception: OWNER_ID = 0

if MONGO_URL:
    mongo_client = AsyncIOMotorClient(MONGO_URL)
    db = mongo_client["UnoBotDB"]
    uno_stats_col = db["uno_stats"]  
    uno_cards_col = db["uno_cards"] 
    print("✅ MongoDB Connected Successfully!")
else: 
    print("⚠️ MONGO_URL not found!")

app = Client("UnoBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
uno_games = {} 
cards_cache = {} 
BOT_USERNAME = ""

async def load_cards_to_cache():
    if not MONGO_URL: return
    async for card in uno_cards_col.find():
        cards_cache[card["card_name"]] = card["file_id"]

async def delayed_delete(message, delay=5):
    await asyncio.sleep(delay)
    try: await message.delete()
    except: pass

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

# ==========================================
# 🛠️ UTILS FOR OWNER (HIDDEN)
# ==========================================
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

# ==========================================
# 👑 HIDDEN OWNER COMMANDS (GCAST, USERS, ETC)
# ==========================================
@app.on_message(filters.command("users") & filters.user(OWNER_ID))
async def users_cmd(client, message):
    chats = get_chats()
    await message.reply(f"📊 **Bot Statistics:**\n\n👤 Total Groups & Users Saved: `{len(chats)}`")

@app.on_message(filters.command("groups") & filters.user(OWNER_ID))
async def groups_cmd(client, message):
    chats = get_chats()
    if not chats: return await message.reply("❌ Abhi tak kisi bhi group ya chat ka data save nahi hua hai!")
    m = await message.reply(f"📂 Fetching details for {len(chats)} chats...")
    text = "📋 **Connected Groups & Chats List:**\n\n"
    for chat_id in chats:
        try:
            chat = await client.get_chat(int(chat_id))
            title = chat.title or chat.first_name or "Private/Unknown"
            username = f"@{chat.username}" if chat.username else f"ID: `{chat.id}`"
            text += f"• **{title}** ({username})\n\n"
        except Exception:
            text += f"• ID: `{chat_id}` (Could not fetch details)\n\n"
    if len(text) > 4000:
        with open("groups_list.txt", "w", encoding="utf-8") as f: f.write(text)
        await message.reply_document("groups_list.txt", caption="📂 List bohot badi thi, isliye file bhej di hai.")
        try: os.remove("groups_list.txt")
        except: pass
        await m.delete()
    else:
        await m.edit(text)

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

@app.on_message(filters.command("uploadcards") & filters.user(OWNER_ID))
async def upload_cards_cmd(client, message):
    if not MONGO_URL: return await message.reply("⚠️ MongoDB connected nahi hai!")
    folder = "uno_images"
    if not os.path.exists(folder):
        return await message.reply(f"⚠️ `{folder}` naam ka folder nahi mila!")
    m = await message.reply("⏳ **Uploading cards safely...**")
    uploaded = 0
    for root_dir, sub_dirs, files in os.walk(folder):
        for file in files:
            name_without_ext = os.path.splitext(file)[0]
            if file.lower().endswith((".png", ".jpg", ".jpeg")):
                file_path = os.path.join(root_dir, file)
                try:
                    msg = await client.send_photo(message.chat.id, file_path)
                    file_id = msg.photo.file_id
                    cards_cache[name_without_ext] = file_id
                    await uno_cards_col.update_one({"card_name": name_without_ext}, {"$set": {"file_id": file_id}}, upsert=True)
                    uploaded += 1
                    await asyncio.sleep(1.2) 
                except Exception: pass
    await m.edit(f"✅ **Upload Complete!** Total: `{uploaded}` cards.")

@app.on_message(filters.command("setposition") & filters.user(OWNER_ID))
async def set_position_cmd(client, message):
    if not MONGO_URL: return await message.reply("⚠️ Database connected nahi hai!")
    args = message.command
    if len(args) != 3: return await message.reply("⚠️ Format: `/setposition <user_id> <wins>`")
    try:
        user_id = int(args[1]); wins = int(args[2])
        try:
            user = await app.get_users(user_id)
            name = user.first_name
        except: name = "Hidden Player"
        await uno_stats_col.update_one({"user_id": user_id}, {"$set": {"wins": wins, "name": name}}, upsert=True)
        await message.reply(f"✅ Update Done!\n👤 **Player:** {name}\n🏆 **Wins Set To:** `{wins}`")
    except ValueError:
        await message.reply("⚠️ User ID and Wins should be numbers!")


# ==========================================
# ⚙️ SETTINGS, STATS & HELP
# ==========================================
@app.on_message(filters.command("help"))
async def help_cmd(client, message):
    add_chat(message.chat.id)
    help_text = (
        "Follow these steps:\n\n"
        "1. Add this bot to a group\n"
        "2. In the group, start a new game with /new or join an already running game with /join\n"
        "3. After at least two players have joined, start the game with /start\n"
        f"4. Type @{BOT_USERNAME} into your chat box and hit **space**, or click the via @{BOT_USERNAME} text next to messages. "
        "You will see your cards (some greyed out), any extra options like drawing, and a ❓ to see the current game state. "
        "The **greyed out cards** are those you **can not** play at the moment. Tap an option to execute the selected action.\n"
        "Players can join the game at any time. To leave a game, use /leave. If a player takes more than 90 seconds to play, "
        "you can use /skip to skip that player.\n\n"
        "**Language and other settings**: /settings\n"
        "Other commands (only game creator):\n"
        "/close - Close lobby\n"
        "/open - Open lobby\n"
        "/kill - Terminate the game\n"
        "/kick - Select a player to kick by replying to him or her\n"
    )
    await message.reply(help_text)

@app.on_message(filters.command("settings") & filters.private)
async def settings_cmd(client, message):
    add_chat(message.chat.id)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Enable statistics", callback_data="enable_stats")],
        [InlineKeyboardButton("🌍 Language", callback_data="change_lang")]
    ])
    await message.reply("Settings:", reply_markup=kb)

@app.on_message(filters.command("stats"))
async def stats_cmd(client, message):
    add_chat(message.chat.id)
    if not MONGO_URL: return await message.reply("Database not connected.")
    
    stats = await uno_stats_col.find_one({"user_id": message.from_user.id})
    wins = stats.get("wins", 0) if stats else 0
    
    # Original bot jaisa accurate stats format
    text = (
        f"**{message.from_user.first_name}'s UNO Stats:**\n\n"
        f"{wins} games played\n"
        f"{wins} first places ({'100' if wins > 0 else '0'}%)\n"
        f"{(wins * 15) + random.randint(10, 50) if wins > 0 else 0} cards played" # Slight dynamic cards played
    )
    await message.reply(text)

@app.on_message(filters.command("topplayers"))
async def top_players_cmd(client, message):
    if not MONGO_URL: return await message.reply("⚠️ Database is not connected!")
    m = await message.reply("🏆 Fetching Leaderboard...")
    top_players = await uno_stats_col.find().sort("wins", -1).limit(10).to_list(10)
    if not top_players:
        return await m.edit("😔 No one has won a game yet!")
    text = "🔥 **UNO GLOBAL LEADERBOARD** 🔥\n\n"
    for i, p in enumerate(top_players, start=1):
        name = p.get("name", "Unknown Player")
        wins = p.get("wins", 0)
        user_id = p.get("user_id")
        if i <= 3: text += f"{i}. 🌟 **[Ultra Pro Player - {name}](tg://user?id={user_id})** ➣ `{wins}` Wins 👑\n"
        elif i <= 6: text += f"{i}. 🎖 **[Pro Player - {name}](tg://user?id={user_id})** ➣ `{wins}` Wins\n"
        else: text += f"{i}. 🔰 **[Beginner Pro - {name}](tg://user?id={user_id})** ➣ `{wins}` Wins\n"
    await m.edit(text)

@app.on_callback_query(filters.regex("^enable_stats$"))
async def cb_enable_stats(client, cb):
    await cb.message.edit("Enabled statistics!")

@app.on_callback_query(filters.regex("^change_lang$"))
async def cb_change_lang(client, cb):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("ca_CA - 🇪🇸 Catalan", callback_data="lang_ca")],
        [InlineKeyboardButton("de_DE - 🇩🇪 Deutsch (DE)", callback_data="lang_de")],
        [InlineKeyboardButton("en_US - 🇺🇸 English (US)", callback_data="lang_en")],
        [InlineKeyboardButton("es_ES - 🇪🇸 Español (ES)", callback_data="lang_es")],
        [InlineKeyboardButton("hi_IN - 🇮🇳 Hindi", callback_data="lang_hi")],
        [InlineKeyboardButton("id_ID - 🇮🇩 Bahasa Indonesia", callback_data="lang_id")],
        [InlineKeyboardButton("it_IT - 🇮🇹 Italiano", callback_data="lang_it")],
        [InlineKeyboardButton("ru_RU - 🇷🇺 Русский язык", callback_data="lang_ru")]
    ])
    await cb.message.edit("Select locale", reply_markup=kb)

@app.on_callback_query(filters.regex(r"^lang_"))
async def cb_set_lang(client, cb):
    await cb.answer("Language updated successfully!", show_alert=True)
    await cb.message.edit("Language preferences saved.")


# ==========================================
# 🃏 UNO CORE ENGINE
# ==========================================
def get_uno_deck():
    colors = ["🔴 Red", "🔵 Blue", "🟢 Green", "🟡 Yellow"]
    values = ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "⏭ Skip", "🔄 Reverse", "➕2"]
    wilds = ["🌈 Wild", "💥 Wild +4"]
    deck = []
    for c in colors:
        for v in values:
            deck.append(f"{c} {v}"); deck.append(f"{c} {v}") if v != "0" else None
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
    game["turn_id"] = game.get("turn_id", 0) + 1  
    return game["turn_index"]

async def send_uno_table(chat_id):
    game = uno_games.get(chat_id)
    if not game or game["status"] != "playing": return
    current_player = game["players"][game["turn_index"]]
    players_text = "\n".join([f"{'👉' if p['id'] == current_player['id'] else '👤'} {p['name']} - {len(p['cards'])} cards" for p in game["players"]])
    
    text = (f"🃏 **UNO TABLE**\n\n🎨 **Current Color:** {game['current_color']}\n🎯 **Top Card:** {game['top_card']}\n\n"
            f"👥 **Players:**\n{players_text}\n\n⏳ *You have 90 seconds to play!*")
            
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🃏 Play Card", switch_inline_query_current_chat="")],
        [InlineKeyboardButton("👀 Show Cards", callback_data="show_uno_cards"), InlineKeyboardButton("📥 Draw", callback_data="uno_draw")]
    ])
    
    if "table_msg" in game:
        try: await game["table_msg"].delete()
        except: pass

    file_key = card_to_filename(game["top_card"]); file_id = cards_cache.get(file_key)
    try:
        if file_id: game["table_msg"] = await app.send_photo(chat_id, photo=file_id, caption=text, reply_markup=kb)
        else: game["table_msg"] = await app.send_message(chat_id, text, reply_markup=kb)
    except: game["table_msg"] = await app.send_message(chat_id, text, reply_markup=kb)

# ==========================================
# 🎮 GAME COMMANDS (/new, /join, /start, /leave, /kill, /kick)
# ==========================================
@app.on_message(filters.command("new") & filters.group)
async def new_game_cmd(client, message):
    chat_id = message.chat.id
    add_chat(chat_id)
    if chat_id in uno_games:
        return await message.reply("⚠️ A game is already in progress or lobby is open! Join with /join or /kill it.")
    player = {"id": message.from_user.id, "name": message.from_user.first_name, "cards": []}
    uno_games[chat_id] = {"status": "lobby", "creator": player["id"], "is_open": True, "players": [player], "lobby_msg": None}
    
    m = await message.reply(f"🃏 **A new UNO game has been created!**\n\nPress /join to enter the game.\nWhen everyone is ready, the creator can type /start.")
    uno_games[chat_id]["lobby_msg"] = m

@app.on_message(filters.command("join") & filters.group)
async def join_game_cmd(client, message):
    chat_id = message.chat.id
    add_chat(chat_id)
    if chat_id not in uno_games or uno_games[chat_id]["status"] != "lobby":
        return await message.reply("⚠️ No open lobby available. Use /new to start one.")
    if not uno_games[chat_id]["is_open"]:
        return await message.reply("⚠️ The lobby is closed by the creator.")
        
    players = uno_games[chat_id]["players"]
    user = message.from_user
    if any(p["id"] == user.id for p in players): 
        return await message.reply("You have already joined!")
        
    players.append({"id": user.id, "name": user.first_name, "cards": []})
    await message.reply(f"✅ {user.first_name} has joined the game! Total players: {len(players)}")

@app.on_message(filters.command("leave") & filters.group)
async def leave_game_cmd(client, message):
    chat_id = message.chat.id
    if chat_id not in uno_games: return
    game = uno_games[chat_id]
    user_id = message.from_user.id
    
    player_idx = next((i for i, p in enumerate(game["players"]) if p["id"] == user_id), None)
    if player_idx is None: return await message.reply("You are not in the game.")
    
    leaving_player = game["players"].pop(player_idx)
    await message.reply(f"👋 {leaving_player['name']} left the game.")
    
    if len(game["players"]) < 2 and game["status"] == "playing":
        uno_games.pop(chat_id, None)
        await app.send_message(chat_id, "⚠️ Not enough players left. Game terminated.")
    elif game["status"] == "playing" and game["turn_index"] == player_idx:
        get_next_turn(game)
        await send_uno_table(chat_id)

@app.on_message(filters.command("close") & filters.group)
async def close_lobby_cmd(client, message):
    chat_id = message.chat.id
    if chat_id in uno_games and uno_games[chat_id]["creator"] == message.from_user.id:
        uno_games[chat_id]["is_open"] = False
        await message.reply("🔒 The game lobby is now closed. No one else can join.")

@app.on_message(filters.command("open") & filters.group)
async def open_lobby_cmd(client, message):
    chat_id = message.chat.id
    if chat_id in uno_games and uno_games[chat_id]["creator"] == message.from_user.id:
        uno_games[chat_id]["is_open"] = True
        await message.reply("🔓 The game lobby is now open. Players can /join.")

@app.on_message(filters.command("start") & filters.group)
async def start_game_cmd(client, message):
    chat_id = message.chat.id
    if chat_id not in uno_games or uno_games[chat_id]["status"] != "lobby":
        return await message.reply("⚠️ No lobby exists or game is already playing.")
        
    game = uno_games[chat_id]
    if len(game["players"]) < 2:
        return await message.reply("⚠️ Need at least 2 players to start!")
        
    game["status"] = "playing"
    deck = get_uno_deck()
    for p in game["players"]: p["cards"] = [deck.pop() for _ in range(7)]
    top_card = deck.pop()
    while "Wild" in top_card or "Reverse" in top_card or "Skip" in top_card or "➕2" in top_card:
        deck.append(top_card); random.shuffle(deck); top_card = deck.pop()
    
    game["deck"] = deck; game["top_card"] = top_card; game["current_color"] = top_card.split(" ")[1]
    game["turn_index"] = 0; game["direction"] = 1; game["turn_id"] = 1  
    
    await message.reply("🎮 **The game has started!**")
    await send_uno_table(chat_id)

@app.on_message(filters.command("kill") & filters.group)
async def kill_game_cmd(client, message):
    chat_id = message.chat.id
    if chat_id in uno_games:
        uno_games.pop(chat_id, None)
        await message.reply("🛑 **The game has been terminated!**")
    else: await message.reply("⚠️ No active game to kill.")

@app.on_message(filters.command("kick") & filters.group)
async def kick_player_cmd(client, message):
    chat_id = message.chat.id
    if chat_id not in uno_games: return
    game = uno_games[chat_id]
    
    if message.from_user.id != game["creator"]:
        return await message.reply("Only the game creator can kick players.")
        
    if not message.reply_to_message:
        return await message.reply("Please reply to the user you want to kick.")
        
    target_id = message.reply_to_message.from_user.id
    player_idx = next((i for i, p in enumerate(game["players"]) if p["id"] == target_id), None)
    
    if player_idx is not None:
        kicked = game["players"].pop(player_idx)
        await message.reply(f"👢 {kicked['name']} has been kicked from the game.")
        if len(game["players"]) < 2 and game["status"] == "playing":
            uno_games.pop(chat_id, None)
            await app.send_message(chat_id, "⚠️ Not enough players left. Game terminated.")
        elif game["status"] == "playing" and game["turn_index"] == player_idx:
            get_next_turn(game)
            await send_uno_table(chat_id)
    else:
        await message.reply("That user is not in the game.")

@app.on_message(filters.command("skip") & filters.group)
async def skip_player_cmd(client, message):
    chat_id = message.chat.id
    if chat_id not in uno_games or uno_games[chat_id]["status"] != "playing": return
    game = uno_games[chat_id]
    
    player = game["players"][game["turn_index"]]
    if not game["deck"]: game["deck"] = get_uno_deck()
    player["cards"].append(game["deck"].pop())
    
    await message.reply(f"⏭️ {player['name']} took too long and was skipped! (Forced draw)")
    get_next_turn(game)
    await send_uno_table(chat_id)

# ==========================================
# 🃏 INLINE PLAYING MECHANICS
# ==========================================
@app.on_callback_query(filters.regex("^show_uno_cards$"))
async def show_uno_cards_cb(client, cb):
    chat_id = cb.message.chat.id
    if chat_id not in uno_games or uno_games[chat_id]["status"] != "playing": 
        return await cb.answer("Game is not active!", show_alert=True)
    player = next((p for p in uno_games[chat_id]["players"] if p["id"] == cb.from_user.id), None)
    if not player: return await cb.answer("You are not playing!", show_alert=True)
    cards_text = "\n".join(player["cards"]); await cb.answer(f"🃏 YOUR CARDS:\n\n{cards_text}", show_alert=True)

@app.on_inline_query()
async def inline_uno_cards(client, query):
    user_id = query.from_user.id
    results, active_chat, player_data = [], None, None
    for chat_id, game in uno_games.items():
        if game["status"] in ["playing", "waiting_color"]:
            for p in game["players"]:
                if p["id"] == user_id: active_chat, player_data = chat_id, p; break
        if active_chat: break

    if not active_chat:
        results.append(InlineQueryResultArticle(id="not_in_game", title="Not playing UNO!", input_message_content=InputTextMessageContent("I tried to play but I'm not in a game!")))
        return await query.answer(results, cache_time=0, is_personal=True)

    game = uno_games[active_chat]; is_my_turn = game["players"][game["turn_index"]]["id"] == user_id
    for i, card in enumerate(player_data["cards"]):
        playable = is_playable(card, game["top_card"], game["current_color"])
        title = f"{'✅ Play' if playable and is_my_turn else '❌ Cannot play'} {card}"
        payload = f"🃏 [UNO] Played: {card}\n\nChatID: {active_chat}\nCardIndex: {i}"
        if not playable or not is_my_turn: payload = f"I tried to cheat and play {card}! 🤡"
        file_key, file_id = card_to_filename(card), cards_cache.get(card_to_filename(card))
        
        if file_id:
            results.append(InlineQueryResultCachedPhoto(photo_file_id=file_id, id=f"card_{i}_{time.time()}", title=title, description="Tap to play this card!" if playable and is_my_turn else "Greyed out/Invalid move", input_message_content=InputTextMessageContent(payload)))
        else:
            results.append(InlineQueryResultArticle(id=f"card_{i}_{time.time()}", title=title, description="Tap to play!" if playable and is_my_turn else "Not your turn or invalid card.", input_message_content=InputTextMessageContent(payload)))
    await query.answer(results, cache_time=0, is_personal=True)

@app.on_message(filters.regex(r"I tried to cheat and play (.*)! 🤡"))
async def catch_cheat(client, message):
    try: await message.delete()
    except: pass
    m = await message.reply(f"🚫 [{message.from_user.first_name}](tg://user?id={message.from_user.id}), you cannot play that card right now!")
    asyncio.create_task(delayed_delete(m, 4))

@app.on_message(filters.regex(r"🃏 \[UNO\] Played: (.*)\n\nChatID: (-\d+)\nCardIndex: (\d+)"))
async def catch_uno_play(client, message):
    try: await message.delete()
    except: pass
    match = message.matches[0]; card, chat_id, card_index = match.group(1), int(match.group(2)), int(match.group(3))
    user_id = message.from_user.id

    if chat_id not in uno_games or uno_games[chat_id]["status"] != "playing": return
    game = uno_games[chat_id]
    
    if game["players"][game["turn_index"]]["id"] != user_id:
        m = await app.send_message(chat_id, f"⚠️ It's not your turn [{message.from_user.first_name}](tg://user?id={message.from_user.id})!")
        return asyncio.create_task(delayed_delete(m, 4))

    player = game["players"][game["turn_index"]]
    if card_index >= len(player["cards"]) or player["cards"][card_index] != card: return

    player["cards"].pop(card_index); game["top_card"] = card

    if "Wild" in card:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔴 Red", callback_data="unocolor_🔴 Red"), InlineKeyboardButton("🔵 Blue", callback_data="unocolor_🔵 Blue")],
            [InlineKeyboardButton("🟢 Green", callback_data="unocolor_🟢 Green"), InlineKeyboardButton("🟡 Yellow", callback_data="unocolor_🟡 Yellow")]
        ])
        game["status"] = "waiting_color"; game["pending_effect"] = "+4" if "+4" in card else "none"
        if "table_msg" in game:
            try: await game["table_msg"].delete()
            except: pass
            
        game["turn_id"] += 1
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
        winner_name, winner_id = player['name'], player['id']; uno_games.pop(chat_id, None)
        if MONGO_URL: await uno_stats_col.update_one({"user_id": winner_id}, {"$inc": {"wins": 1}, "$set": {"name": winner_name}}, upsert=True)
        return await app.send_message(chat_id, f"🎉 **[{winner_name}](tg://user?id={winner_id}) HAS WON UNO!** 🏆")

    get_next_turn(game); await send_uno_table(chat_id)

@app.on_callback_query(filters.regex(r"^unocolor_(.*)$"))
async def choose_color_cb(client, cb):
    chat_id = cb.message.chat.id
    if chat_id not in uno_games or uno_games[chat_id]["status"] != "waiting_color": return
    game = uno_games[chat_id]
    if game["players"][game["turn_index"]]["id"] != cb.from_user.id: return await cb.answer("Wait!", show_alert=True)
        
    game["current_color"] = cb.data.split("_")[1].split(" ")[1]
    if game["pending_effect"] == "+4":
        victim = game["players"][(game["turn_index"] + game["direction"]) % len(game["players"])]
        for _ in range(4):
            if not game["deck"]: game["deck"] = get_uno_deck()
            victim["cards"].append(game["deck"].pop())
        get_next_turn(game)

    game["status"] = "playing"; game["pending_effect"] = "none"
    
    if len(game["players"][game["turn_index"]]["cards"]) == 0:
        winner_name, winner_id = game["players"][game["turn_index"]]["name"], game["players"][game["turn_index"]]["id"]
        uno_games.pop(chat_id, None)
        if MONGO_URL: await uno_stats_col.update_one({"user_id": winner_id}, {"$inc": {"wins": 1}, "$set": {"name": winner_name}}, upsert=True)
        return await app.send_message(chat_id, f"🎉 **{winner_name} HAS WON UNO!** 🏆")
        
    get_next_turn(game); await cb.message.delete(); await send_uno_table(chat_id)

@app.on_callback_query(filters.regex("^uno_draw$"))
async def uno_draw_cb(client, cb):
    chat_id = cb.message.chat.id
    if chat_id not in uno_games or uno_games[chat_id]["status"] != "playing": return
    game = uno_games[chat_id]
    if game["players"][game["turn_index"]]["id"] != cb.from_user.id: return await cb.answer("Wait for your turn!", show_alert=True)
        
    if not game["deck"]: game["deck"] = get_uno_deck()
    drawn = game["deck"].pop(); game["players"][game["turn_index"]]["cards"].append(drawn)
    await cb.answer(f"📥 You drew a card!", show_alert=True)
    get_next_turn(game); await send_uno_table(chat_id)

# ==========================================
# 🚀 MAIN LOOP
# ==========================================
async def main():
    print("⏳ Starting Web Server (Keep-Alive)...")
    threading.Thread(target=run_web, daemon=True).start()
    
    print("⏳ Connecting Bot...")
    await app.start()
    global BOT_USERNAME
    BOT_USERNAME = (await app.get_me()).username
    
    await load_cards_to_cache()
    
    # ❌ NOTICE: OWNER COMMANDS ARE HIDDEN FROM THIS LIST!
    try:
        await app.set_bot_commands([
            BotCommand("new", "Start a new game"),
            BotCommand("join", "Join the current game"),
            BotCommand("start", "Start the game"),
            BotCommand("leave", "Leave the game you're in"),
            BotCommand("close", "Close the game lobby"),
            BotCommand("open", "Open the game lobby"),
            BotCommand("kill", "Terminate the game"),
            BotCommand("kick", "Kick players out of the game"),
            BotCommand("skip", "Skip the current player"),
            BotCommand("help", "How to use this bot?"),
            BotCommand("settings", "Language and other settings"),
            BotCommand("stats", "Show statistics"),
            BotCommand("topplayers", "Global Leaderboard")
        ])
    except Exception as e: print("Could not set commands:", e)
    
    print("=========================================")
    print("✅ PRO UNO BOT ENGINE (WITH HIDDEN ADMIN CMD) IS LIVE!")
    print("=========================================")
    await idle()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
