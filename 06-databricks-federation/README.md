# 06 · PostgreSQL de produção no Databricks, sem copiar os dados

Guia de como consultar a réplica de leitura de um PostgreSQL de produção dentro do Databricks com o **Lakehouse Federation** do Unity Catalog: o banco aparece como um catálogo e cada consulta vai até ele na hora, sem pipeline de cópia. Não há código para rodar na máquina: são o passo a passo e os SQL de exemplo, com placeholders no lugar de host, usuário e senha.

## O problema que ele espelha

A base operacional de uma fintech é um PostgreSQL com uma réplica só de leitura. Para avaliar o Databricks, a equipe quer consultar essas tabelas, e cruzá-las com outras fontes, antes de decidir se vale montar a ingestão. Copiar tudo só para testar é caro e lento; ler direto da réplica responde em horas. Os tropeços de verdade são de rede (o serverless não enxerga a rede privada), de fuso (carimbos sem fuso gravados em UTC) e de custo (warehouse esquecido ligado).

## Quando faz sentido

- Ler algumas tabelas, ou fazer consultas pontuais, sem montar pipeline de cópia.
- Prova de conceito antes de criar a camada bronze (ingestão) no lakehouse.
- Cruzar o operacional com tabelas que já estão no Databricks, na mesma consulta.

Quando **não** faz: dashboard com muita gente, histórico grande ou consultas pesadas e frequentes. Cada consulta vira carga na réplica; aí vale copiar para o lakehouse e consultar a cópia.

## Como rodar

Nada roda localmente. No editor SQL do Databricks (ou num notebook), rode os arquivos de `sql/` na ordem, trocando os placeholders `<...>`. Antes, confira os requisitos e faça o passo 0.

## Requisitos

- Workspace com Unity Catalog.
- Computação: SQL warehouse **Pro** ou **serverless** (o tipo Classic não roda consultas federadas), ou cluster com Unity Catalog e Databricks Runtime 13.3 LTS ou mais novo.
- Privilégios: `CREATE CONNECTION` no metastore (ou ser admin dele) para criar a conexão; `CREATE CATALOG` no metastore e ser dono da conexão (ou ter `CREATE FOREIGN CATALOG` nela) para criar o catálogo.
- Rede: a computação escolhida precisa alcançar `<host-da-replica>:5432` (veja [Rede](#rede)).

## Passo a passo

### 0. Usuário de leitura e segredos

No `psql`, conectado ao **primário** (a réplica não aceita escrita e recebe o usuário pela própria replicação):

```sql
CREATE ROLE leitor_databricks LOGIN;
\password leitor_databricks
GRANT CONNECT ON DATABASE <nome-do-banco> TO leitor_databricks;
GRANT USAGE ON SCHEMA public TO leitor_databricks;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO leitor_databricks;
ALTER ROLE leitor_databricks SET statement_timeout = '5min';
```

O `\password` pede a senha no terminal, sem deixá-la em arquivo. O `statement_timeout` é a trava de segurança contra consulta pesada. Tabela criada depois precisa de um novo `GRANT SELECT`.

Usuário e senha vão para um escopo de segredos, pelo Databricks CLI (sem `--string-value`, o comando pede o valor no terminal):

```bash
databricks secrets create-scope <escopo>
databricks secrets put-secret <escopo> <chave-usuario>
databricks secrets put-secret <escopo> <chave-senha>
```

### 1. Conexão: [`sql/01_conexao.sql`](sql/01_conexao.sql)

```sql
CREATE CONNECTION conexao_replica_pg TYPE postgresql
OPTIONS (
  host '<host-da-replica>',
  port '5432',
  user secret('<escopo>', '<chave-usuario>'),
  password secret('<escopo>', '<chave-senha>')
);
```

### 2. Catálogo estrangeiro: [`sql/02_catalogo.sql`](sql/02_catalogo.sql)

```sql
CREATE FOREIGN CATALOG IF NOT EXISTS replica_fintech
USING CONNECTION conexao_replica_pg
OPTIONS (database '<nome-do-banco>');
```

Os esquemas e as tabelas da réplica aparecem como `replica_fintech.<esquema>.<tabela>`.

### 3. Permissões: [`sql/03_permissoes.sql`](sql/03_permissoes.sql)

```sql
GRANT USE CATALOG, USE SCHEMA, SELECT ON CATALOG replica_fintech TO `<grupo-de-analistas>`;
```

O arquivo traz também as versões por esquema e por tabela. São duas camadas: o usuário do PostgreSQL limita o que existe para o Databricks; o `GRANT` no Unity Catalog limita quem, lá dentro, vê.

### 4. Primeira consulta: [`sql/04_consulta_exemplo.sql`](sql/04_consulta_exemplo.sql)

Poucas linhas com `LIMIT`, depois uma agregação numa janela de 7 dias, um cruzamento com uma tabela do lakehouse e o `EXPLAIN FORMATTED` para ver o que foi enviado ao PostgreSQL.

## Exemplo de saída

Com tabelas fictícias como as do projeto 05 (no PostgreSQL: `bigint`, `timestamp` sem fuso, `text` e `numeric(12,2)`):

```text
> SHOW TABLES IN replica_fintech.public;
database   tableName   isTemporary
public     contratos   false
public     parceiros   false
public     propostas   false

> DESCRIBE TABLE replica_fintech.public.propostas;   -- trecho
col_name           data_type
id                 bigint
criada_em          timestamp
status             string
valor_solicitado   decimal(12,2)
```

## Rede

É o tropeço mais comum: a conexão é criada sem erro e a primeira consulta não chega ao banco.

| Computação | Onde roda | Como chega à réplica |
| --- | --- | --- |
| SQL warehouse Pro, cluster | na rede da sua conta de nuvem (plano clássico) | pela rede privada: a rede do workspace e a do banco ligadas (mesma rede ou peering) e a porta 5432 liberada |
| SQL warehouse serverless | na rede do Databricks (plano serverless) | por uma NCC (Network Connectivity Configuration), criada no console da conta e anexada ao workspace, com regra de private endpoint até o banco; o lado do banco aprova a conexão |

O warehouse do tipo Classic também roda na sua rede, mas não aceita consulta federada. Sintoma típico: a mesma consulta funciona no warehouse Pro e falha no serverless com erro de conexão (em geral, tempo esgotado). Num cluster, um teste rápido de rede num notebook Python:

```python
import socket
socket.create_connection(("<host-da-replica>", 5432), timeout=5).close()  # sem erro: a rede chega
```

## Fuso horário

Na réplica, as colunas `timestamp` (sem fuso) guardam a hora em UTC. Pela federação elas chegam como `timestamp` e, com a sessão no fuso padrão (UTC), mostram o valor gravado, sem conversão.

- Para mostrar no horário de Brasília: `from_utc_timestamp(criada_em, 'America/Sao_Paulo')`.
- Para filtrar por dia de Brasília, converta os limites, não a coluna: `criada_em >= to_utc_timestamp(TIMESTAMP '2026-11-01 00:00:00', 'America/Sao_Paulo')`. Função aplicada na coluna pode impedir que o filtro vá para o PostgreSQL.
- Escolha um caminho só: ou converte na consulta (sessão em UTC), ou muda o fuso da sessão com `SET TIME ZONE`. Os dois juntos dão hora errada.
- Confira o tipo com `DESCRIBE TABLE`: conforme a versão e a configuração, a coluna pode chegar como `timestamp_ntz`.

## Custos

- O custo vem da computação que roda as consultas (e, conforme a rede, do tráfego entre redes); a federação não copia nem guarda dados.
- Warehouse Pro e cluster rodam na sua conta: você paga a DBU ao Databricks **e** a máquina ao provedor de nuvem. No serverless, a DBU já inclui a máquina.
- Ligue o desligamento automático (Auto stop no warehouse, "terminate after" no cluster) com poucos minutos de ociosidade.
- Terminou os testes? Pare o warehouse ou o cluster na mão e confira o consumo (por exemplo, na tabela de sistema `system.billing.usage`). Em período de avaliação, um warehouse esquecido ligado gasta os créditos.

## Cuidados

- **Carga na réplica:** cada consulta vira SQL no PostgreSQL, e uma dashboard com muita gente multiplica isso. Use um usuário dedicado, com `statement_timeout`.
- **Conflito com a replicação:** consulta longa numa réplica pode ser cancelada (`canceling statement due to conflict with recovery`) ou atrasar a réplica, conforme a configuração dela (`max_standby_streaming_delay`, `hot_standby_feedback`). Mais um motivo para consultas curtas.
- **Pushdown limitado:** filtros, projeções, `LIMIT` e agregações simples costumam ir para o PostgreSQL; joins e funções de janela, em geral, rodam no Databricks depois de trazer as linhas. Confira no `EXPLAIN FORMATTED` e na lista de pushdowns da documentação.
- **Consultas grandes em janelas de data:** em vez de um ano de uma vez, quebre por mês ou por semana, sempre filtrando a coluna crua; use `LIMIT` na exploração.
- **Sem cópia, sem foto:** a federação lê o estado atual. Se o operacional altera ou apaga linhas, o resultado muda; para histórico e reprodutibilidade, copie para a camada bronze.

## Checklist final

- [ ] Workspace com Unity Catalog; warehouse Pro ou serverless, ou cluster com DBR 13.3 LTS ou mais novo.
- [ ] Usuário só de leitura criado no primário, com `statement_timeout`.
- [ ] Usuário e senha no escopo de segredos; nenhuma senha em SQL, notebook ou repositório.
- [ ] Rede: a computação escolhida alcança `<host-da-replica>:5432` (serverless: NCC com private endpoint aprovado).
- [ ] `01`: conexão criada e conferida com `DESCRIBE CONNECTION`.
- [ ] `02`: o catálogo mostra os esquemas e as tabelas esperados.
- [ ] `03`: `GRANT` para o grupo, conferido com `SHOW GRANTS`.
- [ ] `04`: primeira consulta com janela de data e `LIMIT`; fuso conferido contra um registro de hora conhecida.
- [ ] O filtro de data aparece no nó de leitura do `EXPLAIN FORMATTED`.
- [ ] Desligamento automático ligado; warehouse ou cluster parado depois dos testes; consumo conferido.

## Decisões técnicas

- **Federação antes da cópia:** nenhum pipeline para manter e o dado sempre atual. Se o uso crescer, a cópia para a camada bronze vem depois, com a prova de conceito já feita.
- **Réplica, nunca o primário:** a carga analítica não disputa com o sistema que atende o cliente.
- **Segredos com `secret()`:** a senha não aparece em SQL, notebook nem histórico.
- **Permissão em duas camadas:** usuário do PostgreSQL só de leitura e `GRANT` no Unity Catalog.
- **Datas em UTC na coluna crua:** o filtro pode ir para o PostgreSQL; a conversão de fuso fica só na saída.

## Estrutura

```text
06-databricks-federation/
├── README.md
└── sql/
    ├── 01_conexao.sql           # CREATE CONNECTION com secret()
    ├── 02_catalogo.sql          # CREATE FOREIGN CATALOG e conferência
    ├── 03_permissoes.sql        # GRANT por catálogo, esquema ou tabela
    └── 04_consulta_exemplo.sql  # janela de data, fuso, cruzamento e EXPLAIN
```

## Referências

Documentação oficial do Databricks (docs.databricks.com), pelo nome da página:

- "What is Lakehouse Federation?"
- "Run federated queries on PostgreSQL"
- "Networking recommendations for Lakehouse Federation"
- "Serverless compute plane networking"
- "Secret management"
- "Manage privileges in Unity Catalog"
- "SQL warehouse types"
- Referência de SQL: "CREATE CONNECTION", "CREATE CATALOG" e "from_utc_timestamp function"

Documentação do PostgreSQL: capítulo "Hot Standby", seção sobre conflitos de consulta na réplica.
