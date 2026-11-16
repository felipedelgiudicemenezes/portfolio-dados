"""Relatório da conferência em Markdown e em HTML autocontido (sem CDN nem JavaScript).

O HTML leva o CSS e a fonte Nunito (SIL OFL 1.1, em fontes/) embutidos em base64:
abre igual em qualquer máquina, até sem internet. O visual é o de uma dashboard:
faixa em degradê no topo, tiles com ícone, a tabela das consultas e um cartão por
consulta com o declarado, o lido de fato e a diferença.
"""

from __future__ import annotations

import base64
import re
from collections import Counter
from collections.abc import Iterable
from datetime import datetime
from functools import lru_cache
from html import escape
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from conferir import Conferencia

FONTE = Path(__file__).resolve().parent / "fontes" / "nunito-latin.woff2"

SIMBOLO = {"ok": "✓", "aviso": "!", "erro": "✗"}
STATUS = ("ok", "aviso", "erro")  # ordem dos tiles e da barra do total
NOME = {"ok": "OK", "aviso": "Aviso", "erro": "Erro"}
NOME_NO_TILE = {"ok": "OK", "aviso": "Com aviso", "erro": "Com erro"}
SINAL = {"sobra": "−", "falta": "+"}
SENTIDO = {"sobra": "declarado e não usado", "falta": "usado e não declarado"}
COMECA_COM_USA = re.compile(r"usa\s*:", re.IGNORECASE)

# Ícones 24×24 de traço: pegam a cor do texto em volta (stroke: currentColor).
TRACOS = {
    "banco": '<ellipse cx="12" cy="5.5" rx="7.5" ry="2.8"/>'
             '<path d="M4.5 5.5v13c0 1.55 3.36 2.8 7.5 2.8s7.5-1.25 7.5-2.8v-13"/>'
             '<path d="M4.5 12c0 1.55 3.36 2.8 7.5 2.8s7.5-1.25 7.5-2.8"/>',
    "consultas": '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/>'
                 '<path d="M14 3v5h5M9 13h6M9 17h4"/>',
    "ok": '<circle cx="12" cy="12" r="9"/><path d="M8 12.4l2.8 2.8 5.2-5.6"/>',
    "aviso": '<path d="M12 3.8 21.2 19.6H2.8z"/><path d="M12 9.6v4.2M12 16.9v.1"/>',
    "erro": '<circle cx="12" cy="12" r="9"/><path d="M9.2 9.2l5.6 5.6M14.8 9.2l-5.6 5.6"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v5.2M12 7.7v.1"/>',
    "seta": '<path d="M9.5 6l6 6-6 6"/>',
}

CSS = """
:root {
  --marca: #2f7189;
  --marca-clara: #4a97b0;
  --verde: #45a870;
  --degrade: linear-gradient(105deg, #4cb27a 0%, #3a9a85 45%, #2f7189 100%);
  --pagina: #eef1f4;
  --cartao: #ffffff;
  --superficie-2: #f6f8fa;
  --texto: #1e2a32;
  --texto-2: #465662;
  --apoio: #626f79;
  --grade: #e8ecf0;
  --borda: #e1e6eb;
  --selecao: #3b82f6;
  --selecao-fundo: #eaf2fe;
  --ok: #1d8746;
  --ok-texto: #176b38;
  --ok-fundo: #e5f4ea;
  --ok-trilho: #cfe8d8;
  --aviso: #f2c037;
  --aviso-texto: #8a6100;
  --aviso-fundo: #fdf4d7;
  --aviso-trilho: #f9e7b0;
  --erro: #d53e3e;
  --erro-texto: #b3302f;
  --erro-fundo: #fcebea;
  --erro-trilho: #f5d0cf;
  --sombra: 0 2px 10px rgba(30, 42, 50, .06), 0 1px 2px rgba(30, 42, 50, .05);
  --raio: 12px;
  --raio-faixa: 16px;
  --sans: "Nunito", system-ui, "Segoe UI", sans-serif;
  --mono: "Cascadia Mono", "SFMono-Regular", Menlo, Consolas, "Liberation Mono", monospace;
}
* { box-sizing: border-box; }
html { color-scheme: light; }
@media (prefers-reduced-motion: no-preference) { html { scroll-behavior: smooth; } }
body { margin: 0; background: var(--pagina); color: var(--texto); font: 400 14px/1.5 var(--sans); }
h1, h2, h3, p, dl, dd { margin: 0; }
code, pre { font-family: var(--mono); }
code {
  padding: 1px 6px;
  border: 1px solid var(--borda);
  border-radius: 5px;
  background: var(--superficie-2);
  color: var(--texto);
  font-size: 12px;
  white-space: nowrap;
}
.vh { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
.icone {
  flex: none;
  width: 1em;
  height: 1em;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.pagina { max-width: 1280px; margin: 0 auto; padding: 18px 32px 28px; }

/* Linha de cima e faixa em degradê */
.topo {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 14px;
  color: var(--texto-2);
  font-size: 12px;
}
.topo strong { color: var(--texto); font-weight: 800; }
.carimbo {
  padding: 5px 14px;
  border: 1px solid var(--borda);
  border-radius: 999px;
  background: var(--cartao);
  box-shadow: var(--sombra);
  white-space: nowrap;
}
.faixa {
  padding: 24px 26px 18px;
  border-radius: var(--raio-faixa);
  background: radial-gradient(90% 160% at 100% 0%, rgba(255, 255, 255, .13), rgba(255, 255, 255, 0) 55%), var(--degrade);
  box-shadow: 0 6px 22px rgba(47, 113, 137, .2);
  color: #fff;
}
.faixa h1 {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 24px;
  font-weight: 800;
  line-height: 1.25;
  text-shadow: 0 1px 2px rgba(18, 58, 70, .2);
}
.faixa h1 .icone { width: 28px; height: 28px; stroke-width: 1.8; }
.campos { display: grid; grid-template-columns: 1.3fr 1fr 1.2fr; gap: 14px; margin-top: 20px; }
.campos > div { min-width: 0; }
.campos dt {
  margin-bottom: 6px;
  color: rgba(255, 255, 255, .95);
  font-size: 10px;
  font-weight: 800;
  letter-spacing: .09em;
  text-transform: uppercase;
}
.campos dd {
  padding: 8px 12px;
  border-radius: 8px;
  background: #fff;
  box-shadow: 0 1px 2px rgba(18, 58, 70, .14);
  color: var(--texto);
  font-size: 14px;
  font-weight: 700;
  overflow-wrap: anywhere;
}
.campos dd code { padding: 0; border: 0; background: none; font-size: 14px; font-weight: 400; }
.faixa-rodape {
  margin-top: 18px;
  padding-top: 14px;
  border-top: 1px solid rgba(255, 255, 255, .3);
  color: rgba(255, 255, 255, .95);
  font-size: 12px;
}
.faixa-rodape strong { color: #fff; font-weight: 800; }

/* Tiles */
.tiles { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; margin-top: 14px; }
.tile {
  display: flex;
  gap: 14px;
  padding: 18px;
  border-radius: var(--raio);
  background: var(--cartao);
  box-shadow: var(--sombra);
}
.tile-icone {
  display: grid;
  flex: none;
  place-items: center;
  width: 46px;
  height: 46px;
  border-radius: 12px;
  color: #fff;
}
.tile-icone .icone { width: 24px; height: 24px; }
.tile-total .tile-icone { background: var(--degrade); }
.tile-ok .tile-icone { background: var(--ok); }
.tile-aviso .tile-icone { background: var(--aviso); color: var(--texto); }
.tile-erro .tile-icone { background: var(--erro); }
.tile-corpo { flex: 1; min-width: 0; }
.rotulo {
  color: var(--apoio);
  font-size: 10px;
  font-weight: 800;
  line-height: 16px;
  letter-spacing: .09em;
  text-transform: uppercase;
}
.rotulo code { padding: 0 4px; font-size: 10px; line-height: 14px; letter-spacing: 0; text-transform: none; }
.tile-numero { margin-top: 2px; color: var(--marca); font-size: 24px; font-weight: 800; line-height: 1.2; }
.tile-nota { margin-top: 8px; color: var(--texto-2); font-size: 12px; }
.tile-nota strong { color: var(--texto); font-weight: 800; }
.barra-seg, .medidor { display: flex; gap: 2px; height: 8px; margin-top: 10px; }
.barra-seg > span { flex-basis: 0; border-radius: 999px; }
.medidor { border-radius: 999px; overflow: hidden; }
.medidor > span { border-radius: 999px; }
.seg-ok, .medidor-ok > span { background: var(--ok); }
.seg-aviso, .medidor-aviso > span { background: var(--aviso); }
.seg-erro, .medidor-erro > span { background: var(--erro); }
.medidor-ok { background: var(--ok-trilho); }
.medidor-aviso { background: var(--aviso-trilho); }
.medidor-erro { background: var(--erro-trilho); }

/* Seções */
.secao { margin-top: 48px; }
.secao-cabeca { display: flex; align-items: center; gap: 12px; margin-bottom: 14px; }
.secao-num {
  display: grid;
  flex: none;
  place-items: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--degrade);
  box-shadow: 0 2px 6px rgba(47, 113, 137, .25);
  color: #fff;
  font-size: 12px;
  font-weight: 800;
}
.secao-cabeca h2 { font-size: 18px; font-weight: 800; line-height: 1.3; }
.secao-dica { margin-left: auto; color: var(--apoio); font-size: 12px; }
.cartao { border-radius: var(--raio); background: var(--cartao); box-shadow: var(--sombra); }

/* Status e chips */
.selo {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 11px 3px 8px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 800;
  line-height: 1.4;
  white-space: nowrap;
}
.selo .icone { width: 14px; height: 14px; stroke-width: 2.4; }
.selo-ok { background: var(--ok-fundo); color: var(--ok-texto); }
.selo-aviso { background: var(--aviso-fundo); color: var(--aviso-texto); }
.selo-erro { background: var(--erro-fundo); color: var(--erro-texto); }
.chips { display: flex; flex-wrap: wrap; gap: 6px; }
.chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 2px 8px;
  border: 1px solid var(--borda);
  border-radius: 6px;
  background: var(--superficie-2);
  color: var(--texto);
  font-family: var(--mono);
  font-size: 12px;
  line-height: 1.5;
  white-space: nowrap;
}
.chip-sobra {
  border-style: dashed;
  border-color: #d4a72c;
  background: var(--cartao);
  color: var(--aviso-texto);
  text-decoration: line-through;
}
.chip-falta { border-color: var(--aviso); background: var(--aviso-fundo); color: var(--aviso-texto); font-weight: 700; }
.sinal { display: inline-block; font-family: var(--sans); font-weight: 800; }

/* Tabela das consultas */
.tabela-cartao { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; table-layout: fixed; }
th {
  padding: 11px 16px;
  border-bottom: 1px solid var(--borda);
  background: var(--superficie-2);
  color: var(--apoio);
  font-size: 10px;
  font-weight: 800;
  letter-spacing: .09em;
  text-align: left;
  text-transform: uppercase;
  white-space: nowrap;
}
th:nth-child(1) { width: 24%; }
th:nth-child(2) { width: 10%; }
th:nth-child(3) { width: 8%; }
th:nth-child(4) { width: 6%; }
td { padding: 12px 16px; border-bottom: 1px solid var(--grade); vertical-align: middle; }
tbody tr:last-child td { border-bottom: 0; }
tbody tr:hover td { background: #fafbfc; }
.num { text-align: right; font-variant-numeric: tabular-nums; }
td.num { color: var(--texto-2); font-weight: 700; }
a.chip-arquivo { font-weight: 700; text-decoration: none; }
a.chip-arquivo:hover { border-color: var(--marca-clara); color: var(--marca); }
a:focus-visible, summary:focus-visible { outline: 2px solid var(--selecao); outline-offset: 2px; }
.achado { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
.achado-texto { margin-right: 2px; color: var(--texto-2); }
.achado-erro { color: var(--texto); font-weight: 700; }
.achado-ok { color: var(--apoio); }

/* Cartões por consulta */
.detalhes { display: grid; gap: 14px; }
.consulta {
  position: relative;
  padding: 16px 20px 18px;
  border-top: 4px solid var(--borda);
  border-radius: var(--raio);
  background: var(--cartao);
  box-shadow: var(--sombra);
  scroll-margin-top: 16px;
}
.consulta:target { background: var(--selecao-fundo); box-shadow: 0 0 0 2px var(--selecao), var(--sombra); }
.consulta-ok { border-top-color: var(--ok); }
.consulta-aviso { border-top-color: var(--aviso); }
.consulta-erro { border-top-color: var(--erro); }
.consulta-cabeca { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 12px; padding-right: 170px; }
.consulta-cabeca h3 { font-size: 14px; line-height: 1.4; }
.consulta-cabeca h3 code {
  padding: 0;
  border: 0;
  background: none;
  font-size: 14px;
  font-weight: 700;
  white-space: normal;
  overflow-wrap: anywhere;
}
.detalhes-ok .consulta-cabeca { padding-right: 0; }
.detalhes-ok .consulta-cabeca h3 { margin-right: 140px; }
.detalhes-ok .consulta-desc { flex-basis: 100%; }
.consulta-desc { color: var(--apoio); font-size: 12px; }
.consulta-corpo {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px 28px;
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid var(--grade);
}
.consulta-erro .consulta-corpo { grid-template-columns: minmax(0, 1fr) minmax(0, 2fr); }
.consulta-ok .consulta-corpo { grid-template-columns: minmax(0, 1fr); }
.detalhes-ok { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
.detalhes-ok > :last-child:nth-child(odd) { grid-column: 1 / -1; }
.bloco > .rotulo, .bloco-cabeca { margin-bottom: 8px; }
.bloco-cabeca { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.bloco-nota { color: var(--apoio); font-size: 12px; }
.mensagem-erro + .bloco-nota { margin-top: 8px; }
.mensagem-erro {
  padding: 9px 12px;
  border-left: 4px solid var(--erro);
  border-radius: 8px;
  background: var(--erro-fundo);
  color: var(--erro-texto);
  font-family: var(--mono);
  font-size: 14px;
  font-weight: 700;
  overflow-wrap: anywhere;
}
.sem-linha {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
  border-radius: 8px;
  background: var(--aviso-fundo);
  color: var(--aviso-texto);
  font-size: 12px;
  font-weight: 800;
}
.sem-linha .icone { width: 14px; height: 14px; stroke-width: 2.4; }
.sem-linha code { border-color: #efd88f; background: var(--cartao); color: var(--aviso-texto); }
.dif { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
.dif + .dif { margin-top: 8px; }
.dif-rotulo { margin-right: 2px; color: var(--texto-2); font-size: 12px; }
.confere { display: inline-flex; align-items: center; gap: 6px; color: var(--ok-texto); font-size: 12px; font-weight: 800; }
.confere .icone { width: 16px; height: 16px; }
details.sql summary {
  position: absolute;
  top: 18px;
  right: 20px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--marca);
  font-size: 12px;
  font-weight: 800;
  cursor: pointer;
  list-style: none;
}
details.sql summary::-webkit-details-marker { display: none; }
details.sql summary .icone { width: 14px; height: 14px; stroke-width: 2.4; }
details.sql summary:hover { color: var(--marca-clara); }
details.sql .fechar, details.sql[open] .abrir { display: none; }
details.sql[open] .fechar { display: inline; }
details.sql[open] summary .icone { transform: rotate(90deg); }
details.sql pre {
  margin-top: 14px;
  padding: 12px 14px;
  border: 1px solid var(--borda);
  border-radius: 8px;
  background: var(--superficie-2);
  font-size: 12px;
  line-height: 1.6;
  overflow-x: auto;
}
details.sql pre code { padding: 0; border: 0; background: none; }

/* Como ler: as duas colunas dividem as mesmas linhas (o fluxo desce por coluna) */
.legenda {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  grid-template-rows: repeat(4, auto);
  grid-auto-flow: column;
  gap: 10px 40px;
  padding: 18px 20px;
  background: linear-gradient(var(--grade), var(--grade)) 50% 0 / 1px 100% no-repeat, var(--cartao);
}
.legenda > .rotulo { margin-bottom: 2px; }
.legenda-item { display: flex; align-items: center; gap: 16px; min-height: 26px; color: var(--texto-2); }
.legenda-marca { display: flex; flex: none; width: 74px; }
.legenda-chips .legenda-marca { width: 132px; }
.nota {
  display: flex;
  gap: 12px;
  margin-top: 14px;
  padding: 14px 18px;
  border-left: 4px solid var(--marca-clara);
  border-radius: var(--raio);
  background: var(--cartao);
  box-shadow: var(--sombra);
  color: var(--texto-2);
}
.nota > .icone { width: 18px; height: 18px; margin-top: 2px; color: var(--marca); }
.nota strong { color: var(--texto); font-weight: 800; }

/* Rodapé */
.rodape {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px 16px;
  margin-top: 48px;
  padding-top: 16px;
  border-top: 1px solid var(--borda);
  color: var(--apoio);
  font-size: 12px;
}
.rodape strong { color: var(--texto); font-weight: 800; }
.rodape-marca { display: inline-flex; align-items: center; gap: 8px; }
.marca {
  display: grid;
  place-items: center;
  width: 22px;
  height: 22px;
  border-radius: 6px;
  background: var(--degrade);
  color: #fff;
}
.marca .icone { width: 14px; height: 14px; }

@media (max-width: 960px) {
  .tiles { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .campos { grid-template-columns: minmax(0, 1fr); }
  .consulta-corpo, .consulta-erro .consulta-corpo, .detalhes-ok { grid-template-columns: minmax(0, 1fr); }
  .legenda { grid-template-columns: minmax(0, 1fr); grid-template-rows: none; grid-auto-flow: row; background: var(--cartao); }
  .legenda > .rotulo:not(:first-child) { margin-top: 10px; }
}
@media (max-width: 640px) {
  .pagina { padding: 14px 16px 24px; }
  .topo { flex-wrap: wrap; }
  .faixa { padding: 20px 18px 16px; }
  .faixa h1 { font-size: 18px; }
  .tiles { grid-template-columns: minmax(0, 1fr); }
  .secao-dica { display: none; }
  thead { display: none; }
  table, tbody, tr, td { display: block; width: 100%; }
  tr { padding: 12px 16px; border-bottom: 1px solid var(--grade); }
  tbody tr:last-child { border-bottom: 0; }
  td { padding: 4px 0; border: 0; }
  td.num { display: inline-block; width: auto; margin-right: 14px; }
  td.num::before { content: attr(data-rotulo) " "; color: var(--apoio); font-weight: 400; }
  .chip { white-space: normal; overflow-wrap: anywhere; }
  .consulta-cabeca { padding-right: 0; }
  .detalhes-ok .consulta-cabeca h3 { margin-right: 0; }
  details.sql summary { position: static; margin-top: 14px; }
  .legenda-item { align-items: flex-start; }
}
"""

NOTA = (
    "<strong>Nenhuma consulta é executada.</strong> Cada arquivo só é preparado com "
    "<code>EXPLAIN</code>, com o banco aberto só para leitura (<code>mode=ro</code>). Na preparação, "
    "o <code>set_authorizer</code> do <code>sqlite3</code> avisa cada tabela e coluna que a consulta lê, "
    "com apelidos, CTEs e <code>SELECT *</code> já resolvidos pelo próprio SQLite; essa lista é comparada "
    "com a linha <code>-- usa:</code> do topo do arquivo. Só o erro, que quebraria o quadro na tela, faz a "
    "conferência terminar com código 1; o aviso não derruba o agendador."
)

DICA_DA_TABELA = "Declara: itens na linha <code>-- usa:</code> · Lê: itens lidos de fato · o arquivo leva ao detalhe"

LEGENDA_STATUS = (
    ("ok", "Prepara no banco e lê exatamente o que declara na linha <code>-- usa:</code>."),
    ("aviso", "Prepara, mas a linha <code>-- usa:</code> falta ou não bate com o que ela lê."),
    ("erro", "Não prepara: tabela ou coluna que não existe, ou SQL inválido."),
)

LEGENDA_CHIPS = (
    ("", "Declarada e lida: confere."),
    ("sobra", "Declarada e não lida: sobra na linha <code>-- usa:</code>."),
    ("falta", "Lida e não declarada: falta na linha <code>-- usa:</code>."),
)


def gravar(conferencias: list[Conferencia], banco: str, pasta: str, destino: Path,
           agora: datetime | None = None) -> tuple[Path, Path]:
    """Grava relatorio.md e relatorio.html em `destino` e devolve os dois caminhos."""
    agora = agora or datetime.now()
    destino.mkdir(parents=True, exist_ok=True)
    md, pagina = destino / "relatorio.md", destino / "relatorio.html"
    md.write_text(para_markdown(conferencias, banco, pasta, agora), encoding="utf-8")
    pagina.write_text(para_html(conferencias, banco, pasta, agora), encoding="utf-8")
    return md, pagina


def para_markdown(conferencias: list[Conferencia], banco: str, pasta: str, agora: datetime) -> str:
    """Tabela com uma linha por consulta e, depois, o declarado e o lido de cada uma."""
    total = Counter(c.status for c in conferencias)
    linhas = [
        "# Conferência das consultas",
        "",
        f"- Banco: `{banco}`",
        f"- Consultas: `{pasta}` ({len(conferencias)} arquivos)",
        f"- Gerado em: {agora:%d/%m/%Y %H:%M}",
        f"- Resultado: {total['erro']} com erro, {total['aviso']} com aviso, {total['ok']} ok",
        "",
        "| Consulta | Status | Detalhe |",
        "| --- | --- | --- |",
    ]
    linhas += [f"| `{c.arquivo}` | {SIMBOLO[c.status]} {c.status} | {_md(c.resumo)} |" for c in conferencias]
    linhas += ["", "## Por consulta"]
    for c in conferencias:
        declara = "sem a linha `-- usa:`" if c.declarado is None else _lista_md(c.declarado)
        le = "não dá para saber (a consulta não prepara)" if c.erro else _lista_md(c.usado)
        linhas += ["", f"### `{c.arquivo}` ({SIMBOLO[c.status]} {c.status})", "",
                   f"- Declara: {declara}", f"- Lê de fato: {le}"]
        if c.erro:
            linhas.append(f"- Erro: {_md(c.erro)}")
    return "\n".join(linhas) + "\n"


def para_html(conferencias: list[Conferencia], banco: str, pasta: str, agora: datetime) -> str:
    """Página única: faixa, tiles, tabela das consultas, um cartão por consulta e a legenda."""
    total = Counter(c.status for c in conferencias)
    n = len(conferencias)
    ancoras = [_ancora(i, c.arquivo) for i, c in enumerate(conferencias, 1)]
    linhas = "\n".join(_linha(c, a) for c, a in zip(conferencias, ancoras))
    # Erro e aviso em cartões de largura inteira; as OK, mais curtas, em duas colunas no fim.
    cartoes = "\n".join(_cartao_consulta(c, a) for c, a in zip(conferencias, ancoras) if c.status != "ok")
    certas = [_cartao_consulta(c, a) for c, a in zip(conferencias, ancoras) if c.status == "ok"]
    if certas:
        cartoes += '\n    <div class="detalhes-ok">\n' + "\n".join(certas) + "\n    </div>"
    dia, hora = f"{agora:%d/%m/%Y}", f"{agora:%H:%M}"
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Conferência SQL × banco</title>
<style>
{_fonte_css(FONTE)}{CSS}</style>
</head>
<body>
<div class="pagina">

<div class="topo">
  <p><strong>Fintech Exemplo</strong> · Qualidade do dado · consultas da dashboard × banco</p>
  <p class="carimbo">Gerado em <strong>{dia} {hora}</strong></p>
</div>

<header class="faixa">
  <h1>{_icone("banco")}Conferência SQL × banco</h1>
  <dl class="campos">
    <div><dt>Banco</dt><dd><code>{escape(banco)}</code></dd></div>
    <div><dt>Pasta das consultas</dt><dd><code>{escape(pasta)}</code></dd></div>
    <div><dt>Método</dt><dd><code>EXPLAIN</code> + <code>set_authorizer</code>, sem executar</dd></div>
  </dl>
  <p class="faixa-rodape"><strong>{_quantas(n)}</strong> {"conferida" if n == 1 else "conferidas"} em
    <strong>{dia}</strong> às <strong>{hora}</strong> · banco aberto só para leitura · erros primeiro</p>
</header>

<section class="tiles" aria-label="Resumo">
{_tiles(total, n)}
</section>

<section class="secao" aria-labelledby="secao-1">
  {_cabeca_secao(1, "Resumo por consulta", DICA_DA_TABELA)}
  <div class="cartao tabela-cartao">
    <table>
      <thead>
        <tr>
          <th scope="col">Consulta</th><th scope="col">Status</th>
          <th scope="col" class="num" title="itens na linha -- usa:">Declara</th>
          <th scope="col" class="num" title="colunas (ou tabelas) lidas de fato">Lê</th>
          <th scope="col">O que a conferência achou</th>
        </tr>
      </thead>
      <tbody>
{linhas}
      </tbody>
    </table>
  </div>
</section>

<section class="secao" aria-labelledby="secao-2">
  {_cabeca_secao(2, "Detalhes", "o que cada arquivo declara × o que ele lê de fato")}
  <div class="detalhes">
{cartoes}
  </div>
</section>

<section class="secao" aria-labelledby="secao-3">
  {_cabeca_secao(3, "Como ler", "")}
  <div class="cartao legenda">
    <p class="rotulo">Status</p>{_legenda_status()}
    <p class="rotulo">Colunas nos cartões</p>{_legenda_chips()}
  </div>
  <aside class="nota">{_icone("info")}<p>{NOTA}</p></aside>
</section>

<footer class="rodape">
  <p class="rodape-marca"><span class="marca">{_icone("banco")}</span>
    <span><strong>Fintech Exemplo</strong> · dados fictícios, gerados por script</span></p>
  <p>Relatório gerado por <code>conferir.py</code> em {dia} às {hora} · HTML autocontido, sem JavaScript</p>
</footer>

</div>
</body>
</html>
"""


@lru_cache(maxsize=4)
def _fonte_css(caminho: Path) -> str:
    """@font-face da Nunito (variável, pesos 400 a 800) em base64; vazio se o arquivo faltar."""
    try:
        dados = caminho.read_bytes()
    except OSError:
        return ""  # sem a fonte, a página cai em system-ui / Segoe UI
    return ('@font-face {\n  font-family: "Nunito";\n  font-style: normal;\n  font-weight: 400 800;\n'
            '  font-display: swap;\n'
            f'  src: url(data:font/woff2;base64,{base64.b64encode(dados).decode("ascii")}) format("woff2");\n}}\n')


def _tiles(total: Counter, n: int) -> str:
    partes = "".join(f'<span class="seg-{s}" style="flex-grow: {total[s]}"></span>' for s in STATUS if total[s])
    descricao = ", ".join(f"{total[s]} {NOME_NO_TILE[s].lower()}" for s in STATUS)
    tiles = [_tile("total", "consultas", "Consultas conferidas", n, n,
                   f'<div class="barra-seg" role="img" aria-label="{descricao}">{partes}</div>')]
    for s in STATUS:
        medidor = (f'<div class="medidor medidor-{s}" role="img" aria-label="{_percentual(total[s], n)} das consultas">'
                   f'<span style="width: {_largura(total[s], n)}"></span></div>')
        tiles.append(_tile(s, s, NOME_NO_TILE[s], total[s], n, medidor))
    return "\n".join(tiles)


def _tile(tipo: str, icone: str, rotulo: str, parte: int, todo: int, grafico: str) -> str:
    """Quadrado do ícone, rótulo, o número, a barra e a linha "44,4% · 4 de 9"."""
    return (f'<article class="tile tile-{tipo}"><span class="tile-icone">{_icone(icone)}</span>'
            f'<div class="tile-corpo"><p class="rotulo">{rotulo}</p><p class="tile-numero">{_inteiro(parte)}</p>'
            f'{grafico}<p class="tile-nota"><strong>{_percentual(parte, todo)}</strong> · '
            f'{_inteiro(parte)} de {_inteiro(todo)}</p></div></article>')


def _cabeca_secao(numero: int, titulo: str, dica: str) -> str:
    dica_html = f'<p class="secao-dica">{dica}</p>' if dica else ""
    return (f'<div class="secao-cabeca"><span class="secao-num" aria-hidden="true">{numero}</span>'
            f'<h2 id="secao-{numero}">{titulo}</h2>{dica_html}</div>')


def _linha(c: Conferencia, ancora: str) -> str:
    declara = "—" if c.declarado is None else _inteiro(len(c.declarado))
    le = "—" if c.erro else _inteiro(len(c.usado))
    return (
        "        <tr>"
        f'<td><a class="chip chip-arquivo" href="#{ancora}">{escape(c.arquivo)}</a></td>'
        f"<td>{_selo(c.status)}</td>"
        f'<td class="num" data-rotulo="Declara">{declara}</td>'
        f'<td class="num" data-rotulo="Lê">{le}</td>'
        f"<td>{_achado(c)}</td></tr>"
    )


def _achado(c: Conferencia) -> str:
    if c.erro:
        corpo = f'<span class="achado-erro">{escape(c.erro)}</span>'
    elif c.status == "ok":
        corpo = '<span class="achado-ok">Lê exatamente o que declara</span>'
    else:
        texto = "Sem a linha <code>-- usa:</code>" if c.declarado is None else "Não bate com o que a consulta lê"
        corpo = (f'<span class="achado-texto">{texto}</span>'
                 + _spans(c.declarado_nao_usado, "sobra") + _spans(c.usado_nao_declarado, "falta"))
    return f'<div class="achado">{corpo}</div>'


def _cartao_consulta(c: Conferencia, ancora: str) -> str:
    descricao = _descricao(c.sql)
    cabeca = (f'<header class="consulta-cabeca">{_selo(c.status)}<h3><code>{escape(c.arquivo)}</code></h3>'
              + (f'<p class="consulta-desc">{escape(descricao)}</p>' if descricao else "") + "</header>")
    if c.status == "ok":
        corpo = _corpo_ok(c)
    elif c.erro:
        corpo = _bloco("Declarado na linha <code>-- usa:</code>", _declarado(c)) + _bloco(
            "O SQLite recusou a consulta",
            f'<p class="mensagem-erro">{escape(c.erro)}</p>'
            '<p class="bloco-nota">Sem preparar a consulta, não dá para saber o que ela lê.</p>')
    else:
        corpo = (_bloco("Declarado na linha <code>-- usa:</code>", _declarado(c))
                 + _bloco("Lido de fato", _lidos(c)) + _bloco("Diferença", _diferenca(c)))
    return (f'    <article class="consulta consulta-{c.status}" id="{ancora}">{cabeca}'
            f'<div class="consulta-corpo">{corpo}</div>{_sql(c)}</article>')


def _corpo_ok(c: Conferencia) -> str:
    """Cartão curto: uma lista só quando o declarado e o lido são iguais (o caso comum)."""
    nenhuma = f'<span class="confere">{_icone("ok")}Nenhuma diferença</span>'
    if c.declarado == c.usado:
        lista = (_chips(c.usado, (), "") if c.usado else
                 '<p class="bloco-nota">Não lê nenhuma tabela, e a linha <code>-- usa:</code> está vazia.</p>')
        return _bloco("Declarado e lido de fato", lista, nenhuma)
    # Ex.: `-- usa: propostas, propostas.status` com só a coluna lida: confere, mas as listas diferem.
    return _bloco("Declarado e lido de fato",
                  f'<div class="dif"><span class="dif-rotulo">Declarado</span>{_spans(c.declarado or (), "")}</div>'
                  f'<div class="dif"><span class="dif-rotulo">Lido de fato</span>{_spans(c.usado, "")}</div>', nenhuma)


def _bloco(rotulo: str, conteudo: str, direita: str = "") -> str:
    cabeca = f'<p class="rotulo">{rotulo}</p>'
    if direita:
        cabeca = f'<div class="bloco-cabeca">{cabeca}{direita}</div>'
    return f'<div class="bloco">{cabeca}{conteudo}</div>'


def _declarado(c: Conferencia) -> str:
    if c.declarado is None:
        return f'<p class="sem-linha">{_icone("aviso")}Sem a linha <code>-- usa:</code> no topo do arquivo</p>'
    if not c.declarado:
        return '<p class="bloco-nota">A linha <code>-- usa:</code> está vazia.</p>'
    return _chips(c.declarado, c.declarado_nao_usado, "sobra")


def _lidos(c: Conferencia) -> str:
    if not c.usado:
        return '<p class="bloco-nota">Não lê nenhuma tabela.</p>'
    return _chips(c.usado, c.usado_nao_declarado, "falta")


def _diferenca(c: Conferencia) -> str:
    grupos = [(tipo, itens) for tipo, itens in (("sobra", c.declarado_nao_usado), ("falta", c.usado_nao_declarado))
              if itens]
    if not grupos:
        return '<p class="bloco-nota">Nada a comparar: a consulta não lê nenhuma tabela.</p>'
    return "".join(f'<div class="dif"><span class="dif-rotulo">{SENTIDO[tipo].capitalize()}</span>'
                   f"{_spans(itens, tipo)}</div>" for tipo, itens in grupos)


def _sql(c: Conferencia) -> str:
    return ('<details class="sql"><summary>'
            f'{_icone("seta")}<span class="abrir">Ver a consulta</span><span class="fechar">Esconder a consulta</span>'
            f"</summary><pre><code>{escape(c.sql.strip())}</code></pre></details>")


def _chips(itens: Iterable[str], destaque: Iterable[str], tipo: str) -> str:
    """Todos os itens em chips; os de `destaque` com a marca de sobra ou de falta."""
    destaque = set(destaque)
    return '<div class="chips">' + "".join(_chip(i, tipo if i in destaque else "") for i in sorted(itens)) + "</div>"


def _spans(itens: Iterable[str], tipo: str) -> str:
    return "".join(_chip(i, tipo) for i in sorted(itens))


def _chip(item: str, tipo: str = "") -> str:
    if not tipo:
        return f'<span class="chip">{escape(item)}</span>'
    return (f'<span class="chip chip-{tipo}" title="{SENTIDO[tipo]}">'
            f'<span class="sinal" aria-hidden="true">{SINAL[tipo]}</span>'
            f'<span class="vh">{SENTIDO[tipo]}: </span>{escape(item)}</span>')


def _legenda_status() -> str:
    return "".join(f'<div class="legenda-item"><span class="legenda-marca">{_selo(s)}</span><span>{texto}</span></div>'
                   for s, texto in LEGENDA_STATUS)


def _legenda_chips() -> str:
    return "".join(f'<div class="legenda-item legenda-chips"><span class="legenda-marca">{_chip("tabela.coluna", tipo)}'
                   f"</span><span>{texto}</span></div>" for tipo, texto in LEGENDA_CHIPS)


def _selo(status: str) -> str:
    return f'<span class="selo selo-{status}">{_icone(status)}{NOME[status]}</span>'


def _icone(nome: str) -> str:
    return f'<svg class="icone" viewBox="0 0 24 24" aria-hidden="true" focusable="false">{TRACOS[nome]}</svg>'


def _descricao(sql: str) -> str:
    """Primeira linha de comentário do topo que não é a `-- usa:` (diz que quadro a consulta alimenta)."""
    for linha in sql.splitlines():
        linha = linha.strip()
        if not linha:
            continue
        if not linha.startswith("--"):
            break
        texto = linha.lstrip("-").strip()
        if any(ch.isalnum() for ch in texto) and not COMECA_COM_USA.match(texto):
            return texto
    return ""


def _ancora(posicao: int, arquivo: str) -> str:
    return f"consulta-{posicao}-" + (re.sub(r"[^a-z0-9]+", "-", arquivo.lower()).strip("-") or "sql")


def _quantas(n: int) -> str:
    return f"{_inteiro(n)} consulta" + ("" if n == 1 else "s")


def _inteiro(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def _percentual(parte: int, todo: int) -> str:
    """44,4%; o 0% e o 100% saem sem casa decimal."""
    if not parte or not todo:
        return "0%"
    if parte == todo:
        return "100%"
    return f"{100 * parte / todo:.1f}".replace(".", ",") + "%"


def _largura(parte: int, todo: int) -> str:
    return f"{100 * parte / todo:.2f}%" if todo else "0%"


def _md(texto: str) -> str:
    return texto.replace("|", "\\|").replace("\n", " ")


def _lista_md(itens: Iterable[str]) -> str:
    return ", ".join(f"`{i}`" for i in sorted(itens)) or "nada"
