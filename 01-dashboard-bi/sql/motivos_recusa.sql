-- Motivos de recusa: por que as propostas criadas no mês pararam antes do pagamento
-- e em que etapa. Sem motivo e ainda não paga = em andamento; fica fora desta conta.
-- Tabelas: propostas (data_criacao, etapa, motivo_recusa, parceiro_id), parceiros (gerente_id).
-- :inicio e :fim delimitam o mês (fim exclusivo); :gerente_id = NULL traz tudo.
SELECT p.motivo_recusa AS motivo,
       p.etapa         AS parou_em,
       COUNT(*)        AS quantidade
FROM propostas p
LEFT JOIN parceiros pa ON pa.id = p.parceiro_id
WHERE p.data_criacao >= :inicio AND p.data_criacao < :fim
  AND p.motivo_recusa IS NOT NULL
  AND (:gerente_id IS NULL OR pa.gerente_id = :gerente_id)
GROUP BY p.motivo_recusa, p.etapa
ORDER BY quantidade DESC, motivo;
