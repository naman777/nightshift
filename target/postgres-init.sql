CREATE DATABASE nightshift;
\c orders
CREATE TABLE orders (id SERIAL PRIMARY KEY, customer_id INT NOT NULL, status TEXT NOT NULL DEFAULT 'paid', created_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE INDEX orders_customer_idx ON orders (customer_id);
CREATE TABLE line_items (id SERIAL PRIMARY KEY, order_id INT NOT NULL REFERENCES orders(id), sku TEXT NOT NULL);
CREATE INDEX line_items_order_idx ON line_items (order_id);
-- customers 1..150 have orders; 151..200 have none (empty results exercise the nil_deref / index-out-of-range bugs)
INSERT INTO orders (customer_id) SELECT (g % 150) + 1 FROM generate_series(1, 3000) g;
INSERT INTO line_items (order_id, sku) SELECT o.id, 'sku-' || (o.id % 40) FROM orders o, generate_series(1, 3);
