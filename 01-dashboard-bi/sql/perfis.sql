-- Perfis de acesso: cada gerente vira um perfil que só enxerga os próprios parceiros
-- (a diretoria, que vê tudo, é acrescentada no kpis.py).
-- Tabela: gerentes (id, nome).
SELECT id, nome
FROM gerentes
ORDER BY id;
