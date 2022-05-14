import re

from redis import Redis
from database.redisworks import Root
from datetime import datetime, timedelta
from pyrogram import Client
from pysondb import db
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from pyrogram.types import (InlineKeyboardMarkup, InlineKeyboardButton)
from dateutil import parser
from termcolor import colored

from model.flood_user import UserFlood

# print(coloredmessage.text("I am result : "+str(name), 'red'))
redis = Redis(host='localhost', port=6379, db=0,
              charset="utf-8", decode_responses=True)

fdb = Root(host='localhost', port=6379, charset="utf-8")
# from model.user_info import User
API_ID = 57018
API_HASH = "2b0e93bfdd2555bf98e7d9f5e5b09426"
app = Client("suervey", api_id=API_ID, api_hash=API_HASH)
users = db.getDb("database/users.json")
surveies = db.getDb("database/surveys.json")
questions = db.getDb("database/questions.json")
admin_ids = [637572531]
channel_id = "MeowthGo"

main_message = "مرحبا بك يا مشرفنا العزيز"


main_inline_keyboard = InlineKeyboardMarkup(
    [
        [
            InlineKeyboardButton('تعديل | إضافة رسالة ترحيب',
                                 callback_data='welcome_message_add_edit')
        ],
        [
            InlineKeyboardButton('إنشاء منشور الاسئلة',
                                 callback_data='question_post')
        ],
        [
            InlineKeyboardButton('المنشورات الفعالة',
                                 callback_data='question_active')
        ],
        [
            InlineKeyboardButton('المقيدين',
                                 callback_data='restricted_users')]
        # [
        #     InlineKeyboardButton('مراجعة الإستبيان النشط',
        #                          callback_data='survey_posts')
        # ]
    ]
)


@ app.on_message()
async def main(client, message):
    if(not message.text):
        return
    user_attempt = redis.get(message.from_user.id)
    if(user_attempt):
        redis.incr(message.from_user.id)
    else:
        redis.set(message.from_user.id, 1, ex=2)
    if(user_attempt and int(user_attempt) == 5):
        return await client.send_message(message.chat.id, "يرجى الإنتظار لا ترسل رسائل بسرعة")
    """main function"""
    if(message.text):
        print(colored(f"{message.from_user.id} : {message.text}", 'blue'))

    if(not(is_admin(message.from_user.id))):
        # start with parameter , start without it
        if message.text == "/start":
            await handle_user_start(client, message)
        elif message.text.startswith("/start"):
            await handle_user_start_survey(client, message)
        elif message.text.startswith("/"):
            await client.send_message(message.chat.id, "شئت بالأمر الغير معروف")
        else:
            await handle_user_steps(client, message)
    else:
        if message.text == "/start":
            await handle_admin_start(client, message)
        elif message.reply_to_message:
            await handle_admin_reply(client, message)
        elif(bool(fdb.steps.action)):
            await handle_admin_steps(client, message)


async def handle_admin_reply(client, message):
    ans_pattern = r"[.*|\s]?#qid_([0-9]+)"
    get_qid = re.findall(
        ans_pattern, message.reply_to_message.text,  re.MULTILINE)
    if len(get_qid) > 0:
        qid = get_qid[0]
        question = questions.getById(qid)
        if(question):
            questions.updateById(qid, {"status": 1, "answer": message.text})
            survey = surveies.getById(question["survey_id"])[0]
            message_text = f"سؤال : {question['text']} \n\n إجابة : {message.text} \n\n 🔥 شاركنا رأيك او وجهة نظرك في التعليقات 🔥"
            survey_question = await client.send_message(channel_id, message_text, reply_to_message_id=int(survey["post_id"]))

            link_to_answer_keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(
                "التوجه للجواب", url=f"https://t.me/{channel_id}/{survey_question.id}")]])
            await client.send_message(question['user_id'], "تم إجابة السؤال ونشره في القناة : @"+channel_id, reply_to_message_id=int(question['message_id']), reply_markup=link_to_answer_keyboard)

            await message.reply_to_message.delete()


async def handle_user_steps(client, message):
    # database
    """handle user steps"""

    if(fdb.user_steps.step == 1 and fdb.user_steps.action == "survey_ask"):
        question_id = questions.add({
            "type": "survey_ask",
            "user_id": message.from_user.id,
            "message_id": str(message.id),
            "text": message.text,
            "date": datetime.now().strftime('%Y-%m-%d %-I:%-M%p'),
            "survey_id": str(fdb.survey),
            "answer": None,
            "status": 0,  # 0 = pending, 1 = answered ,2 = partial-answer, 3 = rejected
        })
        # print(questions.getByQuery({"type": "survey_ask"}))
        # survey = surveies.getByQuery(
        #     {"type": "question_post", "post_id": str(fdb.survey)})[0]
        await message.reply(f"شكرا لك {message.from_user.first_name}.\nتم إضافة السؤال بنجاح , راجين منك الإنتظار لحين الإجابة ,سيتم نشر السؤال في القناة : @"+channel_id)
        fdb.user_steps.step = None
        fdb.user_steps.action = None
        survey_question_keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton('رفض السؤال',
                                         callback_data='reject_question='+str(message.id)),
                    InlineKeyboardButton('نشر السؤال',
                                         callback_data='accept_question='+str(message.id))
                ],
                [
                    InlineKeyboardButton('تقييد المستخدم',
                                         callback_data='restrict='+str(message.chat.id)),
                ]
            ]
        )
        for admin in admin_ids:
            message_text = f"سؤال جديد من {message.from_user.first_name}\n {message.text}\n - @{message.from_user.username} يرجى منك الإجابة عليه أو رفضه\n#qid_{question_id}"
            message_text = message_text.replace("- @None", "")
            await client.send_message(admin, message_text, reply_markup=survey_question_keyboard)
            # print(message)


async def handle_admin_steps(client, message):
    """handle admin steps"""
    # admin_steps = fdb.admin_steps
    if(fdb.steps.step == 1 and fdb.steps.action == "welcome_message_add_edit"):
        fdb.welcome_message = message.text
        await client.send_message(message.chat.id, "تم اضافة الرسالة")
        delete_steps_keys()
    if(fdb.steps.step == 1 and fdb.steps.action == "question_post_expire"):
        fdb.question_post = message.text

        await client.send_message(message.chat.id, f"تم اضافة المنشور بنجاح ، قم بإضافة الوقت \n `{datetime.now().strftime('%Y-%m-%d %-I:%-M%p')}`")
        fdb.steps.step = 2
    elif(fdb.steps.step == 2 and fdb.steps.action == "question_post_expire"):
        try:
            fdb.question_time = parser.parse(message.text)
            await message.reply("تم حفظ المنشور بنجاح")
            delete_steps_keys()
        except:
            await client.send_message(message.chat.id, "خطأ في تنسيق الوقت")
        # print(parser.parse(message.text))
        # datetime_object = datetime.strptime(
        # 'Jun 1 2005  1:33PM', '%b %d %Y %I:%M%p')


async def handle_admin_start(client, message):
    """handle sending start"""
    # print(fdb.steps.action)
    if(not bool(fdb.steps.action)):
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton('تعديل | إضافة رسالة ترحيب', callback_data='welcome_message_add_edit')]])
        await client.send_message(message.chat.id, main_message, reply_markup=main_inline_keyboard)
    else:
        if(fdb.steps.action == 'welcome_message_add_edit' and fdb.steps.step == 1):
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton('رجوع', callback_data='back')]])
            await client.send_message(message.chat.id, "ارسل لنا رسالة ترحيب", reply_markup=keyboard)


async def handle_user_start(client, message):
    """handle sending start"""
    # await client.send_message(message.chat.id, "مرحبا بك ارسل لنا اي إقتراح او سؤال ليتم الرد عليه")
    # print(message.from_user.id)
    # user = User.find(User.telegram_id == message.from_user.id).all()
    # print(user)
    welcome_message = fdb.welcome_message

    if(not bool(welcome_message)):
        welcome_message = "مرحبا بك عضونا المميز"
    current_user = get_users({"tg_id": message.from_user.id})
    if(current_user):
        # re-start
        await client.send_message(message.chat.id, parse_message(welcome_message, message))
    else:
        now = datetime.now()
        timestamp = datetime.timestamp(now)
        users.add({"type": "user", "restricted": False, "tg_id": message.from_user.id,
                   "join_date": timestamp})
        # new start
        await client.send_message(message.chat.id, parse_message(welcome_message, message))
        # print(user)


async def handle_user_start_survey(client, message):
    """handle user start survey"""
    # print(f"{remove_prefix(message.text,'/start ')}")
    surv_id = remove_prefix(message.text, '/start ')
    try:
        surv = surveies.getById(surv_id)
    except:
        await client.send_message(message.chat.id, "هذا الاستبيان غير موجود")
        return

    if(surv):
        if(not surv['active']):
            return await client.send_message(message.chat.id, "هذا الاستبيان غير فعال")
        fdb.survey = surv_id
        fdb.user_steps.action = "survey_ask"
        fdb.user_steps.step = 1
        await message.reply("قم بإرسال سؤالك الذي تحب طرحه وسيتم نشرة في القناة بعد الإجابة عليه.")
    else:
        await client.send_message(message.chat.id, "هذا الاستبيان غير متاح")


@ app.on_callback_query()
async def handle_callback_query(client, callback_query):
    """handle callback query"""
    user_id = "callback_"+str(callback_query.from_user.id)
    user_attempt = redis.get(user_id)
    if(user_attempt):
        await client.answer_callback_query(callback_query.id, "يرجى الإنتظار")
        return
    else:
        redis.set(user_id, 1, ex=3)

    if callback_query.data == "back":
        delete_steps_keys()
        await callback_query.message.edit(main_message, reply_markup=main_inline_keyboard)
        await client.answer_callback_query(callback_query.id, "تم الرجوع للقائمة السابقة")
    elif callback_query.data == 'idle':
        await client.answer_callback_query(callback_query.id, "لا شيء لفعله هنا")
    elif callback_query.data == "welcome_message_add_edit":
        # await client.send_message(callback_query.from_user.id, "رسالة الترحيب")
        try:
            await callback_query.message.delete()
            await client.answer_callback_query(callback_query.id, "إرسل رسالة الترحيب")
            fdb.steps.action = "welcome_message_add_edit"
            fdb.steps.step = 1
        except Exception as e:
            print(e)
    elif callback_query.data == "question_post":
        await callback_query.message.edit("إرسل منشور الاسئلة")
        await client.answer_callback_query(callback_query.id, "إنشاء منشور الاسئلة")
        fdb.steps.action = "question_post_expire"
        fdb.steps.step = 1
    elif callback_query.data.startswith("reject_question"):
        qid = callback_query.data.replace("reject_question=", "")
        question = questions.getByQuery({"message_id": qid})
        if len(question):
            question = question[0]
            questions.updateById(question['id'], {"status": 3})
            # print(question)
        await callback_query.message.delete()
        await client.send_message(question['user_id'], "تم رفض السؤال اما لأنه تكرر او لا يتماشى مع الذوق العام", reply_to_message_id=int(question['message_id']))
        await client.answer_callback_query(callback_query.id, "تم رفض السؤال بنجاح")
    elif callback_query.data.startswith("accept_question"):
        qid = callback_query.data.replace("accept_question=", "")
        question = questions.getByQuery({"message_id": qid})
        if len(question) > 0:
            question = question[0]
            questions.updateById(question['id'], {"status": 2})
            try:
                survey = surveies.getById(question["survey_id"])
            except:
                await client.answer_callback_query(callback_query.id, "هذا الاستبيان غير متاح")
                return
            message_text = f"سؤال : {question['text']} \n\n 🔥 شاركنا رأيك او وجهة نظرك في التعليقات 🔥"
            survey_question = await client.send_message(channel_id, message_text, reply_to_message_id=int(survey['post_id']))
            link_to_answer_keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(
                "التوجه للجواب", url=f"https://t.me/{channel_id}/{survey_question.id}")]])
            await client.send_message(question['user_id'], "تم إجابة السؤال ونشره في القناة  @"+channel_id, reply_to_message_id=int(question['message_id']), reply_markup=link_to_answer_keyboard)

        await callback_query.message.delete()
        await client.answer_callback_query(callback_query.id, "تم رفض السؤال بنجاح")
    elif callback_query.data.startswith('restricted_users'):
        rusers = users.getByQuery({"restricted": True})
        ikm = []
        for user in rusers:
            tguser = await app.get_users(user['tg_id'])
            ikm.append([
                InlineKeyboardButton(
                    tguser.first_name, callback_data=f"idle"),
                InlineKeyboardButton(
                    "🟢", callback_data=f"unrestrict={str(user['tg_id'])}")
            ])
        ikm.append([InlineKeyboardButton("رجوع", callback_data="back")])
        message_text = "المستخدمين المحظورين"
        await callback_query.message.edit(message_text, reply_markup=InlineKeyboardMarkup(ikm))

    elif callback_query.data.startswith("restrict"):
        user_id = callback_query.data.replace("restrict=", "")
        user = users.getByQuery({"tg_id": int(user_id)})
        if len(user) > 0:
            user = user[0]
            users.updateById(user['id'], {"restricted": True})
            await callback_query.message.delete()
            await client.send_message(user_id, "تم حظرك من إستخدام البوت")
            await client.answer_callback_query(callback_query.id, "تم حظر المستخدم بنجاح")
    elif callback_query.data.startswith("unrestrict"):
        user_id = callback_query.data.replace("unrestrict=", "")
        user = users.getByQuery({"tg_id": int(user_id)})
        if len(user) > 0:
            user = user[0]
            users.updateById(user['id'], {"restricted": False})
            await callback_query.message.delete()
            await client.send_message(user_id, "تم الغاء حظرك من إستخدام البوت")
            await client.answer_callback_query(callback_query.id, "تم الغاء حظر المستخدم بنجاح")
    elif callback_query.data.startswith('question_active'):
        csurvies = surveies.getByQuery({"active": 1})
        ikm = []
        for surv in csurvies:
            ikm.append([
                InlineKeyboardButton(
                    surv['question'][:99], callback_data="idle"),
                InlineKeyboardButton(
                    "🟢", callback_data=f"disable_question={str(surv['id'])}"),
                InlineKeyboardButton(
                    "إنتقال للمنشور", url=f"https://t.me/{channel_id}/{surv['post_id']}")
            ])
        ikm.append([InlineKeyboardButton("رجوع", callback_data="back")])
        message_text = "المنشورات الفعاله"
        await callback_query.message.edit(message_text, reply_markup=InlineKeyboardMarkup(ikm))
    elif callback_query.data.startswith('disable_question'):
        surv_id = callback_query.data.replace('disable_question=', '')
        try:
            surv = surveies.getById(surv_id)
        except:
            await client.answer_callback_query(callback_query.id, "هذا الاستبيان غير متاح")
            return
        if len(surv) > 0:

            surveies.updateById(surv['id'], {"active": 0})
            await callback_query.message.delete()
            await client.send_message(callback_query.message.chat.id, "تم إيقاف المنشور")
            await client.answer_callback_query(callback_query.id, "تم إيقاف السؤال بنجاح")


def remove_prefix(text, prefix):
    return text[text.startswith(prefix) and len(prefix):]


def delete_steps_keys():
    """delete steps keys"""
    fdb.steps.action = None
    fdb.steps.step = None


def get_users(parms={}):
    """get users"""
    query = dict({"type": "user"}.items() | parms.items())
    users_arr = users.getByQuery(query)
    return users_arr


def is_admin(user_id):
    """check if user is admin"""
    return user_id in admin_ids


def parse_message(rmessage, message):
    """parse message"""
    parsed_message = rmessage
    parsed_message = parsed_message.format(username=message.from_user.username)
    parsed_message = parsed_message.replace(
        "@None", message.from_user.first_name)
    return parsed_message.format(
        fname=message.from_user.first_name,
        lname=message.from_user.last_name,
    )


scheduler = AsyncIOScheduler()


def check_expiration():
    # for admin in admin_ids:
    if(bool(fdb.question_time)):
        if(fdb.question_time < datetime.now()):

            msg = app.send_message(channel_id, fdb.question_post)

            expire_time = datetime.timestamp(
                fdb.question_time + timedelta(hours=24))
            survey = surveies.add(
                {
                    "type": "question_post",
                    "post_id": str(msg.id),
                    "question": str(fdb.question_post),
                    "active": True,
                    "expire": expire_time,
                    "answer_count": 0
                })

            answer_keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        '📛 أطرح سؤالاً 📛', url=f'https://t.me/tecmtbot?start={str(survey)}'

                    )
                ]
            ])
            app.edit_message_reply_markup(
                channel_id, msg.id, reply_markup=answer_keyboard)
            fdb.question_post = None
            fdb.question_time = None


scheduler.add_job(check_expiration, "interval", seconds=3)
scheduler.start()
app.run()  # Automatically start() and idle()
