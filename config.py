import os
SECRET_KEY = "your_secret_key_here"

# SQLite database file. It is created automatically on first run.
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "database", "smartcart.db")

MAIL_SERVER = "smtp.gmail.com"
MAIL_PORT = 587
MAIL_USE_TLS = True
MAIL_USERNAME = "bonalaadarsh@gmail.com"
MAIL_PASSWORD = "jyoa tkny brii hkpf"

# Razorpay test keys
RAZORPAY_KEY_ID = "rzp_test_TcB8Ox8EYR2f8Z"
RAZORPAY_KEY_SECRET = "unpt14YfKkogu887IJui5bIR"
