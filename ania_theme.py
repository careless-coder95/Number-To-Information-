from pyrogram.types import InlineKeyboardButton

# ---------------------------------------------------------------
# 🎨 ANIA UI THEME (Standalone Export)
# ---------------------------------------------------------------
# Usage:
# 1. Copy this file to your project (e.g., helpers/theme.py)
# 2. Import it: from helpers.theme import UI
# 3. Use: await message.reply(UI.panel("TITLE", "Content here"))
# ---------------------------------------------------------------

class UI:
    """
    The UI Class handling Visual Formatting.
    Style: Bold Small Caps + Boxed Panels.
    """
    
    # Configuration (Edit these for your new bot)
    BOT_NAME = "Ania Bot"
    SUPPORT_LINK = "https://t.me/AniaBots"

    # ---------------------------------------------------------------
    # 🔠 TEXT STYLIZER (Bold Small Caps)
    # ---------------------------------------------------------------
    @staticmethod
    def stylize(text: str) -> str:
        """
        Converts text into BOLD SMALL CAPS.
        Example: "Hello" -> "ʜᴇʟʟᴏ"
        """
        if not text: return ""
            
        mapping = {
            'a': 'ᴀ', 'b': 'ʙ', 'c': 'ᴄ', 'd': 'ᴅ', 'e': 'ᴇ', 'f': 'ғ', 'g': 'ɢ',
            'h': 'ʜ', 'i': 'ɪ', 'j': 'ᴊ', 'k': 'ᴋ', 'l': 'ʟ', 'm': 'ᴍ', 'n': 'ɴ',
            'o': 'ᴏ', 'p': 'ᴘ', 'q': 'ǫ', 'r': 'ʀ', 's': 's', 't': 'ᴛ', 'u': 'ᴜ',
            'v': 'ᴠ', 'w': 'ᴡ', 'x': 'x', 'y': 'ʏ', 'z': 'ᴢ',
            '0': '0', '1': '1', '2': '2', '3': '3', '4': '4', 
            '5': '5', '6': '6', '7': '7', '8': '8', '9': '9'
        }
        
        result = []
        for char in text.lower():
            result.append(mapping.get(char, char))
            
        return "".join(result) 

    # ---------------------------------------------------------------
    # 🖼 PANEL GENERATOR (The Box Style)
    # ---------------------------------------------------------------
    @staticmethod
    def panel(title: str, content: str, footer: bool = True, style: str = "md") -> str:
        """
        Creates a 'Boxed' message style with a header and optional footer.
        Title is automatically STYLIZED (Bold Small Caps).
        """
        # Stylize the title
        styled_title = UI.stylize(title) 

        # The Top Box
        # We add spaces to center it nicely
        header_design = (
            f"╭───────────────────╮\n"
            f"│   **{styled_title.center(19)}**   │\n"
            f"╰───────────────────╯\n\n"
        )
        
        # The Footer Separator and Link
        footer_design = ""
        if footer:
            bold_start = "**" if style == "md" else "<b>"
            bold_end = "**" if style == "md" else "</b>"
            
            # Stylize Footer Text too
            footer_text = UI.stylize(f"Powered By {UI.BOT_NAME}")
            
            footer_design = (
                f"\n◈ ━━━━━━ ⸙ ━━━━━━ ◈\n"
                f"🛡 {bold_start}{footer_text}{bold_end}"
            )
            
        return header_design + content + footer_design
        
    @staticmethod
    def quote_panel(title: str, content: str) -> str:
        s_title = UI.stylize(title)
        return f"**| 🏆 {s_title} 🏆 |**\n\n{content}"

    # ---------------------------------------------------------------
    # 📊 PROGRESS BAR
    # ---------------------------------------------------------------
    @staticmethod
    def progress_bar(current: int, total: int, length: int = 10) -> str:
        """
        Generates a text-based progress bar.
        Example: ▰▰▰▰▱▱▱▱▱▱
        """
        if total == 0: percentage = 0
        else: percentage = int((current / total) * 100)
        
        if percentage > 100: percentage = 100
        
        filled_blocks = int((percentage / 100) * length)
        empty_blocks = length - filled_blocks
        
        bar = "▰" * filled_blocks + "▱" * empty_blocks
        return f"`{bar}` **{percentage}%**"

    # ---------------------------------------------------------------
    # 🔢 SMART FORMATTERS
    # ---------------------------------------------------------------
    @staticmethod
    def format_short_money(amount: int) -> str:
        """Formats 1500 -> $1.5K"""
        if amount >= 1_000_000:
            val = round(amount / 1_000_000, 1)
            return f"${val}M"
        elif amount >= 1_000:
            val = round(amount / 1_000, 1)
            return f"${val}K"
        else:
            return f"${amount}"

    @staticmethod
    def get_support_btn():
        return InlineKeyboardButton("🏟 sᴜᴘᴘᴏʀᴛ", url=UI.SUPPORT_LINK)
