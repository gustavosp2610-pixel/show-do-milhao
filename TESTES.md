# Testes mínimos antes da entrega

Resultado dos testes pedidos pelo professor, feitos em 05/11/2026 nas duas versões do jogo:

- **Terminal (Python):** testes automáticos em `tests/test_entrega.py`, que usam um Supabase simulado em memória para conseguir provocar quedas de conexão. Para rodar: `python -m unittest discover -s tests -v`. Eles também rodam sozinhos no GitHub Actions a cada envio.
- **Site:** testado no **Supabase de verdade**, jogando como visitante (a mesma permissão de quem abre o site), e no navegador (Chromium) para a parte visual do ranking. Os dados de teste foram apagados depois.

**Resultado: todos os testes passaram.** Python: 29 de 29. Site no Supabase: 15 de 15. Site no navegador: 7 de 7.

| # | O que foi pedido | Terminal (Python) | Site |
|---|---|---|---|
| 1 | Partida com 9 acertos paga R$ 1.000.000,00, sem somar as etapas | ✅ prêmio = 1.000.000 (a soma seria 1.891.000) | ✅ prêmio = 1.000.000,00 |
| 2 | Errar a primeira encerra com R$ 0,00 | ✅ | ✅ |
| 2 | Errar depois de alguns acertos | ✅ errou na 4ª e ficou com R$ 10.000 | ✅ errou na 4ª e ficou com R$ 10.000 |
| 2 | Desistência | ✅ parou depois de 2 acertos e ficou com R$ 5.000 | ✅ parou depois de 2 acertos e ficou com R$ 5.000 |
| 3 | Apelido vazio: pede de novo | ✅ recusa vazio, só espaços e mais de 100 letras; aceita em seguida | ✅ recusa e deixa corrigir |
| 3 | Alternativa inválida: deixa corrigir | ✅ recusa `X`, vazio, `AB` e `9`; o jogo continua | ✅ recusa `X`; o jogo continua na mesma pergunta |
| 4 | Ordem das dificuldades | ✅ 3 fáceis, 3 médias, 3 difíceis, mesmo usando os 3 pulos | ✅ fácil → média → difícil, mesmo com pulos |
| 4 | Nenhuma pergunta repetida na partida | ✅ 12 perguntas mostradas (9 + 3 puladas), todas diferentes; 50 sorteios sem repetição | ✅ 12 perguntas sorteadas, todas diferentes |
| 5 | Partida salva com jogo, apelido, valor e duração | ✅ | ✅ |
| 5 | Mesmo valor: menor tempo primeiro | ✅ Bia (40 s) antes de Ana (80 s) | ✅ Bia (40 s) antes de Ana (80 s) |
| 5 | Todas as partidas ficam guardadas, e o ranking mostra a melhor de cada apelido | ✅ 5 partidas guardadas, Ana aparece 1 vez | ✅ Ana aparece 1 vez |
| 5 | Rankings de jogos diferentes não se misturam | ✅ jogo 2 fora do ranking do jogo 1 | ✅ trocar o jogo no filtro mostra só o ranking dele |
| 6 | Falha de conexão, reenvio, partida registrada uma vez | ✅ falhou, reenviou com o mesmo ID e gravou 1 vez; resposta perdida depois de gravar também não duplicou; pendência reenviada depois pelo menu | ✅ repetir o pedido de encerrar é recusado; a partida fica registrada 1 vez |
| 7 | Reabrir e conferir que os resultados continuam | ✅ nova conexão encontra a partida salva | ✅ em uma conexão nova, as 8 partidas de teste continuavam no banco |
| 7 | Ranking vazio | ✅ "Nenhuma partida registrada" | ✅ "Ainda não há partidas no ranking" |
| 7 | Falha de consulta | ✅ "Erro ao consultar o ranking" | ✅ mostra o erro e esconde a tabela antiga |

## Correção encontrada durante os testes

No terminal, a tecla **C** servia ao mesmo tempo para responder a alternativa C e para usar as **Cartas**. Quem queria responder C acabava gastando a ajuda. As ajudas agora usam números: **1** = cartas, **2** = universitários, **3** = plateia, **4** = pular. As letras antigas U, L e S continuam funcionando. O teste `test_responder_c_nao_ativa_as_cartas` confere a correção.
