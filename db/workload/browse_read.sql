-- browse_read.sql: a read-only mix that looks like a storefront / back-office, run as mcp_reader (tenant 1 via RLS).
-- Categories 21-200 are the leaves that hold products (1-20 are parent nodes and have none).
-- Weights: 45% customer order history, 20% order detail, 15% category listing, 10% low-stock report, 10% product text search.
-- The customer id is Zipf-skewed (a few customers are asked about far more often), which is how real traffic behaves
-- and which makes the P01 skew visible: hot customers have 100+ orders, ordinary ones have a handful.
-- It exercises P01 (skew) and P04 (the ILIKE search has no trigram index). It deliberately avoids unbounded queries (P09).
\set pick random(1, 100)
\set cust random_zipfian(1, 1000000, 1.1)
\set ord random_zipfian(1, 5000000, 1.05)
\set cat random(21, 200)
\set word_i random(1, 5)
\if :pick <= 45
    SELECT order_id, status_id, total_amount, placed_at FROM shop.orders
     WHERE customer_id = :cust ORDER BY placed_at DESC LIMIT 20;
\elif :pick <= 65
    SELECT o.order_id, o.total_amount, i.product_id, i.quantity, i.line_total
      FROM shop.orders o JOIN shop.order_items i ON i.order_id = o.order_id
     WHERE o.order_id = :ord;
\elif :pick <= 80
    SELECT product_id, name, base_price FROM shop.products
     WHERE category_id = :cat AND deleted_at IS NULL ORDER BY product_id LIMIT 50;
\elif :pick <= 90
    SELECT * FROM shop.low_stock_items(10, 20);
\else
    SELECT product_id, name FROM shop.products
     WHERE description ILIKE (ARRAY['%wool%', '%steel%', '%cotton%', '%ceramic%', '%oak%'])[:word_i] LIMIT 20;
\endif
