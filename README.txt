SMARTCART - DAYS 1 TO 14

This project keeps the existing Days 1-10 functionality and adds Days 11-14.
No CSS or style attributes were added.

DAY 11
- Session-based cart
- Add to cart
- AJAX add-to-cart from product pages
- Cart count
- Increase quantity
- Decrease quantity
- Remove item
- Grand total
- User stays on the same page for AJAX add-to-cart

DAY 12
- Razorpay Python package
- Razorpay client initialization
- Create Razorpay order from cart total
- Payment page with Razorpay Checkout.js
- Temporary payment-success compatibility route

DAY 13
- Server-side Razorpay signature verification
- orders table
- order_items table
- Atomic order + order item database transaction
- Clear cart after successful order
- Order success page
- My Orders page

DAY 14
- HTML invoice
- xhtml2pdf PDF generation
- Download invoice for a user's own order
- Invoice link from order success and My Orders

SETUP
1. Open the E-C folder in VS Code.
2. Make sure MySQL is running.
3. Run database/schema.sql in MySQL Workbench. It creates missing tables including orders and order_items.
4. Check config.py for MySQL credentials.
5. Add your Razorpay TEST keys to config.py:
   RAZORPAY_KEY_ID = "your_test_key_id"
   RAZORPAY_KEY_SECRET = "your_test_key_secret"
6. Install dependencies:
   python -m venv venv
   venv\Scripts\python.exe -m pip install -r requirements.txt
7. Run:
   venv\Scripts\python.exe app.py
8. Open:
   http://127.0.0.1:5000/

IMPORTANT
- Razorpay keys are required for the payment module. Use TEST mode keys for college/demo testing.
- Do not share your Razorpay secret key or Gmail App Password.
- User registration remains OTP mandatory: the user is inserted into the database only after successful OTP verification.
- The cart is stored in Flask session as requested by Day 11.
\nSHIPPING ADDRESS UPDATE\n1. For an existing database, run database/add_shipping_address.sql in MySQL Workbench.\n2. For a new database, schema.sql includes the shipping columns.\n3. User enters a required shipping address before proceeding to Razorpay. The address is saved with the order and printed on the PDF invoice.\n

============================================================
SMARTCART - SQLITE VERSION
============================================================

This version has been converted from MySQL to SQLite.

1. Open a terminal in the SmartCart folder.
2. Create/activate your virtual environment if needed.
3. Install dependencies:
   pip install -r requirements.txt
4. Initialize the database (optional because app.py also initializes it automatically):
   python database/init_db.py
5. Run:
   python app.py
6. Open:
   http://127.0.0.1:5000

The SQLite database is:
   database/smartcart.db

No MySQL server, MySQL Workbench, username, or password is required.

The existing Flask routes, templates, product uploads, cart, orders, invoice generation,
email OTP flow, and Razorpay integration have been kept intact. Only the database layer
and database schema were changed from MySQL to SQLite.
