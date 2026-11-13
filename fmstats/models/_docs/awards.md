{#- The game's awards and teams of the period. -#}

{% docs award_type %}
What an award is given to: `player`, `manager` (a Manager or Coach award), `team` (a team of
the period: Team of the Week, Team of the Year, Dream Team, Best XI ...), or `pool` (a World
Best XI pool from the scrapbook). Read from the award's name and from which awards have a
stored team.
{% enddocs %}

{% docs award_period %}
How often an award is decided: `week` (of the week, or of the round), `month`, or `season`
(once a year). A weekly or monthly award keeps only the current season's editions in a save.
{% enddocs %}

{% docs edition_date %}
The date the save gives an award's edition: 1 January of its year on an annual award; on a
monthly award the 1st of the month after the one it is for (September's Player of the Month
is dated 1 October); on a weekly award a Tuesday.
{% enddocs %}

{% docs place %}
The edition's place, 1st to 3rd, as the award screen lists them. On a voted award the score
does not decide it.
{% enddocs %}

{% docs score %}
The score an award place carries: votes on a voted award, goals on a Top Goalscorer, as stored
(0 on many awards).
{% enddocs %}

{% docs team_place %}
The player's place in a team of the period, 1 to 11, in the order the save stores the team.
{% enddocs %}

{% docs selection_rating %}
The rating that earned a player his place in a team of the period, 6.0 to 10.0, as stored.
{% enddocs %}

{% docs period_label %}
The period an award edition is for, as the award screen names it: the month on a monthly award
('September 2026'), the edition's date on a weekly one, the year on an annual one.
{% enddocs %}
