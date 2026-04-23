import os
import asyncio
import logging
import aiohttp
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from pymongo import MongoClient

# Bot Configuration
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = os.getenv("OWNER_ID", "")
OWNER_NAME = os.getenv("OWNER_NAME", "Owner")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
LOG_GROUP_ID = -1003642420485  # Fixed log group
API_KEY = os.getenv("API_KEY", "STARK-ANSH")  # API key for Stark API

# Logging setup
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)  # Silence httpx logs
logger = logging.getLogger(__name__)

# API URL for fetching info
API_BASE_URL = "https://stark-free-osint-api.vercel.app/info"

# Bot state
MAINTENANCE_MODE = False

# ═══════════════════════════════════════════════════════════════
# 💾 MONGODB CONNECTION
# ═══════════════════════════════════════════════════════════════

try:
    client = MongoClient(MONGO_URI)
    db = client["uid_bot"]
    
    # Collections
    sudo_col = db["sudo_users"]
    banned_col = db["banned_users"]
    premium_col = db["premium_users"]
    users_col = db["users"]
    config_col = db["config"]
    stats_col = db["stats"]
    history_col = db["history"]
    
    logger.info("MongoDB connected successfully!")
except Exception as e:
    logger.error(f"MongoDB connection failed: {e}")
    raise


# ═══════════════════════════════════════════════════════════════
# 💾 DATABASE FUNCTIONS
# ═══════════════════════════════════════════════════════════════

# Sudo Users
def get_sudo_users() -> set:
    users = sudo_col.find_one({"_id": "sudo_list"})
    return set(users.get("users", [])) if users else set()

def save_sudo_users(users: set):
    sudo_col.update_one({"_id": "sudo_list"}, {"$set": {"users": list(users)}}, upsert=True)

# Banned Users
def get_banned_users() -> set:
    users = banned_col.find_one({"_id": "banned_list"})
    return set(users.get("users", [])) if users else set()

def save_banned_users(users: set):
    banned_col.update_one({"_id": "banned_list"}, {"$set": {"users": list(users)}}, upsert=True)

# Premium Users
def get_premium_users() -> dict:
    users = premium_col.find_one({"_id": "premium_list"})
    return users.get("data", {}) if users else {}

def save_premium_users(data: dict):
    premium_col.update_one({"_id": "premium_list"}, {"$set": {"data": data}}, upsert=True)

# All Users
def get_all_users() -> set:
    users = users_col.find_one({"_id": "all_users"})
    return set(users.get("users", [])) if users else set()

def add_user(user_id: int):
    users = get_all_users()
    users.add(str(user_id))
    users_col.update_one({"_id": "all_users"}, {"$set": {"users": list(users)}}, upsert=True)

# Stats
def get_stats() -> dict:
    stats = stats_col.find_one({"_id": "bot_stats"})
    if stats:
        return stats.get("data", {})
    return {
        "total_lookups": 0,
        "successful": 0,
        "failed": 0,
        "daily": {},
        "user_lookups": {},
        "user_daily": {}
    }

def save_stats(stats: dict):
    stats_col.update_one({"_id": "bot_stats"}, {"$set": {"data": stats}}, upsert=True)

def record_lookup(user_id: int, query: str, success: bool):
    stats = get_stats()
    today = datetime.now().strftime("%Y-%m-%d")
    
    stats["total_lookups"] = stats.get("total_lookups", 0) + 1
    if success:
        stats["successful"] = stats.get("successful", 0) + 1
    else:
        stats["failed"] = stats.get("failed", 0) + 1
    
    if "daily" not in stats:
        stats["daily"] = {}
    stats["daily"][today] = stats["daily"].get(today, 0) + 1
    
    if "user_lookups" not in stats:
        stats["user_lookups"] = {}
    uid_str = str(user_id)
    stats["user_lookups"][uid_str] = stats["user_lookups"].get(uid_str, 0) + 1
    
    save_stats(stats)

# History
def get_user_history(user_id: int) -> list:
    history = history_col.find_one({"_id": str(user_id)})
    return history.get("data", [])[-20:] if history else []

def add_to_history(user_id: int, query: str, result: str):
    history = get_user_history(user_id)
    history.append({
        "query": query,
        "time": datetime.now().isoformat(),
        "result_preview": result[:100] if result else "No data"
    })
    history = history[-50:]  # Keep last 50
    history_col.update_one({"_id": str(user_id)}, {"$set": {"data": history}}, upsert=True)

# Daily Limits
def get_user_daily_lookups(user_id: int) -> int:
    stats = get_stats()
    today = datetime.now().strftime("%Y-%m-%d")
    user_daily = stats.get("user_daily", {}).get(today, {})
    return user_daily.get(str(user_id), 0)

def increment_user_daily(user_id: int):
    stats = get_stats()
    today = datetime.now().strftime("%Y-%m-%d")
    if "user_daily" not in stats:
        stats["user_daily"] = {}
    if today not in stats["user_daily"]:
        stats["user_daily"][today] = {}
    uid_str = str(user_id)
    stats["user_daily"][today][uid_str] = stats["user_daily"][today].get(uid_str, 0) + 1
    save_stats(stats)

def get_daily_limit(user_id: int) -> int:
    if str(user_id) == OWNER_ID:
        return 999999
    premium = get_premium_users()
    if str(user_id) in premium:
        tier = premium[str(user_id)].get("tier", "basic")
        if tier == "vip":
            return 100
        elif tier == "pro":
            return 50
        else:
            return 25
    if str(user_id) in get_sudo_users():
        return 20
    return 5


# ═══════════════════════════════════════════════════════════════
# 🔐 AUTHORIZATION FUNCTIONS
# ═══════════════════════════════════════════════════════════════

def is_owner(user_id: int) -> bool:
    return str(user_id) == OWNER_ID

def is_sudo(user_id: int) -> bool:
    return str(user_id) in get_sudo_users()

def is_premium(user_id: int) -> bool:
    premium = get_premium_users()
    if str(user_id) in premium:
        expiry = premium[str(user_id)].get("expiry")
        if expiry:
            if datetime.fromisoformat(expiry) > datetime.now():
                return True
    return False

def is_banned(user_id: int) -> bool:
    return str(user_id) in get_banned_users()

def is_authorized(user_id: int) -> bool:
    if is_banned(user_id):
        return False
    return is_owner(user_id) or is_sudo(user_id) or is_premium(user_id)


# ═══════════════════════════════════════════════════════════════
# 🎨 STYLING FUNCTIONS
# ═══════════════════════════════════════════════════════════════

def escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def stylize(text: str) -> str:
    if not text:
        return ""
    mapping = {
        'a': 'ᴀ', 'b': 'ʙ', 'c': 'ᴄ', 'd': 'ᴅ', 'e': 'ᴇ', 'f': 'ғ', 'g': 'ɢ',
        'h': 'ʜ', 'i': 'ɪ', 'j': 'ᴊ', 'k': 'ᴋ', 'l': 'ʟ', 'm': 'ᴍ', 'n': 'ɴ',
        'o': 'ᴏ', 'p': 'ᴘ', 'q': 'ǫ', 'r': 'ʀ', 's': 's', 't': 'ᴛ', 'u': 'ᴜ',
        'v': 'ᴠ', 'w': 'ᴡ', 'x': 'x', 'y': 'ʏ', 'z': 'ᴢ',
        'A': 'ᴀ', 'B': 'ʙ', 'C': 'ᴄ', 'D': 'ᴅ', 'E': 'ᴇ', 'F': 'ғ', 'G': 'ɢ',
        'H': 'ʜ', 'I': 'ɪ', 'J': 'ᴊ', 'K': 'ᴋ', 'L': 'ʟ', 'M': 'ᴍ', 'N': 'ɴ',
        'O': 'ᴏ', 'P': 'ᴘ', 'Q': 'ǫ', 'R': 'ʀ', 'S': 's', 'T': 'ᴛ', 'U': 'ᴜ',
        'V': 'ᴠ', 'W': 'ᴡ', 'X': 'x', 'Y': 'ʏ', 'Z': 'ᴢ'
    }
    return ''.join(mapping.get(c, c) for c in text)

def panel(title: str, content: str) -> str:
    styled_title = stylize(title)
    return f"""╭─────────────────────╮
│  {styled_title}
╰─────────────────────╯

{content}"""

def get_owner_footer() -> str:
    if OWNER_NAME and OWNER_ID:
        return f"\n\n━━━━━━━━━━━━━━━━━━━\n👤 <b>Owner:</b> <a href='tg://user?id={OWNER_ID}'>{escape_html(OWNER_NAME)}</a>"
    return ""


# ═══════════════════════════════════════════════════════════════
# 📌 COMMAND HANDLERS
# ═══════════════════════════════════════════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    add_user(user.id)
    
    keyboard = [
        [InlineKeyboardButton("📖 Help", callback_data="help"),
         InlineKeyboardButton("📊 My Stats", callback_data="mystats")],
        [InlineKeyboardButton("📜 History", callback_data="history"),
         InlineKeyboardButton("🔍 New Search", callback_data="new")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome = f"""👋 Welcome <b>{escape_html(user.first_name)}</b>!

🔍 Send any Telegram ID to lookup.
📊 Daily Limit: {get_daily_limit(user.id)}/day"""
    
    await update.message.reply_text(
        panel("🤖 OSINT Bot", welcome + get_owner_footer()),
        reply_markup=reply_markup,
        parse_mode="HTML",
        disable_web_page_preview=True
    )

async def myid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    content = f"👤 <b>Your ID:</b> <code>{user.id}</code>\n📝 <b>Username:</b> @{user.username or 'None'}\n🏷 <b>Name:</b> {escape_html(user.first_name)}"
    await update.message.reply_text(panel("🆔 Your Info", content), parse_mode="HTML")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if is_owner(user.id):
        content = """<b>👑 Owner:</b> /owner

<b>📋 Commands:</b>
/start, /help, /mystats
/history, /limit

Send any Telegram ID to lookup."""
    else:
        content = """<b>📋 Commands:</b>
/start, /help, /mystats
/history, /limit

Send any Telegram ID to lookup."""
    
    await update.message.reply_text(
        panel("📖 Help", content + get_owner_footer()),
        parse_mode="HTML",
        disable_web_page_preview=True
    )

async def owner_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_owner(user.id):
        await update.message.reply_text("❌ Owner only!")
        return
    
    total_users = len(get_all_users())
    sudo_count = len(get_sudo_users())
    banned_count = len(get_banned_users())
    premium_count = len(get_premium_users())
    stats = get_stats()
    
    content = f"""📊 <b>Bot Statistics</b>

👥 Total Users: {total_users}
👑 Sudo: {sudo_count}
⭐ Premium: {premium_count}
🚫 Banned: {banned_count}

🔍 Total Lookups: {stats.get('total_lookups', 0)}
✅ Successful: {stats.get('successful', 0)}
❌ Failed: {stats.get('failed', 0)}

<b>Owner Commands:</b>
/addsudo [id] - Add sudo
/rmsudo [id] - Remove sudo
/sudolist - List sudos
/ban [id] - Ban user
/unban [id] - Unban user
/banlist - List banned
/addpremium [id] - Add premium
/rmpremium [id] - Remove premium
/premiumlist - List premium
/stats - Bot stats
/broadcast [msg] - Broadcast
/maintenance - Toggle maintenance"""
    
    await update.message.reply_text(panel("👑 Owner Panel", content), parse_mode="HTML")

async def add_sudo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_owner(user.id):
        await update.message.reply_text("❌ Owner only!")
        return
    
    if not context.args:
        await update.message.reply_text("Usage: /addsudo [user_id]")
        return
    
    target_id = context.args[0]
    sudos = get_sudo_users()
    sudos.add(target_id)
    save_sudo_users(sudos)
    
    await update.message.reply_text(panel("✅ Added", f"User <code>{target_id}</code> is now sudo."), parse_mode="HTML")

async def remove_sudo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_owner(user.id):
        await update.message.reply_text("❌ Owner only!")
        return
    
    if not context.args:
        await update.message.reply_text("Usage: /rmsudo [user_id]")
        return
    
    target_id = context.args[0]
    sudos = get_sudo_users()
    sudos.discard(target_id)
    save_sudo_users(sudos)
    
    await update.message.reply_text(panel("✅ Removed", f"User <code>{target_id}</code> removed from sudo."), parse_mode="HTML")

async def sudo_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_owner(user.id):
        await update.message.reply_text("❌ Owner only!")
        return
    
    sudos = get_sudo_users()
    if sudos:
        content = "\n".join([f"• <code>{s}</code>" for s in sudos])
    else:
        content = "<i>No sudo users.</i>"
    
    await update.message.reply_text(panel("👑 Sudo List", content), parse_mode="HTML")

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_owner(user.id):
        await update.message.reply_text("❌ Owner only!")
        return
    
    if not context.args:
        await update.message.reply_text("Usage: /ban [user_id]")
        return
    
    target_id = context.args[0]
    banned = get_banned_users()
    banned.add(target_id)
    save_banned_users(banned)
    
    await update.message.reply_text(panel("🚫 Banned", f"User <code>{target_id}</code> is now banned."), parse_mode="HTML")

async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_owner(user.id):
        await update.message.reply_text("❌ Owner only!")
        return
    
    if not context.args:
        await update.message.reply_text("Usage: /unban [user_id]")
        return
    
    target_id = context.args[0]
    banned = get_banned_users()
    banned.discard(target_id)
    save_banned_users(banned)
    
    await update.message.reply_text(panel("✅ Unbanned", f"User <code>{target_id}</code> is unbanned."), parse_mode="HTML")

async def ban_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_owner(user.id):
        await update.message.reply_text("❌ Owner only!")
        return
    
    banned = get_banned_users()
    if banned:
        content = "\n".join([f"• <code>{b}</code>" for b in banned])
    else:
        content = "<i>No banned users.</i>"
    
    await update.message.reply_text(panel("🚫 Banned List", content), parse_mode="HTML")

async def add_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_owner(user.id):
        await update.message.reply_text("❌ Owner only!")
        return
    
    if not context.args:
        await update.message.reply_text("Usage: /addpremium [user_id]")
        return
    
    target_id = context.args[0]
    
    keyboard = [
        [InlineKeyboardButton("🥉 Basic (25/day) - 7d", callback_data=f"premium_{target_id}_7_basic"),
         InlineKeyboardButton("🥉 Basic - 30d", callback_data=f"premium_{target_id}_30_basic")],
        [InlineKeyboardButton("🥈 Pro (50/day) - 7d", callback_data=f"premium_{target_id}_7_pro"),
         InlineKeyboardButton("🥈 Pro - 30d", callback_data=f"premium_{target_id}_30_pro")],
        [InlineKeyboardButton("🥇 VIP (100/day) - 7d", callback_data=f"premium_{target_id}_7_vip"),
         InlineKeyboardButton("🥇 VIP - 30d", callback_data=f"premium_{target_id}_30_vip")],
        [InlineKeyboardButton("❌ Cancel", callback_data="premium_cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    content = f"Select premium tier for <code>{target_id}</code>:"
    await update.message.reply_text(panel("⭐ Add Premium", content), 
                                     reply_markup=reply_markup, parse_mode="HTML")

async def remove_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_owner(user.id):
        await update.message.reply_text("❌ Owner only!")
        return
    
    if not context.args:
        await update.message.reply_text("Usage: /rmpremium [user_id]")
        return
    
    target_id = context.args[0]
    premium = get_premium_users()
    if target_id in premium:
        del premium[target_id]
        save_premium_users(premium)
        await update.message.reply_text(panel("✅ Removed", f"Premium removed for <code>{target_id}</code>."), parse_mode="HTML")
    else:
        await update.message.reply_text(panel("❌ Error", "User is not premium."), parse_mode="HTML")

async def premium_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_owner(user.id):
        await update.message.reply_text("❌ Owner only!")
        return
    
    premium = get_premium_users()
    if premium:
        lines = []
        for uid, data in premium.items():
            tier = data.get("tier", "basic")
            expiry = data.get("expiry", "")
            tier_emoji = {"basic": "🥉", "pro": "🥈", "vip": "🥇"}.get(tier, "⭐")
            lines.append(f"{tier_emoji} <code>{uid}</code> ({tier}) - {expiry[:10]}")
        content = "\n".join(lines)
    else:
        content = "<i>No premium users.</i>"
    
    await update.message.reply_text(panel("⭐ Premium List", content), parse_mode="HTML")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_owner(user.id) and not is_sudo(user.id):
        await update.message.reply_text("❌ Owner/Sudo only!")
        return
    
    stats = get_stats()
    total_users = len(get_all_users())
    
    content = f"""📊 <b>Statistics</b>

👥 Total Users: {total_users}
🔍 Total Lookups: {stats.get('total_lookups', 0)}
✅ Successful: {stats.get('successful', 0)}
❌ Failed: {stats.get('failed', 0)}"""
    
    await update.message.reply_text(panel("📊 Bot Stats", content), parse_mode="HTML")

async def my_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    stats = get_stats()
    lookups = stats.get("user_lookups", {}).get(str(user.id), 0)
    today_used = get_user_daily_lookups(user.id)
    limit = get_daily_limit(user.id)
    
    content = f"""📊 <b>Total Lookups:</b> {lookups}
📅 <b>Today:</b> {today_used}/{limit}
🎯 <b>Daily Limit:</b> {limit}/day"""
    
    await update.message.reply_text(panel("📊 My Stats", content), parse_mode="HTML")

async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    history = get_user_history(user.id)
    
    if history:
        lines = []
        for h in history[-10:]:
            time = h['time'][:19].replace('T', ' ')
            lines.append(f"• <code>{h['query'][:15]}</code> - {time}")
        content = "\n".join(lines)
    else:
        content = "<i>No history yet.</i>"
    
    await update.message.reply_text(panel("📜 History", content), parse_mode="HTML")

async def limit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    limit = get_daily_limit(user.id)
    used = get_user_daily_lookups(user.id)
    remaining = limit - used
    
    content = f"""📊 <b>Daily Limit:</b> {limit}/day
✅ <b>Used:</b> {used}
⏳ <b>Remaining:</b> {remaining}"""
    
    await update.message.reply_text(panel("📊 Your Limit", content), parse_mode="HTML")

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_owner(user.id):
        await update.message.reply_text("❌ Owner only!")
        return
    
    if not context.args:
        await update.message.reply_text("Usage: /broadcast [message]")
        return
    
    message = " ".join(context.args)
    users = get_all_users()
    success = 0
    failed = 0
    
    status_msg = await update.message.reply_text(panel("📢 Broadcasting", "Starting..."), parse_mode="HTML")
    
    for uid in users:
        try:
            await context.bot.send_message(int(uid), message, parse_mode="HTML")
            success += 1
        except:
            failed += 1
        
        if (success + failed) % 10 == 0:
            await status_msg.edit_text(
                panel("📢 Broadcasting", f"✅ Sent: {success}\n❌ Failed: {failed}"),
                parse_mode="HTML"
            )
    
    await status_msg.edit_text(
        panel("📢 Broadcast Complete", f"✅ Sent: {success}\n❌ Failed: {failed}"),
        parse_mode="HTML"
    )

async def maintenance_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global MAINTENANCE_MODE
    user = update.effective_user
    if not is_owner(user.id):
        await update.message.reply_text("❌ Owner only!")
        return
    
    MAINTENANCE_MODE = not MAINTENANCE_MODE
    status = "ENABLED" if MAINTENANCE_MODE else "DISABLED"
    await update.message.reply_text(panel("🔧 Maintenance", f"Maintenance mode: <b>{status}</b>"), parse_mode="HTML")


# ═══════════════════════════════════════════════════════════════
# 🔍 FETCH INFO HANDLER (Using Stark API)
# ═══════════════════════════════════════════════════════════════

async def fetch_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global MAINTENANCE_MODE
    
    user = update.effective_user
    tg_id = update.message.text.strip()
    
    # Add user
    add_user(user.id)
    
    # Check maintenance
    if MAINTENANCE_MODE and not is_owner(user.id):
        await update.message.reply_text(panel("🔧 Maintenance", "Bot is under maintenance."), parse_mode="HTML")
        return
    
    # Check banned
    if is_banned(user.id):
        await update.message.reply_text(panel("🚫 Banned", "You are banned from using this bot."), parse_mode="HTML")
        return
    
    # Validate input (should be numeric)
    if not tg_id.isdigit():
        await update.message.reply_text(panel("❌ Invalid Input", "Please send a valid Telegram ID (numeric only)."), parse_mode="HTML")
        return
    
    # Check daily limit
    limit = get_daily_limit(user.id)
    used = get_user_daily_lookups(user.id)
    if used >= limit:
        await update.message.reply_text(
            panel("⏳ Limit Reached", f"Daily limit: {limit}/day\nUsed: {used}\n\nCome back tomorrow!{get_owner_footer()}"),
            parse_mode="HTML",
            disable_web_page_preview=True
        )
        return
    
    # Increment daily counter
    increment_user_daily(user.id)
    
    # Send loading message
    loading_msg = await update.message.reply_text(panel("🔍 Searching", f"Looking up TG ID <code>{escape_html(tg_id)}</code>..."), parse_mode="HTML")
    
    try:
        # Fetch data from Stark API
        url = f"{API_BASE_URL}?type=tg&tg_id={tg_id}&key={API_KEY}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=30) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Check if data is valid
                    if data and isinstance(data, dict):
                        # Format the response nicely
                        user_mention = f"<a href='tg://user?id={user.id}'>{escape_html(user.first_name)}</a>"
                        
                        # Build formatted result
                        result_lines = []
                        result_lines.append(f"🔍 <b>Telegram ID:</b> <code>{tg_id}</code>\n")
                        
                        for key, value in data.items():
                            if value and str(value).strip():
                                # Format key nicely
                                formatted_key = key.replace("_", " ").title()
                                result_lines.append(f"<b>{formatted_key}:</b> {escape_html(str(value))}")
                        
                        decorated = "\n".join(result_lines)
                        
                        # Add to history
                        add_to_history(user.id, tg_id, str(data)[:200])
                        
                        # Send result
                        record_lookup(user.id, tg_id, True)
                        await loading_msg.edit_text(panel("✅ Found", decorated), parse_mode="HTML", disable_web_page_preview=True)
                        
                        # Log to fixed group
                        try:
                            log_header = f"🔍 <b>Query:</b> <code>{escape_html(tg_id)}</code>\n👤 <b>By:</b> {user_mention} (<code>{user.id}</code>)\n\n"
                            await context.bot.send_message(LOG_GROUP_ID, log_header + decorated, 
                                                           parse_mode="HTML", disable_web_page_preview=True)
                        except Exception as e:
                            logger.warning(f"Log error: {e}")
                    else:
                        record_lookup(user.id, tg_id, False)
                        await loading_msg.edit_text(panel("⚠️ No Data", f"No info found for TG ID <code>{escape_html(tg_id)}</code>"), parse_mode="HTML")
                else:
                    record_lookup(user.id, tg_id, False)
                    await loading_msg.edit_text(panel("❌ Error", f"API returned status code: {response.status}"), parse_mode="HTML")
    
    except asyncio.TimeoutError:
        record_lookup(user.id, tg_id, False)
        logger.error("API request timeout")
        await loading_msg.edit_text(panel("❌ Timeout", "API request timed out. Try again later."), parse_mode="HTML")
    
    except Exception as e:
        record_lookup(user.id, tg_id, False)
        logger.error(f"Fetch error: {e}")
        await loading_msg.edit_text(panel("❌ Error", escape_html(str(e)[:200])), parse_mode="HTML")


# ═══════════════════════════════════════════════════════════════
# 🔘 CALLBACK HANDLER
# ═══════════════════════════════════════════════════════════════

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user = query.from_user
    
    if data == "help":
        if is_owner(user.id):
            content = """<b>👑 Owner:</b> /owner

<b>📋 Commands:</b>
/start, /help, /mystats
/history, /limit

Send any Telegram ID to lookup."""
        else:
            content = """<b>📋 Commands:</b>
/start, /help, /mystats
/history, /limit

Send any Telegram ID to lookup."""
        await query.edit_message_text(panel("📖 Help", content + get_owner_footer()), 
                                       parse_mode="HTML", disable_web_page_preview=True)
    
    elif data == "mystats":
        stats = get_stats()
        lookups = stats.get("user_lookups", {}).get(str(user.id), 0)
        today_used = get_user_daily_lookups(user.id)
        limit = get_daily_limit(user.id)
        content = f"📊 Total: {lookups}\n📅 Today: {today_used}/{limit}"
        await query.edit_message_text(panel("📊 My Stats", content), parse_mode="HTML")
    
    elif data == "history":
        history = get_user_history(user.id)
        if history:
            lines = [f"• <code>{h['query'][:15]}</code>" for h in history[-10:]]
            content = "\n".join(lines)
        else:
            content = "<i>No history.</i>"
        await query.edit_message_text(panel("📜 History", content), parse_mode="HTML")
    
    elif data == "new":
        await query.edit_message_text(panel("🔍 New Search", "Send any Telegram ID to lookup."), parse_mode="HTML")
    
    elif data == "premium_cancel":
        await query.edit_message_text(panel("❌ Cancelled", "Premium operation cancelled."), parse_mode="HTML")
    
    elif data.startswith("premium_"):
        # Only owner can use premium buttons
        if not is_owner(user.id):
            await query.answer("❌ Only owner can do this!", show_alert=True)
            return
        
        # Parse: premium_userid_days_tier
        parts = data.split("_")
        if len(parts) == 4:
            _, target_id, days_str, tier = parts
            days = int(days_str)
            
            # Add premium
            premium = get_premium_users()
            expiry = (datetime.now() + timedelta(days=days)).isoformat()
            premium[target_id] = {"expiry": expiry, "tier": tier}
            save_premium_users(premium)
            
            tier_emoji = {"basic": "🥉", "pro": "🥈", "vip": "🥇"}.get(tier, "⭐")
            tier_limits = {"basic": "25", "pro": "50", "vip": "100"}.get(tier, "25")
            
            content = f"""✅ <b>Premium Activated!</b>

👤 <b>User ID:</b> <code>{target_id}</code>
{tier_emoji} <b>Tier:</b> {tier.upper()}
📊 <b>Daily Limit:</b> {tier_limits}/day
⏰ <b>Duration:</b> {days} days"""
            
            await query.edit_message_text(panel("⭐ Premium Added", content), parse_mode="HTML")
            
            # Send DM to user
            try:
                dm = panel("🎉 Premium Activated", f"You've got {tier_emoji} {tier.upper()} premium for {days} days!\n\n📊 Daily Limit: {tier_limits}/day{get_owner_footer()}")
                await context.bot.send_message(int(target_id), dm, parse_mode="HTML", disable_web_page_preview=True)
            except:
                pass


# ═══════════════════════════════════════════════════════════════
# 🚀 MAIN
# ═══════════════════════════════════════════════════════════════

def create_app():
    """Create and configure the application"""
    from telegram.ext import ApplicationBuilder
    from telegram.request import HTTPXRequest
    
    request = HTTPXRequest(
        connect_timeout=30.0,
        read_timeout=30.0,
        write_timeout=30.0,
        pool_timeout=30.0
    )
    
    app = ApplicationBuilder().token(BOT_TOKEN).request(request).build()
    
    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("myid", myid_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("owner", owner_command))
    app.add_handler(CommandHandler("addsudo", add_sudo))
    app.add_handler(CommandHandler("rmsudo", remove_sudo))
    app.add_handler(CommandHandler("sudolist", sudo_list))
    app.add_handler(CommandHandler("ban", ban_user))
    app.add_handler(CommandHandler("unban", unban_user))
    app.add_handler(CommandHandler("banlist", ban_list))
    app.add_handler(CommandHandler("addpremium", add_premium))
    app.add_handler(CommandHandler("rmpremium", remove_premium))
    app.add_handler(CommandHandler("premiumlist", premium_list))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("mystats", my_stats))
    app.add_handler(CommandHandler("history", history_command))
    app.add_handler(CommandHandler("limit", limit_command))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("maintenance", maintenance_toggle))
    
    # Callbacks & Messages
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, fetch_info))
    
    # Error Handler
    app.add_error_handler(error_handler)
    
    return app


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and handle specific Telegram errors."""
    
    # Handle Conflict: terminated by other getUpdates request
    if "terminated by other getUpdates request" in str(context.error):
        logger.warning("⚠️ Conflict detected: Another instance is running (Polling overlapping).")
        print("ℹ️ Sleeping for 10s to let the other instance stop...")
        await asyncio.sleep(10)
        return

    # Handle Network Errors
    if "Timed out" in str(context.error) or "ConnectTimeout" in str(context.error):
        logger.warning(f"⚠️ Network timeout: {context.error}")
        return

    logger.error(f"Exception while handling an update: {context.error}")


def start_web_server():
    """Starts a dummy web server to keep Render happy."""
    from http.server import HTTPServer, BaseHTTPRequestHandler
    import threading

    class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Bot is running!")
        
        def log_message(self, format, *args):
            pass  # Suppress web server logs
    
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), SimpleHTTPRequestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"🌍 Web server started on port {port}")


def main():
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN not found!")
        return
    
    if not OWNER_ID:
        print("⚠️ OWNER_ID not set!")

    # Start dummy web server for Render
    start_web_server()
    
    print("🚀 Bot starting with MongoDB and Stark API...")
    logger.info("Bot started!")
    
    app = create_app()
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
