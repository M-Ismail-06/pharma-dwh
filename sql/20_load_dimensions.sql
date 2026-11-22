-- DimDate: one row per day 2022-2030
INSERT INTO dim_date (date_key, full_date, day_of_month, day_name, day_of_week, week_of_year,
                      month_number, month_name, year_month, quarter, year, is_weekend)
SELECT CAST(strftime(d, '%Y%m%d') AS INTEGER), CAST(d AS DATE), day(d), dayname(d), isodow(d),
       weekofyear(d), month(d), monthname(d), strftime(d, '%Y-%m'), quarter(d), year(d), isodow(d) >= 6
FROM generate_series(TIMESTAMP '2022-01-01', TIMESTAMP '2030-12-31', INTERVAL 1 DAY) AS t(d)
WHERE CAST(strftime(d, '%Y%m%d') AS INTEGER) NOT IN (SELECT date_key FROM dim_date);

-- DimGeography: union of pharmacy and hospital cities
INSERT INTO dim_geography (geography_key, city, state, country_code, us_region)
SELECT nextval('seq_geography_key'), g.city, g.state, g.country_code, COALESCE(r.us_region, 'Unknown')
FROM (
  SELECT trim(pharmacycity) AS city, trim(pharmacystate) AS state, trim(countrycode) AS country_code FROM etl_raw_sales
  UNION
  SELECT trim(city), trim(state), trim(countrycode) FROM etl_raw_hospital
) g
LEFT JOIN ref_state_region r ON r.state = g.state
WHERE NOT EXISTS (SELECT 1 FROM dim_geography d
                  WHERE d.city = g.city AND d.state = g.state AND d.country_code = g.country_code);

-- DimPharmacy (Type 1)
CREATE OR REPLACE TABLE etl_pharmacy_agg AS
SELECT trim(upper(pharmacyid)) AS pharmacy_id, max(trim(pharmacyname)) AS pharmacy_name,
       max(trim(pharmacytype)) AS pharmacy_type,
       COALESCE(max(NULLIF(trim(hospitalid), '')), 'N/A') AS linked_hospital_id
FROM etl_raw_sales GROUP BY 1;

INSERT INTO dim_pharmacy (pharmacy_key, pharmacy_id, pharmacy_name, pharmacy_type, linked_hospital_id, is_hospital_pharmacy)
SELECT nextval('seq_pharmacy_key'), a.pharmacy_id, a.pharmacy_name, a.pharmacy_type, a.linked_hospital_id,
       a.pharmacy_type = 'Hospital Pharmacy'
FROM etl_pharmacy_agg a
WHERE NOT EXISTS (SELECT 1 FROM dim_pharmacy d WHERE d.pharmacy_id = a.pharmacy_id);

UPDATE dim_pharmacy AS d
SET pharmacy_name = a.pharmacy_name, pharmacy_type = a.pharmacy_type,
    linked_hospital_id = a.linked_hospital_id, is_hospital_pharmacy = (a.pharmacy_type = 'Hospital Pharmacy')
FROM etl_pharmacy_agg AS a
WHERE d.pharmacy_id = a.pharmacy_id
  AND (d.pharmacy_name IS DISTINCT FROM a.pharmacy_name OR d.pharmacy_type IS DISTINCT FROM a.pharmacy_type
       OR d.linked_hospital_id IS DISTINCT FROM a.linked_hospital_id);

-- DimHospital (Type 1)
CREATE OR REPLACE TABLE etl_hospital_agg AS
SELECT trim(upper(hospitalid)) AS hospital_id, max(trim(hospitalname)) AS hospital_name,
       max(trim(hospitaltype)) AS hospital_type, max(trim(hospitalpharmacyid)) AS hospital_pharmacy_id,
       max(CAST(licensedbeds AS INTEGER)) AS licensed_beds, max(CAST(icubeds AS INTEGER)) AS icu_beds,
       max(CAST(averageoccupancyratepct AS INTEGER)) AS avg_occupancy_rate_pct,
       max(COALESCE(NULLIF(trim(traumalevel), ''), 'None')) AS trauma_level,
       max(CAST(catchmentpopulation AS INTEGER)) AS catchment_population
FROM etl_raw_hospital GROUP BY 1;

INSERT INTO dim_hospital
SELECT nextval('seq_hospital_key'), a.hospital_id, a.hospital_name, a.hospital_type, a.hospital_pharmacy_id,
       a.licensed_beds, a.icu_beds, a.avg_occupancy_rate_pct, a.trauma_level, a.catchment_population,
       CASE WHEN a.licensed_beds < 400 THEN 'Small' WHEN a.licensed_beds <= 700 THEN 'Medium' ELSE 'Large' END
FROM etl_hospital_agg a
WHERE NOT EXISTS (SELECT 1 FROM dim_hospital d WHERE d.hospital_id = a.hospital_id);

UPDATE dim_hospital AS d
SET hospital_name = a.hospital_name, hospital_type = a.hospital_type, licensed_beds = a.licensed_beds,
    icu_beds = a.icu_beds, avg_occupancy_rate_pct = a.avg_occupancy_rate_pct, trauma_level = a.trauma_level,
    catchment_population = a.catchment_population,
    bed_size_band = CASE WHEN a.licensed_beds < 400 THEN 'Small' WHEN a.licensed_beds <= 700 THEN 'Medium' ELSE 'Large' END
FROM etl_hospital_agg AS a
WHERE d.hospital_id = a.hospital_id
  AND (d.hospital_name IS DISTINCT FROM a.hospital_name OR d.hospital_type IS DISTINCT FROM a.hospital_type
       OR d.licensed_beds IS DISTINCT FROM a.licensed_beds OR d.icu_beds IS DISTINCT FROM a.icu_beds
       OR d.avg_occupancy_rate_pct IS DISTINCT FROM a.avg_occupancy_rate_pct
       OR d.trauma_level IS DISTINCT FROM a.trauma_level
       OR d.catchment_population IS DISTINCT FROM a.catchment_population);

-- DimSalesProfile (junk): only combinations not seen before
INSERT INTO dim_sales_profile (sales_profile_key, sales_channel, customer_segment, payer_type, payment_method,
       promotion_code, prescription_required_flag, ecommerce_delivery_status, sale_status, delivery_otif_flag)
SELECT nextval('seq_sales_profile_key'), p.sales_channel, p.customer_segment, p.payer_type, p.payment_method,
       p.promotion_code, p.rx_flag, p.ecom_status, p.sale_status, p.otif_flag
FROM (
  SELECT DISTINCT trim(saleschannel) AS sales_channel, trim(customersegment) AS customer_segment,
         trim(payertype) AS payer_type, trim(paymentmethod) AS payment_method,
         COALESCE(NULLIF(trim(promotioncode), ''), 'NONE') AS promotion_code,
         trim(prescriptionrequiredflag) AS rx_flag, trim(ecommercedeliverystatus) AS ecom_status,
         trim(salestatus) AS sale_status, trim(deliveryotifflag) AS otif_flag
  FROM etl_raw_sales
) p
WHERE NOT EXISTS (SELECT 1 FROM dim_sales_profile d
  WHERE d.sales_channel = p.sales_channel AND d.customer_segment = p.customer_segment
    AND d.payer_type = p.payer_type AND d.payment_method = p.payment_method
    AND d.promotion_code = p.promotion_code AND d.prescription_required_flag = p.rx_flag
    AND d.ecommerce_delivery_status = p.ecom_status AND d.sale_status = p.sale_status
    AND d.delivery_otif_flag = p.otif_flag);

-- DimDemandFlags (junk)
INSERT INTO dim_demand_flags (demand_flags_key, medication_request_status, formulary_status)
SELECT nextval('seq_demand_flags_key'), f.s, f.fs
FROM (SELECT DISTINCT trim(medicationrequeststatus) AS s, trim(formularystatus) AS fs FROM etl_raw_hospital) f
WHERE NOT EXISTS (SELECT 1 FROM dim_demand_flags d
                  WHERE d.medication_request_status = f.s AND d.formulary_status = f.fs);