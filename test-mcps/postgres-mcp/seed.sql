-- LangSight test database seed
-- E-commerce schema with sample data for dogfooding MCP health checks and security scans

-- ---------------------------------------------------------------------------
-- Schema
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS customers (
    customer_id   SERIAL PRIMARY KEY,
    name          TEXT        NOT NULL,
    email         TEXT        NOT NULL UNIQUE,
    tier          TEXT        NOT NULL CHECK (tier IN ('standard', 'premium', 'enterprise')),
    country       TEXT        NOT NULL DEFAULT 'DE',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS products (
    product_id    SERIAL PRIMARY KEY,
    name          TEXT           NOT NULL,
    category      TEXT           NOT NULL,
    price_usd     NUMERIC(10, 2) NOT NULL CHECK (price_usd >= 0),
    active        BOOLEAN        NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS orders (
    order_id      SERIAL PRIMARY KEY,
    customer_id   INTEGER        NOT NULL REFERENCES customers(customer_id),
    status        TEXT           NOT NULL CHECK (status IN ('pending', 'processing', 'delivered', 'cancelled', 'refunded')),
    total_usd     NUMERIC(10, 2) NOT NULL CHECK (total_usd >= 0),
    created_at    TIMESTAMPTZ    NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS order_items (
    item_id         SERIAL PRIMARY KEY,
    order_id        INTEGER        NOT NULL REFERENCES orders(order_id),
    product_id      INTEGER        NOT NULL REFERENCES products(product_id),
    quantity        INTEGER        NOT NULL CHECK (quantity > 0),
    unit_price_usd  NUMERIC(10, 2) NOT NULL CHECK (unit_price_usd >= 0)
);

CREATE TABLE IF NOT EXISTS agent_conversations (
    conversation_id  SERIAL PRIMARY KEY,
    session_id       TEXT        NOT NULL,
    agent_name       TEXT        NOT NULL,
    status           TEXT        NOT NULL CHECK (status IN ('success', 'failed', 'timeout', 'in_progress')),
    tool_calls_count INTEGER     NOT NULL DEFAULT 0,
    error_message    TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- Seed data
-- ---------------------------------------------------------------------------

INSERT INTO customers (name, email, tier, country) VALUES
    ('Alice Müller',     'alice@acme-corp.de',       'enterprise', 'DE'),
    ('Bob Schmidt',      'bob@startup.io',            'premium',    'DE'),
    ('Carol Bauer',      'carol@techfirm.com',        'standard',   'AT'),
    ('David Klein',      'david@enterprise.co.uk',    'enterprise', 'GB'),
    ('Eva Fischer',      'eva@digitalagency.nl',      'premium',    'NL'),
    ('Frank Weber',      'frank@freelance.de',        'standard',   'DE'),
    ('Grace Hoffmann',   'grace@bigcorp.ch',          'enterprise', 'CH'),
    ('Hans Schulz',      'hans@startup.berlin',       'standard',   'DE'),
    ('Iris Koch',        'iris@scaleup.io',           'premium',    'FR'),
    ('Jan Richter',      'jan@saascompany.eu',        'standard',   'PL')
ON CONFLICT (email) DO NOTHING;

INSERT INTO products (name, category, price_usd, active) VALUES
    ('Starter Plan',            'subscription',   29.00,  TRUE),
    ('Growth Plan',             'subscription',   99.00,  TRUE),
    ('Enterprise Plan',         'subscription',  499.00,  TRUE),
    ('Data Credits — 100k',     'credits',        49.00,  TRUE),
    ('Data Credits — 500k',     'credits',       199.00,  TRUE),
    ('Data Credits — 1M',       'credits',       349.00,  TRUE),
    ('Priority Support',        'support',        79.00,  TRUE),
    ('Enterprise Support SLA',  'support',       299.00,  TRUE),
    ('API Add-on',              'addon',          49.00,  TRUE),
    ('Custom Connector',        'addon',         199.00,  FALSE)
ON CONFLICT DO NOTHING;

INSERT INTO orders (customer_id, status, total_usd, created_at) VALUES
    (1, 'delivered',  499.00, NOW() - INTERVAL '30 days'),
    (1, 'delivered',  299.00, NOW() - INTERVAL '15 days'),
    (2, 'delivered',   99.00, NOW() - INTERVAL '20 days'),
    (2, 'processing',  49.00, NOW() - INTERVAL '1 day'),
    (3, 'delivered',   29.00, NOW() - INTERVAL '45 days'),
    (4, 'delivered',  798.00, NOW() - INTERVAL '10 days'),
    (5, 'cancelled',   99.00, NOW() - INTERVAL '5 days'),
    (6, 'delivered',   29.00, NOW() - INTERVAL '60 days'),
    (7, 'delivered', 1196.00, NOW() - INTERVAL '7 days'),
    (8, 'pending',     49.00, NOW() - INTERVAL '2 hours')
ON CONFLICT DO NOTHING;

INSERT INTO order_items (order_id, product_id, quantity, unit_price_usd) VALUES
    -- Order 1: enterprise plan
    (1, 3, 1, 499.00),
    -- Order 2: enterprise support
    (2, 8, 1, 299.00),
    -- Order 3: growth plan
    (3, 2, 1, 99.00),
    -- Order 4: data credits 100k
    (4, 4, 1, 49.00),
    -- Order 5: starter plan
    (5, 1, 1, 29.00),
    -- Order 6: enterprise plan + enterprise support
    (6, 3, 1, 499.00),
    (6, 8, 1, 299.00),
    -- Order 7: growth plan (cancelled)
    (7, 2, 1, 99.00),
    -- Order 8: starter plan
    (8, 1, 1, 29.00),
    -- Order 9: enterprise plan x2 + priority support
    (9, 3, 2, 499.00),
    (9, 7, 1,  79.00),
    (9, 8, 1, 119.00),
    -- Order 10: data credits 100k
    (10, 4, 1, 49.00)
ON CONFLICT DO NOTHING;

INSERT INTO agent_conversations (session_id, agent_name, status, tool_calls_count, error_message, created_at) VALUES
    ('sess_abc123', 'customer-support-agent', 'success',     4, NULL,                                          NOW() - INTERVAL '2 hours'),
    ('sess_def456', 'data-analyst-agent',     'success',     7, NULL,                                          NOW() - INTERVAL '1 hour'),
    ('sess_ghi789', 'billing-agent',          'failed',      2, 'postgres-mcp: timeout after 5000ms',          NOW() - INTERVAL '30 minutes'),
    ('sess_jkl012', 'customer-support-agent', 'timeout',     1, 'Tool call exceeded max_duration of 10s',      NOW() - INTERVAL '15 minutes'),
    ('sess_mno345', 'data-analyst-agent',     'in_progress', 3, NULL,                                          NOW())
ON CONFLICT DO NOTHING;
