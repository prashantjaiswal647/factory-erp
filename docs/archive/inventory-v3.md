# Inventory v3

Inventory v3 uses the backend `bucket` field as the only classification source for the Live Inventory page.

## Canonical buckets

- `cup_blanks`
- `bottom_reels`
- `finished_goods`
- `polybags_packing`
- `boxes`
- `raw_other`
- `needs_mapping_review`

Generic `Inventory` rows map `Packaging` to `polybags_packing`, `Raw` to `raw_other`, and any null or unknown category to `needs_mapping_review`. The API keeps `stock_type=Inventory`; the frontend does not infer a bucket from names, categories, or substring matching.

## Page hierarchy

The page shows content categories first: Raw Materials, Finished Goods, Packaging, Boxes, and Other Inventory. The Critical & Low Stock section is a derived operational view placed last. KPI and risk counts are calculated from the same canonical rows.

All API reads remain scoped by the authenticated user's `factory_id`.
