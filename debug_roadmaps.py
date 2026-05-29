import sqlite3
import json

conn = sqlite3.connect('instance/visionx_v4.db')
rows = conn.execute('SELECT id, tech_name, sections FROM roadmap').fetchall()
for r in rows:
    sections = json.loads(r[2])
    print(f"Roadmap ID: {r[0]}, Tech: {r[1]}")
    for i, s in enumerate(sections[:1]):
        print(f"  Section {i+1} keys: {list(s.keys())}")
        if 'topics' in s:
            print(f"  Topics: {s['topics']}")
        if 'gfg_link' in s:
            print(f"  gfg_link: {s['gfg_link']}")
