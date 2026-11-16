-- Ranking de parceiros no mês: contratos pagos e volume liberado (pela data de pagamento)
-- e a conversão das propostas criadas no mês (pagas ÷ simulações). A linha sem parceiro
-- é o canal digital, que não tem gerente: só a diretoria a recebe.
-- Tabelas: parceiros (id, nome, gerente_id), gerentes (nome),
--          contratos (proposta_id, data_pagamento, valor_liberado),
--          propostas (parceiro_id, data_criacao, etapa).
-- :inicio e :fim delimitam o mês (fim exclusivo); :gerente_id = NULL traz tudo.
WITH canais AS (
    SELECT pa.id AS parceiro_id, pa.nome AS parceiro, g.nome AS gerente, pa.gerente_id
    FROM parceiros pa
    JOIN gerentes g ON g.id = pa.gerente_id
    UNION ALL
    SELECT NULL, 'Canal digital', NULL, NULL
),
vendas AS (
    SELECT p.parceiro_id, COUNT(*) AS contratos, SUM(c.valor_liberado) AS volume
    FROM contratos c
    JOIN propostas p ON p.id = c.proposta_id
    WHERE c.data_pagamento >= :inicio AND c.data_pagamento < :fim
    GROUP BY p.parceiro_id
),
coorte AS (
    SELECT parceiro_id, COUNT(*) AS simulacoes, SUM(etapa = 'paga') AS pagas
    FROM propostas
    WHERE data_criacao >= :inicio AND data_criacao < :fim
    GROUP BY parceiro_id
)
SELECT ca.parceiro_id,
       ca.parceiro,
       ca.gerente,
       COALESCE(v.contratos, 0)   AS contratos,
       COALESCE(v.volume, 0)      AS volume,
       COALESCE(co.simulacoes, 0) AS simulacoes,
       COALESCE(co.pagas, 0)      AS pagas
FROM canais ca
LEFT JOIN vendas v  ON v.parceiro_id IS ca.parceiro_id
LEFT JOIN coorte co ON co.parceiro_id IS ca.parceiro_id
WHERE :gerente_id IS NULL OR ca.gerente_id = :gerente_id
ORDER BY ca.parceiro_id IS NULL, volume DESC;
