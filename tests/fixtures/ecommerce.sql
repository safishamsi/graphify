-- E-commerce schema fixture for graphify SQL extractor tests

-- Core entity tables
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE products (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    price DECIMAL(10,2) NOT NULL
);

CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(id),
    status VARCHAR(50) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT NOW()
);

-- NOTE: join table, no surrogate key by design
CREATE TABLE order_items (
    order_id INT REFERENCES orders(id),
    product_id INT REFERENCES products(id),
    quantity INT DEFAULT 1,
    unit_price DECIMAL(10,2)
);

-- Aggregated view used by the reporting dashboard
CREATE VIEW revenue_by_user AS
    SELECT u.id, u.email, SUM(o.id) AS order_count
    FROM users u
    JOIN orders o ON u.id = o.user_id
    GROUP BY u.id, u.email;

-- Performance indexes
CREATE INDEX idx_orders_user    ON orders(user_id);
CREATE INDEX idx_items_order    ON order_items(order_id);
CREATE INDEX idx_items_product  ON order_items(product_id);