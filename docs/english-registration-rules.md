# English squad registration — the rules the `england` rule set encodes

A house rule: the game models none of this. A career with `registration = "england"` in
`fmm.toml` has its Squad page count the squad against these rules
(`seeds/registration_rules.csv`, rule set `england`), with the row picked by the managed
league's tier as the save numbers it: **3** League One, **4** League Two, **5** National
League, **6** National League North and South (`site.leagues.tier`, read in a Truro store).
The Premier League and the Championship (tiers 1–2) have no row yet: the Squad page's
registration card is hidden there until one is added.

**Sources are 2024/25 and 2025/26 club and press summaries, not the EFL Handbook itself**, which
was not found online. Check them against the current Handbook before relying on a borderline
case, and update the seed and this page together.

## League One and League Two (tiers 3–4)

| rule | value | seed column |
|---|---|---|
| Squad list | at most **22** players | `list_max` |
| Home grown on the list | at least **8** | `hg_min` |
| Trained at the club | no separate minimum | `hg_club_min = 0` |
| Under-21s | unlimited, need not be listed | `free_under_age = 21` |
| Under-21 cut-off | born on or after **1 January** 21 years before the season's first year (2025/26: born on or after 1 January 2004) | `free_born_from = 01-01` |
| Goalkeepers | need not be listed, at any age | `free_gk = true` |
| Matchday squad | 11 + 7 substitutes, at least **7 home grown** | `matchday_subs`, `matchday_hg_min` |
| Loans in a matchday squad | at most **5** (4 if one is an emergency goalkeeper loan) | `matchday_loan_max` |
| Loans from one club | at most **4** | `loan_max_per_club` |

- **Home grown** (EFL): registered with a club affiliated to the **FA or the FAW** for three
  seasons or 36 months before his 21st birthday (or the end of the season he turns 21),
  whatever his nationality. Welsh clubs count, so the rule set's home-grown nations are
  `England|Wales` (`hg_nations`): a player trained at Penybont is home grown. The site
  measures the months in the same window as the Danish rule
  (`home_grown_window_ages` in `fmstats/dbt_project.yml`: from the season he turns 15 to the end
  of the season he turns 22, one season longer than the rulebook, so the birthday does not decide
  a borderline case); the EFL rule names no start age, but registration before 15 is rare in the
  save.
- **Loanees.** One summary says every loanee must be listed whatever his age; the EFL text quoted
  in another ("in respect of League One Clubs and League Two Clubs any Under 21 Players need not
  be included in the squad list") does not except loans, and that is what the rule set does: a
  young loanee is exempt like any under-21. The Championship's exemption explicitly excludes
  loans; Leagues One and Two's does not appear to.
- One older source caps loanees **over 23** at two; it is not in the 2024/25 summaries and is not
  encoded.

## National League (tier 5) and North / South (tier 6)

| rule | National League | North / South |
|---|---|---|
| Squad list cap | none | none |
| Home-grown minimum | none | none |
| Matchday squad | 11 + 7 | 11 + 5 |
| Loans in a matchday squad | at most 5 | at most 5 (an older source) |

With no cap the Squad page still counts the list, its home-grown players and the loans, so a
club below League Two can see where it stands; its **Count as** picker recounts the same plan
against League Two's or League One's rules.

## Sources

- [FourFourTwo, EFL squad rules 2024/25](https://fourfourtwo.com/features/what-are-the-efl-squad-rules-for-202425-loanee-limits-home-grown-players-and-how-many-subs-are-allowed)
- [Bristol Rovers, 2025/26 squad list confirmed](https://www.bristolrovers.co.uk/news/202526-squad-list-confirmed): 22-man list, under-21s born on or after 1 January 2004, goalkeepers and under-21s need not be named
- [Exeter City, squad list](https://www.exetercityfc.co.uk/squad-list): at most 22, including 8 home grown
- [The Star, EFL loan rules](https://www.thestar.co.uk/sport/football/sheffield-wednesday/the-efl-loan-rules-sheffield-wednesday-must-follow-3326636)
- [National League rule changes, 2024](https://bullsnews.blogspot.com/2024/08/major-change-to-national-league-rules.html)
- [National League, loan limit](https://www.thenationalleague.org.uk/no-transfer-window-in-national-league-31421)
