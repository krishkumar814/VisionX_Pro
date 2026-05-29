import sqlite3

def patch():
    try:
        conn = sqlite3.connect('instance/visionx_v4.db')
        c = conn.cursor()
        
        # Add remarks to test_session
        try:
            c.execute('ALTER TABLE test_session ADD COLUMN remarks TEXT')
            print("Added remarks to test_session table.")
        except Exception as e:
            print("Warning on altering test_session:", e)
            
        conn.commit()
        conn.close()
        print("Database patched successfully!")
    except Exception as e:
        print("Error:", e)

if __name__ == '__main__':
    patch()
