-- Step 1: close the current version if a tracked (Type 2) attribute changed
UPDATE dim_medicine AS d
SET valid_to = n.effective_date, is_current = FALSE
FROM etl_new_master AS n
WHERE n.effective_date = DATE '{eff_date}'
  AND d.medicine_id = n.medicine_id
  AND d.is_current
  AND d.valid_from < n.effective_date
  AND (d.unit_manufacturing_cost_usd IS DISTINCT FROM n.unit_manufacturing_cost_usd
    OR d.wholesale_price_usd IS DISTINCT FROM n.wholesale_price_usd
    OR d.recommended_retail_price_usd IS DISTINCT FROM n.recommended_retail_price_usd
    OR d.product_status IS DISTINCT FROM n.product_status);

-- Step 2: Type 1 attributes are overwritten on every version (history is restated)
UPDATE dim_medicine AS d
SET generic_name = n.generic_name, brand_name = n.brand_name,
    disease_category = n.disease_category, icd10_category = n.icd10_category,
    therapeutic_class = n.therapeutic_class, dosage_form = n.dosage_form,
    strength = n.strength, administration_route = n.administration_route,
    pack_size = n.pack_size, base_unit_of_measure = n.base_unit_of_measure,
    prescription_class = n.prescription_class, is_controlled = n.is_controlled,
    is_cold_chain = n.is_cold_chain, storage_min_temp_c = n.storage_min_temp_c,
    storage_max_temp_c = n.storage_max_temp_c, max_humidity_pct = n.max_humidity_pct,
    shelf_life_months = n.shelf_life_months,
    min_remaining_shelf_life_days = n.min_remaining_shelf_life_days,
    primary_supplier_id = n.primary_supplier_id, primary_plant_id = n.primary_plant_id,
    manufacturing_lead_time_days = n.manufacturing_lead_time_days,
    standard_batch_size_packs = n.standard_batch_size_packs, safety_stock_days = n.safety_stock_days
FROM etl_new_master AS n
WHERE n.effective_date = DATE '{eff_date}' AND d.medicine_id = n.medicine_id;

-- Step 3: insert a current version for every medicine that has none (new, or just closed)
INSERT INTO dim_medicine (
  medicine_key, medicine_id, internal_sku, generic_name, brand_name, disease_category, icd10_category,
  therapeutic_class, atc_code, dosage_form, strength, administration_route, pack_size,
  base_unit_of_measure, prescription_class, is_controlled, is_cold_chain, storage_min_temp_c,
  storage_max_temp_c, max_humidity_pct, shelf_life_months, min_remaining_shelf_life_days,
  primary_supplier_id, primary_plant_id, manufacturing_lead_time_days, standard_batch_size_packs,
  safety_stock_days, unit_manufacturing_cost_usd, wholesale_price_usd, recommended_retail_price_usd,
  product_status, valid_from, valid_to, is_current)
SELECT nextval('seq_medicine_key'), x.* FROM (
  SELECT n.medicine_id, n.internal_sku, n.generic_name, n.brand_name, n.disease_category, n.icd10_category,
         n.therapeutic_class, n.atc_code, n.dosage_form, n.strength, n.administration_route, n.pack_size,
         n.base_unit_of_measure, n.prescription_class, n.is_controlled, n.is_cold_chain, n.storage_min_temp_c,
         n.storage_max_temp_c, n.max_humidity_pct, n.shelf_life_months, n.min_remaining_shelf_life_days,
         n.primary_supplier_id, n.primary_plant_id, n.manufacturing_lead_time_days, n.standard_batch_size_packs,
         n.safety_stock_days, n.unit_manufacturing_cost_usd, n.wholesale_price_usd,
         n.recommended_retail_price_usd, n.product_status,
         n.effective_date, DATE '9999-12-31', TRUE
  FROM etl_new_master n
  WHERE n.effective_date = DATE '{eff_date}'
    AND NOT EXISTS (SELECT 1 FROM dim_medicine d WHERE d.medicine_id = n.medicine_id AND d.is_current)
) x;