"""Monta saida/relatorio.html: curvas de safra, PDD por faixa e as tabelas, num arquivo só."""

from datetime import date
from html import escape

import graficos
import pdd
import safra
from comum import SAIDA, abrir_banco, data_br, mes_ano, moeda, moeda_curta, numero, parte_de, percentual

CALOR = ("#f7f0e5", "#d6b78a", graficos.BRONZE)  # creme → areia → bronze: quanto mais escuro, mais atraso
MOB_DA_COMPARACAO = 6

ESTILO = """
:root { --marinho: #1c2d42; --areia: #d6b78a; --bronze: #8a6230; --creme: #f7f0e5;
        --tinta: #18212c; --cinza: #677282; --fundo: #ffffff; --linha: #e4e7eb; }
* { box-sizing: border-box; }
body { margin: 0; background: var(--fundo); color: var(--tinta);
       font: 14px/1.5 "Inter", "Segoe UI", Arial, sans-serif; }
main { max-width: 1248px; margin: 0 auto; padding: 36px 24px 40px; }
header { border-bottom: 2px solid var(--areia); padding-bottom: 16px; margin-bottom: 24px; }
.sobretitulo { margin: 0 0 4px; color: var(--bronze); font-size: 12px; font-weight: 600;
               letter-spacing: .08em; text-transform: uppercase; }
h1 { margin: 0; color: var(--marinho); font-size: 30px; line-height: 1.2; }
.subtitulo { margin: 6px 0 0; color: var(--cinza); }
.cartoes { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 36px; }
.cartao { background: var(--creme); border-radius: 10px; padding: 14px 18px; }
.cartao p { margin: 0; }
.rotulo { color: var(--cinza); font-size: 13px; }
.valor { color: var(--marinho); font-size: 26px; font-weight: 600; margin: 2px 0; }
.detalhe { color: var(--cinza); font-size: 12.5px; }
section { margin-bottom: 40px; }
h2 { margin: 0 0 4px; color: var(--marinho); font-size: 20px; }
.intro { margin: 0 0 18px; color: var(--cinza); max-width: 920px; }
svg { display: block; max-width: 100%; height: auto; }
.destaque { margin: 18px 0 0; padding: 10px 14px; background: var(--creme);
            border-left: 3px solid var(--areia); border-radius: 0 8px 8px 0; }
.abas > input { position: absolute; opacity: 0; }
.abas > label { display: inline-block; margin: 0 6px 12px 0; padding: 4px 12px;
                border: 1px solid var(--linha); border-radius: 999px;
                color: var(--cinza); font-size: 13px; cursor: pointer; }
.abas > input:checked + label { background: var(--marinho); border-color: var(--marinho); color: #fff; }
.abas > input:focus-visible + label { outline: 2px solid var(--bronze); outline-offset: 2px; }
.painel { display: none; overflow-x: auto; }
ABA_ABERTA { display: block; }
.matriz { width: 100%; border-collapse: separate; border-spacing: 2px; font-variant-numeric: tabular-nums; }
.matriz th { padding: 2px 4px; color: var(--cinza); font-size: 11px; font-weight: 600; }
.matriz th[scope=row], .matriz .esq { text-align: left; }
.matriz th[scope=row] { color: var(--tinta); font-size: 12px; white-space: nowrap; }
.matriz .grupo { text-align: center; font-weight: 400; }
.matriz td { min-width: 54px; padding: 3px 2px; border-radius: 4px; text-align: center; line-height: 1.25; }
.matriz td span { display: block; font-size: 12px; font-weight: 600; }
.matriz td small { display: block; font-size: 10.5px; }
.matriz td.total { padding-right: 10px; text-align: right; font-size: 12px; }
.legenda { margin: 10px 0 0; color: var(--cinza); font-size: 12.5px; }
.dupla { display: grid; grid-template-columns: 520px 1fr; gap: 32px; align-items: start; }
.pdd { width: 100%; border-collapse: collapse; font-size: 13px; font-variant-numeric: tabular-nums; }
.pdd th, .pdd td { padding: 7px 8px; border-bottom: 1px solid var(--linha);
                   text-align: right; white-space: nowrap; }
.pdd thead th { color: var(--cinza); font-size: 12px; font-weight: 600; }
.pdd .esq { text-align: left; }
.pdd small { margin-left: 6px; color: var(--cinza); font-size: 12px; font-weight: 400; }
.pdd tfoot th, .pdd tfoot td { border-top: 2px solid var(--marinho); border-bottom: 0; font-weight: 600; }
.notas { border-top: 1px solid var(--linha); padding-top: 14px; color: var(--cinza); font-size: 12.5px; }
.notas ul { margin: 6px 0 0; padding-left: 18px; }
.notas b { color: var(--tinta); }
@media (max-width: 960px) {
  .cartoes { grid-template-columns: repeat(2, 1fr); }
  .dupla { grid-template-columns: 1fr; }
}
"""


def celulas(*valores: str) -> str:
    return "".join(f"<td>{valor}</td>" for valor in valores)


def cartoes(safras: list[safra.Safra], linhas: list[pdd.LinhaDaFaixa]) -> str:
    saldo = sum(linha.saldo for linha in linhas)
    em_aberto = sum(linha.contratos for linha in linhas)
    provisao = sum(linha.pdd for linha in linhas)
    graves = [linha for linha in linhas if linha.faixa.de > 90]
    itens = [
        (f"Originado em {len(safras)} safras", moeda_curta(sum(s.valor for s in safras)),
         f"{numero(sum(s.contratos for s in safras))} contratos, "
         f"de {mes_ano(safras[0].inicio)} a {mes_ano(safras[-1].inicio)}"),
        ("Saldo devedor na data-base", moeda_curta(saldo), f"{numero(em_aberto)} contratos em aberto"),
        ("PDD", moeda_curta(provisao),
         f"{percentual(provisao / saldo)} do saldo devedor de {moeda_curta(saldo)}"),
        ("Mais de 90 dias de atraso (E a H)", moeda_curta(sum(linha.saldo for linha in graves)),
         f"{parte_de(sum(linha.contratos for linha in graves), em_aberto)} contratos em aberto"),
    ]
    return '<div class="cartoes">' + "".join(
        f'<div class="cartao"><p class="rotulo">{rotulo}</p><p class="valor">{valor}</p>'
        f'<p class="detalhe">{detalhe}</p></div>'
        for rotulo, valor, detalhe in itens
    ) + "</div>"


def comparacao(safras: list[safra.Safra]) -> str:
    """Frase com as 3 safras mais antigas × as 3 mais novas na mesma idade."""
    maduras = [s for s in safras if len(s.curvas[30]) > MOB_DA_COMPARACAO]
    antigas, novas = maduras[:3], maduras[-3:]
    antes = safra.acumulado(antigas, 30, MOB_DA_COMPARACAO)
    depois = safra.acumulado(novas, 30, MOB_DA_COMPARACAO)
    verbo = "subiu" if depois[0] / depois[1] > antes[0] / antes[1] else "caiu"
    return (
        f"Na mesma idade ({MOB_DA_COMPARACAO} meses de vida), a fatia de contratos que já teve 30 dias "
        f"ou mais de atraso {verbo} de <b>{parte_de(*antes)}</b> nas safras de "
        f"{mes_ano(antigas[0].inicio)} a {mes_ano(antigas[-1].inicio)} para <b>{parte_de(*depois)}</b> "
        f"nas de {mes_ano(novas[0].inicio)} a {mes_ano(novas[-1].inicio)}."
    )


def tabela_matriz(safras: list[safra.Safra], dias: int, por_valor: bool) -> str:
    """Safra × MOB: % da safra que já atingiu `dias` de atraso e, embaixo, o número absoluto."""
    def fracao(ponto: safra.Ponto) -> float:
        return ponto.fracao_valor if por_valor else ponto.fracao_contratos

    mob_maximo = max(len(s.curvas[dias]) for s in safras) - 1
    maior = max(fracao(p) for s in safras for p in s.curvas[dias]) or 1
    idades = "".join(f"<th scope='col'>{mob}</th>" for mob in range(1, mob_maximo + 1))
    cabeca = (
        f"<tr><th colspan='2'></th>"
        f"<th class='grupo' colspan='{mob_maximo}'>meses de vida da safra (MOB)</th></tr>"
        f"<tr><th scope='col' class='esq'>Safra</th>"
        f"<th scope='col'>{'Valor' if por_valor else 'Contratos'}</th>{idades}</tr>"
    )
    linhas = []
    for s in safras:
        nome = mes_ano(s.inicio)
        total = moeda_curta(s.valor) if por_valor else numero(s.contratos)
        tds = []
        for ponto in s.curvas[dias][1:]:
            fatia = percentual(fracao(ponto))
            absoluto = moeda_curta(ponto.valor) if por_valor else numero(ponto.contratos)
            fundo = graficos.na_rampa(CALOR, fracao(ponto) / maior)
            dica = escape(f"Safra {nome} · MOB {ponto.mob}: {fatia} · {absoluto} de {total}")
            tds.append(f'<td style="background:{fundo};color:{graficos.texto_sobre(fundo)}" title="{dica}">'
                       f"<span>{fatia}</span><small>{absoluto}</small></td>")
        tds += ["<td></td>"] * (mob_maximo - len(tds))
        linhas.append(f"<tr><th scope='row'>{nome}</th><td class='total'>{total}</td>{''.join(tds)}</tr>")
    return f"<table class='matriz'><thead>{cabeca}</thead><tbody>{''.join(linhas)}</tbody></table>"


def abas_das_matrizes(safras: list[safra.Safra]) -> tuple[str, str]:
    """Seis tabelas (30/60/90 dias × contratos/valor) trocadas por abas só com CSS.

    Devolve o HTML e os seletores CSS que mostram o painel da aba marcada.
    """
    entradas, paineis, seletores = [], [], []
    for por_valor in (False, True):
        for dias in safra.ATRASOS:
            chave = f"{dias}-{'valor' if por_valor else 'contratos'}"
            marcada = "" if entradas else " checked"
            nome = f"{dias}+ · % {'do valor' if por_valor else 'dos contratos'}"
            entradas.append(f'<input type="radio" name="matriz" id="aba-{chave}"{marcada}>'
                            f'<label for="aba-{chave}">{nome}</label>')
            tabela = tabela_matriz(safras, dias, por_valor)
            paineis.append(f'<div class="painel painel-{chave}">{tabela}</div>')
            seletores.append(f"#aba-{chave}:checked ~ .painel-{chave}")
    return f'<div class="abas">{"".join(entradas)}{"".join(paineis)}</div>', ", ".join(seletores)


def tabela_pdd(linhas: list[pdd.LinhaDaFaixa]) -> str:
    contratos = sum(linha.contratos for linha in linhas)
    saldo = sum(linha.saldo for linha in linhas)
    provisao = sum(linha.pdd for linha in linhas)
    titulos = "".join(f"<th scope='col'>{titulo}</th>"
                      for titulo in ("Provisão", "Contratos", "Saldo devedor", "PDD", "% da PDD"))
    corpo = "".join(
        f"<tr><th scope='row' class='esq'>{linha.faixa.nivel}<small>{linha.faixa.descricao}</small></th>"
        + celulas(percentual(linha.faixa.provisao, 1, enxuto=True), numero(linha.contratos),
                  moeda(linha.saldo), moeda(linha.pdd), percentual(linha.pdd / provisao))
        + "</tr>"
        for linha in linhas
    )
    total = ("<tr><th scope='row' class='esq'>Total</th>"
             + celulas(percentual(provisao / saldo), numero(contratos), moeda(saldo), moeda(provisao), "100%")
             + "</tr>")
    return (f"<table class='pdd'><thead><tr><th scope='col' class='esq'>Faixa · atraso</th>{titulos}</tr>"
            f"</thead><tbody>{corpo}</tbody><tfoot>{total}</tfoot></table>")


def montar(data_base: date, safras: list[safra.Safra], linhas: list[pdd.LinhaDaFaixa]) -> str:
    abas, aba_aberta = abas_das_matrizes(safras)
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Safras e PDD · Fintech Exemplo</title>
<style>{ESTILO.replace("ABA_ABERTA", aba_aberta)}</style>
</head>
<body>
<main>
<header>
  <p class="sobretitulo">Fintech Exemplo · carteira de consignado · dados fictícios</p>
  <h1>Safras e PDD</h1>
  <p class="subtitulo">Data-base {data_br(data_base)} · {len(safras)} safras mensais,
  de {mes_ano(safras[0].inicio)} a {mes_ano(safras[-1].inicio)}</p>
</header>
{cartoes(safras, linhas)}
<section>
  <h2>Curvas de safra</h2>
  <p class="intro">% dos contratos de cada safra que já tiveram alguma parcela com 30, 60 ou 90 dias
  ou mais de atraso, ao fim de cada mês de vida. Uma linha por safra: quanto mais escura, mais recente.
  Passe o mouse para ver os números.</p>
  {safra.svg_curvas(safras)}
  <p class="destaque">{comparacao(safras)}</p>
</section>
<section>
  <h2>Tabela das safras</h2>
  <p class="intro">Os números por trás das curvas, também pelo valor liberado. Cada célula traz o % da
  safra e, embaixo, quantos contratos (ou quanto valor) isso representa; o total da safra está na
  segunda coluna.</p>
  {abas}
  <p class="legenda">Cor mais escura = maior percentual dentro da tabela aberta.
  Célula vazia: a safra ainda não chegou a essa idade.</p>
</section>
<section>
  <h2>PDD por faixa de atraso</h2>
  <p class="intro">Cada contrato vai inteiro para a faixa da parcela mais atrasada (arrasto), e o
  percentual da faixa incide sobre o saldo devedor na data-base.</p>
  <div class="dupla">
    {pdd.svg_pdd(linhas, largura=520)}
    {tabela_pdd(linhas)}
  </div>
</section>
<footer class="notas">
  <b>Como ler</b>
  <ul>
    <li><b>Safra</b> é o mês de originação; <b>MOB</b> (mês de vida) 1 é o fim do mês seguinte.</li>
    <li><b>"Já teve"</b> (ever): o contrato conta a partir do mês em que alguma parcela completou o
    atraso e segue contando mesmo se pagar depois; por isso as curvas nunca descem.</li>
    <li><b>Saldo devedor</b>: parcelas a vencer trazidas a valor presente pela taxa do contrato
    (dias corridos / 30) mais as vencidas em aberto, pelo valor de face.</li>
    <li><b>Faixas e percentuais</b>: tabela de referência da Resolução CMN 2.682/99, só para estudo.</li>
    <li>Todos os dados são fictícios, gerados por script.</li>
  </ul>
</footer>
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
