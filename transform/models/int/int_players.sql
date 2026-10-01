-- Each person's own record, with our squad's values in place: for a player in
-- our squad arrays the name from his latest entry, and his feet and value from
-- it while it is fresh (fresh_entry); a loanee is listed under our club. The
-- player's squad status follows has_attributes and his current contract
-- follows foot_right; staff carry neither. The staff test sits in the columns,
-- not in the joins: a condition on the left table in a join's ON turns DuckDB's
-- hash join into a nested loop (0.02 s -> 36 s). The columns follow
-- raw.players_raw's, so a column the loader adds passes straight through; the
-- name ids are int.person_names'.
{%- set columns = column_names(source('raw', 'players_raw')) %}
{%- set name_ids = ['first_name_id', 'last_name_id', 'common_name_id'] %}
{%- set display_name %}
    case
        when entry.scrapbook_date is not null then entry.full_name
        else person_names.name
    end as name
{%- endset %}

-- The select list walks raw.players_raw's columns in their stored order (the
-- three name ids are skipped): a column with a branch below is replaced in
-- place, and the new columns sit straight after the raw column they belong
-- with -- squad status after has_attributes, the value, loan and contract
-- columns after foot_right. Any other column passes through as
-- record."<column>". After tid comes the display name, unless players_raw has
-- its own `name` column (a store loaded before the name ids), which the `name`
-- branch replaces in place.
select
    {% for column in columns if column not in name_ids %}
    {% if column == 'name' %}
    {{ display_name }},
    {% elif column == 'club_tid' %}
    case
        when entry.loaned_in then entry.squad_club_tid else record.club_tid
    end as club_tid,
    {% elif column == 'club' %}
    case
        when entry.loaned_in then entry.squad_club else record.club
    end as club,
    {% elif column == 'foot_left' %}
    case
        when {{ fresh_entry() }} then entry.foot_left else record.foot_left
    end as foot_left,
    {% elif column == 'foot_right' %}
    case
        when {{ fresh_entry() }} then entry.foot_right else record.foot_right
    end as foot_right,
    case when {{ fresh_entry() }} then entry.value end as player_value,
    coalesce(entry.loaned_in, false) as loaned_in,
    case when entry.loaned_in then entry.own_club_tid end as parent_club_tid,
    case when entry.loaned_in then entry.own_club end as parent_club,
    case
        when not record.is_staff then contracts.wage_units
    end as wage_units,
    case
        when not record.is_staff
            then
                cast(contracts.wage_units as bigint)
                * {{ var('wage_gbp_per_unit') }}
    end as wage_gbp,
    case
        when not record.is_staff then contracts.expiry
    end as contract_expiry,
    case
        when not record.is_staff then cast(year(contracts.expiry) as integer)
    end as contract_expiry_year,
    {% elif column == 'has_attributes' %}
    record.has_attributes,
    case
        when not record.is_staff then training.squad_status
    end as squad_status,
    {% else %}
    record."{{ column }}",
    {% endif %}
    {% if column == 'tid' and 'name' not in columns %}
    {{ display_name }},
    {% endif %}
    {% endfor %}
    case
        when {{ fresh_entry() }} then entry.scrapbook_date
    end as scrapbook_date
from {{ source('raw', 'players_raw') }} as record
left join {{ ref('int_squad_scrapbook') }} as entry
    on
        record.season = entry.season
        and record.phase = entry.phase
        and record.tid = entry.tid
left join {{ ref('int_person_names') }} as person_names
    on
        record.season = person_names.season
        and record.phase = person_names.phase
        and record.tid = person_names.tid
left join {{ ref('stg_training') }} as training
    on
        record.season = training.season
        and record.phase = training.phase
        and record.tid = training.tid
left join {{ ref('stg_contracts') }} as contracts
    on
        record.season = contracts.season
        and record.phase = contracts.phase
        and record.tid = contracts.tid
        and contracts.is_current
