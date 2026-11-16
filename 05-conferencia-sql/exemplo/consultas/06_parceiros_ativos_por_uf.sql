-- Quadro "Parceiros ativos por UF".
-- usa: parceiros.uf
SELECT uf,
       COUNT(*) AS quantidade
FROM parceiros
WHERE ativo = 1
GROUP BY uf
ORDER BY quantidade DESC, uf;
