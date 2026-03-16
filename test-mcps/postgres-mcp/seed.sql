-- LangSight Test Database — Sample Data
-- Simulates a simple e-commerce schema for realistic query testing

-- Customers
CREATE TABLE IF NOT EXISTS customers (
    customer_id     SERIAL PRIMARY KEY,
    email           VARCHAR(255) UNIQUE NOT NULL,
    first_name      VARCHAR(100) NOT NULL,
    last_name       VARCHAR(100) NOT NULL,
    country         VARCHAR(100) NOT NULL,
    tier            VARCHAR(20) NOT NULL DEFAULT 'standard', -- standard, premium, enterprise
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Products
CREATE TABLE IF NOT EXISTS products (
    product_id      SERIAL PRIMARY KEY,
    name            VARCHAR(255) NOT NULL,
    category        VARCHAR(100) NOT NULL,
    price_usd       NUMERIC(10, 2) NOT NULL,
    stock_quantity  INTEGER NOT NULL DEFAULT 0,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Orders
CREATE TABLE IF NOT EXISTS orders (
    order_id        SERIAL PRIMARY KEY,
    customer_id     INTEGER NOT NULL REFERENCES customers(customer_id),
    status          VARCHAR(50) NOT NULL DEFAULT 'pending', -- pending, confirmed, shipped, delivered, cancelled
    total_usd       NUMERIC(10, 2) NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Order Items
CREATE TABLE IF NOT EXISTS order_items (
    item_id         SERIAL PRIMARY KEY,
    order_id        INTEGER NOT NULL REFERENCES orders(order_id),
    product_id      INTEGER NOT NULL REFERENCES products(product_id),
    quantity        INTEGER NOT NULL,
    unit_price_usd  NUMERIC(10, 2) NOT NULL
);

-- Agent Conversations (useful for LangSight dogfooding)
CREATE TABLE IF NOT EXISTS agent_conversations (
    conversation_id VARCHAR(100) PRIMARY KEY,
    agent_name      VARCHAR(100) NOT NULL,
    user_query      TEXT NOT NULL,
    agent_response  TEXT,
    status          VARCHAR(20) NOT NULL DEFAULT 'completed', -- completed, failed, timeout
    duration_ms     INTEGER,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Seed Customers
INSERT INTO customers (email, first_name, last_name, country, tier) VALUES
('alice@acmecorp.com',   'Alice',   'Johnson',  'USA',     'enterprise'),
('bob@techco.io',        'Bob',     'Smith',     'UK',      'premium'),
('carol@startup.de',     'Carol',   'Müller',    'Germany', 'standard'),
('david@bigcorp.com',    'David',   'Lee',       'USA',     'enterprise'),
('eva@agency.fr',        'Eva',     'Dupont',    'France',  'premium'),
('frank@indie.io',       'Frank',   'Brown',     'Canada',  'standard'),
('grace@enterprise.jp',  'Grace',   'Tanaka',    'Japan',   'enterprise'),
('henry@consulting.au',  'Henry',   'Wilson',    'Australia','premium'),
('iris@startup.in',      'Iris',    'Patel',     'India',   'standard'),
('james@corp.sg',        'James',   'Ng',        'Singapore','premium')
ON CONFLICT DO NOTHING;

-- Seed Products
INSERT INTO products (name, category, price_usd, stock_quantity) VALUES
('LangSight Pro License',      'Software',    299.00, 999),
('API Credits 1M',             'Credits',      49.00, 9999),
('Enterprise Support Plan',    'Support',    1299.00,  100),
('MCP Monitoring Add-on',      'Software',    149.00,  500),
('Security Scanner Pro',       'Software',    199.00,  500),
('Starter Pack',               'Bundle',       99.00,  999),
('Team License (10 seats)',    'Software',    799.00,  200),
('Training Workshop',          'Services',    499.00,   50),
('Custom Integration',         'Services',   2499.00,   20),
('Data Retention 1yr Add-on',  'Add-on',       79.00,  999)
ON CONFLICT DO NOTHING;

-- Seed Orders
INSERT INTO orders (customer_id, status, total_usd, created_at) VALUES
(1, 'delivered',  299.00, NOW() - INTERVAL '30 days'),
(2, 'delivered',   49.00, NOW() - INTERVAL '25 days'),
(3, 'shipped',     99.00, NOW() - INTERVAL '10 days'),
(4, 'delivered', 1299.00, NOW() - INTERVAL '20 days'),
(5, 'confirmed',  149.00, NOW() - INTERVAL '3 days'),
(6, 'pending',     49.00, NOW() - INTERVAL '1 day'),
(7, 'delivered',  799.00, NOW() - INTERVAL '15 days'),
(8, 'cancelled',  499.00, NOW() - INTERVAL '12 days'),
(1, 'delivered',  199.00, NOW() - INTERVAL '5 days'),
(4, 'shipped',   2499.00, NOW() - INTERVAL '7 days')
ON CONFLICT DO NOTHING;

-- Seed Order Items
INSERT INTO order_items (order_id, product_id, quantity, unit_price_usd) VALUES
(1, 1, 1, 299.00),
(2, 2, 1,  49.00),
(3, 6, 1,  99.00),
(4, 3, 1, 1299.00),
(5, 4, 1, 149.00),
(6, 2, 1,  49.00),
(7, 7, 1, 799.00),
(8, 8, 1, 499.00),
(9, 5, 1, 199.00),
(10, 9, 1, 2499.00)
ON CONFLICT DO NOTHING;

-- Seed Agent Conversations
INSERT INTO agent_conversations (conversation_id, agent_name, user_query, agent_response, status, duration_ms) VALUES
('conv-001', 'customer-support-bot', 'What is my refund policy?',       'Your refund window is 14 days.',  'completed', 1240),
('conv-002', 'customer-support-bot', 'How do I cancel my subscription?', 'You can cancel from Settings.',   'completed', 980),
('conv-003', 'data-analyst-agent',   'Show me top customers by revenue', NULL,                              'failed',    5000),
('conv-004', 'customer-support-bot', 'What are enterprise pricing tiers?','Enterprise starts at $1,299/yr.','completed', 1100),
('conv-005', 'data-analyst-agent',   'Monthly revenue trend',            'Revenue up 12% MoM.',             'completed', 2300)
ON CONFLICT DO NOTHING;
