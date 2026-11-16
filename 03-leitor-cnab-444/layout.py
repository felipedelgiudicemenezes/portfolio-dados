"""Layout CNAB 444 simplificado, escrito como especificação declarativa.

Cada registro (header, detalhe e trailer) é uma tupla de campos com posição
inicial e final, contadas a partir de 1 como nos manuais, e o tipo do campo.
As posições são ilustrativas, inspiradas nos manuais públicos de CNAB 444 de
FIDC; para uso real, confira o manual do administrador ou do custodiante.

Ao importar o módulo, cada registro é conferido: os campos cobrem as posições
1 a 444 sem buraco nem sobreposição, com os brancos declarados como campos.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum

TAMANHO_LINHA = 444


class Tipo(Enum):
    NUMERICO = "numérico"
    ALFANUMERICO = "alfanumérico"
    DATA = "data DDMMAA"
    VALOR = "valor com 2 decimais implícitas"
    BRANCOS = "brancos"


NUM, ALFA, DATA, VALOR = Tipo.NUMERICO, Tipo.ALFANUMERICO, Tipo.DATA, Tipo.VALOR


def posicoes(inicio: int, fim: int) -> str:
    """Texto das posições para as mensagens: 'posição 7' ou 'posições 8 a 24'."""
    return f"posição {inicio}" if inicio == fim else f"posições {inicio} a {fim}"


@dataclass(frozen=True)
class Campo:
    nome: str
    inicio: int
    fim: int
    tipo: Tipo
    descricao: str = ""

    @property
    def tamanho(self) -> int:
        return self.fim - self.inicio + 1

    def recortar(self, linha: str) -> str:
        """O trecho da linha que pertence a este campo."""
        return linha[self.inicio - 1 : self.fim]


def brancos(inicio: int, fim: int) -> Campo:
    return Campo("brancos", inicio, fim, Tipo.BRANCOS)


@dataclass(frozen=True)
class Registro:
    tipo: str
    nome: str
    campos: tuple[Campo, ...]

    def campo(self, nome: str) -> Campo:
        for campo in self.campos:
            if campo.nome == nome:
                return campo
        raise KeyError(f"o {self.nome} não tem o campo {nome!r}")


TIPO_REGISTRO = Campo("tipo_registro", 1, 1, NUM, "0 = header, 1 = detalhe, 9 = trailer")
SEQUENCIAL = Campo("sequencial_registro", 439, 444, NUM, "1, 2, 3... sem pulo")

HEADER = Registro("0", "header", (
    TIPO_REGISTRO,
    Campo("tipo_arquivo", 2, 2, NUM, "1 = remessa, 2 = retorno"),
    Campo("literal_arquivo", 3, 9, ALFA, "REMESSA ou RETORNO"),
    brancos(10, 26),
    Campo("codigo_originador", 27, 46, NUM),
    Campo("nome_originador", 47, 76, ALFA),
    brancos(77, 94),
    Campo("data_gravacao", 95, 100, DATA),
    brancos(101, 110),
    Campo("sequencial_arquivo", 111, 117, NUM),
    brancos(118, 438),
    SEQUENCIAL,
))

DETALHE = Registro("1", "detalhe", (
    TIPO_REGISTRO,
    brancos(2, 37),
    Campo("seu_numero", 38, 62, ALFA, "número de controle do participante"),
    brancos(63, 70),
    Campo("nosso_numero", 71, 81, NUM, "identificação do título na cobrança"),
    Campo("valor_pago", 82, 94, VALOR, "zero na remessa"),
    Campo("data_ocorrencia", 95, 100, DATA, "na remessa, a data da cessão"),
    brancos(101, 108),
    Campo("codigo_ocorrencia", 109, 110, NUM, "ver OCORRENCIAS"),
    Campo("numero_documento", 111, 120, ALFA),
    Campo("data_vencimento", 121, 126, DATA),
    Campo("valor_titulo", 127, 139, VALOR, "valor de face"),
    brancos(140, 150),
    Campo("data_emissao", 151, 156, DATA),
    brancos(157, 192),
    Campo("valor_presente", 193, 205, VALOR, "preço de aquisição na cessão"),
    brancos(206, 218),
    Campo("tipo_inscricao_sacado", 219, 220, NUM, "01 = CPF, 02 = CNPJ"),
    Campo("numero_inscricao_sacado", 221, 234, NUM),
    Campo("nome_sacado", 235, 274, ALFA),
    brancos(275, 438),
    SEQUENCIAL,
))

TRAILER = Registro("9", "trailer", (
    TIPO_REGISTRO,
    Campo("quantidade_detalhes", 2, 7, NUM),
    Campo("valor_total", 8, 24, VALOR, "soma do valor_titulo dos detalhes"),
    brancos(25, 438),
    SEQUENCIAL,
))

REGISTROS = {registro.tipo: registro for registro in (HEADER, DETALHE, TRAILER)}

# Tabela ilustrativa: cada administrador publica a sua.
OCORRENCIAS = {
    "01": "Entrada de título (remessa)",
    "06": "Liquidação",
    "09": "Baixa",
    "14": "Alteração de vencimento",
}


def conferir_cobertura(campos: Iterable[Campo]) -> list[str]:
    """Buracos e sobreposições entre as posições 1 e 444; lista vazia se estiver certo."""
    problemas = []
    proxima = 1
    for campo in campos:
        if campo.fim < campo.inicio:
            problemas.append(
                f"{campo.nome} termina na posição {campo.fim}, antes de começar ({campo.inicio})"
            )
        if campo.inicio > proxima:
            problemas.append(
                f"buraco: {posicoes(proxima, campo.inicio - 1)} sem campo (antes de {campo.nome})"
            )
        elif campo.inicio < proxima:
            problemas.append(
                f"sobreposição: {campo.nome} começa na posição {campo.inicio}, "
                f"mas a primeira livre é a {proxima}"
            )
        proxima = max(proxima, campo.fim + 1)
    if proxima <= TAMANHO_LINHA:
        problemas.append(f"buraco: {posicoes(proxima, TAMANHO_LINHA)} sem campo (no fim da linha)")
    elif proxima > TAMANHO_LINHA + 1:
        problemas.append(f"os campos passam da posição {TAMANHO_LINHA} e vão até a {proxima - 1}")
    return problemas


def _conferir_layout() -> None:
    for registro in REGISTROS.values():
        problemas = conferir_cobertura(registro.campos)
        if problemas:
            raise ValueError(f"layout do {registro.nome} com problema: " + "; ".join(problemas))


_conferir_layout()
