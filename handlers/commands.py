import handlers.start as start
import handlers.admin as admin
from handlers.admin import notify_dev
from utils.telegram import is_user_admin, set_cached_admins, mute_user, parse_duration
from utils.group_session import (
    handle_add_to_ad_command,
    handle_remove_from_ad_command,
    handle_link_command,
    handle_sr_command,
    handle_srlist_command,
    get_users_with_multiple_links,
    get_unverified_users,
    get_unverified_users_full,
    set_verification_phase,
    get_all_links_count,
    handle_summary_command,
    handle_close_group,
    get_formatted_user_link_list,
    handle_remind_command
)
from utils.message_tracker import track_message, delete_tracked_messages
from utils.message_tracker import delete_tracked_messages_with_progress
from datetime import timedelta
from telebot.types import ChatPermissions
from utils.db import is_command_enabled, get_custom_command
from bson import ObjectId
from handlers.duration import handle_set_deadline, handle_cancel_deadline

def handle_command(bot, bot_id: str, message, db):
    chat_id = message.chat.id
    text = message.text.strip()

    command = text.split()[0]

    if "@" in command:
        text = text.split("@")[0]

    # ✅ Save user metadata in DB
    try:
        db["users"].update_one(
            {"chat_id": chat_id, "bot_id": bot_id, "user_id": message.from_user.id},
            {"$set": {
                "username": message.from_user.username,
                "first_name": message.from_user.first_name,
                "last_name": message.from_user.last_name
            }},
            upsert=True
        )
    except Exception as e:
        notify_dev(bot, e, "DB update", message)

    try:
        if text == "/start":
            try:
                start.handle_start(bot, bot_id, message)
            except Exception as e:
                notify_dev(bot, e, "/start", message)

        elif text == "/help":
            try:
                help_text = (
                    "🤖 <b>Bot Help Menu</b>\n\n"
                    "👤 <b>General Commands:</b>\n"
                    "/s — Start the bot's link tracking\n"
                    "/c — Send a close GIF\n"
                    "/track — Turn on ad tracking\n"
                    "/d [duration] — Set a deadline (e.g., /d 2h or /d 30m)\n"
                    "/cd — Cancel the deadline\n"
                    "/count — Show how many users have dropped links\n"
                    "/remind — List users who have only dropped one link\n"
                    "/unsafe — List users who have not finished their tasks\n"
                    "/list — Show all active users\n"
                    "/ad — Mark a user as complete\n"
                    "/rad — Remove a user from the complete list\n"
                    "/sr — Ask a user for a screen recording\n"
                    "/srlist — List all users who need to send a screen recording\n"
                    "/srm — Mark a user as safe\n"
                    "/muteall — Mute all users who have not completed their tasks\n"
                    "/summary — Show a summary of the session\n"
                    "/e — End all tracking and clear all data\n\n"
                    "🛠️ <b>Admin Panel:</b>\n"
                    "/managegroups — Manage allowed groups (in private chat)"
                )
                msg = bot.send_message(chat_id, help_text, parse_mode="HTML")
                track_message(chat_id, msg.message_id, bot_id=bot_id)
            except Exception as e:
                notify_dev(bot, e, "/help", message)

        elif text == "/managegroups":
            try:
                admin.handle_manage_groups(bot, bot_id, message, db)
            except Exception as e:
                notify_dev(bot, e, "/managegroups", message)

        else:
            try:
                msg = bot.send_message(chat_id, "🤔 Unknown command. Use /help.")
                track_message(chat_id, msg.message_id, bot_id=bot_id)
            except Exception as e:
                notify_dev(bot, e, "Unknown command", message)

    except Exception as e:
        notify_dev(bot, e, "handle_command", message)


def handle_group_command(bot, bot_id: str, message, db):
    chat_id = message.chat.id
    user_id = message.from_user.id
    text = message.text.strip()

    command = text.split()[0]

    if "@" in command:
        text = text.split("@")[0]
    
    try:
        reply = get_custom_command(bot_id, text)
        if reply:
            try:
                msg = bot.send_message(chat_id, reply, parse_mode="HTML", disable_web_page_preview=True)
                track_message(chat_id, msg.message_id, bot_id=bot_id)
                return
            except Exception as e:
                notify_dev(bot, e, f"custom command {text}", message)

        if text in ["/start", "/s"]:
            try:
                start.handle_start_group(bot,bot_id, message)
            except Exception as e:
                notify_dev(bot, e, "/start (group)", message)

        elif text in ["/close", "/c"]:
            try:
                handle_close_group(bot,bot_id, message)
            except Exception as e:
                notify_dev(bot, e, "/close", message)

        elif text in ["/end", "/e"]:
            try:
                start.handle_cancel_group(bot,bot_id, message, db)
            except Exception as e:
                notify_dev(bot, e, "/end", message)

        elif text == "/refresh_admins":
            if is_user_admin(bot, chat_id, user_id):
                try:
                    admins = bot.get_chat_administrators(chat_id)
                    set_cached_admins(chat_id, [admin.user.id for admin in admins], bot_id=bot_id)
                    msg = bot.send_message(chat_id, "✅ Admin list refreshed.")
                    track_message(chat_id, msg.message_id, bot_id=bot_id)
                except Exception as e:
                    notify_dev(bot, e, "/refresh_admins", message)
                    try:
                        msg = bot.send_message(chat_id, "⚠️ Failed to refresh admins.")
                        track_message(chat_id, msg.message_id, bot_id=bot_id)
                    except:
                        pass

        elif text == "/rule":
            try:
                bot_data = db.bots.find_one({"_id": ObjectId(bot_id)})
                rules_text = bot_data.get("rules") if bot_data else None
                if not rules_text:
                    rules_text = (
                        "📛📛 <b>Likes Group Rules:</b>\n\n"
                        "💜 please follow these rules during each session:\n\n"
                        "1️⃣ <b>Link Drop Time</b>\n"
                        "🕐 You have 1 hour to share your tweet link in the group.\n\n"
                        "2️⃣ <b>1 Link Per Person</b>\n"
                        "➤ Only one post per user is allowed per session. No double Link ❌.\n\n"
                        "3️⃣ <b>TL id</b> 🆔\n"
                        "🔁 After 1 hour, we’ll start reposting all shared tweets on our TL account\n\n"
                        "4️⃣ <b>Like All Posts</b>\n"
                        "❤️ You must like all shared tweets, from top to bottom, until we post “Open” under the last tweet.\n\n"
                        "5️⃣ <b>Mark Completion</b>\n"
                        "✅ Once done, typing \"AD\" or \"All Done\" in the group is mandatory."
                    )
                msg = bot.send_message(chat_id, rules_text, parse_mode="HTML", disable_web_page_preview=True)
                track_message(chat_id, msg.message_id, bot_id=bot_id)
            except Exception as e:
                notify_dev(bot, e, "/rule", message)


        elif text in ["/verify", "/track", "/check"]:
            if is_user_admin(bot, chat_id, user_id):
                try:
                    set_verification_phase(bot_id,chat_id)
                    permissions = ChatPermissions(
                        can_send_messages=True,
                        can_send_media_messages=True,
                        can_send_other_messages=True,
                        can_add_web_page_previews=True
                    )
                    bot.set_chat_permissions(chat_id, permissions)
                    msg = bot.send_message(chat_id, "✅ Ad tracking has started! I will track 'ad', 'all done', 'all dn', 'done' messages.")
                    track_message(chat_id, msg.message_id, bot_id=bot_id)
                except Exception as e:
                    notify_dev(bot, e, "/verify", message)
            else:
                msg = bot.send_message(chat_id, "❌ Only admins can enable verification.")
                track_message(chat_id, msg.message_id, bot_id=bot_id)

        elif text == "/count":
            if not is_user_admin(bot, chat_id, user_id):
                msg = bot.send_message(chat_id, "❌ Only admins can use this command.")
                track_message(chat_id, msg.message_id, bot_id=bot_id)
                return
            try:
                count = get_all_links_count(bot_id,chat_id)
                msg = bot.send_message(chat_id, f"📊 Total Users: {count}")
                track_message(chat_id, msg.message_id, bot_id=bot_id)
            except Exception as e:
                notify_dev(bot, e, "/count", message)

        elif text == "/list":
            if not is_user_admin(bot, chat_id, user_id):
                msg = bot.send_message(chat_id, "❌ Only admins can use this command.")
                track_message(chat_id, msg.message_id, bot_id=bot_id)
                return
            try:
                result, count = get_formatted_user_link_list(bot_id,chat_id)
                if not result:
                    msg = bot.send_message(chat_id, "ℹ️ No users have submitted X links yet.")
                else:
                    msg = bot.send_message(chat_id, f"<b>🚨 USERS LIST 🚨: {count}</b>\n\n{result}", parse_mode="HTML", disable_web_page_preview=True)
                track_message(chat_id, msg.message_id, bot_id=bot_id)
            except Exception as e:
                notify_dev(bot, e, "/list", message)

        elif text == "/unsafe":
            if not is_user_admin(bot, chat_id, user_id):
                msg = bot.send_message(chat_id, "❌ Only admins can use this command.")
                track_message(chat_id, msg.message_id, bot_id=bot_id)
                return
            try:
                users = get_unverified_users(bot_id,chat_id)
                if users == "notVerifyingphase":
                    msg = bot.send_message(chat_id, "⚠️ This session is not in the verifying phase.")
                    track_message(chat_id, msg.message_id, bot_id=bot_id)
                    return

                if not users:
                    msg = bot.send_message(chat_id, "✅ All users are safe.")
                else:
                    msg_text = "<b>⚠️ These users did not send 'ad' or 'all done':</b>\n"
                    for user in users:
                        msg_text += f"\n• {user}"
                    msg = bot.send_message(chat_id, msg_text, parse_mode="HTML")
                track_message(chat_id, msg.message_id, bot_id=bot_id)
            except Exception as e:
                notify_dev(bot, e, "/unsafe", message)

        elif text.startswith("/muteunsafe") or text.startswith("/muteall"):
            if not is_user_admin(bot, chat_id, user_id):
                msg = bot.send_message(chat_id, "❌ Only admins can use this command.")
                track_message(chat_id, msg.message_id, bot_id=bot_id)
                return
            try:
                args = text.split(maxsplit=1)
                duration = parse_duration(args[1]) if len(args) > 1 else timedelta(days=3)
                if duration is None:
                    msg = bot.send_message(chat_id, "⚠️ Invalid duration format. Use formats like: 2d 10h 5m")
                    track_message(chat_id, msg.message_id, bot_id=bot_id)
                    return

                unverified = get_unverified_users_full(bot_id,chat_id)
                if unverified == "notVerifyingphase":
                    msg = bot.send_message(chat_id, "⚠️ This session is not in the verifying phase.")
                    track_message(chat_id, msg.message_id, bot_id=bot_id)
                    return

                if not unverified:
                    msg = bot.send_message(chat_id, "✅ No unverified users to mute.")
                    track_message(chat_id, msg.message_id, bot_id=bot_id)
                    return

                success_log, failed = [], []
                for user in unverified:
                    uid = user["user_id"]
                    fname = user.get("first_name", "User")
                    if mute_user(bot, chat_id, uid, duration):
                        mention = f'<a href="tg://user?id={uid}">{fname}</a>'
                        success_log.append(f"• {mention} (ID: <code>{uid}</code>)")
                    else:
                        failed.append(fname)

                msg_text = "<b>🔇 Muted the following unSafe users:</b>\n\n" + "\n".join(success_log)
                if failed:
                    msg_text += "\n\n⚠️ <b>Failed to mute:</b>\n" + "\n".join(f"• {u}" for u in failed)

                msg = bot.send_message(chat_id, msg_text, parse_mode="HTML")
                track_message(chat_id, msg.message_id, bot_id=bot_id)
            except Exception as e:
                notify_dev(bot, e, "/muteunsafe", message)


        elif text == "/remind":
            try:
                handle_remind_command(bot,bot_id, message)
            except Exception as e:
                notify_dev(bot, e, "/remind", message)
        
        elif text == "/summary":
            try:
                handle_summary_command(bot,bot_id, message)
            except Exception as e:
                notify_dev(bot, e, "/summary", message)
        elif text.startswith("/link"):
            try:
                handle_link_command(bot,bot_id,message)
            except Exception as e:
                notify_dev(bot, e, "/link", message)

        elif text.startswith("/d"):
            try:
                handle_set_deadline(bot,bot_id, message, text.split(maxsplit=1)[1])
            except Exception as e:
                notify_dev(bot, e, "/d", message)
        elif text == "/cd":
            try:
                handle_cancel_deadline(bot,bot_id, message)
            except Exception as e:
                notify_dev(bot, e, "/cd", message)
        elif text in ["/ad", "/add_to_ad", "/srm"]:
            try:
                handle_add_to_ad_command(bot,bot_id, message)
            except Exception as e:
                notify_dev(bot, e, "/add_to_ad", message)
        elif text in ["/rad", "/remove_from_ad"]:
            try:
                handle_remove_from_ad_command(bot,bot_id, message)
            except Exception as e:
                notify_dev(bot, e, "/remove_from_ad", message)

        elif text == "/sr":
            try:
                handle_sr_command(bot,bot_id, message)
            except Exception as e:
                notify_dev(bot, e, "/sr", message)

        elif text == "/srlist":
            try:
                handle_srlist_command(bot,bot_id, message)
            except Exception as e:
                notify_dev(bot, e, "/srlist", message)

        elif text in ["/clear", "/clean","/delete"]:
            try:

                if not is_user_admin(bot, message.chat.id, message.from_user.id):
                    msg = bot.reply_to(message, "❌ Only admins can use this command.")
                    track_message(message.chat.id, msg.message_id, bot_id=bot_id)
                    return
                delete_tracked_messages_with_progress(bot, message.chat.id, bot_id=bot_id)
            except Exception as e:
                notify_dev(bot, e, "/clear", message)

    except Exception as e:
        notify_dev(bot, e, "handle_group_command", message)

