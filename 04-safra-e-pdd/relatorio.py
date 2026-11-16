"""Monta saida/relatorio.html: curvas de safra, PDD por faixa e as tabelas, num arquivo só."""

import base64
from bisect import bisect_left
from datetime import date
from decimal import Decimal
from html import escape

import graficos
import pdd
import safra
from comum import PASTA, SAIDA, abrir_banco, data_br, mes_ano, moeda, moeda_curta, numero, parte_de, percentual

FONTE_NUNITO = PASTA / "fontes" / "nunito-latin.woff2"
MOB_DA_COMPARACAO = 6

# Mapa de calor em 7 classes de teal, da mais clara à mais escura. As 4 claras são o tom mais claro da
# rampa misturado com branco (a matiz não muda) e levam texto escuro; as 3 escuras são da própria rampa
# e levam texto branco. Os dois lados têm 4,5:1 ou mais com o texto (há teste). O meio da rampa fica de
# fora: nele, nem o branco nem o escuro chegam a 4,5:1.
CALOR = (
    *(graficos.misturar(graficos.RAMPA_TEAL[-1], graficos.FUNDO, t) for t in (0.86, 0.64, 0.42, 0.10)),
    graficos.RAMPA_TEAL[5], graficos.RAMPA_TEAL[2], graficos.RAMPA_TEAL[0],
)
SEM_ATRASO = "#f6f8fa"  # 0%: ninguém da safra chegou ao atraso (superfície 2, com texto de apoio)

ICONES = {
    "curvas": '<path d="M4 4v15a1 1 0 0 0 1 1h15"/><path d="M8 16.5c4.5-.4 8.2-3.4 11-9"/>'
              '<path d="M8 16.5c2.6-1.5 4.8-5 6.3-10"/>',
    "nota": '<rect x="3" y="6.5" width="18" height="11" rx="2.5"/><circle cx="12" cy="12" r="2.5"/>'
            '<path d="M6.5 12h.01M17.5 12h.01"/>',
    "carteira": '<path d="M19 9V7.5A2.5 2.5 0 0 0 16.5 5h-10A2.5 2.5 0 0 0 4 7.5v9A2.5 2.5 0 0 0 6.5 19h10'
                'a2.5 2.5 0 0 0 2.5-2.5V15"/><path d="M14.5 9H20v6h-5.5a3 3 0 0 1 0-6z"/>',
    "escudo": '<path d="M12 3.5l7 2.6v5.4c0 4.2-2.9 7.6-7 9-4.1-1.4-7-4.8-7-9V6.1z"/><path d="M9 12l2 2 4-4"/>',
    "relogio": '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
}

COMO_LER = (
    ("Safra", "O mês de originação do contrato."),
    ("MOB", "Mês de vida da safra: o MOB 1 é o fim do mês seguinte ao da originação."),
    ('"Já teve" (ever)', "O contrato conta a partir do mês em que alguma parcela completou o atraso e segue "
                         "contando mesmo se pagar depois; por isso as curvas nunca descem."),
    ("Saldo devedor", "Parcelas a vencer trazidas a valor presente pela taxa do contrato (dias corridos / 30) "
                      "mais as vencidas em aberto, pelo valor de face."),
    ("Faixas e percentuais", "Tabela de referência da Resolução CMN 2.682/99, só para estudo."),
    ("Dados", "Fictícios, gerados por script com semente fixa: rodar de novo produz a mesma carteira."),
)

ESTILO = """
:root {
  --marca: #2f7189; --marca-clara: #4a97b0; --marca-escura: #235769; --verde: #45a870;
  --degrade: linear-gradient(105deg, #4cb27a 0%, #3a9a85 45%, #2f7189 100%);
  --degrade-selo: linear-gradient(135deg, #3a9a85 0%, #2f7189 55%, #235769 100%);
  --pagina: #eef1f4; --cartao: #ffffff; --superficie-2: #f6f8fa;
  --texto: #1e2a32; --texto-2: #465662; --apoio: #626f79;
  --grade: #e8ecf0; --eixo: #c6d0d8; --borda: #e1e6eb;
  --selecao: #3b82f6; --selecao-fundo: #eaf2fe; --atencao: #f2c037;
  --trilho: #edf5f7;
  --sombra: 0 2px 10px rgba(30, 42, 50, .06), 0 1px 2px rgba(30, 42, 50, .05);
  --raio: 12px;
  --mono: ui-monospace, "Cascadia Mono", Consolas, "Courier New", monospace;
}
* { box-sizing: border-box; }
html { color-scheme: light; -webkit-text-size-adjust: 100%; }
body { margin: 0; background: var(--pagina); color: var(--texto);
       font: 400 14px/1.5 Nunito, system-ui, "Segoe UI", sans-serif; }
main { max-width: 1280px; margin: 0 auto; padding: 24px 24px 28px; }
p, h1, h2, figure, dl, dd { margin: 0; }
b { font-weight: 800; }
svg { display: block; }
.rotulo { font-size: 10px; font-weight: 800; letter-spacing: .08em; text-transform: uppercase; color: var(--apoio); }
.oculto { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
.selo { flex: none; display: grid; place-items: center; width: 32px; height: 32px; border-radius: 9px;
        background: var(--degrade-selo); color: #fff; }
.selo svg { width: 18px; height: 18px; }

/* Faixa do topo */
.faixa { padding: 26px 30px 20px; border-radius: 16px; background: var(--degrade); color: #fff;
         box-shadow: var(--sombra); }
.faixa-topo { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.faixa h1 { display: flex; align-items: center; gap: 12px; font-size: 24px; font-weight: 800; line-height: 1.25; }
.faixa h1 svg { flex: none; width: 26px; height: 26px; }
.faixa-sub { margin: 4px 0 0 38px; font-size: 14px; font-weight: 600; }
.pilula { padding: 6px 14px; border-radius: 999px; background: #fff; color: var(--texto-2); font-size: 12px;
          white-space: nowrap; box-shadow: var(--sombra); }
.pilula b { color: var(--texto); }
.indicadores { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; margin-top: 22px; }
.indicador { padding: 16px 18px; border-radius: var(--raio); background: var(--cartao); color: var(--texto);
             box-shadow: 0 6px 18px rgba(18, 56, 66, .14); }
.indicador-topo { display: flex; align-items: center; gap: 10px; }
.valor { margin-top: 12px; font-size: 24px; font-weight: 800; line-height: 1.2; letter-spacing: -.01em;
         color: var(--marca-escura); }
.detalhe { margin-top: 4px; font-size: 12px; color: var(--texto-2); }
.faixa-pe { margin-top: 18px; padding-top: 14px; border-top: 1px solid rgba(255, 255, 255, .3);
            font-size: 12px; font-weight: 600; }

/* Seções e cartões */
.secao { margin-top: 48px; }
.secao-topo { margin-bottom: 14px; }
.secao-cabeca { display: flex; align-items: center; gap: 12px; }
.secao-numero { flex: none; display: grid; place-items: center; width: 28px; height: 28px; border-radius: 50%;
                background: var(--degrade-selo); color: #fff; font-size: 14px; font-weight: 800;
                box-shadow: var(--sombra); }
.secao h2 { font-size: 18px; font-weight: 800; line-height: 1.3; }
.intro { max-width: 940px; margin: 6px 0 0 40px; color: var(--texto-2); }
.cartao { padding: 18px 20px; border-radius: var(--raio); background: var(--cartao); box-shadow: var(--sombra); }

/* 1. Curvas de safra */
.legenda-safras { display: flex; align-items: center; gap: 24px; padding: 14px 20px; }
.legenda-safras .rotulo { flex: none; }
.legenda-safras .rotulo span { display: block; margin-top: 2px; font-size: 12px; font-weight: 600;
                               letter-spacing: 0; text-transform: none; color: var(--texto-2); }
.legenda-safras ol { flex: 1; display: grid; grid-auto-flow: column; grid-auto-columns: minmax(0, 1fr); gap: 4px;
                     margin: 0; padding: 0; list-style: none; }
.legenda-safras li { font-size: 12px; font-weight: 600; text-align: center; color: var(--texto-2); }
.legenda-safras li i { display: block; height: 6px; margin-bottom: 5px; border-radius: 3px; }
.trio { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; margin-top: 14px; }
.curva { position: relative; overflow: hidden; padding-top: 18px; }
.curva::before { content: ""; position: absolute; top: 0; left: 0; right: 0; height: 4px; background: var(--degrade); }
.curva figcaption { display: flex; align-items: baseline; justify-content: space-between; gap: 8px;
                    margin-bottom: 8px; }
.curva figcaption b { font-size: 14px; }
.curva figcaption span { font-size: 12px; color: var(--apoio); }
.curva svg { width: 100%; height: auto; }
.serie:hover .linha { stroke: var(--selecao); stroke-width: 3; }
.serie:hover .ponta { fill: var(--selecao); }
.nota { margin-top: 14px; padding: 12px 18px; border-left: 4px solid var(--atencao); border-radius: var(--raio);
        background: var(--cartao); box-shadow: var(--sombra); color: var(--texto-2); }
.nota b { color: var(--texto); }

/* 2. Tabela das safras: abas só com CSS */
.abas > input { position: absolute; opacity: 0; pointer-events: none; }
.abas-grupo { display: inline-block; margin-right: 8px; vertical-align: middle; }
.abas-grupo ~ .abas-grupo { margin-left: 18px; }
.abas > label { display: inline-block; margin-right: 6px; padding: 5px 14px; border: 1px solid var(--borda);
                border-radius: 999px; background: var(--cartao); color: var(--texto-2); font-size: 12px;
                font-weight: 700; vertical-align: middle; cursor: pointer; }
.abas > label:hover { border-color: var(--eixo); color: var(--texto); }
.abas > input:checked + label { border-color: var(--selecao); background: var(--selecao-fundo); color: var(--texto); }
.abas > input:focus-visible + label { outline: 2px solid var(--selecao); outline-offset: 2px; }
.painel { display: none; margin-top: 16px; overflow-x: auto; }
ABA_ABERTA { display: block; }
.matriz { width: 100%; border-collapse: separate; border-spacing: 3px; font-variant-numeric: tabular-nums; }
.matriz caption { padding: 0 3px 10px; text-align: left; font-size: 12px; color: var(--texto-2); }
.matriz thead th { padding: 0 2px 4px; font-size: 12px; font-weight: 700; color: var(--apoio); }
.matriz thead .grupo, .matriz thead .esq, .matriz thead .num { font-size: 10px; font-weight: 800;
                                                                letter-spacing: .08em; text-transform: uppercase; }
.matriz .esq { text-align: left; }
.matriz thead .num { padding-right: 12px; text-align: right; }
.matriz tbody th { padding: 0 8px 0 2px; font-size: 12px; font-weight: 800; text-align: left; white-space: nowrap; }
.matriz td { min-width: 54px; height: 38px; padding: 2px; border-radius: 6px; text-align: center; line-height: 1.2;
             white-space: nowrap; }
.matriz td b { display: block; font-size: 12px; }
.matriz td small { display: block; font-size: 10px; font-weight: 600; }
.matriz td.total { padding-right: 12px; text-align: right; font-size: 12px; font-weight: 700; color: var(--texto-2); }
.escala { display: flex; flex-wrap: wrap; align-items: flex-start; gap: 12px 28px; margin-top: 14px; padding-top: 14px;
          border-top: 1px solid var(--grade); font-size: 12px; line-height: 10px; color: var(--texto-2); }
.escala i { display: block; height: 10px; border-radius: 2px; }
.zero { display: flex; align-items: center; gap: 6px; }
.zero i { width: 22px; background: var(--superficie-2); box-shadow: inset 0 0 0 1px var(--borda); }
.passos { position: relative; display: flex; gap: 2px; margin-left: 10px; padding-bottom: 20px; }
.passos > span { position: relative; width: 48px; }
.passos small { position: absolute; top: 15px; left: 0; transform: translateX(-50%); font-size: 12px;
                line-height: 1.2; white-space: nowrap; }
.passos small.fim { left: 100%; }
.escala-nota { margin-left: auto; color: var(--apoio); }

/* 3. PDD por faixa */
.rolagem { overflow-x: auto; }
.tabela { width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; }
.tabela th, .tabela td { padding: 10px 14px; border-bottom: 1px solid var(--grade); text-align: right;
                         white-space: nowrap; }
.tabela thead th { padding-top: 2px; border-bottom-color: var(--borda); font-size: 10px; font-weight: 800;
                   letter-spacing: .08em; text-transform: uppercase; color: var(--apoio); }
.tabela tr > :first-child { padding-left: 4px; text-align: left; }
.tabela tr > :last-child { padding-right: 4px; }
.tabela tbody th { font-size: 12px; font-weight: 600; color: var(--apoio); }
.nivel { display: inline-flex; align-items: center; gap: 8px; width: 36px; font-size: 14px; font-weight: 800;
         color: var(--texto); }
.nivel::before { content: ""; width: 10px; height: 10px; border-radius: 3px; background: var(--cor); }
.tabela tfoot th, .tabela tfoot td { border-top: 1px solid var(--eixo); border-bottom: 0; font-weight: 800; }
.participacao { width: 34%; }
.participacao div { display: flex; align-items: center; gap: 12px; }
.medidor { flex: 1; height: 10px; overflow: hidden; border-radius: 3px; background: var(--trilho); }
.medidor i { display: block; height: 100%; min-width: 2px; border-radius: 0 3px 3px 0; }
.participacao b { width: 48px; font-weight: 700; text-align: right; }
.tabela tfoot .participacao b { font-weight: 800; }
.tabela tfoot .medidor { background: transparent; }

/* 4. Como ler */
.definicoes { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 18px 28px; }
.definicoes div { padding-left: 14px; border-left: 2px solid var(--grade); }
.definicoes dd { margin-top: 4px; color: var(--texto-2); }

/* Rodapé */
.rodape { margin-top: 48px; padding-top: 16px; border-top: 1px solid var(--borda); font-size: 12px;
          color: var(--texto-2); }
.rodape p { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 10px; }
.rodape p + p { margin-top: 8px; color: var(--apoio); }
.rodape-marca { display: inline-flex; align-items: center; gap: 8px; font-size: 14px; font-weight: 800;
                color: var(--texto); }
.rodape-marca .selo { width: 22px; height: 22px; border-radius: 6px; }
.rodape-marca .selo svg { width: 14px; height: 14px; }
code { padding: 1px 6px; border: 1px solid var(--borda); border-radius: 6px; background: var(--cartao);
       color: var(--texto); font: 12px var(--mono); }

@media (max-width: 1040px) {
  .indicadores { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .trio { grid-template-columns: minmax(0, 1fr); }
  .definicoes { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .legenda-safras { flex-direction: column; align-items: stretch; gap: 12px; }
}
@media (max-width: 640px) {
  main { padding: 16px 16px 24px; }
  .faixa { padding: 20px 18px 16px; }
  .faixa-topo { flex-direction: column; }
  .faixa-sub, .intro { margin-left: 0; }
  .indicadores, .definicoes { grid-template-columns: minmax(0, 1fr); }
  .legenda-safras ol { grid-auto-flow: row; grid-template-columns: repeat(6, minmax(0, 1fr)); row-gap: 8px; }
  .abas-grupo { display: block; margin: 10px 0 6px; }
  .abas-grupo ~ .abas-grupo { margin-left: 0; }
  .escala-nota { margin-left: 0; }
}
"""


def fonte_embutida() -> str:
    """@font-face da Nunito com o arquivo dentro do HTML (base64): o relatório abre sem rede."""
    dados = base64.b64encode(FONTE_NUNITO.read_bytes()).decode("ascii")
    return (
        "/* Nunito: Copyright 2014 The Nunito Project Authors. SIL Open Font License 1.1 (fontes/OFL.txt) */\n"
        '@font-face { font-family: "Nunito"; font-style: normal; font-weight: 400 800; font-display: swap;\n'
        f'  src: url(data:font/woff2;base64,{dados}) format("woff2"); }}\n'
    )


def icone(nome: str) -> str:
    return ('<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" '
            f'stroke-linecap="round" stroke-linejoin="round">{ICONES[nome]}</svg>')


def celulas(*valores: str) -> str:
    return "".join(f"<td>{valor}</td>" for valor in valores)


def indicadores(safras: list[safra.Safra], linhas: list[pdd.LinhaDaFaixa]) -> str:
    saldo = sum(linha.saldo for linha in linhas)
    em_aberto = sum(linha.contratos for linha in linhas)
    provisao = sum(linha.pdd for linha in linhas)
    graves = [linha for linha in linhas if linha.faixa.de > 90]
    itens = [
        ("nota", f"Originado em {len(safras)} safras", moeda_curta(sum(s.valor for s in safras)),
         f"{numero(sum(s.contratos for s in safras))} contratos, "
         f"de {mes_ano(safras[0].inicio)} a {mes_ano(safras[-1].inicio)}"),
        ("carteira", "Saldo devedor na data-base", moeda_curta(saldo), f"{numero(em_aberto)} contratos em aberto"),
        ("escudo", "PDD", moeda_curta(provisao),
         f"{percentual(provisao / saldo)} do saldo devedor de {moeda_curta(saldo)}"),
        ("relogio", "Mais de 90 dias de atraso", moeda_curta(sum(linha.saldo for linha in graves)),
         f"{parte_de(sum(linha.contratos for linha in graves), em_aberto)} contratos em aberto "
         "(faixas E a H)"),
    ]
    return '<div class="indicadores">' + "".join(
        f'<div class="indicador"><div class="indicador-topo"><span class="selo">{icone(nome_do_icone)}</span>'
        f'<p class="rotulo">{rotulo}</p></div><p class="valor">{valor}</p><p class="detalhe">{detalhe}</p></div>'
        for nome_do_icone, rotulo, valor, detalhe in itens
    ) + "</div>"


def faixa_do_topo(data_base: date, safras: list[safra.Safra], linhas: list[pdd.LinhaDaFaixa]) -> str:
    return f"""<header class="faixa">
  <div class="faixa-topo">
    <div>
      <h1>{icone("curvas")}Safras e PDD</h1>
      <p class="faixa-sub">Fintech Exemplo · carteira de consignado · dados fictícios</p>
    </div>
    <p class="pilula">Data-base <b>{data_br(data_base)}</b></p>
  </div>
  {indicadores(safras, linhas)}
  <p class="faixa-pe"><b>{mes_ano(safras[0].inicio)}</b> até <b>{mes_ano(safras[-1].inicio)}</b>
  · {len(safras)} safras mensais · {numero(sum(s.contratos for s in safras))} contratos originados</p>
</header>"""


def cabeca(ordem: int, titulo: str, intro: str = "") -> str:
    """Número no círculo, título e, se houver, o parágrafo de abertura da seção."""
    abertura = f'<p class="intro">{intro}</p>' if intro else ""
    return (f'<div class="secao-topo"><div class="secao-cabeca"><span class="secao-numero">{ordem}</span>'
            f"<h2>{titulo}</h2></div>{abertura}</div>")


def comparacao(safras: list[safra.Safra]) -> str:
    """Nota com as 3 safras mais antigas × as 3 mais novas na mesma idade."""
    maduras = [s for s in safras if len(s.curvas[30]) > MOB_DA_COMPARACAO]
    antigas, novas = maduras[:3], maduras[-3:]
    antes = safra.acumulado(antigas, 30, MOB_DA_COMPARACAO)
    depois = safra.acumulado(novas, 30, MOB_DA_COMPARACAO)
    piorou = depois[0] / depois[1] > antes[0] / antes[1]
    return (
        f"<b>As safras novas atrasam {'mais' if piorou else 'menos'}.</b> "
        f"Na mesma idade ({MOB_DA_COMPARACAO} meses de vida), a fatia de contratos que já teve 30 dias "
        f"ou mais de atraso {'subiu' if piorou else 'caiu'} de <b>{parte_de(*antes)}</b> nas safras de "
        f"{mes_ano(antigas[0].inicio)} a {mes_ano(antigas[-1].inicio)} para <b>{parte_de(*depois)}</b> "
        f"nas de {mes_ano(novas[0].inicio)} a {mes_ano(novas[-1].inicio)}."
    )


def curvas(safras: list[safra.Safra]) -> str:
    """Legenda das safras, os três painéis (30, 60 e 90 dias) em cartões e a nota da comparação."""
    legenda = "".join(f'<li><i style="background:{cor}"></i>{mes_ano(s.inicio)}</li>'
                      for s, cor in zip(safras, safra.cores_das_safras(safras)))
    paineis = "".join(
        f'<figure class="cartao curva"><figcaption><b>{dias} dias ou mais de atraso</b>'
        f"<span>% dos contratos</span></figcaption>{safra.svg_painel(safras, dias)}</figure>"
        for dias in safra.ATRASOS
    )
    return (
        f'<div class="cartao legenda-safras"><p class="rotulo">Safra (mês de originação)'
        f"<span>da mais antiga (clara) à mais nova (escura)</span></p><ol>{legenda}</ol></div>"
        f'<div class="trio">{paineis}</div>'
        f'<p class="nota">{comparacao(safras)}</p>'
    )


def classes_de_calor(maior: float) -> tuple[list[float], list[str]]:
    """Limites redondos das classes (de 0 até cobrir `maior`) e a cor de cada uma, das 7 de CALOR.

    Com menos de 7 classes, as cores saem espalhadas pela rampa: a última é sempre a mais escura.
    """
    bordas = graficos.marcas(maior, intervalos=len(CALOR))
    quantas = len(bordas) - 1
    cores = [CALOR[round(i * (len(CALOR) - 1) / max(quantas - 1, 1))] for i in range(quantas)]
    return bordas, cores


def cor_do_calor(fracao: float, bordas: list[float], cores: list[str]) -> str:
    """Zero fica neutro; o resto cai na classe (borda anterior, borda] que o contém."""
    if fracao == 0:
        return SEM_ATRASO
    return cores[min(max(bisect_left(bordas, fracao) - 1, 0), len(cores) - 1)]


def escala(bordas: list[float], cores: list[str], por_valor: bool) -> str:
    """Legenda do mapa de calor: as classes lado a lado, com os limites embaixo."""
    casas = 0 if all(round(b * 100, 9).is_integer() for b in bordas) else 1
    passos = "".join(f'<span><i style="background:{cor}"></i><small>{percentual(borda, casas)}</small></span>'
                     for borda, cor in zip(bordas, cores))
    return (
        f'<div class="escala"><span class="rotulo">% {"do valor" if por_valor else "dos contratos"} da safra</span>'
        f'<span class="zero"><i></i>nenhum</span>'
        f'<span class="passos">{passos}<small class="fim">{percentual(bordas[-1], casas)}</small></span>'
        f'<span class="escala-nota">Célula vazia: a safra ainda não chegou a essa idade.</span></div>'
    )


def tabela_matriz(safras: list[safra.Safra], dias: int, por_valor: bool) -> str:
    """Safra × MOB: % da safra que já atingiu `dias` de atraso e, embaixo, o número absoluto."""
    def fracao(ponto: safra.Ponto) -> float:
        return ponto.fracao_valor if por_valor else ponto.fracao_contratos

    mob_maximo = max(len(s.curvas[dias]) for s in safras) - 1
    bordas, cores = classes_de_calor(max(fracao(p) for s in safras for p in s.curvas[dias]) or 1)
    idades = "".join(f"<th scope='col'>{mob}</th>" for mob in range(1, mob_maximo + 1))
    medida = "do valor liberado" if por_valor else "dos contratos"
    cabeca_da_tabela = (
        f"<tr><th colspan='2'></th>"
        f"<th class='grupo' colspan='{mob_maximo}'>meses de vida da safra (MOB)</th></tr>"
        f"<tr><th scope='col' class='esq'>Safra</th>"
        f"<th scope='col' class='num'>{'Valor' if por_valor else 'Contratos'}</th>{idades}</tr>"
    )
    linhas = []
    for s in safras:
        nome = mes_ano(s.inicio)
        total = moeda_curta(s.valor) if por_valor else numero(s.contratos)
        tds = []
        for ponto in s.curvas[dias][1:]:
            fatia = percentual(fracao(ponto))
            absoluto = moeda_curta(ponto.valor) if por_valor else numero(ponto.contratos)
            fundo = cor_do_calor(fracao(ponto), bordas, cores)
            tinta = graficos.APOIO if fundo == SEM_ATRASO else graficos.texto_sobre(fundo)
            dica = escape(f"Safra {nome} · MOB {ponto.mob}: {fatia} · {absoluto} de {total}")
            tds.append(f'<td style="background:{fundo};color:{tinta}" title="{dica}">'
                       f'<b>{fatia}</b><small>{absoluto.removeprefix("R$ ")}</small></td>')
        tds += ["<td></td>"] * (mob_maximo - len(tds))
        linhas.append(f"<tr><th scope='row'>{nome}</th><td class='total'>{total}</td>{''.join(tds)}</tr>")
    embaixo = "embaixo, o valor em reais" if por_valor else "embaixo, quantos contratos"
    return (
        f"<table class='matriz'><caption>{dias} dias ou mais de atraso · % {medida} de cada safra "
        f"que já chegou a esse atraso; {embaixo}</caption><thead>{cabeca_da_tabela}</thead>"
        f"<tbody>{''.join(linhas)}</tbody></table>{escala(bordas, cores, por_valor)}"
    )


def abas_das_matrizes(safras: list[safra.Safra]) -> tuple[str, str]:
    """Seis tabelas (30/60/90 dias × contratos/valor) trocadas por abas só com CSS.

    Devolve o HTML e os seletores CSS que mostram o painel da aba marcada.
    """
    controles, paineis, seletores = [], [], []
    for por_valor in (False, True):
        medida = "do valor" if por_valor else "dos contratos"
        controles.append(f'<span class="rotulo abas-grupo">Por {"valor" if por_valor else "contratos"}</span>')
        for dias in safra.ATRASOS:
            chave = f"{dias}-{'valor' if por_valor else 'contratos'}"
            marcada = "" if seletores else " checked"
            controles.append(f'<input type="radio" name="matriz" id="aba-{chave}"{marcada}>'
                             f'<label for="aba-{chave}">{dias}+ dias<span class="oculto"> · % {medida}</span></label>')
            paineis.append(f'<div class="painel painel-{chave}">{tabela_matriz(safras, dias, por_valor)}</div>')
            seletores.append(f"#aba-{chave}:checked ~ .painel-{chave}")
    return f'<div class="abas">{"".join(controles)}{"".join(paineis)}</div>', ", ".join(seletores)


def tabela_pdd(linhas: list[pdd.LinhaDaFaixa]) -> str:
    """Faixas A a H com a barra da fatia de cada uma na PDD (cor mais escura = atraso maior)."""
    contratos = sum(linha.contratos for linha in linhas)
    saldo = sum(linha.saldo for linha in linhas)
    provisao = sum(linha.pdd for linha in linhas)
    titulos = "".join(f"<th scope='col'>{titulo}</th>"
                      for titulo in ("Provisão", "Contratos", "Saldo devedor", "PDD"))
    corpo = []
    for linha, cor in zip(linhas, pdd.cores_das_faixas()):
        faixa = linha.faixa
        fatia = linha.pdd / provisao if provisao else Decimal(0)
        dica = escape(f"Faixa {faixa.nivel} ({faixa.descricao}): {percentual(fatia)} da PDD · "
                      f"{moeda(linha.pdd)} de {moeda(provisao)}")
        barra = f'<i style="width:{float(fatia) * 100:.2f}%;background:{cor}"></i>' if linha.pdd else ""
        corpo.append(
            f"<tr title='{dica}'><th scope='row'><span class='nivel' style='--cor:{cor}'>{faixa.nivel}</span>"
            f"{faixa.descricao}</th>"
            + celulas(percentual(faixa.provisao, 1, enxuto=True), numero(linha.contratos),
                      moeda(linha.saldo), moeda(linha.pdd))
            + f"<td class='participacao'><div><span class='medidor'>{barra}</span>"
              f"<b>{percentual(fatia)}</b></div></td></tr>"
        )
    total = ("<tr><th scope='row'>Total</th>"
             + celulas(percentual(provisao / saldo), numero(contratos), moeda(saldo), moeda(provisao))
             + "<td class='participacao'><div><span class='medidor'></span><b>100%</b></div></td></tr>")
    return (f"<table class='tabela'><thead><tr><th scope='col'>Faixa · atraso</th>{titulos}"
            f"<th scope='col' class='participacao'>% da PDD</th></tr></thead>"
            f"<tbody>{''.join(corpo)}</tbody><tfoot>{total}</tfoot></table>")


def como_ler() -> str:
    itens = "".join(f'<div><dt class="rotulo">{termo}</dt><dd>{texto}</dd></div>' for termo, texto in COMO_LER)
    return f'<div class="cartao"><dl class="definicoes">{itens}</dl></div>'


def rodape(data_base: date, safras: list[safra.Safra]) -> str:
    return f"""<footer class="rodape">
  <p><span class="rodape-marca"><span class="selo">{icone("curvas")}</span>Fintech Exemplo</span>
  <span>· dados fictícios, gerados por script</span>
  <span>Fonte: <code>contratos</code> <code>parcelas</code> <code>parametros</code>
  · SQLite gerado por <code>gerar_carteira.py</code></span></p>
  <p>Data-base {data_br(data_base)} · {numero(sum(s.contratos for s in safras))} contratos em {len(safras)} safras
  · tipografia Nunito (SIL OFL 1.1)</p>
</footer>"""


def montar(data_base: date, safras: list[safra.Safra], linhas: list[pdd.LinhaDaFaixa]) -> str:
    abas, aba_aberta = abas_das_matrizes(safras)
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Safras e PDD · Fintech Exemplo</title>
<style>
{fonte_embutida()}{ESTILO.replace("ABA_ABERTA", aba_aberta)}</style>
</head>
<body>
<main>
{faixa_do_topo(data_base, safras, linhas)}
<section class="secao" id="curvas">
  {cabeca(1, "Curvas de safra",
          "% dos contratos de cada safra que já tiveram alguma parcela com 30, 60 ou 90 dias ou mais de "
          "atraso, ao fim de cada mês de vida. Uma linha por safra: quanto mais escura, mais recente. "
          "Passe o mouse para ver os números.")}
  {curvas(safras)}
</section>
<section class="secao" id="tabela">
  {cabeca(2, "Tabela das safras",
          "Os números por trás das curvas, também pelo valor liberado. Cada célula traz o % da safra e, "
          "embaixo, quantos contratos (ou quanto valor) isso representa; o total da safra está na segunda "
          "coluna.")}
  <div class="cartao">{abas}</div>
</section>
<section class="secao" id="pdd">
  {cabeca(3, "PDD por faixa de atraso",
          "Cada contrato vai inteiro para a faixa da parcela mais atrasada (arrasto), e o percentual da "
          "faixa incide sobre o saldo devedor na data-base.")}
  <div class="cartao"><div class="rolagem">{tabela_pdd(linhas)}</div></div>
</section>
<section class="secao" id="como-ler">
  {cabeca(4, "Como ler")}
  {como_ler()}
</section>
{rodape(data_base, safras)}
</main>
</body>
</html>
"""


def main() -> None:
    with abrir_banco() as conexao:
        data_base, safras = safra.calcular(conexao)
        _, linhas = pdd.calcular(conexao)
    SAIDA.mkdir(exist_ok=True)
    destino = SAIDA / "relatorio.html"
    destino.write_text(montar(data_base, safras, linhas), encoding="utf-8")
    print(f"Relatório gravado em {destino}")


if __name__ == "__main__":
    main()
