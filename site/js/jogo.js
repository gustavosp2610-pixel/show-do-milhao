/* Jogo web do Show do Milhão.
 *
 * Toda a regra do jogo roda no Supabase (funções web_* em sql/02_jogo_web.sql):
 * este arquivo só mostra a pergunta, envia a escolha e desenha a resposta do
 * servidor. A alternativa correta nunca chega ao navegador antes da hora.
 */
(function () {
  'use strict';

  const api = window.MilhaoAPI;
  const root = document.getElementById('jogo');
  if (!api || !root) return;

  const STORAGE_KEY = 'milhao.partida';
  const PREMIOS = [1000, 5000, 10000, 25000, 50000, 100000, 200000, 500000, 1000000];
  const NIVEL = { facil: 'FÁCIL', media: 'MÉDIA', dificil: 'DIFÍCIL' };
  const AJUDA_NOME = { cartas: 'Cartas', universitarios: 'Universitários', plateia: 'Plateia', pulo: 'Pulo' };
  const LETRAS = ['A', 'B', 'C', 'D'];

  const money = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 });
  const $ = id => document.getElementById(id);

  const el = {
    start: $('jogo-inicio'),
    nickname: $('jogo-apelido'),
    play: $('jogo-partida'),
    end: $('jogo-fim'),
    error: $('jogo-erro'),
    hudStage: $('hud-etapa'),
    hudLevel: $('hud-nivel'),
    hudValue: $('hud-valendo'),
    hudSafe: $('hud-garantido'),
    steps: $('jogo-etapas'),
    player: $('jogo-jogador'),
    question: $('jogo-enunciado'),
    answers: $('jogo-alternativas'),
    helpBox: $('jogo-ajuda'),
    feedback: $('jogo-feedback'),
    skips: $('jogo-pulos'),
    stop: $('jogo-parar'),
    confirm: $('jogo-confirmar'),
    again: $('jogo-novo'),
    endIcon: $('fim-icone'),
    endTitle: $('fim-titulo'),
    endText: $('fim-texto'),
    endPrize: $('fim-premio'),
    endHits: $('fim-acertos'),
    endTime: $('fim-tempo')
  };
  const helpButtons = Array.from(root.querySelectorAll('[data-ajuda]'));

  let session = null;   // { id, token }
  let state = null;     // último estado devolvido pelo servidor
  let selected = null;  // letra escolhida antes de confirmar
  let busy = false;
  let stopArmed = null; // timer da confirmação de "Parar"

  /* ---------- Sessão (para continuar a partida se a página recarregar) ---------- */
  function saveSession(value) {
    session = value;
    try {
      if (value) sessionStorage.setItem(STORAGE_KEY, JSON.stringify(value));
      else sessionStorage.removeItem(STORAGE_KEY);
    } catch (_) { /* navegação privada: segue sem salvar */ }
  }

  function loadSession() {
    try {
      const raw = sessionStorage.getItem(STORAGE_KEY);
      const value = raw ? JSON.parse(raw) : null;
      if (value && typeof value.id === 'string' && /^[a-f0-9]{64}$/.test(value.token || '')) return value;
    } catch (_) { /* ignora */ }
    return null;
  }

  /* ---------- Utilidades de interface ---------- */
  function show(view) {
    el.start.hidden = view !== 'start';
    el.play.hidden = view !== 'play';
    el.end.hidden = view !== 'end';
  }

  function showError(text) {
    el.error.textContent = text || '';
    el.error.hidden = !text;
  }

  function setBusy(value) {
    busy = value;
    root.setAttribute('aria-busy', String(value));
    root.querySelectorAll('button, input').forEach(control => {
      if (value) {
        control.dataset.wasDisabled = control.disabled ? '1' : '';
        control.disabled = true;
      } else if (control.dataset.wasDisabled !== undefined) {
        control.disabled = control.dataset.wasDisabled === '1';
        delete control.dataset.wasDisabled;
      }
    });
  }

  function formatTime(seconds) {
    const total = Number(seconds) || 0;
    const min = Math.floor(total / 60);
    const sec = (total % 60).toLocaleString('pt-BR', { maximumFractionDigits: 1 });
    return min > 0 ? `${min}min ${sec}s` : `${sec}s`;
  }

  const wait = ms => new Promise(resolve => setTimeout(resolve, ms));

  function disarmStop() {
    clearTimeout(stopArmed);
    stopArmed = null;
    el.stop.classList.remove('armed');
    el.stop.textContent = 'Parar';
  }

  /* ---------- Desenho da partida ---------- */
  function renderSteps(etapa) {
    el.steps.replaceChildren();
    PREMIOS.forEach((valor, index) => {
      const li = document.createElement('li');
      const numero = index + 1;
      if (numero < etapa) li.className = 'done';
      else if (numero === etapa) li.className = 'current';
      li.textContent = valor >= 1000000 ? '1 mi' : valor / 1000 + ' mil';
      el.steps.append(li);
    });
  }

  function renderAnswers() {
    el.answers.replaceChildren();
    const eliminadas = new Set(state.eliminadas || []);
    LETRAS.forEach(letra => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'answer';
      button.dataset.letra = letra;
      const badge = document.createElement('span');
      badge.className = 'answer-letter';
      badge.textContent = letra;
      const text = document.createElement('span');
      text.className = 'answer-text';
      text.textContent = state.pergunta.alternativas[letra];
      button.append(badge, text);
      if (eliminadas.has(letra)) {
        button.disabled = true;
        button.classList.add('eliminated');
        button.setAttribute('aria-label', `${letra}: eliminada pelas cartas`);
      } else {
        button.setAttribute('aria-pressed', String(selected === letra));
        button.addEventListener('click', () => choose(letra));
      }
      el.answers.append(button);
    });
  }

  function renderHelpResults() {
    const estado = state.ajuda_estado || {};
    el.helpBox.replaceChildren();

    if (estado.cartas) {
      const p = document.createElement('p');
      const elim = estado.cartas.eliminadas || [];
      p.innerHTML = '<strong>Cartas:</strong> ';
      p.append(elim.length
        ? `${elim.length === 1 ? 'eliminou a alternativa' : 'eliminaram as alternativas'} ${elim.join(', ')}.`
        : 'nenhuma alternativa foi eliminada. Que azar!');
      el.helpBox.append(p);
    }

    if (estado.universitarios) {
      const p = document.createElement('p');
      p.innerHTML = '<strong>Universitários:</strong> ';
      const list = document.createElement('span');
      list.className = 'chips';
      (estado.universitarios.palpites || []).forEach((letra, i) => {
        const chip = document.createElement('span');
        chip.className = 'chip';
        chip.textContent = `${i + 1}º → ${letra}`;
        list.append(chip);
      });
      p.append(list);
      el.helpBox.append(p);
    }

    if (estado.plateia) {
      const wrap = document.createElement('div');
      wrap.className = 'audience';
      const title = document.createElement('p');
      title.innerHTML = '<strong>Plateia:</strong> votação em porcentagem';
      wrap.append(title);
      const votos = estado.plateia.votos || {};
      LETRAS.forEach(letra => {
        const pct = Number(votos[letra]) || 0;
        const row = document.createElement('div');
        row.className = 'bar-row';
        const label = document.createElement('span');
        label.textContent = letra;
        const track = document.createElement('span');
        track.className = 'bar-track';
        const fill = document.createElement('span');
        fill.className = 'bar-fill';
        fill.style.width = pct + '%';
        track.append(fill);
        const value = document.createElement('span');
        value.className = 'bar-value';
        value.textContent = pct + '%';
        row.append(label, track, value);
        wrap.append(row);
      });
      el.helpBox.append(wrap);
    }

    el.helpBox.hidden = el.helpBox.childElementCount === 0;
  }

  function renderHelps() {
    const ajudas = state.ajudas || {};
    helpButtons.forEach(button => {
      const tipo = button.dataset.ajuda;
      button.disabled = !ajudas[tipo];
      button.classList.toggle('used', !ajudas[tipo]);
    });
    el.skips.textContent = String(ajudas.pulos_restantes ?? 0);
  }

  function renderPlay() {
    disarmStop();
    el.hudStage.textContent = `${state.etapa}/${state.total_etapas || 9}`;
    el.hudLevel.textContent = NIVEL[state.dificuldade] || '';
    el.hudLevel.dataset.nivel = state.dificuldade || '';
    el.hudValue.textContent = money.format(Number(state.valendo));
    el.hudSafe.textContent = money.format(Number(state.valor_ganho));
    el.player.textContent = `Jogador: ${state.apelido}`;
    el.question.textContent = state.pergunta.enunciado;
    el.feedback.textContent = '';
    el.feedback.className = 'feedback';
    renderSteps(state.etapa);
    renderAnswers();
    renderHelpResults();
    renderHelps();
    el.confirm.disabled = !selected;
    el.confirm.textContent = selected ? `Confirmar ${selected}` : 'Confirmar resposta';
    el.stop.disabled = false;
    show('play');
  }

  function renderEnd() {
    const premio = Number(state.valor_ganho);
    const status = state.status;
    el.endIcon.textContent = status === 'vitoria' ? '★' : status === 'erro' ? '✕' : '◇';
    el.end.dataset.status = status;

    if (status === 'vitoria') {
      el.endTitle.textContent = 'Você ganhou o milhão!';
      el.endText.textContent = `Parabéns, ${state.apelido}! Acertou as nove perguntas.`;
    } else if (status === 'erro') {
      const certa = state.correta;
      const texto = certa && state.pergunta ? state.pergunta.alternativas[certa] : '';
      el.endTitle.textContent = 'Resposta errada.';
      el.endText.textContent = certa
        ? `A resposta certa era ${certa}: ${texto}. Você leva o prêmio do último acerto.`
        : 'Você leva o prêmio do último acerto.';
    } else {
      el.endTitle.textContent = 'Você parou.';
      el.endText.textContent = `Boa decisão, ${state.apelido}. O prêmio do último acerto é seu.`;
    }

    el.endPrize.textContent = money.format(premio);
    el.endHits.textContent = `${state.acertos}/9`;
    el.endTime.textContent = state.tempo_segundos != null ? formatTime(state.tempo_segundos) : '—';
    show('end');
    el.again.focus();
    document.dispatchEvent(new CustomEvent('milhao:partida-finalizada', { detail: { partida_id: state.partida_id } }));
  }

  function render() {
    if (!state) {
      show('start');
      return;
    }
    if (state.status === 'em_andamento') renderPlay();
    else renderEnd();
  }

  /* ---------- Ações ---------- */
  function handleFailure(error) {
    if (error && error.name === 'AbortError') return;
    console.error('[ShowDoMilhao][JogoJS]', error);
    if (error && (error.code === 'PARTIDA_INVALIDA' || error.code === 'PARTIDA_ENCERRADA')) {
      saveSession(null);
      state = null;
      selected = null;
      show('start');
    }
    showError((error && error.message) || 'Algo deu errado. Tente de novo.');
  }

  async function call(action) {
    if (busy) return null;
    showError('');
    setBusy(true);
    try {
      return await action();
    } catch (error) {
      handleFailure(error);
      return null;
    } finally {
      setBusy(false);
    }
  }

  async function start(event) {
    event.preventDefault();
    const apelido = el.nickname.value.trim();
    if (!apelido) {
      showError('Digite um apelido para começar.');
      el.nickname.focus();
      return;
    }
    const result = await call(() => api.game.start(apelido));
    if (!result) return;
    saveSession({ id: result.partida_id, token: result.token });
    delete result.token;
    state = result;
    selected = null;
    render();
    el.question.focus();
  }

  function choose(letra) {
    if (busy || !state || state.status !== 'em_andamento') return;
    selected = letra;
    disarmStop();
    el.answers.querySelectorAll('.answer').forEach(button => {
      if (!button.disabled) button.setAttribute('aria-pressed', String(button.dataset.letra === letra));
    });
    el.confirm.disabled = false;
    el.confirm.textContent = `Confirmar ${letra}`;
  }

  async function confirm() {
    if (!selected || !session) return;
    const letra = selected;
    disarmStop();
    const result = await call(() => api.game.answer(session.id, session.token, letra));
    if (!result) return;

    const chosen = el.answers.querySelector(`[data-letra="${letra}"]`);
    const acertou = result.ultima_resposta && result.ultima_resposta.acertou;
    root.classList.add('revealing');
    el.answers.querySelectorAll('.answer').forEach(button => { button.disabled = true; });
    el.confirm.disabled = true;
    el.stop.disabled = true;
    helpButtons.forEach(button => { button.disabled = true; });

    if (acertou) {
      if (chosen) chosen.classList.add('is-correct');
      el.feedback.textContent = `Certa resposta! Você já tem ${money.format(Number(result.valor_ganho))}.`;
      el.feedback.className = 'feedback good';
    } else {
      if (chosen) chosen.classList.add('is-wrong');
      const right = el.answers.querySelector(`[data-letra="${result.correta}"]`);
      if (right) right.classList.add('is-correct');
      el.feedback.textContent = `Que pena! A certa era ${result.correta}.`;
      el.feedback.className = 'feedback bad';
    }

    await wait(acertou ? 1200 : 2200);
    root.classList.remove('revealing');
    state = result;
    selected = null;
    if (state.status !== 'em_andamento') saveSession(null);
    render();
    if (state.status === 'em_andamento') el.question.focus();
  }

  async function useHelp(tipo) {
    if (!session || !state || state.status !== 'em_andamento') return;
    disarmStop();
    const result = await call(() => api.game.help(session.id, session.token, tipo));
    if (!result) return;
    state = result;
    if (tipo === 'pulo') {
      selected = null;
      render();
      el.feedback.textContent = 'Pergunta trocada! O prêmio continua o mesmo.';
      el.feedback.className = 'feedback';
      el.question.focus();
      return;
    }
    if (selected && (state.eliminadas || []).includes(selected)) selected = null;
    render();
    el.helpBox.focus();
  }

  async function stop() {
    if (!session || !state || state.status !== 'em_andamento') return;
    if (!stopArmed) {
      el.stop.classList.add('armed');
      el.stop.textContent = `Parar e levar ${money.format(Number(state.valor_ganho))}?`;
      stopArmed = setTimeout(disarmStop, 5000);
      return;
    }
    disarmStop();
    const result = await call(() => api.game.stop(session.id, session.token));
    if (!result) return;
    state = result;
    selected = null;
    saveSession(null);
    render();
  }

  function newGame() {
    state = null;
    selected = null;
    saveSession(null);
    showError('');
    show('start');
    el.nickname.focus();
  }

  async function resume() {
    const saved = loadSession();
    if (!saved || !api.isConfigured()) return;
    session = saved;
    setBusy(true);
    try {
      const result = await api.game.state(saved.id, saved.token);
      if (result.status === 'em_andamento') state = result;
      else saveSession(null);
    } catch (error) {
      if (error.code === 'PARTIDA_INVALIDA') saveSession(null);
      else showError('Não foi possível retomar sua partida: ' + error.message);
    } finally {
      setBusy(false);
    }
    render();
  }

  /* ---------- Eventos ---------- */
  el.start.addEventListener('submit', start);
  el.confirm.addEventListener('click', confirm);
  el.stop.addEventListener('click', stop);
  el.again.addEventListener('click', newGame);
  helpButtons.forEach(button => button.addEventListener('click', () => useHelp(button.dataset.ajuda)));

  if (!api.isConfigured()) {
    showError('O jogo aguarda a configuração do Supabase em site/js/supabase.js.');
    el.start.querySelector('button').disabled = true;
  } else {
    resume();
  }
})();
