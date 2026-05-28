#!/usr/bin/env python3
import os
import json
import random
import logging
from typing import Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters
)
from words import WORD_CATEGORIES, get_all_words, get_category_words, get_total_count

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")
PORT = int(os.environ.get("PORT", 8443))


# ─── helpers ──────────────────────────────────────────────────────────────────

def get_user_data(context: ContextTypes.DEFAULT_TYPE) -> dict:
    if "stats" not in context.user_data:
        context.user_data["stats"] = {"known": [], "unknown": [], "total_seen": 0}
    if "session" not in context.user_data:
        context.user_data["session"] = None
    return context.user_data


def build_main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📚 Study Flashcards", callback_data="menu_study")],
        [InlineKeyboardButton("🎯 Quiz Mode", callback_data="menu_quiz")],
        [InlineKeyboardButton("📊 My Progress", callback_data="menu_stats")],
        [InlineKeyboardButton("📋 All Categories", callback_data="menu_categories")],
        [InlineKeyboardButton("🔀 Random Word", callback_data="random_word")],
    ])


def build_category_menu(back_target: str = "main") -> InlineKeyboardMarkup:
    rows = []
    cats = list(WORD_CATEGORIES.items())
    for i in range(0, len(cats), 2):
        row = []
        for cat_id, cat in cats[i:i+2]:
            label = f"{cat['emoji']} {cat['name']} ({len(cat['words'])})"
            row.append(InlineKeyboardButton(label, callback_data=f"cat_{back_target}_{cat_id}"))
        rows.append(row)
    rows.append([InlineKeyboardButton("⭐ All Words", callback_data=f"cat_{back_target}_all")])
    rows.append([InlineKeyboardButton("🏠 Main Menu", callback_data="back_main")])
    return rows, InlineKeyboardMarkup(rows)


def card_text(word: dict, revealed: bool, index: int, total: int) -> str:
    progress = f"Card {index + 1}/{total}"
    cat_name = word.get("category", "")
    header = f"📖 *{cat_name}* — {progress}\n{'─' * 28}\n"
    if not revealed:
        return (
            header
            + f"🇧🇬  *{word['bg']}*\n\n"
            + f"🔤 _{word['tr']}_\n\n"
            + "Tap below to reveal the English translation."
        )
    return (
        header
        + f"🇧🇬  *{word['bg']}*\n"
        + f"🔤 _{word['tr']}_\n\n"
        + f"🇬🇧  *{word['en']}*"
    )


def card_keyboard(revealed: bool, word_id: str) -> InlineKeyboardMarkup:
    if not revealed:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("👁 Reveal Translation", callback_data=f"reveal_{word_id}")],
            [
                InlineKeyboardButton("⏭ Skip", callback_data=f"skip_{word_id}"),
                InlineKeyboardButton("🏠 Menu", callback_data="back_main"),
            ],
        ])
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Know it!", callback_data=f"known_{word_id}"),
            InlineKeyboardButton("❌ Still learning", callback_data=f"unknown_{word_id}"),
        ],
        [
            InlineKeyboardButton("⏭ Next", callback_data=f"next_{word_id}"),
            InlineKeyboardButton("🏠 Menu", callback_data="back_main"),
        ],
    ])


def start_session(context, category_id: str):
    if category_id == "all":
        words = get_all_words()
    else:
        raw = get_category_words(category_id)
        cat = WORD_CATEGORIES[category_id]
        words = [{**w, "category": cat["name"], "cat_id": category_id} for w in raw]
    random.shuffle(words)
    context.user_data["session"] = {
        "category": category_id,
        "words": words,
        "index": 0,
        "revealed": False,
    }


def current_word(context) -> Optional[dict]:
    s = context.user_data.get("session")
    if not s or s["index"] >= len(s["words"]):
        return None
    return s["words"][s["index"]]


def word_uid(word: dict, index: int) -> str:
    return f"{index}"


# ─── command handlers ─────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    get_user_data(context)
    total = get_total_count()
    text = (
        f"👋 *Welcome to Bulgarian Flashcards!*\n\n"
        f"Learn the most common Bulgarian words with flashcards and quizzes.\n\n"
        f"📦 *{total} words* in *{len(WORD_CATEGORIES)} categories*\n\n"
        "Choose an option below to get started:"
    )
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=build_main_menu())


async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🏠 *Main Menu*", parse_mode="Markdown", reply_markup=build_main_menu()
    )


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    d = get_user_data(context)
    stats = d["stats"]
    known = len(set(stats["known"]))
    unknown = len(set(stats["unknown"]))
    seen = stats["total_seen"]
    total = get_total_count()
    pct = round(known / total * 100, 1) if total else 0
    text = (
        f"📊 *Your Progress*\n\n"
        f"✅ Words known: *{known}*\n"
        f"❌ Still learning: *{unknown}*\n"
        f"👁 Total seen: *{seen}*\n"
        f"📦 Total words: *{total}*\n\n"
        f"🏆 Mastery: *{pct}%*"
    )
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=build_main_menu())


# ─── callback query handler ───────────────────────────────────────────────────

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    get_user_data(context)

    # ── main menu buttons ──────────────────────────────────────────────────────
    if data == "back_main" or data == "menu_main":
        await query.edit_message_text(
            "🏠 *Main Menu*", parse_mode="Markdown", reply_markup=build_main_menu()
        )
        return

    if data == "menu_study":
        _, markup = build_category_menu("study")
        await query.edit_message_text(
            "📚 *Choose a category to study:*",
            parse_mode="Markdown",
            reply_markup=markup,
        )
        return

    if data == "menu_quiz":
        _, markup = build_category_menu("quiz")
        await query.edit_message_text(
            "🎯 *Choose a category for the quiz:*",
            parse_mode="Markdown",
            reply_markup=markup,
        )
        return

    if data == "menu_categories":
        lines = [f"{cat['emoji']} *{cat['name']}* — {len(cat['words'])} words"
                 for cat in WORD_CATEGORIES.values()]
        text = "📋 *All Categories:*\n\n" + "\n".join(lines)
        back_btn = InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Main Menu", callback_data="back_main")]])
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=back_btn)
        return

    if data == "menu_stats":
        stats = context.user_data["stats"]
        known = len(set(stats["known"]))
        unknown = len(set(stats["unknown"]))
        seen = stats["total_seen"]
        total = get_total_count()
        pct = round(known / total * 100, 1) if total else 0
        text = (
            f"📊 *Your Progress*\n\n"
            f"✅ Known: *{known}*\n"
            f"❌ Still learning: *{unknown}*\n"
            f"👁 Total seen: *{seen}*\n"
            f"📦 Total words: *{total}*\n\n"
            f"🏆 Mastery: *{pct}%*"
        )
        back_btn = InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Main Menu", callback_data="back_main")]])
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=back_btn)
        return

    if data == "random_word":
        word = random.choice(get_all_words())
        text = (
            f"🔀 *Random Word*\n\n"
            f"🇧🇬 *{word['bg']}*\n"
            f"🔤 _{word['tr']}_\n"
            f"🇬🇧 {word['en']}\n\n"
            f"📁 _{word['category']}_"
        )
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔀 Another Random Word", callback_data="random_word")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="back_main")],
        ])
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=markup)
        return

    # ── category selection ────────────────────────────────────────────────────
    if data.startswith("cat_"):
        _, mode, cat_id = data.split("_", 2)
        if mode == "study":
            start_session(context, cat_id)
            await show_current_card(query, context)
        elif mode == "quiz":
            start_session(context, cat_id)
            await show_quiz(query, context)
        return

    # ── flashcard actions ─────────────────────────────────────────────────────
    if data.startswith("reveal_"):
        s = context.user_data.get("session")
        if s:
            s["revealed"] = True
        word = current_word(context)
        if word:
            s = context.user_data["session"]
            await query.edit_message_text(
                card_text(word, True, s["index"], len(s["words"])),
                parse_mode="Markdown",
                reply_markup=card_keyboard(True, str(s["index"])),
            )
        return

    if data.startswith("known_"):
        s = context.user_data.get("session")
        word = current_word(context)
        if word and s:
            context.user_data["stats"]["known"].append(word["bg"])
            context.user_data["stats"]["total_seen"] += 1
            s["index"] += 1
            s["revealed"] = False
        await show_current_card(query, context)
        return

    if data.startswith("unknown_"):
        s = context.user_data.get("session")
        word = current_word(context)
        if word and s:
            context.user_data["stats"]["unknown"].append(word["bg"])
            context.user_data["stats"]["total_seen"] += 1
            s["index"] += 1
            s["revealed"] = False
        await show_current_card(query, context)
        return

    if data.startswith("skip_") or data.startswith("next_"):
        s = context.user_data.get("session")
        if s:
            s["index"] += 1
            s["revealed"] = False
        await show_current_card(query, context)
        return

    # ── quiz actions ──────────────────────────────────────────────────────────
    if data.startswith("quiz_ans_"):
        parts = data.split("_")
        # format: quiz_ans_{correct_flag}_{word_index}
        correct = parts[2] == "1"
        s = context.user_data.get("session")
        word = current_word(context)
        if word and s:
            if correct:
                context.user_data["stats"]["known"].append(word["bg"])
                feedback = "✅ *Correct!*"
            else:
                context.user_data["stats"]["unknown"].append(word["bg"])
                correct_answer = word["en"]
                feedback = f"❌ *Wrong!* The answer was: *{correct_answer}*"
            context.user_data["stats"]["total_seen"] += 1
            s["index"] += 1
            next_btn = InlineKeyboardMarkup([
                [InlineKeyboardButton("➡️ Next Question", callback_data="quiz_next")],
                [InlineKeyboardButton("🏠 Menu", callback_data="back_main")],
            ])
            await query.edit_message_text(
                f"{feedback}\n\n🇧🇬 *{word['bg']}* → 🇬🇧 *{word['en']}*",
                parse_mode="Markdown",
                reply_markup=next_btn,
            )
        return

    if data == "quiz_next":
        await show_quiz(query, context)
        return

    if data == "quiz_restart":
        s = context.user_data.get("session")
        if s:
            cat_id = s["category"]
            start_session(context, cat_id)
        await show_quiz(query, context)
        return


async def show_current_card(query, context):
    s = context.user_data.get("session")
    if not s:
        await query.edit_message_text(
            "No active session. Choose a category to start.",
            reply_markup=build_main_menu(),
        )
        return

    word = current_word(context)
    if not word:
        known = len(set(context.user_data["stats"]["known"]))
        total = len(s["words"])
        text = (
            f"🎉 *Session Complete!*\n\n"
            f"You studied *{total}* words.\n"
            f"✅ Known: *{known}*\n\n"
            "Great job! Keep practising to improve your Bulgarian! 💪"
        )
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Study Again", callback_data=f"cat_study_{s['category']}")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="back_main")],
        ])
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=markup)
        return

    s["revealed"] = False
    await query.edit_message_text(
        card_text(word, False, s["index"], len(s["words"])),
        parse_mode="Markdown",
        reply_markup=card_keyboard(False, str(s["index"])),
    )


async def show_quiz(query, context):
    s = context.user_data.get("session")
    if not s:
        await query.edit_message_text("No session.", reply_markup=build_main_menu())
        return

    word = current_word(context)
    if not word:
        text = (
            "🎉 *Quiz Complete!*\n\nYou've finished all the words in this category!\n\n"
            "Check your progress with 📊 My Progress."
        )
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Play Again", callback_data="quiz_restart")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="back_main")],
        ])
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=markup)
        return

    # Build 4 answer options: 1 correct + 3 random wrong ones
    all_words = get_all_words()
    wrong_pool = [w["en"] for w in all_words if w["en"] != word["en"]]
    wrong = random.sample(wrong_pool, min(3, len(wrong_pool)))
    options = wrong + [word["en"]]
    random.shuffle(options)

    total = len(s["words"])
    idx = s["index"]
    text = (
        f"🎯 *Quiz* — Question {idx + 1}/{total}\n"
        f"{'─' * 28}\n\n"
        f"🇧🇬 *{word['bg']}*\n"
        f"🔤 _{word['tr']}_\n\n"
        "What does this mean in English?"
    )

    buttons = []
    for opt in options:
        is_correct = "1" if opt == word["en"] else "0"
        buttons.append([InlineKeyboardButton(opt, callback_data=f"quiz_ans_{is_correct}_{idx}")])
    buttons.append([InlineKeyboardButton("🏠 Menu", callback_data="back_main")])

    await query.edit_message_text(
        text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons)
    )


# ─── main ─────────────────────────────────────────────────────────────────────

def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN environment variable not set!")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("menu", cmd_menu))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CallbackQueryHandler(handle_callback))

    if WEBHOOK_URL:
        logger.info(f"Starting webhook on port {PORT}")
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=BOT_TOKEN,
            webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}",
        )
    else:
        logger.info("Starting polling (local mode)")
        app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
