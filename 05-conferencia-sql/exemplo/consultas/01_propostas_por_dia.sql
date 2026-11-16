-- Quadro "Propostas por dia": total e aprovadas.
-- usa: propostas.criada_em, propostas.status
SELECT date(criada_em)          AS dia,
       COUNT(*)                 AS propostas,
       SUM(status = 'aprovada') AS aprovadas
FROM propostas
GROUP BY dia
ORDER BY dia;
