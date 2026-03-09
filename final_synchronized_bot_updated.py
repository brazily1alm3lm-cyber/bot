import asyncio
import logging
import os
import json
import time
from telethon import TelegramClient, events, functions, types
from telethon.sessions import StringSession
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters

# --- إعدادات البوت ---
API_ID = 24386117
API_HASH = 'f164b741f2964e7c0665a0a2d3db7287'
BOT_TOKEN = '8731571658:AAG9GTX8QOtdRaAYnaGHTKOaqwzBqwYPCVY'
OWNER_ID = 6272162286

# كود الـ String Session الخاص بك
STRING_SESSION = '1BJWap1wBuy3evepmxfdi264sjqC8EUQskCrZMv1z759RsrP8b4ilAzxdwHw4xZtEcTEtSpAluspow41-sU-ZqturgqIyygUreE8bwRUutx9QQXxMGS1EPm9_6KuJgoe9njdrLoi8B2n4N6pKn7zFeNLcUahN0t6w74f0FyfYwSQl1c08KIgaEA1Ks89EoEK3V0sXk3_jz1Xa3og5mckxj7k4dh5Kkef8K4GHARXv_-y2XeXJX5Y7mdu--ynGtzy4rR_kXMzhTJ2lJxlPyLwpfMUgd3nqKqlpw3Irrw52RETaDfd1cMCfkrxMqrblsW1HBGyqpFUbaBvpmpUso4BQJOy1eytg1iE=' 
# ------------------------------------------

# إعداد السجلات (فقط الأخطاء Errors)
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.ERROR)
logger = logging.getLogger(__name__)

# ملفات تخزين البيانات
GROUPS_FILE = 'groups_data.json'
SETTINGS_FILE = 'bot_settings.json'

def load_json_file(filename, default_value={}):
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return default_value
    return default_value

def save_json_file(data, filename):
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error(f"Error saving {filename}: {e}")

# تحميل الإعدادات والمجموعات
groups_data = load_json_file(GROUPS_FILE)
bot_settings = load_json_file(SETTINGS_FILE, default_value={'is_running': False, 'broadcast_message': 'رسالة تلقائية من البوت', 'broadcast_interval': 300})

is_running = bot_settings['is_running']
broadcast_message = bot_settings['broadcast_message']
broadcast_interval = bot_settings['broadcast_interval']

reply_map = {}
# لتخزين وقت آخر إرسال لكل مجموعة
last_sent_times = {}

# عميل Telethon باستخدام StringSession
client = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH)

# تطبيق البوت
app = ApplicationBuilder().token(BOT_TOKEN).build()

async def save_bot_settings():
    global is_running, broadcast_message, broadcast_interval
    bot_settings.update({'is_running': is_running, 'broadcast_message': broadcast_message, 'broadcast_interval': broadcast_interval})
    save_json_file(bot_settings, SETTINGS_FILE)

async def get_safe_entity(chat_id):
    try:
        return await client.get_entity(int(chat_id))
    except Exception:
        try:
            await client.get_dialogs()
            return await client.get_entity(int(chat_id))
        except Exception as e:
            logger.error(f"Critical entity error for {chat_id}: {e}")
            return None

async def send_message_safe(chat_id, message):
    try:
        entity = await get_safe_entity(chat_id)
        if entity:
            await client.send_message(entity, message, parse_mode='md')
            return True
    except Exception as e:
        logger.error(f"Failed to send to {chat_id}: {e}")
    return False

async def broadcast_task():
    global is_running, broadcast_message, broadcast_interval, groups_data, last_sent_times
    
    while True:
        if is_running and groups_data:
            current_time = time.time()
            bold_msg = f"**{broadcast_message}**"
            
            tasks = []
            for cid, info in groups_data.items():
                if not info.get('active', True):
                    continue
                
                # تحديد الوقت المطلوب لهذه المجموعة (مخصص أو عام)
                custom_interval = info.get('custom_interval')
                interval = custom_interval if custom_interval is not None else broadcast_interval
                
                # التحقق مما إذا كان الوقت قد حان للإرسال
                last_sent = last_sent_times.get(cid, 0)
                if current_time - last_sent >= interval:
                    tasks.append(process_single_broadcast(cid, bold_msg))
            
            if tasks:
                await asyncio.gather(*tasks)
        
        # فحص كل 5 ثوانٍ لضمان الدقة في المواعيد المخصصة المختلفة
        await asyncio.sleep(5)

async def process_single_broadcast(cid, message):
    global last_sent_times
    success = await send_message_safe(cid, message)
    if success:
        last_sent_times[cid] = time.time()

# --- واجهات البوت ---

async def get_main_keyboard():
    status = "شغال ✅" if is_running else "متوقف ❌"
    keyboard = [
        [InlineKeyboardButton("إيقاف الإرسال" if is_running else "تشغيل الإرسال", callback_data="toggle_running")],
        [InlineKeyboardButton("تعديل الرسالة", callback_data="edit_msg"), InlineKeyboardButton("تعديل الوقت العام", callback_data="edit_time")],
        [InlineKeyboardButton("إدارة المجموعات 👥", callback_data="manage_groups")],
        [InlineKeyboardButton("إضافة مجموعة ➕", callback_data="add_group")]
    ]
    text = f"لوحة تحكم البوت:\nالحالة: {status}\nالوقت العام: {broadcast_interval} ثانية\nالمجموعات: {len(groups_data)}"
    return text, InlineKeyboardMarkup(keyboard)

async def get_manage_groups_keyboard():
    if not groups_data:
        return "لا توجد مجموعات.", InlineKeyboardMarkup([[InlineKeyboardButton("العودة 🔙", callback_data="back_to_main")]])
    keyboard = [[InlineKeyboardButton(f"{'✅' if info.get('active', True) else '⏸'} {info['title']}", callback_data=f"group_{cid}")] for cid, info in groups_data.items()]
    keyboard.append([InlineKeyboardButton("العودة 🔙", callback_data="back_to_main")])
    return "اختر مجموعة لإدارتها أو تخصيص وقتها:", InlineKeyboardMarkup(keyboard)

async def get_group_detail_keyboard(chat_id):
    info = groups_data.get(chat_id)
    if not info: return None, None
    
    interval_text = f"{info['custom_interval']} ثانية (مخصص)" if info.get('custom_interval') is not None else "الوقت العام"
    
    keyboard = [
        [InlineKeyboardButton("إيقاف مؤقت" if info.get('active', True) else "تشغيل", callback_data=f"toggle_group_{chat_id}")],
        [InlineKeyboardButton("تعديل وقت المجموعة", callback_data=f"edit_group_time_{chat_id}")],
    ]
    
    if info.get('custom_interval') is not None:
        keyboard.append([InlineKeyboardButton("إعادة للوقت العام 🔄", callback_data=f"reset_group_time_{chat_id}")])
        
    keyboard.extend([
        [InlineKeyboardButton("حذف المجموعة 🗑", callback_data=f"delete_group_{chat_id}")],
        [InlineKeyboardButton("العودة 🔙", callback_data="manage_groups")]
    ])
    
    text = f"إدارة: {info['title']}\nالحالة: {'نشطة' if info.get('active', True) else 'متوقفة'}\nالوقت الحالي: {interval_text}"
    return text, InlineKeyboardMarkup(keyboard)

# --- المعالجات ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    text, reply_markup = await get_main_keyboard()
    await update.message.reply_text(text, reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global is_running, groups_data, last_sent_times
    query = update.callback_query
    if query.from_user.id != OWNER_ID: return
    await query.answer()
    
    if query.data == "toggle_running":
        is_running = not is_running
        if is_running:
            # تصفير أوقات الإرسال لبدء النشر فوراً عند التشغيل
            last_sent_times = {}
        await save_bot_settings()
        text, reply_markup = await get_main_keyboard()
        await query.edit_message_text(text, reply_markup=reply_markup)
        
    elif query.data == "edit_msg":
        await query.message.reply_text("أرسل الرسالة الجديدة:")
        context.user_data['state'] = 'waiting_for_msg'
        
    elif query.data == "edit_time":
        await query.message.reply_text("أرسل الوقت العام الجديد بالثواني:")
        context.user_data['state'] = 'waiting_for_time'
        
    elif query.data == "add_group":
        await query.message.reply_text("أرسل المعرف أو الرابط:")
        context.user_data['state'] = 'waiting_for_group'
        
    elif query.data == "manage_groups":
        text, reply_markup = await get_manage_groups_keyboard()
        await query.edit_message_text(text, reply_markup=reply_markup)
        
    elif query.data.startswith("group_"):
        text, reply_markup = await get_group_detail_keyboard(query.data.split("_")[1])
        if text: await query.edit_message_text(text, reply_markup=reply_markup)
        
    elif query.data.startswith("toggle_group_"):
        cid = query.data.split("_")[2]
        if cid in groups_data:
            groups_data[cid]['active'] = not groups_data[cid].get('active', True)
            save_json_file(groups_data, GROUPS_FILE)
            text, reply_markup = await get_group_detail_keyboard(cid)
            await query.edit_message_text(text, reply_markup=reply_markup)
            
    elif query.data.startswith("edit_group_time_"):
        cid = query.data.split("_")[3]
        await query.message.reply_text(f"أرسل الوقت المخصص لمجموعة {groups_data[cid]['title']} بالثواني:")
        context.user_data['state'] = 'waiting_for_group_time'
        context.user_data['target_group'] = cid
        
    elif query.data.startswith("reset_group_time_"):
        cid = query.data.split("_")[3]
        if cid in groups_data:
            groups_data[cid]['custom_interval'] = None
            save_json_file(groups_data, GROUPS_FILE)
            text, reply_markup = await get_group_detail_keyboard(cid)
            await query.edit_message_text(text, reply_markup=reply_markup)
            
    elif query.data.startswith("delete_group_"):
        cid = query.data.split("_")[2]
        if cid in groups_data:
            del groups_data[cid]
            save_json_file(groups_data, GROUPS_FILE)
            text, reply_markup = await get_manage_groups_keyboard()
            await query.edit_message_text(text, reply_markup=reply_markup)
            
    elif query.data == "back_to_main":
        text, reply_markup = await get_main_keyboard()
        await query.edit_message_text(text, reply_markup=reply_markup)

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global broadcast_message, broadcast_interval, groups_data
    if update.effective_user.id != OWNER_ID: return
    state = context.user_data.get('state')
    
    if state == 'waiting_for_msg':
        broadcast_message = update.message.text
        await save_bot_settings()
        context.user_data['state'] = None
        await update.message.reply_text("تم تحديث الرسالة!")
        
    elif state == 'waiting_for_time':
        try:
            broadcast_interval = int(update.message.text)
            await save_bot_settings()
            context.user_data['state'] = None
            await update.message.reply_text(f"تم تحديث الوقت العام إلى {broadcast_interval} ثانية!")
        except:
            await update.message.reply_text("أدخل رقماً صحيحاً.")
            
    elif state == 'waiting_for_group_time':
        cid = context.user_data.get('target_group')
        try:
            val = int(update.message.text)
            if cid in groups_data:
                groups_data[cid]['custom_interval'] = val
                save_json_file(groups_data, GROUPS_FILE)
                await update.message.reply_text(f"تم تخصيص وقت {val} ثانية لمجموعة {groups_data[cid]['title']}!")
            context.user_data['state'] = None
        except:
            await update.message.reply_text("أدخل رقماً صحيحاً.")
            
    elif state == 'waiting_for_group':
        try:
            entity = await client.get_entity(update.message.text)
            cid = str(entity.id)
            if cid in groups_data: await update.message.reply_text("موجودة بالفعل.")
            else:
                groups_data[cid] = {"title": getattr(entity, 'title', 'مجموعة'), "active": True, "custom_interval": None}
                save_json_file(groups_data, GROUPS_FILE)
                await update.message.reply_text(f"تمت الإضافة: {groups_data[cid]['title']}")
            context.user_data['state'] = None
        except Exception as e:
            await update.message.reply_text(f"خطأ: {e}")
            
    elif update.message.reply_to_message:
        info = reply_map.get(update.message.reply_to_message.message_id)
        if info:
            try:
                entity = await get_safe_entity(info['chat_id'])
                if entity:
                    await client.send_message(entity, f"**{update.message.text}**", reply_to=info['msg_id'], parse_mode='md')
                    await update.message.reply_text("تم الرد!")
            except Exception as e:
                logger.error(f"Reply error: {e}")

@client.on(events.NewMessage)
async def handle_new_message(event):
    if not event.is_group or not event.is_reply: return
    reply_to_msg = await event.get_reply_message()
    me = await client.get_me()
    if reply_to_msg and reply_to_msg.sender_id == me.id:
        chat = await event.get_chat()
        chat_id_link = str(chat.id).replace('-100', '') if str(chat.id).startswith('-100') else str(chat.id)
        msg_link = f"https://t.me/c/{chat_id_link}/{event.id}"
        alert = (f"🔔 **رد جديد!**\n👥 **الجروب:** {getattr(chat, 'title', 'غير معروف')}\n💬 **المحتوى:** {event.text}")
        sent_msg = await app.bot.send_message(chat_id=OWNER_ID, text=alert, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("الرسالة", url=msg_link)]]), parse_mode='Markdown')
        reply_map[sent_msg.message_id] = {'chat_id': chat.id, 'msg_id': event.id}

async def main():
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    
    await client.start()
    
    asyncio.create_task(broadcast_task())
    async with app:
        await app.initialize()
        await app.start()
        await app.updater.start_polling()
        await client.run_until_disconnected()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.error(f"Critical error: {e}")
