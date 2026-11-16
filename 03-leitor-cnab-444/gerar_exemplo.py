"""Gera os arquivos CNAB 444 fictícios de exemplos/.

    python gerar_exemplo.py

remessa.rem traz os títulos que a Fintech Exemplo cede ao fundo; retorno.ret,
o que aconteceu com esses mesmos títulos; com_erros.rem é a remessa com três
erros de propósito (linha curta, sequencial pulado e total do trailer errado).
Tudo sai de random.Random(42): rodar de novo grava os mesmos bytes.
"""

import random
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from layout import DETALHE, HEADER, SEQUENCIAL, TRAILER, Campo, Registro, Tipo, posicoes

SEMENTE = 42
QUANTIDADE_TITULOS = 40
DATA_REMESSA = date(2026, 3, 2)
DATA_RETORNO = date(2026, 5, 8)
TAXA_MENSAL = Decimal("0.02")  # desconto na cessão
MULTA = Decimal("0.02")  # pagamento depois do vencimento
CENTAVO = Decimal("0.01")
LINHA_DO_PULO = 10  # em com_erros.rem, a linha onde o sequencial pula um número
PASTA_EXEMPLOS = Path(__file__).resolve().parent / "exemplos"


def formatar_campo(campo: Campo, valor) -> str:
    """O valor escrito com o tamanho exato do campo; ValueError se não couber."""
    if campo.tipo is Tipo.BRANCOS:
        texto = " " * campo.tamanho
    elif campo.tipo is Tipo.ALFANUMERICO:
        texto = str(valor).ljust(campo.tamanho)
    elif campo.tipo is Tipo.DATA:
        texto = valor.strftime("%d%m%y")
    elif campo.tipo is Tipo.VALOR:
        texto = str(int(valor * 100)).zfill(campo.tamanho)
    else:
        texto = str(valor).zfill(campo.tamanho)
    so_digitos = campo.tipo in (Tipo.NUMERICO, Tipo.DATA, Tipo.VALOR)
    if len(texto) != campo.tamanho or (so_digitos and not texto.isdigit()):
        onde = posicoes(campo.inicio, campo.fim)
        raise ValueError(f"{valor!r} não cabe em {campo.nome} ({onde})")
    return texto


def trocar_campo(linha: str, campo: Campo, valor) -> str:
    """A linha com um campo reescrito; serve para estragar um arquivo de propósito."""
    return linha[: campo.inicio - 1] + formatar_campo(campo, valor) + linha[campo.fim :]


def montar_linha(registro: Registro, valores: dict) -> str:
    """Uma linha de 444 posições; o tipo de registro vem do próprio registro."""
    valores = {**valores, "tipo_registro": registro.tipo}
    return "".join(
        formatar_campo(campo, None if campo.tipo is Tipo.BRANCOS else valores[campo.nome])
        for campo in registro.campos
    )


def montar_arquivo(header: dict, detalhes: list[dict]) -> list[str]:
    """Header, detalhes e trailer, com sequencial, quantidade e total calculados aqui."""
    trailer = {
        "quantidade_detalhes": len(detalhes),
        "valor_total": sum((detalhe["valor_titulo"] for detalhe in detalhes), Decimal("0.00")),
    }
    registros = [(HEADER, header), *[(DETALHE, d) for d in detalhes], (TRAILER, trailer)]
    return [
        montar_linha(registro, {**valores, "sequencial_registro": numero})
        for numero, (registro, valores) in enumerate(registros, start=1)
    ]


def novo_header(literal: str, data: date) -> dict:
    """Header da Fintech Exemplo, para REMESSA ou RETORNO."""
    return {
        "tipo_arquivo": "1" if literal == "REMESSA" else "2",
        "literal_arquivo": literal,
        "codigo_originador": "12345",
        "nome_originador": "FINTECH EXEMPLO",
        "data_gravacao": data,
        "sequencial_arquivo": "1",
    }


def _digito_verificador(digitos: str, peso_maximo: int) -> str:
    """Módulo 11 com pesos 2, 3, ... da direita para a esquerda, voltando a 2 depois do máximo."""
    soma = sum(int(d) * (2 + i % (peso_maximo - 1)) for i, d in enumerate(reversed(digitos)))
    resto = soma % 11
    return "0" if resto < 2 else str(11 - resto)


def documento_ficticio(rng: random.Random, cpf: bool) -> str:
    """CPF ou CNPJ com o 1º dígito verificador trocado: não passa na conferência."""
    base = "".join(str(rng.randint(0, 9)) for _ in range(9 if cpf else 12))
    peso_maximo = 11 if cpf else 9
    dv1 = _digito_verificador(base, peso_maximo)
    dv2 = _digito_verificador(base + dv1, peso_maximo)
    return base + str((int(dv1) + 1) % 10) + dv2


def valor_presente(valor: Decimal, vencimento: date) -> Decimal:
    """Preço de aquisição: o valor de face descontado à TAXA_MENSAL até o vencimento."""
    meses = Decimal((vencimento - DATA_REMESSA).days) / 30
    return (valor / (1 + TAXA_MENSAL) ** meses).quantize(CENTAVO)


def gerar_titulos(rng: random.Random, quantidade: int = QUANTIDADE_TITULOS) -> list[dict]:
    """Títulos cedidos na remessa (ocorrência 01), com sacados fictícios."""
    titulos = []
    for numero in range(1, quantidade + 1):
        vencimento = DATA_REMESSA + timedelta(days=rng.randint(10, 60))
        valor = Decimal(rng.randint(30_000, 1_500_000)).scaleb(-2)  # R$ 300,00 a R$ 15.000,00
        pessoa_fisica = rng.random() < 0.7
        titulos.append({
            "seu_numero": f"FE-{numero:06d}",
            "nosso_numero": f"{numero:011d}",
            "valor_pago": Decimal("0.00"),
            "data_ocorrencia": DATA_REMESSA,
            "codigo_ocorrencia": "01",
            "numero_documento": f"DOC{numero:07d}",
            "data_vencimento": vencimento,
            "valor_titulo": valor,
            "data_emissao": DATA_REMESSA - timedelta(days=rng.randint(1, 20)),
            "valor_presente": valor_presente(valor, vencimento),
            "tipo_inscricao_sacado": "01" if pessoa_fisica else "02",
            "numero_inscricao_sacado": documento_ficticio(rng, cpf=pessoa_fisica).zfill(14),
            "nome_sacado": f"SACADO FICTICIO {numero:04d}",
        })
    return titulos


def gerar_retorno(rng: random.Random, titulos: list[dict]) -> list[dict]:
    """Uma ocorrência por título: liquidação, alteração de vencimento ou baixa."""
    detalhes = []
    for titulo in titulos:
        vencimento = titulo["data_vencimento"]
        sorteio = rng.random()
        if sorteio < 0.75:
            pagamento = vencimento + timedelta(days=rng.randint(-3, 5))
            pago = titulo["valor_titulo"]
            if pagamento > vencimento:
                pago = (pago * (1 + MULTA)).quantize(CENTAVO)
            mudanca = {"codigo_ocorrencia": "06", "data_ocorrencia": pagamento, "valor_pago": pago}
        elif sorteio < 0.90:
            mudanca = {
                "codigo_ocorrencia": "14",
                "data_ocorrencia": vencimento - timedelta(days=rng.randint(1, 5)),
                "data_vencimento": vencimento + timedelta(days=30),
            }
        else:
            mudanca = {
                "codigo_ocorrencia": "09",
                "data_ocorrencia": vencimento + timedelta(days=rng.randint(1, 5)),
            }
        detalhes.append({**titulo, **mudanca})
    return detalhes


def com_erros(remessa: list[str]) -> list[str]:
    """A remessa com três erros de propósito, um em cada linha."""
    linhas = list(remessa)
    # 1. Some um dos brancos do header: a linha fica com 443 posições.
    linhas[0] = linhas[0][:200] + linhas[0][201:]
    # 2. Da LINHA_DO_PULO em diante, o sequencial vem um número à frente.
    for indice in range(LINHA_DO_PULO - 1, len(linhas)):
        linhas[indice] = trocar_campo(linhas[indice], SEQUENCIAL, indice + 2)
    # 3. O trailer soma R$ 1.000,00 a mais que os detalhes.
    campo_total = TRAILER.campo("valor_total")
    total_errado = Decimal(campo_total.recortar(linhas[-1])).scaleb(-2) + 1000
    linhas[-1] = trocar_campo(linhas[-1], campo_total, total_errado)
    return linhas


def gravar(caminho: Path, linhas: list[str]) -> None:
    """Grava em latin-1, com CRLF no fim de cada linha, como é comum em CNAB."""
    caminho.write_bytes("".join(f"{linha}\r\n" for linha in linhas).encode("latin-1"))


def gerar_exemplos(pasta: Path = PASTA_EXEMPLOS) -> dict[str, list[str]]:
    """Grava os três exemplos na pasta e devolve as linhas de cada um."""
    rng = random.Random(SEMENTE)
    titulos = gerar_titulos(rng)
    remessa = montar_arquivo(novo_header("REMESSA", DATA_REMESSA), titulos)
    retorno = montar_arquivo(novo_header("RETORNO", DATA_RETORNO), gerar_retorno(rng, titulos))
    arquivos = {
        "remessa.rem": remessa,
        "retorno.ret": retorno,
        "com_erros.rem": com_erros(remessa),
    }
    pasta.mkdir(parents=True, exist_ok=True)
    for nome, linhas in arquivos.items():
        gravar(pasta / nome, linhas)
    return arquivos


if __name__ == "__main__":
    for nome, linhas in gerar_exemplos().items():
        print(f"exemplos/{nome}: {len(linhas)} linhas")
