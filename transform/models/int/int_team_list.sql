-- Each team once, as its latest snapshot gives it: its club and team type.
{{ latest(ref('int_teams'), 'team_tid') }}
