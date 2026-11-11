{# The 23 displayed attributes, the nine hidden ones and the eight personality values, each
   1-20 (int.player_attributes; docs/attribute-model.md for the decoder). The displayed
   attributes keep the game's capitalised names. #}

{% docs aerial %}
Aerial, 1-20: stated by a fresh scrapbook entry, else a closed form over heading and jumping
(`var('composites')`) that matches the stated value about 71% of the time.
{% enddocs %}

{% docs crossing %}
Crossing, 1-20. Where no fresh scrapbook entry states it (everyone outside our squad), it is
decoded from the attribute record (`has_estimated_attributes`; docs/attribute-model.md), and can
be off by one or more.
{% enddocs %}

{% docs dribbling %}
Dribbling, 1-20. Where no fresh scrapbook entry states it (everyone outside our squad), it is
decoded from the attribute record (`has_estimated_attributes`; docs/attribute-model.md), and can
be off by one or more.
{% enddocs %}

{% docs shooting %}
Shooting, 1-20. Where no fresh scrapbook entry states it (everyone outside our squad), it is
decoded from the attribute record (`has_estimated_attributes`; docs/attribute-model.md), and can
be off by one or more.
{% enddocs %}

{% docs passing %}
Passing, 1-20. Where no fresh scrapbook entry states it (everyone outside our squad), it is
decoded from the attribute record (`has_estimated_attributes`; docs/attribute-model.md), and can
be off by one or more.
{% enddocs %}

{% docs tackling %}
Tackling, 1-20. Where no fresh scrapbook entry states it (everyone outside our squad), it is
decoded from the attribute record (`has_estimated_attributes`; docs/attribute-model.md), and can
be off by one or more.
{% enddocs %}

{% docs technique %}
Technique, 1-20: read from the attribute record, exact for every player.
{% enddocs %}

{% docs aggression %}
Aggression, 1-20: read from the attribute record, exact for every player.
{% enddocs %}

{% docs creativity %}
Creativity, 1-20. Where no fresh scrapbook entry states it (everyone outside our squad), it is
decoded from the attribute record (`has_estimated_attributes`; docs/attribute-model.md), and can
be off by one or more.
{% enddocs %}

{% docs decisions %}
Decisions, 1-20. Where no fresh scrapbook entry states it (everyone outside our squad), it is
decoded from the attribute record (`has_estimated_attributes`; docs/attribute-model.md), and can
be off by one or more.
{% enddocs %}

{% docs leadership %}
Leadership, 1-20: read from the attribute record, exact for every player.
{% enddocs %}

{% docs movement %}
Movement, 1-20. Where no fresh scrapbook entry states it (everyone outside our squad), it is
decoded from the attribute record (`has_estimated_attributes`; docs/attribute-model.md), and can
be off by one or more.
{% enddocs %}

{% docs positioning %}
Positioning, 1-20. Where no fresh scrapbook entry states it (everyone outside our squad), it is
decoded from the attribute record (`has_estimated_attributes`; docs/attribute-model.md), and can
be off by one or more.
{% enddocs %}

{% docs teamwork %}
Teamwork, 1-20: a closed form over two record bytes (unselfishness and work rate,
`var('composites')`), exact for every player.
{% enddocs %}

{% docs pace %}
Pace, 1-20: read from the attribute record, exact for every player.
{% enddocs %}

{% docs stamina %}
Stamina, 1-20: read from the attribute record, exact for every player.
{% enddocs %}

{% docs strength %}
Strength, 1-20: read from the attribute record, exact for every player.
{% enddocs %}

{% docs agility %}
Agility, 1-20: read from the attribute record, exact for every player.
{% enddocs %}

{% docs handling %}
Handling, 1-20, a goalkeeping attribute (an outfield player sits at the floor). Where no fresh
scrapbook entry states it (everyone outside our squad), it is decoded from the attribute record
(`has_estimated_attributes`; docs/attribute-model.md), and can be off by one or more.
{% enddocs %}

{% docs kicking %}
Kicking, 1-20, a goalkeeping attribute (an outfield player sits at the floor). Where no fresh
scrapbook entry states it (everyone outside our squad), it is decoded from the attribute record
(`has_estimated_attributes`; docs/attribute-model.md), and can be off by one or more.
{% enddocs %}

{% docs reflexes %}
Reflexes, 1-20, a goalkeeping attribute (an outfield player sits at the floor). Where no fresh
scrapbook entry states it (everyone outside our squad), it is decoded from the attribute record
(`has_estimated_attributes`; docs/attribute-model.md), and can be off by one or more.
{% enddocs %}

{% docs communication %}
Communication, 1-20, a goalkeeping attribute (an outfield player sits at the floor). Where no
fresh scrapbook entry states it (everyone outside our squad), it is decoded from the attribute
record (`has_estimated_attributes`; docs/attribute-model.md), and can be off by one or more.
{% enddocs %}

{% docs throwing %}
Throwing, 1-20, a goalkeeping attribute (an outfield player sits at the floor). Where no fresh
scrapbook entry states it (everyone outside our squad), it is decoded from the attribute record
(`has_estimated_attributes`; docs/attribute-model.md), and can be off by one or more.
{% enddocs %}

{% docs jumping %}
Jumping, a hidden attribute, 1-20 as the record stores it; the game never shows the number. Say
what the in-game report would say (docs/agent-context/report-trait-lines.md).
{% enddocs %}

{% docs consistency %}
Consistency, a hidden attribute, 1-20 as the record stores it; the game never shows the number.
Say what the in-game report would say (docs/agent-context/report-trait-lines.md).
{% enddocs %}

{% docs big_match %}
Big-match temperament ("thrives in big matches"), a hidden attribute, 1-20 as the record stores
it; the game never shows the number. Say what the in-game report would say
(docs/agent-context/report-trait-lines.md).
{% enddocs %}

{% docs injury_prone %}
Injury proneness, a hidden attribute, 1-20 as the record stores it; the game never shows the
number. Say what the in-game report would say (docs/agent-context/report-trait-lines.md).
{% enddocs %}

{% docs versatility %}
Versatility, a hidden attribute, 1-20 as the record stores it; the game never shows the number.
Say what the in-game report would say (docs/agent-context/report-trait-lines.md).
{% enddocs %}

{% docs set_pieces %}
Set pieces, a hidden attribute, 1-20 as the record stores it; the game never shows the number.
Say what the in-game report would say (docs/agent-context/report-trait-lines.md).
{% enddocs %}

{% docs penalty %}
Penalty taking, a hidden attribute, 1-20 as the record stores it; the game never shows the
number. Say what the in-game report would say (docs/agent-context/report-trait-lines.md).
{% enddocs %}

{% docs work_rate %}
Work rate, a hidden attribute, 1-20 as the record stores it; the game never shows the number.
Say what the in-game report would say (docs/agent-context/report-trait-lines.md).
{% enddocs %}

{% docs flair %}
Flair, a hidden attribute, 1-20 as the record stores it; the game never shows the number. Say
what the in-game report would say (docs/agent-context/report-trait-lines.md).
{% enddocs %}

{% docs adaptability %}
Adaptability, a personality value, 1-20 as the person record stores it (the game shows a
personality word, not the number).
{% enddocs %}

{% docs ambition %}
Ambition, a personality value, 1-20 as the person record stores it (the game shows a personality
word, not the number).
{% enddocs %}

{% docs determination %}
Determination, a personality value, 1-20 as the person record stores it (the game shows a
personality word, not the number).
{% enddocs %}

{% docs loyalty %}
Loyalty, a personality value, 1-20 as the person record stores it (the game shows a personality
word, not the number).
{% enddocs %}

{% docs pressure %}
Pressure, a personality value, 1-20 as the person record stores it (the game shows a personality
word, not the number).
{% enddocs %}

{% docs professionalism %}
Professionalism, a personality value, 1-20 as the person record stores it (the game shows a
personality word, not the number).
{% enddocs %}

{% docs sportsmanship %}
Sportsmanship, a personality value, 1-20 as the person record stores it (the game shows a
personality word, not the number).
{% enddocs %}

{% docs temperament %}
Temperament, a personality value, 1-20 as the person record stores it (the game shows a
personality word, not the number).
{% enddocs %}

{% docs has_estimated_attributes %}
His decodable attributes are decoded, not stated: they are all stated (a fresh scrapbook entry)
or none are. The seven plain attributes and Teamwork are exact either way.
{% enddocs %}
