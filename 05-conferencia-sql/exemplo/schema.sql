-- Fintech Exemplo: esquema fictício usado na conferência.
-- Datas em texto ISO 8601 (AAAA-MM-DD HH:MM:SS), em UTC.

CREATE TABLE parceiros (
    id    INTEGER PRIMARY KEY,
    nome  TEXT    NOT NULL,
    uf    TEXT    NOT NULL,
    ativo INTEGER NOT NULL DEFAULT 1           -- 1 = ativo, 0 = inativo
);

CREATE TABLE propostas (
    id               INTEGER PRIMARY KEY,
    parceiro_id      INTEGER NOT NULL REFERENCES parceiros (id),
    criada_em        TEXT    NOT NULL,
    status           TEXT    NOT NULL
                     CHECK (status IN ('em_analise', 'aprovada', 'recusada', 'cancelada')),
    valor_solicitado REAL    NOT NULL,
    prazo_meses      INTEGER NOT NULL
);

CREATE TABLE contratos (
    id             INTEGER PRIMARY KEY,
    proposta_id    INTEGER NOT NULL UNIQUE REFERENCES propostas (id),
    pago_em        TEXT    NOT NULL,
    valor_liberado REAL    NOT NULL,
    taxa_mensal    REAL    NOT NULL            -- em %, ex.: 2.35
);
