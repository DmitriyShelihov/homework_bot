from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
    ContextTypes
)

from datetime import datetime
import logging
import re

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация
TOKEN = '8080518586:AAGyBh5VBYNBbyji8rbQPnHz40Psz70rf0g'
ADMIN_ID = 1393947995

# Префиксы для callback_data
DELETE_PREFIX = "del_"
ASSIGN_HW_PREFIX = "hw_"
APPROVE_PREFIX = "approve_"
REJECT_PREFIX = "reject_"
MENTOR_PREFIX = "mentor_"
CHANGE_MENTOR_PREFIX = "change_mentor_"
ROLE_PREFIX = "role_"
REVIEW_PREFIX = "review_"
TASK_PREFIX = "task_"
SUBMISSION_PREFIX = "sub_"

# Состояния
REGISTER_STATES = {
    'START': 0,
    'NAME': 1,
    'FAMILY_NAME': 2,
    'WAIT_APPROVAL': 3
}

ASSIGN_HW_STATES = {
    'SELECT_STUDENT': 0,
    'RECEIVE_FILE': 1,
    'RECEIVE_DEADLINE': 2
}

SEND_TASK_STATES = {
    'SELECT_DEADLINE': 0,
    'RECEIVE_FILES': 1,
    'RECEIVE_COMMENT': 2
}

REVIEW_STATES = {
    'SELECT_SUBMISSION': 0,
    'RECEIVE_REVIEW': 1
}

class User:
    def __init__(self, chat_id, name, family_name, role, mentor_id=None, username=None):
        self.chat_id = chat_id
        self.name = name
        self.family_name = family_name
        self.role = role  # 'admin', 'mentor' или 'student'
        self.mentor_id = mentor_id
        self.username = username
        self.is_active = True

    def full_name(self):
        return f"{self.name} {self.family_name}"

# Хранилища данных
registered_users = []
pending_registrations = {}
user_homeworks = {}
submitted_tasks = {}
task_reviews = {}

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========

def find_user(chat_id):
    """Находит пользователя по chat_id"""
    return next((u for u in registered_users if u.chat_id == chat_id and u.is_active), None)

def get_active_users():
    """Возвращает список активных пользователей"""
    return [u for u in registered_users if u.is_active]

def get_students_for_mentor(mentor_id):
    """Возвращает список студентов для ментора"""
    return [u for u in get_active_users() if u.role == 'student' and u.mentor_id == mentor_id]

def get_mentors():
    """Возвращает список активных менторов"""
    return [u for u in get_active_users() if u.role == 'mentor']

def format_deadline(deadline_str):
    """Форматирует срок сдачи в читаемый вид"""
    try:
        deadline = datetime.strptime(deadline_str, "%d.%m.%Y %H:%M")
        return deadline.strftime("%d %b %Y в %H:%M")
    except ValueError:
        return deadline_str

# ========== ОСНОВНЫЕ КОМАНДЫ ==========

# Обновленные списки команд
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает список команд в зависимости от роли"""
    user = find_user(update.effective_user.id)
    
    if user:
        if user.role == 'admin':
            commands = [
                "/help - Показать это сообщение",
                "/register - Зарегистрировать нового пользователя",
                "/show_users - Показать всех пользователей",
                "/delete_user - Удалить пользователя",
                "/assign_homework - Назначить задание",
                "/change_mentor - Изменить ментора ученику",
                "/review_tasks - Проверить задания",
                "/cancel - Отменить текущее действие"
            ]
        elif user.role == 'mentor':
            commands = [
                "/help - Показать это сообщение",
                "/show_my_students - Мои ученики",
                "/review_tasks - Проверить задания",
                "/assign_homework - Назначить задание своим ученикам",
                "/cancel - Отменить текущее действие"
            ]
        else:  # student
            commands = [
                "/help - Показать это сообщение",
                "/send_task - Отправить выполненное задание",
                "/my_deadlines - Мои дедлайны",
                "/cancel - Отменить текущее действие"
            ]
        
        help_text = "Доступные команды:\n" + "\n".join(commands)
        help_text += "\n\n⚠️ Если бот не отвечает, попробуйте /cancel чтобы сбросить текущее состояние"
        await update.message.reply_text(help_text)
    else:
        await update.message.reply_text(
            "Используйте /register для регистрации.\n"
            "Если бот не отвечает, введите /cancel"
        )


# ========== СИСТЕМА РЕГИСТРАЦИИ ==========

async def register_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало регистрации с полным сбросом состояния"""
    user_id = update.effective_user.id
    
    # Полная очистка предыдущего состояния
    context.user_data.clear()
    
    # Удаляем любые предыдущие попытки регистрации
    if user_id in pending_registrations:
        del pending_registrations[user_id]
    
    # Проверка существующей активной регистрации
    existing_user = next((u for u in registered_users if u.chat_id == user_id and u.is_active), None)
    if existing_user:
        await update.message.reply_text(
            f"❌ Вы уже зарегистрированы как {existing_user.role}!\n"
            f"Имя: {existing_user.full_name()}"
        )
        return ConversationHandler.END
    
    await update.message.reply_text(
        "Введите ваше имя:\n\n"
        "ℹ️ Если передумаете, используйте /cancel"
    )
    return REGISTER_STATES['NAME']

async def register_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка имени"""
    name = update.message.text.strip()
    if not name or len(name) > 50:
        await update.message.reply_text("Пожалуйста, введите корректное имя (до 50 символов)")
        return REGISTER_STATES['NAME']
    
    context.user_data['name'] = name
    await update.message.reply_text("Введите вашу фамилию:")
    return REGISTER_STATES['FAMILY_NAME']

async def register_family_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка фамилии и запрос подтверждения"""
    family_name = update.message.text.strip()
    if not family_name or len(family_name) > 50:
        await update.message.reply_text("Пожалуйста, введите корректную фамилию (до 50 символов)")
        return REGISTER_STATES['FAMILY_NAME']
    
    user_id = update.effective_user.id
    context.user_data['family_name'] = family_name
    
    pending_registrations[user_id] = {
        'name': context.user_data['name'],
        'family_name': context.user_data['family_name'],
        'chat_id': user_id,
        'username': update.effective_user.username
    }
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Принять", callback_data=f"{APPROVE_PREFIX}{user_id}"),
            InlineKeyboardButton("❌ Отклонить", callback_data=f"{REJECT_PREFIX}{user_id}")
        ]
    ]
    
    await context.bot.send_message(
        ADMIN_ID,
        f"📝 Новый запрос на регистрацию:\n"
        f"👤 Имя: {context.user_data['name']}\n"
        f"👥 Фамилия: {context.user_data['family_name']}\n"
        f"🆔 ID: {user_id}\n"
        f"📛 Username: @{update.effective_user.username or 'нет'}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    await update.message.reply_text(
        "✅ Заявка отправлена администратору на рассмотрение. "
        "Вы получите уведомление, когда вашу регистрацию подтвердят."
    )
    return REGISTER_STATES['WAIT_APPROVAL']

async def register_user_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Полная отмена регистрации"""
    user_id = update.effective_user.id
    
    # Очищаем все следы регистрации
    if user_id in pending_registrations:
        del pending_registrations[user_id]
    
    context.user_data.clear()
    
    await update.message.reply_text(
        "✅ Регистрация отменена. Вы можете начать заново командой /register"
    )
    return ConversationHandler.END

async def approve_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Улучшенная обработка подтверждения регистрации"""
    query = update.callback_query
    await query.answer()
    
    try:
        if query.data.startswith(REJECT_PREFIX):
            user_id = int(query.data[len(REJECT_PREFIX):])
            if user_id in pending_registrations:
                # Уведомляем пользователя
                await context.bot.send_message(
                    user_id,
                    "❌ Ваша регистрация была отклонена администратором.\n"
                    "Попробуйте снова: /register"
                )
                del pending_registrations[user_id]
                await query.edit_message_text("✅ Регистрация отклонена")
            else:
                await query.edit_message_text("⚠️ Пользователь уже отменил регистрацию")
        
        elif query.data.startswith(APPROVE_PREFIX):
            user_id = int(query.data[len(APPROVE_PREFIX):])
            if user_id not in pending_registrations:
                await query.edit_message_text("⚠️ Данные регистрации устарели. Пользователь должен начать заново (/register)")
                return
            
            # Создаем клавиатуру выбора роли с проверкой актуальности
            keyboard = [
                [InlineKeyboardButton("Админ", callback_data=f"{ROLE_PREFIX}admin_{user_id}")],
                [InlineKeyboardButton("Ментор", callback_data=f"{ROLE_PREFIX}mentor_{user_id}")],
                [InlineKeyboardButton("Ученик", callback_data=f"{ROLE_PREFIX}student_{user_id}")]
            ]
            
            await query.edit_message_text(
                "Выберите роль для пользователя:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
    
    except Exception as e:
        logger.error(f"Ошибка при обработке подтверждения: {e}")
        await query.edit_message_text("❌ Произошла ошибка. Попробуйте еще раз")

async def assign_role(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора роли с проверкой состояния"""
    query = update.callback_query
    await query.answer()
    
    try:
        _, role, user_id = query.data.split('_')
        user_id = int(user_id)
        
        # Проверяем актуальность запроса
        if user_id not in pending_registrations:
            await query.edit_message_text("⚠️ Регистрация устарела. Пользователь должен начать заново (/register)")
            return
        
        user_data = pending_registrations[user_id]
        
        if role == 'student':
            mentors = [u for u in registered_users if u.role == 'mentor' and u.is_active]
            if not mentors:
                await query.edit_message_text("❌ Нет доступных менторов! Сначала зарегистрируйте ментора.")
                return
            
            keyboard = [
                [InlineKeyboardButton(
                    f"{m.full_name()} (@{m.username})" if m.username else m.full_name(),
                    callback_data=f"{MENTOR_PREFIX}{user_id}_{m.chat_id}"
                )] for m in mentors
            ]
            
            await query.edit_message_text(
                "Выберите ментора для ученика:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            # Регистрация админа или ментора
            new_user = User(
                chat_id=user_id,
                name=user_data['name'],
                family_name=user_data['family_name'],
                role=role,
                username=user_data.get('username')
            )
            registered_users.append(new_user)
            del pending_registrations[user_id]
            
            role_name = "администратор" if role == 'admin' else "ментор"
            await context.bot.send_message(
                user_id, 
                f"🎉 Вы успешно зарегистрированы как {role_name}!"
            )
            await query.edit_message_text(f"✅ Пользователь зарегистрирован как {role}")
    
    except Exception as e:
        logger.error(f"Ошибка при назначении роли: {e}")
        await query.edit_message_text("❌ Произошла ошибка при регистрации")

async def assign_mentor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Прикрепление ментора к ученику"""
    query = update.callback_query
    await query.answer()
    
    _, student_id, mentor_id = query.data.split('_')
    student_id = int(student_id)
    mentor_id = int(mentor_id)
    user_data = pending_registrations.get(student_id)
    
    if not user_data:
        await query.edit_message_text("Ошибка: данные пользователя не найдены.")
        return
    
    # Создаем пользователя
    new_user = User(
        chat_id=student_id,
        name=user_data['name'],
        family_name=user_data['family_name'],
        role='student',
        mentor_id=mentor_id,
        username=user_data.get('username')
    )
    registered_users.append(new_user)
    del pending_registrations[student_id]
    
    # Уведомляем ученика и ментора
    mentor = find_user(mentor_id)
    await context.bot.send_message(
        student_id, 
        f"🎉 Поздравляем! Вы успешно зарегистрированы как ученик.\n"
        f"Ваш ментор: {mentor.full_name()}"
        f"{' (@' + mentor.username + ')' if mentor.username else ''}"
    )
    
    await context.bot.send_message(
        mentor_id, 
        f"📌 Вам назначен новый ученик:\n"
        f"👤 Имя: {new_user.full_name()}\n"
        f"🆔 ID: {new_user.chat_id}\n"
        f"📛 Username: @{new_user.username if new_user.username else 'нет'}"
    )
    
    await query.edit_message_text(
        f"✅ Ученик {new_user.full_name()} успешно зарегистрирован.\n"
        f"Ментор: {mentor.full_name()}"
    )

# ========== НАЗНАЧЕНИЕ ДОМАШНЕГО ЗАДАНИЯ ==========

async def assign_homework(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало процесса назначения домашнего задания"""
    user = find_user(update.effective_user.id)
    if not user or user.role not in ['admin', 'mentor']:
        await update.message.reply_text("❌ Эта команда доступна только администраторам и менторам.")
        return
    
    students = []
    if user.role == 'admin':
        students = [u for u in get_active_users() if u.role == 'student']
    else:  # mentor
        students = get_students_for_mentor(user.chat_id)
    
    if not students:
        await update.message.reply_text("ℹ️ Нет доступных учеников для назначения задания.")
        return
    
    keyboard = [
        [InlineKeyboardButton(
            f"{s.full_name()} (@{s.username})" if s.username else s.full_name(),
            callback_data=f"{ASSIGN_HW_PREFIX}{s.chat_id}"
        )]
        for s in students
    ]
    
    await update.message.reply_text(
        "Выберите ученика для назначения задания:\n\n"
        "ℹ️ Для отмены используйте /cancel",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ASSIGN_HW_STATES['SELECT_STUDENT']

async def select_student_for_homework(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора ученика для задания"""
    query = update.callback_query
    await query.answer()
    
    student_id = int(query.data[len(ASSIGN_HW_PREFIX):])
    student = find_user(student_id)
    
    if not student:
        await query.edit_message_text("❌ Ученик не найден.")
        return ConversationHandler.END
    
    context.user_data['student_id'] = student_id
    context.user_data['student_name'] = student.full_name()
    
    await query.edit_message_text(
        f"Вы выбрали ученика: {student.full_name()}\n"
        "Прикрепите файл с заданием (PDF, Word, изображение) или отправьте текстовое описание:"
    )
    return ASSIGN_HW_STATES['RECEIVE_FILE']

async def receive_homework_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка прикрепленного файла задания"""
    file_info = None
    if update.message.document:
        file_info = {
            'file_id': update.message.document.file_id,
            'file_type': 'document',
            'file_name': update.message.document.file_name
        }
    elif update.message.photo:
        file_info = {
            'file_id': update.message.photo[-1].file_id,
            'file_type': 'photo'
        }
    elif update.message.text:
        file_info = {
            'file_type': 'text',
            'text': update.message.text
        }
    else:
        await update.message.reply_text("ℹ️ Пожалуйста, пришлите файл или текстовое описание задания.")
        return ASSIGN_HW_STATES['RECEIVE_FILE']
    
    context.user_data['hw_file'] = file_info
    await update.message.reply_text(
        "📎 Задание получено. Теперь укажите дедлайн в формате ДД.ММ.ГГГГ ЧЧ:MM (например: 31.12.2023 23:59):"
    )
    return ASSIGN_HW_STATES['RECEIVE_DEADLINE']

async def receive_homework_deadline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка дедлайна для задания"""
    deadline_text = update.message.text.strip()
    student_id = context.user_data.get('student_id')
    hw_file = context.user_data.get('hw_file')
    student_name = context.user_data.get('student_name')
    
    # Проверка формата даты
    if not re.match(r'^\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}$', deadline_text):
        await update.message.reply_text("❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ ЧЧ:MM (например: 31.12.2023 23:59)")
        return ASSIGN_HW_STATES['RECEIVE_DEADLINE']
    
    try:
        deadline = datetime.strptime(deadline_text, "%d.%m.%Y %H:%M")
        if deadline < datetime.now():
            await update.message.reply_text("❌ Дедлайн не может быть в прошлом. Укажите будущую дату.")
            return ASSIGN_HW_STATES['RECEIVE_DEADLINE']
    except ValueError:
        await update.message.reply_text("❌ Неверная дата. Пожалуйста, укажите корректную дату.")
        return ASSIGN_HW_STATES['RECEIVE_DEADLINE']
    
    # Сохраняем задание для ученика
    if student_id not in user_homeworks:
        user_homeworks[student_id] = []
    
    task_id = f"task_{datetime.now().timestamp()}"
    user_homeworks[student_id].append({
        'task_id': task_id,
        'deadline': deadline_text,
        'file_info': hw_file,
        'assigned_by': update.effective_user.id,
        'assigned_at': datetime.now().strftime("%d.%m.%Y %H:%M")
    })
    
    # Отправляем задание ученику
    try:
        student = find_user(student_id)
        if not student:
            await update.message.reply_text("❌ Ученик не найден.")
            return ConversationHandler.END
        
        caption = (
            f"📌 Новое домашнее задание\n"
            f"Дедлайн: {format_deadline(deadline_text)}\n"
            f"От: {update.effective_user.full_name}"
        )
        
        if hw_file['file_type'] == 'document':
            await context.bot.send_document(
                student_id,
                document=hw_file['file_id'],
                caption=caption
            )
        elif hw_file['file_type'] == 'photo':
            await context.bot.send_photo(
                student_id,
                photo=hw_file['file_id'],
                caption=caption
            )
        else:  # text
            await context.bot.send_message(
                student_id,
                text=f"{caption}\n\nОписание задания:\n{hw_file['text']}"
            )
        
        await update.message.reply_text(f"✅ Задание успешно назначено ученику {student_name}!")
    except Exception as e:
        logger.error(f"Ошибка при отправке задания: {e}")
        await update.message.reply_text("❌ Не удалось отправить задание ученику.")
    
    return ConversationHandler.END

# ========== СИСТЕМА СДАЧИ ЗАДАНИЙ ==========

# Обновленная команда для просмотра дедлайнов
async def show_deadlines(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает список дедлайнов с указанием учеников (для менторов)"""
    user = find_user(update.effective_user.id)
    
    if not user:
        await update.message.reply_text("❌ Вы не зарегистрированы. Используйте /register")
        return
    
    if user.role == 'student':
        # Для ученика - только его дедлайны
        if user.chat_id in user_homeworks and user_homeworks[user.chat_id]:
            deadlines = []
            for hw in user_homeworks[user.chat_id]:
                deadline = format_deadline(hw['deadline'])
                status = "✅ Активно" if datetime.now() < datetime.strptime(hw['deadline'], "%d.%m.%Y %H:%M") else "❌ Просрочено"
                deadlines.append(f"• {deadline} - {status}")
            
            text = "📅 Ваши дедлайны:\n" + "\n".join(deadlines)
            text += "\n\nДля сдачи задания используйте /send_task"
        else:
            text = "ℹ️ У вас нет активных заданий."
        
        await update.message.reply_text(text)
    
    elif user.role == 'mentor':
        # Для ментора - дедлайны его учеников
        students = get_students_for_mentor(user.chat_id)
        if not students:
            await update.message.reply_text("ℹ️ У вас пока нет учеников.")
            return
        
        text = "📅 Дедлайны ваших учеников:\n"
        for student in students:
            if student.chat_id in user_homeworks and user_homeworks[student.chat_id]:
                student_deadlines = []
                for hw in user_homeworks[student.chat_id]:
                    deadline = format_deadline(hw['deadline'])
                    status = "✅ Активно" if datetime.now() < datetime.strptime(hw['deadline'], "%d.%m.%Y %H:%M") else "❌ Просрочено"
                    student_deadlines.append(f"  • {deadline} - {status}")
                
                text += f"\n👤 {student.full_name()}:\n" + "\n".join(student_deadlines)
            else:
                text += f"\n👤 {student.full_name()}: нет активных заданий"
        
        text += "\n\nДля проверки заданий используйте /review_tasks"
        await update.message.reply_text(text)
    
    else:  # admin
        # Для админа - все активные дедлайны
        active_hw = {}
        for student_id, assignments in user_homeworks.items():
            student = find_user(student_id)
            if student:
                for hw in assignments:
                    if hw['task_id'] not in active_hw:
                        active_hw[hw['task_id']] = {
                            'deadline': hw['deadline'],
                            'students': []
                        }
                    active_hw[hw['task_id']]['students'].append(student.full_name())
        
        if not active_hw:
            await update.message.reply_text("ℹ️ Нет активных заданий у учеников.")
            return
        
        text = "📅 Все активные дедлайны:\n"
        for task_id, data in active_hw.items():
            deadline = format_deadline(data['deadline'])
            status = "✅ Активно" if datetime.now() < datetime.strptime(data['deadline'], "%d.%m.%Y %H:%M") else "❌ Просрочено"
            text += f"\n• {deadline} - {status}\n"
            text += "  👥 Ученики: " + ", ".join(data['students'])
        
        await update.message.reply_text(text)


async def send_task_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало процесса сдачи задания"""
    user_id = update.effective_user.id
    user = find_user(user_id)
    
    if not user:
        await update.message.reply_text("❌ Вы не зарегистрированы. Используйте /register.")
        return ConversationHandler.END
    
    if user_id not in user_homeworks or not user_homeworks[user_id]:
        await update.message.reply_text("ℹ️ У вас нет активных заданий для сдачи.")
        return ConversationHandler.END
    
    keyboard = []
    for idx, hw in enumerate(user_homeworks[user_id]):
        deadline_text = format_deadline(hw['deadline'])
        keyboard.append([
            InlineKeyboardButton(
                f"{idx+1}. Дедлайн: {deadline_text}",
                callback_data=f"deadline_{idx}"
            )
        ])
    
    await update.message.reply_text(
        "Выберите задание для сдачи:\n\n"
        "ℹ️ Для отмены используйте /cancel",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SEND_TASK_STATES['SELECT_DEADLINE']

async def select_deadline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора задания для сдачи"""
    query = update.callback_query
    await query.answer()
    
    deadline_idx = int(query.data.split('_')[1])
    user_id = query.from_user.id
    
    if user_id not in user_homeworks or deadline_idx >= len(user_homeworks[user_id]):
        await query.edit_message_text("❌ Произошла ошибка. Пожалуйста, попробуйте снова.")
        return ConversationHandler.END
    
    task = user_homeworks[user_id][deadline_idx]
    context.user_data.update({
        'selected_deadline_idx': deadline_idx,
        'task_id': task['task_id'],
        'deadline': task['deadline'],
        'files': []
    })
    
    await query.edit_message_text(
        f"Вы выбрали задание с дедлайном: {format_deadline(task['deadline'])}\n\n"
        "Прикрепите файлы с выполненным заданием (фото, PDF и т.д.). "
        "Когда закончите, нажмите /done_files"
    )
    return SEND_TASK_STATES['RECEIVE_FILES']

async def receive_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка прикрепленных файлов задания"""
    if update.message.document:
        file_type = 'document'
        file_id = update.message.document.file_id
        file_name = update.message.document.file_name
    elif update.message.photo:
        file_type = 'photo'
        file_id = update.message.photo[-1].file_id
        file_name = None
    else:
        await update.message.reply_text("ℹ️ Пожалуйста, присылайте только файлы (фото или документы).")
        return SEND_TASK_STATES['RECEIVE_FILES']
    
    context.user_data.setdefault('files', []).append({
        'type': file_type,
        'id': file_id,
        'name': file_name
    })
    
    await update.message.reply_text(
        f"📎 {'Документ' if file_type == 'document' else 'Фото'} "
        f"{'(' + file_name + ')' if file_name else ''} получен. "
        "Можете прислать еще файлы или нажмите /done_files для продолжения."
    )
    return SEND_TASK_STATES['RECEIVE_FILES']

async def done_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Завершение приема файлов"""
    if not context.user_data.get('files'):
        await update.message.reply_text("❌ Вы не прикрепили ни одного файла. Пожалуйста, прикрепите хотя бы один файл.")
        return SEND_TASK_STATES['RECEIVE_FILES']
    
    await update.message.reply_text(
        "📎 Файлы получены. Теперь вы можете добавить комментарий к заданию "
        "(или отправьте /skip_comment чтобы пропустить)."
    )
    return SEND_TASK_STATES['RECEIVE_COMMENT']

async def receive_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка комментария к заданию"""
    context.user_data['comment'] = update.message.text
    await finish_task_submission(update, context)
    return ConversationHandler.END

async def skip_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Пропуск комментария"""
    context.user_data['comment'] = "Без комментария"
    await finish_task_submission(update, context)
    return ConversationHandler.END

async def finish_task_submission(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Завершение процесса сдачи задания"""
    user_id = update.effective_user.id
    user = find_user(user_id)
    deadline_idx = context.user_data.get('selected_deadline_idx')
    
    if (deadline_idx is None or user_id not in user_homeworks or 
        deadline_idx >= len(user_homeworks[user_id])):
        await update.message.reply_text("❌ Произошла ошибка при обработке задания. Пожалуйста, попробуйте снова.")
        return ConversationHandler.END
    
    task = user_homeworks[user_id][deadline_idx]
    deadline_str = task['deadline']
    
    try:
        deadline = datetime.strptime(deadline_str, "%d.%m.%Y %H:%M")
        submitted_at = datetime.now()
        on_time = submitted_at <= deadline
    except ValueError:
        on_time = False
    
    if user_id not in submitted_tasks:
        submitted_tasks[user_id] = []
    
    submission_id = f"sub_{datetime.now().timestamp()}"
    submission_data = {
        'submission_id': submission_id,
        'task_id': task['task_id'],
        'files': context.user_data.get('files', []),
        'comment': context.user_data.get('comment', 'Без комментария'),
        'submitted_at': submitted_at.strftime("%d.%m.%Y %H:%M"),
        'on_time': on_time,
        'student_id': user_id,
        'student_name': user.full_name(),
        'student_username': user.username,
        'deadline': deadline_str,
        'assigned_by': task.get('assigned_by'),
        'status': 'submitted',
        'review': None
    }
    
    submitted_tasks[user_id].append(submission_data)
    
    # Удаляем задание из списка активных
    del user_homeworks[user_id][deadline_idx]
    
    # Уведомляем ментора и администратора
    mentor_id = user.mentor_id
    if mentor_id:
        await notify_mentor_about_submission(mentor_id, submission_data)
    
    if ADMIN_ID and ADMIN_ID != mentor_id:
        await notify_admin_about_submission(submission_data)
    
    await update.message.reply_text(
        "✅ Ваше задание успешно сдано! Спасибо за работу.\n"
        "Ментор проверит его и отправит вам отзыв."
    )
    return ConversationHandler.END

async def notify_mentor_about_submission(mentor_id, submission_data):
    """Уведомление ментора о сданном задании"""
    try:
        bot = ApplicationBuilder().token(TOKEN).build().bot
        mentor = find_user(mentor_id)
        if not mentor:
            return
        
        student = find_user(submission_data['student_id'])
        if not student:
            return
        
        deadline_status = "✅ Успел в срок" if submission_data['on_time'] else "❌ Опоздал"
        
        message_text = (
            f"📬 Новое сданное задание от вашего ученика!\n\n"
            f"👤 Ученик: {student.full_name()}\n"
            f"📛 Username: @{student.username if student.username else 'нет'}\n"
            f"🆔 ID: {student.chat_id}\n"
            f"📅 Дедлайн: {format_deadline(submission_data['deadline'])}\n"
            f"📩 Сдано: {format_deadline(submission_data['submitted_at'])}\n"
            f"🕒 Статус: {deadline_status}\n"
            f"💬 Комментарий: {submission_data['comment']}\n\n"
            f"Используйте /review_tasks чтобы проверить задание."
        )
        
        await bot.send_message(mentor_id, message_text)
        
        # Отправляем файлы ментору
        for file_info in submission_data.get('files', []):
            if file_info['type'] == 'photo':
                await bot.send_photo(mentor_id, photo=file_info['id'])
            elif file_info['type'] == 'document':
                await bot.send_document(
                    mentor_id,
                    document=file_info['id'],
                    filename=file_info.get('name')
                )
    except Exception as e:
        logger.error(f"Ошибка при отправке уведомления ментору: {e}")

async def notify_admin_about_submission(submission_data):
    """Уведомление администратора о сданном задании"""
    if ADMIN_ID is None:
        return
    
    try:
        bot = ApplicationBuilder().token(TOKEN).build().bot
        student = find_user(submission_data['student_id'])
        if not student:
            return
        
        mentor = find_user(student.mentor_id) if student.mentor_id else None
        deadline_status = "✅ Успел в срок" if submission_data['on_time'] else "❌ Опоздал"
        
        message_text = (
            f"📬 Новое сданное задание!\n\n"
            f"👤 Ученик: {student.full_name()}\n"
            f"📛 Username: @{student.username if student.username else 'нет'}\n"
            f"🆔 ID: {student.chat_id}\n"
            f"👨‍🏫 Ментор: {mentor.full_name() if mentor else 'Не назначен'}\n"
            f"📅 Дедлайн: {format_deadline(submission_data['deadline'])}\n"
            f"📩 Сдано: {format_deadline(submission_data['submitted_at'])}\n"
            f"🕒 Статус: {deadline_status}\n"
            f"💬 Комментарий: {submission_data['comment']}"
        )
        
        await bot.send_message(ADMIN_ID, message_text)
        
        # Отправляем файлы администратору
        for file_info in submission_data.get('files', []):
            if file_info['type'] == 'photo':
                await bot.send_photo(ADMIN_ID, photo=file_info['id'])
            elif file_info['type'] == 'document':
                await bot.send_document(
                    ADMIN_ID,
                    document=file_info['id'],
                    filename=file_info.get('name')
                )
    except Exception as e:
        logger.error(f"Ошибка при отправке уведомления администратору: {e}")

# ========== ПРОВЕРКА ЗАДАНИЙ МЕНТОРОМ ==========

async def review_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало процесса проверки заданий"""
    user = find_user(update.effective_user.id)
    if not user or user.role not in ['admin', 'mentor']:
        await update.message.reply_text("❌ Эта команда доступна только менторам и администраторам.")
        return
    
    # Для ментора - только задания его учеников
    if user.role == 'mentor':
        student_ids = [s.chat_id for s in get_students_for_mentor(user.chat_id)]
        submissions = []
        for student_id in student_ids:
            if student_id in submitted_tasks:
                for task in submitted_tasks[student_id]:
                    if task.get('status') == 'submitted':
                        submissions.append((student_id, task))
    else:  # admin - все задания
        submissions = []
        for student_id, tasks in submitted_tasks.items():
            for task in tasks:
                if task.get('status') == 'submitted':
                    submissions.append((student_id, task))
    
    if not submissions:
        await update.message.reply_text("ℹ️ Нет заданий, ожидающих проверки.")
        return
    
    # Сохраняем список заданий для проверки в контексте
    context.user_data['submissions_to_review'] = submissions
    
    # Создаем клавиатуру с заданиями
    keyboard = []
    for idx, (student_id, task) in enumerate(submissions, 1):
        student = find_user(student_id)
        if not student:
            continue
        
        deadline_status = "✅ В срок" if task['on_time'] else "❌ Опоздание"
        btn_text = (
            f"{idx}. {student.full_name()} - "
            f"{format_deadline(task['deadline'])} "
            f"({deadline_status})"
        )
        
        keyboard.append([
            InlineKeyboardButton(
                btn_text,
                callback_data=f"{REVIEW_PREFIX}{idx-1}"
            )
        ])
    
    await update.message.reply_text(
        "Выберите задание для проверки:\n\n"
        "ℹ️ Для отмены используйте /cancel",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return REVIEW_STATES['SELECT_SUBMISSION']

async def select_submission_for_review(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора задания для проверки"""
    query = update.callback_query
    await query.answer()
    
    submission_idx = int(query.data[len(REVIEW_PREFIX):])
    submissions = context.user_data.get('submissions_to_review')
    
    if not submissions or submission_idx >= len(submissions):
        await query.edit_message_text("❌ Ошибка: задание не найдено.")
        return ConversationHandler.END
    
    student_id, submission = submissions[submission_idx]
    student = find_user(student_id)
    if not student:
        await query.edit_message_text("❌ Ошибка: ученик не найден.")
        return ConversationHandler.END
    
    # Сохраняем данные о выбранном задании
    context.user_data['current_submission'] = submission
    context.user_data['current_submission_idx'] = submission_idx
    context.user_data['student_id'] = student_id
    
    deadline_status = "✅ Сдано в срок" if submission['on_time'] else "❌ Сдано с опозданием"
    
    message_text = (
        f"📝 Задание от: {student.full_name()}\n"
        f"📅 Дедлайн: {format_deadline(submission['deadline'])}\n"
        f"📩 Сдано: {format_deadline(submission['submitted_at'])}\n"
        f"🕒 Статус: {deadline_status}\n"
        f"💬 Комментарий ученика: {submission['comment']}\n\n"
        "Отправьте ваш отзыв (текст или файл с исправлениями):"
    )
    
    await query.edit_message_text(message_text)
    return REVIEW_STATES['RECEIVE_REVIEW']

async def receive_review(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка отзыва ментора"""
    submission = context.user_data.get('current_submission')
    student_id = context.user_data.get('student_id')
    reviewer_id = update.effective_user.id
    
    if not submission or not student_id:
        await update.message.reply_text("❌ Ошибка: данные задания не найдены.")
        return ConversationHandler.END
    
    review_data = {
        'reviewer_id': reviewer_id,
        'reviewed_at': datetime.now().strftime("%d.%m.%Y %H:%M"),
        'status': 'reviewed'
    }
    
    if update.message.text:
        review_data['text'] = update.message.text
    elif update.message.document:
        review_data['file'] = {
            'file_id': update.message.document.file_id,
            'file_name': update.message.document.file_name,
            'file_type': 'document'
        }
    elif update.message.photo:
        review_data['file'] = {
            'file_id': update.message.photo[-1].file_id,
            'file_type': 'photo'
        }
    else:
        await update.message.reply_text("ℹ️ Пожалуйста, отправьте текст или файл с отзывом.")
        return REVIEW_STATES['RECEIVE_REVIEW']
    
    # Обновляем статус задания
    submission.update(review_data)
    
    # Уведомляем ученика
    await notify_student_about_review(student_id, submission, reviewer_id)
    
    await update.message.reply_text("✅ Ваш отзыв успешно отправлен ученику!")
    return ConversationHandler.END

async def notify_student_about_review(student_id, submission, reviewer_id):
    """Уведомление ученика о полученном отзыве"""
    try:
        bot = ApplicationBuilder().token(TOKEN).build().bot
        reviewer = find_user(reviewer_id)
        if not reviewer:
            return
        
        message_text = (
            f"📝 Вы получили отзыв на задание от {reviewer.full_name()}!\n"
            f"📅 Дедлайн: {format_deadline(submission['deadline'])}\n"
            f"📩 Сдано: {format_deadline(submission['submitted_at'])}\n\n"
        )
        
        if 'text' in submission:
            message_text += f"💬 Отзыв:\n{submission['text']}"
            await bot.send_message(student_id, message_text)
        elif 'file' in submission:
            message_text += "📎 Файл с отзывом:"
            await bot.send_message(student_id, message_text)
            
            file_info = submission['file']
            if file_info['file_type'] == 'document':
                await bot.send_document(
                    student_id,
                    document=file_info['file_id'],
                    filename=file_info.get('file_name')
                )
            else:
                await bot.send_photo(student_id, photo=file_info['file_id'])
    except Exception as e:
        logger.error(f"Ошибка при отправке отзыва ученику: {e}")

# ========== УПРАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯМИ ==========

async def delete_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удаление пользователя"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Эта команда доступна только администратору.")
        return
    
    active_users = get_active_users()
    if not active_users:
        await update.message.reply_text("ℹ️ Нет активных пользователей для удаления.")
        return
    
    keyboard = [
        [InlineKeyboardButton(
            f"{u.full_name()} ({u.role})",
            callback_data=f"{DELETE_PREFIX}{u.chat_id}"
        )]
        for u in active_users  # Теперь показываем всех пользователей, включая администратора
    ]
    
    await update.message.reply_text(
        "Выберите пользователя для удаления:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def delete_user_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение удаления пользователя"""
    query = update.callback_query
    await query.answer()
    
    user_id = int(query.data[len(DELETE_PREFIX):])
    current_user_id = query.from_user.id
    user = find_user(user_id)
    
    if not user:
        await query.edit_message_text("❌ Пользователь не найден.")
        return
    
    # Проверяем, не пытается ли администратор удалить себя
    if user_id == current_user_id:
        await query.edit_message_text("❌ Вы не можете удалить самого себя!")
        return
    
    # Помечаем пользователя как неактивного вместо полного удаления
    user.is_active = False
    
    # Уведомляем пользователя
    try:
        await context.bot.send_message(
            user_id,
            "❌ Ваш аккаунт был деактивирован администратором. "
            "Вы можете зарегистрироваться снова с помощью команды /register."
        )
    except Exception as e:
        logger.error(f"Не удалось уведомить пользователя об удалении: {e}")
    
    await query.edit_message_text(f"✅ Пользователь {user.full_name()} ({user.role}) удален.")

async def show_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает список всех зарегистрированных пользователей (только для администратора)"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Эта команда доступна только администратору.")
        return
    
    active_users = get_active_users()
    if not active_users:
        await update.message.reply_text("ℹ️ Нет активных пользователей.")
        return
    
    users_list = []
    for user in active_users:
        mentor_info = ""
        if user.role == 'student' and user.mentor_id:
            mentor = find_user(user.mentor_id)
            mentor_info = f" | Ментор: {mentor.full_name() if mentor else 'Не назначен'}"
        
        status = "✅ Активен" if user.is_active else "❌ Неактивен"
        username = f" (@{user.username})" if user.username else ""
        
        users_list.append(
            f"👤 {user.full_name()}{username} "
            f"({user.role.capitalize()}, ID: {user.chat_id}{mentor_info}) - {status}"
        )
    
    await update.message.reply_text("📋 Список пользователей:\n" + "\n".join(users_list))

async def show_my_students(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает список учеников ментора"""
    mentor_id = update.effective_user.id
    mentor = find_user(mentor_id)
    
    if not mentor or mentor.role != 'mentor':
        await update.message.reply_text("❌ Эта команда доступна только менторам.")
        return
    
    students = get_students_for_mentor(mentor_id)
    
    if not students:
        await update.message.reply_text("ℹ️ У вас пока нет учеников.")
        return
    
    students_list = []
    for idx, student in enumerate(students, 1):
        active_hw = len(user_homeworks.get(student.chat_id, []))
        submitted_hw = len(submitted_tasks.get(student.chat_id, []))
        
        username = f" (@{student.username})" if student.username else ""
        students_list.append(
            f"{idx}. {student.full_name()}{username}\n"
            f"   🆔 ID: {student.chat_id}\n"
            f"   📊 Активных заданий: {active_hw}\n"
            f"   📩 Сданных заданий: {submitted_hw}"
        )
    
    await update.message.reply_text(f"📋 Ваши ученики:\n\n" + "\n\n".join(students_list))

# ========== ОСНОВНАЯ ФУНКЦИЯ ==========

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    
    # Обработчик регистрации
    reg_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('register', register_start)],
        states={
            REGISTER_STATES['NAME']: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_name)],
            REGISTER_STATES['FAMILY_NAME']: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_family_name)],
            REGISTER_STATES['WAIT_APPROVAL']: [
                CallbackQueryHandler(
                    approve_registration, 
                    pattern=f"^({APPROVE_PREFIX}|{REJECT_PREFIX})"
                )
            ]
        },
        fallbacks=[CommandHandler('cancel', register_user_cancel)],
        per_message=False,
        per_chat=True,
        per_user=True
    )
    
    # Обработчик назначения домашнего задания
    assign_hw_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('assign_homework', assign_homework)],
        states={
            ASSIGN_HW_STATES['SELECT_STUDENT']: [
                CallbackQueryHandler(
                    select_student_for_homework,
                    pattern=f"^{ASSIGN_HW_PREFIX}\\d+$"
                )
            ],
            ASSIGN_HW_STATES['RECEIVE_FILE']: [
                MessageHandler(
                    filters.Document.ALL | filters.PHOTO | filters.TEXT & ~filters.COMMAND,
                    receive_homework_file
                )
            ],
            ASSIGN_HW_STATES['RECEIVE_DEADLINE']: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    receive_homework_deadline
                )
            ]
        },
        fallbacks=[CommandHandler('cancel', register_user_cancel)],
        per_message=False,
        per_chat=True,
        per_user=True
    )
    
    # Обработчик сдачи задания
    send_task_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('send_task', send_task_start)],
        states={
            SEND_TASK_STATES['SELECT_DEADLINE']: [
                CallbackQueryHandler(
                    select_deadline,
                    pattern=r'^deadline_\d+$'
                )
            ],
            SEND_TASK_STATES['RECEIVE_FILES']: [
                MessageHandler(
                    filters.Document.ALL | filters.PHOTO,
                    receive_files
                ),
                CommandHandler('done_files', done_files)
            ],
            SEND_TASK_STATES['RECEIVE_COMMENT']: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    receive_comment
                ),
                CommandHandler('skip_comment', skip_comment)
            ]
        },
        fallbacks=[CommandHandler('cancel', register_user_cancel)],
        per_message=False,
        per_chat=True,
        per_user=True
    )
    
    # Обработчик проверки заданий
    review_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('review_tasks', review_tasks)],
        states={
            REVIEW_STATES['SELECT_SUBMISSION']: [
                CallbackQueryHandler(
                    select_submission_for_review,
                    pattern=f"^{REVIEW_PREFIX}\\d+$"
                )
            ],
            REVIEW_STATES['RECEIVE_REVIEW']: [
                MessageHandler(
                    filters.TEXT | filters.Document.ALL | filters.PHOTO,
                    receive_review
                )
            ]
        },
        fallbacks=[CommandHandler('cancel', register_user_cancel)],
        per_message=False,
        per_chat=True,
        per_user=True
    )
    
    # Регистрация обработчиков команд
    app.add_handler(CommandHandler('help', help_command))
    app.add_handler(CommandHandler('show_deadlines', show_deadlines))
    app.add_handler(CommandHandler('show_users', show_users))
    app.add_handler(CommandHandler('delete_user', delete_user))
    app.add_handler(CommandHandler('show_my_students', show_my_students))
    
    # Регистрация обработчиков callback-запросов
    app.add_handler(CallbackQueryHandler(assign_role, pattern=f"^{ROLE_PREFIX}"))
    app.add_handler(CallbackQueryHandler(assign_mentor, pattern=f"^{MENTOR_PREFIX}"))
    app.add_handler(CallbackQueryHandler(delete_user_confirmation, pattern=f"^{DELETE_PREFIX}"))
    
    # Регистрация ConversationHandler
    app.add_handler(reg_conv_handler)
    app.add_handler(assign_hw_conv_handler)
    app.add_handler(send_task_conv_handler)
    app.add_handler(review_conv_handler)
    
    # Запуск бота
    app.run_polling()

if __name__ == '__main__':
    main()