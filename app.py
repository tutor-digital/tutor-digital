import json
import os
import time  # Ditambahkan untuk timestamp nama file
from datetime import datetime, timezone
from flask import Flask, render_template, redirect, url_for, request, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy import func
import psycopg2

# --- KONFIGURASI APP ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'kunci-rahasia-anda-ganti-di-production'

# Konfigurasi PostgreSQL (Neon)
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://neondb_owner:npg_4TZjkSRaEM2s@ep-flat-king-a14iy9pd-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Konfigurasi Upload
# Catatan untuk Vercel: File yang diupload ke folder static di Vercel akan hilang saat redeploy. 
# Untuk production Vercel serius, gunakan AWS S3 atau Cloudinary.
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# 1. Inisialisasi Database
db = SQLAlchemy(app)

# 2. Inisialisasi Login Manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Silakan login untuk mengakses halaman ini.'
login_manager.login_message_category = 'error'

# --- MODELS DATABASE ---

class User(UserMixin, db.Model):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    school = db.Column(db.String(100), default='Umum')
    phone = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    phone = db.Column(db.String(20))
    
    enrollments = db.relationship('Enrollment', backref='user', lazy=True)
    orders = db.relationship('Order', backref='user', lazy=True)
    lesson_progress = db.relationship('LessonProgress', backref='user', lazy=True)
    profile_image = db.Column(db.String(500), nullable=True)

class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(50))
    image = db.Column(db.String(500)) # Menyimpan nama file gambar
    duration = db.Column(db.String(50))
    students = db.Column(db.Integer, default=0)
    rating = db.Column(db.Float, default=0.0)
    level = db.Column(db.String(50))
    description = db.Column(db.Text)
    price = db.Column(db.Integer)
    discount = db.Column(db.Integer, default=0)
    instructor = db.Column(db.String(100))
    
    lessons = db.relationship('Lesson', backref='course', cascade="all, delete-orphan", lazy=True)

class Lesson(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    duration = db.Column(db.String(50))
    type = db.Column(db.String(20), default='video') # video, text, quiz, video_text
    is_preview = db.Column(db.Boolean, default=False)
    content = db.Column(db.Text, nullable=True) # JSON String atau URL

class Enrollment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    enrolled_at = db.Column(db.DateTime, default=datetime.utcnow)

class LessonProgress(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    lesson_id = db.Column(db.Integer, db.ForeignKey('lesson.id'), nullable=False)
    completed_at = db.Column(db.DateTime, default=datetime.utcnow)

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    total = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default='pending')
    payment_method = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    items = db.relationship('OrderItem', backref='order', lazy=True)

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    price_at_purchase = db.Column(db.Integer)
    course_title = db.Column(db.String(200))

# --- LOGIN LOADER ---
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- ROUTES: AUTH ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('home'))
    if request.method == 'POST':
        user = User.query.filter_by(email=request.form.get('email')).first()
        if user and check_password_hash(user.password, request.form.get('password')):
            login_user(user, remember=True if request.form.get('remember') else False)
            flash('Login berhasil!', 'success')
            return redirect(request.args.get('next') or url_for('home'))
        flash('Email atau password salah.', 'error')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated: return redirect(url_for('home'))
    if request.method == 'POST':
        if request.form.get('password') != request.form.get('confirmPassword'):
            flash('Password tidak cocok.', 'error')
        elif User.query.filter_by(email=request.form.get('email')).first():
            flash('Email sudah terdaftar.', 'error')
        else:
            new_user = User(
                username=request.form.get('name'),
                email=request.form.get('email'),
                phone=request.form.get('phone'),
                school=request.form.get('school'),
                password=generate_password_hash(request.form.get('password'))
            )
            db.session.add(new_user)
            db.session.commit()
            login_user(new_user)
            flash('Registrasi berhasil!', 'success')
            return redirect(url_for('home'))
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Anda telah keluar.', 'success')
    return redirect(url_for('home'))

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'update_profile':
            current_user.username = request.form.get('name')
            current_user.email = request.form.get('email')
            current_user.school = request.form.get('school')
            current_user.phone = request.form.get('phone')
            
            # --- LOGIKA BARU: UPLOAD FOTO PROFIL ---
            if 'profile_image' in request.files:
                file = request.files['profile_image']
                if file and file.filename != '':
                    filename = secure_filename(file.filename)
                    # Beri nama unik: id_user_waktu.jpg
                    import time
                    unique_filename = f"user_{current_user.id}_{int(time.time())}_{filename}"
                    
                    # Simpan file
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_filename))
                    
                    # Simpan nama file ke database
                    current_user.profile_image = unique_filename
            # ---------------------------------------

            try:
                db.session.commit()
                flash('Profil berhasil diperbarui.', 'success')
            except:
                db.session.rollback()
                flash('Terjadi kesalahan atau email sudah digunakan.', 'error')

        # ... (kode bagian change_password tetap sama) ...
        
        return redirect(url_for('profile'))
    return render_template('profile.html')

# --- ROUTES: PUBLIC ---
@app.route('/')
def home():
    cat = request.args.get('category', 'all')
    courses = Course.query.all() if cat == 'all' else Course.query.filter_by(category=cat).all()
    return render_template('index.html', courses=courses)

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        # Logika sederhana hanya untuk demo (karena belum ada server email)
        name = request.form.get('name')
        email = request.form.get('email')
        message = request.form.get('message')
        
        # Di sini Anda bisa menambahkan logika kirim email atau simpan ke DB
        flash(f'Terima kasih {name}, pesan Anda telah kami terima!', 'success')
        return redirect(url_for('contact'))
        
    return render_template('contact.html')

@app.route('/terms')
def terms():
    return render_template('terms.html')

@app.route('/privacy')
def privacy():
    return render_template('privacy.html')

@app.route('/course/<int:course_id>')
def course_detail(course_id):
    course = Course.query.get_or_404(course_id)
    is_enrolled = False
    if current_user.is_authenticated:
        is_enrolled = Enrollment.query.filter_by(user_id=current_user.id, course_id=course.id).first() is not None
    return render_template('course_detail.html', course=course, is_enrolled=is_enrolled)

# --- ROUTES: CART & ORDER ---
@app.route('/add_to_cart/<int:course_id>')
def add_to_cart(course_id):
    if 'cart' not in session: session['cart'] = []
    cart = session['cart']
    if course_id not in cart:
        cart.append(course_id)
        session['cart'] = cart
        flash('Kursus ditambahkan ke keranjang!', 'success')
    else:
        flash('Kursus sudah ada di keranjang.', 'info')
    return redirect(url_for('cart'))

@app.route('/cart')
def cart():
    cart_ids = session.get('cart', [])
    courses = Course.query.filter(Course.id.in_(cart_ids)).all() if cart_ids else []
    subtotal = sum([c.price for c in courses])
    total = sum([c.price * (1 - c.discount/100) for c in courses])
    return render_template('cart.html', courses=courses, subtotal=subtotal, total=total, savings=subtotal-total)

@app.route('/cart/remove/<int:course_id>')
def remove_from_cart(course_id):
    cart = session.get('cart', [])
    if course_id in cart:
        cart.remove(course_id)
        session['cart'] = cart
        flash('Item dihapus.', 'success')
    return redirect(url_for('cart'))

@app.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    cart_ids = session.get('cart', [])
    if not cart_ids: return redirect(url_for('home'))
    courses = Course.query.filter(Course.id.in_(cart_ids)).all()
    total = sum([c.price * (1 - c.discount/100) for c in courses])
    
    if request.method == 'POST':
        order = Order(user_id=current_user.id, total=total, status='pending', payment_method=request.form.get('payment'))
        db.session.add(order)
        db.session.flush()
        for c in courses:
            db.session.add(OrderItem(order_id=order.id, course_id=c.id, price_at_purchase=c.price * (1 - c.discount/100), course_title=c.title))
        session.pop('cart', None)
        db.session.commit()
        flash('Order berhasil dibuat. Tunggu konfirmasi admin.', 'success')
        return redirect(url_for('my_courses'))
    return render_template('checkout.html', courses=courses, total=total)

# --- ROUTES: STUDENT ---
@app.route('/my-courses')
@login_required
def my_courses():
    enrollments = Enrollment.query.filter_by(user_id=current_user.id).all()
    course_ids = [e.course_id for e in enrollments]
    courses = Course.query.filter(Course.id.in_(course_ids)).all()
    courses_data = []
    
    for c in courses:
        total = len(c.lessons)
        completed = LessonProgress.query.filter_by(user_id=current_user.id, course_id=c.id).count()
        progress = int((completed/total*100)) if total > 0 else 0
        courses_data.append({'course': c, 'progress': progress, 'is_completed': progress==100})
        
    stats = {'total': len(courses), 'completed': sum(1 for x in courses_data if x['is_completed']), 'in_progress': sum(1 for x in courses_data if not x['is_completed'])}
    return render_template('my_courses.html', courses_data=courses_data, stats=stats)

@app.route('/learning/<int:course_id>')
@login_required
def learning(course_id):
    if not Enrollment.query.filter_by(user_id=current_user.id, course_id=course_id).first():
        flash('Anda belum terdaftar.', 'error')
        return redirect(url_for('course_detail', course_id=course_id))
    
    course = Course.query.get_or_404(course_id)
    completed = [p.lesson_id for p in LessonProgress.query.filter_by(user_id=current_user.id, course_id=course_id).all()]
    progress = int((len(completed)/len(course.lessons)*100)) if course.lessons else 0
    
    # Logic untuk parsing content JSON jika perlu (opsional di sini, biasanya di template handle via JS)
    return render_template('learning.html', course=course, completed_lesson_ids=completed, progress_percent=progress)

@app.route('/api/mark-complete', methods=['POST'])
@login_required
def mark_complete():
    data = request.get_json()
    if not LessonProgress.query.filter_by(user_id=current_user.id, course_id=data['course_id'], lesson_id=data['lesson_id']).first():
        db.session.add(LessonProgress(user_id=current_user.id, course_id=data['course_id'], lesson_id=data['lesson_id']))
        db.session.commit()
    total = Lesson.query.filter_by(course_id=data['course_id']).count()
    completed = LessonProgress.query.filter_by(user_id=current_user.id, course_id=data['course_id']).count()
    return jsonify({'status': 'success', 'progress': int((completed/total*100)), 'is_completed': completed==total})

@app.route('/certificate/<int:course_id>')
@login_required
def view_certificate(course_id):
    if not Enrollment.query.filter_by(user_id=current_user.id, course_id=course_id).first(): return redirect(url_for('home'))
    course = Course.query.get_or_404(course_id)
    now = datetime.now()
    months = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
    return render_template('certificate.html', course=course, cert_number=f"TD-{course.id:03}-{current_user.id:06}", completion_date=f"{now.day} {months[now.month-1]} {now.year}")

# --- ROUTES: ADMIN ---
@app.route('/admin')
@login_required
def admin_panel():
    if not current_user.is_admin: return redirect(url_for('home'))
    filter_cat = request.args.get('filter', 'all')
    courses = Course.query.all() if filter_cat == 'all' else Course.query.filter_by(category=filter_cat).all()
    stats = {
        'total_courses': Course.query.count(),
        'total_orders': Order.query.count(),
        'pending_orders': Order.query.filter_by(status='pending').count(),
        'total_users': User.query.count()
    }
    return render_template('admin_panel.html', active_tab=request.args.get('tab', 'courses'), filter_category=filter_cat, courses=courses, orders=Order.query.order_by(Order.created_at.desc()).all(), users=User.query.all(), stats=stats)

# --- 2 UTAMA: LOGIC SAVE COURSE & UPLOAD GAMBAR ---
@app.route('/admin/add-course', methods=['GET', 'POST'])
@app.route('/admin/edit-course/<int:course_id>', methods=['GET', 'POST'])
@login_required
def save_course(course_id=None):
    if not current_user.is_admin: return redirect(url_for('home'))

    course = Course.query.get_or_404(course_id) if course_id else None

    if request.method == 'POST':
        # 1. Ambil Data Teks
        title = request.form.get('title')
        category = request.form.get('category')
        duration = request.form.get('duration')
        level = request.form.get('level')
        description = request.form.get('description')
        price = int(request.form.get('price', 0))
        discount = int(request.form.get('discount', 0))
        instructor = request.form.get('instructor')
        
        # 2. LOGIKA UPLOAD GAMBAR (Baru)
        image_filename = course.image if course else 'https://via.placeholder.com/600x400?text=No+Image' # Default
        
        # Cek apakah ada file yang diupload
        if 'image_file' in request.files:
            file = request.files['image_file']
            if file and file.filename != '':
                filename = secure_filename(file.filename)
                # Tambahkan timestamp agar nama unik
                unique_filename = f"{int(time.time())}_{filename}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_filename))
                image_filename = unique_filename
        
        # Jika user memasukkan URL manual (opsional fallback)
        elif request.form.get('image'): 
            image_filename = request.form.get('image')

        # 3. Simpan / Update Course
        if not course:
            course = Course(title=title, category=category, image=image_filename, duration=duration, level=level, description=description, price=price, discount=discount, instructor=instructor)
            db.session.add(course)
            db.session.flush() # Flush untuk mendapatkan ID course
        else:
            course.title = title
            course.category = category
            course.image = image_filename # Update gambar
            course.duration = duration
            course.level = level
            course.description = description
            course.price = price
            course.discount = discount
            course.instructor = instructor
            
            # Hapus lesson lama untuk diganti yang baru (cara paling sederhana)
            Lesson.query.filter_by(course_id=course.id).delete()

        # 4. Simpan Lessons
        lessons_data = json.loads(request.form.get('lessons_json', '[]'))
        for l in lessons_data:
            content_data = l.get('content', '')
            # Pastikan Dict/List diubah jadi JSON String sebelum masuk DB
            if isinstance(content_data, (dict, list)):
                content_data = json.dumps(content_data)
                
            new_lesson = Lesson(
                course_id=course.id, 
                title=l['title'], 
                duration=l['duration'], 
                type=l['type'], 
                is_preview=l['isPreview'],
                content=content_data
            )
            db.session.add(new_lesson)

        db.session.commit()
        flash('Kursus berhasil disimpan.', 'success')
        return redirect(url_for('admin_panel'))

    # --- Persiapan Data untuk GET (Edit Mode) ---
    existing_lessons = []
    if course:
        for l in course.lessons:
            # Load kembali konten JSON jika tipe quiz atau video_text
            content_val = l.content
            if l.type in ['quiz', 'video_text'] and l.content:
                try:
                    content_val = json.loads(l.content)
                except:
                    content_val = l.content # Fallback jika gagal parse
            
            existing_lessons.append({
                'id': l.id, 
                'title': l.title, 
                'duration': l.duration, 
                'type': l.type, 
                'isPreview': l.is_preview,
                'content': content_val
            })

    return render_template('add_course.html', course=course, lessons_json=json.dumps(existing_lessons))

@app.route('/admin/delete-course/<int:course_id>', methods=['POST'])
@login_required
def delete_course(course_id):
    if not current_user.is_admin: return redirect(url_for('home'))
    course = Course.query.get_or_404(course_id)
    db.session.delete(course)
    db.session.commit()
    flash('Kursus dihapus.', 'success')
    return redirect(url_for('admin_panel'))

@app.route('/admin/order/<int:order_id>/<action>', methods=['POST'])
@login_required
def update_order_status(order_id, action):
    if not current_user.is_admin: return redirect(url_for('home'))
    order = Order.query.get_or_404(order_id)
    if action == 'confirm':
        order.status = 'confirmed'
        for item in order.items:
            if not Enrollment.query.filter_by(user_id=order.user_id, course_id=item.course_id).first():
                db.session.add(Enrollment(user_id=order.user_id, course_id=item.course_id))
        flash('Order dikonfirmasi.', 'success')
    elif action == 'cancel':
        order.status = 'cancelled'
        flash('Order dibatalkan.', 'success')
    db.session.commit()
    return redirect(url_for('admin_panel', tab='payments' if action == 'confirm' else 'orders'))

def seed_data():
    if not User.query.filter_by(email='admin@tutordigital.com').first():
        db.session.add(User(username='Admin Tutor', email='admin@tutordigital.com', password=generate_password_hash('admin123'), is_admin=True))
        db.session.commit()

# --- MAIN BLOCK (SAFE VERSION) ---
if __name__ == '__main__':
    with app.app_context():
        # Buat tabel jika belum ada (TIDAK MENGHAPUS DATA LAMA)
        db.create_all()
        # Seed admin jika belum ada
        seed_data()
        print("Aplikasi siap dijalankan.")
        
    app.run(debug=True)