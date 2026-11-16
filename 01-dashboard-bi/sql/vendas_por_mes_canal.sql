-- Vendas por mês e canal: contratos pagos em cada mês (pela data de pagamento), separados
-- entre o canal digital e os correspondentes (parceiros). Alimenta as barras empilhadas do
-- gráfico de volume por mês; somados, os canais dão o total de cada mês do vendas_por_mes.sql.
-- Tabelas: contratos (data_pagamento, valor_liberado), propostas (canal, parceiro_id),
--          parceiros (gerente_id).
-- :gerente_id = NULL traz tudo (diretoria); com valor, só os parceiros desse gerente,
-- e o canal digital, que não tem gerente, fica de fora.
SELECT strftime('%Y-%m', c.data_pagamento) AS mes,
       p.canal                             AS canal,
       COUNT(*)                            AS contratos,
       SUM(c.valor_liberado)               AS volume
FROM contratos c
JOIN propostas p       ON p.id = c.proposta_id
LEFT JOIN parceiros pa ON pa.id = p.parceiro_id
WHERE :gerente_id IS NULL OR pa.gerente_id = :gerente_id
GROUP BY mes, p.canal
ORDER BY mes, p.canal;
