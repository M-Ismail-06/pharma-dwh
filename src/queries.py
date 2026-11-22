QUERIES = [
 {"name": "Q01_monthly_sales_by_channel",
  "baseline": """
    SELECT d.year_month, sp.sales_channel, SUM(f.net_sales_usd) AS net_sales_usd,
           SUM(f.gross_margin_usd) AS gross_margin_usd,
           ROUND(100.0 * SUM(f.gross_margin_usd) / SUM(f.net_sales_usd), 2) AS margin_pct, COUNT(*) AS txn_count
    FROM fact_pharmacy_sales f
    JOIN dim_date d ON d.date_key = f.sales_date_key
    JOIN dim_sales_profile sp ON sp.sales_profile_key = f.sales_profile_key
    GROUP BY d.year_month, sp.sales_channel ORDER BY 1, 2""",
  "optimized": """
    SELECT year_month, sales_channel, SUM(net_sales_usd) AS net_sales_usd,
           SUM(gross_margin_usd) AS gross_margin_usd,
           ROUND(100.0 * SUM(gross_margin_usd) / SUM(net_sales_usd), 2) AS margin_pct, SUM(txn_count) AS txn_count
    FROM sum_monthly_sales GROUP BY year_month, sales_channel ORDER BY 1, 2"""},

 {"name": "Q02_channel_pharmacytype_margin",
  "baseline": """
    SELECT sp.sales_channel, p.pharmacy_type, SUM(f.gross_sales_usd) AS gross_sales_usd,
           SUM(f.discount_amount_usd) AS discount_usd,
           ROUND(100.0 * SUM(f.discount_amount_usd) / SUM(f.gross_sales_usd), 2) AS discount_pct,
           SUM(f.net_sales_usd) AS net_sales_usd, SUM(f.gross_margin_usd) AS gross_margin_usd,
           ROUND(100.0 * SUM(f.gross_margin_usd) / SUM(f.net_sales_usd), 2) AS margin_pct
    FROM fact_pharmacy_sales f
    JOIN dim_sales_profile sp ON sp.sales_profile_key = f.sales_profile_key
    JOIN dim_pharmacy p ON p.pharmacy_key = f.pharmacy_key
    GROUP BY sp.sales_channel, p.pharmacy_type ORDER BY 1, 2""",
  "optimized": """
    SELECT sales_channel, pharmacy_type, SUM(gross_sales_usd) AS gross_sales_usd,
           SUM(discount_amount_usd) AS discount_usd,
           ROUND(100.0 * SUM(discount_amount_usd) / SUM(gross_sales_usd), 2) AS discount_pct,
           SUM(net_sales_usd) AS net_sales_usd, SUM(gross_margin_usd) AS gross_margin_usd,
           ROUND(100.0 * SUM(gross_margin_usd) / SUM(net_sales_usd), 2) AS margin_pct
    FROM sum_monthly_sales GROUP BY sales_channel, pharmacy_type ORDER BY 1, 2"""},

 {"name": "Q03_top10_fast_movers",
  "baseline": """
    SELECT m.medicine_id, m.generic_name, m.therapeutic_class, m.disease_category,
           SUM(f.quantity_sold_packs) AS packs_sold, SUM(f.net_sales_usd) AS net_sales_usd
    FROM fact_pharmacy_sales f JOIN dim_medicine m ON m.medicine_key = f.medicine_key
    GROUP BY m.medicine_id, m.generic_name, m.therapeutic_class, m.disease_category
    ORDER BY packs_sold DESC, m.medicine_id LIMIT 10""",
  "optimized": """
    SELECT medicine_id, generic_name, therapeutic_class, disease_category,
           SUM(qty_sold_packs) AS packs_sold, SUM(net_sales_usd) AS net_sales_usd
    FROM sum_medicine_month
    GROUP BY medicine_id, generic_name, therapeutic_class, disease_category
    ORDER BY packs_sold DESC, medicine_id LIMIT 10"""},

 {"name": "Q04_bottom10_slow_movers",
  "baseline": """
    SELECT m.medicine_id, m.generic_name, m.therapeutic_class, m.disease_category,
           SUM(f.quantity_sold_packs) AS packs_sold, SUM(f.net_sales_usd) AS net_sales_usd
    FROM fact_pharmacy_sales f JOIN dim_medicine m ON m.medicine_key = f.medicine_key
    GROUP BY m.medicine_id, m.generic_name, m.therapeutic_class, m.disease_category
    ORDER BY packs_sold ASC, m.medicine_id LIMIT 10""",
  "optimized": """
    SELECT medicine_id, generic_name, therapeutic_class, disease_category,
           SUM(qty_sold_packs) AS packs_sold, SUM(net_sales_usd) AS net_sales_usd
    FROM sum_medicine_month
    GROUP BY medicine_id, generic_name, therapeutic_class, disease_category
    ORDER BY packs_sold ASC, medicine_id LIMIT 10"""},

 {"name": "Q05_hospital_forecast_vs_actual",
  "baseline": """
    SELECT d.year_month, h.hospital_name, SUM(f.forecast_demand_packs) AS forecast_packs,
           SUM(f.approved_quantity_packs) AS approved_packs, SUM(f.consumed_quantity_packs) AS consumed_packs,
           ROUND(SUM(f.consumed_quantity_packs)::DOUBLE / SUM(f.forecast_demand_packs), 3) AS consumed_to_forecast,
           ROUND(SUM(f.approved_quantity_packs)::DOUBLE / SUM(f.forecast_demand_packs), 3) AS approved_to_forecast
    FROM fact_hospital_demand f
    JOIN dim_date d ON d.date_key = f.demand_month_date_key
    JOIN dim_hospital h ON h.hospital_key = f.hospital_key
    GROUP BY d.year_month, h.hospital_name ORDER BY 1, 2""",
  "optimized": """
    SELECT year_month, hospital_name, SUM(forecast_packs) AS forecast_packs,
           SUM(approved_packs) AS approved_packs, SUM(consumed_packs) AS consumed_packs,
           ROUND(SUM(consumed_packs)::DOUBLE / SUM(forecast_packs), 3) AS consumed_to_forecast,
           ROUND(SUM(approved_packs)::DOUBLE / SUM(forecast_packs), 3) AS approved_to_forecast
    FROM sum_hospital_month GROUP BY year_month, hospital_name ORDER BY 1, 2"""},

 {"name": "Q06_unfulfilled_demand",
  "baseline": """
    SELECT h.hospital_name, m.therapeutic_class, SUM(f.unfulfilled_demand_packs) AS unfulfilled_packs,
           SUM(f.stockout_days) AS stockout_days,
           SUM(CASE WHEN f.unfulfilled_demand_packs > 0 THEN 1 ELSE 0 END) AS shortfall_records
    FROM fact_hospital_demand f
    JOIN dim_hospital h ON h.hospital_key = f.hospital_key
    JOIN dim_medicine m ON m.medicine_key = f.medicine_key
    GROUP BY h.hospital_name, m.therapeutic_class
    HAVING SUM(f.unfulfilled_demand_packs) > 0
    ORDER BY unfulfilled_packs DESC, h.hospital_name, m.therapeutic_class LIMIT 20""",
  "optimized": """
    SELECT hospital_name, therapeutic_class, SUM(unfulfilled_packs) AS unfulfilled_packs,
           SUM(stockout_days) AS stockout_days, SUM(shortfall_records) AS shortfall_records
    FROM sum_hospital_month
    GROUP BY hospital_name, therapeutic_class
    HAVING SUM(unfulfilled_packs) > 0
    ORDER BY unfulfilled_packs DESC, hospital_name, therapeutic_class LIMIT 20"""},

 {"name": "Q07_otif_by_warehouse_month",
  "baseline": """
    WITH deliveries AS (
      SELECT f.pharmacy_delivery_id, MIN(f.source_warehouse_id) AS warehouse_id,
             MIN(f.delivery_date_key) AS delivery_date_key, MIN(sp.delivery_otif_flag) AS otif_flag
      FROM fact_pharmacy_sales f
      JOIN dim_sales_profile sp ON sp.sales_profile_key = f.sales_profile_key
      GROUP BY f.pharmacy_delivery_id)
    SELECT d.year_month, x.warehouse_id, COUNT(*) AS deliveries,
           SUM(CASE WHEN x.otif_flag = 'Y' THEN 1 ELSE 0 END) AS otif_deliveries,
           ROUND(100.0 * SUM(CASE WHEN x.otif_flag = 'Y' THEN 1 ELSE 0 END) / COUNT(*), 2) AS otif_pct
    FROM deliveries x JOIN dim_date d ON d.date_key = x.delivery_date_key
    GROUP BY d.year_month, x.warehouse_id ORDER BY 1, 2""",
  "optimized": """
    SELECT year_month, warehouse_id, SUM(deliveries) AS deliveries, SUM(otif_deliveries) AS otif_deliveries,
           ROUND(100.0 * SUM(otif_deliveries) / SUM(deliveries), 2) AS otif_pct
    FROM sum_delivery_otif GROUP BY year_month, warehouse_id ORDER BY 1, 2"""},

 {"name": "Q08_ecommerce_returns_by_segment",
  "baseline": """
    SELECT sp.customer_segment, COUNT(*) AS orders,
           SUM(CASE WHEN sp.ecommerce_delivery_status = 'Returned to sender' THEN 1 ELSE 0 END) AS returned_to_sender,
           ROUND(100.0 * SUM(CASE WHEN sp.ecommerce_delivery_status = 'Returned to sender' THEN 1 ELSE 0 END) / COUNT(*), 2) AS rts_pct,
           SUM(CASE WHEN sp.sale_status = 'Partially returned' THEN 1 ELSE 0 END) AS partial_returns,
           ROUND(100.0 * SUM(CASE WHEN sp.sale_status = 'Partially returned' THEN 1 ELSE 0 END) / COUNT(*), 2) AS partial_return_pct
    FROM fact_pharmacy_sales f JOIN dim_sales_profile sp ON sp.sales_profile_key = f.sales_profile_key
    WHERE sp.sales_channel = 'Ecommerce' GROUP BY sp.customer_segment ORDER BY 1""",
  "optimized": """
    SELECT customer_segment, SUM(txn_count) AS orders,
           SUM(CASE WHEN ecommerce_delivery_status = 'Returned to sender' THEN txn_count ELSE 0 END) AS returned_to_sender,
           ROUND(100.0 * SUM(CASE WHEN ecommerce_delivery_status = 'Returned to sender' THEN txn_count ELSE 0 END) / SUM(txn_count), 2) AS rts_pct,
           SUM(CASE WHEN sale_status = 'Partially returned' THEN txn_count ELSE 0 END) AS partial_returns,
           ROUND(100.0 * SUM(CASE WHEN sale_status = 'Partially returned' THEN txn_count ELSE 0 END) / SUM(txn_count), 2) AS partial_return_pct
    FROM sum_channel_segment_month WHERE sales_channel = 'Ecommerce' GROUP BY customer_segment ORDER BY 1"""},

 {"name": "Q09_pharmacy_league_table",
  "baseline": """
    SELECT g.us_region, g.state, p.pharmacy_id, p.pharmacy_name, p.pharmacy_type,
           SUM(f.net_sales_usd) AS net_sales_usd, SUM(f.gross_margin_usd) AS gross_margin_usd,
           ROUND(100.0 * SUM(f.gross_margin_usd) / SUM(f.net_sales_usd), 2) AS margin_pct, COUNT(*) AS txn_count
    FROM fact_pharmacy_sales f
    JOIN dim_pharmacy p ON p.pharmacy_key = f.pharmacy_key
    JOIN dim_geography g ON g.geography_key = f.geography_key
    GROUP BY g.us_region, g.state, p.pharmacy_id, p.pharmacy_name, p.pharmacy_type
    ORDER BY net_sales_usd DESC, p.pharmacy_id LIMIT 20""",
  "optimized": """
    SELECT us_region, state, pharmacy_id, pharmacy_name, pharmacy_type,
           SUM(net_sales_usd) AS net_sales_usd, SUM(gross_margin_usd) AS gross_margin_usd,
           ROUND(100.0 * SUM(gross_margin_usd) / SUM(net_sales_usd), 2) AS margin_pct, SUM(txn_count) AS txn_count
    FROM sum_pharmacy_month
    GROUP BY us_region, state, pharmacy_id, pharmacy_name, pharmacy_type
    ORDER BY net_sales_usd DESC, pharmacy_id LIMIT 20"""},
]

# Q10 is a selective lookup, so no summary table applies. "Optimized" means: same SQL, run after the index exists.
_Q10 = """
    SELECT f.production_batch_id, f.warehouse_lot_id, f.pharmacy_delivery_id, p.pharmacy_name, g.city, g.state,
           sp.delivery_otif_flag, SUM(f.quantity_sold_packs) AS packs_sold,
           MIN(d.full_date) AS first_sale, MAX(d.full_date) AS last_sale
    FROM fact_pharmacy_sales f
    JOIN dim_pharmacy p ON p.pharmacy_key = f.pharmacy_key
    JOIN dim_geography g ON g.geography_key = f.geography_key
    JOIN dim_sales_profile sp ON sp.sales_profile_key = f.sales_profile_key
    JOIN dim_date d ON d.date_key = f.sales_date_key
    WHERE f.production_batch_id = 'B23-PLT02-000362'
    GROUP BY f.production_batch_id, f.warehouse_lot_id, f.pharmacy_delivery_id, p.pharmacy_name, g.city, g.state, sp.delivery_otif_flag
    ORDER BY packs_sold DESC, f.pharmacy_delivery_id, p.pharmacy_name"""
QUERIES.append({"name": "Q10_batch_trace", "baseline": _Q10, "optimized": _Q10})