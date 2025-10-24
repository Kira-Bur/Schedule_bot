import sqlite3
import logging

logger = logging.getLogger(__name__)

class AdminManager:
    def __init__(self, db_path='admins.db'):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        """Инициализация базы данных админов"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                CREATE TABLE IF NOT EXISTS admins (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    status TEXT DEFAULT 'pending', -- pending, approved, rejected
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    approved_at TIMESTAMP NULL
                )
                ''')
                
                cursor.execute('''
                CREATE TABLE IF NOT EXISTS admin_actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    admin_id INTEGER,
                    action_type TEXT,
                    action_data TEXT,
                    status TEXT DEFAULT 'pending', -- pending, approved, rejected
                    target_user_id INTEGER NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    approved_by INTEGER NULL,
                    FOREIGN KEY (admin_id) REFERENCES admins (user_id)
                )
                ''')
                
                cursor.execute('''
                INSERT OR IGNORE INTO admins (user_id, username, first_name, last_name, status, approved_at)
                VALUES (1347692271, NULL, NULL, NULL, 'approved', CURRENT_TIMESTAMP)
                ''')
                
                conn.commit()
                logger.info("База данных админов инициализирована")
                
        except Exception as e:
            logger.error(f"Ошибка инициализации базы админов: {e}")
    
    def is_admin(self, user_id):
        """Проверяет, является ли пользователь одобренным админом"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT COUNT(*) FROM admins WHERE user_id = ? AND status = 'approved'",
                    (user_id,)
                )
                return cursor.fetchone()[0] > 0
        except Exception as e:
            logger.error(f"Ошибка проверки админа: {e}")
            return False
    
    def is_pending_admin(self, user_id):
        """Проверяет, ожидает ли пользователь одобрения"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT COUNT(*) FROM admins WHERE user_id = ? AND status = 'pending'",
                    (user_id,)
                )
                return cursor.fetchone()[0] > 0
        except Exception as e:
            logger.error(f"Ошибка проверки ожидающего админа: {e}")
            return False
    
    def add_admin_request(self, user_id, username, first_name, last_name):
        """Добавляет запрос на админство"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                INSERT OR REPLACE INTO admins (user_id, username, first_name, last_name, status)
                VALUES (?, ?, ?, ?, 'pending')
                ''', (user_id, username, first_name, last_name))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Ошибка добавления запроса админа: {e}")
            return False
    
    def get_pending_requests(self):
        """Получает все ожидающие запросы"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                SELECT user_id, username, first_name, last_name, created_at 
                FROM admins WHERE status = 'pending' ORDER BY created_at
                ''')
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Ошибка получения ожидающих запросов: {e}")
            return []
    
    def approve_admin(self, user_id, approved_by):
        """Одобряет админа"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                UPDATE admins SET status = 'approved', approved_at = CURRENT_TIMESTAMP 
                WHERE user_id = ?
                ''', (user_id,))
                
                cursor.execute('SELECT first_name FROM admins WHERE user_id = ?', (user_id,))
                result = cursor.fetchone()
                first_name = result[0] if result else "Пользователь"
                
                conn.commit()
                return first_name
        except Exception as e:
            logger.error(f"Ошибка одобрения админа: {e}")
            return None
    
    def reject_admin(self, user_id):
        """Отклоняет админа"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM admins WHERE user_id = ? AND status = 'pending'", (user_id,))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Ошибка отклонения админа: {e}")
            return False
    
    def get_all_admins(self):
        """Получает всех одобренных админов"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                SELECT user_id, username, first_name, last_name, approved_at 
                FROM admins WHERE status = 'approved' ORDER BY approved_at
                ''')
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Ошибка получения списка админов: {e}")
            return []
    
    def add_admin_action(self, admin_id, action_type, action_data, target_user_id=None):
        """Добавляет действие админа для подтверждения"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                INSERT INTO admin_actions (admin_id, action_type, action_data, target_user_id, status)
                VALUES (?, ?, ?, ?, 'pending')
                ''', (admin_id, action_type, action_data, target_user_id))
                conn.commit()
                return cursor.lastrowid
        except Exception as e:
            logger.error(f"Ошибка добавления действия админа: {e}")
            return None
    
    def get_pending_actions(self):
        """Получает все ожидающие действия"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                SELECT a.id, a.admin_id, ad.username, ad.first_name, a.action_type, 
                       a.action_data, a.target_user_id, a.created_at
                FROM admin_actions a
                LEFT JOIN admins ad ON a.admin_id = ad.user_id
                WHERE a.status = 'pending' ORDER BY a.created_at
                ''')
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Ошибка получения ожидающих действий: {e}")
            return []
    
    def approve_action(self, action_id, approved_by):
        """Одобряет действие админа"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                UPDATE admin_actions SET status = 'approved', approved_by = ?
                WHERE id = ?
                ''', (approved_by, action_id))
                conn.commit()
                
                cursor.execute('''
                SELECT action_type, action_data, admin_id FROM admin_actions WHERE id = ?
                ''', (action_id,))
                return cursor.fetchone()
        except Exception as e:
            logger.error(f"Ошибка одобрения действия: {e}")
            return None
    
    def reject_action(self, action_id):
        """Отклоняет действие админа"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM admin_actions WHERE id = ?", (action_id,))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Ошибка отклонения действия: {e}")
            return False

