from src.db_manager import DBManager
import sqlite3
import datetime

# 1. Initialize DB (should trigger migration)
print("Initializing DB...")
db = DBManager()

# 2. Check Schema
print("Checking Schema...")
with sqlite3.connect(db.db_file) as conn:
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(ai_advice)")
    columns = [info[1] for info in cursor.fetchall()]
    if 'specific_model' in columns:
        print("✅ SUCCESS: 'specific_model' column found in ai_advice table.")
    else:
        print("❌ FAILURE: 'specific_model' column MISSING.")

# 3. Test Save and Retrieve
print("Testing Save and Retrieve...")
today = datetime.datetime.now().strftime("%Y-%m-%d")
test_code = "TEST001"
test_model = "TestAI"
test_specific_model = "test-ai-v1.0-turbo"

db.save_ai_advice(today, test_code, test_model, "YES", "Good stock", specific_model=test_specific_model)

# Retrieve
saved_data = db.get_ai_advice(today, test_code)
found = False
for record in saved_data:
    if record['model'] == test_model and record['specific_model'] == test_specific_model:
        print(f"✅ SUCCESS: Record found with specific_model='{record['specific_model']}'")
        found = True
        break

if not found:
    print("❌ FAILURE: Record with specific_model not found.")
