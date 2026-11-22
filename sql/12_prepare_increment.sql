CREATE OR REPLACE TABLE etl_new_master AS
SELECT
  trim(upper(medicineid)) AS medicine_id, trim(internalsku) AS internal_sku,
  trim(genericname) AS generic_name, trim(fictionalbrandname) AS brand_name,
  trim(diseasecategory) AS disease_category, trim(icd10category) AS icd10_category,
  trim(atccode) AS atc_code, trim(therapeuticclass) AS therapeutic_class,
  trim(dosageform) AS dosage_form, trim(strength) AS strength,
  trim(routeofadministration) AS administration_route,
  CAST(packsize AS INTEGER) AS pack_size, trim(baseunitofmeasure) AS base_unit_of_measure,
  trim(prescriptionclass) AS prescription_class,
  (upper(trim(controlledmedicineflag)) = 'Y') AS is_controlled,
  (upper(trim(coldchainflag)) = 'Y') AS is_cold_chain,
  CAST(storagemintempc AS INTEGER) AS storage_min_temp_c,
  CAST(storagemaxtempc AS INTEGER) AS storage_max_temp_c,
  CAST(maxhumiditypct AS INTEGER) AS max_humidity_pct,
  CAST(shelflifemonths AS INTEGER) AS shelf_life_months,
  CAST(minimumremainingshelflifedays AS INTEGER) AS min_remaining_shelf_life_days,
  trim(primarysupplierid) AS primary_supplier_id, trim(primaryplantid) AS primary_plant_id,
  CAST(manufacturingleadtimedays AS INTEGER) AS manufacturing_lead_time_days,
  CAST(standardbatchsizepacks AS INTEGER) AS standard_batch_size_packs,
  CAST(safetystockdays AS INTEGER) AS safety_stock_days,
  CAST(unitmanufacturingcostusd AS DECIMAL(10,2)) AS unit_manufacturing_cost_usd,
  CAST(wholesalepriceusd AS DECIMAL(10,2)) AS wholesale_price_usd,
  CAST(recommendedretailpriceusd AS DECIMAL(10,2)) AS recommended_retail_price_usd,
  trim(productstatus) AS product_status,
  CAST(strptime(effectivefromdate, '%d-%m-%y') AS DATE) AS effective_date,
  batch_id
FROM etl_raw_master
QUALIFY row_number() OVER (PARTITION BY trim(upper(medicineid)), effectivefromdate ORDER BY batch_id) = 1;