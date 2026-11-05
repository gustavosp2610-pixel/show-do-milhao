/* Conexão do site com o Supabase (ranking + jogo web).
 *
 * A chave abaixo é a chave PUBLICÁVEL (sb_publishable_...). Ela foi feita para
 * ficar no navegador: sozinha, só consegue o que o banco libera para o papel
 * "anon" — ler o ranking (jogos, partidas) e chamar as funções web_* do jogo.
 * O gabarito (tabela perguntas) e a gravação direta de resultados continuam
 * bloqueados. NUNCA coloque aqui a chave secreta (sb_secret_...) do Python.
 */
(function (global) {
  'use strict';

  const CONFIG = Object.freeze({
    url: 'https://dsppcphqhuqryrqfrupy.supabase.co',
    publicKey: 'sb_publishable_ipAE-oFjZFtQrMgCn9jdjg_krsPRgvt',
    // Mesmo JOGO_ID do .env do Python (as partidas do site também usam 1).
    defaultGameId: 1
  });

  const PAGE_SIZE = 1000;
  const MAX_ROWS = 100000;

  function isConfigured() {
    const urlValida = Boolean(
      CONFIG.url &&
      CONFIG.url !== 'https://seu-projeto.supabase.co' &&
      CONFIG.url.trim() !== ''
    );
    const keyValida = Boolean(
      CONFIG.publicKey &&
      CONFIG.publicKey !== 'sua-anon-key-aqui' &&
      CONFIG.publicKey.trim() !== ''
    );
    return urlValida && keyValida;
  }

  /* Valida a configuração e devolve a URL base e os cabeçalhos comuns. */
  function connection() {
    if (!isConfigured()) {
      console.warn('[ShowDoMilhao][SupabaseJS] Credenciais ainda não configuradas em site/js/supabase.js.');
      throw new Error('NOT_CONFIGURED');
    }

    let base;
    try {
      base = new URL(CONFIG.url);
    } catch (_) {
      throw new Error('INVALID_CONFIG: SUPABASE_URL malformada.');
    }

    if (base.protocol !== 'https:' || base.username || base.password) {
      throw new Error('INVALID_CONFIG: SUPABASE_URL deve usar HTTPS.');
    }
    if (CONFIG.publicKey.startsWith('sb_secret_')) {
      throw new Error('INVALID_CONFIG: Não use chave secreta (sb_secret_) no navegador. Use a chave publicável.');
    }

    const headers = { apikey: CONFIG.publicKey, Accept: 'application/json' };

    // Chave antiga "anon" (JWT): também vai no Authorization e não pode ser service_role.
    const token = CONFIG.publicKey.split('.');
    if (token.length === 3) {
      try {
        const payload = JSON.parse(atob(token[1].replace(/-/g, '+').replace(/_/g, '/')));
        if (payload.role && payload.role !== 'anon') {
          throw new Error('INVALID_CONFIG: A chave JWT informada não possui role "anon".');
        }
      } catch (err) {
        if (err.message && err.message.startsWith('INVALID_CONFIG')) throw err;
        throw new Error('INVALID_CONFIG: Token JWT inválido em publicKey.');
      }
      headers.Authorization = 'Bearer ' + CONFIG.publicKey;
    }

    return { base, headers };
  }

  async function query(table, parameters, signal) {
    const { base, headers } = connection();
    const url = new URL('/rest/v1/' + table, base);
    url.search = new URLSearchParams(parameters).toString();

    let response;
    try {
      response = await fetch(url, { headers, signal, cache: 'no-store' });
    } catch (networkErr) {
      if (networkErr.name === 'AbortError') throw networkErr;
      console.error(`[ShowDoMilhao][SupabaseJS] Falha de rede ao consultar "${table}":`, networkErr);
      throw new Error('NETWORK_ERROR: Falha de conexão com o Supabase (' + networkErr.message + ')');
    }

    if (!response.ok) {
      let errorDetail = '';
      try {
        const errJson = await response.json();
        console.error(`[ShowDoMilhao][SupabaseJS] Erro retornado pela API (${table}):`, errJson);
        errorDetail = errJson.message || errJson.details || errJson.hint || JSON.stringify(errJson);
      } catch (_) {
        errorDetail = response.statusText;
      }

      if (response.status === 401 || response.status === 403) {
        throw new Error(
          `RLS_PERMISSION_DENIED (HTTP ${response.status}) na tabela "${table}": ${errorDetail}. ` +
          'Confira as permissões em sql/schema.sql e sql/02_jogo_web.sql.'
        );
      }
      if (response.status === 404) {
        throw new Error(
          `TABLE_NOT_FOUND (HTTP 404): A tabela "${table}" não foi encontrada no Supabase (${errorDetail}).`
        );
      }
      throw new Error(`QUERY_FAILED (HTTP ${response.status} em "${table}"): ${errorDetail}`);
    }

    const rows = await response.json();
    if (!Array.isArray(rows)) {
      throw new Error('INVALID_RESPONSE: A resposta do Supabase não é uma lista JSON.');
    }
    return rows;
  }

  /* Chama uma função do banco (POST /rest/v1/rpc/<nome>). Usado pelo jogo web.
   * Em caso de erro, lança Error com a mensagem do banco e .code = dica (ex.: PARTIDA_INVALIDA). */
  async function rpc(fn, args, signal) {
    const { base, headers } = connection();
    const url = new URL('/rest/v1/rpc/' + fn, base);

    let response;
    try {
      response = await fetch(url, {
        method: 'POST',
        headers: { ...headers, 'Content-Type': 'application/json' },
        body: JSON.stringify(args || {}),
        signal,
        cache: 'no-store'
      });
    } catch (networkErr) {
      if (networkErr.name === 'AbortError') throw networkErr;
      const err = new Error('Sem conexão com o servidor do jogo. Verifique a internet e tente de novo.');
      err.code = 'NETWORK_ERROR';
      throw err;
    }

    let data = null;
    try {
      data = await response.json();
    } catch (_) {
      data = null;
    }

    if (!response.ok) {
      const err = new Error((data && data.message) || `O servidor respondeu com erro (HTTP ${response.status}).`);
      err.code = (data && data.hint) || 'HTTP_' + response.status;
      err.status = response.status;
      throw err;
    }
    return data;
  }

  async function allRows(table, params, signal) {
    const result = [];
    for (let offset = 0; offset < MAX_ROWS; offset += PAGE_SIZE) {
      const rows = await query(table, { ...params, limit: PAGE_SIZE, offset }, signal);
      result.push(...rows);
      if (rows.length < PAGE_SIZE) return result;
    }
    throw new Error('RANKING_TOO_LARGE');
  }

  async function listGames(signal) {
    try {
      const games = await allRows('jogos', { select: 'id,nome', order: 'id.asc' }, signal);
      if (games.length > 0) {
        return games;
      }
      return [{ id: CONFIG.defaultGameId, nome: 'Show do Milhão' }];
    } catch (err) {
      if (err.name === 'AbortError') throw err;
      console.warn(
        '[ShowDoMilhao][SupabaseJS] Não foi possível listar a tabela "jogos" (' + err.message + '). ' +
        'Utilizando JOGO_ID=' + CONFIG.defaultGameId
      );
      return [{ id: CONFIG.defaultGameId, nome: 'Show do Milhão' }];
    }
  }

  async function listMatches(gameId, signal) {
    const targetGameId = gameId || CONFIG.defaultGameId;
    return allRows('partidas', {
      select: 'id,jogo_id,apelido,valor_ganho,tempo_segundos,acertos,motivo_encerramento,data_hora',
      jogo_id: 'eq.' + targetGameId,
      order: 'valor_ganho.desc,tempo_segundos.asc,data_hora.asc,id.asc'
    }, signal);
  }

  /* Funções do jogo web (definidas em sql/02_jogo_web.sql). */
  const game = Object.freeze({
    start: (apelido, signal) => rpc('web_iniciar_partida', { p_apelido: apelido }, signal),
    state: (id, token, signal) => rpc('web_estado', { p_partida: id, p_token: token }, signal),
    answer: (id, token, letra, signal) => rpc('web_responder', { p_partida: id, p_token: token, p_letra: letra }, signal),
    help: (id, token, tipo, signal) => rpc('web_usar_ajuda', { p_partida: id, p_token: token, p_tipo: tipo }, signal),
    stop: (id, token, signal) => rpc('web_parar', { p_partida: id, p_token: token }, signal)
  });

  global.MilhaoAPI = Object.freeze({
    CONFIG,
    isConfigured,
    listGames,
    listMatches,
    game
  });
})(window);
