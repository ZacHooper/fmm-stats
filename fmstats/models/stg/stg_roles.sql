-- Player roles by id, from seeds/roles.csv: the training Focus Role
-- (stg_training.focus_role) and the role a Scrapbook Profile shows, which is
-- the same thing on the entry's date. The ids run in position order (0-1 GK,
-- 2 SW, 3-4 full-back, 5-7 DC, 8-12 wide, 13-17 central midfield, 18-24
-- striker) and 25-32 follow as a second set. is_inferred marks a name given
-- by elimination, the role left over in its position block placed by its
-- holders' attributes, rather than one read off a Scrapbook Profile or the
-- Training page.
select
    id as role_id,
    name,
    inferred as is_inferred
from {{ source('raw', 'roles') }}
