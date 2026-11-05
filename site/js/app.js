/* Controlador de interface do Ranking no site (eventos, estados de carregamento e exibição de erros). */
(function () {
  'use strict';

  const api = window.MilhaoAPI;
  const ranking = window.MilhaoRanking;
  const filter = document.getElementById('jogo-filtro');
  const button = document.getElementById('atualizar');
  const status = document.getElementById('ranking-status');
  const table = document.getElementById('ranking-table-wrap');
  const body = document.getElementById('ranking-body');
  const updated = document.getElementById('ranking-updated');
  let activeRequest;

  function message(title, text) {
    table.hidden = true;
    body.replaceChildren();
    status.hidden = false;
    status.querySelector('h3').textContent = title;
    status.querySelector('p').textContent = text;
  }

  async function refresh() {
    if (!api.isConfigured()) {
      console.warn(
        '[ShowDoMilhao][AppJS] O site aguarda o preenchimento de CONFIG.url e CONFIG.publicKey em site/js/supabase.js.'
      );
      message(
        'Configuração do Supabase pendente no site.',
        'Preencha SUPABASE_URL e SUPABASE_ANON_KEY no arquivo site/js/supabase.js com os mesmos dados do seu .env para exibir o ranking.'
      );
      return;
    }

    if (activeRequest) activeRequest.abort();
    const controller = new AbortController();
    activeRequest = controller;
    const timer = setTimeout(() => controller.abort(), 20000);

    button.disabled = true;
    filter.disabled = true;
    document.querySelector('.ranking-panel').setAttribute('aria-busy', 'true');
    message('Consultando resultados…', 'Buscando os jogos e as melhores partidas no Supabase.');

    try {
      const previous = filter.value || String(api.CONFIG.defaultGameId || 1);
      const games = await api.listGames(controller.signal);
      if (activeRequest !== controller) return;

      filter.replaceChildren();
      games.forEach(game => {
        const option = document.createElement('option');
        option.value = String(game.id);
        option.textContent = game.nome;
        filter.append(option);
      });

      if (!games.length) {
        const option = document.createElement('option');
        option.value = '';
        option.textContent = 'Nenhum jogo disponível';
        filter.append(option);
        message('Ainda não há jogos.', 'Cadastre o jogo na tabela "jogos" do Supabase (ex: id = 1).');
        updated.textContent = 'Consulta concluída · nenhum jogo';
        return;
      }

      if (games.some(game => String(game.id) === previous)) {
        filter.value = previous;
      }

      const selected = games.find(game => String(game.id) === filter.value) || games[0];
      const matches = await api.listMatches(selected.id, controller.signal);
      if (activeRequest !== controller) return;

      const rows = ranking.topTen(matches, selected.id);
      if (!rows.length) {
        message(
          'O próximo destaque pode ser você.',
          'Ainda não há partidas no ranking. Seja o primeiro: jogue aqui no site ou no terminal com o Python.'
        );
      } else {
        ranking.render(body, rows, selected.nome);
        status.hidden = true;
        table.hidden = false;
      }

      updated.textContent =
        'Atualizado às ' +
        new Intl.DateTimeFormat('pt-BR', { timeStyle: 'short', timeZone: 'America/Sao_Paulo' }).format(new Date()) +
        ' · Brasília';
    } catch (error) {
      if (activeRequest !== controller) return;
      console.error('[ShowDoMilhao][AppJS] Erro ao carregar ranking:', error);

      let detalheTela = 'A conexão não foi concluída. Verifique o Console do navegador (F12) para mais detalhes.';
      if (error.message === 'RANKING_TOO_LARGE') {
        detalheTela = 'O volume de partidas exige uma consulta de ranking no servidor.';
      } else if (error.message && (error.message.includes('RLS_PERMISSION_DENIED') || error.message.includes('INVALID_CONFIG') || error.message.includes('TABLE_NOT_FOUND') || error.message.includes('QUERY_FAILED'))) {
        detalheTela = error.message;
      }

      message('Não foi possível carregar o ranking.', detalheTela);
      updated.textContent = 'Última consulta sem sucesso';
    } finally {
      clearTimeout(timer);
      if (activeRequest === controller) {
        button.disabled = false;
        filter.disabled = !filter.value;
        document.querySelector('.ranking-panel').setAttribute('aria-busy', 'false');
        activeRequest = null;
      }
    }
  }

  button.addEventListener('click', refresh);
  filter.addEventListener('change', refresh);
  // Quando uma partida do site termina, o ranking é atualizado sozinho.
  document.addEventListener('milhao:partida-finalizada', refresh);
  refresh();
})();
