-- Atomic order + item creation for the Supabase REST API backend.
BEGIN;

CREATE OR REPLACE FUNCTION public.create_order_with_items(
  p_user_id INTEGER,
  p_address VARCHAR,
  p_notes VARCHAR,
  p_items JSONB
) RETURNS INTEGER
LANGUAGE plpgsql
SECURITY INVOKER
AS $$
DECLARE
  new_order_id INTEGER;
  item JSONB;
  order_total NUMERIC(10, 2);
  product_id INTEGER;
  item_quantity INTEGER;
BEGIN
  IF p_address IS NULL OR length(btrim(p_address)) < 5 OR length(p_address) > 300 THEN
    RAISE EXCEPTION 'Endereço inválido' USING ERRCODE = '23514';
  END IF;

  IF p_notes IS NULL OR length(p_notes) > 500 THEN
    RAISE EXCEPTION 'Observações inválidas' USING ERRCODE = '23514';
  END IF;

  IF NOT EXISTS (SELECT 1 FROM public.users WHERE id = p_user_id AND active IS TRUE) THEN
    RAISE EXCEPTION 'Usuário indisponível' USING ERRCODE = '23503';
  END IF;

  IF jsonb_typeof(p_items) IS DISTINCT FROM 'array' THEN
    RAISE EXCEPTION 'Pedido deve conter itens' USING ERRCODE = '23514';
  END IF;

  IF jsonb_array_length(p_items) = 0 THEN
    RAISE EXCEPTION 'Pedido deve conter itens' USING ERRCODE = '23514';
  END IF;

  FOR item IN SELECT value FROM jsonb_array_elements(p_items)
  LOOP
    IF jsonb_typeof(item) IS DISTINCT FROM 'object'
       OR jsonb_typeof(item->'product_id') IS DISTINCT FROM 'number'
       OR jsonb_typeof(item->'quantity') IS DISTINCT FROM 'number'
       OR jsonb_typeof(item->'name') IS DISTINCT FROM 'string'
       OR jsonb_typeof(item->'price') IS DISTINCT FROM 'string'
       OR length(btrim(item->>'name')) = 0
       OR length(item->>'name') > 150
      OR (item->>'price') !~ '^[0-9]+([.][0-9]{1,2})?$' THEN
      RAISE EXCEPTION 'Item de pedido inválido' USING ERRCODE = '23514';
    END IF;

    IF (item->>'product_id')::NUMERIC <> trunc((item->>'product_id')::NUMERIC)
       OR (item->>'product_id')::NUMERIC NOT BETWEEN 1 AND 2147483647
       OR (item->>'quantity')::NUMERIC <> trunc((item->>'quantity')::NUMERIC)
       OR (item->>'quantity')::NUMERIC NOT BETWEEN 1 AND 99
       OR (item->>'price')::NUMERIC < 0 THEN
      RAISE EXCEPTION 'Item de pedido inválido' USING ERRCODE = '23514';
    END IF;

    product_id := (item->>'product_id')::INTEGER;
    IF NOT EXISTS (
      SELECT 1 FROM public.products
       WHERE id = product_id AND active IS TRUE
    ) THEN
      RAISE EXCEPTION 'Produto indisponível' USING ERRCODE = '23514';
    END IF;
  END LOOP;

  SELECT ROUND(SUM((value->>'price')::NUMERIC * (value->>'quantity')::INTEGER), 2)
    INTO order_total
    FROM jsonb_array_elements(p_items);

  INSERT INTO public.orders (user_id, address, notes, status, total)
  VALUES (p_user_id, p_address, p_notes, 'pendente', order_total)
  RETURNING id INTO new_order_id;

  FOR item IN SELECT value FROM jsonb_array_elements(p_items)
  LOOP
    item_quantity := (item->>'quantity')::INTEGER;
    INSERT INTO public.order_items (order_id, product_id, name, price, quantity)
    VALUES (
      new_order_id,
      (item->>'product_id')::INTEGER,
      item->>'name',
      (item->>'price')::NUMERIC,
      item_quantity
    );
  END LOOP;

  RETURN new_order_id;
END;
$$;

REVOKE ALL ON FUNCTION public.create_order_with_items(INTEGER, VARCHAR, VARCHAR, JSONB) FROM PUBLIC;
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    REVOKE ALL ON FUNCTION public.create_order_with_items(INTEGER, VARCHAR, VARCHAR, JSONB) FROM anon;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    REVOKE ALL ON FUNCTION public.create_order_with_items(INTEGER, VARCHAR, VARCHAR, JSONB) FROM authenticated;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
    GRANT EXECUTE ON FUNCTION public.create_order_with_items(INTEGER, VARCHAR, VARCHAR, JSONB) TO service_role;
  END IF;
END $$;

NOTIFY pgrst, 'reload schema';
COMMIT;
