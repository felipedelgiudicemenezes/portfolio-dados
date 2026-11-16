-- 04 · Consultas de exemplo na réplica
--
-- Na réplica, criada_em é timestamp sem fuso, gravado em UTC. Regras:
--   * sempre uma janela de datas, filtrando a coluna crua com limites em UTC
--     (assim o filtro pode ir para o PostgreSQL);
--   * conversão para o horário de Brasília só no resultado;
--   * sessão no fuso padrão (UTC): não combinar com SET TIME ZONE.
--
-- Troque: <catalogo>.<esquema> (consulta 3).

-- 1) Olhar poucas linhas antes de agregar.
SELECT
  p.id,
  p.status,
  p.criada_em                                          AS criada_em_utc,
  from_utc_timestamp(p.criada_em, 'America/Sao_Paulo') AS criada_em_brasilia
FROM replica_fintech.public.propostas AS p
WHERE p.criada_em >= to_utc_timestamp(TIMESTAMP '2026-11-01 00:00:00', 'America/Sao_Paulo')
ORDER BY p.criada_em DESC
LIMIT 20;

-- 2) Propostas por dia de Brasília, numa janela fechada de 7 dias.
SELECT
  to_date(from_utc_timestamp(p.criada_em, 'America/Sao_Paulo')) AS dia,
  count(*)                                                       AS propostas,
  count_if(p.status = 'aprovada')                                AS aprovadas
FROM replica_fintech.public.propostas AS p
WHERE p.criada_em >= to_utc_timestamp(TIMESTAMP '2026-11-01 00:00:00', 'America/Sao_Paulo')
  AND p.criada_em <  to_utc_timestamp(TIMESTAMP '2026-11-08 00:00:00', 'America/Sao_Paulo')
GROUP BY 1
ORDER BY 1;

-- 3) Cruzar com uma tabela que já está no lakehouse. O filtro de data pode ir
--    para o PostgreSQL; o join roda no Databricks.
SELECT
  s.segmento,
  count(*) AS propostas
FROM replica_fintech.public.propostas AS p
JOIN <catalogo>.<esquema>.parceiros_segmento AS s
  ON s.parceiro_id = p.parceiro_id
WHERE p.criada_em >= to_utc_timestamp(TIMESTAMP '2026-11-01 00:00:00', 'America/Sao_Paulo')
  AND p.criada_em <  to_utc_timestamp(TIMESTAMP '2026-11-08 00:00:00', 'America/Sao_Paulo')
GROUP BY s.segmento
ORDER BY propostas DESC;

-- 4) Ver o que vai para o PostgreSQL: procure o filtro de criada_em no nó de
--    leitura da tabela estrangeira. Se ele só aparece num Filter acima dela,
--    o Databricks está trazendo as linhas para filtrar do lado de cá.
EXPLAIN FORMATTED
SELECT count(*)
FROM replica_fintech.public.propostas AS p
WHERE p.criada_em >= to_utc_timestamp(TIMESTAMP '2026-11-01 00:00:00', 'America/Sao_Paulo')
  AND p.criada_em <  to_utc_timestamp(TIMESTAMP '2026-11-08 00:00:00', 'America/Sao_Paulo');
