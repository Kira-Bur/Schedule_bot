import sqlite3
import hashlib
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self, db_name='bot_users.db'):
        self.db_name = db_name
        self.init_db()
    
    def init_db(self):
        """Инициализация базы данных"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                chat_id INTEGER PRIMARY KEY,
                is_group BOOLEAN DEFAULT FALSE,
                building INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS schedule_files (
                filename TEXT PRIMARY KEY,
                file_hash TEXT,
                building INTEGER,
                last_modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()
    
    def add_user(self, chat_id, is_group=False, building=1):
        """Добавление пользователя"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        try:
            cursor.execute('INSERT OR REPLACE INTO users (chat_id, is_group, building) VALUES (?, ?, ?)', 
                          (chat_id, is_group, building))
            conn.commit()
        except Exception as e:
            logger.error(f"Ошибка добавления пользователя: {e}")
        finally:
            conn.close()
    
    def get_user_building(self, chat_id):
        """Получение корпуса пользователя"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT building FROM users WHERE chat_id = ?', (chat_id,))
            result = cursor.fetchone()
            return result[0] if result else 1  # По умолчанию корпус 1
        except Exception as e:
            logger.error(f"Ошибка получения корпуса пользователя: {e}")
            return 1
        finally:
            conn.close()
    
    def set_user_building(self, chat_id, building):
        """Установка корпуса пользователя"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        try:
            cursor.execute('UPDATE users SET building = ? WHERE chat_id = ?', (building, chat_id))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Ошибка установки корпуса пользователя: {e}")
            return False
        finally:
            conn.close()
    
    def get_all_users(self):
        """Получение всех пользователей"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT chat_id, is_group, building FROM users')
        users = {row[0]: {'is_group': row[1], 'building': row[2]} for row in cursor.fetchall()}
        conn.close()
        return users
    
    def get_users_by_building(self, building):
        """Получение пользователей по корпусу"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT chat_id, is_group FROM users WHERE building = ?', (building,))
        users = {row[0]: row[1] for row in cursor.fetchall()}
        conn.close()
        return users
    
    def get_file_hash(self, file_path):
        """Вычисление хэша файла"""
        try:
            hasher = hashlib.md5()
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b''):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except Exception as e:
            logger.error(f"Ошибка вычисления хэша файла {file_path}: {e}")
            return None
    
    def save_file_info(self, filename, file_hash, building):
        """Сохранение информации о файле"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO schedule_files (filename, file_hash, building, last_modified)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ''', (filename, file_hash, building))
            conn.commit()
        except Exception as e:
            logger.error(f"Ошибка сохранения информации о файле: {e}")
        finally:
            conn.close()
    
    def get_known_files(self, building=None):
        """Получение известных файлов"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        if building is not None:
            cursor.execute('SELECT filename, file_hash FROM schedule_files WHERE building = ?', (building,))
            files = {row[0]: row[1] for row in cursor.fetchall()}
        else:
            cursor.execute('SELECT filename, file_hash, building FROM schedule_files')
            files = {}
            for row in cursor.fetchall():
                files[row[0]] = {'hash': row[1], 'building': row[2]}
        
        conn.close()
        return files
    
    def cleanup_old_files(self, current_filenames, building):
        """Очистка устаревших файлов"""
        if not current_filenames:
            logger.warning("Нет текущих файлов для очистки устаревших записей")
            return
        
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        try:
            placeholders = ','.join(['?'] * len(current_filenames))
            cursor.execute(f'DELETE FROM schedule_files WHERE building = ? AND filename NOT IN ({placeholders})', 
                          [building] + current_filenames)
            deleted_count = cursor.rowcount
            conn.commit()
            logger.info(f"Очищено {deleted_count} устаревших записей о файлах для корпуса {building}")
        except Exception as e:
            logger.error(f"Ошибка очистки устаревших файлов: {e}")
        finally:
            conn.close()

