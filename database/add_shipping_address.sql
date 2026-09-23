USE smartcart_db;

-- Run once on an existing database. If a column already exists, skip its ALTER.
ALTER TABLE orders ADD COLUMN shipping_name VARCHAR(150) NULL;
ALTER TABLE orders ADD COLUMN shipping_phone VARCHAR(30) NULL;
ALTER TABLE orders ADD COLUMN shipping_address TEXT NULL;
ALTER TABLE orders ADD COLUMN shipping_city VARCHAR(100) NULL;
ALTER TABLE orders ADD COLUMN shipping_state VARCHAR(100) NULL;
ALTER TABLE orders ADD COLUMN shipping_postal_code VARCHAR(20) NULL;
ALTER TABLE orders ADD COLUMN shipping_country VARCHAR(100) NULL;
