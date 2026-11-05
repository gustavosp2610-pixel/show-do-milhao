/* Módulo de classificação, desempate, deduplicação por apelido e renderização do Ranking Top 10. */
(function (global) {
  'use strict';

  const money = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' });
  const date = new Intl.DateTimeFormat('pt-BR', {
    dateStyle: 'short',
    timeStyle: 'short',
    timeZone: 'America/Sao_Paulo'
  });

  const compareText = (a, b) => (a < b ? -1 : a > b ? 1 : 0);

  /**
   * Critérios oficiais de desempate:
   * 1º Maior valor_ganho (decrescente)
   * 2º Menor tempo_segundos (crescente)
   * 3º Data_hora mais antiga (crescente)
   * 4º ID da partida (crescente)
   */
  function compare(a, b) {
    return (
      Number(b.valor_ganho) - Number(a.valor_ganho) ||
      Number(a.tempo_segundos) - Number(b.tempo_segundos) ||
      Date.parse(a.data_hora) - Date.parse(b.data_hora) ||
      compareText(String(a.id), String(b.id))
    );
  }

  /**
   * Filtra partidas válidas do jogo selecionado, aplica os 4 critérios de desempate,
   * mantém apenas a melhor partida de cada apelido (sem duplicar jogador) e limita ao Top 10.
   */
  function topTen(matches, gameId) {
    const valid = matches.filter(row => {
      const mesmoJogo = String(row.jogo_id) === String(gameId);
      const idValido = row.id != null && String(row.id).trim() !== '';
      const apelidoValido = typeof row.apelido === 'string' && row.apelido.trim().length > 0;
      const valorNum = Number(row.valor_ganho);
      const valorValido = row.valor_ganho != null && row.valor_ganho !== '' && Number.isFinite(valorNum) && valorNum >= 0;
      const tempoNum = Number(row.tempo_segundos);
      const tempoValido = row.tempo_segundos != null && row.tempo_segundos !== '' && Number.isFinite(tempoNum) && tempoNum >= 0;
      const dataValida = Number.isFinite(Date.parse(row.data_hora));

      const registroOk = mesmoJogo && idValido && apelidoValido && valorValido && tempoValido && dataValida;
      if (!registroOk) {
        console.warn('[ShowDoMilhao][RankingJS] Partida ignorada na validação de contrato:', row);
      }
      return registroOk;
    });

    const ordenadas = valid.sort(compare);
    const seen = new Set();

    const deduplicadasTop10 = ordenadas.filter(row => {
      // Normaliza apelido (NFC + trim) para garantir apenas a melhor partida de cada jogador
      const key = row.apelido.trim().normalize('NFC');
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    }).slice(0, 10);

    console.log(
      `[ShowDoMilhao][RankingJS] Jogo ${gameId}: ${matches.length} partida(s) bruta(s) -> ` +
      `${valid.length} válida(s) -> ${deduplicadasTop10.length} no Top 10 deduplicado:`,
      deduplicadasTop10
    );

    return deduplicadasTop10;
  }

  function render(body, rows, gameName) {
    body.replaceChildren();
    rows.forEach((row, index) => {
      const tr = document.createElement('tr');
      if (index < 3) tr.className = 'top-' + (index + 1);

      const place = document.createElement('td');
      const badge = document.createElement('span');
      badge.className = 'place';
      badge.textContent = (index + 1) + 'º';
      place.append(badge);
      tr.append(place);

      const seconds = Number(row.tempo_segundos);
      const duration =
        Math.floor(seconds / 60) +
        'min ' +
        (seconds % 60).toLocaleString('pt-BR', { maximumFractionDigits: 2 }) +
        's';

      [
        gameName,
        row.apelido,
        money.format(Number(row.valor_ganho)),
        duration,
        date.format(new Date(row.data_hora))
      ].forEach(value => {
        const td = document.createElement('td');
        td.textContent = value;
        tr.append(td);
      });

      body.append(tr);
    });
  }

  global.MilhaoRanking = Object.freeze({ topTen, compare, render });
})(window);
