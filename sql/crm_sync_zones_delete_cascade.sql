-- Fix: crm_sync_zones ignoraba sincronizar.accion y siempre hacia upsert,
-- por lo que un delete del CRM nunca borraba crm_delivery_zones,
-- crm_zone_localities ni localities.
--
-- Ahora, cuando accion = 'delete':
--   - borra el link en crm_zone_localities
--   - borra la fila en crm_delivery_zones
--   - borra la locality asociada SOLO si no queda referenciada por
--     otra zona (crm_zone_localities), por product_prices o por
--     locality_catalogs
--
-- El flujo de create/update queda igual que antes.

CREATE OR REPLACE FUNCTION public.crm_sync_zones(payload jsonb)
 RETURNS void
 LANGUAGE plpgsql
AS $function$
DECLARE
  v_action text;
  v_ts timestamptz;
  v_filters jsonb;

  d jsonb;
  z_id int;
  z_name text;

  mapped_locality_id uuid;
  new_locality_id uuid;

  surface_text text;
  surface_parsed jsonb;
BEGIN
  v_action := NULLIF(payload->'sincronizar'->>'accion','');
  v_ts := crm_to_timestamptz(payload->'sincronizar'->>'timestamp');
  v_filters := payload->'filtros';

  FOR d IN
    SELECT * FROM jsonb_array_elements(COALESCE(payload->'datos','[]'::jsonb))
  LOOP
    z_id := crm_to_int(d->>'id');
    IF z_id IS NULL THEN
      CONTINUE;
    END IF;

    z_name := d->>'zona';

    IF v_action = 'delete' THEN
      SELECT czl.locality_id
        INTO mapped_locality_id
      FROM crm_zone_localities czl
      WHERE czl.crm_zone_id = z_id;

      DELETE FROM crm_zone_localities WHERE crm_zone_id = z_id;
      DELETE FROM crm_delivery_zones WHERE crm_zone_id = z_id;

      IF mapped_locality_id IS NOT NULL THEN
        IF NOT EXISTS (SELECT 1 FROM crm_zone_localities WHERE locality_id = mapped_locality_id)
           AND NOT EXISTS (SELECT 1 FROM product_prices WHERE locality_id = mapped_locality_id)
           AND NOT EXISTS (SELECT 1 FROM locality_catalogs WHERE locality_id = mapped_locality_id)
        THEN
          DELETE FROM localities WHERE id = mapped_locality_id;
        END IF;
      END IF;

      INSERT INTO crm_sync_logs(entity_type, crm_entity_id, action, synced_at, filters, payload)
      VALUES (
        'zone',
        z_id,
        COALESCE(v_action,'sync'),
        COALESCE(v_ts, now()),
        v_filters,
        payload
      );

      CONTINUE;
    END IF;

    surface_text := d->>'superficie';
    surface_parsed := crm_try_parse_jsonb(surface_text);

    -- upsert zona
    INSERT INTO crm_delivery_zones (
      crm_zone_id,
      name,
      notice_days,
      public_html,
      private_html,
      surface_geojson,
      surface_raw,
      crm_created_at,
      crm_updated_at,
      crm_deleted_at,
      last_sync_action,
      last_sync_at,
      raw
    )
    VALUES (
      z_id,
      z_name,
      crm_to_int(d->>'dias_aviso'),
      d->>'public_txt',
      d->>'private_txt',
      surface_parsed,
      surface_text,
      crm_to_timestamptz(d->>'created_at'),
      crm_to_timestamptz(d->>'updated_at'),
      crm_to_timestamptz(d->>'deleted_at'),
      v_action,
      v_ts,
      jsonb_build_object(
        'item', d,
        'meta', jsonb_build_object('filtros', v_filters, 'sincronizar', payload->'sincronizar')
      )
    )
    ON CONFLICT (crm_zone_id) DO UPDATE SET
      name = EXCLUDED.name,
      notice_days = EXCLUDED.notice_days,
      public_html = EXCLUDED.public_html,
      private_html = EXCLUDED.private_html,
      surface_geojson = EXCLUDED.surface_geojson,
      surface_raw = EXCLUDED.surface_raw,
      crm_created_at = COALESCE(EXCLUDED.crm_created_at, crm_delivery_zones.crm_created_at),
      crm_updated_at = COALESCE(EXCLUDED.crm_updated_at, crm_delivery_zones.crm_updated_at),
      crm_deleted_at = EXCLUDED.crm_deleted_at,
      last_sync_action = EXCLUDED.last_sync_action,
      last_sync_at = EXCLUDED.last_sync_at,
      raw = EXCLUDED.raw;

    -- log
    INSERT INTO crm_sync_logs(entity_type, crm_entity_id, action, synced_at, filters, payload)
    VALUES (
      'zone',
      z_id,
      COALESCE(v_action,'sync'),
      COALESCE(v_ts, now()),
      v_filters,
      payload
    );

    -- map a locality
    SELECT czl.locality_id
      INTO mapped_locality_id
    FROM crm_zone_localities czl
    WHERE czl.crm_zone_id = z_id;

    IF mapped_locality_id IS NULL THEN
      -- crea locality nueva con name = zona.name
      new_locality_id := gen_random_uuid();

      INSERT INTO localities (id, name, region)
      VALUES (new_locality_id, z_name, 'crm_zone')
      ON CONFLICT DO NOTHING;

      INSERT INTO crm_zone_localities (crm_zone_id, locality_id)
      VALUES (z_id, new_locality_id)
      ON CONFLICT (crm_zone_id) DO NOTHING;

    ELSE
      -- si ya existe el link, sincroniza el nombre
      UPDATE localities
      SET name = z_name
      WHERE id = mapped_locality_id;
    END IF;

  END LOOP;
END;
$function$;
