-- Reversa de 018. Deja marketing_calendar_items como estaba en 014 (sus filas se conservan)
-- y borra campañas, bitácora y biblioteca: úsala solo para deshacer un despliegue.
DROP TABLE IF EXISTS marketing_item_assets;
DROP TABLE IF EXISTS marketing_assets;
DROP TABLE IF EXISTS marketing_change_log;

ALTER TABLE marketing_calendar_items
    DROP CONSTRAINT IF EXISTS ck_marketing_calendar_publish_needs_approval,
    DROP CONSTRAINT IF EXISTS ck_marketing_calendar_workflow_status,
    DROP CONSTRAINT IF EXISTS ck_marketing_calendar_content_type;

DROP INDEX IF EXISTS ix_marketing_calendar_workflow;
DROP INDEX IF EXISTS ix_marketing_calendar_campaign;

ALTER TABLE marketing_calendar_items
    DROP COLUMN IF EXISTS campaign_id,
    DROP COLUMN IF EXISTS community_code,
    DROP COLUMN IF EXISTS content_type,
    DROP COLUMN IF EXISTS objective,
    DROP COLUMN IF EXISTS shopify_product_id,
    DROP COLUMN IF EXISTS shopify_variant_ids,
    DROP COLUMN IF EXISTS copy_text,
    DROP COLUMN IF EXISTS recommendation_episode_id,
    DROP COLUMN IF EXISTS workflow_status,
    DROP COLUMN IF EXISTS approved_by,
    DROP COLUMN IF EXISTS approved_at,
    DROP COLUMN IF EXISTS published_at,
    DROP COLUMN IF EXISTS published_ref,
    DROP COLUMN IF EXISTS measured_at,
    DROP COLUMN IF EXISTS result_notes,
    DROP COLUMN IF EXISTS created_by;

DROP TABLE IF EXISTS marketing_campaigns;
