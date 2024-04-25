import asyncio
import datetime
import logging
import math
from telegram.ext import CommandHandler
from datetime import date, datetime, timedelta
from telegram.ext import Application, MessageHandler, filters, CallbackContext
import dateparser
import requests
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler
from telegram.ext import ConversationHandler
from telegram import Update
import random

TOKEN = '6551813567:AAFetR0elbboz08-p9Iv3WRWrbkW97nQMvM'

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

scheduled = {}

FROM, TO = 1, 2


# показывает расписание на завтра
async def show_tomorrow(update, context):
    if 'chat_id' not in context.user_data:
        await update.message.reply_text('Пожалуйста, начните диалог с ботом, отправив команду /start.')
        return

    # проверка если ли в словаре что-то
    if not scheduled:
        await context.bot.send_message(chat_id=context.user_data['chat_id'], text='Нет событий в расписании.')
        return

    # сортируем события по дате и времени
    sorted_events = sorted(scheduled.items(), key=lambda x: x[1])

    # создаем сообщение расписания
    schedule_message = 'Расписание на завтра:\n'
    tomorrow_date = (datetime.now() + timedelta(days=1)).date()
    event_found = False

    for event, event_date in sorted_events:
        if event_date.date() == tomorrow_date:
            event_time = event_date.strftime('%H:%M')
            schedule_message += f'- {event} ({event_time})\n'
            event_found = True

    # если нет событий на завтра
    if not event_found:
        schedule_message = 'Нет событий на завтра.'

    # отправляем сообщение расписания пользователю
    await context.bot.send_message(chat_id=context.user_data['chat_id'], text=schedule_message)


# /help
async def help_command(update, context):
    help_text = """
    Доступные команды:
    /start - Начать диалог с ботом
    /add <событие> <время> - Добавить событие в расписание. Например: /add кино на завтра 18:00
    /show - Показать текущее расписание
    /delete <событие> - Удалить событие из расписания. Например: /delete Поход в кино
    /route - Начать процесс выбора начальной и конечной точек для расчета маршрута
    /holiday - Скажет ближайший праздник
    /fact - Интересный факт
    /help - Показать эту справку
    """

    await update.message.reply_text(help_text)


def calculate_route_time(coord1, coord2, speed_km=20):
    # расстояние между двумя точками в
    distance = calculate_distance(coord1, coord2)

    # время в пути в часах
    time_hours = distance / speed_km

    # время в часах, минутах и секундах
    hours = int(time_hours)
    minutes = int((time_hours * 60) % 60)

    return f"{hours} часов, {minutes} минут"


def calculate_distance(coord1, coord2):
    lat1, lon1 = coord1
    lat2, lon2 = coord2
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])

    # радиус земли в километрах
    r = 6371

    # вычисление косинусов и синусов широт и разницы долгот
    a = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    # расстояние между двумя точками и на погрешность(не пройти везде на прямую)
    distance = r * c * 2

    return distance


# из части данного адреса получаем полный адрес
def get_full_address(partial_address):
    # url для запроса
    url = (f"https://geocode-maps.yandex.ru/1.x/?apikey=40d1649f-0493-4b70-98ba-98533de7710b&format="
           f"json&geocode={partial_address}")

    # делаем запрос
    response = requests.get(url)

    if response.status_code == 200:
        # парсим ответ
        data = response.json()

        # получаем адрес из ответа
        try:
            full_address = data['response']['GeoObjectCollection']['featureMember'][0]['GeoObject']['metaDataProperty'][
                'GeocoderMetaData']['text']
            return get_coordinates(full_address)
        except (KeyError, IndexError):
            return "Не удалось определить адрес. Проверьте введенные данные."
    else:
        # ошибка, да
        return f"Ошибка: {response.status_code}"


def get_coordinates(address):
    base_url = "https://geocode-maps.yandex.ru/1.x/"
    params = {
        "apikey": '40d1649f-0493-4b70-98ba-98533de7710b',
        "geocode": address,
        "format": "json"
    }
    response = requests.get(base_url, params=params)
    # проверка
    if response.status_code == 200:
        data = response.json()
        try:
            # достаем координаты
            pos = data['response']['GeoObjectCollection']['featureMember'][0]['GeoObject']['Point']['pos']
            longitude, latitude = pos.split(" ")
            return float(latitude), float(longitude)
        except (KeyError, IndexError):
            return None, None
    else:
        return None, None


async def send_event_notification(chat_id, event, event_date, context):
    # проверяем, наступило ли событие
    if datetime.now() >= event_date:
        await context.bot.send_message(chat_id=chat_id, text=f'{event} наступил!')
        del scheduled[event]

    elif datetime.now() < event_date - timedelta(days=1):
        # если оно не скоро (> 1 дня)
        reminder_date = event_date - timedelta(days=1)
        await send_reminder(chat_id, event, reminder_date, context, 'за день')
        time_to_event = (event_date - datetime.now()).total_seconds()
        await asyncio.sleep(time_to_event)
        await context.bot.send_message(chat_id=chat_id, text=f'{event} наступил!')
        del scheduled[event]

    elif datetime.now() < event_date - timedelta(hours=1):
        # если оно скоро (> 1 часа)
        reminder_date = event_date - timedelta(hours=1)
        await send_reminder(chat_id, event, reminder_date, context, 'за час')
        time_to_event = (event_date - datetime.now()).total_seconds()
        await asyncio.sleep(time_to_event)
        await context.bot.send_message(chat_id=chat_id, text=f'{event} наступил!')
        del scheduled[event]

    elif datetime.now() < event_date - timedelta(minutes=15):
        # если оно скоро (> 15 минут)
        reminder_date = event_date - timedelta(minutes=15)
        await send_reminder(chat_id, event, reminder_date, context, 'за 15 минут')
        time_to_event = (event_date - datetime.now()).total_seconds()
        await asyncio.sleep(time_to_event)
        await context.bot.send_message(chat_id=chat_id, text=f'{event} наступил!')
        del scheduled[event]

    else:
        # считаем время до события
        time_to_event = (event_date - datetime.now()).total_seconds()
        # ждем время до события
        await asyncio.sleep(time_to_event)
        await context.bot.send_message(chat_id=chat_id, text=f'{event} наступил!')
        del scheduled[event]


async def send_reminder(chat_id, event, reminder_date, context, time_text):
    # проверяем, наступило ли время для напоминания
    if datetime.now() >= reminder_date:
        await context.bot.send_message(chat_id=chat_id, text=f'Напоминание: {event} {time_text}!')
    else:
        # считаем время до напоминания
        time_to_reminder = (reminder_date - datetime.now()).total_seconds()
        # ждем время до напоминания
        await asyncio.sleep(time_to_reminder)
        await context.bot.send_message(chat_id=chat_id, text=f'Напоминание: {event} {time_text}!')


# /start
async def start(update, context):
    await update.message.reply_text('Привет! Я бот для планирования событий(для помощи /help).')
    context.user_data['chat_id'] = update.effective_chat.id


def parse_datetime_with_relative_dates(user_input):
    # парсим введенную пользователем строку в датетайм
    parsed_datetime = dateparser.parse(user_input, settings={'DATE_ORDER': 'DMY', 'PREFER_DATES_FROM': 'future'})
    return parsed_datetime


dictionary = ['в', 'на', 'около', 'at', 'in', 'on', 'после', 'до', 'к', 'по']

a = []


async def add(update, context):
    # чтоб только 1 пользователю
    if 'chat_id' not in context.user_data:
        await update.message.reply_text('Пожалуйста, начните диалог с ботом, отправив команду /start.')
        return

    # проверка правильности
    if len(context.args) < 2:
        await update.message.reply_text(
            'Пожалуйста, укажите событие в формате "/add <событие> предлог <время>".')
        return
    elif len(context.args) == 2:
        date = context.args[1]
        event = context.args[0]
        date = parse_datetime_with_relative_dates(date)
        scheduled[event] = date

        keyboard = [[InlineKeyboardButton("Show", callback_data='show')]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(f'Событие "{event}" добавлено в расписание.', reply_markup=reply_markup)
        # создаем задание (напоминание)
        asyncio.Task(send_event_notification(context.user_data['chat_id'], event, date, context))
    else:
        for i in range(len(dictionary)):
            if dictionary[i - 1] in context.args:
                # достаем ивент
                a.append(context.args.index(dictionary[i - 1]))
                # достаем дату
                date = ' '.join(context.args[context.args.index(dictionary[i - 1]) + 1::])
        # ивент до первого временного предлога
        event = ' '.join(context.args[:a[-1]])
        # дата после первого временного предлога
        date = parse_datetime_with_relative_dates(date)
        scheduled[event] = date

        keyboard = [[InlineKeyboardButton("Show", callback_data='show')]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(f'Событие "{event}" добавлено в расписание.', reply_markup=reply_markup)
        # создаем задание (напоминание)
        asyncio.Task(send_event_notification(context.user_data['chat_id'], event, date, context))


async def show(update, context):
    if 'chat_id' not in context.user_data:
        await update.message.reply_text('Пожалуйста, начните диалог с ботом, отправив команду /start.')
        return

    if not scheduled:
        await context.bot.send_message(chat_id=context.user_data['chat_id'], text='Нет событий в расписании.')
        return

    # Сортируем события по дате и времени
    sorted_events = sorted(scheduled.items(), key=lambda x: x[1])

    # Формируем сообщение расписания
    schedule_message = 'Расписание:\n'
    current_date = None
    for event, event_date in sorted_events:
        event_time = event_date.strftime('%H:%M')
        event_date_str = event_date.strftime('%d.%m.%Y')

        # проверяем, является ли событие назначенным на текущий день
        if event_date.date() == datetime.now().date():
            if current_date != event_date_str:
                current_date = event_date_str
                schedule_message += f'Сегодня ({event_date_str}):\n'
            schedule_message += f'- {event} ({event_time})\n'

        # проверяем, является ли событие назначенным на завтрашний день
        elif event_date.date() == datetime.now().date() + timedelta(days=1):
            if current_date != event_date_str:
                current_date = event_date_str
                schedule_message += f'Завтра ({event_date_str}):\n'
            schedule_message += f'- {event} ({event_time})\n'

        # проверяем, является ли событие назначенным на ближайшие 7 дней
        elif datetime.now().date() < event_date.date() <= datetime.now().date() + timedelta(days=6):
            if current_date != event_date_str:
                current_date = event_date_str
                schedule_message += f'{event_date.strftime("%A, %d.%m.%Y")}:\n'
            schedule_message += f'- {event} ({event_time})\n'

        # если событие далеко в будущем, то выводим только с датой
        else:
            schedule_message += f'- {event_date_str}: {event}\n'
    # отправляем сообщение расписания пользователю
    await context.bot.send_message(chat_id=context.user_data['chat_id'], text=schedule_message)


async def delete(update, context):
    # чтоб только 1 пользователю отправлялось
    if 'chat_id' not in context.user_data:
        await update.message.reply_text('Пожалуйста, начните диалог с ботом, отправив команду /start.')
        return

    if len(context.args) == 0:
        await update.message.reply_text(
            'Пожалуйста, укажите название события для удаления в формате "/delete <событие>".')
        return

    # находим евент
    event_name = ' '.join(context.args)

    if event_name in scheduled:
        # если есть такой ивент удаляем
        del scheduled[event_name]
        await update.message.reply_text(f'Событие "{event_name}" удалено из расписания.')
        # если нет такого ивента
    else:
        await update.message.reply_text(f'Событие "{event_name}" не найдено в расписании.')


# 2й вопрос
async def from_location(update, context) -> int:
    user_data = context.user_data
    user_data['from_location'] = update.message.text
    await update.message.reply_text('Куда вы хотите поехать? Напишите адрес.')
    return TO


# ответ
async def to_location(update, context) -> int:
    user_data = context.user_data
    from_location = user_data.get('from_location')

    if from_location is None:
        #  когда from_location не определен
        update.message.reply_text("Не удалось определить начальное местоположение.")
        return
    user_data['to_location'] = update.message.text
    coordinates1 = get_coordinates(user_data['from_location'])
    coordinates2 = get_coordinates((user_data['to_location']))

    # координаты откуда
    latitude1, longitude1 = get_coordinates((user_data['from_location']))
    # координаты куда
    latitude2, longitude2 = get_coordinates((user_data['to_location']))

    result = calculate_route_time(coordinates1,
                                  coordinates2, 30)
    result2 = calculate_route_time(coordinates1, coordinates2, 6)

    c = f"https://yandex.ru/maps/?rtext={latitude1}%2C{longitude1}~{latitude2}%2C{longitude2}&rl=0"
    keyboard = [[InlineKeyboardButton("Подробнее", url=c)]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    # отправляем сообщение с кнопкой
    await update.message.reply_text(f'на 🚘(транспорте){result}', reply_markup=reply_markup)
    await update.message.reply_text(f'🚶‍♂️(пешком) {result2}', reply_markup=reply_markup)
    return ConversationHandler.END


# отмена route
async def cancel(update, context):
    await update.message.reply_text('Диалог отменен.')
    return ConversationHandler.END


# 1 вопрос
async def start_route(update, context):
    if 'chat_id' not in context.user_data:
        await update.message.reply_text('Пожалуйста, начните диалог с ботом, отправив команду /start.')
        return
    await update.message.reply_text('Откуда вы находитесь? Напишите адрес.')
    return FROM


# ключ для нахождения ближайшего праздника
API_KEY = 'B063SPSQBfF2KBi7xWRRpmqb9f1Kbw8k'


# получаем ответ на запрос
def get_holidays(country, year, month):
    url = f"https://calendarific.com/api/v2/holidays?api_key={API_KEY}&country={country}&year={year}&month={month}"
    response = requests.get(url)
    data = response.json()
    return data.get('response', {}).get('holidays', [])


# нахождение ближайшего праздника
async def next_holiday(update, context) -> None:
    if 'chat_id' not in context.user_data:
        await update.message.reply_text('Пожалуйста, начните диалог с ботом, отправив команду /start.')
        return

    today = date.today()
    #  ближайший праздник в текущем месяце
    holidays = get_holidays('RU', today.year, today.month)

    if not holidays:
        # если в текущем месяце праздников нет, то получаем праздники следующего месяца
        next_month = today.replace(day=28) + datetime.timedelta(days=4)
        holidays = get_holidays('RU', next_month.year, next_month.month)

    if holidays:
        # сортируем праздники по дате и выбираем ближайший
        holidays.sort(key=lambda x: datetime.strptime(x['date']['iso'], '%Y-%m-%d'))
        closest_holiday = holidays[0]
        await update.message.reply_text(
            f"Ближайший праздник: {closest_holiday['name']} ({closest_holiday['date']['iso']})")
    else:
        await update.message.reply_text("Ближайших праздников нет.")


async def get_random_fact(update, context):
    # Генерируем случайное число от 0 до 1000 для запроса факта
    number = random.randint(0, 1000)

    # URL API для получения случайного факта о числе
    url = f"http://numbersapi.com/{number}"

    try:
        # отправляем запрос к апи
        response = requests.get(url)
        # Если запрос не удался, выбросится исключение
        response.raise_for_status()

        # выводим факт
        await update.message.reply_text(response.text)

    except requests.RequestException as e:
        await update.message.reply_text(f"Произошла ошибка при получении факта: {e}")


# обработка кнопки show
async def button(update, context):
    query = update.callback_query
    await query.answer()
    # если ответ show
    if query.data == 'show':
        await show(update, context)


translation_dict = {
    "Привет": "Hello",
    "Добавить": "Add",
    "Показать": "Show",
    "Удалить": "Delete",
    "Начать": "Start",
    "Помощь": "Help",
    "Завтра": "Tomorrow",
    "Расписание": "Schedule",
    "Нет": "No",
    "Событий": "Events",
    "Расписания": "Schedule",
    "Начать диалог": "Start a conversation",
    "Отправить команду": "Send a command",
    "Пожалуйста": "Please",
    "Укажите": "Please specify",
    "В формате": "In the format",
    "Напишите адрес": "Write an address",
    "Куда вы хотите поехать": "Where do you want to go",
    "Напишите название события для удаления": "Write the name of the event to delete",
    "Откуда вы находитесь": "Where are you from",
    "Диалог отменен": "Conversation cancelled",
    "Подробнее": "More details",
    "🚘(транспорте)": "🚘(by transport)",
    "🚶‍♂️(пешком)": "🚶‍♂️(on foot)"
}


def main():
    application = Application.builder().token(TOKEN).build()
    # добавление функций
    application.add_handler(CommandHandler("delete", delete))
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("add", add))
    application.add_handler(CommandHandler("show", show))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("tomorrow", show_tomorrow))
    application.add_handler(CommandHandler("holiday", next_holiday))
    application.add_handler(CommandHandler("fact", get_random_fact))
    # обработчик для нажатий на кнопки
    application.add_handler(CallbackQueryHandler(button))
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('route', start_route)],
        states={
            FROM: [MessageHandler(filters.TEXT & ~filters.COMMAND, from_location)],
            TO: [MessageHandler(filters.TEXT & ~filters.COMMAND, to_location)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    application.add_handler(conv_handler)
    application.run_polling()


if __name__ == '__main__':
    main()
