import sqlite3

# The database is actually at instance/visionx_v4.db
conn = sqlite3.connect('instance/visionx_v4.db')
cursor = conn.cursor()
try:
    cursor.execute("ALTER TABLE exam_result ADD COLUMN is_submitted BOOLEAN DEFAULT 0")
    conn.commit()
    print("Added is_submitted to ExamResult.")
except sqlite3.OperationalError as e:
    print("Migration skipped or already applied:", e)
conn.close()
