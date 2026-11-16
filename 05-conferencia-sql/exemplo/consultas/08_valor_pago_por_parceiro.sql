-- Quadro "Valor pago por parceiro".
-- usa: contratos.valor_pago, contratos.proposta_id, propostas.id, propostas.parceiro_id, parceiros.id, parceiros.nome
SELECT pa.nome,
       ROUND(SUM(c.valor_pago), 2) AS valor_pago
FROM contratos AS c
JOIN propostas AS p  ON p.id = c.proposta_id
JOIN parceiros AS pa ON pa.id = p.parceiro_id
GROUP BY pa.nome
ORDER BY valor_pago DESC;
