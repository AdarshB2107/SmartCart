from flask import Flask, render_template, request, redirect, session, flash, jsonify, make_response
from flask_mail import Mail, Message
import sqlite3
import bcrypt
import random
import os
from werkzeug.utils import secure_filename
import config
import razorpay
import traceback
from utils.pdf_generator import generate_pdf

app = Flask(__name__)
app.secret_key = config.SECRET_KEY

# ---------------- EMAIL CONFIGURATION ----------------
app.config["MAIL_SERVER"] = config.MAIL_SERVER
app.config["MAIL_PORT"] = config.MAIL_PORT
app.config["MAIL_USE_TLS"] = config.MAIL_USE_TLS
app.config["MAIL_USERNAME"] = config.MAIL_USERNAME
app.config["MAIL_PASSWORD"] = config.MAIL_PASSWORD
mail = Mail(app)

# ---------------- RAZORPAY CONFIGURATION ----------------
razorpay_client = razorpay.Client(
    auth=(config.RAZORPAY_KEY_ID, config.RAZORPAY_KEY_SECRET)
)

# ---------------- FILE UPLOAD FOLDERS ----------------
UPLOAD_FOLDER = "static/uploads/product_images"
ADMIN_UPLOAD_FOLDER = "static/uploads/admin_profiles"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["ADMIN_UPLOAD_FOLDER"] = ADMIN_UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(ADMIN_UPLOAD_FOLDER, exist_ok=True)


class SQLiteCursor:
    """Small compatibility wrapper so existing MySQL-style cursor calls keep working."""
    def __init__(self, cursor, dictionary=False):
        self._cursor = cursor
        self._dictionary = dictionary

    def execute(self, query, params=()):
        # mysql-connector uses %s placeholders; SQLite uses ?.
        query = query.replace("%s", "?")
        self._cursor.execute(query, params or ())
        return self

    def fetchone(self):
        row = self._cursor.fetchone()
        if row is None:
            return None
        return dict(row) if self._dictionary else row

    def fetchall(self):
        rows = self._cursor.fetchall()
        return [dict(row) for row in rows] if self._dictionary else rows

    @property
    def lastrowid(self):
        return self._cursor.lastrowid

    def close(self):
        self._cursor.close()


class SQLiteConnection:
    def __init__(self, path):
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")

    def cursor(self, dictionary=False):
        return SQLiteCursor(self._conn.cursor(), dictionary=dictionary)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()


def get_db_connection():
    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
    first_run = not os.path.exists(config.DB_PATH)
    connection = SQLiteConnection(config.DB_PATH)

    if first_run:
        schema_path = os.path.join(os.path.dirname(config.DB_PATH), "schema.sql")
        with open(schema_path, "r", encoding="utf-8") as schema_file:
            connection._conn.executescript(schema_file.read())
        connection.commit()

    return connection


def logged_in():
    return "admin_id" in session


def user_logged_in():
    return "user_id" in session


# =============================================================
# HOME
# =============================================================
@app.route("/")
def home():
    return render_template("index.html")


# =============================================================
# DAY 2-3: ADMIN SIGNUP + OTP + LOGIN + DASHBOARD + LOGOUT
# =============================================================
@app.route("/admin-signup", methods=["GET", "POST"])
def admin_signup():
    if request.method == "GET":
        return render_template("admin/admin_signup.html")

    name = request.form["name"].strip()
    email = request.form["email"].strip().lower()

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT admin_id FROM admin WHERE email=%s", (email,))
    exists = cur.fetchone()
    cur.close()
    conn.close()

    if exists:
        flash("This email is already registered. Please login instead.", "danger")
        return redirect("/admin-signup")

    session["signup_name"] = name
    session["signup_email"] = email
    session["otp"] = random.randint(100000, 999999)

    try:
        msg = Message(
            "SmartCart Admin OTP",
            sender=config.MAIL_USERNAME,
            recipients=[email]
        )
        msg.body = f"Your OTP for SmartCart Admin Registration is: {session['otp']}"
        mail.send(msg)
    except Exception as e:
        print("ADMIN EMAIL ERROR:", e)
        flash("Could not send OTP. Check Gmail SMTP settings in config.py.", "danger")
        return redirect("/admin-signup")

    flash("OTP sent to your email!", "success")
    return redirect("/verify-otp")


@app.route("/verify-otp", methods=["GET"])
def verify_otp_get():
    if "signup_email" not in session or "otp" not in session:
        flash("Please start admin registration first.", "danger")
        return redirect("/admin-signup")
    return render_template("admin/verify_otp.html")


@app.route("/verify-otp", methods=["POST"])
def verify_otp_post():
    if "signup_email" not in session or "otp" not in session:
        flash("Registration session expired. Please register again.", "danger")
        return redirect("/admin-signup")

    if str(session.get("otp")) != request.form["otp"].strip():
        flash("Invalid OTP. Try again!", "danger")
        return redirect("/verify-otp")

    hashed = bcrypt.hashpw(
        request.form["password"].encode("utf-8"),
        bcrypt.gensalt()
    ).decode("utf-8")

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO admin (name, email, password) VALUES (%s, %s, %s)",
        (session["signup_name"], session["signup_email"], hashed)
    )
    conn.commit()
    cur.close()
    conn.close()

    for key in ("otp", "signup_name", "signup_email"):
        session.pop(key, None)

    flash("Admin registered successfully! Please login.", "success")
    return redirect("/admin-login")


@app.route("/admin-login", methods=["GET", "POST"])
def admin_login():
    if request.method == "GET":
        return render_template("admin/admin_login.html")

    email = request.form["email"].strip().lower()
    password = request.form["password"]

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM admin WHERE email=%s", (email,))
    admin = cur.fetchone()
    cur.close()
    conn.close()

    if not admin:
        flash("Email not found! Please register first.", "danger")
        return redirect("/admin-login")

    stored = admin["password"].encode("utf-8") if isinstance(admin["password"], str) else admin["password"]
    if not bcrypt.checkpw(password.encode("utf-8"), stored):
        flash("Incorrect password! Try again.", "danger")
        return redirect("/admin-login")

    session["admin_id"] = admin["admin_id"]
    session["admin_name"] = admin["name"]
    session["admin_email"] = admin["email"]
    flash("Login successful!", "success")
    return redirect("/admin-dashboard")


@app.route("/admin-dashboard")
def dashboard():
    if not logged_in():
        flash("Please login to access dashboard!", "danger")
        return redirect("/admin-login")
    return render_template("admin/dashboard.html", admin_name=session["admin_name"])


@app.route("/admin-logout")
def logout():
    # Remove both admin and user session values when logging out.
    session.clear()
    flash("Logged out successfully.", "success")
    return redirect("/admin-login")


# =============================================================
# DAY 4: ADD PRODUCT
# =============================================================
@app.route("/admin/add-item", methods=["GET"])
def add_item_page():
    if not logged_in():
        flash("Please login first!", "danger")
        return redirect("/admin-login")
    return render_template("admin/add_item.html")


@app.route("/admin/add-item", methods=["POST"])
def add_item():
    if not logged_in():
        flash("Please login first!", "danger")
        return redirect("/admin-login")

    image = request.files.get("image")
    if not image or not image.filename:
        flash("Please upload a product image!", "danger")
        return redirect("/admin/add-item")

    filename = secure_filename(image.filename)
    image.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO products (name, description, category, price, image) VALUES (%s,%s,%s,%s,%s)",
        (
            request.form["name"],
            request.form["description"],
            request.form["category"],
            request.form["price"],
            filename
        )
    )
    conn.commit()
    cur.close()
    conn.close()
    flash("Product added successfully!", "success")
    return redirect("/admin/item-list")


# =============================================================
# DAY 5 + DAY 7: ADMIN PRODUCT LIST / SEARCH / FILTER / VIEW
# =============================================================
@app.route("/admin/item-list")
def item_list():
    if not logged_in():
        flash("Please login first!", "danger")
        return redirect("/admin-login")

    search = request.args.get("search", "").strip()
    category = request.args.get("category", "").strip()

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT DISTINCT category FROM products ORDER BY category")
    categories = cur.fetchall()

    query = "SELECT * FROM products WHERE 1=1"
    params = []
    if search:
        query += " AND name LIKE %s"
        params.append("%" + search + "%")
    if category:
        query += " AND category=%s"
        params.append(category)

    query += " ORDER BY product_id DESC"
    cur.execute(query, params)
    products = cur.fetchall()
    cur.close()
    conn.close()

    return render_template("admin/item_list.html", products=products, categories=categories)


@app.route("/admin/view-item/<int:item_id>")
def view_item(item_id):
    if not logged_in():
        flash("Please login first!", "danger")
        return redirect("/admin-login")

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM products WHERE product_id=%s", (item_id,))
    product = cur.fetchone()
    cur.close()
    conn.close()

    if not product:
        flash("Product not found!", "danger")
        return redirect("/admin/item-list")

    return render_template("admin/view_item.html", product=product)


# =============================================================
# DAY 6: UPDATE PRODUCT + IMAGE REPLACE
# =============================================================
@app.route("/admin/update-item/<int:item_id>", methods=["GET"])
def update_item_page(item_id):
    if not logged_in():
        flash("Please login first!", "danger")
        return redirect("/admin-login")

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM products WHERE product_id=%s", (item_id,))
    product = cur.fetchone()
    cur.close()
    conn.close()

    if not product:
        flash("Product not found!", "danger")
        return redirect("/admin/item-list")

    return render_template("admin/update_item.html", product=product)


@app.route("/admin/update-item/<int:item_id>", methods=["POST"])
def update_item(item_id):
    if not logged_in():
        flash("Please login first!", "danger")
        return redirect("/admin-login")

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM products WHERE product_id=%s", (item_id,))
    product = cur.fetchone()

    if not product:
        cur.close()
        conn.close()
        flash("Product not found!", "danger")
        return redirect("/admin/item-list")

    final_image = product["image"]
    image = request.files.get("image")

    if image and image.filename:
        new_filename = secure_filename(image.filename)
        image.save(os.path.join(app.config["UPLOAD_FOLDER"], new_filename))

        old_image = product["image"]
        if old_image:
            old_path = os.path.join(app.config["UPLOAD_FOLDER"], old_image)
            if os.path.exists(old_path):
                os.remove(old_path)
        final_image = new_filename

    cur.execute(
        "UPDATE products SET name=%s,description=%s,category=%s,price=%s,image=%s WHERE product_id=%s",
        (
            request.form["name"],
            request.form["description"],
            request.form["category"],
            request.form["price"],
            final_image,
            item_id
        )
    )
    conn.commit()
    cur.close()
    conn.close()
    flash("Product updated successfully!", "success")
    return redirect("/admin/item-list")


# =============================================================
# DAY 7: DELETE PRODUCT + IMAGE
# =============================================================
@app.route("/admin/delete-item/<int:item_id>")
def delete_item(item_id):
    if not logged_in():
        flash("Please login first!", "danger")
        return redirect("/admin-login")

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT image FROM products WHERE product_id=%s", (item_id,))
    product = cur.fetchone()

    if not product:
        cur.close()
        conn.close()
        flash("Product not found!", "danger")
        return redirect("/admin/item-list")

    if product["image"]:
        image_path = os.path.join(app.config["UPLOAD_FOLDER"], product["image"])
        if os.path.exists(image_path):
            os.remove(image_path)

    cur.execute("DELETE FROM products WHERE product_id=%s", (item_id,))
    conn.commit()
    cur.close()
    conn.close()
    flash("Product deleted successfully!", "success")
    return redirect("/admin/item-list")


# =============================================================
# DAY 8: ADMIN PROFILE
# =============================================================
@app.route("/admin/profile", methods=["GET"])
def profile():
    if not logged_in():
        flash("Please login!", "danger")
        return redirect("/admin-login")

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM admin WHERE admin_id=%s", (session["admin_id"],))
    admin = cur.fetchone()
    cur.close()
    conn.close()
    return render_template("admin/admin_profile.html", admin=admin)


@app.route("/admin/profile", methods=["POST"])
def profile_update():
    if not logged_in():
        flash("Please login!", "danger")
        return redirect("/admin-login")

    aid = session["admin_id"]
    name = request.form["name"].strip()
    email = request.form["email"].strip().lower()
    newpass = request.form.get("password", "")
    image = request.files.get("profile_image")

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM admin WHERE admin_id=%s", (aid,))
    admin = cur.fetchone()

    cur.execute("SELECT admin_id FROM admin WHERE email=%s AND admin_id<>%s", (email, aid))
    if cur.fetchone():
        cur.close()
        conn.close()
        flash("That email is already used by another admin.", "danger")
        return redirect("/admin/profile")

    finalpass = (
        bcrypt.hashpw(newpass.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        if newpass else admin["password"]
    )
    finalimage = admin["profile_image"]

    if image and image.filename:
        new_filename = secure_filename(image.filename)
        image.save(os.path.join(app.config["ADMIN_UPLOAD_FOLDER"], new_filename))
        if finalimage:
            old_path = os.path.join(app.config["ADMIN_UPLOAD_FOLDER"], finalimage)
            if os.path.exists(old_path):
                os.remove(old_path)
        finalimage = new_filename

    cur.execute(
        "UPDATE admin SET name=%s,email=%s,password=%s,profile_image=%s WHERE admin_id=%s",
        (name, email, finalpass, finalimage, aid)
    )
    conn.commit()
    cur.close()
    conn.close()

    session["admin_name"] = name
    session["admin_email"] = email
    flash("Profile updated successfully!", "success")
    return redirect("/admin/profile")


# =============================================================
# DAY 9: USER REGISTRATION WITH MANDATORY OTP VERIFICATION
# =============================================================
@app.route("/user-register", methods=["GET", "POST"])
def user_register():
    if request.method == "GET":
        return render_template("user/user_register.html")

    name = request.form["name"].strip()
    email = request.form["email"].strip().lower()
    password = request.form["password"]

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT user_id FROM users WHERE email=%s", (email,))
    existing_user = cur.fetchone()
    cur.close()
    conn.close()

    if existing_user:
        flash("Email already registered! Please login.", "danger")
        return redirect("/user-login")

    # Store registration data temporarily. The user is NOT inserted yet.
    # Database insertion happens only after correct OTP verification.
    session["user_signup_name"] = name
    session["user_signup_email"] = email
    session["user_signup_password"] = password
    session["user_otp"] = random.randint(100000, 999999)

    try:
        msg = Message(
            "SmartCart User OTP",
            sender=config.MAIL_USERNAME,
            recipients=[email]
        )
        msg.body = f"Your OTP for SmartCart User Registration is: {session['user_otp']}"
        mail.send(msg)
    except Exception as e:
        print("USER EMAIL ERROR:", e)
        for key in ("user_signup_name", "user_signup_email", "user_signup_password", "user_otp"):
            session.pop(key, None)
        flash("Could not send OTP. Check Gmail SMTP settings in config.py.", "danger")
        return redirect("/user-register")

    flash("OTP sent to your email. Verification is required to complete registration.", "success")
    return redirect("/user-verify-otp")


@app.route("/user-verify-otp", methods=["GET"])
def user_verify_otp_get():
    if "user_signup_email" not in session or "user_otp" not in session:
        flash("Please start user registration first.", "danger")
        return redirect("/user-register")
    return render_template("user/user_verify_otp.html")


@app.route("/user-verify-otp", methods=["POST"])
def user_verify_otp_post():
    if "user_signup_email" not in session or "user_otp" not in session:
        flash("Registration session expired. Please register again.", "danger")
        return redirect("/user-register")

    entered_otp = request.form["otp"].strip()

    # Mandatory verification: no user record is created unless OTP matches.
    if str(session.get("user_otp")) != entered_otp:
        flash("Invalid OTP. Registration is not completed. Try again!", "danger")
        return redirect("/user-verify-otp")

    email = session["user_signup_email"]
    name = session["user_signup_name"]
    password = session["user_signup_password"]

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT user_id FROM users WHERE email=%s", (email,))
    existing_user = cur.fetchone()

    if existing_user:
        cur.close()
        conn.close()
        for key in ("user_signup_name", "user_signup_email", "user_signup_password", "user_otp"):
            session.pop(key, None)
        flash("Email already registered! Please login.", "danger")
        return redirect("/user-login")

    hashed_password = bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt()
    ).decode("utf-8")

    cur.execute(
        "INSERT INTO users (name, email, password) VALUES (%s, %s, %s)",
        (name, email, hashed_password)
    )
    conn.commit()
    cur.close()
    conn.close()

    for key in ("user_signup_name", "user_signup_email", "user_signup_password", "user_otp"):
        session.pop(key, None)

    flash("Registration successful! OTP verified. Please login.", "success")
    return redirect("/user-login")


# =============================================================
# DAY 9: USER LOGIN + DASHBOARD + LOGOUT
# =============================================================
@app.route("/user-login", methods=["GET", "POST"])
def user_login():
    if request.method == "GET":
        return render_template("user/user_login.html")

    email = request.form["email"].strip().lower()
    password = request.form["password"]

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM users WHERE email=%s", (email,))
    user = cur.fetchone()
    cur.close()
    conn.close()

    if not user:
        flash("Email not found! Please register.", "danger")
        return redirect("/user-login")

    stored = user["password"].encode("utf-8") if isinstance(user["password"], str) else user["password"]
    if not bcrypt.checkpw(password.encode("utf-8"), stored):
        flash("Incorrect password!", "danger")
        return redirect("/user-login")

    session["user_id"] = user["user_id"]
    session["user_name"] = user["name"]
    session["user_email"] = user["email"]
    flash("Login successful!", "success")
    return redirect("/user-dashboard")


@app.route("/user-dashboard")
def user_dashboard():
    if not user_logged_in():
        flash("Please login first!", "danger")
        return redirect("/user-login")
    return render_template("user/user_home.html", user_name=session["user_name"])


@app.route("/user-logout")
def user_logout():
    session.clear()
    flash("Logged out successfully!", "success")
    return redirect("/user-login")


# =============================================================
# DAY 10: USER PRODUCT LISTING + SEARCH + CATEGORY FILTER
# =============================================================
@app.route("/user/products")
def user_products():
    if not user_logged_in():
        flash("Please login to view products!", "danger")
        return redirect("/user-login")

    search = request.args.get("search", "").strip()
    category_filter = request.args.get("category", "").strip()

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT DISTINCT category FROM products ORDER BY category")
    categories = cur.fetchall()

    query = "SELECT * FROM products WHERE 1=1"
    params = []

    if search:
        query += " AND name LIKE %s"
        params.append("%" + search + "%")

    if category_filter:
        query += " AND category = %s"
        params.append(category_filter)

    query += " ORDER BY product_id DESC"
    cur.execute(query, params)
    products = cur.fetchall()
    cur.close()
    conn.close()

    return render_template(
        "user/user_products.html",
        products=products,
        categories=categories
    )


# =============================================================
# DAY 10: USER PRODUCT DETAILS
# =============================================================
@app.route("/user/product/<int:product_id>")
def user_product_details(product_id):
    if not user_logged_in():
        flash("Please login!", "danger")
        return redirect("/user-login")

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM products WHERE product_id=%s", (product_id,))
    product = cur.fetchone()
    cur.close()
    conn.close()

    if not product:
        flash("Product not found!", "danger")
        return redirect("/user/products")

    return render_template("user/product_details.html", product=product)



# =============================================================
# DAY 11: USER CART SYSTEM USING FLASK SESSION
# =============================================================
@app.route("/user/add-to-cart/<int:product_id>", methods=["GET"])
def add_to_cart(product_id):
    if not user_logged_in():
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"success": False, "message": "Please login first!"}), 401
        flash("Please login first!", "danger")
        return redirect("/user-login")

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM products WHERE product_id=%s", (product_id,))
    product = cur.fetchone()
    cur.close()
    conn.close()

    if not product:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"success": False, "message": "Product not found."}), 404
        flash("Product not found.", "danger")
        return redirect(request.referrer or "/user/products")

    cart = session.get("cart", {})
    pid = str(product_id)

    if pid in cart:
        cart[pid]["quantity"] += 1
    else:
        cart[pid] = {
            "name": product["name"],
            "price": float(product["price"]),
            "image": product["image"],
            "quantity": 1
        }

    session["cart"] = cart
    session.modified = True

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        cart_count = sum(item["quantity"] for item in cart.values())
        return jsonify({
            "success": True,
            "message": "Item added to cart!",
            "cart_count": cart_count
        })

    flash("Item added to cart!", "success")
    return redirect(request.referrer or "/user/products")


@app.route("/user/cart")
def view_cart():
    if not user_logged_in():
        flash("Please login first!", "danger")
        return redirect("/user-login")

    cart = session.get("cart", {})
    grand_total = sum(item["price"] * item["quantity"] for item in cart.values())
    cart_count = sum(item["quantity"] for item in cart.values())
    return render_template("user/cart.html", cart=cart, grand_total=grand_total, cart_count=cart_count)


@app.route("/user/cart/increase/<pid>")
def increase_quantity(pid):
    if not user_logged_in():
        flash("Please login first!", "danger")
        return redirect("/user-login")
    cart = session.get("cart", {})
    if pid in cart:
        cart[pid]["quantity"] += 1
        session["cart"] = cart
        session.modified = True
    return redirect("/user/cart")


@app.route("/user/cart/decrease/<pid>")
def decrease_quantity(pid):
    if not user_logged_in():
        flash("Please login first!", "danger")
        return redirect("/user-login")
    cart = session.get("cart", {})
    if pid in cart:
        cart[pid]["quantity"] -= 1
        if cart[pid]["quantity"] <= 0:
            cart.pop(pid)
        session["cart"] = cart
        session.modified = True
    return redirect("/user/cart")


@app.route("/user/cart/remove/<pid>")
def remove_from_cart(pid):
    if not user_logged_in():
        flash("Please login first!", "danger")
        return redirect("/user-login")
    cart = session.get("cart", {})
    if pid in cart:
        cart.pop(pid)
        session["cart"] = cart
        session.modified = True
        flash("Item removed!", "success")
    return redirect("/user/cart")


# =============================================================
# DAY 12: RAZORPAY PAYMENT GATEWAY - CREATE ORDER
# =============================================================
@app.route("/user/pay", methods=["GET", "POST"])
def user_pay():
    if not user_logged_in():
        flash("Please login!", "danger")
        return redirect("/user-login")

    cart = session.get("cart", {})
    if not cart:
        flash("Your cart is empty!", "danger")
        return redirect("/user/products")

    if request.method == "GET":
        return render_template("user/payment.html", step="address")

    # Shipping address is required before creating the payment order.
    address = {
        "full_name": request.form.get("full_name", "").strip(),
        "phone": request.form.get("phone", "").strip(),
        "address_line": request.form.get("address_line", "").strip(),
        "city": request.form.get("city", "").strip(),
        "state": request.form.get("state", "").strip(),
        "postal_code": request.form.get("postal_code", "").strip(),
        "country": request.form.get("country", "").strip()
    }
    if not all(address.values()):
        flash("Please fill in every shipping address field.", "danger")
        return render_template("user/payment.html", step="address", address=address)

    total_amount = sum(item["price"] * item["quantity"] for item in cart.values())
    razorpay_amount = int(round(total_amount * 100))
    try:
        razorpay_order = razorpay_client.order.create({
            "amount": razorpay_amount,
            "currency": "INR",
            "payment_capture": "1"
        })
    except Exception as e:
        app.logger.error("Razorpay order creation failed: %s", e)
        flash("Unable to start payment. Check Razorpay configuration.", "danger")
        return redirect("/user/cart")

    session["shipping_address"] = address
    session["razorpay_order_id"] = razorpay_order["id"]
    session["razorpay_amount"] = total_amount
    return render_template(
        "user/payment.html",
        step="payment",
        amount=total_amount,
        key_id=config.RAZORPAY_KEY_ID,
        order_id=razorpay_order["id"],
        address=address
    )


@app.route("/payment-success")
def payment_success():
    # Kept as a compatibility route from Day 12. Day 13 uses secure POST verification.
    payment_id = request.args.get("payment_id")
    order_id = request.args.get("order_id")
    if not payment_id:
        flash("Payment failed!", "danger")
        return redirect("/user/cart")
    return render_template("user/payment_success.html", payment_id=payment_id, order_id=order_id)


# =============================================================
# DAY 13: VERIFY RAZORPAY PAYMENT + STORE ORDER + ORDER ITEMS
# =============================================================
@app.route("/verify-payment", methods=["POST"])
def verify_payment():
    if not user_logged_in():
        flash("Please login to complete the payment.", "danger")
        return redirect("/user-login")

    razorpay_payment_id = request.form.get("razorpay_payment_id")
    razorpay_order_id = request.form.get("razorpay_order_id")
    razorpay_signature = request.form.get("razorpay_signature")

    if not (razorpay_payment_id and razorpay_order_id and razorpay_signature):
        flash("Payment verification failed (missing data).", "danger")
        return redirect("/user/cart")

    payload = {
        "razorpay_order_id": razorpay_order_id,
        "razorpay_payment_id": razorpay_payment_id,
        "razorpay_signature": razorpay_signature
    }

    try:
        razorpay_client.utility.verify_payment_signature(payload)
    except Exception as e:
        app.logger.error("Razorpay signature verification failed: %s", str(e))
        flash("Payment verification failed. Please contact support.", "danger")
        return redirect("/user/cart")

    user_id = session["user_id"]
    cart = session.get("cart", {})
    if not cart:
        flash("Cart is empty. Cannot create order.", "danger")
        return redirect("/user/products")

    total_amount = sum(item["price"] * item["quantity"] for item in cart.values())

    # Verify that the payment is for the Razorpay order created by this session.
    expected_rzp_order_id = session.get("razorpay_order_id")
    if expected_rzp_order_id and expected_rzp_order_id != razorpay_order_id:
        flash("Payment order mismatch. Please try again.", "danger")
        return redirect("/user/cart")

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO orders
            (user_id, razorpay_order_id, razorpay_payment_id, amount, payment_status,
             shipping_name, shipping_phone, shipping_address, shipping_city, shipping_state,
             shipping_postal_code, shipping_country)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            user_id, razorpay_order_id, razorpay_payment_id, total_amount, "paid",
            session.get("shipping_address", {}).get("full_name", ""),
            session.get("shipping_address", {}).get("phone", ""),
            session.get("shipping_address", {}).get("address_line", ""),
            session.get("shipping_address", {}).get("city", ""),
            session.get("shipping_address", {}).get("state", ""),
            session.get("shipping_address", {}).get("postal_code", ""),
            session.get("shipping_address", {}).get("country", "")
        ))
        order_db_id = cursor.lastrowid

        for pid_str, item in cart.items():
            product_id = int(pid_str)
            cursor.execute("""
                INSERT INTO order_items
                (order_id, product_id, product_name, quantity, price)
                VALUES (%s, %s, %s, %s, %s)
            """, (order_db_id, product_id, item["name"], item["quantity"], item["price"]))

        conn.commit()
        session.pop("cart", None)
        session.pop("razorpay_order_id", None)
        session.pop("razorpay_amount", None)
        session.pop("shipping_address", None)
        flash("Payment successful and order placed!", "success")
        return redirect(f"/user/order-success/{order_db_id}")
    except Exception as e:
        conn.rollback()
        app.logger.error("Order storage failed: %s\n%s", str(e), traceback.format_exc())
        flash("There was an error saving your order. Contact support.", "danger")
        return redirect("/user/cart")
    finally:
        cursor.close()
        conn.close()


@app.route("/user/order-success/<int:order_db_id>")
def order_success(order_db_id):
    if not user_logged_in():
        flash("Please login!", "danger")
        return redirect("/user-login")

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT * FROM orders WHERE order_id=%s AND user_id=%s",
        (order_db_id, session["user_id"])
    )
    order = cursor.fetchone()
    cursor.execute("SELECT * FROM order_items WHERE order_id=%s", (order_db_id,))
    items = cursor.fetchall()
    cursor.close()
    conn.close()

    if not order:
        flash("Order not found.", "danger")
        return redirect("/user/products")

    return render_template("user/order_success.html", order=order, items=items)


@app.route("/user/my-orders")
def my_orders():
    if not user_logged_in():
        flash("Please login!", "danger")
        return redirect("/user-login")

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT * FROM orders WHERE user_id=%s ORDER BY created_at DESC",
        (session["user_id"],)
    )
    orders = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template("user/my_orders.html", orders=orders)


# =============================================================
# DAY 14: HTML INVOICE -> PDF
# =============================================================
@app.route("/user/download-invoice/<int:order_id>")
def download_invoice(order_id):
    if not user_logged_in():
        flash("Please login!", "danger")
        return redirect("/user-login")

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT * FROM orders WHERE order_id=%s AND user_id=%s",
        (order_id, session["user_id"])
    )
    order = cursor.fetchone()
    cursor.execute("SELECT * FROM order_items WHERE order_id=%s", (order_id,))
    items = cursor.fetchall()
    cursor.close()
    conn.close()

    if not order:
        flash("Order not found.", "danger")
        return redirect("/user/my-orders")

    html = render_template("user/invoice.html", order=order, items=items)
    pdf = generate_pdf(html)
    if not pdf:
        flash("Error generating PDF", "danger")
        return redirect("/user/my-orders")

    response = make_response(pdf.getvalue())
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = f"attachment; filename=invoice_{order_id}.pdf"
    return response

if __name__ == "__main__":
    app.run(debug=True)
