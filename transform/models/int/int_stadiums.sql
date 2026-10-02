-- Each stadium once, as its latest snapshot gives it (capacity included).
{{ latest(ref('stg_stadiums'), 'stadium_id') }}
