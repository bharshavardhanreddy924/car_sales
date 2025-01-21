# app.py
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_pymongo import PyMongo
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from functools import wraps
from bson import ObjectId
import pandas as pd
import os
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'  # Change this to a secure secret key
app.config["MONGO_URI"] = "mongodb://localhost:27017/mercedes_showroom"
mongo = PyMongo(app)

# Create admin user if not exists
def create_admin():
    admin = mongo.db.users.find_one({"username": "ADMIN"})
    if not admin:
        admin_user = {
            "username": "ADMIN",
            "password": generate_password_hash("ADMIN123"),
            "role": "admin",
            "created_at": datetime.now()
        }
        mongo.db.users.insert_one(admin_user)

# Login decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Admin required decorator
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session or session['role'] != 'admin':
            flash('Admin access required')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = mongo.db.users.find_one({"username": username})
        
        if user and check_password_hash(user['password'], password):
            session['user'] = username
            session['role'] = user['role']
            flash('Login successful!')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
@admin_required
def register():
    if request.method == 'POST':
        # Calculate age from DOB
        dob = datetime.strptime(request.form['dob'], '%Y-%m-%d')
        today = datetime.now()
        age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        
        new_user = {
            "username": request.form['username'],
            "password": generate_password_hash(request.form['password']),
            "role": "sales_person",
            "employee_id": request.form['employee_id'],
            "first_name": request.form['first_name'],
            "last_name": request.form['last_name'],
            "gender": request.form['gender'],
            "phone_number": request.form['phone_number'],
            "hire_date": datetime.strptime(request.form['hire_date'], '%Y-%m-%d'),
            "salary": float(request.form['salary']),
            "work_schedule": request.form['work_schedule'],
            "dob": dob,
            "age": age,
            "sales_month": 0,
            "sales_year": 0,
            "created_at": datetime.now()
        }
        
        mongo.db.users.insert_one(new_user)
        flash('Sales person registered successfully!')
        return redirect(url_for('manage_staff'))
    return render_template('register.html')

@app.route('/dashboard')
@login_required
def dashboard():
    cars = list(mongo.db.cars.find())
    sales = list(mongo.db.sales.find())
    if session['role'] == 'admin':
        staff = list(mongo.db.users.find({"role": "sales_person"}))
        return render_template('admin_dashboard.html', cars=cars, sales=sales, staff=staff)
    else:
        user = mongo.db.users.find_one({"username": session['user']})
        user_sales = list(mongo.db.sales.find({"sales_person_id": str(user['_id'])}))
        return render_template('sales_dashboard.html', cars=cars, sales=user_sales, user=user)

@app.route('/manage_staff')
@admin_required
def manage_staff():
    staff = list(mongo.db.users.find({"role": "sales_person"}))
    return render_template('manage_staff.html', staff=staff)

@app.route('/add_sale', methods=['GET', 'POST'])
@login_required
def add_sale():
    if request.method == 'POST':
        user = mongo.db.users.find_one({"username": session['user']})
        
        sale = {
            "car_id": request.form['car_id'],
            "sales_person_id": str(user['_id']),
            "sale_date": datetime.now(),
            "price": float(request.form['price']),
            "customer_name": request.form['customer_name'],
            "customer_contact": request.form['customer_contact']
        }
        
        mongo.db.sales.insert_one(sale)
        
        # Update sales person's sales counts
        mongo.db.users.update_one(
            {"_id": user['_id']},
            {
                "$inc": {
                    "sales_month": 1,
                    "sales_year": 1
                }
            }
        )
        
        flash('Sale recorded successfully!')
        return redirect(url_for('dashboard'))
    
    cars = list(mongo.db.cars.find())
    return render_template('add_sale.html', cars=cars)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/import_cars')
@admin_required
def import_cars():
    # Import cars from CSV if not already imported
    if mongo.db.cars.count_documents({}) == 0:
        df = pd.read_csv('Mercedes_Benz_Data.csv')
        cars = df.to_dict('records')
        mongo.db.cars.insert_many(cars)
        flash('Cars imported successfully!')
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    create_admin()
    app.run(debug=True)