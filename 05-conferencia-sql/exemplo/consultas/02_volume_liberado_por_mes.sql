-- Quadro "Volume liberado por mês", no período escolhido no topo da tela.
-- usa: contratos.pago_em, contratos.valor_liberado
SELECT strftime('%Y-%m', pago_em)    AS mes,
       COUNT(*)                      AS contratos,
       ROUND(SUM(valor_liberado), 2) AS liberado
FROM contratos
WHERE pago_em >= :inicio
  AND pago_em <  :fim
GROUP BY mes
ORDER BY mes;
