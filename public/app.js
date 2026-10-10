const app = document.querySelector('#app');
let team = 1;
let current = null, screen = 'home', selectedClue = null, receivedAt = 0, busy = false;
let portalRoundId = null, finalAttemptEditing = false;
let gmPage = 'overview';
let gmCodeDrafts = {1: '', 2: ''}, gmCodeVisible = {1: false, 2: false};
let gmDashboard = null, gmEvents = {1: [], 2: []}, gmHasMore = {1: false, 2: false}, gmEventVersion = {1: 0, 2: 0}, gmLoading = false, gmNotice = '', gmNoticeUntil = 0, gmTeamCodes = {1: false, 2: false};
let audioContext, soundOn = false, soundNodes = [];
const backgroundMusic = new Audio('/media/background.mp3');
backgroundMusic.loop = true;
backgroundMusic.volume = 0.24;
const esc = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const formatTime = seconds => `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`;
function home(notice = '') {
  stopBackgroundMusic();
  resetSuspense();
  const url = new URL(window.location.href);
  url.searchParams.delete('team');
  history.replaceState(null, '', `${url.pathname}${url.search}${url.hash}`);
  screen = 'home';
  app.innerHTML = `<section class="hero"><div><p class="eyebrow">AN EVENING TO REMEMBER. A SECRET TO UNCOVER.</p><h1>The Last<br>Reunion <em>Dinner.</em></h1><p class="description">Old friends. Unfinished stories. One final toast.<br>A reunion takes a deadly turn when a classmate collapses at dinner. Everyone has a motive. Can your team find the truth?</p><div class="stats"><div class="stat"><strong>30</strong><span>MINUTES</span></div><div class="stat"><strong>05</strong><span>HIDDEN CLUES</span></div><div class="stat"><strong>02</strong><span>TEAMS</span></div></div><p class="eyebrow" style="margin-bottom:10px">CHOOSE YOUR INVESTIGATION</p><div class="team-choose game-choices"><button class="team-button" data-team="1">Game 1 <span>TEAM ONE · THE NIGHT OWLS</span></button><button class="team-button" data-team="2">Game 2 <span>TEAM TWO · THE SILENT WITNESSES</span></button></div><p class="small-note">Each team has a separate case file and timer.</p><p id="home-error" class="error" role="status"></p><button id="game-master-login" class="secondary gm-login-link">Game master login</button></div><div class="hero-image"><span class="photo-label">THE SCENE · REUNION NIGHT</span><div class="photo-caption"><span>TABLE FOR FRIENDS. ROOM FOR SECRETS.</span><p>“Some things should have<br>stayed in the past.”</p></div></div></section><section><div class="section-head"><h2>Your evening, in three acts.</h2><p>Trust the evidence. Question everyone.</p></div><div class="steps"><div class="step"><span class="num">01</span><div><h3>Step into the story</h3><p>Meet the people at the table. Old friendships hide complicated motives.</p></div></div><div class="step"><span class="num">02</span><div><h3>Follow the evidence</h3><p>Answer five questions to unlock numbered clues, hidden messages, and witness accounts.</p></div></div><div class="step"><span class="num">03</span><div><h3>Make your accusation</h3><p>Name the killer, the murder weapon, and the motive before time runs out.</p></div></div></div></section>`;
  app.querySelectorAll('[data-team]').forEach(button => button.onclick = () => enterTeam(Number(button.dataset.team)));
  document.querySelector('#home-error').textContent = notice;
  document.querySelector('#game-master-login').onclick = openGameMasterDashboard;
}
async function enterTeam(number) {
  team = number;
  const url = new URL(window.location.href);
  url.searchParams.set('team', String(team));
  history.replaceState(null, '', `${url.pathname}${url.search}${url.hash}`);
  selectedClue = null;
  try { await refresh(); portalRoundId = current.round_id; finalAttemptEditing = false; if (current.started) {screen = 'game'; renderGame();} else brief(); }
  catch (error) {
    if (error.status === 401) return teamCodePrompt();
    if (error.status === 409) return teamCodePrompt('The Game Master needs to set this team’s access code before play.');
    home(); document.querySelector('#home-error').textContent = 'Cannot reach the game server. Please try again.';
  }
}
function teamCodePrompt(notice = '') {
  screen = 'team-login';
  stopBackgroundMusic();
  app.innerHTML = `<section class="gm-auth team-auth"><div class="card"><p class="eyebrow">TEAM ${team} ACCESS</p><h1>${team === 1 ? 'The Night Owls' : 'The Silent Witnesses'}</h1><p>Enter the access code provided by your Game Master to open your team’s case file.</p><form id="team-login-form" autocomplete="off"><label class="answer-label" for="team-code">TEAM ${team} ACCESS CODE</label><input id="team-code" name="code" type="password" autocomplete="off" minlength="8" maxlength="200" required><button class="primary" type="submit">Enter team portal <span aria-hidden="true">↗</span></button><p id="team-login-error" class="error" role="status" aria-live="polite">${esc(notice)}</p></form><button id="team-login-back" class="subtle-link">Back to game selection</button></div></section>`;
  document.querySelector('#team-login-back').onclick = home;
  document.querySelector('#team-login-form').onsubmit = async event => {
    event.preventDefault();
    const button = event.submitter;
    button.disabled = true;
    try {
      const response = await fetch('/api/team/login', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({team, code:document.querySelector('#team-code').value})});
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || 'Could not verify that access code.');
      document.querySelector('#team-code').value = '';
      await refresh();
      portalRoundId = current.round_id;
      finalAttemptEditing = false;
      if (current.started) {screen = 'game'; renderGame();} else brief();
    } catch (error) {
      const message = document.querySelector('#team-login-error');
      if (message) message.textContent = error.message;
      button.disabled = false;
    }
  };
  document.querySelector('#team-code').focus();
}
function openGameMaster() {
  screen = 'gm-login';
  app.innerHTML = `<section class="gm-auth"><div class="card"><p class="eyebrow">GAME MASTER ACCESS</p><h1>Welcome back.</h1><p>Sign in to monitor both teams and manage rounds.</p><form id="gm-login-form" autocomplete="off"><label class="answer-label" for="gm-password">GAME MASTER PASSWORD</label><input id="gm-password" name="password" type="password" autocomplete="off" required><button class="primary" type="submit">Log in <span aria-hidden="true">↗</span></button><p id="gm-login-error" class="error" role="status" aria-live="polite"></p></form><button id="gm-back" class="subtle-link">Back to game selection</button></div></section>`;
  document.querySelector('#gm-back').onclick = home;
  document.querySelector('#gm-login-form').onsubmit = async event => {
    event.preventDefault();
    const button = event.submitter;
    button.disabled = true;
    try {
      const response = await fetch('/api/gm/login', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({password:document.querySelector('#gm-password').value})});
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || 'Sign-in failed.');
      gmEvents = {1: [], 2: []}; gmDashboard = null; gmHasMore = {1: false, 2: false}; gmNotice = '';
      gmPage = 'overview';
      gmCodeDrafts = {1: '', 2: ''}; gmCodeVisible = {1: false, 2: false};
      await loadDashboard(true);
    } catch (error) {
      const message = document.querySelector('#gm-login-error');
      if (message) message.textContent = error.message;
      button.disabled = false;
    }
  };
  document.querySelector('#gm-password').focus();
}
async function gmFetch(url, options = {}) {
  const response = await fetch(url, {...options, cache:'no-store'});
  const result = await response.json();
  if (!response.ok) throw Object.assign(new Error(result.error || 'Game master request failed.'), {status:response.status});
  return result;
}
async function openGameMasterDashboard() {
  openGameMaster();
}
async function loadDashboard(initial = false) {
  if (gmLoading) return;
  gmLoading = true;
  const eventVersion = {...gmEventVersion};
  try {
    const [dashboard, teamOnePage, teamTwoPage, teamCodes] = await Promise.all([
      gmFetch('/api/gm/dashboard'),
      gmFetch('/api/gm/events?team=1&limit=30'),
      gmFetch('/api/gm/events?team=2&limit=30'),
      gmFetch('/api/gm/team-codes'),
    ]);
    if (gmDashboard && gmDashboard.round_id !== dashboard.round_id) {
      gmEvents = {1: [], 2: []};
      gmHasMore = {1: false, 2: false};
    }
    gmDashboard = dashboard;
    gmTeamCodes = Object.fromEntries(teamCodes.teams.map(item => [item.team, item.configured]));
    for (const [teamId, page] of [[1, teamOnePage], [2, teamTwoPage]]) {
      if (gmEventVersion[teamId] !== eventVersion[teamId]) continue;
      const alreadyLoadedEvents = gmEvents[teamId].length > 0;
      const merged = new Map([...page.events, ...gmEvents[teamId]].map(item => [item.id, item]));
      gmEvents[teamId] = [...merged.values()].sort((a,b) => b.id-a.id);
      if (!alreadyLoadedEvents) gmHasMore[teamId] = page.has_more;
    }
    if (Date.now() >= gmNoticeUntil) gmNotice = '';
    if (initial || (screen === 'gm-dashboard' && gmPage === 'overview')) renderGameMasterDashboard();
  } catch (error) {
    if (error.status === 401 || error.status === 503) {
      openGameMaster();
      const message = document.querySelector('#gm-login-error');
      if (message) message.textContent = error.message;
    } else {
      gmNotice = error.message;
      if (screen === 'gm-dashboard' && gmPage === 'overview') renderGameMasterDashboard();
    }
  } finally { gmLoading = false; }
}function renderGameMasterDashboard() {
  if (!gmDashboard) return;
  document.querySelectorAll('[data-team-code-form]').forEach(form => {
    const teamId = Number(form.dataset.teamCodeForm);
    const input = form.querySelector('input');
    if (input) {
      gmCodeDrafts[teamId] = input.value;
      gmCodeVisible[teamId] = input.type === 'text';
    }
  });
  stopBackgroundMusic();
  resetSuspense();
  screen = 'gm-dashboard';
  app.innerHTML = `<section class="dashboard-head"><div><p class="eyebrow">GAME MASTER · LIVE MONITOR</p><h1>Game Master Dashboard</h1><p>Each team's 30-minute timer starts when that team enters its investigation.</p></div><div class="dashboard-actions"><button id="new-round" class="primary">Start new round</button><button id="gm-logout" class="subtle-link">Log out</button></div></section>${gmNotice ? `<p class="error" role="status">${esc(gmNotice)}</p>` : ''}<nav class="dashboard-nav" aria-label="Game Master pages"><button class="secondary ${gmPage === 'overview' ? 'active' : ''}" type="button" data-gm-page="overview" ${gmPage === 'overview' ? 'aria-current="page"' : ''}>Team overview</button><button class="secondary ${gmPage === 'access-codes' ? 'active' : ''}" type="button" data-gm-page="access-codes" ${gmPage === 'access-codes' ? 'aria-current="page"' : ''}>Team access codes</button></nav>${gmPage === 'overview' ? `<section class="dashboard-teams" aria-label="Team progress">${gmDashboard.teams.map(renderTeamCard).join('')}</section><section class="activity-panel"><div class="activity-heading"><div><p class="eyebrow">ROUND ACTIVITY</p><h2>Team activity logs</h2></div><button id="refresh-dashboard" class="secondary">Refresh</button></div><div class="activity-columns">${[1,2].map(renderTeamActivity).join('')}</div></section>` : renderTeamAccessCodes()}`;
  document.querySelector('#gm-logout').onclick = logoutGameMaster;
  document.querySelector('#refresh-dashboard')?.addEventListener('click', () => loadDashboard(true));
  document.querySelector('#new-round').onclick = startNewRound;
  document.querySelectorAll('[data-gm-page]').forEach(button => {
    button.onclick = () => {gmPage = button.dataset.gmPage; renderGameMasterDashboard();};
  });
  document.querySelectorAll('[data-team-code-form]').forEach(form => {
    const teamId = Number(form.dataset.teamCodeForm);
    const input = form.querySelector('input');
    const toggle = form.querySelector('[data-toggle-team-code]');
    input.value = gmCodeDrafts[teamId] || '';
    input.type = gmCodeVisible[teamId] ? 'text' : 'password';
    toggle.textContent = gmCodeVisible[teamId] ? 'Hide' : 'Show';
    toggle.setAttribute('aria-pressed', String(Boolean(gmCodeVisible[teamId])));
    toggle.setAttribute('aria-label', `${gmCodeVisible[teamId] ? 'Hide' : 'Show'} Team ${teamId} access code`);
    input.addEventListener('input', () => {gmCodeDrafts[teamId] = input.value;});
    form.onsubmit = async event => {
      event.preventDefault();
      const button = form.querySelector('[type="submit"]');
      const message = form.querySelector('[role="status"]');
      button.disabled = true;
      try {
        await gmFetch('/api/gm/team-codes', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({team:teamId, code:input.value})});
        gmTeamCodes[teamId] = true;
        gmCodeVisible[teamId] = false;
        input.type = 'password';
        gmNotice = `Team ${teamId} access code saved. Existing sessions for that team must sign in again.`;
        gmNoticeUntil = Date.now() + 10000;
        renderGameMasterDashboard();
      } catch (error) {
        message.textContent = error.message;
        button.disabled = false;
      }
    };
  });
  document.querySelectorAll('[data-toggle-team-code]').forEach(button => {
    button.onclick = async () => {
      const input = document.getElementById(button.dataset.toggleTeamCode);
      const teamId = Number(button.dataset.team);
      if (input.type === 'password' && gmTeamCodes[teamId] && !gmCodeDrafts[teamId]) {
        button.disabled = true;
        try {
          const result = await gmFetch(`/api/gm/team-codes/reveal?team=${teamId}`);
          gmCodeDrafts[teamId] = result.code;
          input.value = result.code;
        } catch (error) {
          const message = button.closest('form').querySelector('[role="status"]');
          message.textContent = error.message;
          button.disabled = false;
          return;
        }
        button.disabled = false;
      }
      const showing = input.type === 'password';
      input.type = showing ? 'text' : 'password';
      gmCodeVisible[teamId] = showing;
      button.textContent = showing ? 'Hide' : 'Show';
      button.setAttribute('aria-pressed', String(showing));
      button.setAttribute('aria-label', `${showing ? 'Hide' : 'Show'} Team ${button.dataset.team} access code`);
    };
  });
  document.querySelectorAll('[data-load-older]').forEach(button => {
    button.onclick = () => loadOlderEvents(Number(button.dataset.loadOlder));
  });
  document.querySelectorAll('[data-delete-log]').forEach(button => {
    button.onclick = () => clearTeamActivity(Number(button.dataset.deleteLog));
  });
}
function renderTeamAccessCodes() {
  return `<section class="team-code-panel"><div class="activity-heading"><div><p class="eyebrow">TEAM SECURITY</p><h2>Team access codes</h2><p>Set a separate code for each team and share it with them privately. Saving a new code signs that team out.</p></div></div><div class="team-code-grid">${[1,2].map(teamId => `<form class="team-code-card" data-team-code-form="${teamId}" autocomplete="off"><div class="team-code-heading"><h3>Team ${teamId === 1 ? 'One · The Night Owls' : 'Two · The Silent Witnesses'}</h3><span class="team-status ${gmTeamCodes[teamId] ? 'status-live' : 'status-waiting'}">${gmTeamCodes[teamId] ? 'Code set' : 'Not set'}</span></div><label class="answer-label" for="team-code-${teamId}">${gmTeamCodes[teamId] ? 'REPLACE TEAM ACCESS CODE' : 'CREATE ACCESS CODE'}</label><div class="team-code-input-row"><input id="team-code-${teamId}" type="password" minlength="8" maxlength="200" autocomplete="off" required placeholder="${gmTeamCodes[teamId] ? '••••••••' : 'At least 8 characters'}"><button class="secondary team-code-toggle" type="button" data-toggle-team-code="team-code-${teamId}" data-team="${teamId}" aria-label="Show Team ${teamId} access code" aria-pressed="false">Show</button></div><button class="secondary" type="submit">${gmTeamCodes[teamId] ? 'Replace code' : 'Save code'}</button><p class="small-note">After saving, Show can reveal the code during this dashboard session. On a later login, enter a replacement to view it again. Replacing a code signs out this team.</p><p class="error" role="status" aria-live="polite"></p></form>`).join('')}</div></section>`;
}
function renderTeamActivity(teamId) {
  const label = teamId === 1 ? 'Team One' : 'Team Two';
  const events = gmEvents[teamId];
  return `<section class="activity-column" aria-label="${label} activity"><div class="activity-column-heading"><h3>${label} Activity</h3><div class="activity-column-actions"><span>${events.length} events</span><button class="subtle-link delete-team-log" data-delete-log="${teamId}" ${events.length ? '' : 'disabled'} aria-label="Delete ${label} activity log">Delete log</button></div></div>${events.length ? `<ol class="activity-list">${events.map(renderEvent).join('')}</ol>` : '<p class="empty">No activity yet. Team actions will appear here.</p>'}${gmHasMore[teamId] ? `<button class="secondary load-older" data-load-older="${teamId}">Load older ${label.toLowerCase()} activity</button>` : ''}</section>`;
}function renderTeamCard(teamState) {
  const status = teamState.ended ? (teamState.expired ? 'Time expired' : 'Case finished') : teamState.started ? 'Investigating' : 'Not started';
  const statusClass = teamState.ended ? 'status-done' : teamState.started ? 'status-live' : 'status-waiting';
  const accusation = teamState.submission ? `<div class="team-accusation"><strong>Final accusation</strong><span>${esc(teamState.submission.killer)} · ${esc(teamState.submission.weapon)} · ${esc(teamState.submission.motive)}</span><em>${teamState.correct ? 'Correct' : 'Incorrect'}</em></div>` : '';
  return `<article class="team-monitor"><div class="team-monitor-head"><div><p class="eyebrow">GAME ${teamState.team}</p><h2>Team ${teamState.team === 1 ? 'One · The Night Owls' : 'Two · The Silent Witnesses'}</h2></div><span class="team-status ${statusClass}">${status}</span></div><div class="team-metrics"><div><span>CLUES RECOVERED</span><strong>${teamState.progress}/5</strong></div><div><span>TIME REMAINING</span><strong>${teamState.started ? formatTime(Math.ceil(teamState.remaining)) : '30:00'}</strong></div><div><span>WRONG FINAL ANSWERS</span><strong>${teamState.wrong_attempts}</strong></div></div><div class="progress-track" role="progressbar" aria-label="Team ${teamState.team} clue progress" aria-valuemin="0" aria-valuemax="5" aria-valuenow="${teamState.progress}"><span style="width:${teamState.progress*20}%"></span></div>${accusation}</article>`;
}
function renderEvent(event) {
  const teamLabel = event.team ? `Game ${event.team}` : 'Game master';
  const details = event.payload && event.type === 'answer_attempt' ? `<p>Answer submitted: “${esc(event.payload.answer || '')}”</p>` :
    event.payload && ['final_attempt','final_accusation'].includes(event.type) ? `<p>${esc(event.payload.killer)} · ${esc(event.payload.weapon)} · ${esc(event.payload.motive)}${event.payload.penalty_seconds ? ` · ${Math.ceil(event.payload.penalty_seconds/60)} minutes deducted` : ''}</p>` : '';
  const outcome = event.correct === null ? '' : `<span class="event-outcome ${event.correct ? 'outcome-correct' : 'outcome-wrong'}">${event.correct ? 'Correct' : 'Incorrect'}</span>`;
  return `<li class="activity-item"><span class="event-marker ${event.correct === false ? 'marker-wrong' : ''}" aria-hidden="true"></span><div class="activity-copy"><div class="event-meta"><strong>Round ${event.round_id} · ${teamLabel} · ${esc(event.type.replaceAll('_',' '))}</strong><time datetime="${esc(event.timestamp)}">${new Date(event.timestamp).toLocaleString()}</time>${outcome}</div><p>${esc(event.summary)}</p>${details}</div></li>`;
}
async function loadOlderEvents(teamId) {
  const events = gmEvents[teamId];
  if (!events.length) return;
  const eventVersion = gmEventVersion[teamId];
  const cursor = Math.min(...events.map(event => event.id));
  try {
    const page = await gmFetch(`/api/gm/events?team=${teamId}&limit=30&before=${cursor}`);
    if (gmEventVersion[teamId] !== eventVersion) return;
    const merged = new Map([...events, ...page.events].map(item => [item.id, item]));
    gmEvents[teamId] = [...merged.values()].sort((a,b) => b.id-a.id);
    gmHasMore[teamId] = page.has_more;
    renderGameMasterDashboard();
  } catch (error) {gmNotice = error.message; renderGameMasterDashboard();}
}
async function clearTeamActivity(teamId) {
  const label = teamId === 1 ? 'Team One' : 'Team Two';
  if (!window.confirm(`Permanently delete ${label}'s activity log? Team progress, answers, results, and timer will remain unchanged.`)) return;
  const button = document.querySelector(`[data-delete-log="${teamId}"]`);
  if (button) button.disabled = true;
  try {
    await gmFetch('/api/gm/clear-team-events', {
      method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({team:teamId}),
    });
    gmEventVersion[teamId]++;
    gmEvents[teamId] = [];
    gmHasMore[teamId] = false;
    gmNotice = '';
    renderGameMasterDashboard();
  } catch (error) {
    gmNotice = error.message;
    renderGameMasterDashboard();
  }
}
async function startNewRound() {
  if (!window.confirm("Start a new round? This permanently clears both teams' activity logs, progress, answers, results, penalties, and timers.")) return;
  const button = document.querySelector('#new-round');
  button.disabled = true;
  try {
    const result = await gmFetch('/api/gm/new-round', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'});
    gmEvents = {1: [], 2: []}; gmDashboard = null; gmHasMore = {1: false, 2: false}; gmEventVersion[1]++; gmEventVersion[2]++; gmNotice = result.message;
    await loadDashboard(true);
  } catch (error) {gmNotice = error.message; if (screen === 'gm-dashboard') renderGameMasterDashboard();}
}
async function logoutGameMaster() {
  try {await gmFetch('/api/gm/logout', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'});} catch {}
  gmDashboard = null; gmEvents = {1: [], 2: []}; gmHasMore = {1: false, 2: false};
  gmCodeDrafts = {1: '', 2: ''}; gmCodeVisible = {1: false, 2: false}; gmPage = 'overview'; home();
}
function brief() {
  screen = 'brief';
  resetSuspense();
  app.innerHTML = `<section class="brief"><p class="eyebrow">TEAM ${team} · YOUR CASE BRIEFING</p><div class="card"><p class="eyebrow">REUNION MURDER MYSTERY</p><h2>A toast to the past.<br>A night with no tomorrow.</h2><p>A group of former high-school classmates reunites for dinner after many years. One of them, now a famous vlogger and successful entrepreneur, returns to reconnect with old friends.</p><p>Keep the source articles available: they contain the answers to the five questions. Answers ignore capitalization and surrounding spaces. Clues unlock in order; revisit them in your case file anytime.</p><button id="start" class="primary">Start the 30-minute investigation ↗</button><p id="start-error" class="error" role="status"></p><button id="back" class="subtle-link">Back to team selection</button></div></section>`;
  document.querySelector('#back').onclick = home;
  document.querySelector('#start').onclick = async e => {
    e.currentTarget.disabled = true;
    startBackgroundMusic();
    try { await action('/api/start', {}); screen = 'game'; renderGame(); }
    catch (error) {stopBackgroundMusic(); document.querySelector('#start-error').textContent = error.message; document.querySelector('#start').disabled = false;}
  };
}
async function refresh() {
  const response = await fetch(`/api/state?team=${team}`, {cache:'no-store'});
  const result = await response.json();
  if (!response.ok) throw Object.assign(new Error(result.error || 'The game server could not be reached.'), {status:response.status});
  current = result; receivedAt = Date.now();
}
async function action(url, data) {
  const response = await fetch(url, {method:'POST', headers:{'Content-Type':'application/json'},body:JSON.stringify({team,round_id:current?.round_id,...data})});
  current = await response.json(); receivedAt = Date.now();
  if (!response.ok) throw new Error(current.error || 'Please try again.');
}
function remaining() {return current ? Math.max(0, current.remaining - (Date.now() - receivedAt) / 1000) : 1800;}
function renderGame() {
  if (!current) return;
  screen = 'game';
  document.body.classList.add('investigation-active');
  updateSuspense();
  const elapsed = current.ended && current.elapsed != null ? `<span>CASE CLOSED · ${formatTime(current.elapsed)} ELAPSED</span>` : '<span>TIME TO FIND THE TRUTH</span>';
  app.innerHTML = `<div class="case-top"><div><p class="eyebrow">TEAM ${team === 1 ? 'ONE · THE NIGHT OWLS' : 'TWO · THE SILENT WITNESSES'}</p><h1>The Last Reunion Dinner</h1></div><div class="timer"><strong id="clock">${formatTime(Math.ceil(remaining()))}</strong>${elapsed}</div></div><div class="case-grid"><aside class="case-sidebar"><h2>YOUR CASE FILE</h2>${[1,2,3,4,5].map(n => `<button class="clue-tab ${selectedClue === n ? 'active' : ''}" data-clue="${n}" ${n > current.progress ? 'disabled' : ''}><b>${String(n).padStart(2,'0')}</b><span>Clue ${n}</span> ${n <= current.progress ? '✓' : '○'}</button>`).join('')}<button class="clue-tab" id="investigation" ${current.progress < 5 && !current.ended ? 'disabled aria-label="Final accusation locked until all five clues are recovered"' : ''}><b>06</b><span>${current.ended ? 'The truth' : current.progress === 5 ? 'Final accusation' : `Locked · ${current.progress}/5 clues`}</span> →</button><p class="sidebar-note">${current.progress} of 5 clues recovered.<br>Compare the evidence before making your final accusation.</p><button id="switch" class="subtle-link">Return to team selection</button></aside><section class="card" id="case-content"></section></div><p id="connection" role="status"></p>`;
  app.querySelectorAll('[data-clue]').forEach(b => b.onclick = () => {selectedClue = Number(b.dataset.clue); renderGame();});
  document.querySelector('#investigation').onclick = () => {selectedClue = null; renderGame();};
  document.querySelector('#switch').onclick = () => {selectedClue = null; home();};
  const content = document.querySelector('#case-content');
  if (selectedClue && selectedClue <= current.progress) evidence(content);
  else if (current.ended) reveal(content);
  else if (current.progress === 5) finalForm(content);
  else question(content);
}
function question(content) {
  content.innerHTML = `<p class="eyebrow">CLUE ${String(current.progress + 1).padStart(2,'0')} · LOCKED EVIDENCE</p><h2>${esc(current.question)}</h2><p>Find the answer in your source article to open this evidence envelope.</p><form id="answer-form" autocomplete="off"><label class="answer-label" for="answer">YOUR ANSWER</label><div class="answer-row"><input id="answer" name="answer" required autocomplete="off" placeholder="Type your answer…" maxlength="200"><button class="primary" type="submit">Unlock clue ↗</button></div><p class="small-note">Answers are not case sensitive.${current.progress === 0 ? ' Include the % symbol.' : ''}</p><p class="error" id="answer-error" role="status"></p></form>`;
  document.querySelector('#answer-form').onsubmit = async e => {
    e.preventDefault(); if (busy) return; busy = true;
    const number = current.progress + 1, answer = document.querySelector('#answer').value;
    e.submitter.disabled = true;
    try {await action('/api/answer', {number,answer}); selectedClue = number; renderGame(); chime();}
    catch (error) {if (current.ended || current.progress !== number - 1) renderGame(); else {document.querySelector('#answer-error').textContent = error.message; document.querySelector('#answer-form button').disabled = false;}}
    finally {busy = false;}
  };
}
function evidence(content) {
  const clue = current.clues[selectedClue - 1];
  let media = '';
  if (selectedClue === 4) media = `<img class="evidence-media" src="/media/hidden-photo.jpg" alt="Hidden photo of the victim and Chef sharing a private moment at a restaurant table"><p class="eyebrow">THE PRIVATE CONVERSATION</p><video class="evidence-media" controls playsinline preload="metadata" src="/media/secret.mp4"></video>`;
  if (selectedClue === 2) media = `<p class="eyebrow">THE WAITRESS'S STATEMENT</p><video class="evidence-media" controls playsinline preload="metadata" poster="/media/restaurant.jpg" src="/media/waitress.mp4"></video><p class="eyebrow">THE CHEF'S STATEMENT</p><video class="evidence-media" controls playsinline preload="metadata" src="/media/chef.mp4"></video>`;
  content.innerHTML = `<p class="eyebrow">CLUE ${String(selectedClue).padStart(2,'0')} · EVIDENCE RECOVERED</p><h2>${esc(clue.title)}</h2><span class="badge">UNLOCKED & SAVED TO YOUR CASE FILE</span><div class="evidence"><p>${esc(clue.text)}</p></div>${media}<p>${selectedClue === 1 ? 'If the food was clean, what else did the victim consume?' : selectedClue === 3 ? 'Who sent this message? Who was hiding a relationship?' : selectedClue === 2 ? 'Hear both witness statements and compare what each person reveals.' : selectedClue === 5 ? "Review the Chief's statement and compare it with the other evidence." : 'Discuss what this evidence changes about your theory.'}</p><button class="primary" id="continue">${current.ended ? 'Return to the truth' : current.progress === 5 ? 'Make your final accusation' : 'Continue investigating'} →</button>`;
  document.querySelector('#continue').onclick = () => {selectedClue = null; renderGame();};
  content.querySelectorAll('video').forEach(v => v.onplay = () => {if (soundOn) toggleSound(); content.querySelectorAll('video').forEach(other => {if(other !== v) other.pause();});});
}
function finalForm(content) {
  const priorAttempt = current.last_attempt && !finalAttemptEditing ? current.last_attempt : null;
  if (priorAttempt) {
    content.innerHTML = `<p class="eyebrow">QUESTION 06 · YOUR FINAL DEDUCTION</p><h2>Accusation submitted</h2><p class="error" role="status">That combination was incorrect. Three minutes were deducted. Your submitted answers are locked below.</p>${accusationFields(priorAttempt, true)}<button class="primary" id="retry-accusation" type="button">Try another accusation</button>`;
    document.querySelector('#retry-accusation').onclick = () => {finalAttemptEditing = true; renderGame();};
    return;
  }
  content.innerHTML = `<p class="eyebrow">QUESTION 06 · YOUR FINAL DEDUCTION</p><h2>Everyone has a secret.<br>Only one is a killer.</h2><p>You have all five clues. Discuss your theory, then identify the killer, the weapon, and the motive. An incorrect combination deducts 3 minutes; you can try again.</p><form id="final-form" autocomplete="off"><div class="form-grid"><div><label class="answer-label" for="killer">KILLER</label><input id="killer" autocomplete="off" required maxlength="100" placeholder="Who committed the murder?"></div><div><label class="answer-label" for="weapon">MURDER WEAPON</label><input id="weapon" autocomplete="off" required maxlength="100" placeholder="What killed the victim?"></div><div class="full"><label class="answer-label" for="motive">MOTIVE</label><select id="motive" autocomplete="off" required><option value="">Select your theory</option>${['Jealousy','Business Conflict','Unresolved conflict','Infidelity Issues','Money Motive','Insecurity'].map(m => `<option>${m}</option>`).join('')}</select></div></div><p class="small-note">Answers ignore capitalization. Review your evidence before submitting.</p><button class="primary" type="submit">Submit final accusation ↗</button><p class="error" id="final-error" role="status"></p></form>`;
  document.querySelector('#final-form').onsubmit = async e => {
    e.preventDefault(); if (busy) return; busy = true; e.submitter.disabled = true;
    const data = Object.fromEntries(['killer','weapon','motive'].map(k => [k, document.getElementById(k).value]));
    finalAttemptEditing = false;
    try {await action('/api/final', data); renderGame(); chime();}
    catch(error) {if(current.ended) renderGame(); else {document.querySelector('#final-error').textContent = error.message; renderGame();}}
    finally {busy = false;}
  };
}
function accusationFields(values, disabled) {
  const attr = disabled ? 'disabled' : '';
  const value = key => esc(values && values[key] || '');
  return `<div class="form-grid accusation-fields"><div><label class="answer-label" for="locked-killer">KILLER</label><input id="locked-killer" value="${value('killer')}" ${attr}></div><div><label class="answer-label" for="locked-weapon">MURDER WEAPON</label><input id="locked-weapon" value="${value('weapon')}" ${attr}></div><div class="full"><label class="answer-label" for="locked-motive">MOTIVE</label><input id="locked-motive" value="${value('motive')}" ${attr}></div></div>`;
}
function reveal(content) {
  const attempt = current.last_attempt || current.submission;
  const lockedAnswers = attempt ? `<p class="eyebrow">YOUR TEAM'S FINAL ANSWERS</p>${accusationFields(attempt, true)}` : '';
  const confetti = current.correct ? `<div class="confetti-celebration" aria-hidden="true">${Array.from({length:36}, (_,i) => `<i style="--x:${(i*37)%100}%;--delay:${(i%9)*.08}s;--hue:${(i*47)%360};--drift:${(i*17)%90-45}px;--spin:${(i*59)%360}deg"></i>`).join('')}</div>` : '';
  if (!current.solution) {
    content.innerHTML = `${confetti}<p class="eyebrow">YOUR INVESTIGATION IS COMPLETE</p>${current.correct ? '<p class="victory-kicker">YOU WON!</p><h2>You Uncovered the Truth</h2><p>Your team correctly identified the killer, weapon, and motive.</p>' : `<h2>${current.expired && !current.submission ? 'The last minute has passed.' : 'One secret escaped you.'}</h2><p>Your team’s result has been recorded.</p>`}${lockedAnswers}<p class="small-note">The full case reveal will be available after both teams have finished.</p><span class="badge">${current.progress}/5 CLUES RECOVERED · ${current.correct ? 'CASE SOLVED' : 'INVESTIGATION CLOSED'}</span>`;
    return;
  }
  content.innerHTML = `${confetti}<p class="eyebrow">CASE CLOSED · THE TRUTH BEHIND THE REUNION</p>${current.correct ? '<p class="victory-kicker">YOU WON!</p><h2>You Uncovered the Truth</h2>' : `<h2>${current.expired && !current.submission ? 'The last minute has passed.' : 'One secret escaped you.'}</h2>`}<p>${current.expired && !current.submission ? 'Time ran out before your final accusation.' : current.correct ? 'Your team correctly identified the killer, weapon, and motive.' : 'Your accusation has been recorded.'}</p>${lockedAnswers}<div class="deduction">${Object.entries(current.solution).map(([k,v]) => `<div class="suspect"><span class="eyebrow">${k.toUpperCase()}</span><h3>${esc(v)}</h3></div>`).join('')}</div><div class="evidence"><p>${esc(current.solution_explanation)}</p></div><span class="badge">${current.progress}/5 CLUES RECOVERED · ${current.correct ? 'CASE SOLVED' : 'CASE REVEALED'}</span><p class="small-note">Both teams have finished their investigations.</p>`;
}
function resetSuspense() {
  document.body.classList.remove('investigation-active', 'timer-critical');
  document.body.style.removeProperty('--suspense-color');
  document.body.style.removeProperty('--timer-tension');
}
function updateSuspense() {
  if (!current) return;
  const seconds = remaining();
  const tension = Math.max(0, Math.min(1, 1 - seconds / 1800));
  const hue = Math.round(44 * (1 - tension));
  const lightness = Math.round(65 - 15 * tension);
  document.body.style.setProperty('--suspense-color', `hsl(${hue} 62% ${lightness}%)`);
  document.body.style.setProperty('--timer-tension', tension.toFixed(3));
  document.body.classList.toggle('timer-critical', seconds < 180 && !current.ended);
}function toggleSound() {
  soundOn = !soundOn;
  if (soundOn) startBackgroundMusic(); else stopBackgroundMusic();
  document.querySelector('#sound').setAttribute('aria-pressed',soundOn);
  document.querySelector('#sound span').textContent=soundOn?'Music on':'Music off';
}
function startBackgroundMusic() {
  soundOn = true;
  if (!audioContext && (window.AudioContext || window.webkitAudioContext)) {
    audioContext = new (window.AudioContext || window.webkitAudioContext)();
  }
  if (audioContext) audioContext.resume();
  backgroundMusic.play().catch(error => {
    stopBackgroundMusic();
    console.warn('Background music could not be played:', error);
  });
  const button = document.querySelector('#sound');
  if (button) {button.setAttribute('aria-pressed','true'); button.querySelector('span').textContent='Music on';}
}
function stopBackgroundMusic() {
  backgroundMusic.pause();
  backgroundMusic.currentTime = 0;
  soundOn = false;
  const button = document.querySelector('#sound');
  if (button) {button.setAttribute('aria-pressed','false'); button.querySelector('span').textContent='Music off';}
}
function chime() {
  if(!soundOn || !audioContext) return;
  const osc=audioContext.createOscillator(), gain=audioContext.createGain(); const now=audioContext.currentTime;
  osc.frequency.setValueAtTime(440,now); osc.frequency.setValueAtTime(660,now+.2);
  gain.gain.setValueAtTime(.04,now); gain.gain.exponentialRampToValueAtTime(.001,now+.65);
  osc.connect(gain).connect(audioContext.destination); osc.start();osc.stop(now+.7);
}
document.querySelector('#sound').onclick=toggleSound;
const musicDialog=document.querySelector('#music-dialog');
document.querySelector('#music').onclick=()=>{if(soundOn)toggleSound(); document.querySelector('#youtube').src='https://www.youtube.com/embed/ZkcnW1ZzHJI';musicDialog.showModal();};
musicDialog.querySelector('.close').onclick=()=>musicDialog.close();
musicDialog.onclose=()=>document.querySelector('#youtube').src='';
setInterval(()=>{
  if(screen!=='game'||!current)return;
  updateSuspense();
  const clock=document.querySelector('#clock');
  if(clock&&!current.ended){clock.textContent=formatTime(Math.ceil(remaining()));clock.parentElement.classList.toggle('urgent',remaining()<180);}
},250);
setInterval(async()=>{
  if(!['brief','game'].includes(screen)||busy)return;
  const previous=current, activeTeam=team, activeScreen=screen;
  try {
    await refresh();
    if(!['brief','game'].includes(screen)||activeTeam!==team)return;
    if(portalRoundId!==null && current.round_id!==portalRoundId) {
      portalRoundId=current.round_id;
      selectedClue=null;
      finalAttemptEditing=false;
      home('A new round is ready. Select your team to begin.');
      return;
    }
    if(activeScreen==='game' && (previous.progress!==current.progress || previous.ended!==current.ended || Boolean(previous.solution)!==Boolean(current.solution))) renderGame();
    const c=document.querySelector('#connection');if(c)c.textContent='';
  } catch (error) {
    if (error.status === 401 || error.status === 409) {
      teamCodePrompt(error.message);
      return;
    }
    if(screen==='game') {
      const c=document.querySelector('#connection'); if(c){c.textContent='Connection interrupted. Your server timer continues; reconnect to submit answers.'; c.className='connection';}
    } else if(screen==='brief') {
      const error=document.querySelector('#start-error'); if(error)error.textContent='Connection interrupted. Your server timer continues.';
    }
  }
},2000);
setInterval(()=>{
  if(screen==='gm-dashboard') loadDashboard();
},2500);
const routeTeam = Number(new URLSearchParams(window.location.search).get('team'));
if ([1, 2].includes(routeTeam)) enterTeam(routeTeam);
else (async () => {
  try {
    const response = await fetch('/api/gm/session', {cache:'no-store'});
    const session = await response.json();
    if (response.ok && session.authenticated) {
      gmPage = 'overview';
      await loadDashboard(true);
      return;
    }
  } catch {}
  home();
})();
