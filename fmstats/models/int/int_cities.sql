-- Each city once, as its latest snapshot gives it. The save stores no city
-- name in the city record.
{{ latest(ref('stg_cities'), 'city_id') }}
