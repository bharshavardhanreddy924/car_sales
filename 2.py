from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_pymongo import PyMongo
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from functools import wraps
from bson import ObjectId
import pandas as pd
import os
from datetime import datetime
import calendar

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

# Decorators for route protection
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session or session['role'] != 'admin':
            flash('Admin access required')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# Routes
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
            session['user_id'] = str(user['_id'])
            flash('Login successful!')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password')
    return render_template('login.html')

@app.route('/public_register', methods=['GET', 'POST'])
def public_register():
    if request.method == 'POST':
        # Check if username already exists
        existing_user = mongo.db.users.find_one({"username": request.form['username']})
        if existing_user:
            flash('Username already exists')
            return redirect(url_for('public_register'))

        try:
            # Calculate age from DOB
            dob = datetime.strptime(request.form['dob'], '%Y-%m-%d')
            today = datetime.now()
            age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
            
            # Generate employee ID
            year = str(datetime.now().year)
            count = mongo.db.users.count_documents({"role": "sales_person"}) + 1
            employee_id = f"SP_{year}_{str(count).zfill(3)}"
            
            new_user = {
                "username": request.form['username'],
                "password": generate_password_hash(request.form['password']),
                "role": "sales_person",
                "employee_id": employee_id,
                "first_name": request.form['first_name'],
                "last_name": request.form['last_name'],
                "gender": request.form['gender'],
                "phone_number": request.form['phone_number'],
                "hire_date": datetime.now(),
                "salary": 0,  # Will be set by admin
                "work_schedule": "TBD",  # Will be set by admin
                "dob": dob,
                "age": age,
                "sales_month": 0,
                "sales_year": 0,
                "status": "pending",  # New users need admin approval
                "created_at": datetime.now()
            }
            
            mongo.db.users.insert_one(new_user)
            flash('Registration successful! Please wait for admin approval.')
            return redirect(url_for('login'))
        except Exception as e:
            flash(f'Error during registration: {str(e)}')
            return redirect(url_for('public_register'))
            
    return render_template('public_register.html')

@app.route('/dashboard')
@login_required
def dashboard():
    if session['role'] == 'admin':
        # Admin Dashboard Data
        cars = list(mongo.db.cars.find())
        sales = list(mongo.db.sales.find())
        staff = list(mongo.db.users.find({"role": "sales_person"}))
        orders = list(mongo.db.orders.find())
        
        # Calculate statistics
        total_sales = len(sales)
        total_revenue = sum(sale.get('price', 0) for sale in sales)
        pending_approvals = mongo.db.users.count_documents({"role": "sales_person", "status": "pending"})
        pending_orders = mongo.db.orders.count_documents({"status": "pending"})
        
        # Monthly sales statistics
        current_month = datetime.now().month
        current_year = datetime.now().year
        monthly_sales = mongo.db.sales.count_documents({
            "sale_date": {
                "$gte": datetime(current_year, current_month, 1),
                "$lt": datetime(current_year, current_month + 1, 1) if current_month < 12 else datetime(current_year + 1, 1, 1)
            }
        })
        
        return render_template('admin_dashboard.html',
                             cars=cars,
                             sales=sales,
                             staff=staff,
                             orders=orders,
                             total_sales=total_sales,
                             total_revenue=total_revenue,
                             monthly_sales=monthly_sales,
                             pending_approvals=pending_approvals,
                             pending_orders=pending_orders)
    else:
        # Sales Person Dashboard Data
        user = mongo.db.users.find_one({"_id": ObjectId(session['user_id'])})
        available_cars = list(mongo.db.cars.find())
        user_orders = list(mongo.db.orders.find({"sales_person_id": session['user_id']}).sort("order_date", -1))
        
        # Calculate statistics
        total_sales = len([order for order in user_orders if order['status'] == 'approved'])
        total_revenue = sum(order.get('price', 0) for order in user_orders if order['status'] == 'approved')
        
        # Get recent orders
        recent_orders = user_orders[:5]
        
        return render_template('sales_dashboard.html',
                             user=user,
                             available_cars=available_cars,
                             recent_orders=recent_orders,
                             total_sales=total_sales,
                             total_revenue=total_revenue,
                             monthly_sales=len([order for order in user_orders 
                                              if order['status'] == 'approved' and 
                                              order['order_date'].month == datetime.now().month]))

@app.route('/place_order', methods=['POST'])
@login_required
def place_order():
    if request.method == 'POST':
        car_id = request.form['car_id']
        customer_name = request.form['customer_name']
        customer_phone = request.form['customer_phone']
        customer_email = request.form['customer_email']
        
        car = mongo.db.cars.find_one({"_id": ObjectId(car_id)})
        if not car:
            flash('Car not found')
            return redirect(url_for('dashboard'))
        
        order = {
            "car_id": car_id,
            "car_model": car['Model Name'],
            "price": car['Price of Model ($)'],
            "sales_person_id": session['user_id'],
            "sales_person_name": session['user'],
            "customer_name": customer_name,
            "customer_phone": customer_phone,
            "customer_email": customer_email,
            "order_date": datetime.now(),
            "status": "pending"
        }
        
        mongo.db.orders.insert_one(order)
        flash('Order placed successfully!')
        return redirect(url_for('dashboard'))

@app.route('/orders')
@admin_required
def orders():
    all_orders = list(mongo.db.orders.find().sort("order_date", -1))
    return render_template('orders.html', orders=all_orders)

@app.route('/update_order_status/<order_id>/<status>')
@admin_required
def update_order_status(order_id, status):
    try:
        mongo.db.orders.update_one(
            {"_id": ObjectId(order_id)},
            {"$set": {"status": status}}
        )
        
        # If order is approved, update sales statistics
        if status == 'approved':
            order = mongo.db.orders.find_one({"_id": ObjectId(order_id)})
            if order:
                # Add to sales collection
                sale = {
                    "order_id": order_id,
                    "car_id": order['car_id'],
                    "car_model": order['car_model'],
                    "price": order['price'],
                    "sales_person_id": order['sales_person_id'],
                    "sales_person_name": order['sales_person_name'],
                    "customer_name": order['customer_name'],
                    "sale_date": datetime.now()
                }
                mongo.db.sales.insert_one(sale)
                
                # Update sales person's statistics
                mongo.db.users.update_one(
                    {"_id": ObjectId(order['sales_person_id'])},
                    {
                        "$inc": {
                            "sales_month": 1,
                            "sales_year": 1
                        }
                    }
                )
        
        flash(f'Order {status} successfully!')
    except Exception as e:
        flash(f'Error updating order status: {str(e)}')
    return redirect(url_for('orders'))

@app.route('/manage_staff')
@admin_required
def manage_staff():
    staff = list(mongo.db.users.find({"role": "sales_person"}))
    return render_template('manage_staff.html', staff=staff)

@app.route('/approve_sales_person/<user_id>')
@admin_required
def approve_sales_person(user_id):
    try:
        mongo.db.users.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"status": "active"}}
        )
        flash('Sales person approved successfully!')
    except Exception as e:
        flash(f'Error approving sales person: {str(e)}')
    return redirect(url_for('manage_staff'))

@app.route('/reject_sales_person/<user_id>')
@admin_required
def reject_sales_person(user_id):
    try:
        mongo.db.users.delete_one({"_id": ObjectId(user_id)})
        flash('Sales person rejected and removed from system.')
    except Exception as e:
        flash(f'Error rejecting sales person: {str(e)}')
    return redirect(url_for('manage_staff'))

@app.route('/update_sales_person/<user_id>', methods=['POST'])
@admin_required
def update_sales_person(user_id):
    try:
        updates = {
            "salary": float(request.form['salary']),
            "work_schedule": request.form['work_schedule']
        }
        
        mongo.db.users.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": updates}
        )
        flash('Sales person information updated successfully!')
    except Exception as e:
        flash(f'Error updating sales person information: {str(e)}')
    return redirect(url_for('manage_staff'))

@app.route('/logout')
@login_required
def logout():
    session.clear()
    flash('You have been logged out.')
    return redirect(url_for('login'))

# Car Management Routes
@app.route('/add_car', methods=['POST'])
@admin_required
def add_car():
    try:
        new_car = {
            "Model Name": request.form['model_name'],
            "Type": request.form['type'],
            "Year": int(request.form['year']),
            "Price of Model ($)": float(request.form['price']),
            "created_at": datetime.now()
        }
        
        mongo.db.cars.insert_one(new_car)
        flash('Car added successfully!')
    except Exception as e:
        flash(f'Error adding car: {str(e)}')
    return redirect(url_for('dashboard'))

@app.route('/update_car/<car_id>', methods=['POST'])
@admin_required
def update_car(car_id):
    try:
        updates = {
            "Model Name": request.form['model_name'],
            "Type": request.form['type'],
            "Year": int(request.form['year']),
            "Price of Model ($)": float(request.form['price'])
        }
        
        mongo.db.cars.update_one(
            {"_id": ObjectId(car_id)},
            {"$set": updates}
        )
        flash('Car information updated successfully!')
    except Exception as e:
        flash(f'Error updating car information: {str(e)}')
    return redirect(url_for('dashboard'))

@app.route('/delete_car/<car_id>')
@admin_required
def delete_car(car_id):
    try:
        mongo.db.cars.delete_one({"_id": ObjectId(car_id)})
        flash('Car removed successfully!')
    except Exception as e:
        flash(f'Error removing car: {str(e)}')
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    create_admin()
    app.run(debug=True)