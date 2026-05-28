#!/usr/bin/env python3
import os
import random
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from words_ru import CEFR_LEVELS, get_level_words, get_all_words, get_total_count
from texts_ru import TEXTS

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")
PORT = int(os.environ.get("PORT", 8443))
SENTENCES_PER_PAGE = 5


# ── helpers ────────────────────────────────────────────────────────────────────

def init_user(context):
    if "stats" not in context.user_data:
        context.user_data["stats"] = {lid: {"known": [], "unknown": [], "seen": 0} for lid in CEFR_LEVELS}
        context.user_data["stats"]["all"] = {"known": [], "unknown": [], "seen": 0}
    context.user_data.setdefault("session", None)
    context.user_data.setdefault("reading", None)


def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📚 Учить слова", callback_data="menu_study")],
        [InlineKeyboardButton("🎯 Тест", callback_data="menu_quiz")],
        [InlineKeyboardButton("📖 Чтение", callback_data="menu_reading")],
        [InlineKeyboardButton("📊 Прогресс", callback_data="menu_stats")],
        [InlineKeyboardButton("🔀 Случайное слово", callback_data="random_word")],
    ])


def level_menu(mode):
    rows = []
    for lid, lv in CEFR_LEVELS.items():
        count = len(lv["words"])
        rows.append([InlineKeyboardButton(
            f"{lv['emoji']} {lid} — {lv['label']}  ({count} сл.)",
            callback_data=f"lvl_{mode}_{lid}"
        )])
    rows.append([InlineKeyboardButton("⭐ Все уровни", callback_data=f"lvl_{mode}_all")])
    rows.append([InlineKeyboardButton("🏠 Меню", callback_data="back_main")])
    return InlineKeyboardMarkup(rows)


def text_menu():
    rows = []
    for tid, t in TEXTS.items():
        n = len(t["sentences"])
        rows.append([InlineKeyboardButton(
            f"📄 {t['title_bg']}  ({n} пр.)", callback_data=f"text_{tid}"
        )])
    rows.append([InlineKeyboardButton("🏠 Меню", callback_data="back_main")])
    return InlineKeyboardMarkup(rows)


# ── flashcard rendering ────────────────────────────────────────────────────────

def card_hidden(w, idx, total, label):
    return (
        f"📚 *{label}*  ·  {idx+1}/{total}\n"
        f"{'─'*30}\n\n"
        f"🇧🇬  *{w['bg']}*\n"
        f"🔤  _{w['tr']}_\n\n"
        f"📖  _{w['example_bg']}_\n\n"
        f"_Нажмите, чтобы увидеть перевод_"
    )


def card_shown(w, idx, total, label):
    return (
        f"📚 *{label}*  ·  {idx+1}/{total}\n"
        f"{'─'*30}\n\n"
        f"🇧🇬  *{w['bg']}*\n"
        f"🔤  _{w['tr']}_\n"
        f"📖  _{w['example_bg']}_\n\n"
        f"{'─'*30}\n\n"
        f"🇷🇺  *{w['ru']}*\n"
        f"📖  _{w['example_ru']}_"
    )


def kb_hidden(idx):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👁 Показать перевод", callback_data=f"reveal_{idx}")],
        [InlineKeyboardButton("⏭ Пропустить", callback_data=f"skip_{idx}"),
         InlineKeyboardButton("🏠 Меню", callback_data="back_main")],
    ])


def kb_shown(idx):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Знаю", callback_data=f"known_{idx}"),
         InlineKeyboardButton("❌ Не знаю", callback_data=f"unknown_{idx}")],
        [InlineKeyboardButton("⏭ Следующее", callback_data=f"next_{idx}"),
         InlineKeyboardButton("🏠 Меню", callback_data="back_main")],
    ])


# ── reading rendering ──────────────────────────────────────────────────────────

def reading_text(tid, page, show_ru):
    t = TEXTS[tid]
    sents = t["sentences"]
    total_pages = (len(sents) + SENTENCES_PER_PAGE - 1) // SENTENCES_PER_PAGE
    start = page * SENTENCES_PER_PAGE
    chunk = sents[start: start + SENTENCES_PER_PAGE]

    header = f"📖 *{t['title_bg']}*\nСтр. {page+1}/{total_pages}\n{'─'*30}\n\n"
    body = ""
    for i, s in enumerate(chunk, start=start + 1):
        if show_ru:
            body += f"🇧🇬 *{i}.* {s['bg']}\n🇷🇺 _{s['ru']}_\n\n"
        else:
            body += f"*{i}.* {s['bg']}\n"
    return header + body.strip()


def reading_kb(tid, page, show_ru):
    t = TEXTS[tid]
    total_pages = (len(t["sentences"]) + SENTENCES_PER_PAGE - 1) // SENTENCES_PER_PAGE
    sr = 1 if show_ru else 0
    rows = []
    if show_ru:
        rows.append([InlineKeyboardButton("🇧🇬 Скрыть перевод", callback_data=f"rtog_{tid}_{page}_0")])
    else:
        rows.append([InlineKeyboardButton("🇷🇺 Показать перевод", callback_data=f"rtog_{tid}_{page}_1")])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️ Назад", callback_data=f"rp_{tid}_{page-1}_{sr}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("▶️ Вперёд", callback_data=f"rp_{tid}_{page+1}_{sr}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton("📚 Все тексты", callback_data="menu_reading"),
                 InlineKeyboardButton("🏠 Меню", callback_data="back_main")])
    return InlineKeyboardMarkup(rows)


# ── session helpers ────────────────────────────────────────────────────────────

def start_session(context, mode, level_id):
    if level_id == "all":
        words = get_all_words()
        label = "Все уровни"
    else:
        lv = CEFR_LEVELS[level_id]
        words = [{**w, "_level": level_id} for w in lv["words"]]
        label = f"{lv['emoji']} {level_id} — {lv['label']}"
    random.shuffle(words)
    context.user_data["session"] = {
        "mode": mode, "level": level_id, "label": label,
        "words": words, "index": 0, "revealed": False,
    }


def cur_word(context):
    s = context.user_data.get("session")
    if not s or s["index"] >= len(s["words"]):
        return None
    return s["words"][s["index"]]


# ── command handlers ───────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    init_user(context)
    total = get_total_count()
    await update.message.reply_text(
        f"👋 *Добро пожаловать в болгарские флэшкарты\\!*\n\n"
        f"Учите болгарский язык по уровням — от A1 до B2\\.\n"
        f"📦 *{total} слов* с примерами предложений\n"
        f"📖 Тексты для чтения\n\n"
        f"Выберите режим ниже:",
        parse_mode="MarkdownV2",
        reply_markup=main_menu()
    )


async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    init_user(context)
    await update.message.reply_text("🏠 *Главное меню*", parse_mode="Markdown",
                                    reply_markup=main_menu())


# ── callback router ────────────────────────────────────────────────────────────

async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    d = q.data
    init_user(context)

    # ── main menu ──────────────────────────────────────────────────────────────
    if d == "back_main":
        await q.edit_message_text("🏠 *Главное меню*", parse_mode="Markdown", reply_markup=main_menu())
        return

    if d == "menu_study":
        await q.edit_message_text("📚 *Выберите уровень для изучения:*",
                                  parse_mode="Markdown", reply_markup=level_menu("study"))
        return

    if d == "menu_quiz":
        await q.edit_message_text("🎯 *Выберите уровень для теста:*",
                                  parse_mode="Markdown", reply_markup=level_menu("quiz"))
        return

    if d == "menu_reading":
        lines = "\n".join(
            f"{t['emoji']} *{t['title_bg']}* — {t['level']}"
            for t in TEXTS.values()
        )
        await q.edit_message_text(
            f"📖 *Тексты для чтения*\n\n{lines}\n\nВыберите текст:",
            parse_mode="Markdown", reply_markup=text_menu()
        )
        return

    if d == "menu_stats":
        stats = context.user_data["stats"]
        total = get_total_count()
        all_known = len(set(w for lid in CEFR_LEVELS for w in stats[lid]["known"]))
        lines = []
        for lid, lv in CEFR_LEVELS.items():
            k = len(set(stats[lid]["known"]))
            cnt = len(lv["words"])
            lines.append(f"{lv['emoji']} {lid}: ✅ {k}/{cnt}")
        pct = round(all_known / total * 100, 1) if total else 0
        text = (
            f"📊 *Ваш прогресс*\n\n"
            + "\n".join(lines)
            + f"\n\n🏆 Всего знаете: *{all_known}/{total}* ({pct}%)"
        )
        await q.edit_message_text(text, parse_mode="Markdown",
                                  reply_markup=InlineKeyboardMarkup(
                                      [[InlineKeyboardButton("🏠 Меню", callback_data="back_main")]]))
        return

    if d == "random_word":
        w = random.choice(get_all_words())
        text = (
            f"🔀 *Случайное слово*\n\n"
            f"🇧🇬 *{w['bg']}*\n"
            f"🔤 _{w['tr']}_\n"
            f"📖 _{w['example_bg']}_\n\n"
            f"🇷🇺 *{w['ru']}*\n"
            f"📖 _{w['example_ru']}_"
        )
        await q.edit_message_text(text, parse_mode="Markdown",
                                  reply_markup=InlineKeyboardMarkup([
                                      [InlineKeyboardButton("🔀 Ещё слово", callback_data="random_word")],
                                      [InlineKeyboardButton("🏠 Меню", callback_data="back_main")],
                                  ]))
        return

    # ── level selection ────────────────────────────────────────────────────────
    if d.startswith("lvl_"):
        _, mode, lid = d.split("_", 2)
        start_session(context, mode, lid)
        if mode == "study":
            await show_card(q, context)
        else:
            await show_quiz(q, context)
        return

    # ── reading ────────────────────────────────────────────────────────────────
    if d.startswith("text_"):
        tid = d[5:]
        await q.edit_message_text(reading_text(tid, 0, False), parse_mode="Markdown",
                                  reply_markup=reading_kb(tid, 0, False))
        return

    if d.startswith("rtog_"):
        _, tid, page, sr = d.split("_")
        page, sr = int(page), int(sr)
        await q.edit_message_text(reading_text(tid, page, bool(sr)), parse_mode="Markdown",
                                  reply_markup=reading_kb(tid, page, bool(sr)))
        return

    if d.startswith("rp_"):
        _, tid, page, sr = d.split("_")
        page, sr = int(page), int(sr)
        await q.edit_message_text(reading_text(tid, page, bool(sr)), parse_mode="Markdown",
                                  reply_markup=reading_kb(tid, page, bool(sr)))
        return

    # ── flashcard actions ──────────────────────────────────────────────────────
    if d.startswith("reveal_"):
        s = context.user_data.get("session")
        if s:
            s["revealed"] = True
        w = cur_word(context)
        if w and s:
            await q.edit_message_text(
                card_shown(w, s["index"], len(s["words"]), s["label"]),
                parse_mode="Markdown", reply_markup=kb_shown(s["index"])
            )
        return

    if d.startswith("known_"):
        s = context.user_data.get("session")
        w = cur_word(context)
        if w and s:
            lid = w.get("_level", s["level"])
            if lid != "all":
                context.user_data["stats"][lid]["known"].append(w["bg"])
                context.user_data["stats"][lid]["seen"] += 1
            s["index"] += 1
            s["revealed"] = False
        await show_card(q, context)
        return

    if d.startswith("unknown_"):
        s = context.user_data.get("session")
        w = cur_word(context)
        if w and s:
            lid = w.get("_level", s["level"])
            if lid != "all":
                context.user_data["stats"][lid]["unknown"].append(w["bg"])
                context.user_data["stats"][lid]["seen"] += 1
            s["index"] += 1
            s["revealed"] = False
        await show_card(q, context)
        return

    if d.startswith("skip_") or d.startswith("next_"):
        s = context.user_data.get("session")
        if s:
            s["index"] += 1
            s["revealed"] = False
        await show_card(q, context)
        return

    # ── quiz actions ───────────────────────────────────────────────────────────
    if d.startswith("qa_"):
        # qa_{correct}_{idx}
        parts = d.split("_")
        correct = parts[1] == "1"
        s = context.user_data.get("session")
        w = cur_word(context)
        if w and s:
            lid = w.get("_level", s["level"])
            if correct:
                if lid != "all":
                    context.user_data["stats"][lid]["known"].append(w["bg"])
                feedback = f"✅ *Правильно!*\n\n🇧🇬 *{w['bg']}* → 🇷🇺 *{w['ru']}*"
            else:
                if lid != "all":
                    context.user_data["stats"][lid]["unknown"].append(w["bg"])
                feedback = f"❌ *Неверно!*\n\nПравильный ответ: *{w['ru']}*\n🇧🇬 *{w['bg']}* → 🇷🇺 *{w['ru']}*"
            if lid != "all":
                context.user_data["stats"][lid]["seen"] += 1
            s["index"] += 1
            await q.edit_message_text(feedback, parse_mode="Markdown",
                                      reply_markup=InlineKeyboardMarkup([
                                          [InlineKeyboardButton("➡️ Следующий вопрос", callback_data="quiz_next")],
                                          [InlineKeyboardButton("🏠 Меню", callback_data="back_main")],
                                      ]))
        return

    if d == "quiz_next":
        await show_quiz(q, context)
        return

    if d == "quiz_restart":
        s = context.user_data.get("session")
        if s:
            start_session(context, "quiz", s["level"])
        await show_quiz(q, context)
        return


# ── card / quiz display ────────────────────────────────────────────────────────

async def show_card(q, context):
    s = context.user_data.get("session")
    if not s:
        await q.edit_message_text("Сессия не найдена.", reply_markup=main_menu())
        return
    w = cur_word(context)
    if not w:
        known = len(set(context.user_data["stats"].get(s["level"], {}).get("known", [])))
        await q.edit_message_text(
            f"🎉 *Сессия завершена\\!*\n\n"
            f"Изучено слов: *{len(s['words'])}*\n"
            f"✅ Знаете: *{known}*\n\n"
            f"Отличная работа\\! Продолжайте практиковаться 💪",
            parse_mode="MarkdownV2",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Повторить", callback_data=f"lvl_study_{s['level']}")],
                [InlineKeyboardButton("🏠 Меню", callback_data="back_main")],
            ])
        )
        return
    s["revealed"] = False
    await q.edit_message_text(
        card_hidden(w, s["index"], len(s["words"]), s["label"]),
        parse_mode="Markdown", reply_markup=kb_hidden(s["index"])
    )


async def show_quiz(q, context):
    s = context.user_data.get("session")
    if not s:
        await q.edit_message_text("Сессия не найдена.", reply_markup=main_menu())
        return
    w = cur_word(context)
    if not w:
        await q.edit_message_text(
            "🎉 *Тест завершён!*\n\nПроверьте прогресс в разделе 📊.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Повторить тест", callback_data="quiz_restart")],
                [InlineKeyboardButton("🏠 Меню", callback_data="back_main")],
            ])
        )
        return

    all_words = get_all_words()
    wrong_pool = [x["ru"] for x in all_words if x["ru"] != w["ru"]]
    options = random.sample(wrong_pool, min(3, len(wrong_pool))) + [w["ru"]]
    random.shuffle(options)

    total = len(s["words"])
    text = (
        f"🎯 *Тест* — {s['label']}\n"
        f"Вопрос {s['index']+1}/{total}\n"
        f"{'─'*30}\n\n"
        f"🇧🇬 *{w['bg']}*\n"
        f"🔤 _{w['tr']}_\n\n"
        f"📖 _{w['example_bg']}_\n\n"
        f"Как это по-русски?"
    )
    buttons = [
        [InlineKeyboardButton(opt, callback_data=f"qa_{'1' if opt == w['ru'] else '0'}_{s['index']}")]
        for opt in options
    ]
    buttons.append([InlineKeyboardButton("🏠 Меню", callback_data="back_main")])
    await q.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


# ── main ───────────────────────────────────────────────────────────────────────

def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN not set")
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("menu", cmd_menu))
    app.add_handler(CallbackQueryHandler(on_callback))

    if WEBHOOK_URL:
        app.run_webhook(listen="0.0.0.0", port=PORT,
                        url_path=BOT_TOKEN,
                        webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}")
    else:
        app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
