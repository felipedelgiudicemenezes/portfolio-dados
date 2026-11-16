"""Camada de regras: roda as consultas de sql/ e monta o payload de cada perfil.

O recorte por perfil é o parâmetro :gerente_id das consultas. O payload de um gerente
já nasce só com a carteira dele, então a página gerada a partir dele não tem como
mostrar dado de outro gerente.
"""

import sqlite3
from datetime import date, timedelta
from pathlib import Path

PASTA_SQL = Path(__file__).resolve().parent / "sql"
EMPRESA = "Fintech Exemplo"
INDICADORES = ("volume", "contratos", "ticket_medio", "prazo_medio", "taxa_media")
VARIACAO_EM_DIFERENCA = {"prazo_medio", "taxa_media"}  # em meses e em pontos percentuais
QUADROS = ("vendas_por_mes", "funil", "motivos_recusa", "ranking_parceiros")


def conectar(caminho):
    """Abre a base só para leitura: a dashboard nunca escreve no banco."""
    return sqlite3.connect(f"{Path(caminho).resolve().as_uri()}?mode=ro", uri=True)


def consultar(con, nome, parametros):
    """Roda sql/<nome>.sql e devolve a fonte do quadro: arquivo, SQL, parâmetros e linhas."""
    sql = (PASTA_SQL / f"{nome}.sql").read_text(encoding="utf-8")
    usados = {chave: valor for chave, valor in parametros.items() if f":{chave}" in sql}
    cursor = con.execute(sql, usados)
    colunas = [coluna[0] for coluna in cursor.description]
    linhas = [dict(zip(colunas, linha)) for linha in cursor]
    return {"arquivo": f"sql/{nome}.sql", "sql": sql, "parametros": usados, "linhas": linhas}


def listar_perfis(con):
    """Diretoria (tudo) e um perfil por gerente (só os parceiros dele)."""
    gerentes = consultar(con, "perfis", {})["linhas"]
    return [{"id": "diretoria", "nome": "Diretoria", "gerente_id": None}] + [
        {"id": f"gerente-{g['id']}", "nome": g["nome"], "gerente_id": g["id"]} for g in gerentes
    ]


def montar_payload(con, perfil):
    """Tudo o que a página do perfil mostra, já recortado para ele."""
    periodo = consultar(con, "periodo", {})["linhas"][0]
    primeiro_dia = date.fromisoformat(periodo["inicio"])
    ultimo_dia = date.fromisoformat(periodo["fim"])
    mes = ultimo_dia.replace(day=1)
    parametros = {"gerente_id": perfil["gerente_id"],
                  "inicio": mes.isoformat(), "fim": proximo_mes(mes).isoformat()}
    fontes = {nome: consultar(con, nome, parametros) for nome in QUADROS}

    serie = serie_mensal(fontes["vendas_por_mes"]["linhas"], meses_entre(primeiro_dia, ultimo_dia))
    anterior = serie[-2] if len(serie) > 1 else None
    funil = montar_funil(fontes["funil"]["linhas"])
    simulacoes, pagas = funil[0]["quantidade"], funil[-1]["quantidade"]
    motivos = montar_motivos(fontes["motivos_recusa"]["linhas"], simulacoes)
    return {
        "empresa": EMPRESA,
        "perfil": perfil,
        "data_dado": ultimo_dia.isoformat(),
        "mes_referencia": serie[-1]["mes"],
        "mes_anterior": anterior["mes"] if anterior else None,
        "kpis": montar_kpis(serie[-1], anterior),
        "vendas_por_mes": serie,
        "funil": funil,
        "conversao_total": percentual(pagas, simulacoes),
        "em_andamento": simulacoes - pagas - motivos["total"],
        "motivos": motivos,
        "ranking": montar_ranking(fontes["ranking_parceiros"]["linhas"]),
        "fontes": fontes,
    }


def serie_mensal(linhas, meses):
    """Um item por mês do período, com zero no mês sem venda."""
    por_mes = {linha["mes"]: linha for linha in linhas}
    vazio = {"contratos": 0, "volume": 0.0, "prazo_medio": None, "taxa_media": None}
    serie = []
    for mes in meses:
        linha = por_mes.get(mes, vazio)
        serie.append({
            "mes": mes,
            "contratos": linha["contratos"],
            "volume": linha["volume"],
            "ticket_medio": dividir(linha["volume"], linha["contratos"]),
            "prazo_medio": linha["prazo_medio"],
            "taxa_media": linha["taxa_media"],
        })
    return serie


def montar_kpis(atual, anterior):
    """Indicadores do mês de referência e a variação sobre o mês anterior."""
    kpis = {}
    for chave in INDICADORES:
        base = anterior[chave] if anterior else None
        kpis[chave] = {"atual": atual[chave], "anterior": base, "variacao": variacao(chave, atual[chave], base)}
    return kpis


def variacao(chave, atual, anterior):
    """Prazo e taxa variam em diferença (meses, p.p.); os demais, em percentual."""
    if atual is None or anterior is None:
        return None
    if chave in VARIACAO_EM_DIFERENCA:
        return atual - anterior
    return percentual(atual - anterior, anterior)


def montar_funil(linhas):
    """Cada etapa com a conversão sobre a etapa anterior."""
    funil, anterior = [], None
    for linha in linhas:
        quantidade = linha["chegaram"]
        funil.append({"etapa": linha["etapa"], "quantidade": quantidade, "base": anterior,
                      "conversao": percentual(quantidade, anterior)})
        anterior = quantidade
    return funil


def montar_motivos(linhas, criadas):
    """Cada motivo com a fatia do total que parou; e quanto esse total pesa nas criadas."""
    total = sum(linha["quantidade"] for linha in linhas)
    itens = [{**linha, "percentual": percentual(linha["quantidade"], total)} for linha in linhas]
    return {"itens": itens, "total": total, "criadas": criadas, "percentual_das_criadas": percentual(total, criadas)}


def montar_ranking(linhas):
    """Parceiros por volume, a linha do canal digital (só na diretoria) e o total."""
    parceiros = [_com_indicadores(linha) for linha in linhas if linha["parceiro_id"] is not None]
    digital = [_com_indicadores(linha) for linha in linhas if linha["parceiro_id"] is None]
    for posicao, linha in enumerate(parceiros, start=1):
        linha["posicao"] = posicao
    soma = {campo: sum(linha[campo] for linha in parceiros + digital)
            for campo in ("contratos", "volume", "simulacoes", "pagas")}
    return {"parceiros": parceiros, "digital": digital[0] if digital else None, "total": _com_indicadores(soma)}


def _com_indicadores(linha):
    return {**linha, "ticket_medio": dividir(linha["volume"], linha["contratos"]),
            "conversao": percentual(linha["pagas"], linha["simulacoes"])}


def percentual(parte, todo):
    return None if not todo else 100 * parte / todo


def dividir(numerador, denominador):
    return None if not denominador else numerador / denominador


def proximo_mes(dia):
    return (dia.replace(day=28) + timedelta(days=4)).replace(day=1)


def meses_entre(inicio, fim):
    """['2025-11', ..., '2026-10']: todos os meses de `inicio` a `fim`."""
    meses, dia = [], inicio.replace(day=1)
    while dia <= fim:
        meses.append(dia.strftime("%Y-%m"))
        dia = proximo_mes(dia)
    return meses
