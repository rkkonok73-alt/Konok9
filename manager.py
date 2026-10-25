"""
Telegram Multi-Bot Manager — starter template
IMPORTANT:
- Do NOT paste your bot token into this file.
- Set MANAGER_BOT_TOKEN and ADMIN_ID as environment variables on your hosting service.
- Run only ZIP files containing code you own or trust. Python files can execute arbitrary code.
- This starter launches child Python processes. Your host must permit long-running subprocesses.
"""
import os
import re
import zipfile
import shutil
import asyncio
import logging
import signal
from pathlib import Path

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# Set these in your hosting provider's Environment Variables / Secrets panel.
TOKEN = os.environ["MANAGER_BOT_TOKEN"]
ADMIN_ID = int(os.environ["ADMIN_ID"])
ROOT = Path(os.environ.get("BOT_DATA_DIR", "bot_data")).resolve()
PROJECTS = ROOT / "projects"
LOGS = ROOT / "logs"

MAX_ZIP_BYTES = 20 * 1024 * 1024
MAX_EXTRACTED_BYTES = 100 * 1024 * 1024
MAX_FILES = 500

ROOT.mkdir(parents=True, exist_ok=True)
PROJECTS.mkdir(parents=True, exist_ok=True)
LOGS.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)

# name -> asyncio subprocess
running = {}


def is_admin(update: Update) -> bool:
    user = update.effective_user
    return bool(user and user.id == ADMIN_ID)


def safe_name(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_-]", "_", value.strip())
    return value[:32] or "bot"


async def deny(update: Update) -> None:
    if update.effective_message:
        await update.effective_message.reply_text(
            "⛔ এই Manager Bot শুধু Admin ব্যবহার করতে পারবে।"
        )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update):
        return await deny(update)
    await update.effective_message.reply_text(
        "🤖 Multi-Bot Manager চালু আছে।\n\n"
        "একটি ZIP পাঠাও—ZIP-এর root অথবা top-level bot folder-এ main.py থাকতে হবে।\n\n"
        "কমান্ড:\n"
        "/bots — ইনস্টল করা বট\n"
        "/startbot NAME — বট চালু\n"
        "/stopbot NAME — বট বন্ধ\n"
        "/status — চলমান বটের অবস্থা\n"
        "/logs NAME — শেষের লগ\n"
        "/help — সাহায্য\n\n"
        "শুধু নিজের বা বিশ্বস্ত Python কোড আপলোড করবে।"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await start(update, context)


async def receive_zip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update):
        return await deny(update)

    message = update.effective_message
    document = message.document
    if not document or not (document.file_name or "").lower().endswith(".zip"):
        return await message.reply_text("একটি .zip ফাইল পাঠাও।")

    if document.file_size and document.file_size > MAX_ZIP_BYTES:
        return await message.reply_text("ZIP সর্বোচ্চ 20 MB হতে পারবে।")

    temporary_zip = ROOT / "incoming.zip"
    staging = ROOT / "staging"

    try:
        telegram_file = await context.bot.get_file(document.file_id)
        await telegram_file.download_to_drive(custom_path=temporary_zip)

        with zipfile.ZipFile(temporary_zip) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_FILES:
                return await message.reply_text("ZIP-এ ফাইলের সংখ্যা 500-এর বেশি।")
            if sum(entry.file_size for entry in entries) > MAX_EXTRACTED_BYTES:
                return await message.reply_text("Extract করা ফাইলের মোট সাইজ 100 MB-এর বেশি।")

            # Reject path traversal and symlinks.
            for entry in entries:
                path = Path(entry.filename)
                if path.is_absolute() or ".." in path.parts or entry.filename.startswith(("/", "\\")):
                    return await message.reply_text("ZIP-এ অনিরাপদ path আছে; বাতিল করা হয়েছে।")
                mode = (entry.external_attr >> 16) & 0o170000
                if mode == 0o120000:
                    return await message.reply_text("ZIP-এ symlink আছে; বাতিল করা হয়েছে।")

            shutil.rmtree(staging, ignore_errors=True)
            staging.mkdir(parents=True, exist_ok=True)
            archive.extractall(staging)

        candidates = []
        if (staging / "main.py").is_file():
            candidates.append((staging, safe_name(Path(document.file_name).stem)))
        else:
            for child in staging.iterdir():
                if child.is_dir() and (child / "main.py").is_file():
                    candidates.append((child, safe_name(child.name)))

        if not candidates:
            shutil.rmtree(staging, ignore_errors=True)
            return await message.reply_text(
                "ZIP-এ main.py পাওয়া যায়নি। Root বা top-level bot folder-এ main.py রাখো।"
            )

        installed = []
        for source, name in candidates:
            destination = PROJECTS / name
            if name in running and running[name].returncode is None:
                continue
            shutil.rmtree(destination, ignore_errors=True)
            shutil.copytree(source, destination)
            (LOGS / f"{name}.log").touch(exist_ok=True)
            installed.append(name)

        shutil.rmtree(staging, ignore_errors=True)
        if installed:
            await message.reply_text(
                "✅ ইনস্টল হয়েছে: " + ", ".join(installed) +
                "\nচালাতে: /startbot " + installed[0] +
                "\n\nনোট: প্রতিটি বটের requirements.txt-এর প্যাকেজ আলাদাভাবে প্রস্তুত করতে হবে।"
            )
        else:
            await message.reply_text("নতুন বট ইনস্টল হয়নি; নামটি হয়তো ইতিমধ্যে চলছে।")

    except zipfile.BadZipFile:
        await message.reply_text("ফাইলটি সঠিক ZIP নয়।")
    except Exception as error:
        logging.exception("ZIP upload failed")
        await message.reply_text(f"ZIP প্রসেস করা যায়নি: {type(error).__name__}")
    finally:
        temporary_zip.unlink(missing_ok=True)


async def list_bots(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update):
        return await deny(update)
    names = sorted(
        path.name for path in PROJECTS.iterdir()
        if path.is_dir() and (path / "main.py").is_file()
    )
    await update.effective_message.reply_text(
        "ইনস্টল করা বট:\n" + ("\n".join(f"• {name}" for name in names) if names else "এখনো কোনো বট নেই।")
    )


async def start_bot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update):
        return await deny(update)
    if not context.args:
        return await update.effective_message.reply_text("ব্যবহার: /startbot NAME")

    name = safe_name(context.args[0])
    folder = PROJECTS / name
    if not (folder / "main.py").is_file():
        return await update.effective_message.reply_text("main.py-সহ বট পাওয়া যায়নি। /bots দেখো।")

    current = running.get(name)
    if current and current.returncode is None:
        return await update.effective_message.reply_text(f"{name} ইতিমধ্যে চলছে।")

    log_handle = open(LOGS / f"{name}.log", "ab", buffering=0)
    try:
        process = await asyncio.create_subprocess_exec(
            "python", "-u", "main.py",
            cwd=str(folder),
            stdout=log_handle,
            stderr=asyncio.subprocess.STDOUT,
            start_new_session=True,
        )
        running[name] = process
        await update.effective_message.reply_text(
            f"▶️ {name} চালু করার অনুরোধ পাঠানো হয়েছে (PID {process.pid})।\n/logs {name}"
        )
    except Exception as error:
        log_handle.close()
        await update.effective_message.reply_text(f"চালু করা যায়নি: {type(error).__name__}")


async def stop_bot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update):
        return await deny(update)
    if not context.args:
        return await update.effective_message.reply_text("ব্যবহার: /stopbot NAME")

    name = safe_name(context.args[0])
    process = running.get(name)
    if not process or process.returncode is not None:
        return await update.effective_message.reply_text(f"{name} চলছে না।")

    try:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            await asyncio.wait_for(process.wait(), timeout=8)
        except asyncio.TimeoutError:
            os.killpg(process.pid, signal.SIGKILL)
            await process.wait()
        await update.effective_message.reply_text(f"⏹️ {name} বন্ধ হয়েছে।")
    except ProcessLookupError:
        await update.effective_message.reply_text(f"{name} ইতিমধ্যে বন্ধ।")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update):
        return await deny(update)
    rows = []
    for folder in sorted(PROJECTS.iterdir()):
        if folder.is_dir() and (folder / "main.py").is_file():
            process = running.get(folder.name)
            state = "RUNNING" if process and process.returncode is None else "STOPPED"
            rows.append(f"{folder.name}: {state}" + (f" (PID {process.pid})" if state == "RUNNING" else ""))
    await update.effective_message.reply_text("\n".join(rows) if rows else "কোনো বট ইনস্টল নেই।")


async def logs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update):
        return await deny(update)
    if not context.args:
        return await update.effective_message.reply_text("ব্যবহার: /logs NAME")
    name = safe_name(context.args[0])
    path = LOGS / f"{name}.log"
    if not path.exists():
        return await update.effective_message.reply_text("লগ পাওয়া যায়নি।")
    content = path.read_bytes()[-3500:].decode("utf-8", errors="replace")
    await update.effective_message.reply_text(content or "(লগ খালি)")


def main() -> None:
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("bots", list_bots))
    application.add_handler(CommandHandler("startbot", start_bot))
    application.add_handler(CommandHandler("stopbot", stop_bot))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("logs", logs))
    application.add_handler(MessageHandler(filters.Document.ALL, receive_zip))
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
