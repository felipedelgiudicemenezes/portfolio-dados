-- Quadro "Aprovação por parceiro".
-- usa: parceiros.id, parceiros.nome, propostas.parceiro_id, propostas.status
WITH por_parceiro AS (
    SELECT parceiro_id,
           COUNT(*)                 AS propostas,
           SUM(status = 'aprovada') AS aprovadas
    FROM propostas
    GROUP BY parceiro_id
)
SELECT pa.nome,
       pp.propostas,
       ROUND(100.0 * pp.aprovadas / pp.propostas, 1) AS taxa_aprovacao
FROM por_parceiro AS pp
JOIN parceiros AS pa ON pa.id = pp.parceiro_id
ORDER BY taxa_aprovacao DESC;
