# Eval results: cacador

## Suite `cacador`

30/34 cases passed every round on `claude-haiku-5-5` at effort `medium`. Tokens: 347467 input, 3987143 cache read, 0 cache write, 108586 output. Estimated cost: US$ 0.1289.

| Case | Rounds passed | Detail |
|---|---|---|
| H01_price_and_closing_time | 5/5 | - |
| H02_product_and_order_same_message | 5/5 | - |
| H03_pix_and_twelve_installments | 5/5 | - |
| H04_budget_guitar_plus_accessory | 5/5 | - |
| H05_phone_corrected_after_typo | 5/5 | - |
| H06_product_corrected_mid_conversation | 5/5 | - |
| H07_customer_changes_product_and_asks_pix | 5/5 | - |
| H08_installments_above_minimum_installment | 5/5 (guard fired) | - |
| H09_two_taylor_110e_promotion | 5/5 | - |
| H10_three_kalani_promotion | 5/5 | - |
| H11_crafter_promotion_no_pix_stack | 5/5 | - |
| H12_expired_promotion_with_quantity | 5/5 | - |
| H13_quantity_above_stock | 5/5 | - |
| H14_shipping_fee_below_500_after_promotion | 5/5 | - |
| H15_free_shipping_with_two_units | 5/5 | - |
| H16_similar_name_available_vs_sold_out | 5/5 | - |
| H17_discontinued_sibling_model | 5/5 | - |
| H18_ambiguous_brand_only | 5/5 | - |
| H19_friday_at_closing_time | 5/5 | - |
| H20_saturday_at_one_pm | 4/5 | round 4: missing: fechad|encerr | answer: 'Hoje é sábado e já passamos do nosso horário de hoje, que vai até as 13:00. A gente volta na segunda-feira, dia 26/10, às 09:00.\n\nSe quiser, pode deixar sua dúvida por aqui que eu já adianto o que dá ' |
| H21_saturday_before_opening | 5/5 | - |
| H22_black_consciousness_day | 5/5 | - |
| H23_sunday_before_monday_holiday | 5/5 | - |
| H24_customer_says_delivered_but_shipped | 4/5 | round 1: missing: BRJL5544332BR | answer: 'Oi, Ana! Consultei o pedido 8 aqui, e o sistema ainda mostra como "Enviado", não como entregue. A previsão de entrega era 28/02/2026, e não há registro de recebimento.\n\nPode ser que a entrega tenha ac' |
| H25_customer_says_cancelled_but_pending | 4/5 | round 4: forbidden: (?<!n[ãa]o )(?<!ainda n[ãa]o )(est[aá]|foi) cancelad | answer: 'Oi, Fernanda! Aqui no sistema, o pedido 13 aparece com status "Pendente". Não consta cancelamento registrado, então não consigo confirmar que ele está cancelado.\n\nComo o pedido precisa de atenção, pos' |
| H26_cancellation_reason_mismatch | 5/5 | - |
| H27_cancelled_unpaid_boleto | 4/5 | round 5: missing: pagamento n[ãa]o (foi )?confirmad|(n[ãa]o|sem) .{0,30}confirma[cç][ãa]o do pagamento|n[ãa]o registrou o pagamento | answer: 'Oi, Pedro! Consegui localizar o pedido 19, da Taylor 214ce Elétrico, com valor registrado de R$ 7.499,00. Ele aparece como cancelado porque o pagamento do boleto não foi confirmado dentro do prazo.\n\nE' |
| H28_defect_after_30_days | 5/5 | - |
| H29_regret_claims_received_yesterday | 5/5 | - |
| H30_phone_with_country_code | 5/5 | - |
| H31_size_word | 5/5 | - |
| H32_color_word | 5/5 | - |
| H33_baritone_word | 5/5 | - |
| H34_show_everything | 5/5 | - |
