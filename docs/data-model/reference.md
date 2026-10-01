# Reference dimensions — semantic model

Conceptual model only; names are not final tables. The small lookup dimensions the other models
join to. None has facts of its own.

```mermaid
erDiagram
    dim_nation   ||--o{ dim_city : "in"
    dim_city     ||--o{ dim_stadium : "in"
    dim_position ||--o{ dim_role : "played from"
    dim_nation   |o--o{ dim_currency : "uses"

    dim_position {
        int position_key PK
        string code "GK / DC / DM / AMC / ST ..."
        string unit "goalkeeper / defence / midfield / attack"
        int display_order
    }
    dim_role {
        int role_key PK
        int position_key FK
        string name
    }
    dim_city {
        int city_key PK
        string name
        int nation_key FK
    }
    dim_stadium {
        int stadium_key PK
        string name
        int city_key FK
        int capacity
        int expansion_capacity
    }
    dim_currency {
        int currency_key PK
        string name
        float rate_per_gbp
    }
```

| Dimension | Holds | Used by |
|---|---|---|
| `dim_position` | position code, **unit** (goalkeeper / defence / midfield / attack), display order | position played (`fact_player_match`), training focus position. Positional ratings stay columns on the player snapshot. The unit means no query re-encodes "which positions are midfield". |
| `dim_role` | role name, the position it is played from | training focus role, and anything else that names a role. The save gives role ids only; this puts the names in the warehouse. |
| `dim_city` | name, nation | stadiums, a nation's capital, where a club is based |
| `dim_stadium` | name, city, capacity, expansion capacity | matches, a club's ground (club snapshot), a nation's national stadium |
| `dim_currency` | name, exchange rate to GBP | **optional.** Parsed, but money in the save is already in one currency; model it only if comparing money across nations turns out to need it. |

Lookups that belong to one model stay in that model: `dim_event_type` and `dim_period` (match),
`dim_award` (person), `dim_formation` (match).
