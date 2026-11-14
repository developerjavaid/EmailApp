-- Run in Databricks SQL editor / notebook to standardize column names
-- on the table created via the Catalog Explorer CSV upload, so they
-- match the snake_case names used by load_leads_csv.py.
--
-- Source names below are the CSV headers lowercased as-is (what Databricks
-- produces on upload); only columns that actually need renaming are listed.
-- If DESCRIBE TABLE shows different source names, adjust accordingly.

ALTER TABLE claraport_ws.viasmiles_campaigns.lead RENAME COLUMN prefixttl TO prefix_ttl;
ALTER TABLE claraport_ws.viasmiles_campaigns.lead RENAME COLUMN individualname TO individual_name;
ALTER TABLE claraport_ws.viasmiles_campaigns.lead RENAME COLUMN firstname TO first_name;
ALTER TABLE claraport_ws.viasmiles_campaigns.lead RENAME COLUMN middlename TO middle_name;
ALTER TABLE claraport_ws.viasmiles_campaigns.lead RENAME COLUMN lastname TO last_name;
ALTER TABLE claraport_ws.viasmiles_campaigns.lead RENAME COLUMN address2line TO address2_line;
ALTER TABLE claraport_ws.viasmiles_campaigns.lead RENAME COLUMN confidencecode TO confidence_code;
ALTER TABLE claraport_ws.viasmiles_campaigns.lead RENAME COLUMN ageofindividual TO age_of_individual;
ALTER TABLE claraport_ws.viasmiles_campaigns.lead RENAME COLUMN estimatedincomehigherranges TO estimated_income_higher_ranges;
ALTER TABLE claraport_ws.viasmiles_campaigns.lead RENAME COLUMN businessowner TO business_owner;

-- The following CSV columns already come out matching the script's
-- snake_case target and need no rename: address, city, state, zip, zip4,
-- dpbc, keycode, ukeycode1, fips_county_name, itacomb, gender, email,
-- ibe2359, ibe2359_description, autowork, boating, fash, fishing, golf,
-- grchld, owndog, photogr, rlestinv, selfimpr, snowskiing, stocksbond,
-- swpcont, vacationtravel_rv, aviation, beautyandcosmetics, health_medical,
-- history_military, investing_financegrouping, nascar, equestrian, tennis,
-- spectatorsports_hockey, theater_performingarts, travelgrouping,
-- homeownren, hownrenfl.
