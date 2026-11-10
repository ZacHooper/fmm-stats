{# Money, in pounds. Every block here is money, so its canonical name ends _gbp
   (scripts/check_dbt_docs.py checks it). #}

{% docs value_gbp %}
A player's transfer value in £. The save states one only for our own squad (a fresh scrapbook
entry's); everyone else's is the transfer-value model's estimate (int.player_value,
`is_value_estimated`), NULL where the model lacks an input. On `site.players` only the stated
value is shown (NULL for an estimate); on `site.finances` it is the sum over the players we own.
{% enddocs %}

{% docs wage_gbp %}
The player's wage in £ a year: the contract's weekly wage, stored in units of £10, × 520. On a
contract, read on its first and last snapshot; on `site.finances`, summed over the players we
own.
{% enddocs %}

{% docs fee_gbp %}
The transfer fee in £, from the fee code on the selling club's career-history line (a code
below `var('fee_code_floor')` is the fee in thousands): the fee where the code is one, 0 for a
free move on `fact_transfer` (a free, a Bosman `stay`, a contract run out, a free agent signed),
NULL where the code is not a fee or not understood.
{% enddocs %}
