{#- The old (season, phase) key of a snapshot, for the legacy models: join
    stg.snapshots as `snapshots` on snapshot_date. -#}
{% macro legacy_key() -%}
snapshots.season,
    strftime(snapshots.snapshot_date, '%Y-%m-%d') as phase
{%- endmacro %}

{% macro join_snapshots(alias) -%}
inner join {{ ref('stg_snapshots') }} as snapshots
    on {{ alias }}.snapshot_date = snapshots.snapshot_date
{%- endmacro %}
