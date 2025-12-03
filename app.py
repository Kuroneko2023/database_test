from flask import Flask, render_template, request, redirect, url_for, flash, session
import psycopg2
import math
import os
from dotenv import load_dotenv
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

load_dotenv()

app = Flask(__name__)
app.secret_key = 'super_secret_key'

UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

DB_CONFIG = {
    'dbname': os.getenv('DB_NAME'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'host': os.getenv('DB_HOST'),
    'port': os.getenv('DB_PORT')
}

def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)

@app.template_filter('split_tags')
def split_tags_filter(s):
    if not s: return []
    return [tag.strip() for tag in s.split(',')]

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_image(file):
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        return filename
    return None

def get_form_data():
    def clean(key):
        val = request.form.get(key, '').strip()
        return val if val else None
    
    file = request.files.get('image')
    image_filename = save_image(file)

    return [
        clean('title'), clean('author_name'), clean('category'), clean('paper_type'),
        clean('volume_size'), clean('publication_date'), clean('language'), clean('isbn'),
        clean('edition'), clean('publisher'), clean('price'), clean('number_of_pages'),
        clean('cover_type'), clean('rating'), clean('synopsis'), clean('characters'),
        clean('genre'), clean('target_audience'), clean('illustrator_name'),
        clean('printing_location'), clean('printing_company'), clean('printing_date'),
        clean('edition_notes'), clean('awards'), clean('sales_ranking'), clean('series_name'),
        image_filename
    ]

# --- Login / Register ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        identifier = request.form['identifier']
        password = request.form['password']

        if identifier == 'AdminBackend' and password == 'Adminback0073':
            session['user_id'] = 'admin'
            session['username'] = 'AdminBackend'
            session['is_admin'] = True
            flash('Welcome back, Admin!', 'success')
            return redirect(url_for('admin_dashboard'))

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('SELECT id, username, password_hash FROM "Book_data"."Users" WHERE username = %s OR email = %s', (identifier, identifier))
        user = cur.fetchone()
        cur.close()
        conn.close()

        if user:
            if check_password_hash(user[2], password):
                session['user_id'] = user[0]
                session['username'] = user[1]
                session['is_admin'] = False
                flash('Login successful!', 'success')
                return redirect(url_for('shop'))
            else:
                flash('รหัสผ่านไม่ถูกต้อง', 'danger')
        else:
            flash('ไม่พบชื่อผู้ใช้หรืออีเมลนี้', 'danger')

    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        hashed_pw = generate_password_hash(password)

        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute('INSERT INTO "Book_data"."Users" (username, email, password_hash) VALUES (%s, %s, %s)',
                        (username, email, hashed_pw))
            conn.commit()
            flash('สมัครสมาชิกสำเร็จ! กรุณาล็อกอิน', 'success')
            return redirect(url_for('login'))
        except psycopg2.IntegrityError:
            conn.rollback()
            flash('Username หรือ Email นี้ถูกใช้ไปแล้ว', 'danger')
        finally:
            cur.close()
            conn.close()

    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully.', 'info')
    return redirect(url_for('login'))

# --- Shop Route (เพิ่ม Genre Filter) ---
@app.route('/')
def shop():
    page = request.args.get('page', 1, type=int)
    search_query = request.args.get('search', '').strip()
    category_filter = request.args.get('category', '').strip()
    genre_filter = request.args.get('genre', '').strip() # รับค่า Genre
    
    per_page = 12
    offset = (page - 1) * per_page
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # 1. ดึงรายชื่อ Category (เหมือนเดิม)
    cur.execute('SELECT DISTINCT category FROM "Book_data"."Book" WHERE category IS NOT NULL ORDER BY category ASC')
    cat_raw = [row[0] for row in cur.fetchall()]
    categories = set()
    for c in cat_raw:
        for tag in c.split(','): categories.add(tag.strip())
    categories = sorted(list(categories))

    # 2. [เพิ่ม] ดึงรายชื่อ Genre (เหมือน Category)
    cur.execute('SELECT DISTINCT genre FROM "Book_data"."Book" WHERE genre IS NOT NULL ORDER BY genre ASC')
    gen_raw = [row[0] for row in cur.fetchall()]
    genres = set()
    for g in gen_raw:
        for tag in g.split(','): genres.add(tag.strip())
    genres = sorted(list(genres))

    # 3. เงื่อนไขการค้นหา
    conditions = []
    params = []
    
    if category_filter:
        conditions.append('category ILIKE %s')
        params.append(f'%{category_filter}%')
        
    if genre_filter: # เพิ่มเงื่อนไข Genre
        conditions.append('genre ILIKE %s')
        params.append(f'%{genre_filter}%')
        
    if search_query:
        searchable_columns = ['title', 'author_name', 'category', 'genre']
        search_group = " OR ".join([f"{col} ILIKE %s" for col in searchable_columns])
        conditions.append(f"({search_group})")
        term = f"%{search_query}%"
        params.extend([term] * len(searchable_columns))
    
    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
    
    # 4. นับจำนวน & ดึงข้อมูล
    count_sql = f'SELECT COUNT(*) FROM "Book_data"."Book" {where_clause}'
    cur.execute(count_sql, params)
    total_records = cur.fetchone()[0]
    total_pages = math.ceil(total_records / per_page)
    
    data_sql = f'''
        SELECT id, title, author_name, price, image_filename, rating, category 
        FROM "Book_data"."Book" {where_clause} 
        ORDER BY id DESC LIMIT %s OFFSET %s
    '''
    cur.execute(data_sql, params + [per_page, offset])
    
    books = []
    for row in cur.fetchall():
        books.append({
            'id': row[0], 'title': row[1], 'author_name': row[2], 
            'price': row[3], 'image_filename': row[4], 
            'rating': row[5], 'category': row[6]
        })
    
    cur.close()
    conn.close()
    
    return render_template('shop.html', 
                           books=books, 
                           page=page, 
                           total_pages=total_pages, 
                           search_query=search_query,
                           categories=categories,
                           current_category=category_filter,
                           genres=genres,              # ส่งรายการ Genre ไปหน้าเว็บ
                           current_genre=genre_filter) # ส่ง Genre ที่เลือกอยู่

# --- Admin & Detail (เหมือนเดิม) ---
@app.route('/admin')
def admin_dashboard():
    if not session.get('is_admin'):
        flash('Access Denied: Admin only.', 'danger')
        return redirect(url_for('login'))

    page = request.args.get('page', 1, type=int)
    search_query = request.args.get('search', '')
    per_page = 50
    offset = (page - 1) * per_page
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    where_clause = ""
    params = []
    
    if search_query:
        searchable_columns = ['title', 'author_name', 'category', 'publisher', 'isbn', 'series_name']
        conditions = [f"{col} ILIKE %s" for col in searchable_columns]
        where_clause = "WHERE " + " OR ".join(conditions)
        term = f"%{search_query}%"
        params = [term] * len(searchable_columns)
    
    count_sql = f'SELECT COUNT(*) FROM "Book_data"."Book" {where_clause}'
    cur.execute(count_sql, params)
    total_records = cur.fetchone()[0]
    total_pages = math.ceil(total_records / per_page)
    
    data_sql = f'''
        SELECT id, title, author_name, category, price, publisher, isbn 
        FROM "Book_data"."Book" {where_clause} 
        ORDER BY id DESC LIMIT %s OFFSET %s
    '''
    cur.execute(data_sql, params + [per_page, offset])
    rows = cur.fetchall()
    cur.close()
    conn.close()
    
    return render_template('index.html', rows=rows, page=page, total_pages=total_pages, search_query=search_query)

@app.route('/book/<int:id>')
def book_detail(id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT * FROM "Book_data"."Book" WHERE id = %s', (id,))
    row = cur.fetchone()
    if row is None: return "Book not found", 404
    columns = [desc[0] for desc in cur.description]
    book = dict(zip(columns, row))
    cur.close()
    conn.close()
    return render_template('detail.html', book=book)

# --- Add/Edit/Delete (เหมือนเดิม) ---
@app.route('/add', methods=('GET', 'POST'))
def add_book():
    if not session.get('is_admin'):
        return redirect(url_for('login'))

    if request.method == 'POST':
        conn = get_db_connection()
        cur = conn.cursor()
        sql = '''
            INSERT INTO "Book_data"."Book" (
                title, author_name, category, paper_type, volume_size, publication_date, 
                language, isbn, edition, publisher, price, number_of_pages, cover_type, 
                rating, synopsis, characters, genre, target_audience, illustrator_name, 
                printing_location, printing_company, printing_date, edition_notes, awards, 
                sales_ranking, series_name, image_filename
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        '''
        try:
            cur.execute(sql, tuple(get_form_data()))
            conn.commit()
            flash('เพิ่มข้อมูลสำเร็จ!', 'success')
            return redirect(url_for('admin_dashboard'))
        except Exception as e:
            conn.rollback()
            flash(f'เกิดข้อผิดพลาด: {e}', 'danger')
        finally:
            cur.close()
            conn.close()
    return render_template('form.html', action='Add', book={})

@app.route('/edit/<int:id>', methods=('GET', 'POST'))
def edit_book(id):
    if not session.get('is_admin'):
        return redirect(url_for('login'))

    conn = get_db_connection()
    cur = conn.cursor()
    if request.method == 'POST':
        form_data = get_form_data()
        new_image = form_data[-1]
        
        if new_image:
            sql = '''
                UPDATE "Book_data"."Book" SET 
                    title=%s, author_name=%s, category=%s, paper_type=%s, volume_size=%s, 
                    publication_date=%s, language=%s, isbn=%s, edition=%s, publisher=%s, 
                    price=%s, number_of_pages=%s, cover_type=%s, rating=%s, synopsis=%s, 
                    characters=%s, genre=%s, target_audience=%s, illustrator_name=%s, 
                    printing_location=%s, printing_company=%s, printing_date=%s, 
                    edition_notes=%s, awards=%s, sales_ranking=%s, series_name=%s,
                    image_filename=%s
                WHERE id=%s
            '''
            params = tuple(form_data) + (id,)
        else:
            sql = '''
                UPDATE "Book_data"."Book" SET 
                    title=%s, author_name=%s, category=%s, paper_type=%s, volume_size=%s, 
                    publication_date=%s, language=%s, isbn=%s, edition=%s, publisher=%s, 
                    price=%s, number_of_pages=%s, cover_type=%s, rating=%s, synopsis=%s, 
                    characters=%s, genre=%s, target_audience=%s, illustrator_name=%s, 
                    printing_location=%s, printing_company=%s, printing_date=%s, 
                    edition_notes=%s, awards=%s, sales_ranking=%s, series_name=%s
                WHERE id=%s
            '''
            params = tuple(form_data[:-1]) + (id,)

        try:
            cur.execute(sql, params)
            conn.commit()
            flash('แก้ไขข้อมูลเรียบร้อย!', 'success')
            return redirect(url_for('book_detail', id=id))
        except Exception as e:
            conn.rollback()
            flash(f'เกิดข้อผิดพลาด: {e}', 'danger')
        finally:
            cur.close()
            conn.close()

    cur.execute('SELECT * FROM "Book_data"."Book" WHERE id = %s', (id,))
    row = cur.fetchone()
    columns = [desc[0] for desc in cur.description]
    book = dict(zip(columns, row))
    cur.close()
    conn.close()
    return render_template('form.html', book=book, action='Edit')

@app.route('/delete/<int:id>', methods=('POST',))
def delete_book(id):
    if not session.get('is_admin'):
        return redirect(url_for('login'))

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('DELETE FROM "Book_data"."Book" WHERE id = %s', (id,))
    conn.commit()
    cur.close()
    conn.close()
    flash('ลบข้อมูลเรียบร้อย', 'danger')
    return redirect(url_for('admin_dashboard'))

if __name__ == '__main__':
    app.run(debug=True)