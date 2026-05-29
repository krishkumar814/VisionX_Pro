import sqlite3

def patch():
    try:
        conn = sqlite3.connect('instance/visionx_v4.db')
        c = conn.cursor()
        
        # 1. Add student_id to complaint
        try:
            c.execute('ALTER TABLE complaint ADD COLUMN student_id INTEGER')
            print("Added student_id to complaint table.")
        except Exception as e:
            print("Warning on altering complaint:", e)
            
        # 2. Create teacher_notification table
        try:
            c.execute('''
            CREATE TABLE IF NOT EXISTS teacher_notification (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_id INTEGER NOT NULL,
                message VARCHAR(255) NOT NULL,
                is_read BOOLEAN NOT NULL DEFAULT 0,
                created_at DATETIME
            )
            ''')
            print("Created teacher_notification table.")
        except Exception as e:
            print("Warning on creating teacher_notification:", e)
            
        conn.commit()
        conn.close()
        print("Database patched successfully!")
    except Exception as e:
        print("Error:", e)

if __name__ == '__main__':
    patch()
