import geopy.exc
import telebot
from telebot import custom_filters
from telebot.handler_backends import State, StatesGroup
from telebot.storage import StateMemoryStorage
from geopy.geocoders import Nominatim
from geopy.location import Location
import requests
import json
import time
import datetime

# инициализация сервиса геопозиций
geolocator = Nominatim(user_agent="Eventhelper")

# инициализация бота
state_storage = StateMemoryStorage()
bot = telebot.TeleBot("5345404061:AAEa-GVN9ZkWn9b-NzUCGMwfl6rTWaz_VvY",
                      state_storage=state_storage)

# возможные состояния диалога с ботом
class MyStates(StatesGroup):
    address = State() # ввод адреса
    select_address = State() # выбор адреса
    event = State() # выбор страницы мероприятий

# обработчик команды /stop
# позволяет вернуться в исходное состояние диалога
@bot.message_handler(state="*", commands='stop')
def stop(message):
    bot.send_message(message.chat.id, "Отмена")
    bot.delete_state(message.from_user.id, message.chat.id)

# обработчик команд /start и /help
# начинают диалог с ботом
@bot.message_handler(commands=['start', 'help'])
def start(message):
    bot.set_state(message.from_user.id, MyStates.address, message.chat.id)
    # бот запрашивает геолокацию в виде встроенной функции Телеграма или любого адреса в пределах Москвы
    bot.send_message(message.chat.id, 'Привет! Где будем сегодня? Скинь геолокацию или напиши адрес:')

# вывод списка адресов
def get_addresses(locations):
    text = "Выберите номер вашего адреса из списка:"
    for k, v in enumerate(locations):
        text += f"\n\n{k + 1} - {v.address}"
    text += "\n\nВведите 0 для отмены"
    return text

# получение ближайших мероприятий
def get_events(latitude, longitude, page):
    t = round(time.time())
    # производится запрос к сайту kudago.com
    r = requests.get(f'https://kudago.com/public-api/v1.4/events/?lang=ru'
                     f'&location=msk'  # искать мероприятия только по Москве
                     f'&page={page}'  # текущая страница
                     f'&page_size=9'  # количество мероприятий на страницу
                     f'&fields=id,title,is_free,dates,price,site_url'
                     f'&actual_since={t}'  # мероприятия, которые всё ещё идут
                     f'&actual_until={t + 3600 * 24}'  # закончатся не ранее, чем через 24 часа
                     f'&lat={latitude}'  # широта поиска
                     f'&lon={longitude}'  # долгота поиска
                     f'&radius=15000'  # в радиусе 15 километров
                     ).json()
    text = "События вблизи вас:"
    ev = []
    if (r.get('results') is None) or (len(r['results']) == 0):
        return text + '\n\nСобытий больше нету'

    # фильтр событий, которые можно посетить прямо сейчас или в ближайшее время
    for k, v in enumerate(r['results']):
        date = ""
        for d in v['dates']:
            if d['start'] < 0:
                continue
            if d['start'] < t < d['end']:
                date = "Идёт прямо сейчас"
            elif t < d['start']:
                date = f"Через {datetime.timedelta(seconds=d['start'] - t)}"
        if date == "":
            continue

        ev.append(f"\n{v['title'].title()}"
                  f"\nЦена: {'бесплатно' if bool(v['is_free']) else v['price']}"
                  f"\nОсталось времени: {date}"
                  f"\n{v['site_url']}")

    if len(ev) == 0:
        return text + '\n\nСобытий больше нету'

    for k, v in enumerate(ev):
        text += f"\n\nНомер {k + 1}" + v

    text += f"\n\nНажмите 0 для перехода на следущую страницу"
    return text

# получение списка возможных адресов
@bot.message_handler(state=MyStates.address, content_types=['text'])
def address(message):
    try:
        locations = geolocator.geocode(message.text,
                                       language="ru",
                                       country_codes="ru",
                                       exactly_one=False,
                                       bounded=True,
                                       # искать адреса только в пределах Москвы
                                       viewbox=((55.92746848810237, 37.33108560765978),
                                                (55.561842393045026, 38.03558386988545)))

    # иногда сервис Nominatim может быть перегружен, если к нему было сделано слишком много запросов
    except geopy.exc.GeopyError:
        bot.send_message(message.chat.id, "Сервис перегружен, пропробуйте ещё раз через несколько секунд:")
        return

    # если пользователь ввёл несуществующий адрес или сделал в нём опечатку
    if locations is None:
        bot.send_message(message.chat.id, "Адрес не найден, пропробуйте ещё раз:")
    else:
        bot.set_state(message.from_user.id, MyStates.select_address, message.chat.id)
        # вывод возможных адресов пользователю
        bot.send_message(message.chat.id, get_addresses(locations))
        with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
            data['locations'] = locations


# выбор пользователем правильного адреса
@bot.message_handler(state=MyStates.select_address, is_digit=True)
def select_address(message):
    num = int(message.text)
    # если пользователь ввёл 0, то возвращаемся в состояние диалога ввода адреса
    if num == 0:
        bot.set_state(message.from_user.id, MyStates.address, message.chat.id)
        bot.send_message(message.chat.id, 'Напишите адрес:')
        return
    # иначе получем широту и долготу и сохраняем в хранилище
    with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
        location = data['locations'][num - 1] if len(data['locations']) >= num > 0 else None
        if location is None:
            # пользователь мог ввести несуществующее число
            bot.send_message(message.chat.id, 'Введите существующий номер адреса:')
            return
        bot.set_state(message.from_user.id, MyStates.event, message.chat.id)
        data['page'] = 1
        # вывод мероприятий
        event = get_events(location.latitude, location.longitude, 1)
        bot.send_message(message.chat.id, event, disable_web_page_preview=True)
        data['lat'] = location.latitude
        data['lon'] = location.longitude


# отдельная обработка ввода, если пользователь ввёл неправильное сообщение
@bot.message_handler(state=MyStates.select_address, is_digit=False)
def select_address(message):
    bot.send_message(message.chat.id, "Пожалуйста введите число")


# получение геолокации с помощью специальной функции Телеграма
@bot.message_handler(state=MyStates.address, content_types=['location'])
def address_location(message):
    bot.set_state(message.from_user.id, MyStates.event, message.chat.id)
    event = get_events(message.location.latitude, message.location.longitude, 1)
    bot.send_message(message.chat.id, event, disable_web_page_preview=True)

    # сохранение данных, введённых пользователем, в специальное хранилище
    with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
        data['page'] = 1
        data['lat'] = message.location.latitude
        data['lon'] = message.location.longitude


# вывод следующей страницы мероприятий
@bot.message_handler(state=MyStates.event, is_digit=True)
def events(message):
    # обработка ввода пользователя
    num = int(message.text)
    with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
        if num == 0:
            data['page'] += 1
            # получение списка мероприятий
            event = get_events(data['lat'], data['lon'], data['page'])
            bot.send_message(message.chat.id, event, disable_web_page_preview=True)
        else:
            bot.send_message(message.chat.id, "Чтобы остановить бота, напишите /stop")


# отдельная обработка ввода, если пользователь ввёл неправильное сообщение
@bot.message_handler(state=MyStates.event, is_digit=False)
def events(message):
    bot.send_message(message.chat.id, "Пожалуйста введите число")


# запуск бота
bot.add_custom_filter(custom_filters.StateFilter(bot))
bot.add_custom_filter(custom_filters.IsDigitFilter())

bot.infinity_polling(skip_pending=True)
