"""Leitor: ida e volta, cada tipo de erro na linha certa, resumo, CSV e linha de comando."""

import codecs
import csv
import io
import random
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import gerar_exemplo as gerador
from layout import DETALHE, OCORRENCIAS, SEQUENCIAL, TRAILER
from leitor import COLUNAS_CSV, exportar_csv, ler_arquivo, ler_linhas, main, resumir


def titulos_e_retorno():
    rng = random.Random(gerador.SEMENTE)
    titulos = gerador.gerar_titulos(rng)
    return titulos, gerador.gerar_retorno(rng, titulos)


def montar(literal, detalhes):
    data = gerador.DATA_REMESSA if literal == "REMESSA" else gerador.DATA_RETORNO
    return gerador.montar_arquivo(gerador.novo_header(literal, data), detalhes)


def escrever(linha, campo, texto):
    """Põe qualquer texto, até um inválido, nas posições do campo."""
    assert len(texto) == campo.tamanho
    return linha[: campo.inicio - 1] + texto + linha[campo.fim :]


def trocar(linhas, numero, nova):
    """Cópia das linhas com a linha 'numero' (contada a partir de 1) substituída."""
    copia = list(linhas)
    copia[numero - 1] = nova
    return copia


def onde(erros):
    return [(erro.linha, erro.campo.nome if erro.campo else None) for erro in erros]


class TestIdaEVolta(unittest.TestCase):
    """Gerar, gravar e ler: os valores voltam iguais, já convertidos."""

    def conferir(self, literal, detalhes):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "arquivo.rem"
            gerador.gravar(caminho, montar(literal, detalhes))
            leitura = ler_arquivo(caminho)
        self.assertEqual(leitura.erros, [])
        self.assertEqual(leitura.header["literal_arquivo"], literal)
        self.assertEqual(len(leitura.detalhes), len(detalhes))
        for escrito, lido in zip(detalhes, leitura.detalhes):
            self.assertEqual({chave: lido[chave] for chave in escrito}, escrito)
        self.assertEqual(leitura.trailer["valor_total"], sum(d["valor_titulo"] for d in detalhes))

    def test_remessa(self):
        titulos, _ = titulos_e_retorno()
        self.conferir("REMESSA", titulos)

    def test_retorno(self):
        _, retorno = titulos_e_retorno()
        self.conferir("RETORNO", retorno)


class TestErros(unittest.TestCase):
    """Cada tipo de erro aparece com a linha e o campo certos."""

    def setUp(self):
        self.linhas = montar("REMESSA", titulos_e_retorno()[0])
        self.ultima = len(self.linhas)

    def no_detalhe(self, numero, nome_campo, texto):
        linha = escrever(self.linhas[numero - 1], DETALHE.campo(nome_campo), texto)
        return trocar(self.linhas, numero, linha)

    def no_trailer(self, nome_campo, texto):
        linha = escrever(self.linhas[-1], TRAILER.campo(nome_campo), texto)
        return trocar(self.linhas, self.ultima, linha)

    def com_pulo_a_partir_da_linha(self, numero):
        return [linha if n < numero else escrever(linha, SEQUENCIAL, f"{n + 1:06d}")
                for n, linha in enumerate(self.linhas, start=1)]

    def test_primeiro_erro_de_cada_caso(self):
        l, ultima = self.linhas, self.ultima
        total = int(TRAILER.campo("valor_total").recortar(l[-1]))
        casos = [
            # descrição, linhas, linha do erro, campo do erro, trecho da mensagem
            ("arquivo vazio", [], None, None, "arquivo vazio"),
            ("linha curta", trocar(l, 5, l[4][:-1]), 5, None, "tem 443 caracteres"),
            ("linha longa", trocar(l, 5, l[4] + " "), 5, None, "tem 445 caracteres"),
            ("linha vazia", trocar(l, 5, ""), 5, None, "linha vazia"),
            ("sem header", l[1:], 1, "tipo_registro", "começar pelo header"),
            ("sem trailer", l[:-1], ultima - 1, "tipo_registro", "terminar pelo trailer"),
            ("header no meio", l[:5] + l[:1] + l[5:], 6, "tipo_registro", "header fora"),
            ("trailer no meio", l[:5] + l[-1:] + l[5:], 6, "tipo_registro", "trailer antes"),
            ("tipo desconhecido", trocar(l, 5, "5" + l[4][1:]), 5, "tipo_registro",
             "'5' desconhecido"),
            ("sequencial pulado", self.com_pulo_a_partir_da_linha(4), 4, "sequencial_registro",
             "o esperado era 000004"),
            ("data inexistente", self.no_detalhe(5, "data_vencimento", "310226"), 5,
             "data_vencimento", "data inválida"),
            ("valor com vírgula", self.no_detalhe(5, "valor_titulo", "00000001234,5"), 5,
             "valor_titulo", "só dígitos"),
            ("número com brancos", self.no_detalhe(5, "nosso_numero", "     123456"), 5,
             "nosso_numero", "só dígitos"),
            ("ocorrência fora da tabela", self.no_detalhe(5, "codigo_ocorrencia", "77"), 5,
             "codigo_ocorrencia", "código 77"),
            ("quantidade do trailer", self.no_trailer("quantidade_detalhes", "000041"), ultima,
             "quantidade_detalhes", "informa 41 detalhes"),
            ("total do trailer", self.no_trailer("valor_total", f"{total + 1:017d}"), ultima,
             "valor_total", "mas os detalhes somam"),
        ]
        for descricao, linhas, linha, nome_campo, trecho in casos:
            with self.subTest(descricao):
                erros = ler_linhas(linhas).erros
                self.assertTrue(erros, "nenhum erro encontrado")
                self.assertEqual(onde(erros)[0], (linha, nome_campo))
                self.assertIn(trecho, erros[0].mensagem)

    def test_pulo_no_sequencial_gera_um_erro_so(self):
        erros = ler_linhas(self.com_pulo_a_partir_da_linha(4)).erros
        self.assertEqual(onde(erros), [(4, "sequencial_registro")])

    def test_detalhe_com_tamanho_errado_impede_conferir_o_total(self):
        erros = ler_linhas(trocar(self.linhas, 5, self.linhas[4][:-1])).erros
        self.assertEqual(onde(erros), [(5, None), (self.ultima, "valor_total")])
        self.assertIn("total não conferido: sem o valor_titulo da linha 5", erros[1].mensagem)

    def test_acento_gravado_em_utf8_ocupa_duas_posicoes(self):
        nome = DETALHE.campo("nome_sacado")
        com_acento = escrever(self.linhas[4], nome, "SACADO FICTÍCIO".ljust(nome.tamanho))
        linhas = trocar(self.linhas, 5, com_acento)
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "utf8.rem"
            caminho.write_bytes("".join(f"{linha}\r\n" for linha in linhas).encode("utf-8"))
            erros = ler_arquivo(caminho).erros
        self.assertEqual(onde(erros)[0], (5, None))
        self.assertIn("tem 445 caracteres", erros[0].mensagem)

    def test_exemplo_com_erros_tem_os_tres_erros_nas_linhas_certas(self):
        erros = ler_linhas(gerador.com_erros(self.linhas)).erros
        esperado = [(1, None), (gerador.LINHA_DO_PULO, "sequencial_registro"),
                    (self.ultima, "valor_total")]
        self.assertEqual(onde(erros), esperado)
        self.assertIn("tem 443 caracteres", erros[0].mensagem)
        self.assertIn("veio 000011", erros[1].mensagem)
        self.assertIn("o trailer informa", erros[2].mensagem)


class TestResumoECsv(unittest.TestCase):
    def setUp(self):
        _, self.retorno = titulos_e_retorno()
        self.leitura = ler_linhas(montar("RETORNO", self.retorno))

    def test_resumo_soma_por_ocorrencia(self):
        resumo = resumir(self.leitura.detalhes)
        codigos = sorted({d["codigo_ocorrencia"] for d in self.retorno})
        self.assertEqual([item.codigo for item in resumo], codigos)
        for item in resumo:
            do_codigo = [d for d in self.retorno if d["codigo_ocorrencia"] == item.codigo]
            with self.subTest(codigo=item.codigo):
                self.assertEqual(item.descricao, OCORRENCIAS[item.codigo])
                self.assertEqual(item.quantidade, len(do_codigo))
                self.assertEqual(item.valor_titulos, sum(d["valor_titulo"] for d in do_codigo))
                self.assertEqual(item.valor_pago, sum(d["valor_pago"] for d in do_codigo))

    def test_csv_para_o_excel_brasileiro(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "nova" / "retorno.csv"
            exportar_csv(self.leitura.detalhes, caminho)
            bruto = caminho.read_bytes()
        self.assertTrue(bruto.startswith(codecs.BOM_UTF8))
        tabela = list(csv.reader(bruto.decode("utf-8-sig").splitlines(), delimiter=";"))
        self.assertEqual(tabela[0], COLUNAS_CSV)
        self.assertEqual(len(tabela), len(self.retorno) + 1)
        primeira, esperado = dict(zip(tabela[0], tabela[1])), self.retorno[0]
        valor = f"{esperado['valor_titulo']:.2f}".replace(".", ",")
        descricao = OCORRENCIAS[esperado["codigo_ocorrencia"]]
        self.assertEqual(primeira["linha"], "2")
        self.assertEqual(primeira["valor_titulo"], valor)
        self.assertEqual(primeira["data_vencimento"], esperado["data_vencimento"].isoformat())
        self.assertEqual(primeira["descricao_ocorrencia"], descricao)


class TestLinhaDeComando(unittest.TestCase):
    def setUp(self):
        temporaria = tempfile.TemporaryDirectory()
        self.addCleanup(temporaria.cleanup)
        self.pasta = Path(temporaria.name)
        gerador.gerar_exemplos(self.pasta)

    def rodar(self, *argumentos):
        saida, erro = io.StringIO(), io.StringIO()
        with redirect_stdout(saida), redirect_stderr(erro):
            codigo = main(list(argumentos))
        return codigo, saida.getvalue(), erro.getvalue()

    def test_arquivo_certo_mostra_o_resumo_e_grava_o_csv(self):
        destino = self.pasta / "saida" / "retorno.csv"
        codigo, saida, _ = self.rodar(str(self.pasta / "retorno.ret"), "--csv", str(destino))
        self.assertEqual(codigo, 0)
        self.assertIn("06 Liquidação", saida)
        self.assertTrue(destino.exists())

    def test_arquivo_com_erro_sai_com_1_e_nao_grava_o_csv(self):
        destino = self.pasta / "saida" / "com_erros.csv"
        codigo, saida, _ = self.rodar(str(self.pasta / "com_erros.rem"), "--csv", str(destino))
        self.assertEqual(codigo, 1)
        onde_pulou = f"linha {gerador.LINHA_DO_PULO}, posições 439 a 444 (sequencial_registro)"
        self.assertIn(onde_pulou, saida)
        self.assertFalse(destino.exists())

    def test_argumentos_errados_ou_arquivo_inexistente_saem_com_2(self):
        casos = [[], ["a.rem", "--csv"], ["a.rem", "--xlsx"], ["a.rem", "b.rem"],
                 [str(self.pasta / "nao_existe.rem")]]
        for argumentos in casos:
            with self.subTest(argumentos=argumentos):
                codigo, _, erro = self.rodar(*argumentos)
                self.assertEqual(codigo, 2)
                self.assertTrue(erro.startswith("erro: "))

    def test_ajuda(self):
        codigo, saida, _ = self.rodar("-h")
        self.assertEqual(codigo, 0)
        self.assertIn("uso", saida.lower())


if __name__ == "__main__":
    unittest.main()
