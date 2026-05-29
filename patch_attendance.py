import sqlite3

def patch():
    try:
        conn = sqlite3.connect('instance/visionx_v4.db')
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS attendance_record (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                teacher_id INTEGER NOT NULL,
                class_id INTEGER NOT NULL,
                subject_id INTEGER NOT NULL,
                date DATE NOT NULL,
                status VARCHAR(20) NOT NULL,
                FOREIGN KEY(student_id) REFERENCES user(id),
                FOREIGN KEY(teacher_id) REFERENCES user(id),
                FOREIGN KEY(class_id) REFERENCES class(id),
                FOREIGN KEY(subject_id) REFERENCES subject(id)
            )
        ''')
        conn.commit()
        conn.close()
        print("AttendanceRecord table created successfully!")
    except Exception as e:
        print("Error:", e)

if __name__ == '__main__':
    patch()
