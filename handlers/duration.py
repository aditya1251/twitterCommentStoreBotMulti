from utils.redis_client import get_redis
import time
import json
from utils.group_session import (
    is_group_verifying,
    handle_close_group,
)
from datetime import datetime, timedelta
from utils.telegram import parse_duration

def set_group_deadline(bot_id, group_id, seconds):
    r = get_redis()
    deadlines = json.loads(r.get(f"deadlines:{bot_id}") or "{}")
    deadlines[str(group_id)] = {
        "seconds": seconds,
        "timestamp": int(time.time())
    }
    r.set(f"deadlines:{bot_id}", json.dumps(deadlines))

def cancel_group_deadline(bot_id, group_id):
    r = get_redis()
    deadlines = json.loads(r.get(f"deadlines:{bot_id}") or "{}")
    if str(group_id) in deadlines:
        deadlines.pop(str(group_id))
        r.set(f"deadlines:{bot_id}", json.dumps(deadlines))

from apscheduler.schedulers.background import BackgroundScheduler
scheduler = BackgroundScheduler()
scheduler.start()

def schedule_group_close(bot, bot_id, group_id, seconds):
    scheduler.add_job(
    handle_close_group_due_to_deadline,
    'date',
    run_date=datetime.now() + timedelta(seconds=seconds),  # ✅ datetime object
    args=[bot, bot_id, group_id]
)


def handle_close_group_due_to_deadline(bot, bot_id, group_id):
    # Create a fake Message object with chat.id = group_id
    class FakeMessage:
        class Chat:
            id = group_id
        chat = Chat()
    message = FakeMessage()

    # Close the group
    handle_close_group(bot, bot_id, message)
    
    # Remove deadline from Redis
    cancel_group_deadline(bot_id, group_id)
    bot.send_message(group_id, "⏰ Deadline reached! Group session is now closed.")

def handle_set_deadline(bot, bot_id, message, duration_str):
    td = parse_duration(duration_str)
    if not td:
        bot.send_message(message.chat.id, "⚠️ Invalid duration format. Example: 2h 30m")
        return

    seconds = int(td.total_seconds())

    if not is_group_verifying(bot_id, message.chat.id):
        bot.send_message(message.chat.id, "⚠️ Can only set a deadline during verifying phase.")
        return

    set_group_deadline(bot_id, message.chat.id, seconds)
    schedule_group_close(bot, bot_id, message.chat.id, seconds)
    bot.send_message(message.chat.id, f"✅ Deadline set for {duration_str}.")

def handle_cancel_deadline(bot, bot_id, message):
    cancel_group_deadline(bot_id, message.chat.id)
    bot.send_message(message.chat.id, "✅ Deadline canceled.")
