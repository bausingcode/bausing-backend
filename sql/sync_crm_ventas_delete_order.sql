-- Fix: en sync_crm_ventas, el branch de accion='delete' borraba crm_orders
-- ANTES de borrar la orden interna (orders), y esta tiene
-- fk_orders_crm_order FOREIGN KEY (crm_order_id) REFERENCES crm_orders(crm_order_id)
-- sin cascade, asi que el DELETE FROM crm_orders siempre fallaba con
-- ForeignKeyViolation mientras existiera la orden interna.
--
-- Tambien faltaba desvincular wallet_movements y sale_retry_queue
-- (sin ON DELETE CASCADE hacia orders), igual que ya hace el endpoint
-- admin DELETE /orders/<crm_order_id> en routes/admin.py (delete_order).
--
-- Este fix replica ese mismo orden de borrado dentro de la funcion de
-- sincronizacion, para que el delete que llega del CRM haga la misma
-- cascada que el borrado manual desde el admin de Bausing.

CREATE OR REPLACE FUNCTION public.sync_crm_ventas(p_payload jsonb)
 RETURNS TABLE(p_crm_order_id integer, delivery_status text, affected text)
 LANGUAGE plpgsql
AS $function$
DECLARE
  v_action text;
  v_ts timestamp;

  v_sale jsonb;
  v_order_id int;

  v_item jsonb;
  v_item_uuid uuid;
  v_row_id int;

  v_pay jsonb;

  v_internal_order_uuid uuid;
BEGIN
  IF COALESCE(p_payload->>'tipo','') <> 'ventas' THEN
    RAISE EXCEPTION 'payload.tipo debe ser "ventas", vino: %', p_payload->>'tipo';
  END IF;

  v_action := NULLIF(p_payload #>> '{sincronizar,accion}', '');
  v_ts := NULLIF(p_payload #>> '{sincronizar,timestamp}', '')::timestamp;

  FOR v_sale IN
    SELECT value
    FROM jsonb_array_elements(COALESCE(p_payload->'datos','[]'::jsonb))
  LOOP
    v_order_id := NULLIF(v_sale->>'id','')::int;
    IF v_order_id IS NULL THEN
      CONTINUE;
    END IF;

    -- DELETE
    IF v_action = 'delete' THEN
      -- borrar primero la orden interna (y lo que la referencia sin cascade),
      -- antes de tocar crm_orders, porque orders.crm_order_id -> crm_orders
      -- sin ON DELETE CASCADE
      SELECT id INTO v_internal_order_uuid
      FROM orders
      WHERE crm_order_id = v_order_id;

      IF v_internal_order_uuid IS NOT NULL THEN
        UPDATE wallet_movements SET order_id = NULL WHERE order_id = v_internal_order_uuid;
        UPDATE sale_retry_queue SET order_id = NULL WHERE order_id = v_internal_order_uuid;
        DELETE FROM product_reviews WHERE order_id = v_internal_order_uuid;
        DELETE FROM referrals WHERE order_id = v_internal_order_uuid;
        DELETE FROM order_items WHERE order_id = v_internal_order_uuid;
        DELETE FROM orders WHERE id = v_internal_order_uuid;
      END IF;

      -- borrar CRM children
      DELETE FROM crm_order_item_payment_proposals p
      USING crm_order_items i
      WHERE p.crm_order_item_id = i.id
        AND i.crm_order_id = v_order_id;

      DELETE FROM crm_order_items
      WHERE crm_order_id = v_order_id;

      DELETE FROM crm_order_payments_processed
      WHERE crm_order_id = v_order_id;

      DELETE FROM crm_orders
      WHERE crm_order_id = v_order_id;

      p_crm_order_id := v_order_id;
      delivery_status := NULL;
      affected := 'delete';
      RETURN NEXT;
      CONTINUE;
    END IF;

    -- =====================================================
    -- 1) UPSERT CRM ORDERS
    -- =====================================================
    INSERT INTO crm_orders (
      id,
      crm_order_id,

      receipt_number,
      detail_date,
      crm_seller_id,

      client_name,
      client_address,
      client_phone,
      client_email,

      client_document,
      crm_doc_type_id,
      crm_province_id,
      city,

      crm_zone_id,
      crm_sale_type_id,

      status,
      total_sale,
      total_with_payment,
      is_cancelled,

      delivery_date,
      cobranza_at,
      caja_at,

      crm_created_at,
      crm_updated_at,

      last_sync_action,
      last_sync_at,

      raw,
      created_at,
      updated_at
    )
    VALUES (
      gen_random_uuid(),
      v_order_id,

      NULLIF(v_sale->>'numero_comprobante',''),
      NULLIF(v_sale->>'fecha_detalle','')::date,
      NULLIF(v_sale->>'vendedor_id','')::int,

      NULLIF(v_sale->>'cliente_nombre',''),
      NULLIF(v_sale->>'cliente_direccion',''),
      NULLIF(v_sale->>'cliente_telefono',''),
      NULLIF(v_sale->>'email_cliente',''),

      NULLIF(v_sale->>'documento_cliente',''),

      -- doc type soft FK
      (
        SELECT cdt.crm_doc_type_id
        FROM crm_doc_types cdt
        WHERE cdt.crm_doc_type_id = NULLIF(v_sale->>'tipo_documento_cliente','')::int
      ),

      -- province soft FK
      (
        SELECT cp.crm_province_id
        FROM crm_provinces cp
        WHERE cp.crm_province_id = NULLIF(v_sale->>'provincia_id','')::int
      ),

      NULLIF(v_sale->>'localidad',''),

      -- zone soft FK
      (
        SELECT z.crm_zone_id
        FROM crm_delivery_zones z
        WHERE z.crm_zone_id = NULLIF(v_sale->>'zona_id','')::int
      ),

      -- sale type soft FK
      (
        SELECT st.crm_sale_type_id
        FROM crm_sale_types st
        WHERE st.crm_sale_type_id = NULLIF(v_sale->>'tipo_venta','')::int
      ),

      NULLIF(v_sale->>'estado',''),
      NULLIF(v_sale->>'total_venta','')::numeric,
      NULLIF(v_sale->>'total_con_fpago','')::numeric,
      CASE
        WHEN v_sale ? 'venta_cancelada'
          THEN (NULLIF(v_sale->>'venta_cancelada','')::int = 1)
        ELSE NULL
      END,

      NULLIF(v_sale->>'fecha_entrega','')::timestamp,
      NULLIF(v_sale->>'fecha_paso_cobranza','')::timestamp,
      NULLIF(v_sale->>'fecha_paso_caja','')::timestamp,

      NULLIF(v_sale->>'created_at','')::timestamp,
      NULLIF(v_sale->>'updated_at','')::timestamp,

      v_action,
      v_ts,

      v_sale,
      now(),
      now()
    )
    ON CONFLICT (crm_order_id) DO UPDATE SET
      receipt_number = EXCLUDED.receipt_number,
      detail_date = EXCLUDED.detail_date,
      crm_seller_id = EXCLUDED.crm_seller_id,

      client_name = EXCLUDED.client_name,
      client_address = EXCLUDED.client_address,
      client_phone = EXCLUDED.client_phone,
      -- PRESERVAR client_email: si ya existe (y no es ''), no lo pises
      client_email = COALESCE(NULLIF(crm_orders.client_email, ''), EXCLUDED.client_email),

      client_document = EXCLUDED.client_document,
      crm_doc_type_id = EXCLUDED.crm_doc_type_id,
      crm_province_id = EXCLUDED.crm_province_id,
      city = EXCLUDED.city,

      crm_zone_id = EXCLUDED.crm_zone_id,
      crm_sale_type_id = EXCLUDED.crm_sale_type_id,

      status = EXCLUDED.status,
      total_sale = EXCLUDED.total_sale,
      total_with_payment = EXCLUDED.total_with_payment,
      is_cancelled = EXCLUDED.is_cancelled,

      delivery_date = EXCLUDED.delivery_date,
      cobranza_at = EXCLUDED.cobranza_at,
      caja_at = EXCLUDED.caja_at,

      crm_created_at = EXCLUDED.crm_created_at,
      crm_updated_at = EXCLUDED.crm_updated_at,

      last_sync_action = EXCLUDED.last_sync_action,
      last_sync_at = EXCLUDED.last_sync_at,

      raw = EXCLUDED.raw,
      updated_at = now();

    -- =====================================================
    -- 2) REEMPLAZO CRM ITEMS + FORMAPAGOS
    -- =====================================================
    DELETE FROM crm_order_item_payment_proposals p
    USING crm_order_items i
    WHERE p.crm_order_item_id = i.id
      AND i.crm_order_id = v_order_id;

    DELETE FROM crm_order_items
    WHERE crm_order_id = v_order_id;

    FOR v_item IN
      SELECT value
      FROM jsonb_array_elements(COALESCE(v_sale->'js','[]'::jsonb))
    LOOP
      v_row_id := NULLIF(v_item->>'id','')::int;
      v_item_uuid := gen_random_uuid();

      INSERT INTO crm_order_items (
        id,
        crm_order_id,
        crm_row_id,

        item_id,
        crm_product_id,

        quantity,
        price,
        cost_price,
        commission,

        raw,
        created_at,
        updated_at
      )
      VALUES (
        v_item_uuid,
        v_order_id,
        v_row_id,

        NULLIF(v_item->>'item_id','')::int,
        NULLIF(v_item->>'item_id','')::int,

        NULLIF(v_item->>'cantidad_recibida','')::int,
        NULLIF(v_item->>'precio','')::numeric,
        NULLIF(v_item->>'precio_costo','')::numeric,
        NULLIF(v_item->>'comision','')::numeric,

        v_item,
        now(),
        now()
      );

      FOR v_pay IN
        SELECT value
        FROM jsonb_array_elements(COALESCE(v_item->'formaPagos','[]'::jsonb))
      LOOP
        INSERT INTO crm_order_item_payment_proposals (
          id,
          crm_order_item_id,
          payment_method_id,
          amount_without_formula,
          amount_with_formula,
          raw,
          created_at,
          updated_at
        )
        VALUES (
          gen_random_uuid(),
          v_item_uuid,
          NULLIF(v_pay->>'medio_pago_id','')::int,
          NULLIF(v_pay->>'monto_sin_formula','')::numeric,
          NULLIF(v_pay->>'monto_con_formula','')::numeric,
          v_pay,
          now(),
          now()
        );
      END LOOP;
    END LOOP;

    -- =====================================================
    -- 3) REEMPLAZO CRM PAGOS PROCESADOS
    -- =====================================================
    DELETE FROM crm_order_payments_processed
    WHERE crm_order_id = v_order_id;

    FOR v_pay IN
      SELECT value
      FROM jsonb_array_elements(COALESCE(v_sale->'pagos_procesados','[]'::jsonb))
    LOOP
      INSERT INTO crm_order_payments_processed (
        id,
        crm_order_id,
        crm_payment_id,

        payment_method_id,
        payment_method_description,

        coupon_value,
        credited_value,
        difference,

        receipt_number,
        collected_at,

        raw,
        created_at,
        updated_at
      )
      VALUES (
        gen_random_uuid(),
        v_order_id,
        NULLIF(v_pay->>'id','')::int,

        NULLIF(v_pay->>'forma_pago_id','')::int,
        NULLIF(v_pay->>'forma_pago_descripcion',''),

        NULLIF(v_pay->>'valor_cupon','')::numeric,
        NULLIF(v_pay->>'valor_acreditado','')::numeric,
        NULLIF(v_pay->>'diferencia','')::numeric,

        NULLIF(v_pay->>'numero_comprobante',''),
        NULLIF(v_pay->>'fecha_cobranza','')::timestamp,

        v_pay,
        now(),
        now()
      );
    END LOOP;

    -- =====================================================
    -- 4) UPSERT ORDERS (interno)
    -- =====================================================
    INSERT INTO orders (
      id,
      crm_order_id,
      user_id,
      total,
      status,
      payment_method,
      used_wallet_amount,
      created_at
    )
    VALUES (
      gen_random_uuid(),
      v_order_id,
      NULL, -- si user_id es NOT NULL, esto va a fallar y hay que resolverlo
      NULLIF(v_sale->>'total_venta','')::numeric,
      NULLIF(v_sale->>'estado',''),
      NULL,
      0,
      now()
    )
    ON CONFLICT (crm_order_id) DO UPDATE SET
      total = EXCLUDED.total,
      status = EXCLUDED.status
    RETURNING id INTO v_internal_order_uuid;

    -- =====================================================
    -- 5) ORDER_ITEMS interno (NO requiere product_variants)
    -- =====================================================
    DELETE FROM order_items
    WHERE order_id = v_internal_order_uuid;

    INSERT INTO order_items (
      id,
      order_id,
      product_variant_id,   -- puede ser NULL
      product_id,           -- puede ser NULL
      crm_product_id,       -- siempre
      quantity,
      unit_price
    )
    SELECT
      gen_random_uuid(),
      v_internal_order_uuid,
      pv.id AS product_variant_id,
      p.id  AS product_id,
      ci.crm_product_id,
      ci.quantity,
      ci.price
    FROM crm_order_items ci
    LEFT JOIN products p
      ON p.crm_product_id = ci.crm_product_id
    LEFT JOIN LATERAL (
      SELECT pv1.id
      FROM product_variants pv1
      WHERE p.id IS NOT NULL
        AND pv1.product_id = p.id
      ORDER BY pv1.created_at ASC
      LIMIT 1
    ) pv ON TRUE
    WHERE ci.crm_order_id = v_order_id;

    -- retorno
    p_crm_order_id := v_order_id;
    delivery_status := NULLIF(v_sale->>'estado','');
    affected := COALESCE(v_action, 'upsert');
    RETURN NEXT;
  END LOOP;

  RETURN;
END;
$function$;
