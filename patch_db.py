import sqlite3

def patch():
    try:
        conn = sqlite3.connect('instance/visionx_v4.db')
        c = conn.cursor()
        c.execute('ALTER TABLE question_bank ADD COLUMN session_id INTEGER')
        conn.commit()
        conn.close()
        print("Database patched successfully!")
    except Exception as e:
        print("Error:", e)

if __name__ == '__main__':
    patch()
