# Show do Milhão — site

Front-end estático em HTML, CSS e JavaScript puro, sem build nem dependências. Tem o **jogo web** e o **ranking**, os dois conectados ao Supabase.

## Visualizar

Na raiz do repositório, rode `python3 -m http.server 8000` e abra <http://localhost:8000/>. A página da raiz encaminha para `site/`.

Arquivos:

- `index.html`: início, regras, jogo (`#jogar`) e ranking (`#ranking`).
- `css/style.css`: identidade azul e dourada, layout responsivo e movimento reduzido.
- `js/supabase.js`: URL e chave publicável do Supabase, consultas do ranking e chamadas às funções do jogo.
- `js/jogo.js`: tela do jogo (apelido, perguntas, ajudas, parar, resultado).
- `js/ranking.js`: classificação, deduplicação e renderização segura do Top 10.
- `js/app.js`: filtro e atualização do ranking (também atualiza sozinho ao fim de cada partida).
- `assets/emblema.svg`: emblema original local.

## Como o site fala com o Supabase

`js/supabase.js` usa a chave **publicável** (`sb_publishable_…`). Ela é pública por definição e o banco só deixa essa chave fazer duas coisas:

1. **Ler o ranking**: `GET /rest/v1/jogos` e `GET /rest/v1/partidas`.
2. **Jogar**: `POST /rest/v1/rpc/web_iniciar_partida`, `web_responder`, `web_usar_ajuda`, `web_parar` e `web_estado` (definidas em `sql/02_jogo_web.sql`).

A pergunta é sorteada e a resposta é conferida **no banco**. O navegador recebe o enunciado e as alternativas, mas nunca o gabarito, e não consegue gravar em `partidas` direto. Cada partida tem um token secreto, que fica no `sessionStorage` para retomar o jogo se a página recarregar. Nunca coloque a chave secreta (`sb_secret_…`) no site.

O ranking ordena por maior prêmio, menor tempo, data mais antiga e ID, e mostra só a melhor partida de cada apelido. Partidas do site e do Python aparecem juntas (`jogo_id = 1`).

## Publicar no GitHub Pages

### Publicação pela main e pela raiz

Em **Settings → Pages → Build and deployment**, selecione **Deploy from a branch**, branch **main** e pasta **/(root)**, e salve. O `index.html` da raiz encaminha automaticamente para `./site/`, mantendo os arquivos do Front-end organizados nessa pasta. Não há build ou instalação de dependências.

Após o workflow **pages build and deployment** concluir, abra:

- Página inicial: <https://xxzre.github.io/jogo_show_do_milhao/>
- Acesso direto ao site: <https://xxzre.github.io/jogo_show_do_milhao/site/>

A aba **Actions** mostra as execuções de publicação, não a interface do site. O botão **Visit site** em **Settings → Pages** abre a página publicada. Se estiver vendo uma versão anterior, confirme o commit da última publicação e atualize o navegador com `Ctrl+F5`.

### Alternativa: publicar somente a pasta site com Actions

Os caminhos são relativos e também funcionam ao publicar apenas o conteúdo de `site/` na raiz do endereço Pages. O GitHub Pages não permite selecionar `site/` diretamente em “Deploy from a branch” (as opções são raiz e `docs/`). Para publicar somente essa pasta, substitua o modo de publicação por Actions:

1. Com autorização da equipe, crie `.github/workflows/pages.yml` na raiz usando o exemplo abaixo. Ele não foi adicionado automaticamente para não ativar publicação no repositório compartilhado.
2. Em **Settings → Pages → Build and deployment**, selecione **GitHub Actions**.
3. Faça commit e push dos arquivos e do workflow somente com autorização. Execute o workflow na aba Actions. O exemplo é manual e publica o conteúdo de `site/`.

```yaml
name: Publicar site
on:
  workflow_dispatch:
permissions:
  contents: read
  pages: write
  id-token: write
concurrency:
  group: pages
  cancel-in-progress: false
jobs:
  deploy:
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/configure-pages@v5
      - uses: actions/upload-pages-artifact@v3
        with:
          path: site
      - name: Publicar
        id: deployment
        uses: actions/deploy-pages@v4
```

## Verificação

1. Jogue uma partida até o fim e confira se ela aparece no ranking sem recarregar a página.
2. Use cada ajuda: as cartas nunca eliminam a certa, a plateia soma 100% e o pulo mantém o prêmio.
3. Recarregue no meio da partida: ela deve continuar na mesma pergunta.
4. Use um apelido como `<img src=x onerror=alert(1)>`: ele deve aparecer só como texto.
5. No F12 (aba Rede), confira que nenhuma resposta traz a alternativa correta antes de você responder.
