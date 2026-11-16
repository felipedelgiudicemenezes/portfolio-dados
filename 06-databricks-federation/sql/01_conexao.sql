-- 01 · Conexão com a réplica de leitura do PostgreSQL
--
-- Quem roda: admin do metastore ou quem tem CREATE CONNECTION nele.
-- Antes: usuário e senha guardados num escopo de segredos (passo 0 do README).
-- Nenhuma senha fica escrita aqui: secret() busca o valor no escopo.
--
-- Troque: <host-da-replica>, <escopo>, <chave-usuario>, <chave-senha>.

CREATE CONNECTION conexao_replica_pg TYPE postgresql
OPTIONS (
  host '<host-da-replica>',
  port '5432',
  user secret('<escopo>', '<chave-usuario>'),
  password secret('<escopo>', '<chave-senha>')
);

-- Conferir a conexão criada.
DESCRIBE CONNECTION conexao_replica_pg;
