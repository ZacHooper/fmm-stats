-- The attribute decoder's training rows, one per (tid, entry_date): every
-- scrapbook entry -- our club's lists and the World Best XI pools alike --
-- paired with the player's attribute record on the snapshot nearest the
-- entry's date, at most var('attribute_label_max_gap_days') away. An entry is a
-- copy of the profile as it was on its date, so a pair is kept only while the
-- record still shows that profile: each of the seven attributes the record
-- holds as plain bytes (var('exact_single')) equals the entry's. That also
-- keeps a tid only while it names the same person (a tid is a slot, reused
-- after a retirement). An entry held by several lists or snapshots is one
-- row, from the latest copy. is_our_club: the entry is in our club's lists.
-- scripts/fit_attribute_model.py fits on it.
{%- set lists = var('club_lists') %}

with entries as (
    select
        player_tid as tid,
        entry_date,
        list between {{ lists[0] }} and {{ lists[1] }}
        or list = {{ var('club_all_time_list') }} as is_our_club,
        {% for attribute in var('attr_order') %}
        "{{ attribute }}"{% if not loop.last %},{% endif %}
        {% endfor %}
    from {{ ref('stg_scrapbook_entries') }}
    where player_tid is not null
    qualify row_number() over (
        partition by player_tid, entry_date
        order by snapshot_date desc, list asc
    ) = 1
)

select
    person.snapshot_date,
    entries.tid,
    entries.entry_date,
    abs(date_diff('day', entries.entry_date, person.snapshot_date))
        as gap_days,
    entries.is_our_club,
    {% for attribute in var('attr_order') %}
    entries."{{ attribute }}"{% if not loop.last %},{% endif %}
    {% endfor %}
from entries
inner join {{ ref('stg_persons') }} as person
    on entries.tid = person.tid
inner join {{ ref('stg_player_attributes') }} as record
    on
        person.snapshot_date = record.snapshot_date
        and person.sid = record.sid
where
    abs(date_diff('day', entries.entry_date, person.snapshot_date))
    <= {{ var('attribute_label_max_gap_days') }}
    {% for attribute in var('exact_single') %}
    and entries."{{ attribute }}" = record.{{ attribute | lower }}_src
    {% endfor %}
qualify row_number() over (
    partition by entries.tid, entries.entry_date
    order by gap_days asc, person.snapshot_date desc
) = 1
