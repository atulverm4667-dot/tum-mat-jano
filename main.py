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
# 🌐 DUMMY WEB PAGE / KEEP-ALIVE SERVER (FOR RENDER)
# ==========================================
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "<h1>🤖 UNO Bot is Alive and Running Successfully! 🚀</h1>"

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
    print("⚠️ MONGO_URL not found! Leaderboard and cards won't work.")

# ==========================================
# 🤖 BOT CLIENTS & GLOBALS
# ==========================================
app = Client("UnoBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

uno_games = {} 
cards_cache = {} 

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
                except Exception as e: pass
    await m.edit(f"✅ **Upload Complete!** Total: `{uploaded}` cards.")


# ==========================================
# 🏆 UNO LEADERBOARD & OWNER COMMANDS
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
        if i <= 3: text += f"{i}. 🌟 **[Ultra Pro Player - {name}](tg://user?id={user_id})** ➣ `{wins}` Wins 👑\n"
        elif i <= 6: text += f"{i}. 🎖 **[Pro Player - {name}](tg://user?id={user_id})** ➣ `{wins}` Wins\n"
        else: text += f"{i}. 🔰 **[Beginner Pro - {name}](tg://user?id={user_id})** ➣ `{wins}` Wins\n"
    await m.edit(text)

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

@app.on_message(filters.command("setposition") & filters.user(OWNER_ID))
async def set_position_cmd(client, message):
    if not MONGO_URL: return await message.reply("⚠️ Database connected nahi hai!")
    args = message.command
    if len(args) != 3: return await message.reply("⚠️ Sahi format use kar: `/setposition <user_id> <wins>`")
    try:
        user_id = int(args[1]); wins = int(args[2])
        try:
            user = await app.get_users(user_id)
            name = user.first_name
        except: name = "Hidden Player"
        await uno_stats_col.update_one({"user_id": user_id}, {"$set": {"wins": wins, "name": name}}, upsert=True)
        await message.reply(f"✅ Position Update Hogyi!\n👤 **Player:** {name}\n🏆 **Wins Set To:** `{wins}`")
    except ValueError:
        await message.reply("⚠️ User ID aur Wins numbers me hone chahiye!")


# ==========================================
# 🃏 UNO ENGINE (MAU MAU STYLE) & ⏱️ TIMERS
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
    game["turn_id"] = game.get("turn_id", 0) + 1  
    return game["turn_index"]

# ⏳ 60-Second Auto-Draw Timer Logic
async def uno_turn_timer(chat_id, turn_id):
    await asyncio.sleep(60)
    if chat_id not in uno_games: return
    game = uno_games.get(chat_id)
    if not game or game.get("turn_id") != turn_id: return
    
    try:
        player = game["players"][game["turn_index"]]
        
        if game["status"] == "waiting_color":
            game["current_color"] = "🔴"
            game["status"] = "playing"
            if game.get("pending_effect") == "+4":
                victim = game["players"][(game["turn_index"] + game["direction"]) % len(game["players"])]
                for _ in range(4):
                    if not game["deck"]: game["deck"] = get_uno_deck()
                    victim["cards"].append(game["deck"].pop())
            game["pending_effect"] = "none"
            await app.send_message(chat_id, f"⏳ **Time's up!** {player['name']} ne koi color nahi chuna. Default '🔴 Red' select ho gaya.")
            get_next_turn(game)
            asyncio.create_task(uno_turn_timer(chat_id, game["turn_id"]))
            await send_uno_table(chat_id)
            return
            
        if game["status"] == "playing":
            if not game["deck"]: game["deck"] = get_uno_deck()
            drawn = game["deck"].pop()
            player["cards"].append(drawn)
            await app.send_message(chat_id, f"⏳ **Time's up!** [{player['name']}](tg://user?id={player['id']}) ne 60 sec me card nahi khela, isliye automatic ek card draw ho gaya.")
            get_next_turn(game)
            asyncio.create_task(uno_turn_timer(chat_id, game["turn_id"]))
            await send_uno_table(chat_id)
    except Exception as e: pass

async def send_uno_table(chat_id):
    game = uno_games.get(chat_id)
    if not game: return
    current_player = game["players"][game["turn_index"]]
    players_text = "\n".join([f"{'👉' if p['id'] == current_player['id'] else '👤'} {p['name']} - {len(p['cards'])} cards" for p in game["players"]])
    
    text = (f"🃏 **UNO TABLE**\n\n"
            f"🎨 **Current Color:** {game['current_color']}\n"
            f"🎯 **Top Card:** {game['top_card']}\n\n"
            f"👥 **Players:**\n{players_text}\n\n"
            f"⏳ *You have 60 seconds to play!*")
            
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🃏 Play Card", switch_inline_query_current_chat="")],
        [InlineKeyboardButton("👀 Show Cards", callback_data="show_uno_cards"), InlineKeyboardButton("📥 Draw", callback_data="uno_draw")]
    ])
    
    if "table_msg" in game:
        try: await game["table_msg"].delete()
        except: pass

    file_key = card_to_filename(game["top_card"])
    file_id = cards_cache.get(file_key)

    try:
        if file_id: game["table_msg"] = await app.send_photo(chat_id, photo=file_id, caption=text, reply_markup=kb)
        else: game["table_msg"] = await app.send_message(chat_id, text, reply_markup=kb)
    except Exception:
        game["table_msg"] = await app.send_message(chat_id, text, reply_markup=kb)
    
    ping = await app.send_message(chat_id, f"🎯 **Teri baari hai:** [{current_player['name']}](tg://user?id={current_player['id']})")
    asyncio.create_task(delayed_delete(ping, 7))

# 🛑 FORCE END GAME COMMAND
@app.on_message(filters.command("end") & filters.group)
async def end_uno_game_cmd(client, message):
    chat_id = message.chat.id
    if chat_id in uno_games:
        uno_games.pop(chat_id, None)
        await message.reply("🛑 **UNO Game forcefully ended!**")
    else:
        await message.reply("⚠️ Koi active UNO game nahi chal raha hai!")

@app.on_message(filters.command("startgame") & filters.group)
async def start_uno_game(client, message):
    chat_id = message.chat.id
    add_chat(chat_id)
    if chat_id in uno_games and uno_games[chat_id]['status'] != 'finished':
        return await message.reply("⚠️ Ek game pehle se active hai ya lobby open hai! (To stop: `/end`)")
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
        game["turn_id"] = 1  
        
        asyncio.create_task(uno_turn_timer(chat_id, 1))
        await send_uno_table(chat_id)

@app.on_callback_query(filters.regex("^show_uno_cards$"))
async def show_uno_cards_cb(client, cb):
    chat_id = cb.message.chat.id
    if chat_id not in uno_games or uno_games[chat_id]["status"] != "playing":
        return await cb.answer("Game active nahi hai!", show_alert=True)
    player = next((p for p in uno_games[chat_id]["players"] if p["id"] == cb.from_user.id), None)
    if not player: return await cb.answer("Tu is game me nahi khel raha bhai!", show_alert=True)
    cards_text = "\n".join(player["cards"])
    await cb.answer(f"🃏 TERE CARDS:\n\n{cards_text}", show_alert=True)

@app.on_inline_query()
async def inline_uno_cards(client, query):
    user_id = query.from_user.id
    results, active_chat, player_data = [], None, None
    for chat_id, game in uno_games.items():
        if game["status"] in ["playing", "waiting_color"]:
            for p in game["players"]:
                if p["id"] == user_id:
                    active_chat, player_data = chat_id, p
                    break
        if active_chat: break

    if not active_chat:
        results.append(InlineQueryResultArticle(
            id="not_in_game", title="Not playing UNO!", 
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
        
        file_id = cards_cache.get(card_to_filename(card))
        if file_id:
            results.append(InlineQueryResultCachedPhoto(
                photo_file_id=file_id, id=f"card_{i}_{time.time()}", title=title,
                description="Tap to play this card!" if playable and is_my_turn else "Invalid move",
                input_message_content=InputTextMessageContent(payload)
            ))
        else:
            results.append(InlineQueryResultArticle(
                id=f"card_{i}_{time.time()}", title=title, 
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
            
        game["turn_id"] += 1  
        asyncio.create_task(uno_turn_timer(chat_id, game["turn_id"]))
        
        game["table_msg"] = await app.send_message(chat_id, f"🌈 **WILD CARD PLAYED by {player['name']}!**\nChoose a new color quickly (60s):", reply_markup=kb)
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
        winner_name, winner_id = player['name'], player['id']
        uno_games.pop(chat_id, None)
        await add_win(winner_id, winner_name) 
        return await app.send_message(chat_id, f"🎉 **[{winner_name}](tg://user?id={winner_id}) HAS WON UNO!** 🏆")

    get_next_turn(game)
    asyncio.create_task(uno_turn_timer(chat_id, game["turn_id"]))
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
        winner_name, winner_id = game["players"][game["turn_index"]]["name"], game["players"][game["turn_index"]]["id"]
        uno_games.pop(chat_id, None)
        await add_win(winner_id, winner_name) 
        return await app.send_message(chat_id, f"🎉 **{winner_name} HAS WON UNO!** 🏆")
        
    get_next_turn(game)
    await cb.message.delete()
    asyncio.create_task(uno_turn_timer(chat_id, game["turn_id"]))
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
    asyncio.create_task(uno_turn_timer(chat_id, game["turn_id"]))
    await send_uno_table(chat_id)


# ==========================================
# 👑 OWNER COMMANDS & UTILS
# ==========================================
@app.on_message(filters.command("id"))
async def get_id(client, message):
    await message.reply(f"👤 **Your User ID is:** `{message.from_user.id}`\n🛠 **System Owner ID:** `{OWNER_ID}`")

@app.on_message(filters.command("users") & filters.user(OWNER_ID))
async def users_cmd(client, message):
    await message.reply(f"📊 **Bot Statistics:**\n\n👤 Total Groups: `{len(get_chats())}`")

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

@app.on_message(filters.command("start"))
async def start_cmd(client, message):
    add_chat(message.chat.id)
    await message.reply(
        f"Hello {message.from_user.mention}! UNO Bot is ready and running smoothly. 🃏\n\n"
        "**🃏 UNO COMMANDS:**\n"
        "• `/startgame` - Start a new UNO lobby\n"
        "• `/end` - Force end active game\n"
        "• `/topplayers` - Global Leaderboard"
    )

# ==========================================
# 🚀 MAIN LOOP
# ==========================================
async def main():
    print("⏳ Starting Web Server (Keep-Alive)...")
    threading.Thread(target=run_web, daemon=True).start()
    
    print("⏳ Connecting Bot...")
    await app.start()
    
    await load_cards_to_cache()
    
    try:
        await app.set_bot_commands([
            BotCommand("startgame", "Start UNO lobby"),
            BotCommand("end", "End UNO Game"),
            BotCommand("topplayers", "UNO Leaderboard")
        ])
    except: pass
    
    print("=========================================")
    print("✅ PURE UNO BOT ENGINE IS LIVE!")
    print("=========================================")
    await idle()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
