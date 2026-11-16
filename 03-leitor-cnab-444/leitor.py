"""Lê, valida e converte arquivos CNAB 444 de remessa e de retorno.

Uso:
    python leitor.py ARQUIVO [--csv SAIDA.csv]

Com o arquivo certo, mostra o resumo por ocorrência e, se pedido, grava o CSV.
Com erro, lista cada um com linha e posição e sai com código 1, sem gravar o
CSV. Argumentos errados ou arquivo que não abre: código 2.
"""

import csv
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path

from layout import (DETALHE, HEADER, OCORRENCIAS, REGISTROS, SEQUENCIAL, TAMANHO_LINHA,
                    TIPO_REGISTRO, TRAILER, Campo, Registro, Tipo, posicoes)

USO = "uso: python leitor.py ARQUIVO [--csv SAIDA.csv]"

COLUNAS_CSV = [
    "linha", "seu_numero", "nosso_numero", "numero_documento", "codigo_ocorrencia",
    "descricao_ocorrencia", "data_ocorrencia", "data_emissao", "data_vencimento",
    "valor_titulo", "valor_presente", "valor_pago", "tipo_inscricao_sacado",
    "numero_inscricao_sacado", "nome_sacado",
]


@dataclass(frozen=True)
class Erro:
    linha: int | None
    mensagem: str
    campo: Campo | None = None

    def __str__(self) -> str:
        onde = []
        if self.linha is not None:
            onde.append(f"linha {self.linha}")
        if self.campo is not None:
            onde.append(f"{posicoes(self.campo.inicio, self.campo.fim)} ({self.campo.nome})")
        return f"{', '.join(onde)}: {self.mensagem}" if onde else self.mensagem


@dataclass
class Leitura:
    """Registros convertidos e erros; linha com erro fica fora de header, trailer e detalhes."""

    header: dict | None = None
    trailer: dict | None = None
    detalhes: list[dict] = field(default_factory=list)
    erros: list[Erro] = field(default_factory=list)
    total_linhas: int = 0


@dataclass
class ItemResumo:
    codigo: str
    descricao: str
    quantidade: int = 0
    valor_titulos: Decimal = Decimal("0.00")
    valor_pago: Decimal = Decimal("0.00")


def converter(campo: Campo, texto: str):
    """Data vira date, valor vira Decimal e número continua texto (guarda os zeros à esquerda).

    ValueError quando o texto não serve para o tipo do campo.
    """
    if campo.tipo is Tipo.ALFANUMERICO:
        return texto.rstrip()
    if not (texto.isascii() and texto.isdigit()):
        raise ValueError(f"esperava só dígitos e veio {texto!r}")
    if campo.tipo is Tipo.VALOR:
        return Decimal(texto).scaleb(-2)
    if campo.tipo is Tipo.DATA:
        try:
            return date(2000 + int(texto[4:]), int(texto[2:4]), int(texto[:2]))
        except ValueError:
            raise ValueError(f"data inválida {texto!r} (formato DDMMAA)") from None
    return texto


def _problema_no_tipo(tipo: str, numero: int, ultima: int) -> str | None:
    """Header só na primeira linha, trailer só na última e nenhum tipo desconhecido."""
    if numero == 1 and tipo != HEADER.tipo:
        return "o arquivo deve começar pelo header (tipo 0)"
    if numero == ultima and tipo != TRAILER.tipo:
        return "o arquivo deve terminar pelo trailer (tipo 9)"
    if tipo == HEADER.tipo and numero != 1:
        return "header fora da primeira linha"
    if tipo == TRAILER.tipo and numero != ultima:
        return "trailer antes do fim do arquivo"
    if tipo not in REGISTROS:
        return f"tipo de registro {tipo!r} desconhecido (esperado 0, 1 ou 9)"
    return None


def _ler_linha(linha: str, numero: int, ultima: int) -> tuple[Registro | None, dict, list[Erro]]:
    """Registro, valores convertidos e erros de uma linha; sequência e totais vêm depois."""
    if not linha:
        return None, {}, [Erro(numero, "linha vazia")]
    registro = REGISTROS.get(linha[0])
    erros = []
    problema = _problema_no_tipo(linha[0], numero, ultima)
    if problema:
        erros.append(Erro(numero, problema, TIPO_REGISTRO))
    if len(linha) != TAMANHO_LINHA:
        mensagem = f"a linha tem {len(linha)} caracteres; o esperado é {TAMANHO_LINHA}"
        erros.append(Erro(numero, mensagem))
        return registro, {}, erros
    if registro is None:
        return None, {}, erros

    valores = {}
    for campo in registro.campos:
        if campo.tipo is Tipo.BRANCOS:
            continue
        try:
            valores[campo.nome] = converter(campo, campo.recortar(linha))
        except ValueError as erro:
            erros.append(Erro(numero, str(erro), campo))

    codigo = valores.get("codigo_ocorrencia")
    if registro is DETALHE and codigo is not None:
        if codigo in OCORRENCIAS:
            valores["descricao_ocorrencia"] = OCORRENCIAS[codigo]
        else:
            erros.append(Erro(numero, f"código {codigo} fora da tabela de ocorrências",
                              DETALHE.campo("codigo_ocorrencia")))
    return registro, valores, erros


def ler_linhas(linhas: list[str]) -> Leitura:
    """Valida e converte as linhas (já sem a quebra) de um arquivo CNAB 444."""
    leitura = Leitura(total_linhas=len(linhas))
    if not linhas:
        leitura.erros.append(Erro(None, "arquivo vazio: faltam o header e o trailer"))
        return leitura

    ultima = len(linhas)
    anterior = 0
    detalhes_no_arquivo, soma, sem_valor = 0, Decimal("0.00"), []
    trailer = {}
    for numero, linha in enumerate(linhas, start=1):
        registro, valores, erros = _ler_linha(linha, numero, ultima)

        # Compara com o sequencial anterior, e não com o número da linha:
        # um pulo vira um erro só, em vez de um erro em cada linha seguinte.
        esperado = anterior + 1
        sequencial = valores.get("sequencial_registro")
        if sequencial is not None and int(sequencial) != esperado:
            mensagem = f"veio {sequencial}; o esperado era {esperado:06d}"
            erros.append(Erro(numero, mensagem, SEQUENCIAL))
        anterior = int(sequencial) if sequencial is not None else esperado

        if registro is DETALHE:
            detalhes_no_arquivo += 1
            if "valor_titulo" in valores:
                soma += valores["valor_titulo"]
            else:
                sem_valor.append(numero)
            if not erros:
                leitura.detalhes.append({"linha": numero, **valores})
        elif registro is HEADER and numero == 1 and not erros:
            leitura.header = valores
        elif registro is TRAILER and numero == ultima:
            trailer = valores
            leitura.trailer = valores if not erros else None
        leitura.erros += erros

    if trailer:
        leitura.erros += _conferir_trailer(trailer, ultima, detalhes_no_arquivo, soma, sem_valor)
    return leitura


def _conferir_trailer(trailer: dict, numero: int, quantidade: int, soma: Decimal,
                      sem_valor: list[int]) -> list[Erro]:
    """Quantidade e valor total do trailer contra os detalhes do arquivo."""
    erros = []
    informada = trailer.get("quantidade_detalhes")
    if informada is not None and int(informada) != quantidade:
        mensagem = f"o trailer informa {int(informada)} detalhes, mas o arquivo tem {quantidade}"
        erros.append(Erro(numero, mensagem, TRAILER.campo("quantidade_detalhes")))

    total = trailer.get("valor_total")
    mensagem = None
    if total is not None and sem_valor:
        de = "da linha" if len(sem_valor) == 1 else "das linhas"
        mensagem = f"total não conferido: sem o valor_titulo {de} {', '.join(map(str, sem_valor))}"
    elif total is not None and total != soma:
        mensagem = f"o trailer informa {reais(total)}, mas os detalhes somam {reais(soma)}"
    if mensagem:
        erros.append(Erro(numero, mensagem, TRAILER.campo("valor_total")))
    return erros


def ler_arquivo(caminho) -> Leitura:
    """Lê em latin-1 (um byte, uma posição) e aceita quebra de linha CRLF ou LF."""
    linhas = Path(caminho).read_bytes().decode("latin-1").split("\n")
    if linhas[-1] == "":
        linhas.pop()
    return ler_linhas([linha.removesuffix("\r") for linha in linhas])


def reais(valor: Decimal) -> str:
    """Valor no formato brasileiro: R$ 1.234,56."""
    return "R$ " + f"{valor:,.2f}".translate(str.maketrans(",.", ".,"))


def resumir(detalhes: Iterable[dict]) -> list[ItemResumo]:
    """Quantidade e valores por código de ocorrência, em ordem de código."""
    itens: dict[str, ItemResumo] = {}
    for detalhe in detalhes:
        codigo = detalhe["codigo_ocorrencia"]
        item = itens.setdefault(codigo, ItemResumo(codigo, detalhe["descricao_ocorrencia"]))
        item.quantidade += 1
        item.valor_titulos += detalhe["valor_titulo"]
        item.valor_pago += detalhe["valor_pago"]
    return [itens[codigo] for codigo in sorted(itens)]


def _celula(valor):
    if isinstance(valor, Decimal):
        return f"{valor:.2f}".replace(".", ",")
    if isinstance(valor, date):
        return valor.isoformat()
    return valor


def exportar_csv(detalhes: Iterable[dict], caminho) -> None:
    """CSV para o Excel brasileiro: ';' entre colunas, vírgula decimal e BOM do UTF-8."""
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", encoding="utf-8-sig", newline="") as arquivo:
        escritor = csv.writer(arquivo, delimiter=";")
        escritor.writerow(COLUNAS_CSV)
        for detalhe in detalhes:
            escritor.writerow([_celula(detalhe[coluna]) for coluna in COLUNAS_CSV])


def _tabela(resumo: list[ItemResumo]) -> list[str]:
    modelo = "{:<31}{:>6}{:>20}{:>16}"
    total = ItemResumo("", "Total")
    linhas = [modelo.format("Ocorrência", "Qtde", "Valor dos títulos", "Valor pago")]
    for item in resumo:
        linhas.append(modelo.format(f"{item.codigo} {item.descricao}", item.quantidade,
                                    reais(item.valor_titulos), reais(item.valor_pago)))
        total.quantidade += item.quantidade
        total.valor_titulos += item.valor_titulos
        total.valor_pago += item.valor_pago
    linhas.append(modelo.format(total.descricao, total.quantidade,
                                reais(total.valor_titulos), reais(total.valor_pago)))
    return linhas


def relatorio(caminho, leitura: Leitura) -> str:
    """O texto da linha de comando: os erros ou, sem erro, o resumo por ocorrência."""
    texto = [str(caminho)]
    if leitura.header:
        h = leitura.header
        texto.append(f"{h['literal_arquivo']} nº {int(h['sequencial_arquivo'])} de "
                     f"{h['data_gravacao']:%d/%m/%Y}, originador {h['nome_originador']}")
    if leitura.erros:
        quantos = len(leitura.erros)
        texto.append(f"{quantos} erro{'s' if quantos > 1 else ''}:")
        texto += [f"  {erro}" for erro in leitura.erros]
    else:
        texto.append(f"{leitura.total_linhas} linhas, {len(leitura.detalhes)} detalhes, "
                     "nenhum erro")
        texto += ["", *_tabela(resumir(leitura.detalhes))]
    return "\n".join(texto)


def ler_argumentos(argv: list[str]) -> tuple[str, str | None]:
    """(arquivo, CSV de saída). Lidos à mão para as mensagens saírem em português."""
    arquivo = destino = None
    argumentos = iter(argv)
    for argumento in argumentos:
        if argumento == "--csv":
            destino = next(argumentos, None)
            if destino is None:
                raise ValueError("faltou o caminho do CSV depois de --csv")
        elif argumento.startswith("-"):
            raise ValueError(f"opção desconhecida: {argumento}")
        elif arquivo is None:
            arquivo = argumento
        else:
            raise ValueError(f"argumento a mais: {argumento}")
    if arquivo is None:
        raise ValueError("informe o arquivo CNAB")
    return arquivo, destino


def main(argv: list[str] | None = None) -> int:
    """Roda a linha de comando e devolve o código de saída (0, 1 ou 2)."""
    argv = sys.argv[1:] if argv is None else argv
    if {"-h", "--ajuda", "--help"} & set(argv):
        print(__doc__.strip())
        return 0
    try:
        arquivo, destino = ler_argumentos(argv)
    except ValueError as erro:
        print(f"erro: {erro}\n{USO}", file=sys.stderr)
        return 2
    try:
        leitura = ler_arquivo(arquivo)
    except FileNotFoundError:
        print(f"erro: arquivo não encontrado: {arquivo}", file=sys.stderr)
        return 2
    except OSError:
        print(f"erro: não foi possível ler {arquivo}", file=sys.stderr)
        return 2

    print(relatorio(arquivo, leitura))
    if leitura.erros:
        if destino:
            print("\nO CSV não foi gravado, porque o arquivo tem erros.")
        return 1
    if destino:
        exportar_csv(leitura.detalhes, destino)
        print(f"\nCSV gravado em {destino} ({len(leitura.detalhes)} linhas).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
