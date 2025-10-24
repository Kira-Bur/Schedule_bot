import os
import requests
import zipfile
import shutil
import telebot
import time
import threading
from datetime import datetime
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
import io
from database import DatabaseManager
from image_processor import ImageProcessor
from admin_db import AdminManager

import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Настройки бота
BOT_TOKEN = '8274210121:AAGyTRNIInUGqYqP6dtvayTxxjXZm2Btn-Y'
DOWNLOAD_URL = 'http://docs.vztec.ru/index.php/s/W5yaNali0j7SSDD/download'
ZIP_FILENAME = 'schedule.zip'
EXTRACT_FOLDER = 'Расписание'
TARGET_FOLDERS = ['корпус №1 (ФМПК)', 'корпус №2 (ПТФ)']
UPDATE_INTERVAL = 60
MAIN_ADMIN_ID = 1347692271

# Инициализация компонентов
db_manager = DatabaseManager()
image_processor = ImageProcessor()
admin_manager = AdminManager()
bot = telebot.TeleBot(BOT_TOKEN)

# Состояния для FSM
admin_states = {}

def find_schedule_folder(base_path, building=1):
    """Поиск папки с расписанием для конкретного корпуса"""
    if not os.path.exists(base_path):
        return None
    
    # Определяем целевую папку по корпусу
    target_folder = None
    if building == 1:
        target_folder = 'корпус №1 (ФМПК)'
    elif building == 2:
        target_folder = 'корпус №2 (ПТФ)'
    
    # Сначала ищем конкретную папку
    if target_folder:
        potential_path = os.path.join(base_path, target_folder)
        if os.path.exists(potential_path) and os.path.isdir(potential_path):
            return potential_path
    
    # Если не нашли конкретную, ищем по ключевым словам
    for root, dirs, files in os.walk(base_path):
        for dir_name in dirs:
            lower_dir = dir_name.lower()
            if building == 1 and any(keyword in lower_dir for keyword in ['корпус 1', 'фмпк', 'корпус№1']):
                return os.path.join(root, dir_name)
            elif building == 2 and any(keyword in lower_dir for keyword in ['корпус 2', 'птф', 'корпус№2']):
                return os.path.join(root, dir_name)
    
    return None

def download_file(url, filename):
    """Скачивание файла по URL"""
    try:
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()
        
        with open(filename, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        return True
    except Exception as e:
        logger.error(f"Ошибка при скачивании: {e}")
        return False

def extract_zip(zip_path, extract_to):
    """Распаковка ZIP архива"""
    try:
        if os.path.exists(extract_to):
            shutil.rmtree(extract_to)
        
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall('.')
        
        return os.path.exists(extract_to)
    except Exception as e:
        logger.error(f"Ошибка при распаковке: {e}")
        return False

def get_schedule_files(building=1):
    """Получение списка файлов расписания для конкретного корпуса"""
    if not os.path.exists(EXTRACT_FOLDER):
        return []
    
    schedule_folder = find_schedule_folder(EXTRACT_FOLDER, building)
    
    if not schedule_folder:
        return []
    
    schedule_files = []
    
    for file in os.listdir(schedule_folder):
        file_path = os.path.join(schedule_folder, file)
        if os.path.isfile(file_path) and (file.lower().endswith('.docx') or file.lower().endswith('.xml')):
            schedule_files.append(file)
    
    return sorted(schedule_files)

def create_building_keyboard():
    """Создание клавиатуры для выбора корпуса"""
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("🏢 Корпус №1 (ФМПК)", callback_data='building_1'),
        InlineKeyboardButton("🏫 Корпус №2 (ПТФ)", callback_data='building_2')
    )
    return keyboard

def create_files_keyboard(building=1):
    """Создание клавиатуры с названиями файлов для конкретного корпуса"""
    files = get_schedule_files(building)
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    
    if files:
        # Добавляем кнопки с названиями файлов
        buttons = [KeyboardButton(file) for file in files]
        keyboard.add(*buttons)
    
    # Добавляем кнопку "Обновить список"
    keyboard.add(KeyboardButton("🔄 Обновить список"))
    
    # Добавляем кнопку "Сменить корпус"
    keyboard.add(KeyboardButton("🏢 Сменить корпус"))
    
    return keyboard

def create_admin_keyboard():
    """Создание клавиатуры для админов"""
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    keyboard.add(
        KeyboardButton("📊 Статистика"),
        KeyboardButton("📢 Отправить всем"),
        KeyboardButton("🔄 Обновить расписание"),
        KeyboardButton("❌ Выйти из админ-панели")
    )
    return keyboard

def send_file_to_user(chat_id, file_path, filename):
    """Отправка файла пользователю с оптимизацией размера"""
    try:
        img = image_processor.convert_to_image(file_path)
        
        if img:
            # Оптимизируем размер без изменения разрешения
            img_buffer = io.BytesIO()
            
            # Конвертируем в RGB если нужно (для JPEG)
            if img.mode in ('RGBA', 'LA'):
                background = Image.new('RGB', img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[-1])
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Сохраняем с оптимизацией (качество 85%, прогрессивная загрузка)
            img.save(img_buffer, format='JPEG', optimize=True, quality=85, progressive=True)
            img_buffer.seek(0)
            
            png_filename = os.path.splitext(filename)[0] + '.jpg'
            bot.send_document(chat_id, img_buffer, visible_file_name=png_filename)
            img_buffer.close()
        else:
            with open(file_path, 'rb') as f:
                bot.send_document(chat_id, f)
                
    except Exception as e:
        logger.error(f"Ошибка отправки файла пользователю {chat_id}: {e}")

def update_schedule():
    """Обновление расписания"""
    logger.info("Начало обновления расписания...")
    
    if download_file(DOWNLOAD_URL, ZIP_FILENAME):
        if extract_zip(ZIP_FILENAME, EXTRACT_FOLDER):
            logger.info("Расписание успешно обновлено")
            try:
                os.remove(ZIP_FILENAME)
            except:
                pass
            return True
    return False

def check_new_files(chat_id=None, building=None):
    """Проверка новых файлов и отправка только новых пользователям"""
    logger.info(f"Проверка новых файлов для корпуса {building if building else 'всех'}...")
    
    # Если указан конкретный корпус, проверяем только его
    if building is not None:
        buildings_to_check = [building]
    else:
        buildings_to_check = [1, 2]  # Проверяем оба корпуса
    
    all_new_files = []
    
    for current_building in buildings_to_check:
        schedule_folder = find_schedule_folder(EXTRACT_FOLDER, current_building)
        if not schedule_folder:
            logger.warning(f"Папка с расписанием для корпуса {current_building} не найдена")
            if chat_id and (building == current_building or building is None):
                bot.send_message(chat_id, f"❌ Папка с расписанием для корпуса {current_building} не найдена")
            continue
        
        current_files = get_schedule_files(current_building)
        
        # Если нет файлов, не очищаем базу - возможно временная проблема
        if not current_files:
            logger.warning(f"Не найдено файлов расписания для корпуса {current_building}.")
            if chat_id and (building == current_building or building is None):
                bot.send_message(chat_id, f"❌ Файлы расписания для корпуса {current_building} не найдены")
            continue
        
        known_files = db_manager.get_known_files(current_building)
        
        # Определяем, кому отправлять файлы
        if chat_id:
            # Отправляем только конкретному пользователю
            user_building = db_manager.get_user_building(chat_id)
            # Проверяем, что пользователь подписан на этот корпус
            if user_building == current_building:
                users = {chat_id: False}  # Предполагаем, что это не группа
                send_to_all = False
            else:
                users = {}
                send_to_all = False
        else:
            # Отправляем всем пользователям этого корпуса (автоматическая проверка)
            users = db_manager.get_users_by_building(current_building)
            send_to_all = True
        
        if not users:
            logger.info(f"Нет пользователей для корпуса {current_building} для отправки уведомлений")
            continue
        
        new_files = []
        updated_files = []
        
        for filename in current_files:
            file_path = os.path.join(schedule_folder, filename)
            if os.path.exists(file_path):
                current_hash = db_manager.get_file_hash(file_path)
                
                if filename not in known_files:
                    # Новый файл
                    new_files.append((filename, file_path, current_hash))
                    logger.info(f"Обнаружен новый файл для корпуса {current_building}: {filename}")
                elif known_files[filename] != current_hash:
                    # Файл изменился
                    updated_files.append((filename, file_path, current_hash))
                    logger.info(f"Файл изменен для корпуса {current_building}: {filename}")
        
        # Отправка новых и измененных файлов
        files_to_send = new_files + updated_files
        all_new_files.extend([(f[0], f[1], f[2], current_building) for f in files_to_send])
        
        if files_to_send:
            logger.info(f"Найдено {len(files_to_send)} файлов для отправки для корпуса {current_building}")
            
            # Формируем сообщение о новых файлах
            building_name = "Корпус №1 (ФМПК)" if current_building == 1 else "Корпус №2 (ПТФ)"
            
            if new_files:
                new_files_names = [f[0] for f in new_files]
                new_files_text = "\n".join([f"• {name}" for name in new_files_names])
                message_text = f"📥 Новые файлы расписания ({building_name}):\n{new_files_text}"
            else:
                message_text = f"📝 Обновленные файлы расписания ({building_name}):"
            
            if updated_files:
                updated_files_names = [f[0] for f in updated_files]
                updated_files_text = "\n".join([f"• {name}" for name in updated_files_names])
                message_text += f"\n\n🔄 Обновленные файлы:\n{updated_files_text}"
            
            # Отправляем уведомление и файлы
            for user_id, is_group in users.items():
                try:
                    # Отправляем сообщение о новых/обновленных файлах
                    if send_to_all or user_id == chat_id:
                        bot.send_message(user_id, message_text)
                    
                    # Отправляем сами файлы
                    for filename, file_path, file_hash in files_to_send:
                        send_file_to_user(user_id, file_path, filename)
                        time.sleep(0.1)  # Небольшая задержка между отправками
                    
                except Exception as e:
                    logger.error(f"Ошибка отправки пользователю {user_id}: {e}")
            
            # Сохраняем информацию о файлах после успешной отправки
            for filename, file_path, file_hash in files_to_send:
                if file_hash:
                    db_manager.save_file_info(filename, file_hash, current_building)
            
            # Очистка устаревших записей
            db_manager.cleanup_old_files(current_files, current_building)
            
        else:
            logger.info(f"Новых или измененных файлов не обнаружено для корпуса {current_building}")
            if chat_id and (building == current_building or building is None):
                bot.send_message(chat_id, f"✅ Для корпуса {current_building} новых файлов не обнаружено. Все актуально!")
    
    return all_new_files

def periodic_update():
    """Периодическое обновление и проверка файлов"""
    while True:
        try:
            if update_schedule():
                # Проверяем новые файлы для ВСЕХ пользователей, но каждый получит только файлы своего корпуса
                check_new_files()
            time.sleep(UPDATE_INTERVAL)
        except Exception as e:
            logger.error(f"Ошибка в periodic_update: {e}")
            time.sleep(UPDATE_INTERVAL)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    """Обработчик команды start"""
    try:
        # Определяем тип чата
        is_group = message.chat.type in ['group', 'supergroup']
        
        # Проверяем, есть ли пользователь уже в базе
        current_building = db_manager.get_user_building(message.chat.id)
        
        if current_building is None:
            # Если пользователь новый, просим выбрать корпус
            db_manager.add_user(message.chat.id, is_group, 1)  # Временно добавляем с корпусом 1
            keyboard = create_building_keyboard()
            welcome_text = (
                "👋 Добро пожаловать в бот расписания!\n\n"
                "📍 Пожалуйста, выберите ваш корпус:"
            )
            bot.send_message(message.chat.id, welcome_text, reply_markup=keyboard)
        else:
            # Если пользователь уже есть, показываем обычное меню
            db_manager.add_user(message.chat.id, is_group, current_building)
            
            schedule_folder = find_schedule_folder(EXTRACT_FOLDER, current_building)
            if schedule_folder:
                files = get_schedule_files(current_building)
                if files:
                    # Если это группа, не показываем клавиатуру
                    if is_group:
                        building_name = "Корпус №1 (ФМПК)" if current_building == 1 else "Корпус №2 (ПТФ)"
                        welcome_text = (
                            f"👋 Бот расписания готов к работе!\n\n"
                            f"📍 Ваш корпус: {building_name}\n"
                            f"📍 Новые файлы будут автоматически отправляться в эту группу"
                        )
                        bot.send_message(message.chat.id, welcome_text)
                    else:
                        # Для личных чатов показываем клавиатуру
                        keyboard = create_files_keyboard(current_building)
                        building_name = "Корпус №1 (ФМПК)" if current_building == 1 else "Корпус №2 (ПТФ)"
                        welcome_text = (
                            f"👋 Добро пожаловать!\n\n"
                            f"📍 Ваш корпус: {building_name}\n\n"
                            f"Выберите нужное расписание из списка ниже:\n\n"
                            f"📁 Доступно файлов: {len(files)}\n"
                            f"📍 Нажмите на название файла, чтобы получить его\n"
                            f"🔄 Нажмите 'Обновить список' для проверки новых файлов\n"
                            f"🏢 Нажмите 'Сменить корпус' для изменения корпуса"
                        )
                        bot.send_message(message.chat.id, welcome_text, reply_markup=keyboard)
                else:
                    bot.send_message(message.chat.id, "Файлы расписания не найдены")
            else:
                bot.send_message(message.chat.id, "Расписание не загружено")
            
    except Exception as e:
        logger.error(f"Ошибка в send_welcome: {e}")

@bot.message_handler(commands=['schedule'])
def show_schedule_for_groups(message):
    """Команда для показа расписания обоих корпусов в группах"""
    try:
        # Проверяем, что это группа
        if message.chat.type not in ['group', 'supergroup']:
            bot.send_message(message.chat.id, "❌ Эта команда работает только в группах!")
            return
        
        # Создаем инлайн-клавиатуру с обоими корпусами
        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton("🏢 Корпус №1 (ФМПК)", callback_data='schedule_building_1'),
            InlineKeyboardButton("🏫 Корпус №2 (ПТФ)", callback_data='schedule_building_2'),
            InlineKeyboardButton("📋 Оба корпуса", callback_data='schedule_both')
        )
        
        # Получаем текущий корпус группы
        current_building = db_manager.get_user_building(message.chat.id)
        current_building_name = "Корпус №1 (ФМПК)" if current_building == 1 else "Корпус №2 (ПТФ)"
        
        # Получаем количество файлов для каждого корпуса
        files_1 = get_schedule_files(1)
        files_2 = get_schedule_files(2)
        
        bot.send_message(
            message.chat.id,
            f"📅 РАСПИСАНИЕ ДЛЯ ГРУПП\n\n"
            f"📍 Текущий корпус группы: {current_building_name}\n"
            f"📁 Доступно файлов:\n"
            f"• Корпус 1: {len(files_1)} файлов\n"
            f"• Корпус 2: {len(files_2)} файлов\n\n"
            f"Выберите, расписание какого корпуса показать:",
            reply_markup=keyboard
        )
            
    except Exception as e:
        logger.error(f"Ошибка в show_schedule_for_groups: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка при выполнении команды!")

@bot.callback_query_handler(func=lambda call: call.data.startswith('schedule_'))
def handle_schedule_selection(call):
    """Обработчик выбора расписания для групп"""
    try:
        action = call.data.split('_')[1]
        
        if action == 'building':
            building = int(call.data.split('_')[2])
            send_schedule_files(call.message.chat.id, building, call.message.message_id)
            
        elif action == 'both':
            send_both_buildings_schedule(call.message.chat.id, call.message.message_id)
            
    except Exception as e:
        logger.error(f"Ошибка при выборе расписания: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка при загрузке расписания!")

def send_schedule_files(chat_id, building, message_id=None):
    """Отправка файлов расписания для конкретного корпуса"""
    try:
        building_name = "Корпус №1 (ФМПК)" if building == 1 else "Корпус №2 (ПТФ)"
        schedule_folder = find_schedule_folder(EXTRACT_FOLDER, building)
        
        if not schedule_folder:
            bot.send_message(chat_id, f"❌ Папка с расписанием для {building_name} не найдена")
            return
        
        files = get_schedule_files(building)
        
        if not files:
            bot.send_message(chat_id, f"❌ Файлы расписания для {building_name} не найдены")
            return
        
        # Обновляем сообщение с инлайн-клавиатурой
        if message_id:
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=f"📅 Отправляю расписание для {building_name}...",
                reply_markup=None
            )
        
        # Отправляем файлы
        bot.send_message(chat_id, f"📅 РАСПИСАНИЕ {building_name.upper()}:")
        
        for filename in files:
            file_path = os.path.join(schedule_folder, filename)
            if os.path.exists(file_path):
                try:
                    send_file_to_user(chat_id, file_path, filename)
                    time.sleep(0.5)  # Задержка между отправками
                except Exception as e:
                    logger.error(f"Ошибка отправки файла {filename}: {e}")
                    bot.send_message(chat_id, f"❌ Не удалось отправить файл: {filename}")
        
        # Создаем кнопку для возврата к выбору
        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineKeyboardButton("↩️ Вернуться к выбору", callback_data='back_to_schedule_menu'))
        
        bot.send_message(
            chat_id,
            f"✅ Расписание для {building_name} отправлено!\n"
            f"Всего файлов: {len(files)}",
            reply_markup=keyboard
        )
            
    except Exception as e:
        logger.error(f"Ошибка в send_schedule_files: {e}")
        bot.send_message(chat_id, "❌ Ошибка при отправке расписания!")

def send_both_buildings_schedule(chat_id, message_id=None):
    """Отправка расписания для обоих корпусов"""
    try:
        if message_id:
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text="📅 Отправляю расписание для обоих корпусов...",
                reply_markup=None
            )
        
        # Отправляем расписание для корпуса 1
        send_schedule_files(chat_id, 1, None)
        time.sleep(1)
        
        # Отправляем расписание для корпуса 2
        send_schedule_files(chat_id, 2, None)
        
        # Создаем кнопку для возврата к выбору
        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineKeyboardButton("↩️ Вернуться к выбору", callback_data='back_to_schedule_menu'))
        
        bot.send_message(
            chat_id,
            "✅ Расписание для обоих корпусов отправлено!",
            reply_markup=keyboard
        )
            
    except Exception as e:
        logger.error(f"Ошибка в send_both_buildings_schedule: {e}")
        bot.send_message(chat_id, "❌ Ошибка при отправке расписания!")

@bot.callback_query_handler(func=lambda call: call.data == 'back_to_schedule_menu')
def back_to_schedule_menu(call):
    """Возврат к меню выбора расписания"""
    try:
        # Просто повторно вызываем команду /raspisanie
        show_schedule_for_groups(call.message)
        
        # Удаляем предыдущее сообщение
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
            
    except Exception as e:
        logger.error(f"Ошибка в back_to_schedule_menu: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка при возврате в меню!")

@bot.callback_query_handler(func=lambda call: call.data.startswith('building_'))
def handle_building_selection(call):
    """Обработчик выбора корпуса"""
    try:
        building = int(call.data.split('_')[1])
        db_manager.set_user_building(call.message.chat.id, building)
        
        # Обновляем сообщение
        building_name = "Корпус №1 (ФМПК)" if building == 1 else "Корпус №2 (ПТФ)"
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"✅ Выбран {building_name}"
        )
        
        # Показываем меню с файлами
        schedule_folder = find_schedule_folder(EXTRACT_FOLDER, building)
        if schedule_folder:
            files = get_schedule_files(building)
            if files:
                keyboard = create_files_keyboard(building)
                welcome_text = (
                    f"👋 Добро пожаловать!\n\n"
                    f"📍 Ваш корпус: {building_name}\n\n"
                    f"Выберите нужное расписание из списка ниже:\n\n"
                    f"📁 Доступно файлов: {len(files)}\n"
                    f"📍 Нажмите на название файла, чтобы получить его\n"
                    f"🔄 Нажмите 'Обновить список' для проверки новых файлов\n"
                    f"🏢 Нажмите 'Сменить корпус' для изменения корпуса"
                )
                bot.send_message(call.message.chat.id, welcome_text, reply_markup=keyboard)
            else:
                bot.send_message(call.message.chat.id, f"Файлы расписания для {building_name} не найдены")
        else:
            bot.send_message(call.message.chat.id, f"Расписание для {building_name} не загружено")
            
    except Exception as e:
        logger.error(f"Ошибка при выборе корпуса: {e}")

@bot.message_handler(func=lambda message: message.text in get_schedule_files(1) + get_schedule_files(2))
def send_selected_file(message):
    """Обработчик выбора файла из клавиатуры"""
    try:
        # Проверяем, что это личный чат (в группах клавиатура не отображается)
        if message.chat.type in ['group', 'supergroup']:
            return
            
        filename = message.text
        building = db_manager.get_user_building(message.chat.id)
        
        # Проверяем файл в обоих корпусах
        schedule_folder_1 = find_schedule_folder(EXTRACT_FOLDER, 1)
        schedule_folder_2 = find_schedule_folder(EXTRACT_FOLDER, 2)
        
        file_path = None
        file_building = None
        
        if schedule_folder_1:
            potential_path = os.path.join(schedule_folder_1, filename)
            if os.path.exists(potential_path):
                file_path = potential_path
                file_building = 1
        
        if not file_path and schedule_folder_2:
            potential_path = os.path.join(schedule_folder_2, filename)
            if os.path.exists(potential_path):
                file_path = potential_path
                file_building = 2
        
        if file_path:
            bot.send_message(message.chat.id, f"📄 Отправляю файл: {filename}")
            send_file_to_user(message.chat.id, file_path, filename)
            
            # Сохраняем информацию о файле после отправки
            file_hash = db_manager.get_file_hash(file_path)
            if file_hash and file_building:
                db_manager.save_file_info(filename, file_hash, file_building)
        else:
            bot.send_message(message.chat.id, f"❌ Файл {filename} не найден")
            
    except Exception as e:
        logger.error(f"Ошибка при отправке выбранного файла: {e}")

@bot.message_handler(func=lambda message: message.text == "🔄 Обновить список")
def refresh_files_list(message):
    """Обработчик обновления списка файлов - с проверкой новых файлов"""
    try:
        # Проверяем, что это личный чат (в группах эта команда не работает)
        if message.chat.type in ['group', 'supergroup']:
            return

        building = db_manager.get_user_building(message.chat.id)
        building_name = "Корпус №1 (ФМПК)" if building == 1 else "Корпус №2 (ПТФ)"

        # Сначала обновляем расписание
        bot.send_message(message.chat.id, f"🔄 Обновляю расписание для {building_name}...")

        if update_schedule():
            # Проверяем новые файлы ТОЛЬКО для корпуса пользователя
            new_files = check_new_files(message.chat.id, building)

            # Обновляем клавиатуру в любом случае
            keyboard = create_files_keyboard(building)
            files = get_schedule_files(building)

            if files:
                if new_files:
                    # Если были новые файлы, сообщение уже отправлено в check_new_files
                    bot.send_message(message.chat.id,
                                   f"✅ Список обновлен для {building_name}!\n📁 Доступно файлов: {len(files)}",
                                   reply_markup=keyboard)
                else:
                    bot.send_message(message.chat.id,
                                   f"✅ Расписание обновлено для {building_name}!\n📁 Доступно файлов: {len(files)}\n🔄 Новых файлов не обнаружено",
                                   reply_markup=keyboard)
            else:
                bot.send_message(message.chat.id,
                               f"❌ Файлы расписания не найдены для {building_name}",
                               reply_markup=keyboard)
        else:
            bot.send_message(message.chat.id, "❌ Не удалось обновить расписание")

    except Exception as e:
        logger.error(f"Ошибка при обновлении списка файлов: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка при обновлении списка файлов")

@bot.message_handler(func=lambda message: message.text == "🏢 Сменить корпус")
def change_building(message):
    """Обработчик смены корпуса"""
    try:
        # Проверяем, что это личный чат
        if message.chat.type in ['group', 'supergroup']:
            return
            
        keyboard = create_building_keyboard()
        current_building = db_manager.get_user_building(message.chat.id)
        current_building_name = "Корпус №1 (ФМПК)" if current_building == 1 else "Корпус №2 (ПТФ)"
        
        bot.send_message(
            message.chat.id,
            f"📍 Ваш текущий корпус: {current_building_name}\n\n"
            "Выберите новый корпус:",
            reply_markup=keyboard
        )
            
    except Exception as e:
        logger.error(f"Ошибка при смене корпуса: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка при смене корпуса")

@bot.message_handler(commands=['status'])
def send_status(message):
    """Обработчик команды status"""
    try:
        users = db_manager.get_all_users()
        users_count = len(users)
        
        # Статистика по корпусам
        building_1_users = sum(1 for user_data in users.values() if user_data['building'] == 1)
        building_2_users = sum(1 for user_data in users.values() if user_data['building'] == 2)
        
        group_users_count = sum(1 for user_data in users.values() if user_data['is_group'])
        personal_users_count = users_count - group_users_count
        
        # Файлы по корпусам
        files_1 = get_schedule_files(1)
        files_2 = get_schedule_files(2)
        
        known_files_1 = db_manager.get_known_files(1)
        known_files_2 = db_manager.get_known_files(2)
        
        status_text = (
            f"📊 Статус бота:\n"
            f"• Пользователей: {users_count}\n"
            f"  - Группы: {group_users_count}\n"
            f"  - Личные чаты: {personal_users_count}\n"
            f"• По корпусам:\n"
            f"  - Корпус 1: {building_1_users} пользователей\n"
            f"  - Корпус 2: {building_2_users} пользователей\n"
            f"• Файлов расписания:\n"
            f"  - Корпус 1: {len(files_1)} файлов\n"
            f"  - Корпус 2: {len(files_2)} файлов\n"
            f"• Отслеживаемых файлов:\n"
            f"  - Корпус 1: {len(known_files_1)}\n"
            f"  - Корпус 2: {len(known_files_2)}\n"
        )
        
        bot.send_message(message.chat.id, status_text)
        
    except Exception as e:
        logger.error(f"Ошибка в send_status: {e}")
        bot.send_message(message.chat.id, "Ошибка получения статуса")

@bot.message_handler(commands=['college'])
def set_building_command(message):
    """Команда для смены корпуса с инлайн-клавиатурой"""
    try:
        # Проверяем, что это группа
        if message.chat.type not in ['group', 'supergroup']:
            bot.send_message(message.chat.id, "❌ Эта команда работает только в группах!")
            return
        
        # Создаем инлайн-клавиатуру
        keyboard = InlineKeyboardMarkup()
        keyboard.add(
            InlineKeyboardButton("🏢 Корпус №1 (ФМПК)", callback_data='group_building_1'),
            InlineKeyboardButton("🏫 Корпус №2 (ПТФ)", callback_data='group_building_2')
        )
        
        # Получаем текущий корпус группы
        current_building = db_manager.get_user_building(message.chat.id)
        current_building_name = "Корпус №1 (ФМПК)" if current_building == 1 else "Корпус №2 (ПТФ)"
        
        bot.send_message(
            message.chat.id,
            f"📍 Текущий корпус: {current_building_name}\n\n"
            "Выберите новый корпус для группы:",
            reply_markup=keyboard
        )
            
    except Exception as e:
        logger.error(f"Ошибка в set_building_command: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка при выполнении команды!")

@bot.callback_query_handler(func=lambda call: call.data.startswith('group_building_'))
def handle_group_building_selection(call):
    """Обработчик выбора корпуса для группы"""
    try:
        building = int(call.data.split('_')[2])
        building_name = "Корпус №1 (ФМПК)" if building == 1 else "Корпус №2 (ПТФ)"
        
        # Обновляем корпус для группы
        if db_manager.set_user_building(call.message.chat.id, building):
            # Обновляем сообщение
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=f"✅ Корпус группы успешно изменен на:\n{building_name}\n\n"
                     f"Теперь вы будете получать уведомления только о расписании для этого корпуса."
            )
        else:
            bot.answer_callback_query(call.id, "❌ Ошибка при изменении корпуса!")
            
    except Exception as e:
        logger.error(f"Ошибка при выборе корпуса группы: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка при изменении корпуса!")

@bot.message_handler(commands=['admin'])
def request_admin(message):
    """Запрос прав администратора"""
    try:
        user_id = message.from_user.id
        username = message.from_user.username
        first_name = message.from_user.first_name
        last_name = message.from_user.last_name
        
        # Проверяем, не является ли уже админом
        if admin_manager.is_admin(user_id):
            bot.send_message(message.chat.id, "✅ Вы уже являетесь администратором!")
            return
        
        # Проверяем, не отправлял ли уже запрос
        if admin_manager.is_pending_admin(user_id):
            bot.send_message(message.chat.id, "⏳ Ваш запрос уже отправлен и ожидает рассмотрения!")
            return
        
        # Добавляем запрос
        if admin_manager.add_admin_request(user_id, username, first_name, last_name):
            # Отправляем уведомление главному админу
            user_info = f"ID: {user_id}\nUsername: @{username}\nИмя: {first_name} {last_name}"
            
            keyboard = InlineKeyboardMarkup()
            keyboard.add(
                InlineKeyboardButton("✅ Одобрить", callback_data=f'approve_admin_{user_id}'),
                InlineKeyboardButton("❌ Отклонить", callback_data=f'reject_admin_{user_id}')
            )
            
            bot.send_message(
                MAIN_ADMIN_ID,
                f"🆕 Новый запрос на админство:\n\n{user_info}",
                reply_markup=keyboard
            )
            
            bot.send_message(
                message.chat.id,
                "✅ Ваш запрос на права администратора отправлен на рассмотрение!"
            )
        else:
            bot.send_message(message.chat.id, "❌ Ошибка при отправке запроса!")
            
    except Exception as e:
        logger.error(f"Ошибка в request_admin: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка при отправке запроса!")

@bot.message_handler(commands=['admin_panel'])
def admin_panel(message):
    """Панель администратора"""
    try:
        user_id = message.from_user.id
        
        if not admin_manager.is_admin(user_id):
            bot.send_message(message.chat.id, "❌ У вас нет прав администратора!")
            return
        
        # Входим в режим админа
        admin_states[user_id] = 'admin_mode'
        keyboard = create_admin_keyboard()
        
        bot.send_message(
            message.chat.id,
            "👨‍💻 Добро пожаловать в панель администратора!\n\n"
            "Выберите действие:",
            reply_markup=keyboard
        )
            
    except Exception as e:
        logger.error(f"Ошибка в admin_panel: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка при открытии панели админа!")

@bot.message_handler(func=lambda message: admin_states.get(message.from_user.id) == 'admin_mode')
def handle_admin_actions(message):
    """Обработчик действий админа"""
    try:
        user_id = message.from_user.id
        
        if message.text == "📊 Статистика":
            send_detailed_stats(message)
            
        elif message.text == "📢 Отправить всем":
            request_broadcast_message(message)
            
        elif message.text == "🔄 Обновить расписание":
            force_update_schedule(message)
            
        elif message.text == "❌ Выйти из админ-панели":
            exit_admin_panel(message)
            
    except Exception as e:
        logger.error(f"Ошибка в handle_admin_actions: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка при выполнении действия!")

def send_detailed_stats(message):
    """Отправка подробной статистики"""
    try:
        users = db_manager.get_all_users()
        admins = admin_manager.get_all_admins()
        pending_requests = admin_manager.get_pending_requests()
        pending_actions = admin_manager.get_pending_actions()
        
        stats_text = (
            f"📊 ДЕТАЛЬНАЯ СТАТИСТИКА:\n\n"
            f"👥 ПОЛЬЗОВАТЕЛИ:\n"
            f"• Всего: {len(users)}\n"
            f"• Группы: {sum(1 for u in users.values() if u['is_group'])}\n"
            f"• Личные чаты: {sum(1 for u in users.values() if not u['is_group'])}\n"
            f"• Корпус 1: {sum(1 for u in users.values() if u['building'] == 1)}\n"
            f"• Корпус 2: {sum(1 for u in users.values() if u['building'] == 2)}\n\n"
            f"👨‍💻 АДМИНИСТРАТОРЫ:\n"
            f"• Всего: {len(admins)}\n"
            f"• Ожидают одобрения: {len(pending_requests)}\n"
            f"• Ожидают действий: {len(pending_actions)}\n\n"
            f"📁 ФАЙЛЫ:\n"
            f"• Корпус 1: {len(get_schedule_files(1))} файлов\n"
            f"• Корпус 2: {len(get_schedule_files(2))} файлов\n"
            f"• Отслеживаемых: {len(db_manager.get_known_files(1)) + len(db_manager.get_known_files(2))}"
        )
        
        bot.send_message(message.chat.id, stats_text)
        
    except Exception as e:
        logger.error(f"Ошибка в send_detailed_stats: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка при получении статистики!")

def request_broadcast_message(message):
    """Запрос сообщения для рассылки"""
    try:
        admin_states[message.from_user.id] = 'awaiting_broadcast'
        bot.send_message(
            message.chat.id,
            "📝 Введите сообщение для рассылки всем пользователям:",
            reply_markup=ReplyKeyboardMarkup(resize_keyboard=True).add(KeyboardButton("❌ Отмена"))
        )
        
    except Exception as e:
        logger.error(f"Ошибка в request_broadcast_message: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка при запросе сообщения!")

@bot.message_handler(func=lambda message: admin_states.get(message.from_user.id) == 'awaiting_broadcast')
def handle_broadcast_message(message):
    """Обработка сообщения для рассылки"""
    try:
        if message.text == "❌ Отмена":
            exit_admin_panel(message)
            return
        
        # Добавляем действие для подтверждения
        action_id = admin_manager.add_admin_action(
            message.from_user.id,
            'broadcast',
            message.text
        )
        
        if action_id:
            # Отправляем запрос на подтверждение главному админу
            admin_info = f"Админ: @{message.from_user.username or message.from_user.first_name}"
            
            keyboard = InlineKeyboardMarkup()
            keyboard.add(
                InlineKeyboardButton("✅ Одобрить рассылку", callback_data=f'approve_broadcast_{action_id}'),
                InlineKeyboardButton("❌ Отклонить", callback_data=f'reject_broadcast_{action_id}')
            )
            
            bot.send_message(
                MAIN_ADMIN_ID,
                f"📢 ЗАПРОС НА РАССЫЛКУ:\n\n"
                f"{admin_info}\n\n"
                f"Сообщение:\n{message.text}",
                reply_markup=keyboard
            )
            
            bot.send_message(
                message.chat.id,
                "✅ Запрос на рассылку отправлен на подтверждение главному администратору!"
            )
            
            # Возвращаемся в обычный режим админа
            admin_states[message.from_user.id] = 'admin_mode'
            
        else:
            bot.send_message(message.chat.id, "❌ Ошибка при создании запроса на рассылку!")
            
    except Exception as e:
        logger.error(f"Ошибка в handle_broadcast_message: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка при обработке сообщения!")

def force_update_schedule(message):
    """Принудительное обновление расписания"""
    try:
        bot.send_message(message.chat.id, "🔄 Принудительное обновление расписания...")
        
        if update_schedule():
            new_files = check_new_files()
            
            if new_files:
                bot.send_message(message.chat.id, f"✅ Расписание обновлено! Найдено {len(new_files)} новых/измененных файлов.")
            else:
                bot.send_message(message.chat.id, "✅ Расписание обновлено! Новых файлов не обнаружено.")
        else:
            bot.send_message(message.chat.id, "❌ Не удалось обновить расписание!")
            
    except Exception as e:
        logger.error(f"Ошибка в force_update_schedule: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка при обновлении расписания!")

def exit_admin_panel(message):
    """Выход из панели админа"""
    try:
        user_id = message.from_user.id
        if user_id in admin_states:
            del admin_states[user_id]
        
        # Возвращаем обычную клавиатуру
        building = db_manager.get_user_building(user_id)
        if building:
            keyboard = create_files_keyboard(building)
            bot.send_message(
                message.chat.id,
                "✅ Вы вышли из панели администратора.",
                reply_markup=keyboard
            )
        else:
            bot.send_message(
                message.chat.id,
                "✅ Вы вышли из панели администратора.",
                reply_markup=ReplyKeyboardRemove()
            )
            
    except Exception as e:
        logger.error(f"Ошибка в exit_admin_panel: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith(('approve_admin_', 'reject_admin_')))
def handle_admin_approval(call):
    """Обработчик одобрения/отклонения админов"""
    try:
        action = call.data.split('_')[0]
        user_id = int(call.data.split('_')[2])
        
        if action == 'approve':
            first_name = admin_manager.approve_admin(user_id, call.from_user.id)
            if first_name:
                # Уведомляем одобренного админа
                try:
                    bot.send_message(
                        user_id,
                        f"✅ Ваш запрос на права администратора одобрен!\n\n"
                        f"Используйте команду /admin_panel для доступа к панели управления."
                    )
                except:
                    pass
                
                bot.answer_callback_query(call.id, f"✅ {first_name} теперь администратор!")
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=f"✅ Администратор одобрен: {first_name}"
                )
            else:
                bot.answer_callback_query(call.id, "❌ Ошибка одобрения!")
                
        else:  # reject
            if admin_manager.reject_admin(user_id):
                # Уведомляем отклоненного пользователя
                try:
                    bot.send_message(
                        user_id,
                        "❌ Ваш запрос на права администратора отклонен."
                    )
                except:
                    pass
                
                bot.answer_callback_query(call.id, "✅ Запрос отклонен!")
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text="❌ Запрос на админство отклонен"
                )
            else:
                bot.answer_callback_query(call.id, "❌ Ошибка отклонения!")
                
    except Exception as e:
        logger.error(f"Ошибка в handle_admin_approval: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка обработки запроса!")

@bot.callback_query_handler(func=lambda call: call.data.startswith(('approve_broadcast_', 'reject_broadcast_')))
def handle_broadcast_approval(call):
    """Обработчик одобрения/отклонения рассылки"""
    try:
        action = call.data.split('_')[0]
        action_id = int(call.data.split('_')[2])
        
        if action == 'approve':
            result = admin_manager.approve_action(action_id, call.from_user.id)
            if result:
                action_type, action_data, admin_id = result
                
                # Выполняем рассылку
                users = db_manager.get_all_users()
                success_count = 0
                fail_count = 0
                
                for user_id in users.keys():
                    try:
                        bot.send_message(user_id, f"📢 ОБЪЯВЛЕНИЕ:\n\n{action_data}")
                        success_count += 1
                        time.sleep(0.1)
                    except:
                        fail_count += 1
                
                # Уведомляем админа о результате
                bot.send_message(
                    admin_id,
                    f"✅ Рассылка выполнена!\n"
                    f"• Успешно: {success_count}\n"
                    f"• Не удалось: {fail_count}"
                )
                
                bot.answer_callback_query(call.id, "✅ Рассылка одобрена и выполнена!")
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=f"✅ Рассылка выполнена!\nОтправлено: {success_count} пользователям"
                )
            else:
                bot.answer_callback_query(call.id, "❌ Ошибка одобрения рассылки!")
                
        else:  # reject
            if admin_manager.reject_action(action_id):
                # Уведомляем админа об отклонении
                admin_id = call.data.split('_')[2]
                try:
                    bot.send_message(
                        admin_id,
                        "❌ Ваш запрос на рассылку отклонен главным администратором."
                    )
                except:
                    pass
                
                bot.answer_callback_query(call.id, "✅ Рассылка отклонена!")
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text="❌ Рассылка отклонена"
                )
            else:
                bot.answer_callback_query(call.id, "❌ Ошибка отклонения рассылки!")
                
    except Exception as e:
        logger.error(f"Ошибка в handle_broadcast_approval: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка обработки рассылки!")

def main():
    """Основная функция"""
    logger.info("Запуск бота расписания...")
    
    # Первоначальное обновление расписания
    if update_schedule():
        # При первом запуске сохраняем все файлы как известные для обоих корпусов
        for building in [1, 2]:
            schedule_folder = find_schedule_folder(EXTRACT_FOLDER, building)
            if schedule_folder:
                files = get_schedule_files(building)
                for filename in files:
                    file_path = os.path.join(schedule_folder, filename)
                    file_hash = db_manager.get_file_hash(file_path)
                    if file_hash:
                        db_manager.save_file_info(filename, file_hash, building)
                logger.info(f"Сохранено {len(files)} файлов для корпуса {building} при первом запуске")
    
    # Запуск фонового обновления
    update_thread = threading.Thread(target=periodic_update, daemon=True)
    update_thread.start()
    
    logger.info("Бот запущен. Ожидание сообщений...")
    bot.infinity_polling()

if __name__ == "__main__":
    main()
