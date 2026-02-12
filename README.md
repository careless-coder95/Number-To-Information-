# 🔍 UID Info Bot

A powerful Telegram bot to fetch and display user information with a premium, robust, and persistent architecture.

## ✨ Features

- **🔎 Persistent Data:** MongoDB for reliable storage of users, history, and premium status.
- **👑 Advanced Management:** Owner, Sudo, and Premium tiers with varying limits.
- **🛡️ Robust Polling:** Auto-resolves conflicts and connection issues.
- **🌍 Self-Healing Browser:** Auto-installs Playwright dependencies if missing (Fixes Render/Heroku path issues).
- **📝 Automatic Logging:** Hardcoded log channel support.
- **🎨 Premium UI:** Ania Theme with sleek inline buttons and detailed formatting.

---

## 🚀 Deployment Guide

### Option 1: Render (Recommended)

1.  **Fork this Repository** to your GitHub account.
2.  Log in to [Render](https://render.com).
3.  Click **New +** → **Web Service** (recommended to satisfy port binding) or **Background Worker**.
4.  Connect your repository.
5.  **Settings:**
    *   **Runtime:** `Python 3`
    *   **Build Command:** `chmod +x build.sh && ./build.sh`
    *   **Start Command:** `python bot.py`
6.  **Environment Variables (Env Groups):**
    *   Add the variables listed below.
7.  **Deploy!** (The self-healing script will handle browser installation).

### Option 2: Heroku

1.  **Fork this Repository**.
2.  Create a new app on [Heroku](https://heroku.com).
3.  **Settings > Config Vars:**
    *   Add the variables listed below.
4.  **Settings > Buildpacks:**
    *   Add `heroku/python`
    *   Add `https://github.com/mxschmitt/heroku-playwright-buildpack.git`
    *   *(Make sure they are in this order)*
5.  **Deploy:**
    *   Go to **Deploy** tab → Connect GitHub → **Manual Deploy**.

---

## 🔑 Environment Variables

| Variable | Required | Description |
| :--- | :---: | :--- |
| `BOT_TOKEN` | ✅ | Telegram Bot Token from [@BotFather](https://t.me/BotFather) |
| `OWNER_ID` | ✅ | Your Telegram User ID (get via `/myid`) |
| `MONGO_URI` | ✅ | MongoDB Connection String (from [MongoDB Atlas](https://www.mongodb.com/atlas)) |
| `OWNER_NAME` | ❌ | Your display name (Default: `Owner`) |

---

## 🛠️ Commands

### 👤 User Commands
- `/start` - Check access/status.
- `/mystats` - View your usage and plan.
- `/history` - View your search history.
- `/myid` - View your Telegram ID (Use this for OWNER_ID).
- **Search:** Send any mobile number/UID to fetch info.

### 👑 Owner Commands (via `/owner`)
> *Commands are hidden from regular users.*

- `/addsudo [id]` - Grant Sudo access.
- `/rmsudo [id]` - Revoke Sudo access.
- `/addpremium [id] [days] [tier]` - Grant Premium (Basic, Pro, VIP).
- `/rmpremium [id]` - Revoke Premium.
- `/ban [id]` / `/unban [id]` - Manage access.
- `/broadcast [msg]` - Send message to all users.
- `/maintenance` - Toggle maintenance mode.
- `/stats` - View global bot statistics.

---

## 🧩 Technical Details for Developers

- **Language:** Python 3.11+
- **Framework:** `python-telegram-bot` (v20.8+)
- **Browser Automation:** `playwright` (Chromium)
- **Database:** `pymongo`
- **WSGI:** Built-in dummy HTTP server for Render Port Binding.

### Local Development
1. Clone repo: `git clone <url>`
2. Install deps: `pip install -r requirements.txt`
3. Install browser: `playwright install chromium`
4. Setup `.env` file.
5. Run: `python bot.py`

---

## 📝 License
MIT License.
