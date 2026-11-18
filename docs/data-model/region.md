# Regional strength

How good each region of the career's home nation is at football, measured three ways so a
career can watch one region grow (Truro: the South West). A region is the game's own
(`dim_region`: South-West, London, ...); a club's region is its ground's city's, a player's is
his origin club's. The scores group by `dim_home_region`: the home nation's regions, plus one
row per other nation whose clubs play in its leagues (Wales, for Cardiff, Swansea, Newport,
Wrexham and Merthyr in England), keyed by the negated nation id. Counties are not in the save; they would replace the region key without
changing anything below it.

## The ruler: tier levels
`fact_tier_level_snapshot`, per snapshot and tier of the home nation's men's leagues (reserve
and women's leagues left out). A tier's level is the median CA of its teams' best 14 players,
every nationality counted. A tier is **scored** when its leagues have matches in the store: the
game plays out only the top of the pyramid (England: Premier League to National League
North/South). `tier_weight` is a tier's level above the first unscored tier's, over the lowest
scored tier's, so the lowest scored tier weighs 1 and the gaps follow the data (England's top
step is the widest).

## Clubs: Elo
`fact_club_elo` (a Python model) rates every team in the home nation's leagues match by
match, league and cup. A team is seeded on its first snapshot at
`base + per_level_point x (its tier's level - the lowest scored tier's)`; a match moves both
sides by `k x margin x (result - expected)`. Settings are `var('region_elo')`, chosen by how
well the ratings predict results (Brier score): wider starting gaps between tiers predict
better up to 14-16 points per level point, and a smaller k predicts worse, so a club's form
moves its rating fast but the tiers start far enough apart that a run of wins doesn't carry
a club past the tier above in half a season.
`fact_club_region_snapshot` gives each team's rating, tier, facilities and region on each
snapshot; `fact_region_snapshot` aggregates a region's scored-tier teams: mean, median, best
three, and the share above the nation's 75th percentile, plus facilities.

## Players: levels and appearances
`fact_player_origin_snapshot` places every player from the nation's youth systems by region,
with the highest scored tier whose level he reaches (`level_tier`).
`fact_region_level_snapshot` counts them at each tier's level or better, all ages and
under-21s. `fact_region_season` sums their appearances for scored-tier teams each season,
weighted by tier.

## Progress
Every count carries the region's share of the nation's (`nation_share`) and that share over
the region's first (`nation_share_index`): the size of a region cancels out, so London's volume
does not hide the South West's growth. CA stays inside the warehouse; presentation carries the
weights, counts and shares only.

## On the site
The World page's **Regions** tab (`site.region_*`, `world.json`'s `regions`): our region's
tiles, then Clubs (Elo and facilities by region), Players (counts at each division's level,
all ages or under-21s), Appearances (tier-weighted, by season) and Club Elo (every club, with
its rating over time).
