import logging
import asyncio
import os
import time
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
    return "<h1>🤖 PRO UNO Bot is Alive (Auto-Delete Commands Edition)! 🚀</h1>"

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
# 🌍 TRANSLATION ENGINE
# ==========================================
TRANSLATIONS = {
    "en_US": {
        "help": "> 💡 **ᴜɴᴏ ʙᴏᴛ ɢᴜɪᴅᴇ:**\n>\n> 1️⃣ ᴀᴅᴅ ᴛʜɪꜱ ʙᴏᴛ ᴛᴏ ᴀ ɢʀᴏᴜᴘ.\n> 2️⃣ ꜱᴛᴀʀᴛ ᴀ ɴᴇᴡ ɢᴀᴍᴇ ᴡɪᴛʜ /startgame ᴏʀ /new.\n> 3️⃣ ᴄʟɪᴄᴋ ᴛʜᴇ 'ᴊᴏɪɴ ɢᴀᴍᴇ' ʙᴜᴛᴛᴏɴ. ɢᴀᴍᴇ ꜱᴛᴀʀᴛꜱ ᴀᴜᴛᴏᴍᴀᴛɪᴄᴀʟʟʏ ᴀꜰᴛᴇʀ 45ꜱ!\n> 4️⃣ ᴛʏᴘᴇ @{bot} ɪɴᴛᴏ ʏᴏᴜʀ ᴄʜᴀᴛ ʙᴏx ᴀɴᴅ ʜɪᴛ ꜱᴘᴀᴄᴇ. ʏᴏᴜ ᴡɪʟʟ ꜱᴇᴇ ʏᴏᴜʀ ᴄᴀʀᴅꜱ. (ɢʀᴇʏᴇᴅ ᴏᴜᴛ = ᴄᴀɴɴᴏᴛ ᴘʟᴀʏ).\n>\n> ⚙️ **ꜱᴇᴛᴛɪɴɢꜱ ᴀɴᴅ ʀᴜʟᴇꜱ:**\n> ➥ /rules : ᴇxᴘʟᴀɴᴀᴛɪᴏɴ ᴏꜰ ɢᴀᴍᴇ ʀᴜʟᴇꜱ\n> ➥ /settings : ʟᴀɴɢᴜᴀɢᴇ ᴀɴᴅ ꜱᴛᴀᴛꜱ ꜱᴇᴛᴛɪɴɢꜱ",
        "rules_text": "> 🃏 **ᴜɴᴏ ɢᴀᴍᴇ ʀᴜʟᴇꜱ & ᴍᴏᴅᴇꜱ:**\n>\n> 🔴 **ᴄʟᴀꜱꜱɪᴄ ᴜɴᴏ:**\n> ➥ ᴍᴀᴛᴄʜ ᴛʜᴇ ᴛᴏᴘ ᴄᴀʀᴅ ʙʏ ᴄᴏʟᴏʀ ᴏʀ ɴᴜᴍʙᴇʀ.\n> ➥ ᴘʟᴀʏ ꜱᴘᴇᴄɪᴀʟ ᴄᴀʀᴅꜱ (ꜱᴋɪᴘ, ʀᴇᴠᴇʀꜱᴇ, ᴅʀᴀᴡ 2) ᴛᴏ ᴅɪꜱʀᴜᴘᴛ ᴏᴘᴘᴏɴᴇɴᴛꜱ.\n> 🌈 ᴡɪʟᴅ ᴄᴀʀᴅꜱ ᴄᴀɴ ᴄʜᴀɴɢᴇ ᴛʜᴇ ᴄᴜʀʀᴇɴᴛ ᴄᴏʟᴏʀ.\n> 💥 ᴡɪʟᴅ +4 ᴄʜᴀɴɢᴇꜱ ᴛʜᴇ ᴄᴏʟᴏʀ ᴀɴᴅ ꜰᴏʀᴄᴇꜱ ᴛʜᴇ ɴᴇxᴛ ᴘʟᴀʏᴇʀ ᴛᴏ ᴅʀᴀᴡ 4 ᴄᴀʀᴅꜱ.\n> 📥 ɪꜰ ʏᴏᴜ ᴄᴀɴ'ᴛ ᴘʟᴀʏ ᴀɴʏ ᴄᴀʀᴅ, ʏᴏᴜ ᴍᴜꜱᴛ ᴄʟɪᴄᴋ 'ᴅʀᴀᴡ' ᴛᴏ ᴘɪᴄᴋ ᴀ ᴄᴀʀᴅ.\n> 🏆 ᴛʜᴇ ꜰɪʀꜱᴛ ᴘʟᴀʏᴇʀ ᴛᴏ ɢᴇᴛ ʀɪᴅ ᴏꜰ ᴀʟʟ ᴛʜᴇɪʀ ᴄᴀʀᴅꜱ ᴡɪɴꜱ!\n>\n> ⏳ **ᴀꜰᴋ ʀᴜʟᴇ (ᴀᴜᴛᴏ-ᴋɪᴄᴋ):**\n> ɪꜰ ʏᴏᴜ ᴛᴀᴋᴇ ᴍᴏʀᴇ ᴛʜᴀɴ 60 ꜱᴇᴄᴏɴᴅꜱ, ʏᴏᴜ ᴀʀᴇ ꜱᴋɪᴘᴘᴇᴅ ᴀɴᴅ ᴅʀᴀᴡ ᴀ ᴄᴀʀᴅ (1ꜱᴛ ᴛɪᴍᴇ). ɪꜰ ʏᴏᴜ ᴅᴏ ɪᴛ ᴀɢᴀɪɴ, ʏᴏᴜ ᴀʀᴇ ᴀᴜᴛᴏᴍᴀᴛɪᴄᴀʟʟʏ ᴋɪᴄᴋᴇᴅ ꜰʀᴏᴍ ᴛʜᴇ ɢᴀᴍᴇ!",
        "settings": "> ⚙️ **ꜱᴇᴛᴛɪɴɢꜱ:**\n> ᴄʜᴏᴏꜱᴇ ᴀɴ ᴏᴘᴛɪᴏɴ ʙᴇʟᴏᴡ ᴛᴏ ᴜᴘᴅᴀᴛᴇ ʏᴏᴜʀ ᴘʀᴇꜰᴇʀᴇɴᴄᴇꜱ.",
        "stats_disabled": "> ⚠️ ʏᴏᴜ ᴅɪᴅ ɴᴏᴛ ᴇɴᴀʙʟᴇ ꜱᴛᴀᴛɪꜱᴛɪᴄꜱ. ᴜꜱᴇ /settings ᴛᴏ ᴇɴᴀʙʟᴇ ᴛʜᴇᴍ.",
        "stats_msg": "> 📊 **{name}'ꜱ ᴜɴᴏ ꜱᴛᴀᴛꜱ:**\n>\n> 🏆 ɢᴀᴍᴇꜱ ᴡᴏɴ : `{wins}`\n> 🥇 ꜰɪʀꜱᴛ ᴘʟᴀᴄᴇꜱ : `{percent}%`\n> 🃏 ᴄᴀʀᴅꜱ ᴘʟᴀʏᴇᴅ : `{cards}`",
        "rank_msg": "> 🎖️ **{name}'ꜱ ᴜɴᴏ ʀᴀɴᴋ:**\n>\n> 🌐 **ɢʟᴏʙᴀʟ ʀᴀɴᴋ:** `#{rank}`\n> 🏆 **ᴛᴏᴛᴀʟ ᴡɪɴꜱ:** `{wins}`",
        "no_rank": "> 😔 {name}, ʏᴏᴜ ʜᴀᴠᴇ ɴᴏᴛ ᴡᴏɴ ᴀɴʏ ɢᴀᴍᴇꜱ ʏᴇᴛ ᴏʀ ꜱᴛᴀᴛꜱ ᴀʀᴇ ᴅɪꜱᴀʙʟᴇᴅ! ᴘʟᴀʏ ᴀ ɢᴀᴍᴇ ᴛᴏ ɢᴇᴛ ᴀ ʀᴀɴᴋ.",
        "db_error": "> ⚠️ ᴅᴀᴛᴀʙᴀꜱᴇ ɴᴏᴛ ᴄᴏɴɴᴇᴄᴛᴇᴅ.",
        "enabled_stats": "> ✅ ᴇɴᴀʙʟᴇᴅ ꜱᴛᴀᴛɪꜱᴛɪᴄꜱ!",
        "lang_saved": "> ✅ ʟᴀɴɢᴜᴀɢᴇ ᴘʀᴇꜰᴇʀᴇɴᴄᴇꜱ ꜱᴀᴠᴇᴅ ᴛᴏ ᴇɴɢʟɪꜱʜ.",
        "already_playing": "> ⚠️ ᴀ ɢᴀᴍᴇ ɪꜱ ᴀʟʀᴇᴀᴅʏ ɪɴ ᴘʀᴏɢʀᴇꜱꜱ ᴏʀ ʟᴏʙʙʏ ɪꜱ ᴏᴘᴇɴ! ᴜꜱᴇ /kill ᴛᴏ ꜱᴛᴏᴘ ɪᴛ.",
        "new_lobby": "> 🃏 **ᴜɴᴏ ɢᴀᴍᴇ ʟᴏʙʙʏ ꜱᴛᴀʀᴛᴇᴅ!**\n>\n> ⏳ ᴛɪᴍᴇ ʟᴇꜰᴛ: {time}\n>\n> 👥 ᴘʟᴀʏᴇʀꜱ ᴊᴏɪɴᴇᴅ ({count}):\n{players}",
        "timer_30": "> ⏳ **30 Seconds left!** Join fast!",
        "timer_15": "> ⏳ **15 Seconds left!**",
        "timer_5": "> ⏳ **5 Seconds left!** Get ready!",
        "join_btn": "🎮 ᴊᴏɪɴ ɢᴀᴍᴇ ({count})",
        "already_joined_alert": "⚠️ ʏᴏᴜ ʜᴀᴠᴇ ᴀʟʀᴇᴀᴅʏ ᴊᴏɪɴᴇᴅ!",
        "joined_alert": "✅ ʏᴏᴜ ᴊᴏɪɴᴇᴅ ᴛʜᴇ ɢᴀᴍᴇ!",
        "lobby_closed_alert": "⚠️ ʟᴏʙʙʏ ɪꜱ ᴄʟᴏꜱᴇᴅ ᴏʀ ɢᴀᴍᴇ ꜱᴛᴀʀᴛᴇᴅ!",
        "not_in_game": "> ⚠️ ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ɪɴ ᴛʜᴇ ɢᴀᴍᴇ.",
        "left_game": "> 👋 {name} ʟᴇꜰᴛ ᴛʜᴇ ɢᴀᴍᴇ.",
        "not_enough_players": "> ⚠️ ɴᴏᴛ ᴇɴᴏᴜɢʜ ᴘʟᴀʏᴇʀꜱ ʟᴇꜰᴛ. ɢᴀᴍᴇ ᴛᴇʀᴍɪɴᴀᴛᴇᴅ.",
        "not_enough_players_start": "> ⚠️ ɴᴏᴛ ᴇɴᴏᴜɢʜ ᴘʟᴀʏᴇʀꜱ (ᴍɪɴɪᴍᴜᴍ 2). ɢᴀᴍᴇ ᴄᴀɴᴄᴇʟʟᴇᴅ!",
        "game_started": "> 🎮 **ᴛʜᴇ ɢᴀᴍᴇ ʜᴀꜱ ꜱᴛᴀʀᴛᴇᴅ!**",
        "game_killed": "> 🛑 **ᴛʜᴇ ɢᴀᴍᴇ ʜᴀꜱ ʙᴇᴇɴ ᴛᴇʀᴍɪɴᴀᴛᴇᴅ!**",
        "no_kill": "> ⚠️ ɴᴏ ᴀᴄᴛɪᴠᴇ ɢᴀᴍᴇ ᴛᴏ ᴋɪʟʟ.",
        "only_creator_kick": "> ⚠️ ᴏɴʟʏ ᴛʜᴇ ɢᴀᴍᴇ ᴄʀᴇᴀᴛᴏʀ ᴄᴀɴ ᴋɪᴄᴋ ᴘʟᴀʏᴇʀꜱ.",
        "reply_to_kick": "> ⚠️ ᴘʟᴇᴀꜱᴇ ʀᴇᴘʟʏ ᴛᴏ ᴛʜᴇ ᴜꜱᴇʀ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ᴋɪᴄᴋ.",
        "kicked": "> 👢 {name} ʜᴀꜱ ʙᴇᴇɴ ᴋɪᴄᴋᴇᴅ ꜰʀᴏᴍ ᴛʜᴇ ɢᴀᴍᴇ.",
        "afk_kick": "> 👢 **bkl bhag gya {name}**",
        "afk_warn": "> ⏳ **1ꜱᴛ ᴡᴀʀɴɪɴɢ:** {name} ᴛᴏᴏᴋ ᴛᴏᴏ ʟᴏɴɢ ᴀɴᴅ ᴡᴀꜱ ꜱᴋɪᴘᴘᴇᴅ! (ꜰᴏʀᴄᴇᴅ ᴅʀᴀᴡ)",
        "afk_wild_warn": "> ⏳ **1ꜱᴛ ᴡᴀʀɴɪɴɢ:** {name} ᴅɪᴅ ɴᴏᴛ ᴄʜᴏᴏꜱᴇ ᴀ ᴄᴏʟᴏʀ. ᴅᴇꜰᴀᴜʟᴛ '🔴 ʀᴇᴅ' ꜱᴇʟᴇᴄᴛ ʜᴏ ɢᴀʏᴀ.",
        "skipped": "> ⏭️ {name} ᴡᴀꜱ ꜱᴋɪᴘᴘᴇᴅ!",
        "not_active": "⚠️ ɢᴀᴍᴇ ɪꜱ ɴᴏᴛ ᴀᴄᴛɪᴠᴇ!",
        "ur_cards_title": "🃏 ʏᴏᴜʀ ᴄᴀʀᴅꜱ:\n\n{cards}",
        "cant_play_cheat": "🚫 {name}, ʏᴏᴜ ᴄᴀɴɴᴏᴛ ᴘʟᴀʏ ᴛʜᴀᴛ ᴄᴀʀᴅ ʀɪɢʜᴛ ɴᴏᴡ!",
        "not_ur_turn": "⚠️ ɪᴛ'ꜱ ɴᴏᴛ ʏᴏᴜʀ ᴛᴜʀɴ {name}!",
        "wild_played": "> 🌈 **WILD CARD PLAYED by {name}!**\n> ᴄʜᴏᴏꜱᴇ ᴀ ɴᴇᴡ ᴄᴏʟᴏʀ:",
        "won_game": "> 🎉 **{name} HAS WON UNO!** 🏆",
        "drew_card": "📥 ʏᴏᴜ ᴅʀᴇᴡ ᴀ ᴄᴀʀᴅ!",
        "wait_turn": "⚠️ ᴡᴀɪᴛ ꜰᴏʀ ʏᴏᴜʀ ᴛᴜʀɴ!",
        "players_list": "👥 PLAYERS LIST:\n\n{players}",
        "table_text": "> 🃏 **ᴜɴᴏ ᴛᴀʙʟᴇ**\n>\n> 🎨 **ᴄᴜʀʀᴇɴᴛ ᴄᴏʟᴏʀ:** {color}\n> 🎯 **ᴛᴏᴘ ᴄᴀʀᴅ:** {card}\n>\n> 👤 **ᴄᴜʀʀᴇɴᴛ ᴛᴜʀɴ:** **{turn_name}** 👈\n>\n> ⏳ *ʏᴏᴜ ʜᴀᴠᴇ 60 ꜱᴇᴄᴏɴᴅꜱ ᴛᴏ ᴘʟᴀʏ!*"
    },
    "hi_IN": {
        "help": "> 💡 **ᴜɴᴏ ʙᴏᴛ ɢᴜɪᴅᴇ:**\n>\n> 1️⃣ ɪꜱ ʙᴏᴛ ᴋᴏ ᴋɪꜱɪ ɢʀᴏᴜᴘ ᴍᴇ ᴀᴅᴅ ᴋᴀʀᴇɪɴ.\n> 2️⃣ ɴᴀʏᴀ ɢᴀᴍᴇ ʙᴀɴᴀɴᴇ ᴋᴇ ʟɪʏᴇ /startgame ʏᴀ /new ʙʜᴇᴊᴇɪɴ.\n> 3️⃣ ɴɪᴄʜᴇ ᴅɪʏᴇ ɢᴀʏᴇ 'ᴊᴏɪɴ ɢᴀᴍᴇ' ʙᴜᴛᴛᴏɴ ᴘᴀʀ ᴄʟɪᴄᴋ ᴋᴀʀᴇɪɴ. ɢᴀᴍᴇ 45 ꜱᴇᴄ ᴍᴇ ᴀᴘɴᴇ ᴀᴀᴘ ꜱᴛᴀʀᴛ ʜᴏ ᴊᴀʏᴇɢᴀ!\n> 4️⃣ ᴀᴘɴᴇ ᴄʜᴀᴛ ʙᴏx ᴍᴇ @{bot} ʟɪᴋʜ ᴋᴀʀ ꜱᴘᴀᴄᴇ ᴅᴀʙᴀʏᴇɪɴ. ᴀᴀᴘᴋᴏ ᴀᴘɴᴇ ᴄᴀʀᴅꜱ ᴅɪᴋʜ ᴊᴀʏᴇɴɢᴇ. (ɢʀᴇʏ ᴄᴀʀᴅꜱ ɴᴀʜɪ ᴋʜᴇʟ ꜱᴀᴋᴛᴇ).\n>\n> ⚙️ **ꜱᴇᴛᴛɪɴɢꜱ ᴀᴜʀ ʀᴜʟᴇꜱ:**\n> ➥ /rules : ᴜɴᴏ ᴋʜᴇʟɴᴇ ᴋᴇ ɴɪʏᴀᴍ\n> ➥ /settings : ʟᴀɴɢᴜᴀɢᴇ ᴀᴜʀ ꜱᴛᴀᴛꜱ ꜱᴇᴛᴛɪɴɢꜱ",
        "rules_text": "> 🃏 **ᴜɴᴏ ɢᴀᴍᴇ ʀᴜʟᴇꜱ (ɴɪʏᴀᴍ):**\n>\n> 🔴 **ᴄʟᴀꜱꜱɪᴄ ᴜɴᴏ:**\n> ➥ ᴛᴏᴘ ᴄᴀʀᴅ ᴋᴇ ᴄᴏʟᴏʀ ʏᴀ ɴᴜᴍʙᴇʀ ꜱᴇ ᴍᴀᴛᴄʜ ᴋᴀʀᴛᴀ ʜᴜᴀ ᴄᴀʀᴅ ᴋʜᴇʟᴇɪɴ.\n> ➥ ᴏᴘᴘᴏɴᴇɴᴛꜱ ᴋᴏ ʀᴏᴋɴᴇ ᴋᴇ ʟɪʏᴇ ꜱᴘᴇᴄɪᴀʟ ᴄᴀʀᴅꜱ (ꜱᴋɪᴘ, ʀᴇᴠᴇʀꜱᴇ, ᴅʀᴀᴡ 2) ᴋᴀ ᴜꜱᴇ ᴋᴀʀᴇɪɴ.\n> 🌈 ᴡɪʟᴅ ᴄᴀʀᴅ ᴋʜᴇʟ ᴋᴀʀ ᴀᴀᴘ ᴄᴏʟᴏʀ ᴄʜᴀɴɢᴇ ᴋᴀʀ ꜱᴀᴋᴛᴇ ʜᴀɪɴ.\n> 💥 ᴡɪʟᴅ +4 ᴄᴏʟᴏʀ ʙʜɪ ᴄʜᴀɴɢᴇ ᴋᴀʀᴛᴀ ʜᴀɪ ᴀᴜʀ ᴀɢʟᴇ ᴘʟᴀʏᴇʀ ᴋᴏ 4 ᴄᴀʀᴅꜱ ɴɪᴋᴀʟɴᴇ ᴘᴀᴅᴛᴇ ʜᴀɪɴ.\n> 📥 ᴀɢᴀʀ ᴀᴀᴘᴋᴇ ᴘᴀᴀꜱ ᴋʜᴇʟɴᴇ ᴋᴇ ʟɪʏᴇ ᴋᴏɪ ᴠᴀʟɪᴅ ᴄᴀʀᴅ ɴᴀʜɪ ʜᴀɪ, ᴛᴏʜ 'ᴅʀᴀᴡ' ᴘᴀʀ ᴄʟɪᴄᴋ ᴋᴀʀᴋᴇ ɴᴀʏᴀ ᴄᴀʀᴅ ɴɪᴋᴀʟᴇɪɴ.\n> 🏆 ᴊᴏ ᴘʟᴀʏᴇʀ ꜱᴀʙꜱᴇ ᴘᴇʜʟᴇ ᴀᴘɴᴇ ꜱᴀᴀʀᴇ ᴄᴀʀᴅꜱ ᴋʜᴀᴛᴀᴍ ᴋᴀʀᴇɢᴀ, ᴡᴏ ᴊᴇᴇᴛᴇɢᴀ!\n>\n> ⏳ **ᴀꜰᴋ ʀᴜʟᴇ (ᴀᴜᴛᴏ-ᴋɪᴄᴋ):**\n> ᴀɢᴀʀ ᴋᴏɪ 60 ꜱᴇᴄᴏɴᴅ ᴛᴀᴋ ɴᴀʜɪ ᴋʜᴇʟᴇɢᴀ, ᴛᴏʜ 1ꜱᴛ ᴛɪᴍᴇ ᴜꜱᴇ ᴘᴇɴᴀʟᴛʏ ᴍɪʟᴇɢɪ ᴀᴜʀ ꜱᴋɪᴘ ʜᴏɢᴀ. 2ɴᴅ ᴛɪᴍᴇ ᴡᴀʜɪ ɢᴀʟᴛɪ ᴋᴀʀɴᴇ ᴘᴀʀ ᴀᴜᴛᴏᴍᴀᴛɪᴄᴀʟʟʏ ɢᴀᴍᴇ ꜱᴇ ɴɪᴋᴀᴀʟ ᴅɪʏᴀ ᴊᴀʏᴇɢᴀ!",
        "settings": "> ⚙️ **ꜱᴇᴛᴛɪɴɢꜱ (ꜱᴇᴛɪɴɢꜱ):**\n> ɴɪᴄʜᴇ ᴅɪʏᴇ ɢᴀʏᴇ ᴏᴘᴛɪᴏɴꜱ ꜱᴇ ᴀᴘɴɪ ᴘᴀꜱᴀɴᴅ ᴄʜᴜɴᴇɪɴ.",
        "stats_disabled": "> ⚠️ ᴀᴀᴘɴᴇ ꜱᴛᴀᴛɪꜱᴛɪᴄꜱ ᴏɴ ɴᴀʜɪ ᴋɪʏᴀ ʜᴀɪ. /settings ʙʜᴇᴊ ᴋᴀʀ ᴏɴ ᴋᴀʀᴇɪɴ.",
        "stats_msg": "> 📊 **{name} ᴋᴇ ᴜɴᴏ ꜱᴛᴀᴛꜱ:**\n>\n> 🏆 ɢᴀᴍᴇꜱ ᴊᴇᴇᴛᴇ : `{wins}`\n> 🥇 ꜰɪʀꜱᴛ ᴘʟᴀᴄᴇꜱ : `{percent}%`\n> 🃏 ᴄᴀʀᴅꜱ ᴋʜᴇʟᴇ : `{cards}`",
        "rank_msg": "> 🎖️ **{name} ᴋɪ ᴜɴᴏ ʀᴀɴᴋ:**\n>\n> 🌐 **ɢʟᴏʙᴀʟ ʀᴀɴᴋ:** `#{rank}`\n> 🏆 **ᴛᴏᴛᴀʟ ᴡɪɴꜱ:** `{wins}`",
        "no_rank": "> 😔 {name}, ᴀᴀᴘɴᴇ ᴀᴀʙɪ ᴛᴀᴋ ᴋᴏɪ ɢᴀᴍᴇ ɴᴀʜɪ ᴊᴇᴇᴛᴀ ʜᴀɪ ʏᴀ ꜱᴛᴀᴛꜱ ᴏɴ ɴᴀʜɪ ʜᴀɪɴ! ᴘᴇʜʟᴇ ᴇᴋ ɢᴀᴍᴇ ᴋʜᴇʟᴇɪɴ.",
        "db_error": "> ⚠️ ᴅᴀᴛᴀʙᴀꜱᴇ ᴄᴏɴɴᴇᴄᴛᴇᴅ ɴᴀʜɪ ʜᴀɪ.",
        "enabled_stats": "> ✅ ꜱᴛᴀᴛɪꜱᴛɪᴄꜱ ᴏɴ ᴋᴀʀ ᴅɪʏᴇ ɢᴀʏᴇ ʜᴀɪɴ!",
        "lang_saved": "> ✅ ɪꜱ ɢʀᴏᴜᴘ/ᴄʜᴀᴛ ᴋɪ ʙʜᴀꜱʜᴀ ʜɪɴᴅɪ ᴍᴇ ꜱᴇᴛ ᴋᴀʀ ᴅɪ ɢᴀʏɪ ʜᴀɪ.",
        "already_playing": "> ⚠️ ᴇᴋ ɢᴀᴍᴇ ᴘᴇʜʟᴇ ꜱᴇ ᴄʜᴀʟ ʀᴀʜᴀ ʜᴀɪ ʏᴀ ʟᴏʙʙʏ ᴏᴘᴇɴ ʜᴀɪ! ᴜꜱᴇ /kill ᴋᴀʀᴇɪɴ.",
        "new_lobby": "> 🃏 **ᴇᴋ ɴᴀʏᴀ ᴜɴᴏ ɢᴀᴍᴇ ʙᴀɴ ɢᴀʏᴀ ʜᴀɪ!**\n>\n> ⏳ ᴛɪᴍᴇ ʟᴇꜰᴛ: {time}\n>\n> 👥 ᴘʟᴀʏᴇʀꜱ ᴊᴏɪɴᴇᴅ ({count}):\n{players}",
        "timer_30": "> ⏳ **30 Seconds bache hain!** Jaldi join karo!",
        "timer_15": "> ⏳ **15 Seconds bache hain!**",
        "timer_5": "> ⏳ **5 Seconds bache hain!** Get ready!",
        "join_btn": "🎮 ᴊᴏɪɴ ɢᴀᴍᴇ ({count})",
        "already_joined_alert": "⚠️ ᴀᴀᴘ ᴘᴇʜʟᴇ ꜱᴇ ɢᴀᴍᴇ ᴍᴇ ʜᴀɪɴ!",
        "joined_alert": "✅ ᴀᴀᴘɴᴇ ɢᴀᴍᴇ ᴊᴏɪɴ ᴋᴀʀ ʟɪʏᴀ!",
        "lobby_closed_alert": "⚠️ ʟᴏʙʙʏ ʙᴀɴᴅ ʜᴏ ᴄʜᴜᴋɪ ʜᴀɪ!",
        "not_in_game": "> ⚠️ ᴀᴀᴘ ɪꜱ ɢᴀᴍᴇ ᴍᴇ ɴᴀʜɪ ʜᴀɪɴ.",
        "left_game": "> 👋 {name} ɢᴀᴍᴇ ᴄʜʜᴏᴅ ᴋᴀʀ ᴄʜᴀʟᴀ ɢᴀʏᴀ.",
        "not_enough_players": "> ⚠️ ᴋʜᴇʟɴᴇ ᴋᴇ ʟɪʏᴇ ʟᴏɢ ᴋᴀᴍ ʜᴀɪɴ. ɢᴀᴍᴇ ᴋʜᴀᴛᴀᴍ ᴋᴀʀ ᴅɪʏᴀ ɢᴀʏᴀ.",
        "not_enough_players_start": "> ⚠️ ᴋᴀᴍ ꜱᴇ ᴋᴀᴍ 2 ᴘʟᴀʏᴇʀꜱ ᴄʜᴀʜɪʏᴇ! ɢᴀᴍᴇ ᴄᴀɴᴄᴇʟʟᴇᴅ.",
        "game_started": "> 🎮 **ɢᴀᴍᴇ ꜱʜᴜʀᴜ ʜᴏ ɢᴀʏᴀ ʜᴀɪ!**",
        "game_killed": "> 🛑 **ɢᴀᴍᴇ ꜰᴏʀᴄᴇꜰᴜʟʟʏ ʙᴀɴᴅ ᴋᴀʀ ᴅɪʏᴀ ɢᴀʏᴀ ʜᴀɪ!**",
        "no_kill": "> ⚠️ ᴋɪʟʟ ᴋᴀʀɴᴇ ᴋᴇ ʟɪʏᴇ ᴋᴏɪ ɢᴀᴍᴇ ɴᴀʜɪ ᴄʜᴀʟ ʀᴀʜᴀ.",
        "only_creator_kick": "> ⚠️ ꜱɪʀꜰ ɢᴀᴍᴇ ʙᴀɴᴀɴᴇ ᴡᴀʟᴀ ʜɪ ᴋɪᴄᴋ ᴋᴀʀ ꜱᴀᴋᴛᴀ ʜᴀɪ.",
        "reply_to_kick": "> ⚠️ ᴊɪꜱᴇ ɴɪᴋᴀʟɴᴀ ʜᴀɪ ᴜꜱᴋᴇ ᴍᴇꜱꜱᴀɢᴇ ᴘᴀʀ ʀᴇᴘʟʏ ᴋᴀʀᴇɪɴ.",
        "kicked": "> 👢 {name} ᴋᴏ ɢᴀᴍᴇ ꜱᴇ ɴɪᴋᴀᴀʟ ᴅɪʏᴀ ɢᴀʏᴀ ʜᴀɪ.",
        "afk_kick": "> 👢 **bkl bhag gya {name}**",
        "afk_warn": "> ⏳ **1ꜱᴛ ᴡᴀʀɴɪɴɢ:** {name} ɴᴇ ʙᴀʜᴜᴛ ᴛɪᴍᴇ ʟᴀɢᴀʏᴀ ɪꜱʟɪʏᴇ ꜱᴋɪᴘ ᴋᴀʀ ᴅɪʏᴀ ɢᴀʏᴀ! (ꜰᴏʀᴄᴇᴅ ᴅʀᴀᴡ)",
        "afk_wild_warn": "> ⏳ **1ꜱᴛ ᴡᴀʀɴɪɴɢ:** {name} ɴᴇ ᴋᴏɪ ᴄᴏʟᴏʀ ɴᴀʜɪ ᴄʜᴜɴᴀ. ᴅᴇꜰᴀᴜʟᴛ '🔴 ʀᴇᴅ' ꜱᴇʟᴇᴄᴛ ʜᴏ ɢᴀʏᴀ.",
        "skipped": "> ⏭️ {name} ᴋɪ ʙᴀᴀʀɪ ꜱᴋɪᴘ ᴋᴀʀ ᴅɪ ɢᴀʏɪ! (ꜰᴏʀᴄᴇᴅ ᴅʀᴀᴡ)",
        "not_active": "⚠️ ɢᴀᴍᴇ ᴀʙʜɪ ᴄʜᴀʟ ɴᴀʜɪ ʀᴀʜᴀ ʜᴀɪ!",
        "ur_cards_title": "🃏 ᴀᴀᴘᴋᴇ ᴄᴀʀᴅꜱ:\n\n{cards}",
        "cant_play_cheat": "🚫 {name}, ᴀᴀᴘ ʏᴇ ᴄᴀʀᴅ ᴀʙʜɪ ɴᴀʜɪ ᴋʜᴇʟ ꜱᴀᴋᴛᴇ!",
        "not_ur_turn": "⚠️ ʏᴇ ᴀᴀᴘᴋɪ ʙᴀᴀʀɪ ɴᴀʜɪ ʜᴀɪ {name}!",
        "wild_played": "> 🌈 **WILD CARD PLAYED by {name}!**\n> ɴᴀʏᴀ ᴄᴏʟᴏʀ ᴄʜᴜɴᴇɪɴ:",
        "won_game": "> 🎉 **{name} UNO JEET GAYA HAI!** 🏆",
        "drew_card": "📥 ᴀᴀᴘɴᴇ ᴇᴋ ɴᴀʏᴀ ᴄᴀʀᴅ ɴɪᴋᴀʟᴀ!",
        "wait_turn": "⚠️ ᴀᴘɴɪ ʙᴀᴀʀɪ ᴋᴀ ɪɴᴛᴇᴢᴀᴀʀ ᴋᴀʀᴇɪɴ!",
        "players_list": "👥 PLAYERS LIST:\n\n{players}",
        "table_text": "> 🃏 **ᴜɴᴏ ᴛᴀʙʟᴇ**\n>\n> 🎨 **ᴄᴜʀʀᴇɴᴛ ᴄᴏʟᴏʀ:** {color}\n> 🎯 **ᴛᴏᴘ ᴄᴀʀᴅ:** {card}\n>\n> 👤 **ᴄᴜʀʀᴇɴᴛ ᴛᴜʀɴ:** **{turn_name}** 👈\n>\n> ⏳ *ᴀᴀᴘᴋᴇ ᴘᴀᴀꜱ ᴋʜᴇʟɴᴇ ᴋᴇ ʟɪʏᴇ 60 ꜱᴇᴄᴏɴᴅꜱ ʜᴀɪɴ!*"
    }
}

async def get_lang(uid):
    if uid in user_langs_cache: return user_langs_cache[uid]
    if MONGO_URL:
        u = await user_settings_col.find_one({"user_id": uid})
        if u and "lang" in u:
            user_langs_cache[uid] = u["lang"]
            return u["lang"]
    return "en_US"

async def _t(uid, key, **kwargs):
    lang = await get_lang(uid)
    if lang not in TRANSLATIONS: lang = "en_US"
    text = TRANSLATIONS[lang].get(key, TRANSLATIONS["en_US"].get(key, key))
    if kwargs:
        try: return text.format(**kwargs)
        except: return text
    return text

# ==========================================
# 🛠️ UTILS FOR OWNER & BOT
# ==========================================
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
            if word.startswith(('http://', 'https://', 't.me/', 'www.', '@', '/')): final_words.append(word)
            else: final_words.append(to_small_caps(word))
        final_lines.append("> " + " ".join(final_words))
    return "\n".join(final_lines)

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
# 👑 HIDDEN OWNER COMMANDS & DIRECT CAPTION /setstart
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
    m = await message.reply(f"🚀 **Broadcasting premium formatted message to {len(chats)} chats...**")
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

# 🔥 UNIVERSAL /setstart HANDLER
@app.on_message(filters.command("setstart") & filters.user(OWNER_ID) & filters.private)
async def setstart_universal_cmd(client, message):
    target_msg = message.reply_to_message if message.reply_to_message else message
    
    if not target_msg.photo:
        return await message.reply("⚠️ Kripya photo ke sath caption me `/setstart` likhein YA photo par reply karke `/setstart` likhein!")
    
    file_id = target_msg.photo.file_id
    full_caption = target_msg.caption or ""
    
    clean_text = full_caption.replace("/setstart", "").strip()
    
    buttons = []
    final_lines = []
    
    for line in clean_text.split("\n"):
        line_clean = line.strip()
        if " - " in line_clean:
            parts = line_clean.split(" - ", 1)
            btn_title = parts[0].strip()
            btn_link = parts[1].strip()
            
            if btn_link.startswith("@"):
                btn_link = f"https://t.me/{btn_link[1:]}"
            elif not btn_link.startswith(("http://", "https://", "t.me/")):
                btn_link = f"https://{btn_link}"
            elif btn_link.startswith("t.me/"):
                btn_link = f"https://{btn_link}"
                
            buttons.append({"text": btn_title, "url": btn_link})
        else:
            final_lines.append(line)
            
    text_content = "\n".join(final_lines).strip()
    
    await user_settings_col.update_one(
        {"type": "start_msg"}, 
        {"$set": {
            "has_photo": True, 
            "file_id": file_id, 
            "text": text_content, 
            "buttons": buttons[:5]
        }}, 
        upsert=True
    )
    await message.reply("✅ **Naya `/start` message (Photo + Caption + Buttons) successfully set ho gaya hai!**")


# ==========================================
# ⚙️ GENERAL COMMANDS (/start, /help, /settings...)
# ==========================================
@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    asyncio.create_task(delayed_delete(message, 5))
    add_chat(message.chat.id)
    user = message.from_user
    fname = user.first_name if user else "User"
    uname = f"@{user.username}" if user and user.username else fname
    
    default_text = (f"> 🃏 **ᴡᴇʟᴄᴏᴍᴇ ᴛᴏ ᴘʀᴏ ᴜɴᴏ ʙᴏᴛ, {uname}!**\n>\n"
                    f"> ɪ ᴀᴍ ᴀɴ ᴀᴅᴠᴀɴᴄᴇᴅ ᴜɴᴏ ɢᴀᴍᴇ ʙᴏᴛ.\n"
                    f"> ᴀᴅᴅ ᴍᴇ ᴛᴏ ʏᴏᴜʀ ɢʀᴏᴜᴘ ᴀɴᴅ ᴛʏᴘᴇ `/startgame` ᴛᴏ ꜱᴛᴀʀᴛ ᴘʟᴀʏɪɴɢ!\n>\n"
                    f"> 📚 ᴘʀᴇꜱꜱ `/rules` ᴛᴏ ᴋɴᴏᴡ ᴛʜᴇ ɢᴀᴍᴇ ʀᴜʟᴇꜱ.")
    
    if MONGO_URL:
        config = await user_settings_col.find_one({"type": "start_msg"})
        if config:
            raw_text = config.get("text", "")
            formatted_text = raw_text.replace("{name}", fname).replace("{username}", uname)
            
            kb = None
            if config.get("buttons"):
                keyboard = []
                for b in config["buttons"][:5]:
                    keyboard.append([InlineKeyboardButton(b["text"], url=b["url"])])
                kb = InlineKeyboardMarkup(keyboard)
                
            if config.get("has_photo"):
                return await message.reply_photo(photo=config["file_id"], caption=formatted_text, reply_markup=kb)
            else:
                return await message.reply(formatted_text, reply_markup=kb)
                
    formatted_default = default_text.replace("{name}", fname).replace("{username}", uname)
    await message.reply(formatted_default)

@app.on_message(filters.command("help"))
async def help_cmd(client, message):
    asyncio.create_task(delayed_delete(message, 5))
    add_chat(message.chat.id)
    uid = message.from_user.id if message.from_user else message.chat.id
    text = await _t(uid, "help", bot=BOT_USERNAME)
    await message.reply(text)

@app.on_message(filters.command("rules"))
async def rules_cmd(client, message):
    asyncio.create_task(delayed_delete(message, 5))
    add_chat(message.chat.id)
    uid = message.from_user.id if message.from_user else message.chat.id
    text = await _t(uid, "rules_text")
    await message.reply(text)

@app.on_message(filters.command("settings"))
async def settings_cmd(client, message):
    asyncio.create_task(delayed_delete(message, 5))
    add_chat(message.chat.id)
    uid = message.from_user.id if message.from_user else message.chat.id
    text = await _t(uid, "settings")
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Enable statistics", callback_data="enable_stats")],
        [InlineKeyboardButton("🌍 Language", callback_data="change_lang")]
    ])
    await message.reply(text, reply_markup=kb)

@app.on_message(filters.command("stats"))
async def stats_cmd(client, message):
    asyncio.create_task(delayed_delete(message, 5))
    add_chat(message.chat.id)
    uid = message.from_user.id if message.from_user else message.chat.id
    fname = message.from_user.first_name if message.from_user else "Admin"
    if not MONGO_URL: return await message.reply(await _t(uid, "db_error"))
    stats = await uno_stats_col.find_one({"user_id": uid})
    if not stats: return await message.reply(await _t(uid, "stats_disabled"))
    
    wins = stats.get("wins", 0)
    text = await _t(uid, "stats_msg", name=fname, wins=wins, percent='100' if wins>0 else '0', cards=(wins*15)+random.randint(10,50) if wins>0 else 0)
    await message.reply(text)

@app.on_message(filters.command("rank"))
async def rank_cmd(client, message):
    asyncio.create_task(delayed_delete(message, 5))
    add_chat(message.chat.id)
    uid = message.from_user.id if message.from_user else message.chat.id
    fname = message.from_user.first_name if message.from_user else "User"
    if not MONGO_URL: return await message.reply(await _t(uid, "db_error"))
    
    stats = await uno_stats_col.find_one({"user_id": uid})
    if not stats or stats.get("wins", 0) == 0:
        return await message.reply(await _t(uid, "no_rank", name=fname))
        
    user_wins = stats.get("wins", 0)
    higher_ranks_count = await uno_stats_col.count_documents({"wins": {"$gt": user_wins}})
    rank = higher_ranks_count + 1
    
    text = await _t(uid, "rank_msg", name=fname, rank=rank, wins=user_wins)
    await message.reply(text)

@app.on_message(filters.command("topplayers"))
async def top_players_cmd(client, message):
    asyncio.create_task(delayed_delete(message, 5))
    add_chat(message.chat.id)
    if not MONGO_URL: return await message.reply("⚠️ Database is not connected!")
    m = await message.reply("🏆 Fetching Leaderboard...")
    top_players = await uno_stats_col.find().sort("wins", -1).limit(10).to_list(10)
    if not top_players: return await m.edit("😔 No one has won a game yet!")
    text = "> 🔥 **ᴜɴᴏ ɢʟᴏʙᴀʟ ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ** 🔥\n>\n"
    for i, p in enumerate(top_players, start=1):
        name = p.get("name", "Unknown Player")
        wins = p.get("wins", 0)
        user_id = p.get("user_id")
        if i <= 3: text += f"> {i}. 🌟 **[ᴜʟᴛʀᴀ ᴘʀᴏ ᴘʟᴀʏᴇʀ - {name}](tg://user?id={user_id})** ➣ `{wins}` ᴡɪɴꜱ 👑\n"
        elif i <= 6: text += f"> {i}. 🎖 **[ᴘʀᴏ ᴘʟᴀʏᴇʀ - {name}](tg://user?id={user_id})** ➣ `{wins}` ᴡɪɴꜱ\n"
        else: text += f"> {i}. 🔰 **[ʙᴇɢɪɴɴᴇʀ ᴘʀᴏ - {name}](tg://user?id={user_id})** ➣ `{wins}` ᴡɪɴꜱ\n"
    await m.edit(text)

@app.on_callback_query(filters.regex("^enable_stats$"))
async def cb_enable_stats(client, cb):
    uid = cb.from_user.id
    if MONGO_URL: await uno_stats_col.update_one({"user_id": uid}, {"$set": {"name": cb.from_user.first_name}}, upsert=True)
    await cb.message.edit(await _t(uid, "enabled_stats"))

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
    uid = cb.from_user.id 
    user_langs_cache[uid] = lang_code
    if MONGO_URL: await user_settings_col.update_one({"user_id": uid}, {"$set": {"lang": lang_code}}, upsert=True)
    await cb.answer("Updated!", show_alert=False)
    await cb.message.edit(await _t(uid, "lang_saved"))


# ==========================================
# 🃏 UNO CORE ENGINE & TIMERS
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
    
    clickable_turn_name = f"[{current_player['name']}](tg://user?id={current_player['id']})"
    
    text = await _t(uid, "table_text", color=game['current_color'], card=game['top_card'], turn_name=clickable_turn_name)
            
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🃏 Play Card", switch_inline_query_current_chat="")],
        [InlineKeyboardButton("👀 Show Cards", callback_data="show_uno_cards"), InlineKeyboardButton("📥 Draw", callback_data="uno_draw")],
        [InlineKeyboardButton("👥 Players", callback_data="show_uno_players")]
    ])
    
    if "table_msg" in game:
        try: await game["table_msg"].delete()
        except: pass

    file_key = card_to_filename(game["top_card"]); file_id = cards_cache.get(file_key)
    try:
        if file_id: game["table_msg"] = await app.send_photo(chat_id, photo=file_id, caption=text, reply_markup=kb)
        else: game["table_msg"] = await app.send_message(chat_id, text, reply_markup=kb)
    except: game["table_msg"] = await app.send_message(chat_id, text, reply_markup=kb)

async def uno_lobby_timer(chat_id):
    game = uno_games.get(chat_id)
    if not game or game["status"] != "lobby": return
    uid = game["creator"] 
    alert_msg = None

    await asyncio.sleep(15)
    if chat_id in uno_games and uno_games[chat_id]["status"] == "lobby":
        alert_msg = await app.send_message(chat_id, await _t(uid, "timer_30"))

    await asyncio.sleep(15)
    if chat_id in uno_games and uno_games[chat_id]["status"] == "lobby":
        try: await alert_msg.delete()
        except: pass
        alert_msg = await app.send_message(chat_id, await _t(uid, "timer_15"))

    await asyncio.sleep(10)
    if chat_id in uno_games and uno_games[chat_id]["status"] == "lobby":
        try: await alert_msg.delete()
        except: pass
        alert_msg = await app.send_message(chat_id, await _t(uid, "timer_5"))

    await asyncio.sleep(5)

    if chat_id in uno_games and uno_games[chat_id]["status"] == "lobby":
        try: await alert_msg.delete()
        except: pass
        
        game = uno_games[chat_id]
        if len(game["players"]) < 2:
            uno_games.pop(chat_id, None)
            await app.send_message(chat_id, await _t(uid, "not_enough_players_start"))
            return
            
        game["status"] = "playing"
        deck = get_uno_deck()
        for p in game["players"]: 
            p["cards"] = [deck.pop() for _ in range(7)]
            p["afk_strikes"] = 0
        top_card = deck.pop()
        while "Wild" in top_card or "Reverse" in top_card or "Skip" in top_card or "➕2" in top_card:
            deck.append(top_card); random.shuffle(deck); top_card = deck.pop()
        
        game["deck"] = deck; game["top_card"] = top_card; game["current_color"] = top_card.split(" ")[1]
        game["turn_index"] = 0; game["direction"] = 1; game["turn_id"] = 1  
        
        try: await game["lobby_msg"].delete()
        except: pass
        
        await app.send_message(chat_id, await _t(uid, "game_started"))
        asyncio.create_task(uno_turn_timer(chat_id, 1))
        await send_uno_table(chat_id, uid)

async def uno_turn_timer(chat_id, turn_id):
    await asyncio.sleep(60)
    if chat_id not in uno_games: return
    game = uno_games.get(chat_id)
    if not game or game.get("turn_id") != turn_id: return
    
    try:
        player_idx = game["turn_index"]
        player = game["players"][player_idx]
        uid = player["id"] 
        
        player["afk_strikes"] = player.get("afk_strikes", 0) + 1
        
        if player["afk_strikes"] >= 2:
            kicked_name = player["name"]
            game["players"].pop(player_idx)
            kick_msg = await _t(uid, "afk_kick", name=f"[{kicked_name}](tg://user?id={player['id']})")
            await app.send_message(chat_id, kick_msg)
            
            if len(game["players"]) < 2:
                uno_games.pop(chat_id, None)
                await app.send_message(chat_id, await _t(uid, "not_enough_players"))
            else:
                if game["direction"] == -1: game["turn_index"] = (game["turn_index"] - 1) % len(game["players"])
                else: game["turn_index"] = game["turn_index"] % len(game["players"])
                game["status"] = "playing"; game["pending_effect"] = "none"; game["turn_id"] += 1
                asyncio.create_task(uno_turn_timer(chat_id, game["turn_id"]))
                await send_uno_table(chat_id, uid)
            return

        if game["status"] == "waiting_color":
            game["current_color"] = "🔴"; game["status"] = "playing"
            if game.get("pending_effect") == "+4":
                victim = game["players"][(game["turn_index"] + game["direction"]) % len(game["players"])]
                for _ in range(4):
                    if not game["deck"]: game["deck"] = get_uno_deck()
                    victim["cards"].append(game["deck"].pop())
            game["pending_effect"] = "none"
            warn_msg = await _t(uid, "afk_wild_warn", name=f"[{player['name']}](tg://user?id={player['id']})")
            await app.send_message(chat_id, warn_msg)
            get_next_turn(game)
            asyncio.create_task(uno_turn_timer(chat_id, game["turn_id"]))
            await send_uno_table(chat_id, uid)
            
        elif game["status"] == "playing":
            if not game["deck"]: game["deck"] = get_uno_deck()
            drawn = game["deck"].pop()
            player["cards"].append(drawn)
            warn_msg = await _t(uid, "afk_warn", name=f"[{player['name']}](tg://user?id={player['id']})")
            await app.send_message(chat_id, warn_msg)
            get_next_turn(game)
            asyncio.create_task(uno_turn_timer(chat_id, game["turn_id"]))
            await send_uno_table(chat_id, uid)
    except: pass

# ==========================================
# 🎮 GAME COMMANDS & LOBBY LOGIC
# ==========================================
@app.on_message(filters.command(["startgame", "new"]) & filters.group)
async def new_game_cmd(client, message):
    asyncio.create_task(delayed_delete(message, 5))
    chat_id = message.chat.id
    uid = message.from_user.id if message.from_user else message.chat.id
    fname = message.from_user.first_name if message.from_user else "Admin"
    add_chat(chat_id)
    if chat_id in uno_games:
        return await message.reply(await _t(uid, "already_playing"))
        
    player = {"id": uid, "name": fname, "cards": [], "afk_strikes": 0}
    uno_games[chat_id] = {"status": "lobby", "creator": uid, "is_open": True, "players": [player], "lobby_msg": None}
    
    players_text = f"> - {fname}"
    text = await _t(uid, "new_lobby", time="45s", count=1, players=players_text)
    
    btn_text = await _t(uid, "join_btn", count=1)
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(btn_text, callback_data="join_uno")]])
    
    m = await message.reply(text, reply_markup=kb)
    uno_games[chat_id]["lobby_msg"] = m
    
    asyncio.create_task(uno_lobby_timer(chat_id))

@app.on_callback_query(filters.regex("^join_uno$"))
async def join_uno_cb(client, cb):
    chat_id = cb.message.chat.id
    uid = cb.from_user.id
    fname = cb.from_user.first_name
    
    if chat_id not in uno_games or uno_games[chat_id]["status"] != "lobby":
        return await cb.answer(await _t(uid, "lobby_closed_alert"), show_alert=True)
        
    game = uno_games[chat_id]
    players = game["players"]
    if any(p["id"] == uid for p in players): 
        return await cb.answer(await _t(uid, "already_joined_alert"), show_alert=True)
        
    players.append({"id": uid, "name": fname, "cards": [], "afk_strikes": 0})
    await cb.answer(await _t(uid, "joined_alert"), show_alert=False)
    
    creator_id = game["creator"]
    players_text = "\n> ".join([f"- {p['name']}" for p in players])
    text = await _t(creator_id, "new_lobby", time="45s", count=len(players), players=f"> {players_text}")
    
    btn_text = await _t(creator_id, "join_btn", count=len(players))
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(btn_text, callback_data="join_uno")]])
    
    try: await cb.message.edit_text(text, reply_markup=kb)
    except: pass

@app.on_message(filters.command("leave") & filters.group)
async def leave_game_cmd(client, message):
    asyncio.create_task(delayed_delete(message, 5))
    chat_id = message.chat.id
    uid = message.from_user.id if message.from_user else message.chat.id
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

@app.on_message(filters.command(["kill", "end"]) & filters.group)
async def kill_game_cmd(client, message):
    asyncio.create_task(delayed_delete(message, 5))
    chat_id = message.chat.id
    uid = message.from_user.id if message.from_user else message.chat.id
    if chat_id in uno_games:
        uno_games.pop(chat_id, None)
        await message.reply(await _t(uid, "game_killed"))
    else: await message.reply(await _t(uid, "no_kill"))

@app.on_message(filters.command("kick") & filters.group)
async def kick_player_cmd(client, message):
    asyncio.create_task(delayed_delete(message, 5))
    chat_id = message.chat.id
    uid = message.from_user.id if message.from_user else message.chat.id
    if chat_id not in uno_games: return
    game = uno_games[chat_id]
    
    if uid != game["creator"]:
        return await message.reply(await _t(uid, "only_creator_kick"))
    if not message.reply_to_message:
        return await message.reply(await _t(uid, "reply_to_kick"))
        
    target_id = message.reply_to_message.from_user.id if message.reply_to_message.from_user else 0
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
    asyncio.create_task(delayed_delete(message, 5))
    chat_id = message.chat.id
    uid = message.from_user.id if message.from_user else message.chat.id
    if chat_id not in uno_games or uno_games[chat_id]["status"] != "playing": return
    game = uno_games[chat_id]
    
    player_idx = game["turn_index"]
    player = game["players"][player_idx]
    player["afk_strikes"] = player.get("afk_strikes", 0) + 1
    
    if player["afk_strikes"] >= 2:
        kicked_name = player["name"]
        game["players"].pop(player_idx)
        kick_msg = await _t(uid, "afk_kick", name=f"[{kicked_name}](tg://user?id={player['id']})")
        await app.send_message(chat_id, kick_msg)
        
        if len(game["players"]) < 2:
            uno_games.pop(chat_id, None)
            await app.send_message(chat_id, await _t(uid, "not_enough_players"))
        else:
            if game["direction"] == -1: game["turn_index"] = (game["turn_index"] - 1) % len(game["players"])
            else: game["turn_index"] = game["turn_index"] % len(game["players"])
            game["status"] = "playing"; game["turn_id"] += 1
            asyncio.create_task(uno_turn_timer(chat_id, game["turn_id"]))
            await send_uno_table(chat_id, uid)
    else:
        if not game["deck"]: game["deck"] = get_uno_deck()
        player["cards"].append(game["deck"].pop())
        warn_msg = await _t(uid, "afk_warn", name=f"[{player['name']}](tg://user?id={player['id']})")
        await app.send_message(chat_id, warn_msg)
        get_next_turn(game); game["turn_id"] += 1
        asyncio.create_task(uno_turn_timer(chat_id, game["turn_id"]))
        await send_uno_table(chat_id, uid)

# ==========================================
# 🃏 INLINE PLAYING MECHANICS & POPUPS
# ==========================================
@app.on_callback_query(filters.regex("^show_uno_players$"))
async def show_uno_players_cb(client, cb):
    chat_id = cb.message.chat.id
    uid = cb.from_user.id
    if chat_id not in uno_games or uno_games[chat_id]["status"] != "playing": 
        return await cb.answer(await _t(uid, "not_active"), show_alert=True)
    
    game = uno_games[chat_id]
    current_player = game["players"][game["turn_index"]]
    
    players_text = "\n".join([f"{'👉' if p['id'] == current_player['id'] else '👤'} {p['name']} - {len(p['cards'])} Cards" for p in game["players"]])
    final_text = await _t(uid, "players_list", players=players_text)
    
    if len(final_text) > 195:
        final_text = final_text[:192] + "..."
        
    await cb.answer(final_text, show_alert=True)

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
    fname = message.from_user.first_name if message.from_user else "Player"
    m = await message.reply(await _t(uid, "cant_play_cheat", name=f"[{fname}](tg://user?id={uid})"))
    asyncio.create_task(delayed_delete(m, 4))

@app.on_message(filters.regex(r"🃏 \[UNO\] Played: (.*)\n\nChatID: (-\d+)\nCardIndex: (\d+)"))
async def catch_uno_play(client, message):
    try: await message.delete()
    except: pass
    match = message.matches[0]; card, chat_id, card_index = match.group(1), int(match.group(2)), int(match.group(3))
    uid = message.from_user.id
    fname = message.from_user.first_name if message.from_user else "Player"

    if chat_id not in uno_games or uno_games[chat_id]["status"] != "playing": return
    game = uno_games[chat_id]
    
    if game["players"][game["turn_index"]]["id"] != uid:
        m = await app.send_message(chat_id, await _t(uid, "not_ur_turn", name=f"[{fname}](tg://user?id={uid})"))
        return asyncio.create_task(delayed_delete(m, 4))

    player = game["players"][game["turn_index"]]
    if card_index >= len(player["cards"]) or player["cards"][card_index] != card: return

    player["cards"].pop(card_index); game["top_card"] = card
    player["afk_strikes"] = 0 # RESET STRIKES IF PLAYED SUCCESSFULLY

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
        asyncio.create_task(uno_turn_timer(chat_id, game["turn_id"]))
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

    get_next_turn(game)
    game["turn_id"] += 1
    asyncio.create_task(uno_turn_timer(chat_id, game["turn_id"]))
    await send_uno_table(chat_id, uid)

@app.on_callback_query(filters.regex(r"^unocolor_(.*)$"))
async def choose_color_cb(client, cb):
    chat_id = cb.message.chat.id; uid = cb.from_user.id
    if chat_id not in uno_games or uno_games[chat_id]["status"] != "waiting_color": return
    game = uno_games[chat_id]
    if game["players"][game["turn_index"]]["id"] != uid: return await cb.answer("Wait!", show_alert=True)
        
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
        
    get_next_turn(game); await cb.message.delete()
    game["turn_id"] += 1
    asyncio.create_task(uno_turn_timer(chat_id, game["turn_id"]))
    await send_uno_table(chat_id, uid)

@app.on_callback_query(filters.regex("^uno_draw$"))
async def uno_draw_cb(client, cb):
    chat_id = cb.message.chat.id; uid = cb.from_user.id
    if chat_id not in uno_games or uno_games[chat_id]["status"] != "playing": return
    game = uno_games[chat_id]
    if game["players"][game["turn_index"]]["id"] != uid: return await cb.answer("Wait for your turn!", show_alert=True)
        
    if not game["deck"]: game["deck"] = get_uno_deck()
    drawn = game["deck"].pop(); game["players"][game["turn_index"]]["cards"].append(drawn)
    await cb.answer("📥 You drew a card!", show_alert=True)
    get_next_turn(game)
    game["turn_id"] += 1
    asyncio.create_task(uno_turn_timer(chat_id, game["turn_id"]))
    await send_uno_table(chat_id, uid)

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
            BotCommand("start", "Start the bot"),
            BotCommand("startgame", "Start a new game"),
            BotCommand("new", "Start a new game"),
            BotCommand("leave", "Leave the game you're in"),
            BotCommand("kill", "Terminate the game"),
            BotCommand("end", "Terminate the game (Same as kill)"),
            BotCommand("kick", "Kick players out of the game"),
            BotCommand("skip", "Skip the current player"),
            BotCommand("rank", "Check your global rank and wins"),
            BotCommand("help", "How to use this bot?"),
            BotCommand("rules", "Explanation of game rules"),
            BotCommand("settings", "Language and other settings"),
            BotCommand("stats", "Show statistics"),
            BotCommand("topplayers", "Global Leaderboard")
        ])
    except Exception as e: print("Could not set commands:", e)
    
    print("=========================================")
    print("✅ PRO UNO BOT (AUTO-DELETE CMDS EDITION) IS LIVE!")
    print("=========================================")
    await idle()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
