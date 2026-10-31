# Pedido atrasado

**Shows:** Order lookup by phone, overdue delivery, handoff.

Recorded by `scripts/record_examples.py` (scenario `12_shipped_late_order`) on model `claude-haiku-5-5`, with the store clock pinned to Wednesday 2026-10-28 14:00.

**Cliente:** Cadê meu pedido? Número 8, telefone (67) 99654-7821

> `consultar_pedido({"numero_pedido": 8, "telefone": "(67) 99654-7821"})`

**Tom:** Oi, Ana! Consegui localizar o seu pedido 8.

- Status: Enviado
- Item: Kala KA-C Concert Mogno (1 unidade)
- Valor registrado: R$ 349,90
- Compra em 15/02/2026, pagamento no cartão de débito
- Código de rastreio: BRJL5544332BR (também pode ser consultado no site dos Correios ou da Jadlog)

A previsão de entrega era 28/02/2026, e ela já passou. Pelo sistema, o pedido está com atraso e marcado para atenção da equipe. Não consigo ver a movimentação do rastreio daqui, então não sei dizer onde ele está parado.

Quer que eu abra um chamado para a equipe verificar com a transportadora e te dar um retorno?

---
