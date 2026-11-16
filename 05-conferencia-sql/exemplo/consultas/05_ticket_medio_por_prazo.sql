-- Quadro "Ticket médio por prazo".
-- usa: propostas.valor, propostas.prazo_meses
SELECT prazo_meses,
       COUNT(*)                        AS propostas,
       ROUND(AVG(valor_solicitado), 2) AS ticket_medio
FROM propostas
GROUP BY prazo_meses
ORDER BY prazo_meses;
