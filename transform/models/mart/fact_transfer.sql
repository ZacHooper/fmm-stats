-- Every permanent move between clubs, keyed (person_id, to_line_index): from
-- the career history, and the club on the newest snapshot for a move the
-- history has no line for yet (int.transfers for the rules). from_club_tid is
-- NULL for a free agent signed. Club level: first team <-> reserves is no move,
-- and which team he joins is on fact_player_snapshot. moved_after / moved_by
-- bound a move made while the store was watching, and move_date is the day he
-- joined where the save gives it; was_free_agent, that he had no club on
-- moved_after. The two contracts a bounded move ends and
-- starts are named by their first_seen_date (fact_contract).
with transfers as (
    select * from {{ ref('int_transfers') }}
),

contracts as (
    select * from {{ ref('int_contracts') }}
)

select
    transfers.person_id,
    transfers.to_line_index,
    transfers.from_club_tid,
    transfers.to_club_tid,
    transfers.season,
    transfers.moved_after,
    transfers.moved_by,
    transfers.move_date,
    transfers.was_free_agent,
    transfers.transfer_type,
    transfers.fee_gbp,
    transfers.fee_kind,
    transfers.is_from_snapshot,
    ended.first_seen_date as ended_contract_first_seen_date,
    started.first_seen_date as new_contract_first_seen_date
from transfers
left join contracts as ended
    on
        transfers.person_id = ended.person_id
        and transfers.moved_after = ended.last_seen_date
        and transfers.from_club_tid = ended.club_tid
left join contracts as started
    on
        transfers.person_id = started.person_id
        and transfers.moved_by = started.first_seen_date
        and transfers.to_club_tid = started.club_tid
