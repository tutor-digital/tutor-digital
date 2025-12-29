import json
import os
from datetime import datetime, timezone
from flask import Flask, render_template, redirect, url_for, request, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import func
import psycopg2

# --- KONFIGURASI APP ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'kunci-rahasia-anda-ganti-di-production'

# Konfigurasi PostgreSQL Anda
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://neondb_owner:npg_4TZjkSRaEM2s@ep-flat-king-a14iy9pd-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 1. Inisialisasi Database
db = SQLAlchemy(app)

# 2. Inisialisasi Login Manager (INI YANG HILANG/ERROR)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Silakan login untuk mengakses halaman ini.'
login_manager.login_message_category = 'error'

# --- MODELS DATABASE ---

class User(UserMixin, db.Model):
    __tablename__ = 'user'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), nullable=False) # Nama Lengkap
    email = db.Column(db.String(120), unique=True, nullable=False) # Email untuk login
    password = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    school = db.Column(db.String(100), default='Umum')
    phone = db.Column(db.String(20))
    
    # Menggunakan timezone-aware datetime
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    # Relasi (String reference untuk menghindari error urutan)
    enrollments = db.relationship('Enrollment', backref='user', lazy=True)
    orders = db.relationship('Order', backref='user', lazy=True)
    lesson_progress = db.relationship('LessonProgress', backref='user', lazy=True)

    def __repr__(self):
        return f'<User {self.email}>'

class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(50))
    image = db.Column(db.String(500))
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
    type = db.Column(db.String(20), default='video') # video, text, quiz
    is_preview = db.Column(db.Boolean, default=False)
    
    # KOLOM BARU: Menyimpan URL Video, Teks Panjang, atau JSON String untuk Quiz
    content = db.Column(db.Text, nullable=True) 

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
    status = db.Column(db.String(20), default='pending') # pending, confirmed, cancelled
    payment_method = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    items = db.relationship('OrderItem', backref='order', lazy=True)

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    price_at_purchase = db.Column(db.Integer)
    course_title = db.Column(db.String(200))

# --- LOGIN MANAGER ---

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- ROUTES: AUTHENTICATION ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        remember = True if request.form.get('remember') else False
        
        user = User.query.filter_by(email=email).first()
        
        if user and check_password_hash(user.password, password):
            login_user(user, remember=remember)
            flash('Login berhasil! Selamat datang kembali.', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('home'))
        else:
            flash('Email atau password salah.', 'error')
            
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        school = request.form.get('school')
        password = request.form.get('password')
        confirm_password = request.form.get('confirmPassword')

        if password != confirm_password:
            flash('Password tidak cocok.', 'error')
            return render_template('register.html', form_data=request.form)
        
        if User.query.filter_by(email=email).first():
            flash('Email sudah terdaftar.', 'error')
            return render_template('register.html', form_data=request.form)

        new_user = User(
            username=name,
            email=email,
            phone=phone,
            school=school,
            password=generate_password_hash(password)
        )
        
        try:
            db.session.add(new_user)
            db.session.commit()
            login_user(new_user)
            flash('Registrasi berhasil!', 'success')
            return redirect(url_for('home'))
        except Exception:
            db.session.rollback()
            flash('Terjadi kesalahan sistem.', 'error')

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
            try:
                db.session.commit()
                flash('Profil diperbarui.', 'success')
            except:
                db.session.rollback()
                flash('Email mungkin sudah digunakan.', 'error')
                
        elif action == 'change_password':
            current_pass = request.form.get('currentPassword')
            new_pass = request.form.get('newPassword')
            confirm_pass = request.form.get('confirmPassword')
            
            if not check_password_hash(current_user.password, current_pass):
                flash('Password lama salah.', 'error')
            elif new_pass != confirm_pass:
                flash('Konfirmasi password tidak cocok.', 'error')
            elif len(new_pass) < 6:
                flash('Password minimal 6 karakter.', 'error')
            else:
                current_user.password = generate_password_hash(new_pass)
                db.session.commit()
                flash('Password berhasil diubah.', 'success')
                
        return redirect(url_for('profile'))
    return render_template('profile.html')

# --- ROUTES: PUBLIC & COURSES ---

@app.route('/')
def home():
    category_filter = request.args.get('category', 'all')
    if category_filter == 'all':
        courses = Course.query.all()
    else:
        courses = Course.query.filter_by(category=category_filter).all()
    return render_template('index.html', courses=courses)

@app.route('/course/<int:course_id>')
def course_detail(course_id):
    course = Course.query.get_or_404(course_id)
    is_enrolled = False
    if current_user.is_authenticated:
        is_enrolled = Enrollment.query.filter_by(user_id=current_user.id, course_id=course.id).first() is not None
    return render_template('course_detail.html', course=course, is_enrolled=is_enrolled)

# --- ROUTES: CART & CHECKOUT ---

@app.route('/add_to_cart/<int:course_id>')
def add_to_cart(course_id):
    if 'cart' not in session:
        session['cart'] = []
    
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
    savings = subtotal - total
    
    return render_template('cart.html', courses=courses, subtotal=subtotal, total=total, savings=savings)

@app.route('/cart/remove/<int:course_id>')
def remove_from_cart(course_id):
    cart_ids = session.get('cart', [])
    if course_id in cart_ids:
        cart_ids.remove(course_id)
        session['cart'] = cart_ids
        flash('Item dihapus.', 'success')
    return redirect(url_for('cart'))

@app.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    cart_ids = session.get('cart', [])
    if not cart_ids:
        flash('Keranjang kosong.', 'error')
        return redirect(url_for('home'))
        
    courses = Course.query.filter(Course.id.in_(cart_ids)).all()
    total = sum([c.price * (1 - c.discount/100) for c in courses])

    if request.method == 'POST':
        payment_method = request.form.get('payment')
        
        new_order = Order(
            user_id=current_user.id,
            total=total,
            status='pending',
            payment_method=payment_method
        )
        db.session.add(new_order)
        db.session.flush()
        
        for c in courses:
            final_price = c.price * (1 - c.discount/100)
            item = OrderItem(
                order_id=new_order.id,
                course_id=c.id,
                price_at_purchase=final_price,
                course_title=c.title
            )
            db.session.add(item)
            
        session.pop('cart', None)
        db.session.commit()
        flash(f'Order #{new_order.id} berhasil dibuat. Tunggu konfirmasi admin.', 'success')
        return redirect(url_for('my_courses'))

    return render_template('checkout.html', courses=courses, total=total)

# --- ROUTES: STUDENT LEARNING ---

@app.route('/my-courses')
@login_required
def my_courses():
    enrollments = Enrollment.query.filter_by(user_id=current_user.id).all()
    course_ids = [e.course_id for e in enrollments]
    courses = Course.query.filter(Course.id.in_(course_ids)).all()
    
    courses_data = []
    completed_count = 0
    in_progress_count = 0
    
    for course in courses:
        total_lessons = len(course.lessons)
        completed_lessons = LessonProgress.query.filter_by(user_id=current_user.id, course_id=course.id).count()
        progress = int((completed_lessons / total_lessons * 100)) if total_lessons > 0 else 0
        
        if progress == 100: completed_count += 1
        elif progress > 0: in_progress_count += 1
            
        courses_data.append({
            'course': course,
            'progress': progress,
            'is_completed': progress == 100
        })

    stats = {'total': len(courses), 'completed': completed_count, 'in_progress': in_progress_count}
    return render_template('my_courses.html', courses_data=courses_data, stats=stats)

@app.route('/learning/<int:course_id>')
@login_required
def learning(course_id):
    enrollment = Enrollment.query.filter_by(user_id=current_user.id, course_id=course_id).first()
    if not enrollment:
        flash('Anda belum terdaftar.', 'error')
        return redirect(url_for('course_detail', course_id=course_id))

    course = Course.query.get_or_404(course_id)
    completed_lessons = LessonProgress.query.filter_by(user_id=current_user.id, course_id=course_id).all()
    completed_ids = [p.lesson_id for p in completed_lessons]
    
    total = len(course.lessons)
    progress = int((len(completed_ids) / total * 100)) if total > 0 else 0

    return render_template('learning.html', course=course, completed_lesson_ids=completed_ids, progress_percent=progress)

@app.route('/api/mark-complete', methods=['POST'])
@login_required
def mark_complete():
    data = request.get_json()
    course_id = data.get('course_id')
    lesson_id = data.get('lesson_id')
    
    exists = LessonProgress.query.filter_by(user_id=current_user.id, course_id=course_id, lesson_id=lesson_id).first()
    if not exists:
        progress = LessonProgress(user_id=current_user.id, course_id=course_id, lesson_id=lesson_id)
        db.session.add(progress)
        db.session.commit()
        
    total = Lesson.query.filter_by(course_id=course_id).count()
    completed = LessonProgress.query.filter_by(user_id=current_user.id, course_id=course_id).count()
    
    return jsonify({'status': 'success', 'progress': int((completed/total*100)), 'is_completed': completed==total})

@app.route('/certificate/<int:course_id>')
@login_required
def view_certificate(course_id):
    course = Course.query.get_or_404(course_id)
    enrollment = Enrollment.query.filter_by(user_id=current_user.id, course_id=course_id).first()
    
    if not enrollment:
        flash('Akses ditolak.', 'error')
        return redirect(url_for('home'))

    cert_number = f"TD-{str(course.id).zfill(3)}-{str(current_user.id).zfill(6)}"
    months = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
    now = datetime.now()
    date_str = f"{now.day} {months[now.month - 1]} {now.year}"

    return render_template('certificate.html', course=course, cert_number=cert_number, completion_date=date_str)

# --- ROUTES: ADMIN ---

@app.route('/admin')
@login_required
def admin_panel():
    if not current_user.is_admin:
        return redirect(url_for('home'))

    active_tab = request.args.get('tab', 'courses')
    filter_cat = request.args.get('filter', 'all')

    courses = Course.query.all() if filter_cat == 'all' else Course.query.filter_by(category=filter_cat).all()
    orders = Order.query.order_by(Order.created_at.desc()).all()
    users = User.query.all()
    
    stats = {
        'total_courses': Course.query.count(),
        'total_orders': Order.query.count(),
        'pending_orders': Order.query.filter_by(status='pending').count(),
        'total_users': User.query.count()
    }

    return render_template('admin_panel.html', active_tab=active_tab, filter_category=filter_cat, courses=courses, orders=orders, users=users, stats=stats)

@app.route('/admin/add-course', methods=['GET', 'POST'])
@app.route('/admin/edit-course/<int:course_id>', methods=['GET', 'POST'])
@login_required
def save_course(course_id=None):
    if not current_user.is_admin: return redirect(url_for('home'))

    course = Course.query.get_or_404(course_id) if course_id else None

    if request.method == 'POST':
        # ... (Ambil data course dasar: title, category, dll - TETAP SAMA) ...
        title = request.form.get('title')
        category = request.form.get('category')
        image = request.form.get('image')
        duration = request.form.get('duration')
        level = request.form.get('level')
        description = request.form.get('description')
        price = int(request.form.get('price', 0))
        discount = int(request.form.get('discount', 0))
        instructor = request.form.get('instructor')
        
        # Ambil JSON lessons
        lessons_data = json.loads(request.form.get('lessons_json', '[]'))

        if not course:
            course = Course(title=title, category=category, image=image, duration=duration, level=level, description=description, price=price, discount=discount, instructor=instructor)
            db.session.add(course)
            db.session.flush()
        else:
            # Update fields
            course.title = title
            course.category = category
            course.image = image
            course.duration = duration
            course.level = level
            course.description = description
            course.price = price
            course.discount = discount
            course.instructor = instructor
            
            # Hapus lesson lama
            Lesson.query.filter_by(course_id=course.id).delete()

        # Simpan Lessons Baru beserta CONTENT-nya
        for l in lessons_data:
            # Pastikan content dikirim, jika quiz/array maka dump ke string
            content_data = l.get('content', '')
            if isinstance(content_data, (dict, list)):
                content_data = json.dumps(content_data)
                
            new_lesson = Lesson(
                course_id=course.id, 
                title=l['title'], 
                duration=l['duration'], 
                type=l['type'], 
                is_preview=l['isPreview'],
                content=content_data # Simpan konten
            )
            db.session.add(new_lesson)

        db.session.commit()
        flash('Kursus berhasil disimpan.', 'success')
        return redirect(url_for('admin_panel'))

    # Persiapkan data untuk edit mode
    existing_lessons = []
    if course:
        for l in course.lessons:
            # Jika tipe quiz, load content string kembali ke JSON object agar JS bisa baca
            content_val = l.content
            if l.type == 'quiz' and l.content:
                try:
                    content_val = json.loads(l.content)
                except:
                    content_val = []
            
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

# --- SEED DATA ---

def seed_data():
    if Course.query.first(): return
    
    # Admin
    if not User.query.filter_by(email='admin@tutordigital.com').first():
        admin = User(username='Admin Tutor', email='admin@tutordigital.com', password=generate_password_hash('admin123'), is_admin=True)
        db.session.add(admin)

    # Sample Courses
    courses_data = [
        {
            'title': 'Pemrograman Web untuk Pemula', 'category': 'IT',
            'image': 'https://images.unsplash.com/photo-1565229284535-2cbbe3049123?w=1080&q=80',
            'duration': '8 Minggu', 'students': 1250, 'rating': 4.8, 'level': 'Pemula',
            'description': 'Pelajari dasar-dasar HTML, CSS, dan JavaScript.', 'price': 500000, 'discount': 20, 'instructor': 'Budi Santoso'
        },
        {
            'title': 'Microsoft Office Profesional', 'category': 'Office',
            'image': 'https://images.unsplash.com/photo-1706735733956-deebaf5d001c?w=1080&q=80',
            'duration': '6 Minggu', 'students': 2100, 'rating': 4.9, 'level': 'Menengah',
            'description': 'Kuasai Word, Excel, dan PowerPoint.', 'price': 400000, 'discount': 15, 'instructor': 'Siti Rahayu'
        }
    ]
    
    for data in courses_data:
        course = Course(**data)
        db.session.add(course)
        db.session.flush()
        # Add dummy lessons
        db.session.add(Lesson(course_id=course.id, title='Pengenalan', duration='10 menit'))
        db.session.add(Lesson(course_id=course.id, title='Materi Inti', duration='45 menit'))
        
    db.session.commit()

if __name__ == '__main__':
    with app.app_context():
        print("Mereset database...")
        
        # 1. Hapus semua tabel lama
        db.drop_all()
        
        # 2. Buat ulang tabel dengan struktur baru (termasuk kolom 'content')
        db.create_all()
        
        # 3. Isi data awal
        seed_data()
        
        print("Database berhasil di-reset dan di-update!")
        
    app.run(debug=True)