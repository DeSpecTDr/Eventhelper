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

geolocator = Nominatim(user_agent="Eventhelper")

state_storage = StateMemoryStorage()
bot = telebot.TeleBot("5345404061:AAEa-GVN9ZkWn9b-NzUCGMwfl6rTWaz_VvY", state_storage=state_storage)

class MyStates(StatesGroup):
    address = State()
    select_address = State()
    event = State()

@bot.message_handler(state="*", commands='stop')
def stop(message):
    bot.send_message(message.chat.id, "Отмена")
    bot.delete_state(message.from_user.id, message.chat.id)

@bot.message_handler(commands=['start', 'help'])
def start(message):
    bot.set_state(message.from_user.id, MyStates.address, message.chat.id)
    bot.send_message(message.chat.id, 'Привет! Где будем сегодня? Скинь геолокацию или напиши адрес:')

def get_addresses(locations):
    text = "Выберите номер вашего адреса из списка:"
    for k, v in enumerate(locations):
        text += f"\n\n{k + 1} - {v.address}"
    text += "\n\nВведите 0 для отмены"
    return text

def get_events(latitude, longitude, page):
    t = round(time.time())
    r = requests.get(f'https://kudago.com/public-api/v1.4/events/?lang=ru'
                     f'&location=msk'
                     f'&page={page}'
                     f'&page_size=9'
                     f'&fields=id,title,is_free,dates,price,site_url'
                     f'&actual_since={t}'
                     f'&actual_until={t + 3600 * 24}'
                     f'&lat={latitude}'
                     f'&lon={longitude}'
                     f'&radius=5000').json()
    text = "События вблизи вас:"
    ev = []
    if (r.get('results') == None) or (len(r['results']) == 0):
        return text + '\n\nСобытий больше нету'
    for k, v in enumerate(r['results']):
        date = ""
        for d in v['dates']:
            if d['start'] < 0:
                continue
            if d['start'] < t < d['end']:
                date = "Идёт прямо сейчас"
            elif t < d['start']:
                date = f"Через {datetime.timedelta(seconds=d['start']-t)}"
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

@bot.message_handler(state=MyStates.address, content_types=['text'])
def address(message):
    try:
        locations = geolocator.geocode(message.text,
                                       language="ru",
                                       country_codes="ru",
                                       exactly_one=False,
                                       bounded=True,
                                       viewbox=((55.92746848810237, 37.33108560765978),
                                                (55.561842393045026, 38.03558386988545)))

    except geopy.exc.GeopyError:
        bot.send_message(message.chat.id, "Сервис перегружен, пропробуйте ещё раз через несколько секунд:")
        return

    if locations is None:
        bot.send_message(message.chat.id, "Адрес не найден, пропробуйте ещё раз:")
    else:
        bot.set_state(message.from_user.id, MyStates.select_address, message.chat.id)
        bot.send_message(message.chat.id, get_addresses(locations))
        with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
            data['locations'] = locations

@bot.message_handler(state=MyStates.select_address, is_digit=True)
def select_address(message):
    num = int(message.text)
    if num == 0:
        bot.set_state(message.from_user.id, MyStates.address, message.chat.id)
        bot.send_message(message.chat.id, 'Напишите адрес:')
        return
    with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
        location = data['locations'][num - 1] if len(data['locations']) >= num > 0 else None
        if location == None:
            bot.send_message(message.chat.id, 'Введите существующий номер адреса:')
            return
        bot.set_state(message.from_user.id, MyStates.event, message.chat.id)
        data['page'] = 1
        event = get_events(location.latitude, location.longitude, 1)
        bot.send_message(message.chat.id, event, disable_web_page_preview=True)
        data['lat'] = location.latitude
        data['lon'] = location.longitude

@bot.message_handler(state=MyStates.select_address, is_digit=False)
def select_address(message):
    bot.send_message(message.chat.id, "Пожалуйста введите число")

@bot.message_handler(state=MyStates.address, content_types=['location'])
def address_location(message):
    bot.set_state(message.from_user.id, MyStates.event, message.chat.id)
    event = get_events(message.location.latitude, message.location.longitude, 1)
    bot.send_message(message.chat.id, event, disable_web_page_preview=True)
    with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
        data['page'] = 1
        data['lat'] = message.location.latitude
        data['lon'] = message.location.longitude

@bot.message_handler(state=MyStates.event, is_digit=True)
def events(message):
    num = int(message.text)
    with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
        if num == 0:
            data['page'] += 1
            event = get_events(data['lat'], data['lon'], data['page'])
            bot.send_message(message.chat.id, event, disable_web_page_preview=True)
        else:
            bot.send_message(message.chat.id, "Чтобы остановить бота, напишите /stop")


@bot.message_handler(state=MyStates.event, is_digit=False)
def events(message):
    bot.send_message(message.chat.id, "Пожалуйста введите число")


bot.add_custom_filter(custom_filters.StateFilter(bot))
bot.add_custom_filter(custom_filters.IsDigitFilter())

bot.infinity_polling(skip_pending=True)
