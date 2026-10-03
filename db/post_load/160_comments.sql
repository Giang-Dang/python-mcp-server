-- 160_comments.sql
-- Column descriptions for the data dictionary (docs/data-dictionary.md is generated from them by `shopdb docs`).
--
-- Why they matter beyond documentation: the MCP server will let a model write SQL against this schema. A model has only names and
-- comments to go on; "channel" or "kind" with no description invites wrong guesses, and a wrong guess in a WHERE clause is a
-- wrong answer or a full table scan.
--
-- Why this is a post_load file and not an edit of db/schema/*.sql: the schema files only run when the data volume is created.
-- Comments are metadata, so this file can be applied to a live database in a second (`shopdb post-load --only 160`) and
-- it is re-runnable: a column that already has a comment (from the schema files) is left alone.
--
-- Every statement here describes what the schema enforces (CHECK constraints, trigger code, seeded value sets), not guesses.

SET ROLE shop_owner;

DO $$
DECLARE
    r record;
BEGIN
    FOR r IN
        SELECT * FROM (VALUES
            -- addresses
            ('addresses', 'address_id',   'Surrogate key.'),
            ('addresses', 'customer_id',  'Owner of the address (customers.customer_id).'),
            ('addresses', 'kind',         'shipping or billing.'),
            ('addresses', 'line1',        'First street line.'),
            ('addresses', 'line2',        'Second street line (apartment, floor); often NULL.'),
            ('addresses', 'city',         'City.'),
            ('addresses', 'region',       'State, province or county; free text.'),
            ('addresses', 'postal_code',  'Postal or ZIP code; free text, formats differ by country.'),
            ('addresses', 'country_code', 'ISO 3166 alpha-2 code (countries.country_code).'),
            ('addresses', 'is_default',   'True for the address pre-selected at checkout.'),
            ('addresses', 'created_at',   'Row creation time.'),
            ('addresses', 'updated_at',   'Last change; maintained by a trigger.'),
            -- audit_log
            ('audit_log', 'audit_id',     'Surrogate key (identity column).'),
            ('audit_log', 'created_at',   'When the change happened; the partition key. Always filter on it to avoid scanning every partition (P03).'),
            ('audit_log', 'tenant_id',    'Tenant of the changed row, taken from its tenant_id column when it has one.'),
            ('audit_log', 'table_name',   'Name of the audited table (for example orders, payments).'),
            ('audit_log', 'record_id',    'Primary key value of the changed row in table_name.'),
            ('audit_log', 'action',       'I = insert, U = update, D = delete.'),
            ('audit_log', 'changed_by',   'Database role that connected (session_user), not the SECURITY DEFINER owner.'),
            ('audit_log', 'old_data',     'Row as JSON before the change (updates and deletes only).'),
            ('audit_log', 'new_data',     'Row as JSON after the change (inserts and updates only).'),
            -- carts
            ('carts', 'cart_id',          'Surrogate key.'),
            ('carts', 'customer_id',      'Owner of the cart.'),
            ('carts', 'status',           'open, converted (became an order) or abandoned.'),
            ('carts', 'created_at',       'Row creation time.'),
            ('carts', 'updated_at',       'Last change; maintained by a trigger.'),
            ('carts', 'expires_at',       'Expiry time of the cart.'),
            -- categories
            ('categories', 'category_id', 'Surrogate key. Ids 1-20 are top-level categories; products belong to leaf categories 21-200.'),
            ('categories', 'parent_id',   'Parent category; NULL for top-level categories.'),
            ('categories', 'name',        'Display name.'),
            ('categories', 'slug',        'URL-safe unique name.'),
            -- countries, currencies
            ('countries', 'country_code', 'ISO 3166 alpha-2 code; the primary key.'),
            ('countries', 'name',         'English name.'),
            ('countries', 'region',       'Continent-level grouping (Africa, Asia, Europe, North America, Oceania, South America).'),
            ('currencies', 'currency_code', 'ISO 4217 alpha-3 code; the primary key.'),
            ('currencies', 'name',        'English name.'),
            ('currencies', 'minor_units', 'Number of decimal places of the currency (2 for USD, 0 for JPY).'),
            -- customers
            ('customers', 'customer_id',  'Surrogate key.'),
            ('customers', 'tenant_id',    'Tenant that owns the customer. Row-level security filters on it using app.tenant_id.'),
            ('customers', 'email',        'Login and contact email; unique per tenant (not globally), stored lower case.'),
            ('customers', 'first_name',   'Given name.'),
            ('customers', 'last_name',    'Family name.'),
            ('customers', 'phone',        'Phone number as typed; free text; often NULL.'),
            ('customers', 'marketing_opt_in', 'True if the customer agreed to marketing email.'),
            ('customers', 'created_at',   'Row creation time.'),
            ('customers', 'updated_at',   'Last change; maintained by a trigger.'),
            -- employees
            ('employees', 'employee_id',  'Surrogate key.'),
            ('employees', 'warehouse_id', 'Warehouse the employee works in; NULL for non-warehouse staff.'),
            ('employees', 'manager_id',   'Employee who manages this one (self reference); NULL at the top.'),
            ('employees', 'full_name',    'Display name.'),
            ('employees', 'email',        'Work email.'),
            ('employees', 'role',         'Job title, free text (Picker, Packer, Buyer, Customer Support, ...).'),
            ('employees', 'hired_at',     'Hire date.'),
            ('employees', 'updated_at',   'Last change; maintained by a trigger.'),
            -- inventory
            ('inventory', 'warehouse_id', 'Warehouse holding the stock. Together with variant_id this is the primary key.'),
            ('inventory', 'variant_id',   'Product variant stocked. Inventory is shared by all tenants.'),
            ('inventory', 'quantity_on_hand', 'Units physically in the warehouse; never negative.'),
            ('inventory', 'quantity_reserved', 'Units promised to open orders; never negative. Available stock = on hand - reserved.'),
            ('inventory', 'reorder_point', 'Stock level at which the variant should be reordered.'),
            ('inventory', 'updated_at',   'Last change; maintained by a trigger.'),
            -- inventory_movements
            ('inventory_movements', 'movement_id',   'Surrogate key.'),
            ('inventory_movements', 'warehouse_id',  'Warehouse the stock moved in or out of.'),
            ('inventory_movements', 'variant_id',    'Product variant that moved.'),
            ('inventory_movements', 'movement_type', 'receipt, sale, adjustment, return or transfer.'),
            ('inventory_movements', 'reference_type', 'What caused the movement: order, purchase_order or transfer; NULL when there is no source document.'),
            ('inventory_movements', 'reference_id',  'Id of the referenced row (an order_id when reference_type is order).'),
            ('inventory_movements', 'created_at',    'When the movement was recorded.'),
            -- invoices
            ('invoices', 'invoice_id',     'Surrogate key.'),
            ('invoices', 'order_id',       'Order being invoiced; unique, so an order has at most one invoice.'),
            ('invoices', 'invoice_number', 'Human-readable unique number, format INV-nnnnnnnnn (4 letters plus 9 digits).'),
            ('invoices', 'status',         'draft, issued, paid or void.'),
            ('invoices', 'total_amount',   'Amount due, in the currency of the order.'),
            ('invoices', 'issued_at',      'When the invoice was issued.'),
            ('invoices', 'due_at',         'Payment due date.'),
            -- order_items
            ('order_items', 'order_item_id', 'Surrogate key.'),
            ('order_items', 'order_id',    'Order the line belongs to. No row-level security on this table (known gap): filter through orders.'),
            ('order_items', 'product_id',  'Product ordered (denormalized from the variant). Has no index (planted problem P02).'),
            ('order_items', 'variant_id',  'Variant ordered.'),
            ('order_items', 'quantity',    'Units ordered; greater than zero.'),
            ('order_items', 'unit_price',  'Price of one unit at order time (base price + variant delta), not a live price.'),
            ('order_items', 'discount',    'Discount on the line in currency units.'),
            ('order_items', 'line_total',  'Total for the line after discount.'),
            ('order_items', 'created_at',  'Row creation time.'),
            -- order_statuses
            ('order_statuses', 'status_id', 'Primary key; ids are stable and referenced by orders.status_id.'),
            ('order_statuses', 'code',     'Machine name: pending, paid, processing, shipped, delivered, cancelled, refunded, on_hold.'),
            ('order_statuses', 'description', 'Human-readable explanation of the status.'),
            -- orders
            ('orders', 'order_id',        'Surrogate key.'),
            ('orders', 'tenant_id',       'Tenant that owns the order. Row-level security filters on it using app.tenant_id.'),
            ('orders', 'customer_id',     'Customer who placed the order. Skewed: about 1 percent of customers own about 30 percent of orders (P01).'),
            ('orders', 'status_id',       'Current status (order_statuses.status_id); transitions are validated by a trigger.'),
            ('orders', 'order_number',    'Human-readable unique number, format ORD-tt-nnnnnnnn (tenant and order id).'),
            ('orders', 'channel',         'Where the order came from: web, mobile, store or api.'),
            ('orders', 'currency_code',   'Currency of every amount on the order and its lines.'),
            ('orders', 'subtotal',        'Sum of the line totals; recomputed by a statement-level trigger when lines are inserted.'),
            ('orders', 'tax_amount',      'Tax on the subtotal.'),
            ('orders', 'shipping_amount', 'Shipping cost.'),
            ('orders', 'discount_amount', 'Order-level discount.'),
            ('orders', 'shipping_address_id', 'Delivery address (addresses.address_id).'),
            ('orders', 'billing_address_id',  'Billing address (addresses.address_id).'),
            ('orders', 'notes',           'Free-text note from the customer or staff; often NULL.'),
            ('orders', 'created_at',      'Row creation time (the order time itself is placed_at).'),
            ('orders', 'updated_at',      'Last change; maintained by a trigger.'),
            ('orders', 'deleted_at',      'Soft delete marker; NULL means active. Partial indexes for it do not exist (P06).'),
            -- payment_methods
            ('payment_methods', 'payment_method_id', 'Surrogate key.'),
            ('payment_methods', 'code',   'Machine name of the method.'),
            ('payment_methods', 'name',   'Display name.'),
            ('payment_methods', 'is_active', 'False if the method can no longer be chosen at checkout.'),
            -- payments
            ('payments', 'payment_id',    'Surrogate key.'),
            ('payments', 'tenant_id',     'Tenant that owns the payment. Row-level security filters on it using app.tenant_id.'),
            ('payments', 'order_id',      'Order being paid.'),
            ('payments', 'payment_method_id', 'How the customer paid.'),
            ('payments', 'amount',        'Amount in currency_code; zero or more.'),
            ('payments', 'currency_code', 'Currency of the payment.'),
            ('payments', 'status',        'pending, authorized, captured, failed or refunded.'),
            ('payments', 'provider_ref',  'Id of the payment at the external provider, for example pi_293aeb3eca0aa59f.'),
            ('payments', 'paid_at',       'When the payment was captured; NULL if it never was.'),
            ('payments', 'created_at',    'Row creation time.'),
            ('payments', 'updated_at',    'Last change; maintained by a trigger.'),
            -- price_history
            ('price_history', 'price_history_id', 'Surrogate key.'),
            ('price_history', 'product_id', 'Product whose base price changed.'),
            ('price_history', 'old_price', 'Base price before the change.'),
            ('price_history', 'new_price', 'Base price after the change.'),
            ('price_history', 'changed_at', 'When the price changed.'),
            ('price_history', 'changed_by', 'Who or what changed it (a person, pricing_bot or supplier_feed).'),
            -- product_variants
            ('product_variants', 'variant_id', 'Surrogate key; the unit that is stocked and ordered.'),
            ('product_variants', 'product_id', 'Parent product.'),
            ('product_variants', 'sku',       'Stock keeping unit, unique, format SKU-nnnnnnn-n.'),
            ('product_variants', 'size',      'Size label (S, M, L, ...).'),
            ('product_variants', 'color',     'Color name.'),
            ('product_variants', 'weight_grams', 'Shipping weight in grams.'),
            ('product_variants', 'price_delta', 'Amount added to the product base price for this variant.'),
            ('product_variants', 'barcode',   'Barcode digits (distinct in the seeded data; not enforced by a constraint).'),
            ('product_variants', 'is_active', 'False if the variant can no longer be ordered.'),
            ('product_variants', 'created_at', 'Row creation time.'),
            ('product_variants', 'updated_at', 'Last change; maintained by a trigger.'),
            -- products
            ('products', 'product_id',    'Surrogate key.'),
            ('products', 'supplier_id',   'Supplier of the product.'),
            ('products', 'category_id',   'Leaf category (categories 21-200).'),
            ('products', 'sku',           'Product-level stock keeping unit, unique.'),
            ('products', 'name',          'Display name.'),
            ('products', 'description',   'Long text. Searching it with ILIKE has no trigram index (planted problem P04).'),
            ('products', 'brand',         'Brand name; free text.'),
            ('products', 'base_price',    'Price before the variant price_delta, in currency_code; zero or more.'),
            ('products', 'currency_code', 'Currency of base_price.'),
            ('products', 'is_active',     'False if the product is hidden from the catalog.'),
            ('products', 'created_at',    'Row creation time.'),
            ('products', 'updated_at',    'Last change; maintained by a trigger.'),
            ('products', 'deleted_at',    'Soft delete marker; NULL means active. About 4 percent of products are soft deleted (P06).'),
            -- refunds
            ('refunds', 'refund_id',      'Surrogate key.'),
            ('refunds', 'order_id',       'Order being refunded.'),
            ('refunds', 'payment_id',     'Payment the money returns to.'),
            ('refunds', 'amount',         'Amount to refund; greater than zero.'),
            ('refunds', 'reason',         'Free-text reason.'),
            ('refunds', 'status',         'requested, approved, processed or rejected.'),
            ('refunds', 'created_at',     'Row creation time.'),
            -- shipment_items
            ('shipment_items', 'shipment_item_id', 'Surrogate key.'),
            ('shipment_items', 'shipment_id',      'Shipment that carries the line.'),
            ('shipment_items', 'order_item_id',    'Order line being shipped.'),
            ('shipment_items', 'quantity',         'Units of the line in this shipment; greater than zero. A line can be split across shipments.'),
            -- shipments
            ('shipments', 'shipment_id',  'Surrogate key.'),
            ('shipments', 'order_id',     'Order being shipped.'),
            ('shipments', 'warehouse_id', 'Warehouse it ships from.'),
            ('shipments', 'carrier',      'Carrier name: DHL, DPD, FedEx, Royal Mail, UPS or USPS.'),
            ('shipments', 'tracking_number', 'Carrier tracking number.'),
            ('shipments', 'status',       'pending, in_transit, delivered or returned. Updating it fires the deliberately slow carrier SLA trigger (P13).'),
            ('shipments', 'shipped_at',   'When the carrier took the parcel.'),
            ('shipments', 'delivered_at', 'When it was delivered; NULL while still in transit.'),
            ('shipments', 'created_at',   'Row creation time.'),
            ('shipments', 'updated_at',   'Last change; maintained by a trigger.'),
            -- suppliers
            ('suppliers', 'supplier_id',  'Surrogate key.'),
            ('suppliers', 'name',         'Company name.'),
            ('suppliers', 'country_code', 'Country of the supplier.'),
            ('suppliers', 'contact_email', 'Purchasing contact.'),
            ('suppliers', 'lead_time_days', 'Typical days from purchase order to delivery.'),
            ('suppliers', 'rating',       'Quality rating from 0 to 5.'),
            ('suppliers', 'updated_at',   'Last change; maintained by a trigger.'),
            -- tenants
            ('tenants', 'tenant_id',      'Surrogate key. Tenant 1 owns about 40 percent of customers and is the default tenant of the mcp_* roles.'),
            ('tenants', 'name',           'Company name.'),
            ('tenants', 'plan',           'free, standard or enterprise.'),
            ('tenants', 'created_at',     'Row creation time.'),
            -- warehouses
            ('warehouses', 'warehouse_id', 'Surrogate key.'),
            ('warehouses', 'name',        'Display name.'),
            ('warehouses', 'country_code', 'Country where the warehouse is.'),
            ('warehouses', 'city',        'City where the warehouse is.'),
            ('warehouses', 'capacity_units', 'Storage capacity in units; greater than zero.')
        ) AS t(table_name, column_name, description)
    LOOP
        -- Leave an existing comment (written in db/schema) untouched; fail loudly if a column name is wrong.
        IF col_description(format('shop.%I', r.table_name)::regclass,
                           (SELECT attnum FROM pg_attribute
                             WHERE attrelid = format('shop.%I', r.table_name)::regclass
                               AND attname = r.column_name AND NOT attisdropped)) IS NULL THEN
            EXECUTE format('COMMENT ON COLUMN shop.%I.%I IS %L', r.table_name, r.column_name, r.description);
        END IF;
    END LOOP;
END
$$;
