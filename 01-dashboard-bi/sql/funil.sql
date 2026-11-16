-- Funil do mês: das propostas criadas no mês de referência, quantas chegaram (pelo menos)
-- a cada etapa. A conversão de uma etapa para a seguinte é calculada no kpis.py.
-- Tabelas: propostas (data_criacao, etapa, parceiro_id), parceiros (gerente_id).
-- :inicio e :fim delimitam o mês (fim exclusivo); :gerente_id = NULL traz tudo.
WITH etapas (etapa, ordem) AS (
    VALUES ('simulacao', 1), ('proposta', 2), ('analise', 3),
           ('aprovada', 4), ('assinada', 5), ('paga', 6)
),
ultima_etapa AS (
    SELECT p.etapa, COUNT(*) AS quantidade
    FROM propostas p
    LEFT JOIN parceiros pa ON pa.id = p.parceiro_id
    WHERE p.data_criacao >= :inicio AND p.data_criacao < :fim
      AND (:gerente_id IS NULL OR pa.gerente_id = :gerente_id)
    GROUP BY p.etapa
)
SELECT e.etapa,
       SUM(COALESCE(u.quantidade, 0)) OVER (ORDER BY e.ordem DESC) AS chegaram
FROM etapas e
LEFT JOIN ultima_etapa u ON u.etapa = e.etapa
ORDER BY e.ordem;
