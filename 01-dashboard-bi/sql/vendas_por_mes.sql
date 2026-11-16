-- Vendas por mês: contratos pagos em cada mês (pela data de pagamento), com o volume
-- liberado, o prazo médio e a taxa média ponderada pelo valor liberado.
-- Alimenta a linha de KPIs (mês de referência × mês anterior) e o gráfico de volume.
-- Tabelas: contratos (data_pagamento, valor_liberado, prazo_meses, taxa_mensal),
--          propostas (parceiro_id), parceiros (gerente_id).
-- :gerente_id = NULL traz tudo (diretoria); com valor, só os parceiros desse gerente.
SELECT strftime('%Y-%m', c.data_pagamento)                           AS mes,
       COUNT(*)                                                      AS contratos,
       SUM(c.valor_liberado)                                         AS volume,
       AVG(c.prazo_meses)                                            AS prazo_medio,
       SUM(c.taxa_mensal * c.valor_liberado) / SUM(c.valor_liberado) AS taxa_media
FROM contratos c
JOIN propostas p       ON p.id = c.proposta_id
LEFT JOIN parceiros pa ON pa.id = p.parceiro_id
WHERE :gerente_id IS NULL OR pa.gerente_id = :gerente_id
GROUP BY mes
ORDER BY mes;
