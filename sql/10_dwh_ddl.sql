-- Surrogate key sequences
CREATE SEQUENCE IF NOT EXISTS seq_medicine_key START 1;
CREATE SEQUENCE IF NOT EXISTS seq_pharmacy_key START 1;
CREATE SEQUENCE IF NOT EXISTS seq_hospital_key START 1;
CREATE SEQUENCE IF NOT EXISTS seq_geography_key START 1;
CREATE SEQUENCE IF NOT EXISTS seq_sales_profile_key START 1;
CREATE SEQUENCE IF NOT EXISTS seq_demand_flags_key START 1;
CREATE SEQUENCE IF NOT EXISTS seq_sales_key START 1;
CREATE SEQUENCE IF NOT EXISTS seq_hospital_demand_key START 1;

-- ETL bookkeeping
CREATE TABLE IF NOT EXISTS etl_loaded_batches (
  source_table VARCHAR, batch_id VARCHAR, loaded_at TIMESTAMP, rows_staged BIGINT,
  PRIMARY KEY (source_table, batch_id));

CREATE TABLE IF NOT EXISTS ref_state_region (state VARCHAR PRIMARY KEY, us_region VARCHAR);
INSERT OR IGNORE INTO ref_state_region VALUES
  ('CT','Northeast'),('MA','Northeast'),('NY','Northeast'),('PA','Northeast'),
  ('IL','Midwest'),('MI','Midwest'),('OH','Midwest'),
  ('GA','South'),('NC','South'),('TN','South'),('FL','South'),('TX','South'),
  ('CA','West'),('CO','West'),('NV','West');

-- Dimensions
CREATE TABLE IF NOT EXISTS dim_date (
  date_key INTEGER PRIMARY KEY, full_date DATE, day_of_month TINYINT, day_name VARCHAR,
  day_of_week TINYINT, week_of_year TINYINT, month_number TINYINT, month_name VARCHAR,
  year_month VARCHAR, quarter TINYINT, year SMALLINT, is_weekend BOOLEAN);

CREATE TABLE IF NOT EXISTS dim_medicine (
  medicine_key BIGINT PRIMARY KEY, medicine_id VARCHAR NOT NULL, internal_sku VARCHAR,
  generic_name VARCHAR, brand_name VARCHAR, disease_category VARCHAR, icd10_category VARCHAR,
  therapeutic_class VARCHAR, atc_code VARCHAR, dosage_form VARCHAR, strength VARCHAR,
  administration_route VARCHAR, pack_size INTEGER, base_unit_of_measure VARCHAR,
  prescription_class VARCHAR, is_controlled BOOLEAN, is_cold_chain BOOLEAN,
  storage_min_temp_c INTEGER, storage_max_temp_c INTEGER, max_humidity_pct INTEGER,
  shelf_life_months INTEGER, min_remaining_shelf_life_days INTEGER,
  primary_supplier_id VARCHAR, primary_plant_id VARCHAR, manufacturing_lead_time_days INTEGER,
  standard_batch_size_packs INTEGER, safety_stock_days INTEGER,
  unit_manufacturing_cost_usd DECIMAL(10,2), wholesale_price_usd DECIMAL(10,2),
  recommended_retail_price_usd DECIMAL(10,2), product_status VARCHAR,
  valid_from DATE, valid_to DATE, is_current BOOLEAN);

CREATE TABLE IF NOT EXISTS dim_pharmacy (
  pharmacy_key BIGINT PRIMARY KEY, pharmacy_id VARCHAR NOT NULL, pharmacy_name VARCHAR,
  pharmacy_type VARCHAR, linked_hospital_id VARCHAR, is_hospital_pharmacy BOOLEAN);

CREATE TABLE IF NOT EXISTS dim_hospital (
  hospital_key BIGINT PRIMARY KEY, hospital_id VARCHAR NOT NULL, hospital_name VARCHAR,
  hospital_type VARCHAR, hospital_pharmacy_id VARCHAR, licensed_beds INTEGER, icu_beds INTEGER,
  avg_occupancy_rate_pct INTEGER, trauma_level VARCHAR, catchment_population INTEGER,
  bed_size_band VARCHAR);

CREATE TABLE IF NOT EXISTS dim_geography (
  geography_key BIGINT PRIMARY KEY, city VARCHAR, state VARCHAR, country_code VARCHAR,
  us_region VARCHAR);

CREATE TABLE IF NOT EXISTS dim_sales_profile (
  sales_profile_key BIGINT PRIMARY KEY, sales_channel VARCHAR, customer_segment VARCHAR,
  payer_type VARCHAR, payment_method VARCHAR, promotion_code VARCHAR,
  prescription_required_flag VARCHAR, ecommerce_delivery_status VARCHAR,
  sale_status VARCHAR, delivery_otif_flag VARCHAR);

CREATE TABLE IF NOT EXISTS dim_demand_flags (
  demand_flags_key BIGINT PRIMARY KEY, medication_request_status VARCHAR,
  formulary_status VARCHAR);

-- Unknown members (key -1)
INSERT OR IGNORE INTO dim_date (date_key, full_date) VALUES (-1, NULL);
INSERT OR IGNORE INTO dim_medicine (medicine_key, medicine_id, generic_name, valid_from, valid_to, is_current)
  VALUES (-1, 'N/A', 'Unknown', DATE '1900-01-01', DATE '9999-12-31', TRUE);
INSERT OR IGNORE INTO dim_pharmacy VALUES (-1, 'N/A', 'Unknown', 'Unknown', 'N/A', FALSE);
INSERT OR IGNORE INTO dim_hospital VALUES (-1, 'N/A', 'Not applicable', 'Not applicable', 'N/A', NULL, NULL, NULL, 'None', NULL, 'N/A');
INSERT OR IGNORE INTO dim_geography VALUES (-1, 'Unknown', 'NA', 'NA', 'Unknown');
INSERT OR IGNORE INTO dim_sales_profile VALUES (-1, 'Unknown', 'Unknown', 'Unknown', 'Unknown', 'NONE', 'N', 'Unknown', 'Unknown', 'N');
INSERT OR IGNORE INTO dim_demand_flags VALUES (-1, 'Unknown', 'Unknown');

-- Facts
CREATE TABLE IF NOT EXISTS fact_pharmacy_sales (
  sales_key BIGINT PRIMARY KEY,
  sales_transaction_id VARCHAR NOT NULL UNIQUE,
  sales_date_key INTEGER NOT NULL, delivery_date_key INTEGER NOT NULL, batch_expiry_date_key INTEGER NOT NULL,
  medicine_key BIGINT NOT NULL, pharmacy_key BIGINT NOT NULL, hospital_key BIGINT NOT NULL,
  geography_key BIGINT NOT NULL, sales_profile_key BIGINT NOT NULL,
  pharmacy_order_id VARCHAR, pharmacy_delivery_id VARCHAR, warehouse_lot_id VARCHAR,
  production_batch_id VARCHAR, source_warehouse_id VARCHAR, prescription_id VARCHAR,
  sales_timestamp_utc TIMESTAMP,
  quantity_sold_packs INTEGER, returned_quantity_packs INTEGER, unit_retail_price_usd DECIMAL(10,2),
  gross_sales_usd DECIMAL(12,2), discount_amount_usd DECIMAL(12,2), net_sales_usd DECIMAL(12,2),
  sales_tax_usd DECIMAL(12,2), cost_of_goods_sold_usd DECIMAL(12,2), gross_margin_usd DECIMAL(12,2),
  manufacturing_cost_usd DECIMAL(12,2), delivery_quantity_packs INTEGER, days_to_expiry_at_sale INTEGER,
  batch_id VARCHAR, load_timestamp TIMESTAMP DEFAULT current_timestamp);

CREATE TABLE IF NOT EXISTS fact_hospital_demand (
  hospital_demand_key BIGINT PRIMARY KEY,
  hospital_demand_record_id VARCHAR NOT NULL UNIQUE,
  demand_month_date_key INTEGER NOT NULL, hospital_key BIGINT NOT NULL, medicine_key BIGINT NOT NULL,
  geography_key BIGINT NOT NULL, demand_flags_key BIGINT NOT NULL,
  estimated_disease_cases INTEGER, disease_related_admissions INTEGER, outpatient_encounters INTEGER,
  forecast_demand_packs INTEGER, requested_quantity_packs INTEGER, approved_quantity_packs INTEGER,
  received_quantity_packs INTEGER, emergency_request_quantity_packs INTEGER, opening_stock_packs INTEGER,
  dispensed_quantity_packs INTEGER, consumed_quantity_packs INTEGER, wastage_quantity_packs INTEGER,
  closing_stock_packs INTEGER, unfulfilled_demand_packs INTEGER, stockout_days INTEGER,
  service_level_pct DECIMAL(5,2), average_lead_time_days INTEGER, demand_trend_index DECIMAL(6,3),
  forecast_error_packs INTEGER,
  batch_id VARCHAR, load_timestamp TIMESTAMP DEFAULT current_timestamp);

-- First version of each medicine (fallback for sales dated before its first valid_from)
CREATE OR REPLACE VIEW v_medicine_first AS
SELECT medicine_id, medicine_key, unit_manufacturing_cost_usd
FROM dim_medicine WHERE medicine_key > 0
QUALIFY row_number() OVER (PARTITION BY medicine_id ORDER BY valid_from) = 1;