-- mart.transfers on the new layers: one row per change of the team whose
-- books a player is on between two consecutive snapshots of his
-- (fact_player_snapshot), typed as the old view types it: internal (both
-- teams one club's), released (to no club), free_agent_signing (from none),
-- else transfer. A transfer's fee and date are fact_transfer's for the move
-- the change shows (its moved_by and buying club); a change no transfer
-- explains keeps the record's joined date where it lies between the two
-- snapshots. season and transfer_window keep the old view's calendar rule
-- (a move in June or later is for the next season).
with steps as (
    select
        player.person_id,
        player.tid,
        player.team_tid,
        player.club_tid,
        player.joined_date,
        player.snapshot_date,
        snapshots.phase,
        lag(player.team_tid) over w as prev_team_tid,
        lag(player.club_tid) over w as prev_club_tid,
        lag(player.snapshot_date) over w as prev_snapshot_date,
        lag(snapshots.phase) over w as prev_phase
    from {{ ref('fact_player_snapshot') }} as player
    inner join {{ ref('site_snapshots') }} as snapshots
        on player.snapshot_date = snapshots.phase_date
    window w as (partition by player.person_id order by player.snapshot_date)
),

moves as (
    select *
    from steps
    where
        prev_snapshot_date is not null
        and (team_tid is distinct from prev_team_tid)
),

typed as (
    select
        moves.*,
        transfers.fee_kind,
        transfers.fee_gbp as transfer_fee_gbp,
        transfers.transfer_type,
        transfers.person_id is not null as has_transfer,
        case
            when moves.club_tid = moves.prev_club_tid then 'internal'
            when moves.prev_team_tid is null then 'free_agent_signing'
            when moves.team_tid is null then 'released'
            else 'transfer'
        end as move_type,
        coalesce(
            transfers.move_date,
            case
                when
                    transfers.person_id is null
                    and moves.joined_date > moves.prev_snapshot_date
                    and moves.joined_date <= moves.snapshot_date
                    then moves.joined_date
            end
        ) as move_date
    from moves
    left join {{ ref('fact_transfer') }} as transfers
        on
            moves.person_id = transfers.person_id
            and moves.snapshot_date = transfers.moved_by
            and moves.club_tid = transfers.to_club_tid
            and moves.club_tid is distinct from moves.prev_club_tid
),

dated as (
    select
        *,
        coalesce(move_date, snapshot_date) as moved_on
    from typed
)

select
    typed.person_id,
    typed.tid,
    people.name,
    date_diff('year', people.dob, typed.moved_on) as age,
    typed.prev_team_tid as from_club_tid,
    from_teams.name as from_club,
    typed.team_tid as to_club_tid,
    to_teams.name as to_club,
    typed.move_date,
    typed.prev_phase as after_phase,
    typed.phase as by_phase,
    case
        when month(typed.moved_on) >= 6 then year(typed.moved_on) + 1
        else year(typed.moved_on)
    end as season,
    case
        when month(typed.moved_on) between 6 and 9 then 'summer'
        when month(typed.moved_on) in (12, 1, 2) then 'winter'
        else 'outside'
    end as transfer_window,
    typed.move_type,
    case
        when typed.fee_kind = 'fee'
            then cast(typed.transfer_fee_gbp // 1000 as varchar)
        when typed.fee_kind = 'contract_ended' then '65532'
        when typed.fee_kind in ('free', 'stay', 'loan') then typed.fee_kind
    end as fee_code,
    case
        when typed.move_type = 'internal' then 'none'
        when typed.move_type in ('free_agent_signing', 'released') then 'free'
        when typed.transfer_type = 'permanent' then 'fee'
        when typed.transfer_type = 'free' then 'free'
        else 'unknown'
    end as fee_type,
    case
        when typed.move_type in ('free_agent_signing', 'released') then 0
        when typed.move_type = 'transfer' then typed.transfer_fee_gbp
    end as fee_gbp
from dated as typed
inner join {{ ref('dim_person') }} as people
    on typed.person_id = people.person_id
left join {{ ref('dim_team') }} as from_teams
    on typed.prev_team_tid = from_teams.team_tid
left join {{ ref('dim_team') }} as to_teams
    on typed.team_tid = to_teams.team_tid
