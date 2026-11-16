# Da reunião gravada à lista de pedidos

Dois scripts que transformam uma reunião gravada numa lista de pedidos para conferir. O `transcrever.py` passa o áudio ou o vídeo para texto com o Whisper, rodando na própria máquina, e marca o horário de cada trecho. O `requisitos.py` separa as falas que parecem pedido e monta uma lista de verificação em Markdown, com o horário de cada uma para voltar à gravação.

## O problema

Na reunião de acompanhamento de uma dashboard, os pedidos aparecem soltos no meio da conversa ("precisa ter...", "dá para mostrar...?"). Quem anota perde parte deles e participa menos; quem não anota depende da memória. Gravar, transcrever e filtrar devolve, em minutos, um rascunho da lista de pedidos com o minuto exato de cada um.

## Como rodar

Python 3.10 ou mais novo. O `requisitos.py` e os testes usam só a biblioteca padrão; para transcrever, instale o faster-whisper.

```powershell
pip install faster-whisper                       # só para o transcrever.py
python transcrever.py reuniao.mp4                # gera reuniao.txt e reuniao.srt ao lado do vídeo
python transcrever.py reuniao.m4a --modelo medium --idioma pt --saida transcricoes
python requisitos.py reuniao.txt                 # gera reuniao-requisitos.md
python requisitos.py exemplo/reuniao-ficticia.txt -o exemplo/requisitos.md
python -m unittest discover -s testes -v
```

Na primeira vez, o faster-whisper baixa o modelo escolhido (algumas centenas de MB no `small`) e o guarda em cache; depois disso, a transcrição roda sem internet. Em máquina sem acesso à internet, `--modelo` também aceita a pasta de um modelo já baixado. Sem o pacote instalado, o `transcrever.py` para e mostra o comando de instalação.

## Estrutura

```
07-transcricao-reunioes/
├── transcrever.py                 áudio ou vídeo para .txt com [hh:mm:ss] e .srt
├── requisitos.py                  .txt para lista de pedidos em Markdown
├── exemplo/reuniao-ficticia.txt   reunião inventada, de uns 5 minutos
├── exemplo/requisitos.md          lista gerada a partir dela
└── testes/                        unittest (não precisam do Whisper)
```

## Exemplo de saída

Com dois trechos fictícios, o `transcrever.py` grava o `.txt` (uma linha por trecho, sem o nome de quem fala) e o `.srt` assim:

```
[00:00:03] Bom dia, pessoal. A pauta de hoje é curta: a dashboard comercial.
[00:00:09] Bom dia. Subi ontem a versão nova, com o funil do dia e o volume por canal.
```

```
1
00:00:03,000 --> 00:00:08,620
Bom dia, pessoal. A pauta de hoje é curta: a dashboard comercial.

2
00:00:09,100 --> 00:00:15,480
Bom dia. Subi ontem a versão nova, com o funil do dia e o volume por canal.
```

O `requisitos.py` transforma a reunião de exemplo em `exemplo/requisitos.md` (abaixo, um trecho; o arquivo abre com um aviso de que a lista é heurística):

```markdown
Transcrição: `reuniao-ficticia.txt`. Falas que parecem pedido: 34,0% · 16 de 47.

- [ ] `00:00:29` **Diretor:** Precisa ter a conversão por canal logo no topo da tela. _(precisa)_
- [ ] `00:00:48` **Gerente:** Dá para mostrar o número absoluto junto com o percentual? _(dá para)_
- [ ] `00:01:06` **Diretor:** Outra coisa: eu quero ver o volume pago por dia, comparado com a meta do mês. _(quero)_
- [ ] `00:01:14` **Analista:** A meta está numa planilha separada. Eu consigo importar, mas alguém tem que me mandar atualizada todo mês. _(tem que)_
```

Dos 16 itens, 2 não são pedido: "Dá para fazer", que é a resposta do analista, e "Falta pouco para a reunião das dez". E 2 pedidos ficaram de fora por não usar nenhuma das expressões: "Coloca no alto, do lado do título", uma ordem direta, e "sem o dado de um parceiro aparecer para o outro", uma restrição. A revisão humana resolve os dois lados em poucos minutos, com o horário de cada fala na mão.

## Decisões técnicas

- **Whisper local, pelo faster-whisper:** a reunião não sai da máquina e não há custo por minuto. Na CPU, com `int8`, roda em notebook sem placa de vídeo.
- **Modelo `small` por padrão:** equilíbrio entre qualidade em português e tempo; `medium` ou `large-v3` para áudio ruim.
- **Filtro de voz ligado (`vad_filter`):** pula os silêncios, onde o Whisper costuma inventar frases.
- **Dois formatos de saída:** o `.txt` com `[hh:mm:ss]` serve para ler, buscar e alimentar o `requisitos.py`; o `.srt` abre junto do vídeo para conferir um trecho.
- **Heurística por expressões, e não IA:** é previsível, explicável (cada item mostra a expressão que o pôs na lista) e não custa nada. O preço é o falso positivo e o pedido que escapa, e por isso a revisão é humana.
- **Comparação sem acento e sem maiúscula:** "DÁ PRA", "da pra" e "dá para" contam igual, e o `\b` evita pegar "quer" dentro de "requer".
- **O Whisper não identifica quem fala.** O `requisitos.py` aceita linha com ou sem "Falante:"; no exemplo, os falantes foram anotados à mão.

Todos os dados são fictícios, gerados por script. A reunião de exemplo foi inventada e escrita para mostrar o formato; a lista de pedidos sai do `requisitos.py`.
