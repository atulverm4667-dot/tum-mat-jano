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
    return "<h1>🤖 PRO UNO Bot is Alive with Multi-Lang & Rules! 🚀</h1>"

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
    user_settings_col = db["user_settings"] 
    print("✅ MongoDB Connected Successfully!")
else: 
    print("⚠️ MONGO_URL not found!")

app = Client("UnoBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
uno_games = {} 
cards_cache = {} 
user_langs_cache = {} 
BOT_USERNAME = ""

# ==========================================
# 🌍 TRANSLATION ENGINE (MULTI-LANG DICTIONARY)
# ==========================================
TRANSLATIONS = {
    "en_US": {
        "help": "Follow these steps:\n\n1. Add this bot to a group\n2. In the group, start a new game with /new or join an already running game with /join\n3. After at least two players have joined, start the game with /start\n4. Type @{bot} into your chat box and hit **space**. You will see your cards (greyed out = invalid).\nPlayers can join at any time. To leave, use /leave. If a player takes too long, use /skip.\n\n**Explanation of game modes**: /modes\n**Language and other settings**: /settings",
        "modes_text": "🃏 **UNO Game Rules & Modes:**\n\n**Classic UNO:**\n- Match the top card by color or number.\n- Play special cards (Skip, Reverse, Draw 2) to disrupt opponents.\n- Wild cards can change the current color.\n- Wild +4 changes the color AND forces the next player to draw 4 cards.\n- If you can't play any card, you must click 'Draw' to pick a card.\n- The first player to get rid of all their cards wins!\n\n*(More custom modes coming soon!)*",
        "settings": "⚙️ **Settings:**\nChoose an option below to update your preferences.",
        "stats_disabled": "You did not enable statistics. Use /settings in a private chat with the bot to enable them.",
        "stats_msg": "**{name}'s UNO Stats:**\n\n{wins} games won\n{wins} first places ({percent}%)\n{cards} cards played",
        "db_error": "⚠️ Database not connected.",
        "enabled_stats": "✅ Enabled statistics!",
        "lang_saved": "✅ Language preferences saved to English (US).",
        "already_playing": "⚠️ A game is already in progress or lobby is open! Join with /join or /kill it.",
        "new_lobby": "🃏 **A new UNO game has been created!**\n\nPress /join to enter the game.\nWhen everyone is ready, the creator can type /start.",
        "no_lobby": "⚠️ No open lobby available. Use /new to start one.",
        "lobby_closed_err": "⚠️ The lobby is closed by the creator.",
        "already_joined": "⚠️ You have already joined!",
        "joined_success": "✅ {name} has joined the game! Total players: {count}",
        "not_in_game": "⚠️ You are not in the game.",
        "left_game": "👋 {name} left the game.",
        "not_enough_players": "⚠️ Not enough players left. Game terminated.",
        "lobby_closed": "🔒 The game lobby is now closed. No one else can join.",
        "lobby_opened": "🔓 The game lobby is now open. Players can /join.",
        "start_error": "⚠️ No lobby exists or game is already playing.",
        "need_2_players": "⚠️ Need at least 2 players to start!",
        "game_started": "🎮 **The game has started!**",
        "game_killed": "🛑 **The game has been terminated!**",
        "no_kill": "⚠️ No active game to kill.",
        "only_creator_kick": "⚠️ Only the game creator can kick players.",
        "reply_to_kick": "⚠️ Please reply to the user you want to kick.",
        "kicked": "👢 {name} has been kicked from the game.",
        "skipped": "⏭️ {name} took too long and was skipped! (Forced draw)",
        "not_active": "⚠️ Game is not active!",
        "ur_cards_title": "🃏 YOUR CARDS:\n\n{cards}",
        "cant_play_cheat": "🚫 {name}, you cannot play that card right now!",
        "not_ur_turn": "⚠️ It's not your turn {name}!",
        "wild_played": "🌈 **WILD CARD PLAYED by {name}!**\nChoose a new color:",
        "won_game": "🎉 **{name} HAS WON UNO!** 🏆",
        "drew_card": "📥 You drew a card!",
        "wait_turn": "⚠️ Wait for your turn!",
        "table_text": "🃏 **UNO TABLE**\n\n🎨 **Current Color:** {color}\n🎯 **Top Card:** {card}\n\n👥 **Players:**\n{players}\n\n⏳ *You have 90 seconds to play!*"
    },
    "hi_IN": {
        "help": "Bot ko use karne ke steps:\n\n1. Is bot ko kisi group me add karein.\n2. Group me naya game banane ke liye /new bhejein, ya chalte game me /join karein.\n3. Jab 2 ya zyada log aa jayein, toh game shuru karne ke liye /start bhejein.\n4. Apne chat box me @{bot} likh kar **space** dabayein. Aapko apne cards dikh jayenge (jo card grey hai wo aap abhi nahi khel sakte).\nKoi bhi kabhi bhi join kar sakta hai. Game chhodne ke liye /leave use karein. Agar koi der lagaye, toh /skip use karein.\n\n**Rules padhne ke liye**: /modes\n**Language aur settings ke liye**: /settings",
        "modes_text": "🃏 **UNO Game Rules & Modes (Niyam):**\n\n**Classic UNO:**\n- Top card ke color ya number se match karta hua card khelein.\n- Opponents ko rokne ke liye special cards (Skip, Reverse, Draw 2) ka use karein.\n- Wild card khel kar aap color change kar sakte hain.\n- Wild +4 color bhi change karta hai aur agle player ko 4 cards nikalne padte hain.\n- Agar aapke paas khelne ke liye koi valid card nahi hai, toh aapko 'Draw' par click karke naya card nikalna padega.\n- Jo player sabse pehle apne saare cards khatam kar dega, wo jeetega!\n\n*(Aur custom modes jaldi add honge!)*",
        "settings": "⚙️ **Settings (सेटिंग्स):**\nNiche diye gaye options se apni pasand chunein.",
        "stats_disabled": "Aapne statistics on nahi kiya hai. Bot ki private chat me /settings bhej kar on karein.",
        "stats_msg": "**{name} ke UNO Stats:**\n\n{wins} games jeete\n{wins} first places ({percent}%)\n{cards} cards khele gaye",
        "db_error": "⚠️ Database connected nahi hai.",
        "enabled_stats": "✅ Statistics on kar diye gaye hain!",
        "lang_saved": "✅ Aapki bhasha Hindi (Hinglish) me set kar di gayi hai.",
        "already_playing": "⚠️ Ek game pehle se chal raha hai ya lobby open hai! /join se join karein ya /kill se band karein.",
        "new_lobby": "🃏 **Ek naya UNO game ban gaya hai!**\n\nGame me aane ke liye /join dabayein.\nJab sab ready ho jayein, toh creator /start daba kar game shuru kare.",
        "no_lobby": "⚠️ Koi open lobby nahi mili. Nayi lobby banane ke liye /new dabayein.",
        "lobby_closed_err": "⚠️ Creator ne lobby close kar di hai.",
        "already_joined": "⚠️ Aap pehle se game me hain!",
        "joined_success": "✅ {name} ne game join kar liya hai! Total players: {count}",
        "not_in_game": "⚠️ Aap is game me nahi hain.",
        "left_game": "👋 {name} game chhod kar chala gaya.",
        "not_enough_players": "⚠️ Khelne ke liye log kam hain. Game khatam kar diya gaya.",
        "lobby_closed": "🔒 Game lobby ab band ho chuki hai. Koi naya banda join nahi kar sakta.",
        "lobby_opened": "🔓 Game lobby open ho chuki hai. Ab koi bhi /join kar sakta hai.",
        "start_error": "⚠️ Koi lobby open nahi hai ya game pehle se chal raha hai.",
        "need_2_players": "⚠️ Game shuru karne ke liye kam se kam 2 players chahiye!",
        "game_started": "🎮 **Game shuru ho gaya hai! Khelna start karein!**",
        "game_killed": "🛑 **Game forcefully band kar diya gaya hai!**",
        "no_kill": "⚠️ Kill karne ke liye koi game chal hi nahi raha.",
        "only_creator_kick": "⚠️ Sirf game banane wala hi kisi ko nikaal (kick) sakta hai.",
        "reply_to_kick": "⚠️ Jise nikalna hai uske message par reply karein.",
        "kicked": "👢 {name} ko game se nikaal diya gaya hai.",
        "skipped": "⏭️ {name} ne bahut time lagaya isliye uski baari skip kar di gayi! (Forced draw)",
        "not_active": "⚠️ Game abhi chal nahi raha hai!",
        "ur_cards_title": "🃏 AAPKE CARDS:\n\n{cards}",
        "cant_play_cheat": "🚫 {name}, aap ye card abhi nahi khel sakte!",
        "not_ur_turn": "⚠️ Ye aapki baari nahi hai {name}!",
        "wild_played": "🌈 **{name} ne WILD CARD khela hai!**\nNaya color chunein:",
        "won_game": "🎉 **{name} UNO JEET GAYA HAI!** 🏆",
        "drew_card": "📥 Aapne ek naya card nikala!",
        "wait_turn": "⚠️ Apni baari ka intezaar karein!",
        "table_text": "🃏 **UNO TABLE**\n\n🎨 **Current Color:** {color}\n🎯 **Top Card:** {card}\n\n👥 **Players:**\n{players}\n\n⏳ *Aapke paas khelne ke liye 90 seconds hain!*"
    }
}

async def get_user_lang(user_id):
    if user_id in user_langs_cache: return user_langs_cache[user_id]
    if MONGO_URL:
        u = await user_settings_col.find_one({"user_id": user_id})
        if u and "lang" in u:
            user_langs_cache[user_id] = u["lang"]
            return u["lang"]
    return "en_US"

async def _t(user_id, key, **kwargs):
    lang = await get_user_lang(user_id)
    if lang not in TRANSLATIONS: lang = "en_US"
    text = TRANSLATIONS[lang].get(key, TRANSLATIONS["en_US"].get(key, key))
    if kwargs:
        try: return text.format(**kwargs)
        except: return text
    return text

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
    color = parts[1]; v = " ".join(parts[2:])
    if "Skip" in v: return f"{color}_Skip"
    if "Reverse" in v: return f"{color}_Reverse"
    if "➕2" in v or "+2" in v: return f"{color}_Draw_2"
    return f"{color}_{parts[2]}"

# ==========================================
# 👑 HIDDEN OWNER COMMANDS 
# ==========================================
@app.on_message(filters.command("users") & filters.user(OWNER_ID))
async def users_cmd(client, message):
    await message.reply(f"📊 **Bot Statistics:**\n\n👤 Total Groups & Users: `{len(get_chats())}`")

@app.on_message(filters.command("groups") & filters.user(OWNER_ID))
async def groups_cmd(client, message):
    chats = get_chats()
    if not chats: return await message.reply("❌ Database is empty!")
    m = await message.reply(f"📂 Fetching details for {len(chats)} chats...")
    text = "📋 **Connected Groups List:**\n\n"
    for chat_id in chats:
        try:
            chat = await client.get_chat(int(chat_id))
            title = chat.title or chat.first_name or "Unknown"
            username = f"@{chat.username}" if chat.username else f"ID: `{chat.id}`"
            text += f"• **{title}** ({username})\n\n"
        except: text += f"• ID: `{chat_id}` (Details Failed)\n\n"
    if len(text) > 4000:
        with open("groups_list.txt", "w", encoding="utf-8") as f: f.write(text)
        await message.reply_document("groups_list.txt", caption="📂 File generated."); await m.delete()
    else: await m.edit(text)

@app.on_message(filters.command("gcast") & filters.user(OWNER_ID))
async def gcast_cmd(client, message):
    replied = message.reply_to_message
    if not replied: return await message.reply("⚠️ Puraane kisi message par reply karke `/gcast` likho!")
    chats = get_chats()
    if not chats: return await message.reply("❌ Database is empty!")
    m = await message.reply(f"🚀 **Broadcasting exactly same message to {len(chats)} chats...**")
    success, failed = 0, 0
    for chat in chats:
        try:
            await replied.copy(int(chat)) 
            success += 1
            await asyncio.sleep(0.2)
        except: failed += 1
    await m.edit(f"✅ **Broadcast Completed!**\n\n🎯 Success: `{success}`\n❌ Failed: `{failed}`")

@app.on_message(filters.command("setposition") & filters.user(OWNER_ID))
async def set_position_cmd(client, message):
    if not MONGO_URL: return await message.reply("⚠️ Database connected nahi hai!")
    args = message.command
    if len(args) != 3: return await message.reply("⚠️ Format: `/setposition <user_id> <wins>`")
    try:
        user_id = int(args[1]); wins = int(args[2])
        try: name = (await app.get_users(user_id)).first_name
        except: name = "Hidden Player"
        await uno_stats_col.update_one({"user_id": user_id}, {"$set": {"wins": wins, "name": name}}, upsert=True)
        await message.reply(f"✅ Update Done!\n👤 **Player:** {name}\n🏆 **Wins Set To:** `{wins}`")
    except: await message.reply("⚠️ User ID and Wins should be numbers!")


# ==========================================
# ⚙️ SETTINGS, STATS, HELP & MODES (RULES)
# ==========================================
@app.on_message(filters.command("help"))
async def help_cmd(client, message):
    add_chat(message.chat.id)
    text = await _t(message.from_user.id, "help", bot=BOT_USERNAME)
    await message.reply(text)

@app.on_message(filters.command(["modes", "rules"]))
async def modes_cmd(client, message):
    add_chat(message.chat.id)
    text = await _t(message.from_user.id, "modes_text")
    await message.reply(text)

@app.on_message(filters.command("settings") & filters.private)
async def settings_cmd(client, message):
    add_chat(message.chat.id)
    text = await _t(message.from_user.id, "settings")
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Enable statistics", callback_data="enable_stats")],
        [InlineKeyboardButton("🌍 Language", callback_data="change_lang")]
    ])
    await message.reply(text, reply_markup=kb)

@app.on_message(filters.command("stats"))
async def stats_cmd(client, message):
    add_chat(message.chat.id)
    if not MONGO_URL: return await message.reply(await _t(message.from_user.id, "db_error"))
    stats = await uno_stats_col.find_one({"user_id": message.from_user.id})
    if not stats: return await message.reply(await _t(message.from_user.id, "stats_disabled"))
    
    wins = stats.get("wins", 0)
    text = await _t(message.from_user.id, "stats_msg", name=message.from_user.first_name, wins=wins, percent='100' if wins>0 else '0', cards=(wins*15)+random.randint(10,50) if wins>0 else 0)
    await message.reply(text)

@app.on_message(filters.command("topplayers"))
async def top_players_cmd(client, message):
    if not MONGO_URL: return await message.reply("⚠️ Database is not connected!")
    m = await message.reply("🏆 Fetching Leaderboard...")
    top_players = await uno_stats_col.find().sort("wins", -1).limit(10).to_list(10)
    if not top_players: return await m.edit("😔 No one has won a game yet!")
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
    if MONGO_URL: await uno_stats_col.update_one({"user_id": cb.from_user.id}, {"$set": {"name": cb.from_user.first_name}}, upsert=True)
    await cb.message.edit(await _t(cb.from_user.id, "enabled_stats"))

@app.on_callback_query(filters.regex("^change_lang$"))
async def cb_change_lang(client, cb):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("en_US - 🇺🇸 English (US)", callback_data="lang_en_US")],
        [InlineKeyboardButton("hi_IN - 🇮🇳 Hindi", callback_data="lang_hi_IN")]
    ])
    await cb.message.edit("Select locale / Bhasha chunein:", reply_markup=kb)

@app.on_callback_query(filters.regex(r"^lang_"))
async def cb_set_lang(client, cb):
    lang_code = cb.data.replace("lang_", "")
    user_langs_cache[cb.from_user.id] = lang_code
    if MONGO_URL: await user_settings_col.update_one({"user_id": cb.from_user.id}, {"$set": {"lang": lang_code}}, upsert=True)
    await cb.answer("Updated!", show_alert=False)
    await cb.message.edit(await _t(cb.from_user.id, "lang_saved"))


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

async def send_uno_table(chat_id, action_user_id=None):
    game = uno_games.get(chat_id)
    if not game or game["status"] != "playing": return
    
    uid = action_user_id if action_user_id else game["creator"]
    current_player = game["players"][game["turn_index"]]
    players_text = "\n".join([f"{'👉' if p['id'] == current_player['id'] else '👤'} {p['name']} - {len(p['cards'])} cards" for p in game["players"]])
    
    text = await _t(uid, "table_text", color=game['current_color'], card=game['top_card'], players=players_text)
            
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
    uid = message.from_user.id
    add_chat(chat_id)
    if chat_id in uno_games:
        return await message.reply(await _t(uid, "already_playing"))
    player = {"id": uid, "name": message.from_user.first_name, "cards": []}
    uno_games[chat_id] = {"status": "lobby", "creator": uid, "is_open": True, "players": [player], "lobby_msg": None}
    await message.reply(await _t(uid, "new_lobby"))

@app.on_message(filters.command("join") & filters.group)
async def join_game_cmd(client, message):
    chat_id = message.chat.id
    uid = message.from_user.id
    add_chat(chat_id)
    if chat_id not in uno_games or uno_games[chat_id]["status"] != "lobby":
        return await message.reply(await _t(uid, "no_lobby"))
    if not uno_games[chat_id]["is_open"]:
        return await message.reply(await _t(uid, "lobby_closed_err"))
        
    players = uno_games[chat_id]["players"]
    if any(p["id"] == uid for p in players): 
        return await message.reply(await _t(uid, "already_joined"))
        
    players.append({"id": uid, "name": message.from_user.first_name, "cards": []})
    await message.reply(await _t(uid, "joined_success", name=message.from_user.first_name, count=len(players)))

@app.on_message(filters.command("leave") & filters.group)
async def leave_game_cmd(client, message):
    chat_id = message.chat.id
    uid = message.from_user.id
    if chat_id not in uno_games: return
    game = uno_games[chat_id]
    
    player_idx = next((i for i, p in enumerate(game["players"]) if p["id"] == uid), None)
    if player_idx is None: return await message.reply(await _t(uid, "not_in_game"))
    
    leaving_player = game["players"].pop(player_idx)
    await message.reply(await _t(uid, "left_game", name=leaving_player['name']))
    
    if len(game["players"]) < 2 and game["status"] == "playing":
        uno_games.pop(chat_id, None)
        await app.send_message(chat_id, await _t(uid, "not_enough_players"))
    elif game["status"] == "playing" and game["turn_index"] == player_idx:
        get_next_turn(game)
        await send_uno_table(chat_id, uid)

@app.on_message(filters.command("close") & filters.group)
async def close_lobby_cmd(client, message):
    chat_id = message.chat.id
    uid = message.from_user.id
    if chat_id in uno_games and uno_games[chat_id]["creator"] == uid:
        uno_games[chat_id]["is_open"] = False
        await message.reply(await _t(uid, "lobby_closed"))

@app.on_message(filters.command("open") & filters.group)
async def open_lobby_cmd(client, message):
    chat_id = message.chat.id
    uid = message.from_user.id
    if chat_id in uno_games and uno_games[chat_id]["creator"] == uid:
        uno_games[chat_id]["is_open"] = True
        await message.reply(await _t(uid, "lobby_opened"))

@app.on_message(filters.command("start") & filters.group)
async def start_game_cmd(client, message):
    chat_id = message.chat.id
    uid = message.from_user.id
    if chat_id not in uno_games or uno_games[chat_id]["status"] != "lobby":
        return await message.reply(await _t(uid, "start_error"))
        
    game = uno_games[chat_id]
    if len(game["players"]) < 2:
        return await message.reply(await _t(uid, "need_2_players"))
        
    game["status"] = "playing"
    deck = get_uno_deck()
    for p in game["players"]: p["cards"] = [deck.pop() for _ in range(7)]
    top_card = deck.pop()
    while "Wild" in top_card or "Reverse" in top_card or "Skip" in top_card or "➕2" in top_card:
        deck.append(top_card); random.shuffle(deck); top_card = deck.pop()
    
    game["deck"] = deck; game["top_card"] = top_card; game["current_color"] = top_card.split(" ")[1]
    game["turn_index"] = 0; game["direction"] = 1; game["turn_id"] = 1  
    
    await message.reply(await _t(uid, "game_started"))
    await send_uno_table(chat_id, uid)

@app.on_message(filters.command("kill") & filters.group)
async def kill_game_cmd(client, message):
    chat_id = message.chat.id
    uid = message.from_user.id
    if chat_id in uno_games:
        uno_games.pop(chat_id, None)
        await message.reply(await _t(uid, "game_killed"))
    else: await message.reply(await _t(uid, "no_kill"))

@app.on_message(filters.command("kick") & filters.group)
async def kick_player_cmd(client, message):
    chat_id = message.chat.id
    uid = message.from_user.id
    if chat_id not in uno_games: return
    game = uno_games[chat_id]
    
    if uid != game["creator"]:
        return await message.reply(await _t(uid, "only_creator_kick"))
    if not message.reply_to_message:
        return await message.reply(await _t(uid, "reply_to_kick"))
        
    target_id = message.reply_to_message.from_user.id
    player_idx = next((i for i, p in enumerate(game["players"]) if p["id"] == target_id), None)
    
    if player_idx is not None:
        kicked = game["players"].pop(player_idx)
        await message.reply(await _t(uid, "kicked", name=kicked['name']))
        if len(game["players"]) < 2 and game["status"] == "playing":
            uno_games.pop(chat_id, None)
            await app.send_message(chat_id, await _t(uid, "not_enough_players"))
        elif game["status"] == "playing" and game["turn_index"] == player_idx:
            get_next_turn(game); await send_uno_table(chat_id, uid)

@app.on_message(filters.command("skip") & filters.group)
async def skip_player_cmd(client, message):
    chat_id = message.chat.id
    uid = message.from_user.id
    if chat_id not in uno_games or uno_games[chat_id]["status"] != "playing": return
    game = uno_games[chat_id]
    
    player = game["players"][game["turn_index"]]
    if not game["deck"]: game["deck"] = get_uno_deck()
    player["cards"].append(game["deck"].pop())
    
    await message.reply(await _t(uid, "skipped", name=player['name']))
    get_next_turn(game)
    await send_uno_table(chat_id, uid)

# ==========================================
# 🃏 INLINE PLAYING MECHANICS
# ==========================================
@app.on_callback_query(filters.regex("^show_uno_cards$"))
async def show_uno_cards_cb(client, cb):
    chat_id = cb.message.chat.id; uid = cb.from_user.id
    if chat_id not in uno_games or uno_games[chat_id]["status"] != "playing": 
        return await cb.answer(await _t(uid, "not_active"), show_alert=True)
    player = next((p for p in uno_games[chat_id]["players"] if p["id"] == uid), None)
    if not player: return await cb.answer(await _t(uid, "not_in_game"), show_alert=True)
    cards_text = "\n".join(player["cards"]); 
    await cb.answer(await _t(uid, "ur_cards_title", cards=cards_text), show_alert=True)

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
    uid = message.from_user.id
    m = await message.reply(await _t(uid, "cant_play_cheat", name=f"[{message.from_user.first_name}](tg://user?id={uid})"))
    asyncio.create_task(delayed_delete(m, 4))

@app.on_message(filters.regex(r"🃏 \[UNO\] Played: (.*)\n\nChatID: (-\d+)\nCardIndex: (\d+)"))
async def catch_uno_play(client, message):
    try: await message.delete()
    except: pass
    match = message.matches[0]; card, chat_id, card_index = match.group(1), int(match.group(2)), int(match.group(3))
    uid = message.from_user.id

    if chat_id not in uno_games or uno_games[chat_id]["status"] != "playing": return
    game = uno_games[chat_id]
    
    if game["players"][game["turn_index"]]["id"] != uid:
        m = await app.send_message(chat_id, await _t(uid, "not_ur_turn", name=f"[{message.from_user.first_name}](tg://user?id={uid})"))
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
        game["table_msg"] = await app.send_message(chat_id, await _t(uid, "wild_played", name=player['name']), reply_markup=kb)
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
        return await app.send_message(chat_id, await _t(uid, "won_game", name=f"[{winner_name}](tg://user?id={winner_id})"))

    get_next_turn(game); await send_uno_table(chat_id, uid)

@app.on_callback_query(filters.regex(r"^unocolor_(.*)$"))
async def choose_color_cb(client, cb):
    chat_id = cb.message.chat.id; uid = cb.from_user.id
    if chat_id not in uno_games or uno_games[chat_id]["status"] != "waiting_color": return
    game = uno_games[chat_id]
    if game["players"][game["turn_index"]]["id"] != uid: return await cb.answer(await _t(uid, "wait_turn"), show_alert=True)
        
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
        return await app.send_message(chat_id, await _t(uid, "won_game", name=f"[{winner_name}](tg://user?id={winner_id})"))
        
    get_next_turn(game); await cb.message.delete(); await send_uno_table(chat_id, uid)

@app.on_callback_query(filters.regex("^uno_draw$"))
async def uno_draw_cb(client, cb):
    chat_id = cb.message.chat.id; uid = cb.from_user.id
    if chat_id not in uno_games or uno_games[chat_id]["status"] != "playing": return
    game = uno_games[chat_id]
    if game["players"][game["turn_index"]]["id"] != uid: return await cb.answer(await _t(uid, "wait_turn"), show_alert=True)
        
    if not game["deck"]: game["deck"] = get_uno_deck()
    drawn = game["deck"].pop(); game["players"][game["turn_index"]]["cards"].append(drawn)
    await cb.answer(await _t(uid, "drew_card"), show_alert=True)
    get_next_turn(game); await send_uno_table(chat_id, uid)

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
            BotCommand("modes", "Explanation of game modes"),
            BotCommand("settings", "Language and other settings"),
            BotCommand("stats", "Show statistics"),
            BotCommand("topplayers", "Global Leaderboard")
        ])
    except Exception as e: print("Could not set commands:", e)
    
    print("=========================================")
    print("✅ PRO UNO BOT ENGINE IS LIVE!")
    print("=========================================")
    await idle()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
