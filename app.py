from flask import Flask, render_template, request
import psycopg2
import math
import os                    # <--- เพิ่มตัวนี้ (เพื่ออ่านค่าจากเครื่อง)
from dotenv import load_dotenv # <--- เพิ่มตัวนี้ (เพื่ออ่านไฟล์ .env)

# โหลดค่าจากไฟล์ .env เข้ามาในระบบ
load_dotenv()

app = Flask(__name__)

# --- ดึงค่าจาก .env มาใช้แทนการพิมพ์รหัสทิ้งไว้ ---
DB_CONFIG = {
    'dbname': os.getenv('DB_NAME'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'host': os.getenv('DB_HOST'),
    'port': os.getenv('DB_PORT')
}

@app.route('/')
def index():
    page = request.args.get('page', 1, type=int)
    search_query = request.args.get('search', '')
    
    per_page = 50
    offset = (page - 1) * per_page
    
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        
        where_clause = ""
        params = []
        
        if search_query:
            # รายชื่อคอลัมน์ที่อยากให้ค้นหาได้
            searchable_columns = [
                'title', 'author_name', 'category', 'paper_type', 
                'language', 'publisher', 'genre', 'illustrator_name', 
                'printing_method', 'translator_name', 'isbn', 'awards'
            ]
            
            conditions = [f"{col} ILIKE %s" for col in searchable_columns]
            where_clause = "WHERE " + " OR ".join(conditions)
            
            term = f"%{search_query}%"
            params = [term] * len(searchable_columns)
            
            print(f"กำลังค้นหา '{search_query}'")
        
        # 1. นับจำนวน
        count_sql = f'SELECT COUNT(*) FROM "Book_data"."Book" {where_clause}'
        cur.execute(count_sql, params)
        total_records = cur.fetchone()[0]
        total_pages = math.ceil(total_records / per_page)
        
        # 2. ดึงข้อมูล
        data_sql = f'SELECT * FROM "Book_data"."Book" {where_clause} ORDER BY title ASC LIMIT %s OFFSET %s'
        cur.execute(data_sql, params + [per_page, offset])
        
        columns = [desc[0] for desc in cur.description]
        rows = cur.fetchall()
        
        cur.close()
        
        return render_template('index.html', 
                               columns=columns, 
                               rows=rows, 
                               page=page, 
                               total_pages=total_pages,
                               search_query=search_query)
        
    except Exception as e:
        print(f"Error: {e}")
        return f"<h1 style='color:red'>เกิดข้อผิดพลาด: {e}</h1>"
    finally:
        if conn:
            conn.close()

if __name__ == '__main__':
    app.run(debug=True)