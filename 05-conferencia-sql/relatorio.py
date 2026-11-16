"""Relatório da conferência em Markdown e em HTML autocontido (sem CDN nem JavaScript)."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from datetime import datetime
from html import escape
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from conferir import Conferencia

SIMBOLO = {"ok": "✓", "aviso": "!", "erro": "✗"}

ICONE = {
    "ok": '<svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="6.6"/>'
          '<path d="M5 8.2l2 2 4-4.3"/></svg>',
    "aviso": '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 1.9l6.5 11.6h-13z"/>'
             '<path d="M8 6.3v3.2M8 11.6v.1"/></svg>',
    "erro": '<svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="6.6"/>'
            '<path d="M5.8 5.8l4.4 4.4M10.2 5.8l-4.4 4.4"/></svg>',
}

CSS = """
:root {
  --marinho: #1c2d42;
  --areia: #d6b78a;
  --bronze: #8a6230;
  --creme: #f7f0e5;
  --tinta: #18212c;
  --cinza: #677282;
  --fundo: #ffffff;
  --linha: #ebe2d3;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--fundo);
  color: var(--tinta);
  font: 15px/1.55 "Inter", "Segoe UI", Arial, sans-serif;
}
main { max-width: 1120px; margin: 0 auto; padding: 44px 32px 48px; }
code, pre { font-family: Consolas, "Courier New", monospace; }
.sobrancelha {
  margin: 0;
  color: var(--bronze);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: .1em;
  text-transform: uppercase;
}
h1 { margin: 6px 0; color: var(--marinho); font-size: 30px; line-height: 1.2; }
.meta { margin: 0; color: var(--cinza); font-size: 14px; }
.meta code { color: var(--tinta); font-size: 13.5px; }
.resumo { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin: 28px 0 32px; }
.cartao { padding: 16px 18px; border-radius: 12px; background: var(--creme); }
.numero { display: block; margin-bottom: 8px; color: var(--marinho); font-size: 32px; font-weight: 700; line-height: 1.1; }
.cartao-rotulo { font-size: 13px; font-weight: 600; }
table { width: 100%; border-collapse: collapse; table-layout: fixed; }
th {
  padding: 0 14px 10px;
  border-bottom: 2px solid var(--areia);
  color: var(--cinza);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: .08em;
  text-align: left;
  text-transform: uppercase;
}
th:nth-child(1) { width: 27%; }
th:nth-child(2) { width: 12%; }
td { padding: 14px; border-bottom: 1px solid var(--linha); vertical-align: top; }
td.arquivo code { color: var(--marinho); font-size: 13.5px; font-weight: 700; overflow-wrap: anywhere; }
.selo {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 2px 11px 2px 8px;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 700;
  white-space: nowrap;
}
.selo svg {
  width: 15px;
  height: 15px;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.7;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.selo-ok { background: var(--creme); color: var(--marinho); box-shadow: inset 0 0 0 1px var(--areia); }
.selo-aviso { background: var(--areia); color: var(--tinta); }
.selo-erro { background: var(--marinho); color: var(--fundo); }
.achado { margin: 0; }
.achado-erro { color: var(--marinho); font-weight: 700; }
.grupo { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin-top: 6px; }
.grupo:first-child { margin-top: 0; }
.grupo-rotulo { margin-right: 2px; color: var(--cinza); font-size: 12.5px; }
.chip {
  padding: 1px 8px;
  border: 1px solid transparent;
  border-radius: 6px;
  background: var(--creme);
  font-family: Consolas, "Courier New", monospace;
  font-size: 12.5px;
}
.chip-sobra { border: 1px dashed var(--cinza); background: var(--fundo); color: var(--cinza); text-decoration: line-through; }
.chip-falta { border-color: var(--bronze); background: var(--fundo); color: var(--bronze); font-weight: 700; }
details { margin-top: 6px; }
summary { color: var(--bronze); font-size: 13px; cursor: pointer; }
pre {
  margin: 8px 0 0;
  padding: 12px 14px;
  overflow-x: auto;
  border-radius: 8px;
  background: var(--creme);
  font-size: 12.5px;
  line-height: 1.5;
}
.legenda { margin-top: 28px; padding: 18px 20px; border-radius: 12px; background: var(--creme); font-size: 14px; }
.legenda dl { display: grid; grid-template-columns: max-content 1fr; align-items: center; gap: 8px 12px; margin: 0; }
.legenda dt, .legenda dd { margin: 0; }
.legenda .nota { margin: 14px 0 0; }
@media (max-width: 760px) {
  main { padding: 28px 16px 40px; }
  .resumo { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  thead { display: none; }
  table, tbody, tr, td { display: block; width: 100%; }
  tr { padding: 12px 0; border-bottom: 1px solid var(--linha); }
  td { padding: 4px 0; border: 0; }
}
"""


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
    """Página única: resumo em cartões, tabela das consultas e legenda dos status."""
    total = Counter(c.status for c in conferencias)
    cartoes = _cartao(len(conferencias), '<span class="cartao-rotulo">consultas conferidas</span>')
    cartoes += "".join(_cartao(total[s], _selo(s)) for s in ("ok", "aviso", "erro"))
    linhas = "\n".join(_linha(c) for c in conferencias)
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Conferência das consultas</title>
<style>{CSS}</style>
</head>
<body>
<main>
  <header>
    <p class="sobrancelha">Qualidade do dado</p>
    <h1>Conferência das consultas</h1>
    <p class="meta">Banco <code>{escape(banco)}</code> · {len(conferencias)} consultas em <code>{escape(pasta)}</code> · gerado em {agora:%d/%m/%Y} às {agora:%H:%M}</p>
  </header>
  <section class="resumo" aria-label="Resumo">{cartoes}</section>
  <table>
    <thead>
      <tr><th scope="col">Consulta</th><th scope="col">Status</th><th scope="col">O que a conferência achou</th></tr>
    </thead>
    <tbody>
{linhas}
    </tbody>
  </table>
  <footer class="legenda">
    <dl>
      <dt>{_selo('ok')}</dt><dd>prepara no banco e lê exatamente o que declara na linha <code>-- usa:</code>.</dd>
      <dt>{_selo('aviso')}</dt><dd>prepara, mas a declaração falta ou não bate com o que a consulta lê.</dd>
      <dt>{_selo('erro')}</dt><dd>não prepara: tabela ou coluna que não existe, ou SQL inválido. O quadro quebraria na tela.</dd>
    </dl>
    <p class="nota">Nenhuma consulta é executada: cada uma só é preparada com <code>EXPLAIN</code>, com o banco aberto só para leitura.</p>
  </footer>
</main>
</body>
</html>
"""


def _linha(c: Conferencia) -> str:
    return (
        "      <tr>\n"
        f'        <td class="arquivo"><code>{escape(c.arquivo)}</code></td>\n'
        f"        <td>{_selo(c.status)}</td>\n"
        f"        <td>{_achado(c)}<details><summary>ver a consulta</summary>"
        f"<pre><code>{escape(c.sql.strip())}</code></pre></details></td>\n"
        "      </tr>"
    )


def _achado(c: Conferencia) -> str:
    if c.erro:
        return f'<p class="achado achado-erro">{escape(c.erro)}</p>'
    if c.status == "ok":
        return f'<div class="grupo"><span>Lê exatamente o que declara:</span>{_chips(c.usado, "chip")}</div>'
    texto = ("Sem a linha <code>-- usa:</code> no topo." if c.declarado is None
             else "A declaração não bate com o que a consulta lê.")
    return (f'<p class="achado">{texto}</p>'
            + _grupo("declarado e não usado", c.declarado_nao_usado, "chip chip-sobra")
            + _grupo("usado e não declarado", c.usado_nao_declarado, "chip chip-falta"))


def _grupo(rotulo: str, itens: list[str], classe: str) -> str:
    if not itens:
        return ""
    return f'<div class="grupo"><span class="grupo-rotulo">{rotulo}</span>{_chips(itens, classe)}</div>'


def _chips(itens: Iterable[str], classe: str) -> str:
    return "".join(f'<span class="{classe}">{escape(i)}</span>' for i in sorted(itens))


def _selo(status: str) -> str:
    return f'<span class="selo selo-{status}">{ICONE[status]}{status}</span>'


def _cartao(numero: int, rotulo: str) -> str:
    return f'<div class="cartao"><span class="numero">{numero}</span>{rotulo}</div>'


def _md(texto: str) -> str:
    return texto.replace("|", "\\|").replace("\n", " ")


def _lista_md(itens: Iterable[str]) -> str:
    return ", ".join(f"`{i}`" for i in sorted(itens)) or "nada"
