CREATE OR REPLACE TABLE sum_monthly_sales AS
SELECT d.year_month, sp.sales_channel, p.pharmacy_type, m.disease_category, m.therapeutic_class,
       COUNT(*) AS txn_count, SUM(f.quantity_sold_packs) AS qty_sold_packs,
       SUM(f.returned_quantity_packs) AS returned_packs, SUM(f.gross_sales_usd) AS gross_sales_usd,
       SUM(f.discount_amount_usd) AS discount_amount_usd, SUM(f.net_sales_usd) AS net_sales_usd,
       SUM(f.sales_tax_usd) AS sales_tax_usd, SUM(f.cost_of_goods_sold_usd) AS cogs_usd,
       SUM(f.gross_margin_usd) AS gross_margin_usd, SUM(f.manufacturing_cost_usd) AS manufacturing_cost_usd
FROM fact_pharmacy_sales f
JOIN dim_date d ON d.date_key = f.sales_date_key
JOIN dim_sales_profile sp ON sp.sales_profile_key = f.sales_profile_key
JOIN dim_pharmacy p ON p.pharmacy_key = f.pharmacy_key
JOIN dim_medicine m ON m.medicine_key = f.medicine_key
GROUP BY ALL;

CREATE OR REPLACE TABLE sum_medicine_month AS
SELECT d.year_month, m.medicine_id, m.generic_name, m.therapeutic_class, m.disease_category,
       SUM(f.quantity_sold_packs) AS qty_sold_packs, SUM(f.net_sales_usd) AS net_sales_usd,
       SUM(f.gross_margin_usd) AS gross_margin_usd
FROM fact_pharmacy_sales f
JOIN dim_date d ON d.date_key = f.sales_date_key
JOIN dim_medicine m ON m.medicine_key = f.medicine_key
GROUP BY ALL;

CREATE OR REPLACE TABLE sum_pharmacy_month AS
SELECT d.year_month, g.us_region, g.state, g.city, p.pharmacy_id, p.pharmacy_name, p.pharmacy_type,
       COUNT(*) AS txn_count, SUM(f.net_sales_usd) AS net_sales_usd, SUM(f.gross_margin_usd) AS gross_margin_usd
FROM fact_pharmacy_sales f
JOIN dim_date d ON d.date_key = f.sales_date_key
JOIN dim_pharmacy p ON p.pharmacy_key = f.pharmacy_key
JOIN dim_geography g ON g.geography_key = f.geography_key
GROUP BY ALL;

CREATE OR REPLACE TABLE sum_channel_segment_month AS
SELECT d.year_month, sp.sales_channel, sp.customer_segment, sp.ecommerce_delivery_status, sp.sale_status,
       COUNT(*) AS txn_count, SUM(f.quantity_sold_packs) AS qty_sold_packs,
       SUM(f.returned_quantity_packs) AS returned_packs, SUM(f.net_sales_usd) AS net_sales_usd
FROM fact_pharmacy_sales f
JOIN dim_date d ON d.date_key = f.sales_date_key
JOIN dim_sales_profile sp ON sp.sales_profile_key = f.sales_profile_key
GROUP BY ALL;

CREATE OR REPLACE TABLE sum_delivery_otif AS
WITH deliveries AS (
  SELECT f.pharmacy_delivery_id, MIN(f.source_warehouse_id) AS warehouse_id,
         MIN(f.delivery_date_key) AS delivery_date_key, MIN(sp.delivery_otif_flag) AS otif_flag
  FROM fact_pharmacy_sales f
  JOIN dim_sales_profile sp ON sp.sales_profile_key = f.sales_profile_key
  GROUP BY f.pharmacy_delivery_id)
SELECT d.year_month, x.warehouse_id, COUNT(*) AS deliveries,
       SUM(CASE WHEN x.otif_flag = 'Y' THEN 1 ELSE 0 END) AS otif_deliveries
FROM deliveries x JOIN dim_date d ON d.date_key = x.delivery_date_key
GROUP BY ALL;

CREATE OR REPLACE TABLE sum_hospital_month AS
SELECT d.year_month, h.hospital_id, h.hospital_name, m.therapeutic_class, m.disease_category,
       COUNT(*) AS record_count, SUM(f.forecast_demand_packs) AS forecast_packs,
       SUM(f.requested_quantity_packs) AS requested_packs, SUM(f.approved_quantity_packs) AS approved_packs,
       SUM(f.consumed_quantity_packs) AS consumed_packs, SUM(f.unfulfilled_demand_packs) AS unfulfilled_packs,
       SUM(f.stockout_days) AS stockout_days,
       SUM(CASE WHEN f.unfulfilled_demand_packs > 0 THEN 1 ELSE 0 END) AS shortfall_records
FROM fact_hospital_demand f
JOIN dim_date d ON d.date_key = f.demand_month_date_key
JOIN dim_hospital h ON h.hospital_key = f.hospital_key
JOIN dim_medicine m ON m.medicine_key = f.medicine_key
GROUP BY ALL;

-- Indexing experiment: DuckDB's ART index for selective lookups (used by the batch trace query Q10)
DROP INDEX IF EXISTS ix_fact_sales_batch;
CREATE INDEX ix_fact_sales_batch ON fact_pharmacy_sales (production_batch_id);