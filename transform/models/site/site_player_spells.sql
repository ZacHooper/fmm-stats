-- mart.player_spells on the new layers: the four spell views in one. Spells
-- of different types may overlap (injured while out on loan).
{% for spells in ['site_at_club_spells', 'site_loan_in_spells',
                  'site_loan_out_spells', 'site_injury_spells'] %}
select
    person_id,
    tid,
    name,
    spell_type,
    club_tid,
    club,
    season,
    valid_from,
    valid_to,
    arrival_window
from {{ ref(spells) }}
{% if not loop.last %}union all{% endif %}
{% endfor %}
