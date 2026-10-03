-- 145_bloat.sql
-- Planted problem P05: a wide JSONB document that is rewritten often, so the table fills with dead row versions (bloat).
--
-- How bloat happens: an UPDATE never changes a row in place. Postgres writes a NEW version of the whole row (here about 1.2 KB,
-- because the JSONB document is stored inline) and leaves the old one behind as a "dead tuple" until VACUUM reclaims the space.
-- Normally autovacuum does that quickly. Here autovacuum is switched OFF for the table, as happens in real systems when
-- someone disables it "temporarily" during a migration, and a nightly "catalog sync" rewrites every product document.
--
-- Result: shop.products keeps about 4 versions of every product on disk, queries read pages full of dead rows, and the
-- size per live row is far above the real row width. tests/test_planted.py (P05) measures that ratio.
--
-- Re-run guard: it does nothing if autovacuum is already disabled on the table (that means this ran before).
-- The refresh also advances products.updated_at (the trigger fires) and adds two keys to every attributes document.

SET ROLE shop_owner;

DO $$
BEGIN
    IF coalesce((SELECT 'autovacuum_enabled=false' = ANY (reloptions) FROM pg_class WHERE oid = 'shop.products'::regclass), false) THEN
        RAISE NOTICE 'P05 already applied (autovacuum is disabled on shop.products); nothing to do';
        RETURN;
    END IF;

    ALTER TABLE shop.products SET (autovacuum_enabled = false);

    FOR i IN 1..3 LOOP
        UPDATE shop.products
           SET attributes = attributes || jsonb_build_object('refresh_round', i, 'refreshed_by', 'catalog_sync');
    END LOOP;
END
$$;
