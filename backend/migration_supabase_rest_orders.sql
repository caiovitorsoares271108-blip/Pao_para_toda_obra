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
BEGIN
  IF jsonb_typeof(p_items) <> 'array' OR jsonb_array_length(p_items) = 0 THEN
    RAISE EXCEPTION 'Pedido deve conter itens' USING ERRCODE = '23514';
  END IF;

  FOR item IN SELECT value FROM jsonb_array_elements(p_items)
  LOOP
    IF NOT EXISTS (
      SELECT 1 FROM public.products
       WHERE id = (item->>'product_id')::INTEGER AND active IS TRUE
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
    INSERT INTO public.order_items (order_id, product_id, name, price, quantity)
    VALUES (
      new_order_id,
      (item->>'product_id')::INTEGER,
      item->>'name',
      (item->>'price')::NUMERIC,
      (item->>'quantity')::INTEGER
    );
  END LOOP;

  RETURN new_order_id;
END;
$$;

REVOKE ALL ON FUNCTION public.create_order_with_items(INTEGER, VARCHAR, VARCHAR, JSONB) FROM PUBLIC;
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
    GRANT EXECUTE ON FUNCTION public.create_order_with_items(INTEGER, VARCHAR, VARCHAR, JSONB) TO service_role;
  END IF;
END $$;

NOTIFY pgrst, 'reload schema';
COMMIT;
