-- Período da base: a primeira e a última data de criação de proposta. A última é a
-- "data do dado" do cabeçalho e define o mês de referência (o mês dela).
-- Tabela: propostas (data_criacao).
SELECT MIN(data_criacao) AS inicio,
       MAX(data_criacao) AS fim
FROM propostas;
