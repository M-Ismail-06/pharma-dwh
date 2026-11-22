-- FactPharmacySales: new transactions only, ordered by date
INSERT INTO fact_pharmacy_sales (
  sales_key, sales_transaction_id, sales_date_key, delivery_date_key, batch_expiry_date_key,
  medicine_key, pharmacy_key, hospital_key, geography_key, sales_profile_key,
  pharmacy_order_id, pharmacy_delivery_id, warehouse_lot_id, production_batch_id, source_warehouse_id,
  prescription_id, sales_timestamp_utc, quantity_sold_packs, returned_quantity_packs, unit_retail_price_usd,
  gross_sales_usd, discount_amount_usd, net_sales_usd, sales_tax_usd, cost_of_goods_sold_usd,
  gross_margin_usd, manufacturing_cost_usd, delivery_quantity_packs, days_to_expiry_at_sale, batch_id)
WITH s AS (
  SELECT
    trim(salestransactionid) AS txn_id,
    CAST(strptime(salesdate, '%d-%m-%y') AS DATE) AS sales_date,
    CAST(strptime(pharmacydeliverydate, '%d-%m-%y') AS DATE) AS delivery_date,
    CAST(strptime(batchexpirydate, '%d-%m-%y') AS DATE) AS expiry_date,
    CAST(replace(replace(salestimestamputc, 'T', ' '), 'Z', '') AS TIMESTAMP) AS sales_ts,
    trim(upper(medicineid)) AS medicine_id, trim(upper(pharmacyid)) AS pharmacy_id,
    NULLIF(trim(hospitalid), '') AS hospital_id,
    trim(pharmacycity) AS city, trim(pharmacystate) AS state, trim(countrycode) AS country_code,
    trim(saleschannel) AS sales_channel, trim(customersegment) AS customer_segment,
    trim(payertype) AS payer_type, trim(paymentmethod) AS payment_method,
    COALESCE(NULLIF(trim(promotioncode), ''), 'NONE') AS promotion_code,
    trim(prescriptionrequiredflag) AS rx_flag, trim(ecommercedeliverystatus) AS ecom_status,
    trim(salestatus) AS sale_status, trim(deliveryotifflag) AS otif_flag,
    trim(pharmacyorderid) AS order_id, trim(pharmacydeliveryid) AS delivery_id,
    trim(warehouselotid) AS lot_id, trim(productionbatchid) AS prod_batch_id,
    trim(sourcewarehouseid) AS warehouse_id, NULLIF(trim(prescriptionid), '') AS rx_id,
    CAST(quantitysoldpacks AS INTEGER) AS qty, CAST(returnedquantitypacks AS INTEGER) AS returned_qty,
    CAST(unitretailpriceusd AS DECIMAL(10,2)) AS unit_price,
    CAST(grosssalesamountusd AS DECIMAL(12,2)) AS gross, CAST(discountamountusd AS DECIMAL(12,2)) AS discount,
    CAST(netsalesamountusd AS DECIMAL(12,2)) AS net, CAST(salestaxusd AS DECIMAL(12,2)) AS tax,
    CAST(costofgoodssoldusd AS DECIMAL(12,2)) AS cogs, CAST(grossmarginusd AS DECIMAL(12,2)) AS margin,
    CAST(deliveryquantitypacks AS INTEGER) AS delivery_qty,
    CAST(daystoexpiryatsale AS INTEGER) AS days_to_expiry, batch_id
  FROM etl_raw_sales r
  WHERE NOT EXISTS (SELECT 1 FROM fact_pharmacy_sales f WHERE f.sales_transaction_id = trim(r.salestransactionid))
)
SELECT nextval('seq_sales_key'), j.* FROM (
  SELECT s.txn_id,
    CAST(strftime(s.sales_date, '%Y%m%d') AS INTEGER),
    CAST(strftime(s.delivery_date, '%Y%m%d') AS INTEGER),
    CAST(strftime(s.expiry_date, '%Y%m%d') AS INTEGER),
    COALESCE(m.medicine_key, mf.medicine_key, -1),
    COALESCE(p.pharmacy_key, -1), COALESCE(h.hospital_key, -1),
    COALESCE(g.geography_key, -1), COALESCE(sp.sales_profile_key, -1),
    s.order_id, s.delivery_id, s.lot_id, s.prod_batch_id, s.warehouse_id, s.rx_id,
    s.sales_ts, s.qty, s.returned_qty, s.unit_price,
    s.gross, s.discount, s.net, s.tax, s.cogs, s.margin,
    CAST(s.qty * COALESCE(m.unit_manufacturing_cost_usd, mf.unit_manufacturing_cost_usd) AS DECIMAL(12,2)),
    s.delivery_qty, s.days_to_expiry, s.batch_id
  FROM s
  LEFT JOIN dim_medicine m ON m.medicine_id = s.medicine_id AND m.medicine_key > 0
        AND s.sales_date >= m.valid_from AND s.sales_date < m.valid_to
  LEFT JOIN v_medicine_first mf ON mf.medicine_id = s.medicine_id
  LEFT JOIN dim_pharmacy p ON p.pharmacy_id = s.pharmacy_id
  LEFT JOIN dim_hospital h ON h.hospital_id = s.hospital_id
  LEFT JOIN dim_geography g ON g.city = s.city AND g.state = s.state AND g.country_code = s.country_code
  LEFT JOIN dim_sales_profile sp ON sp.sales_channel = s.sales_channel AND sp.customer_segment = s.customer_segment
        AND sp.payer_type = s.payer_type AND sp.payment_method = s.payment_method
        AND sp.promotion_code = s.promotion_code AND sp.prescription_required_flag = s.rx_flag
        AND sp.ecommerce_delivery_status = s.ecom_status AND sp.sale_status = s.sale_status
        AND sp.delivery_otif_flag = s.otif_flag
  ORDER BY s.sales_date, s.txn_id
) j;

-- FactHospitalDemand
INSERT INTO fact_hospital_demand (
  hospital_demand_key, hospital_demand_record_id, demand_month_date_key, hospital_key, medicine_key,
  geography_key, demand_flags_key, estimated_disease_cases, disease_related_admissions, outpatient_encounters,
  forecast_demand_packs, requested_quantity_packs, approved_quantity_packs, received_quantity_packs,
  emergency_request_quantity_packs, opening_stock_packs, dispensed_quantity_packs, consumed_quantity_packs,
  wastage_quantity_packs, closing_stock_packs, unfulfilled_demand_packs, stockout_days, service_level_pct,
  average_lead_time_days, demand_trend_index, forecast_error_packs, batch_id)
WITH h AS (
  SELECT
    trim(hospitaldemandrecordid) AS record_id,
    CAST(strptime(demandmonth, '%d-%m-%y') AS DATE) AS demand_month,
    trim(upper(hospitalid)) AS hospital_id, trim(upper(medicineid)) AS medicine_id,
    trim(city) AS city, trim(state) AS state, trim(countrycode) AS country_code,
    trim(medicationrequeststatus) AS req_status, trim(formularystatus) AS formulary_status,
    CAST(estimateddiseasecases AS INTEGER) AS cases, CAST(diseaserelatedadmissions AS INTEGER) AS admissions,
    CAST(outpatientencounters AS INTEGER) AS outpatient, CAST(forecastdemandpacks AS INTEGER) AS forecast,
    CAST(requestedquantitypacks AS INTEGER) AS requested, CAST(approvedquantitypacks AS INTEGER) AS approved,
    CAST(receivedquantitypacks AS INTEGER) AS received, CAST(emergencyrequestquantitypacks AS INTEGER) AS emergency,
    CAST(openingstockpacks AS INTEGER) AS opening, CAST(dispensedquantitypacks AS INTEGER) AS dispensed,
    CAST(consumedquantitypacks AS INTEGER) AS consumed, CAST(wastagequantitypacks AS INTEGER) AS wastage,
    CAST(closingstockpacks AS INTEGER) AS closing, CAST(unfulfilleddemandpacks AS INTEGER) AS unfulfilled,
    CAST(stockoutdays AS INTEGER) AS stockout_days, CAST(servicelevelpct AS DECIMAL(5,2)) AS service_level,
    CAST(averageleadtimedays AS INTEGER) AS lead_time, CAST(demandtrendindex AS DECIMAL(6,3)) AS trend_index,
    batch_id
  FROM etl_raw_hospital r
  WHERE NOT EXISTS (SELECT 1 FROM fact_hospital_demand f WHERE f.hospital_demand_record_id = trim(r.hospitaldemandrecordid))
)
SELECT nextval('seq_hospital_demand_key'), j.* FROM (
  SELECT h.record_id,
    CAST(strftime(h.demand_month, '%Y%m%d') AS INTEGER),
    COALESCE(dh.hospital_key, -1),
    COALESCE(m.medicine_key, mf.medicine_key, -1),
    COALESCE(g.geography_key, -1), COALESCE(fl.demand_flags_key, -1),
    h.cases, h.admissions, h.outpatient, h.forecast, h.requested, h.approved, h.received, h.emergency,
    h.opening, h.dispensed, h.consumed, h.wastage, h.closing, h.unfulfilled, h.stockout_days,
    h.service_level, h.lead_time, h.trend_index, h.consumed - h.forecast, h.batch_id
  FROM h
  LEFT JOIN dim_hospital dh ON dh.hospital_id = h.hospital_id
  LEFT JOIN dim_medicine m ON m.medicine_id = h.medicine_id AND m.medicine_key > 0
        AND h.demand_month >= m.valid_from AND h.demand_month < m.valid_to
  LEFT JOIN v_medicine_first mf ON mf.medicine_id = h.medicine_id
  LEFT JOIN dim_geography g ON g.city = h.city AND g.state = h.state AND g.country_code = h.country_code
  LEFT JOIN dim_demand_flags fl ON fl.medication_request_status = h.req_status AND fl.formulary_status = h.formulary_status
  ORDER BY h.demand_month, h.record_id
) j;