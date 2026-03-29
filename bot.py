import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, LabeledPrice, PreCheckoutQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from dotenv import load_dotenv
import os
from datetime import datetime, timedelta
import aiosqlite

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
ADMIN = int(os.getenv("ADMIN_ID"))
COURSE = os.getenv("COURSE_LINK")
bot = Bot(token=TOKEN)
dp = Dispatcher()
DB = "baza.db"

class Form(StatesGroup):
    reg = State()
    photo = State()
    email = State()

async def init_db():
    async with aiosqlite.connect(DB) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, platform TEXT, niche TEXT, city TEXT, country TEXT, is_pro INTEGER DEFAULT 0, pro_expires TEXT, rating INTEGER DEFAULT 100)")
        await db.execute("CREATE TABLE IF NOT EXISTS subs (from_id INTEGER, to_id INTEGER, status TEXT DEFAULT 'pending', UNIQUE(from_id, to_id))")
        await db.execute("CREATE TABLE IF NOT EXISTS photos (id INTEGER PRIMARY KEY, user_id INTEGER, prompt TEXT, status TEXT DEFAULT 'pending')")
        await db.execute("CREATE TABLE IF NOT EXISTS charity (id INTEGER PRIMARY KEY, name TEXT, age INTEGER, story TEXT, goal INTEGER, collected INTEGER DEFAULT 0, receipt TEXT, status TEXT DEFAULT 'active')")
        await db.commit()

async def get_user(uid):
    async with aiosqlite.connect(DB) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM users WHERE user_id=?", (uid,))
        return await cur.fetchone()

async def add_user(uid, uname, platform, niche, city, country):
    async with aiosqlite.connect(DB) as db:
        await db.execute("INSERT OR REPLACE INTO users VALUES (?,?,?,?,?,?,?,?,?)", (uid, uname, platform, niche, city, country, 0, None, 100))
        await db.commit()

async def set_pro(uid, days):
    exp = datetime.now() + timedelta(days=days)
    async with aiosqlite.connect(DB) as db:
        await db.execute("UPDATE users SET is_pro=1, pro_expires=? WHERE user_id=?", (exp.isoformat(), uid))
        await db.commit()

async def cancel_pro(uid):    async with aiosqlite.connect(DB) as db:
        await db.execute("UPDATE users SET is_pro=0, pro_expires=None WHERE user_id=?", (uid,))
        await db.commit()

async def find_users(niche, city, exclude, limit=10):
    async with aiosqlite.connect(DB) as db:
        db.row_factory = aiosqlite.Row
        q = "SELECT * FROM users WHERE user_id!=? AND niche=?"
        p = [exclude, niche]
        if city:
            q += " AND city=?"
            p.append(city)
        q += " ORDER BY rating DESC LIMIT ?"
        p.append(limit)
        cur = await db.execute(q, p)
        return await cur.fetchall()

async def add_sub(from_id, to_id):
    async with aiosqlite.connect(DB) as db:
        await db.execute("INSERT OR IGNORE INTO subs VALUES (?,?,?)", (from_id, to_id, 'pending'))
        await db.commit()

async def add_photo(uid, prompt):
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute("INSERT INTO photos (user_id, prompt) VALUES (?,?)", (uid, prompt))
        await db.commit()
        return cur.lastrowid

async def get_photos():
    async with aiosqlite.connect(DB) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT p.*, u.username FROM photos p JOIN users u ON p.user_id=u.user_id WHERE p.status='pending'")
        return await cur.fetchall()

async def complete_photo(oid):
    async with aiosqlite.connect(DB) as db:
        await db.execute("UPDATE photos SET status='completed' WHERE id=?", (oid,))
        await db.commit()

async def get_charity():
    async with aiosqlite.connect(DB) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM charity WHERE status='active' LIMIT 1")
        return await cur.fetchone()

async def add_charity(amount):
    ch = await get_charity()
    if ch:
        async with aiosqlite.connect(DB) as db:
            await db.execute("UPDATE charity SET collected=collected+? WHERE id=?", (amount, ch['id']))            await db.commit()

async def add_charity_task(name, age, story, goal):
    async with aiosqlite.connect(DB) as db:
        await db.execute("INSERT INTO charity (name, age, story, goal) VALUES (?,?,?,?)", (name, age, story, goal))
        await db.commit()

def main_menu(is_pro=False):
    kb = [["🔍 Найти людей", "👤 Профиль"], ["🎨 Фото", "📚 Курс"], ["❤️ Детям"]]
    if is_pro:
        kb.append(["💎 Отменить PRO"])
    else:
        kb.append(["🔥 Купить PRO"])
    return types.ReplyKeyboardMarkup(keyboard=[[types.KeyboardButton(text=x) for x in row] for row in kb], resize_keyboard=True)

def user_card(tid):
    kb = [[types.InlineKeyboardButton(text="🔗 Профиль", url=f"tg://user?id={tid}")], [types.InlineKeyboardButton(text="✅ Подписался", callback_data=f"sub:{tid}")], [types.InlineKeyboardButton(text="➡️ Далее", callback_data="next")]]
    return types.InlineKeyboardMarkup(inline_keyboard=kb)

def pay_btn(item, price):
    kb = [[types.InlineKeyboardButton(text=f"💳 Оплатить {price} ⭐", callback_data=f"pay:{item}")]]
    return types.InlineKeyboardMarkup(inline_keyboard=kb)

def admin_photos(orders):
    kb = [[types.InlineKeyboardButton(text=f"#{o['id']} @{o['username']}", callback_data=f"aph:{o['id']}")] for o in orders[:5]]
    kb.append([types.InlineKeyboardButton(text="⬅️ Назад", callback_data="aback")])
    return types.InlineKeyboardMarkup(inline_keyboard=kb)

def admin_order(oid):
    kb = [[types.InlineKeyboardButton(text="✅ Готово", callback_data=f"acomp:{oid}")], [types.InlineKeyboardButton(text="❌ Отмена", callback_data=f"acanc:{oid}")], [types.InlineKeyboardButton(text="⬅️ Назад", callback_data="aord")]]
    return types.InlineKeyboardMarkup(inline_keyboard=kb)

def charity_kb():
    kb = [[types.InlineKeyboardButton(text="📄 Чек", callback_data="chrec")], [types.InlineKeyboardButton(text="📊 История", callback_data="chhist")]]
    return types.InlineKeyboardMarkup(inline_keyboard=kb)

def cancel_pro_kb():
    kb = [[types.InlineKeyboardButton(text="❌ Да, отменить", callback_data="cancel_pro_confirm")]]
    return types.InlineKeyboardMarkup(inline_keyboard=kb)

@dp.message(Command("start"))
async def start(msg: Message):
    u = await get_user(msg.from_user.id)
    if not u:
        await msg.answer("👋 Привет! Давай зарегистрируемся.\n\n1. Твоя платформа? (Instagram/TikTok/YouTube)")
        await dp.storage.set_data(user_id=msg.from_user.id, data={"step": 1})
        await Form.reg.set()
    else:
        pro = u['is_pro'] and u['pro_expires'] and datetime.fromisoformat(u['pro_expires']) > datetime.now()
        await msg.answer(f"👋 С возвращением, @{msg.from_user.username}!", reply_markup=main_menu(pro))
@dp.message(Form.reg)
async def reg_step(msg: Message, state: FSMContext):
    d = await dp.storage.get_data(user_id=msg.from_user.id)
    s = d.get("step", 1)
    if s == 1:
        await dp.storage.update_data(user_id=msg.from_user.id, data={"platform": msg.text, "step": 2})
        await msg.answer("2. Твоя ниша? (спорт/красота/юмор...)")
    elif s == 2:
        await dp.storage.update_data(user_id=msg.from_user.id, data={"niche": msg.text, "step": 3})
        await msg.answer("3. Твой город?")
    elif s == 3:
        await dp.storage.update_data(user_id=msg.from_user.id, data={"city": msg.text, "step": 4})
        await msg.answer("4. Твоя страна?")
    elif s == 4:
        await dp.storage.update_data(user_id=msg.from_user.id, data={"country": msg.text})
        d = await dp.storage.get_data(user_id=msg.from_user.id)
        await add_user(msg.from_user.id, msg.from_user.username, d["platform"], d["niche"], d["city"], d["country"])
        await dp.storage.clear(user_id=msg.from_user.id)
        await state.finish()
        await msg.answer("✅ Готово!", reply_markup=main_menu())

@dp.message(F.text == "🔍 Найти людей")
async def search(msg: Message):
    u = await get_user(msg.from_user.id)
    if not u:
        await msg.answer("Сначала /start")
        return
    res = await find_users(u['niche'], u['city'], msg.from_user.id)
    if not res:
        await msg.answer("😔 Пока нет людей. Попробуй позже!")
        return
    t = res[0]
    await dp.storage.set_data(user_id=msg.from_user.id, data={"sres": [x['user_id'] for x in res], "sidx": 0})
    txt = f"👤 @{t['username']}\n📱 {t['platform']}\n🎯 {t['niche']}\n📍 {t['city']}\n⭐ Рейтинг: {t['rating']}%"
    await msg.answer(txt, reply_markup=user_card(t['user_id']))

@dp.callback_query(F.data.startswith("sub:"))
async def sub_conf(cb: CallbackQuery):
    tid = int(cb.data.split(":")[1])
    await add_sub(cb.from_user.id, tid)
    await cb.answer("✅ Отлично!", show_alert=True)
    try:
        await bot.send_message(tid, f"🔔 На вас подписался @{cb.from_user.username}!")
    except:
        pass

@dp.callback_query(F.data == "next")
async def next_res(cb: CallbackQuery):
    d = await dp.storage.get_data(user_id=cb.from_user.id)    res = d.get("sres", [])
    idx = d.get("sidx", 0) + 1
    if idx >= len(res):
        await cb.answer("Это всё!", show_alert=True)
        return
    tid = res[idx]
    t = await get_user(tid)
    await dp.storage.update_data(user_id=cb.from_user.id, data={"sidx": idx})
    txt = f"👤 @{t['username']}\n📱 {t['platform']}\n🎯 {t['niche']}\n📍 {t['city']}\n⭐ Рейтинг: {t['rating']}%"
    await cb.message.edit_text(txt, reply_markup=user_card(tid))

@dp.message(F.text == "🔥 Купить PRO")
async def buy_pro(msg: Message):
    await msg.answer("🔥 PRO: безлимит + помощь детям\n\nЦена: 100 ⭐/мес", reply_markup=pay_btn("pro", 100))

@dp.message(F.text == "💎 Отменить PRO")
async def cancel_pro_msg(msg: Message):
    await msg.answer("❌ Отменить PRO-подписку?", reply_markup=cancel_pro_kb())

@dp.callback_query(F.data == "cancel_pro_confirm")
async def cancel_pro_conf(cb: CallbackQuery):
    await cancel_pro(cb.from_user.id)
    await cb.message.edit_text("✅ PRO отменен.", reply_markup=main_menu(False))

@dp.callback_query(F.data.startswith("pay:"))
async def pay_cb(cb: CallbackQuery):
    item = cb.data.split(":")[1]
    prices = {"pro": 100, "course": 500, "photo": 50}
    titles = {"pro": "PRO", "course": "Курс", "photo": "Фото"}
    await bot.send_invoice(cb.from_user.id, title=titles[item], description=titles[item], payload=item, provider_token="", currency="XTR", prices=[LabeledPrice(label="Оплата", amount=prices[item])], need_email=(item=="course"))

@dp.pre_checkout_query()
async def pre_check(q: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(q.id, ok=True)

@dp.message(F.successful_payment)
async def pay_ok(msg: Message):
    p = msg.successful_payment
    pl = p.invoice_payload
    amt = p.total_amount
    if pl == "pro":
        await set_pro(msg.from_user.id, 30)
        await add_charity(int(amt * 0.10))
        await msg.answer("✅ PRO активирован! ❤️", reply_markup=main_menu(True))
    elif pl == "course":
        if p.order_info and p.order_info.email:
            await msg.answer(f"✅ Доступ на {p.order_info.email}")
        else:
            await msg.answer("📧 Напишите почту:")
            await Form.email.set()    elif pl == "photo":
        await msg.answer("🎨 Напишите описание:")
        await Form.photo.set()

@dp.message(Form.email)
async def email_ok(msg: Message, state: FSMContext):
    await msg.answer(f"✅ Доступ на {msg.text}")
    await state.finish()

@dp.message(Form.photo)
async def photo_req(msg: Message, state: FSMContext):
    oid = await add_photo(msg.from_user.id, msg.text)
    await msg.answer(f"✅ Заказ #{oid} принят! Ждите ⏳")
    await bot.send_message(ADMIN, f"📩 Фото #{oid}\n@{msg.from_user.username}\n{msg.text}")
    await state.finish()

@dp.message(F.text == "🎨 Фото")
async def photo_menu(msg: Message):
    await msg.answer("🎨 Опишите фото или купите PRO")

@dp.message(F.text == "📚 Курс")
async def course_menu(msg: Message):
    await msg.answer("📚 Курс по ИИ\n\nЦена: 500 ⭐", reply_markup=pay_btn("course", 500))

@dp.message(F.text == "❤️ Детям")
async def charity_menu(msg: Message):
    ch = await get_charity()
    if not ch:
        await msg.answer("🔄 Нет сбора")
        return
    pr = min(int(ch['collected'] / ch['goal'] * 100), 100)
    await msg.answer(f"❤️ {ch['name']}, {ch['age']} лет\n{ch['story']}\n🎯 {ch['goal']}₽\n✅ {ch['collected']}₽ ({pr}%)", reply_markup=charity_kb())

@dp.callback_query(F.data == "chrec")
async def ch_rec(cb: CallbackQuery):
    ch = await get_charity()
    if ch and ch['receipt']:
        await cb.message.answer(f"📄 {ch['receipt']}")
    else:
        await cb.answer("Чек будет позже", show_alert=True)

@dp.message(Command("admin"))
async def admin(msg: Message):
    if msg.from_user.id != ADMIN:
        return
    kb = [[types.InlineKeyboardButton(text="📩 Заказы", callback_data="aord")]]
    await msg.answer("🔧 Админ", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data == "aord")
async def a_ord(cb: CallbackQuery):    orders = await get_photos()
    if not orders:
        await cb.answer("Нет заказов", show_alert=True)
        return
    await cb.message.edit_text("📩 Заказы:", reply_markup=admin_photos(orders))

@dp.callback_query(F.data.startswith("aph:"))
async def a_ph(cb: CallbackQuery):
    oid = int(cb.data.split(":")[1])
    await cb.message.edit_text(f"Заказ #{oid}", reply_markup=admin_order(oid))

@dp.callback_query(F.data.startswith("acomp:"))
async def a_comp(cb: CallbackQuery):
    oid = int(cb.data.split(":")[1])
    await complete_photo(oid)
    await cb.answer("✅ Готово!", show_alert=True)

@dp.callback_query(F.data == "aback")
async def a_back(cb: CallbackQuery):
    kb = [[types.InlineKeyboardButton(text="📩 Заказы", callback_data="aord")]]
    await cb.message.edit_text("🔧 Админ", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))

async def main():
    await init_db()
    ch = await get_charity()
    if not ch:
        await add_charity_task("Аня", 8, "ДЦП", 50000)
    print("✅ Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
