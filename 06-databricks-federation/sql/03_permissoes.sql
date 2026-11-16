-- 03 · Permissões: quem pode ler o catálogo
--
-- Quem roda: o dono do catálogo (quem o criou) ou um admin.
-- O limite de fundo é o usuário do PostgreSQL usado na conexão: o Databricks
-- não lê nada que esse usuário não possa ler. O GRANT decide quem, dentro do
-- Databricks, enxerga o que sobra.
-- Use UMA das opções abaixo, da mais aberta para a mais fechada.
--
-- Troque: <grupo-de-analistas>.

-- Opção A: o catálogo inteiro.
GRANT USE CATALOG, USE SCHEMA, SELECT ON CATALOG replica_fintech TO `<grupo-de-analistas>`;

-- Opção B: só um esquema.
-- GRANT USE CATALOG ON CATALOG replica_fintech TO `<grupo-de-analistas>`;
-- GRANT USE SCHEMA, SELECT ON SCHEMA replica_fintech.public TO `<grupo-de-analistas>`;

-- Opção C: só algumas tabelas.
-- GRANT USE CATALOG ON CATALOG replica_fintech TO `<grupo-de-analistas>`;
-- GRANT USE SCHEMA ON SCHEMA replica_fintech.public TO `<grupo-de-analistas>`;
-- GRANT SELECT ON TABLE replica_fintech.public.propostas TO `<grupo-de-analistas>`;
-- GRANT SELECT ON TABLE replica_fintech.public.contratos TO `<grupo-de-analistas>`;

-- Conferir.
SHOW GRANTS ON CATALOG replica_fintech;
