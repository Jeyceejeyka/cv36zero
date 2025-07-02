from flask import Flask, request, jsonify, session
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os
from datetime import datetime, timedelta
import jwt
from functools import wraps

app = Flask(__name__)
app.config['SECRET_KEY'] = 'cv360-secret-key-change-in-production'
CORS(app, supports_credentials=True)

# Database setup
def init_db():
    conn = sqlite3.connect('cv360.db')
    c = conn.cursor()
    
    # Users table
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'worker',
        phone TEXT,
        full_name TEXT,
        location TEXT,
        profile_photo TEXT,
        is_verified BOOLEAN DEFAULT FALSE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # CV profiles table
    c.execute('''CREATE TABLE IF NOT EXISTS cv_profiles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        bio TEXT,
        skills TEXT,
        experience TEXT,
        education TEXT,
        certifications TEXT,
        voice_cv_path TEXT,
        is_approved BOOLEAN DEFAULT FALSE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )''')
    
    # Jobs table
    c.execute('''CREATE TABLE IF NOT EXISTS jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        employer_id INTEGER,
        title TEXT NOT NULL,
        description TEXT,
        location TEXT,
        salary_range TEXT,
        job_type TEXT,
        requirements TEXT,
        is_international BOOLEAN DEFAULT FALSE,
        is_approved BOOLEAN DEFAULT FALSE,
        deadline DATE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (employer_id) REFERENCES users (id)
    )''')
    
    # Applications table
    c.execute('''CREATE TABLE IF NOT EXISTS applications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id INTEGER,
        worker_id INTEGER,
        status TEXT DEFAULT 'pending',
        message TEXT,
        applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (job_id) REFERENCES jobs (id),
        FOREIGN KEY (worker_id) REFERENCES users (id)
    )''')
    
    # Messages table
    c.execute('''CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender_id INTEGER,
        receiver_id INTEGER,
        content TEXT,
        is_read BOOLEAN DEFAULT FALSE,
        sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (sender_id) REFERENCES users (id),
        FOREIGN KEY (receiver_id) REFERENCES users (id)
    )''')
    
    conn.commit()
    conn.close()

# Initialize database
init_db()

# JWT token decorator
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'message': 'Token is missing'}), 401
        
        try:
            if token.startswith('Bearer '):
                token = token.split(' ')[1]
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            current_user_id = data['user_id']
        except:
            return jsonify({'message': 'Token is invalid'}), 401
        
        return f(current_user_id, *args, **kwargs)
    
    return decorated

# Authentication routes
@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    
    # Validate input
    required_fields = ['username', 'email', 'password', 'role', 'full_name']
    for field in required_fields:
        if field not in data:
            return jsonify({'message': f'{field} is required'}), 400
    
    if data['role'] not in ['worker', 'employer', 'admin']:
        return jsonify({'message': 'Invalid role'}), 400
    
    conn = sqlite3.connect('cv360.db')
    c = conn.cursor()
    
    # Check if user exists
    c.execute('SELECT id FROM users WHERE username = ? OR email = ?', 
              (data['username'], data['email']))
    if c.fetchone():
        conn.close()
        return jsonify({'message': 'User already exists'}), 400
    
    # Create user
    password_hash = generate_password_hash(data['password'])
    c.execute('''INSERT INTO users (username, email, password_hash, role, full_name, phone, location) 
                 VALUES (?, ?, ?, ?, ?, ?, ?)''', 
              (data['username'], data['email'], password_hash, data['role'], 
               data['full_name'], data.get('phone', ''), data.get('location', '')))
    
    user_id = c.lastrowid
    conn.commit()
    conn.close()
    
    # Generate token
    token = jwt.encode({
        'user_id': user_id,
        'exp': datetime.utcnow() + timedelta(days=30)
    }, app.config['SECRET_KEY'])
    
    return jsonify({
        'message': 'User created successfully',
        'token': token,
        'user': {
            'id': user_id,
            'username': data['username'],
            'email': data['email'],
            'role': data['role'],
            'full_name': data['full_name']
        }
    }), 201

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    
    if not data.get('username') or not data.get('password'):
        return jsonify({'message': 'Username and password required'}), 400
    
    conn = sqlite3.connect('cv360.db')
    c = conn.cursor()
    
    c.execute('SELECT * FROM users WHERE username = ? OR email = ?', 
              (data['username'], data['username']))
    user = c.fetchone()
    conn.close()
    
    if not user or not check_password_hash(user[3], data['password']):
        return jsonify({'message': 'Invalid credentials'}), 401
    
    token = jwt.encode({
        'user_id': user[0],
        'exp': datetime.utcnow() + timedelta(days=30)
    }, app.config['SECRET_KEY'])
    
    return jsonify({
        'token': token,
        'user': {
            'id': user[0],
            'username': user[1],
            'email': user[2],
            'role': user[4],
            'full_name': user[6],
            'phone': user[5],
            'location': user[7]
        }
    })

# User profile routes
@app.route('/api/profile', methods=['GET'])
@token_required
def get_profile(current_user_id):
    conn = sqlite3.connect('cv360.db')
    c = conn.cursor()
    
    c.execute('SELECT * FROM users WHERE id = ?', (current_user_id,))
    user = c.fetchone()
    
    if not user:
        conn.close()
        return jsonify({'message': 'User not found'}), 404
    
    # Get CV profile if exists
    c.execute('SELECT * FROM cv_profiles WHERE user_id = ?', (current_user_id,))
    cv_profile = c.fetchone()
    
    conn.close()
    
    profile_data = {
        'id': user[0],
        'username': user[1],
        'email': user[2],
        'role': user[4],
        'phone': user[5],
        'full_name': user[6],
        'location': user[7],
        'profile_photo': user[8],
        'is_verified': user[9],
        'cv_profile': {
            'bio': cv_profile[2] if cv_profile else '',
            'skills': cv_profile[3] if cv_profile else '',
            'experience': cv_profile[4] if cv_profile else '',
            'education': cv_profile[5] if cv_profile else '',
            'certifications': cv_profile[6] if cv_profile else '',
            'is_approved': cv_profile[8] if cv_profile else False
        } if cv_profile else None
    }
    
    return jsonify(profile_data)

# Jobs routes
@app.route('/api/jobs', methods=['GET'])
@token_required
def get_jobs(current_user_id):
    conn = sqlite3.connect('cv360.db')
    c = conn.cursor()
    
    # Get user role
    c.execute('SELECT role FROM users WHERE id = ?', (current_user_id,))
    user_role = c.fetchone()[0]
    
    if user_role == 'employer':
        # Get employer's jobs
        c.execute('''SELECT j.*, u.full_name as employer_name 
                     FROM jobs j 
                     JOIN users u ON j.employer_id = u.id 
                     WHERE j.employer_id = ?
                     ORDER BY j.created_at DESC''', (current_user_id,))
    else:
        # Get all approved jobs for workers/admins
        c.execute('''SELECT j.*, u.full_name as employer_name 
                     FROM jobs j 
                     JOIN users u ON j.employer_id = u.id 
                     WHERE j.is_approved = TRUE
                     ORDER BY j.created_at DESC''')
    
    jobs = c.fetchall()
    conn.close()
    
    jobs_list = []
    for job in jobs:
        jobs_list.append({
            'id': job[0],
            'employer_id': job[1],
            'title': job[2],
            'description': job[3],
            'location': job[4],
            'salary_range': job[5],
            'job_type': job[6],
            'requirements': job[7],
            'is_international': job[8],
            'is_approved': job[9],
            'deadline': job[10],
            'created_at': job[11],
            'employer_name': job[12]
        })
    
    return jsonify(jobs_list)

@app.route('/api/jobs', methods=['POST'])
@token_required
def create_job(current_user_id):
    data = request.get_json()
    
    # Validate input
    required_fields = ['title', 'description', 'location', 'salary_range', 'job_type']
    for field in required_fields:
        if field not in data:
            return jsonify({'message': f'{field} is required'}), 400
    
    conn = sqlite3.connect('cv360.db')
    c = conn.cursor()
    
    # Check if user is employer
    c.execute('SELECT role FROM users WHERE id = ?', (current_user_id,))
    user_role = c.fetchone()[0]
    
    if user_role != 'employer':
        conn.close()
        return jsonify({'message': 'Only employers can create jobs'}), 403
    
    c.execute('''INSERT INTO jobs (employer_id, title, description, location, 
                 salary_range, job_type, requirements, is_international, deadline) 
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
              (current_user_id, data['title'], data['description'], data['location'],
               data['salary_range'], data['job_type'], data.get('requirements', ''),
               data.get('is_international', False), data.get('deadline')))
    
    job_id = c.lastrowid
    conn.commit()
    conn.close()
    
    return jsonify({'message': 'Job created successfully', 'job_id': job_id}), 201

# Applications routes
@app.route('/api/applications', methods=['POST'])
@token_required
def apply_for_job(current_user_id):
    data = request.get_json()
    
    if not data.get('job_id'):
        return jsonify({'message': 'job_id is required'}), 400
    
    conn = sqlite3.connect('cv360.db')
    c = conn.cursor()
    
    # Check if user is worker
    c.execute('SELECT role FROM users WHERE id = ?', (current_user_id,))
    user_role = c.fetchone()[0]
    
    if user_role != 'worker':
        conn.close()
        return jsonify({'message': 'Only workers can apply for jobs'}), 403
    
    # Check if already applied
    c.execute('SELECT id FROM applications WHERE job_id = ? AND worker_id = ?',
              (data['job_id'], current_user_id))
    if c.fetchone():
        conn.close()
        return jsonify({'message': 'Already applied for this job'}), 400
    
    c.execute('''INSERT INTO applications (job_id, worker_id, message) 
                 VALUES (?, ?, ?)''',
              (data['job_id'], current_user_id, data.get('message', '')))
    
    conn.commit()
    conn.close()
    
    return jsonify({'message': 'Application submitted successfully'}), 201

# Admin routes
@app.route('/api/admin/stats', methods=['GET'])
@token_required
def get_admin_stats(current_user_id):
    conn = sqlite3.connect('cv360.db')
    c = conn.cursor()
    
    # Check if user is admin
    c.execute('SELECT role FROM users WHERE id = ?', (current_user_id,))
    user_role = c.fetchone()[0]
    
    if user_role != 'admin':
        conn.close()
        return jsonify({'message': 'Admin access required'}), 403
    
    # Get statistics
    c.execute('SELECT COUNT(*) FROM users WHERE role = "worker"')
    total_workers = c.fetchone()[0]
    
    c.execute('SELECT COUNT(*) FROM users WHERE role = "employer"')
    total_employers = c.fetchone()[0]
    
    c.execute('SELECT COUNT(*) FROM jobs')
    total_jobs = c.fetchone()[0]
    
    c.execute('SELECT COUNT(*) FROM applications')
    total_applications = c.fetchone()[0]
    
    c.execute('SELECT COUNT(*) FROM jobs WHERE is_approved = FALSE')
    pending_jobs = c.fetchone()[0]
    
    conn.close()
    
    return jsonify({
        'total_workers': total_workers,
        'total_employers': total_employers,
        'total_jobs': total_jobs,
        'total_applications': total_applications,
        'pending_jobs': pending_jobs
    })

@app.route('/api/admin/users', methods=['GET'])
@token_required
def get_all_users(current_user_id):
    conn = sqlite3.connect('cv360.db')
    c = conn.cursor()
    
    # Check if user is admin
    c.execute('SELECT role FROM users WHERE id = ?', (current_user_id,))
    user_role = c.fetchone()[0]
    
    if user_role != 'admin':
        conn.close()
        return jsonify({'message': 'Admin access required'}), 403
    
    c.execute('SELECT id, username, email, role, full_name, phone, location, is_verified, created_at FROM users')
    users = c.fetchall()
    conn.close()
    
    users_list = []
    for user in users:
        users_list.append({
            'id': user[0],
            'username': user[1],
            'email': user[2],
            'role': user[3],
            'full_name': user[4],
            'phone': user[5],
            'location': user[6],
            'is_verified': user[7],
            'created_at': user[8]
        })
    
    return jsonify(users_list)

if __name__ == '__main__':
    app.run(debug=True, port=5000)