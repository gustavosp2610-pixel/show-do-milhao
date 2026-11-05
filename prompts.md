# Registro de Prompts e Evolução Técnica — Show do Milhão (Python + Supabase + GitHub Pages)

Este documento registra os prompts utilizados no desenvolvimento e diagnóstico de integração do projeto acadêmico **Show do Milhão**, bem como as decisões arquiteturais e correções aplicadas.

---

## Roteiro resumido: prompts básicos de cada etapa

Resumo dos pedidos feitos à IA, na ordem em que o projeto foi construído. Os registros detalhados de cada etapa vêm logo depois.

| Etapa | Parte do projeto | Resultado |
|---|---|---|
| 1 | Planejamento | Divisão em Python, Supabase e site |
| 2 | Banco de dados | `sql/schema.sql` |
| 3 | Perguntas | 24 perguntas cadastradas no Supabase |
| 4 | Jogo em Python | `main.py`, `game_logic.py`, `ajudas.py` |
| 5 | Python + Supabase | `config.py`, `database.py`, `.env.example` |
| 6 | Testes | `tests/` e `.github/workflows/testes.yml` |
| 7 | Site | `site/index.html`, `site/css`, `site/js/ranking.js` |
| 8 | Jogo no site | `sql/02_jogo_web.sql`, `site/js/jogo.js` |
| 9 | Integração final | Tudo conectado ao mesmo Supabase |
| 10 | Publicação | GitHub Pages e Actions |

**1. Planejamento**
> "Vamos fazer um Show do Milhão para a escola: jogo em Python, banco de dados no Supabase com ranking e um site onde dá para jogar. Divida o projeto em partes para um grupo, diga o que cada parte entrega e como elas se conectam."

**2. Banco de dados no Supabase**
> "Crie o SQL das tabelas do Show do Milhão no Supabase: perguntas (enunciado, alternativas A a D, correta, dificuldade fácil/média/difícil), partidas (apelido, valor ganho, tempo, acertos, motivo de encerramento, data), ajudas utilizadas e etapas de premiação de R$ 1.000 a R$ 1.000.000. Ative o RLS e não deixe o navegador ver as respostas certas."

**3. Perguntas**
> "Escreva 24 perguntas de conhecimentos gerais (8 fáceis, 8 médias e 8 difíceis), com 4 alternativas e só uma correta, no formato de INSERT para a tabela perguntas."

**4. Jogo em Python**
> "Faça o jogo em Python para o terminal: pede o apelido, sorteia 9 perguntas (3 de cada nível) sem repetir, prêmio substitutivo até R$ 1 milhão, opção de parar e quatro ajudas: cartas (elimina de 0 a 3 erradas), universitários (3 palpites), plateia (porcentagens que somam 100%) e 3 pulos. Separe em arquivos e comente o código."

**5. Ligar o Python ao Supabase**
> "Conecte o jogo Python ao Supabase com a biblioteca supabase-py. Leia URL e chave de um arquivo .env, busque as perguntas no banco e salve o resultado da partida e as ajudas usadas. Se a internet cair, não perca o resultado. Mostre o ranking Top 10 no terminal."

**6. Testes**
> "Crie testes automáticos com unittest que não precisem de internet: as cartas nunca eliminam a certa, a plateia soma 100%, os pulos funcionam e a vitória paga R$ 1 milhão. Crie também um GitHub Actions que rode os testes a cada push."

**7. Site**
> "Crie o site do Show do Milhão em HTML, CSS e JavaScript puro, azul e dourado, funcionando no celular: início, regras, escada de prêmios e ranking Top 10 lido do Supabase. O ranking ordena por maior prêmio e menor tempo e mostra só a melhor partida de cada apelido."

**8. Jogo no site, sem dar para colar**
> "Coloque o jogo dentro do site, com as mesmas regras do Python. A resposta certa não pode ir para o navegador e ninguém pode gravar um resultado falso no ranking. Faça a lógica rodar no Supabase (funções no banco) e o site só mostrar a pergunta e mandar a resposta."

**9. Integração final**
> "Cada um fez uma parte e, na hora de juntar, o site não ficou conectado com o jogo nem com o Supabase. Analise o repositório e o banco, encontre o que está errado e conecte tudo: partidas do site e do Python no mesmo ranking. Teste antes de entregar."

**10. Publicação**
> "Publique o site no GitHub Pages, confira se os testes e o pacote de entrega rodam no GitHub Actions e escreva um README e um COMO_ABRIR.txt explicando como jogar e como rodar o Python."

---

## Prompt 1 — Desenvolvimento do Módulo do Jogo em Python (Terminal) Integrado ao Supabase

### Contexto / Solicitação
Desenvolvimento modular em Python 3.10+ para execução no terminal integrado ao Supabase (`supabase-py`), contendo:
- Validação de apelido não vazio.
- Sorteio de 9 perguntas (3 fáceis, 3 médias e 3 difíceis) + reservas para pulos, sem repetição.
- Sistema de ajudas (Cartas, Universitários, Plateia e Pulos).
- Tabela de prêmios substitutivos (de R$ 1.000,00 até R$ 1.000.000,00).
- Medição precisa de tempo com `time.perf_counter()`.
- Persistência idempotente de partidas com `uuid.uuid4()` gerado localmente e fila de reintento em memória em caso de falha de rede.

### Arquivos Estruturados
- `config.py`, `database.py`, `game_logic.py`, `ajudas.py`, `main.py`, `requirements.txt`, `.env.example`.

---

## Prompt 2 — Diagnóstico e Correção de Sincronização entre Python, Supabase e Ranking Web (GitHub Pages)

### Problema Relatado
> *"Estou com um problema de sincronização entre o meu jogo em Python (Show do Milhão) e o site de ranking publicado no GitHub Pages (`https://xxzre.github.io/jogo_show_do_milhao/`). O jogo no terminal roda, mas os dados das partidas finalizadas não estão refletindo na tabela de ranking da página web. Preciso que você diagnostique a causa e forneça as correções necessárias para alinhar o código em Python com o front-end JavaScript do site."*

### Diagnóstico de Causa Raiz (4 Gargalos Identificados)
1. **Credenciais vazias no Front-End (`site/js/supabase.js`)**:
   - O objeto `CONFIG` no arquivo `site/js/supabase.js` estava com `url: ''` e `publicKey: ''`, fazendo `isConfigured()` retornar `false` e impedindo qualquer requisição HTTP ao Supabase.
2. **Bloqueio de Row Level Security (RLS) e `REVOKE ALL` no Banco (`sql/schema.sql`)**:
   - O script `sql/schema.sql` habilitava RLS em todas as tabelas e executava `REVOKE ALL ... FROM anon, authenticated` sem criar políticas (`CREATE POLICY`) para o papel `anon`. Assim, tanto o navegador quanto o cliente Python usando a chave `anon` recebiam erro de permissão (`HTTP 401/403 - permission denied`).
3. **Ausência da Tabela `jogos` no Script SQL (`sql/schema.sql`)**:
   - O site consulta primeiro a tabela `jogos` (`SELECT id, nome FROM jogos`) para popular o seletor de jogos antes de buscar `partidas`. O script `sql/schema.sql` original não criava a tabela `public.jogos` nem inseria o registro inicial (`id = 1, nome = 'Show do Milhão'`).
4. **Alinhamento de Critérios de Desempate e Deduplicação (`database.py` vs `site/js/ranking.js`)**:
   - Adicionada validação automática do `jogo_id` na tabela `jogos`, logs detalhados de status HTTP/PostgREST em `database.py`, e alinhamento da consulta do ranking para aplicar os 4 critérios oficiais (`valor_ganho DESC`, `tempo_segundos ASC`, `data_hora ASC`, `id ASC`) mantendo apenas a melhor partida de cada `apelido` (Top 10).

---

## Prompt 3 — Integração final: site jogável conectado ao Supabase e ao ranking

### Problema relatado
> *"Cada um fez uma parte e, na hora de juntar, deu muito problema. O site está sozinho, não está conectado com o jogo nem com o Supabase. Quero que você entenda todo o projeto e conecte tudo."*

### Diagnóstico
1. O banco real estava diferente do `sql/schema.sql`: não existia a tabela `jogos`, e o navegador (`anon`) não tinha permissão nem para ler o ranking.
2. O `sql/schema.sql` da correção anterior liberava `INSERT`/`UPDATE` em `partidas` para `anon`. Isso deixaria qualquer visitante inventar resultados, e o script nunca chegou a ser aplicado.
3. O site tinha só apresentação e ranking, com a chave de exemplo (`sua-anon-key-aqui`), e não tinha o jogo.
4. A tabela `partidas_web` existia para um jogo web que não tinha sido implementado.

### Solução aplicada
- **Banco (`sql/02_jogo_web.sql`)**: criada a tabela `jogos` (id 1 = Show do Milhão), liberada só a **leitura** de `jogos` e `partidas` para o ranking, e criadas as funções `web_*`, que rodam o jogo do site no servidor do banco com as mesmas regras e probabilidades do `ajudas.py`. No fim da partida, o resultado vai para `partidas` e as ajudas para `ajudas_utilizadas`, igual ao Python.
- **Site**: nova seção **Jogar** (`site/js/jogo.js`), `site/js/supabase.js` configurado com a chave publicável, e ranking atualizado automaticamente quando a partida termina.
- **Python**: usa só perguntas ativas e avisa se o `.env` estiver com a chave pública em vez da secreta.
- **`sql/schema.sql`** reescrito para refletir o banco real, sem permissões de escrita para o navegador.
- **Testes**: funções do banco testadas como visitante (vitória com todas as ajudas, erro, desistência, token falso, tentativa de gravar no ranking e de ler o gabarito) e site testado no navegador, jogando partidas completas.

