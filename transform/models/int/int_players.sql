{#- A column of raw.players_raw is replaced where our squad's entry says otherwise; the
    player's squad status follows has_attributes, and the squad-entry columns and his current
    contract follow foot_right. Staff carry neither a squad status nor a contract. (The staff
    test sits in the columns, not in the joins' ON: a condition on the left table there turns
    DuckDB's hash join into a nested loop, 0.02 s -> 36 s.) The name ids are
    int.person_names'. -#}
{#- The SELECT list is built by walking raw.players_raw's columns in their stored order, so
    raw.players keeps that order and a column the loader adds passes straight through. -#}
{%- set cols = column_names(source('raw', 'players_raw')) -%}
{#- over: the raw columns whose value is replaced -- column name -> the SQL that replaces it.
    k is the player's squad entry (int.squad_scrapbook), n his display name, r his record. -#}
{%- set over = {
    'name': 'CASE WHEN ' ~ has_entry() ~ ' THEN k.full_name ELSE n.name END',
    'club_tid': 'CASE WHEN k.loaned_in THEN k.squad_club_tid ELSE r.club_tid END',
    'club': 'CASE WHEN k.loaned_in THEN k.squad_club ELSE r.club END',
    'foot_left': 'CASE WHEN ' ~ fresh_entry() ~ ' THEN k.foot_left ELSE r.foot_left END',
    'foot_right': 'CASE WHEN ' ~ fresh_entry() ~ ' THEN k.foot_right ELSE r.foot_right END',
} -%}
{#- added_after: new columns, each placed straight after the named raw column, as
    (new column, its SQL). t is his training row, c his current contract. -#}
{%- set added_after = {
    'has_attributes': [
        ('squad_status', 'CASE WHEN NOT r.is_staff THEN t.squad_status END')],
    'foot_right': [
        ('player_value', 'CASE WHEN ' ~ fresh_entry() ~ ' THEN k.value END'),
        ('loaned_in', 'COALESCE(k.loaned_in, FALSE)'),
        ('parent_club_tid', 'CASE WHEN k.loaned_in THEN k.own_club_tid END'),
        ('parent_club', 'CASE WHEN k.loaned_in THEN k.own_club END'),
        ('wage_units', 'CASE WHEN NOT r.is_staff THEN c.wage_units END'),
        ('wage_gbp', 'CASE WHEN NOT r.is_staff THEN CAST(c.wage_units AS BIGINT) * '
                     ~ var('wage_gbp_per_unit') ~ ' END'),
        ('contract_expiry', 'CASE WHEN NOT r.is_staff THEN c.expiry END'),
        ('contract_expiry_year',
         'CASE WHEN NOT r.is_staff THEN CAST(year(c.expiry) AS INTEGER) END')],
} -%}
{#- The walk: for each raw column (the three name ids are skipped; int.person_names owns them)
      1. emit it -- its `over` expression if it has one, else r."<column>" unchanged;
      2. then emit the new columns `added_after` places behind it;
      3. and after tid, emit the display name when players_raw has no `name` column of its own
         (a store loaded before the name ids has one, and step 1 replaces it in place).
    scrapbook_date goes last. `sel` collects the expressions; the SELECT joins them. -#}
{%- set sel = [] -%}
{%- for c in cols if c not in ('first_name_id', 'last_name_id', 'common_name_id') -%}
    {%- do sel.append(over[c] ~ ' AS "' ~ c ~ '"' if c in over else 'r."' ~ c ~ '"') -%}
    {%- for n, e in added_after.get(c, []) -%}{%- do sel.append(e ~ ' AS "' ~ n ~ '"') -%}{%- endfor -%}
    {%- if c == 'tid' and 'name' not in cols -%}{%- do sel.append(over['name'] ~ ' AS "name"') -%}{%- endif -%}
{%- endfor -%}
{%- do sel.append('CASE WHEN ' ~ fresh_entry() ~ ' THEN k.scrapbook_date END AS "scrapbook_date"') -%}
SELECT {{ sel | join(',\n       ') }}
FROM {{ source('raw', 'players_raw') }} r
LEFT JOIN {{ ref('int_squad_scrapbook') }} k
       ON k.season = r.season AND k.phase = r.phase AND k.tid = r.tid
LEFT JOIN {{ ref('int_person_names') }} n
       ON n.season = r.season AND n.phase = r.phase AND n.tid = r.tid
LEFT JOIN {{ ref('stg_training') }} t
       ON t.season = r.season AND t.phase = r.phase AND t.tid = r.tid
LEFT JOIN {{ ref('stg_contracts') }} c
       ON c.season = r.season AND c.phase = r.phase AND c.tid = r.tid AND c.is_current
