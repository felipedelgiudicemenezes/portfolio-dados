# Leitor e validador de CNAB 444

Lê arquivos CNAB 444, o formato posicional (444 caracteres por linha) que fundos de recebíveis (FIDC) trocam com o administrador, e confere a estrutura e os totais. Quando há erro, aponta a linha e a posição de cada um; quando não há, mostra o resumo por ocorrência e exporta um CSV pronto para o Excel.

## O problema

Na cessão de recebíveis, o originador manda ao fundo um arquivo de **remessa** com os títulos que está cedendo, e o administrador devolve um arquivo de **retorno** com o que aconteceu com cada um: liquidação, baixa, alteração de vencimento. Não há separador: cada informação vale pela posição na linha. Um caractere a mais desloca o resto da linha, um título perdido só aparece quando o total do trailer não fecha, e abrir o arquivo no Excel não mostra nada disso. Antes de usar os dados, é preciso validar o arquivo e convertê-lo para algo que a área de negócio consiga ler.

## Como rodar

Python 3.10 ou mais novo, só com a biblioteca padrão. A partir desta pasta:

```bash
python gerar_exemplo.py                                        # recria os arquivos de exemplos/
python leitor.py exemplos/remessa.rem --csv saida/remessa.csv
python leitor.py exemplos/retorno.ret --csv saida/retorno.csv
python leitor.py exemplos/com_erros.rem                        # lista os erros e sai com código 1
python -m unittest discover -s testes -v
```

Códigos de saída: 0 para arquivo certo; 1 para arquivo com erro (nesse caso o CSV não é gravado); 2 para argumento errado ou arquivo que não abre.

## Estrutura

```
03-leitor-cnab-444/
├── layout.py           # o layout como dado: campos, posições, tipos e tabela de ocorrências
├── leitor.py           # lê, valida e converte; resumo, CSV e linha de comando
├── gerar_exemplo.py    # gera os arquivos fictícios de exemplos/ (semente 42)
├── exemplos/
│   ├── remessa.rem     # 40 títulos cedidos pela Fintech Exemplo
│   ├── retorno.ret     # o que aconteceu com esses 40 títulos
│   └── com_erros.rem   # a remessa com três erros de propósito
└── testes/             # unittest: layout, leitor e gerador
```

## Exemplo de saída

O validador no arquivo com erros:

```
$ python leitor.py exemplos/com_erros.rem
exemplos/com_erros.rem
3 erros:
  linha 1: a linha tem 443 caracteres; o esperado é 444
  linha 10, posições 439 a 444 (sequencial_registro): veio 000011; o esperado era 000010
  linha 42, posições 8 a 24 (valor_total): o trailer informa R$ 333.146,31, mas os detalhes somam R$ 332.146,31
```

O retorno, que está certo:

```
$ python leitor.py exemplos/retorno.ret --csv saida/retorno.csv
exemplos/retorno.ret
RETORNO nº 1 de 08/05/2026, originador FINTECH EXEMPLO
42 linhas, 40 detalhes, nenhum erro

Ocorrência                       Qtde   Valor dos títulos      Valor pago
06 Liquidação                      31       R$ 248.123,84   R$ 250.723,44
09 Baixa                            2        R$ 19.408,17         R$ 0,00
14 Alteração de vencimento          7        R$ 64.614,30         R$ 0,00
Total                              40       R$ 332.146,31   R$ 250.723,44

CSV gravado em saida/retorno.csv (40 linhas).
```

O começo do CSV, com `;` entre as colunas, vírgula decimal e datas ISO:

```
linha;seu_numero;nosso_numero;numero_documento;codigo_ocorrencia;descricao_ocorrencia;data_ocorrencia;data_emissao;data_vencimento;valor_titulo;valor_presente;valor_pago;tipo_inscricao_sacado;numero_inscricao_sacado;nome_sacado
2;FE-000001;00000000001;DOC0000001;06;Liquidação;2026-04-20;2026-02-21;2026-04-21;2634,78;2549,24;2634,78;01;00033218196010;SACADO FICTICIO 0001
3;FE-000002;00000000002;DOC0000002;06;Liquidação;2026-03-17;2026-02-13;2026-03-13;2264,93;2248,54;2310,23;01;00090838637959;SACADO FICTICIO 0002
```

## O layout

É um layout simplificado, com três registros de 444 posições: o header (tipo 0), um detalhe por título (tipo 1) e o trailer (tipo 9), que traz a quantidade de detalhes e o valor total. **As posições são ilustrativas**, inspiradas nos manuais públicos de CNAB 444 de FIDC; para uso real, é preciso conferir o manual do administrador ou do custodiante. A tabela de ocorrências também é ilustrativa:

| Código | Ocorrência |
|---|---|
| 01 | Entrada de título (remessa) |
| 06 | Liquidação |
| 09 | Baixa |
| 14 | Alteração de vencimento |

## Decisões técnicas

- **O layout é dado, não código.** `layout.py` lista cada campo com posição inicial, posição final e tipo, como a tabela de um manual. Ler, escrever e validar usam a mesma lista, então trocar de layout é editar uma tabela. Os brancos também são campos, e o módulo confere, ao ser importado, que cada registro cobre de 1 a 444 sem buraco nem sobreposição.
- **Tipos certos na conversão.** Valores viram `Decimal`, nunca `float`, e datas DDMMAA viram `date` (ano 20AA). Campos numéricos continuam texto, para não perder os zeros à esquerda de códigos e documentos.
- **Um byte, uma posição.** O arquivo é lido em latin-1, em que cada byte é um caractere. Por isso um "Í" gravado em UTF-8 (dois bytes) aparece como uma linha de 445 posições, do mesmo jeito que o sistema que recebe o arquivo enxergaria.
- **Todos os erros de uma vez**, cada um com linha e posição, em vez de parar no primeiro.
- **Sem erro em cascata.** O sequencial é comparado com o da linha anterior, então um pulo gera um erro só, e não um em cada linha seguinte. Uma linha com tamanho errado não é lida campo a campo, porque as posições deixam de valer; se for um detalhe, o validador avisa que o total do trailer não pôde ser conferido.
- **Com erro, nada de CSV.** Melhor nenhum arquivo do que uma planilha pela metade que parece completa.
- **CSV para o Excel brasileiro**: `;` como separador, vírgula decimal e UTF-8 com BOM, para os acentos abrirem certos.
- **Linha de comando lida à mão**, sem `argparse`, para que as mensagens saiam em português.

## Dados

Todos os dados são fictícios, gerados por script (`random.Random(42)`). A empresa é a "Fintech Exemplo", e os sacados vão de "SACADO FICTICIO 0001" a "SACADO FICTICIO 0040". Os CPFs e CNPJs dos sacados também são fictícios: têm o dígito verificador errado de propósito, e um teste confere isso.
