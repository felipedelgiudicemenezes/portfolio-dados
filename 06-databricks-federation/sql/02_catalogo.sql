-- 02 · Catálogo estrangeiro: o banco da réplica aparece no Unity Catalog
--
-- Quem roda: quem tem CREATE CATALOG no metastore e é dono da conexão
-- (ou tem CREATE FOREIGN CATALOG nela).
-- Os esquemas e as tabelas do PostgreSQL aparecem sozinhos; nenhum dado é copiado.
--
-- Troque: <nome-do-banco>.

CREATE FOREIGN CATALOG IF NOT EXISTS replica_fintech
USING CONNECTION conexao_replica_pg
OPTIONS (database '<nome-do-banco>');

-- Conferir o que apareceu (só metadados, nenhuma linha das tabelas).
SHOW SCHEMAS IN replica_fintech;
SHOW TABLES IN replica_fintech.public;
DESCRIBE TABLE replica_fintech.public.propostas;
