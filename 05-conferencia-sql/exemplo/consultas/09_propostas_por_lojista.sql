-- Quadro "Propostas por lojista".
-- usa: lojistas.id, lojistas.nome, propostas.parceiro_id
SELECT l.nome,
       COUNT(*) AS propostas
FROM propostas AS p
JOIN lojistas AS l ON l.id = p.parceiro_id
GROUP BY l.nome
ORDER BY propostas DESC;
