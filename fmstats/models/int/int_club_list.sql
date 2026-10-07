-- Each club once, as its latest snapshot gives it.
{{ latest(ref('int_club_snapshots'), 'club_tid') }}
