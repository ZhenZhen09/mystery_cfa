const app = document.querySelector('#app');
let team = Number(localStorage.getItem('reunion-team')) || 1;
if (![1, 2].includes(team)) team = 1;
let current = null, screen = 'home', selectedClue = null, receivedAt = 0, busy = false;
let audioContext, soundOn = false, soundNodes = [];
const esc = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const formatTime = seconds => `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`;
function home() {
  screen = 'home';
  app.innerHTML = `<section class="hero"><div><p class="eyebrow">AN EVENING TO REMEMBER. A SECRET TO UNCOVER.</p><h1>The Last<br>Reunion <em>Dinner.</em></h1><p class="description">Old friends. Unfinished stories. One final toast.<br>A reunion takes a deadly turn when a classmate collapses at dinner. Everyone has a motive. Can your team find the truth?</p><div class="stats"><div class="stat"><strong>30</strong><span>MINUTES</span></div><div class="stat"><strong>05</strong><span>HIDDEN CLUES</span></div><div class="stat"><strong>02</strong><span>TEAMS</span></div></div><p class="eyebrow" style="margin-bottom:10px">CHOOSE YOUR INVESTIGATION TEAM</p><div class="team-choose">${[1,2].map(n => `<button class="team-button ${team === n ? 'selected' : ''}" data-team="${n}" aria-pressed="${team === n}">Team ${n === 1 ? 'One' : 'Two'} <span>${n === 1 ? 'THE NIGHT OWLS' : 'THE SILENT WITNESSES'}</span></button>`).join('')}</div><button id="enter" class="primary wide">Enter the reunion <span>↗</span></button><p class="small-note">One shared case file per team. Use a different team slot for each group.</p><p id="home-error" class="error" role="status"></p></div><div class="hero-image"><span class="photo-label">THE SCENE · REUNION NIGHT</span><div class="photo-caption"><span>TABLE FOR FRIENDS. ROOM FOR SECRETS.</span><p>“Some things should have<br>stayed in the past.”</p></div></div></section><section><div class="section-head"><h2>Your evening, in three acts.</h2><p>Trust the evidence. Question everyone.</p></div><div class="steps"><div class="step"><span class="num">01</span><div><h3>Step into the story</h3><p>Meet the people at the table. Old friendships hide complicated motives.</p></div></div><div class="step"><span class="num">02</span><div><h3>Follow the evidence</h3><p>Answer five questions to unlock numbered clues, hidden messages, and witness accounts.</p></div></div><div class="step"><span class="num">03</span><div><h3>Make your accusation</h3><p>Name the killer, the murder weapon, and the motive before time runs out.</p></div></div></div></section>`;
  app.querySelectorAll('[data-team]').forEach(button => button.onclick = () => {team = Number(button.dataset.team); localStorage.setItem('reunion-team', team); home();});
  document.querySelector('#enter').onclick = async () => {
    try { await refresh(); if (current.started) {screen = 'game'; renderGame();} else brief(); }
    catch {document.querySelector('#home-error').textContent = 'Cannot reach the game server. Please try again.';}
  };
}
function brief() {
  screen = 'brief';
  app.innerHTML = `<section class="brief"><p class="eyebrow">TEAM ${team} · YOUR CASE BRIEFING</p><div class="card"><p class="eyebrow">REUNION MURDER MYSTERY</p><h2>A toast to the past.<br>A night with no tomorrow.</h2><p>A group of former high-school classmates reunites for dinner after many years. One of them, now a famous vlogger and successful entrepreneur, returns to reconnect with old friends.</p><p>But old relationships, jealousy, secrets, and unresolved conflicts return with them. During dinner, the victim suddenly collapses. Everyone becomes a suspect.</p><div class="intro-grid"><div class="suspect"><h3>The Victim</h3><p>A successful vlogger and entrepreneur. A familiar face with a life no one fully knows.</p></div><div class="suspect"><h3>The Chef</h3><p>Prepared the reunion dinner. Had access to the kitchen and the table service.</p></div><div class="suspect"><h3>The Waitress</h3><p>Served the table throughout the evening. May have noticed something others missed.</p></div><div class="suspect"><h3>The Classmates</h3><p>Old friends with old wounds. Business conflict, insecurity, and unresolved grudges make everyone worth questioning.</p></div></div><p class="eyebrow">YOUR 30-MINUTE INVESTIGATION</p><div class="timeline"><span>00–03 · Story & characters</span><span>03–08 · Suspects & motives</span><span>08–14 · Poison & weapon</span><span>14–21 · Secret relationship</span><span>21–26 · Chef & waitress</span><span>26–28 · Team discussion</span><span>28–30 · Final accusation</span></div><p>Keep the source articles available: they contain the answers to the five questions. Answers ignore capitalization and surrounding spaces. Clues unlock in order; revisit them in your case file anytime. The timeline is guidance, not a lock on your progress.</p><p class="small-note">The 30-minute clock starts when you press the button below. Include your opening discussion in those 30 minutes. Your final accusation is submitted once.</p><button id="start" class="primary">Start the 30-minute investigation ↗</button><p id="start-error" class="error" role="status"></p><button id="back" class="subtle-link">Back to team selection</button></div></section>`;
  document.querySelector('#back').onclick = home;
  document.querySelector('#start').onclick = async e => {
    e.currentTarget.disabled = true;
    try { await action('/api/start', {}); screen = 'game'; renderGame(); }
    catch (error) {document.querySelector('#start-error').textContent = error.message; document.querySelector('#start').disabled = false;}
  };
}
async function refresh() {
  const response = await fetch(`/api/state?team=${team}`, {cache:'no-store'});
  if (!response.ok) throw new Error('The game server could not be reached.');
  current = await response.json(); receivedAt = Date.now();
}
async function action(url, data) {
  const response = await fetch(url, {method:'POST', headers:{'Content-Type':'application/json'},body:JSON.stringify({team,...data})});
  current = await response.json(); receivedAt = Date.now();
  if (!response.ok) throw new Error(current.error || 'Please try again.');
}
function remaining() {return current ? Math.max(0, current.remaining - (Date.now() - receivedAt) / 1000) : 1800;}
function renderGame() {
  if (!current) return;
  screen = 'game';
  const elapsed = current.ended && current.elapsed != null ? `<span>CASE CLOSED · ${formatTime(current.elapsed)} ELAPSED</span>` : '<span>TIME TO FIND THE TRUTH</span>';
  app.innerHTML = `<div class="case-top"><div><p class="eyebrow">TEAM ${team === 1 ? 'ONE · THE NIGHT OWLS' : 'TWO · THE SILENT WITNESSES'}</p><h1>The Last Reunion Dinner</h1></div><div class="timer"><strong id="clock">${formatTime(Math.ceil(remaining()))}</strong>${elapsed}</div></div><div class="case-grid"><aside class="case-sidebar"><h2>YOUR CASE FILE</h2>${[1,2,3,4,5].map(n => `<button class="clue-tab ${selectedClue === n ? 'active' : ''}" data-clue="${n}" ${n > current.progress ? 'disabled' : ''}><b>${String(n).padStart(2,'0')}</b><span>Clue ${n}</span> ${n <= current.progress ? '✓' : '○'}</button>`).join('')}<button class="clue-tab" id="investigation"><b>06</b><span>${current.ended ? 'The truth' : current.progress === 5 ? 'Final accusation' : 'Investigation'}</span> →</button><p class="sidebar-note">${current.progress} of 5 clues recovered.<br>Compare the evidence before making your final accusation.</p><button id="switch" class="subtle-link">Return to team selection</button></aside><section class="card" id="case-content"></section></div><p id="connection" role="status"></p>`;
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
  content.innerHTML = `<p class="eyebrow">CLUE ${String(current.progress + 1).padStart(2,'0')} · LOCKED EVIDENCE</p><h2>${esc(current.question)}</h2><p>Find the answer in your source article to open this evidence envelope.</p><form id="answer-form"><label class="answer-label" for="answer">YOUR ANSWER</label><div class="answer-row"><input id="answer" name="answer" required autocomplete="off" placeholder="Type your answer…" maxlength="200"><button class="primary" type="submit">Unlock clue ↗</button></div><p class="small-note">Answers are not case sensitive.${current.progress === 0 ? ' Include the % symbol.' : ''}</p><p class="error" id="answer-error" role="status"></p></form>`;
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
  if (selectedClue === 4) media = `<img class="evidence-media" src="/media/hidden-photo.jpg" alt="Hidden photo of the victim and Chef sharing a private moment at a restaurant table"><p class="eyebrow">THE PRIVATE CONVERSATION</p><video class="evidence-media" controls playsinline preload="metadata" src="/media/secret.mp4"></video><p class="eyebrow">THE CHEF’S STATEMENT</p><video class="evidence-media" controls playsinline preload="metadata" src="/media/intro.mp4"></video>`;
  if (selectedClue === 5) media = `<video class="evidence-media" controls playsinline preload="metadata" poster="/media/restaurant.jpg" src="/media/waitress.mp4"></video>`;
  content.innerHTML = `<p class="eyebrow">CLUE ${String(selectedClue).padStart(2,'0')} · EVIDENCE RECOVERED</p><h2>${esc(clue.title)}</h2><span class="badge">UNLOCKED & SAVED TO YOUR CASE FILE</span><div class="evidence"><p>${esc(clue.text)}</p></div>${media}<p>${selectedClue === 1 ? 'If the food was clean, what else did the victim consume?' : selectedClue === 3 ? 'Who sent this message? Who was hiding a relationship?' : 'Discuss what this evidence changes about your theory.'}</p><button class="primary" id="continue">${current.ended ? 'Return to the truth' : current.progress === 5 ? 'Make your final accusation' : 'Continue investigating'} →</button>`;
  document.querySelector('#continue').onclick = () => {selectedClue = null; renderGame();};
  content.querySelectorAll('video').forEach(v => v.onplay = () => {if (soundOn) toggleSound(); content.querySelectorAll('video').forEach(other => {if(other !== v) other.pause();});});
}
function finalForm(content) {
  content.innerHTML = `<p class="eyebrow">QUESTION 06 · YOUR FINAL DEDUCTION</p><h2>Everyone has a secret.<br>Only one is a killer.</h2><p>You have all five clues. Discuss your theory, then identify the killer, the weapon, and the motive. This accusation is final.</p><form id="final-form"><div class="form-grid"><div><label class="answer-label" for="killer">KILLER</label><input id="killer" required maxlength="100" placeholder="Who committed the murder?"></div><div><label class="answer-label" for="weapon">MURDER WEAPON</label><input id="weapon" required maxlength="100" placeholder="What killed the victim?"></div><div class="full"><label class="answer-label" for="motive">MOTIVE</label><select id="motive" required><option value="">Select your theory</option>${['Business Conflict','Jealousy','Unresolved conflict','Infidelity Issues','Money Motive','Insecurity'].map(m => `<option>${m}</option>`).join('')}</select></div></div><p class="small-note">Answers ignore capitalization. Review your evidence before submitting.</p><button class="primary" type="submit">Submit final accusation ↗</button><p class="error" id="final-error" role="status"></p></form>`;
  document.querySelector('#final-form').onsubmit = async e => {
    e.preventDefault(); if (busy) return; busy = true; e.submitter.disabled = true;
    const data = Object.fromEntries(['killer','weapon','motive'].map(k => [k, document.getElementById(k).value]));
    try {await action('/api/final', data); renderGame(); chime();}
    catch(error) {if(current.ended) renderGame(); else {document.querySelector('#final-error').textContent = error.message; document.querySelector('#final-form button').disabled = false;}}
    finally {busy = false;}
  };
}
function reveal(content) {
  content.innerHTML = `<p class="eyebrow">CASE CLOSED · THE TRUTH BEHIND THE REUNION</p><h2>${current.expired && !current.submission ? 'The last minute has passed.' : current.correct ? 'You uncovered the truth.' : 'One secret escaped you.'}</h2><p>${current.expired && !current.submission ? 'Time ran out before your final accusation. Here is what happened that night.' : current.correct ? 'Your team correctly identified the killer, weapon, and motive.' : 'Your accusation has been recorded. Here is the complete solution.'}</p><div class="deduction">${Object.entries(current.solution).map(([k,v]) => `<div class="suspect"><span class="eyebrow">${k.toUpperCase()}</span><h3>${esc(v)}</h3></div>`).join('')}</div><div class="evidence"><p>The food was clean. The poison was in the drink. The Chef handled the glass, and the hidden message and photo exposed a secret relationship. Jealousy turned that secret into murder.</p></div><p>The waitress witnessed the Chef handling the glass. Her own love for the Chef kept her silent, but her confession finally connected the evidence.</p>${current.submission ? `<p class="eyebrow">YOUR TEAM’S ACCUSATION</p><p>${esc(current.submission.killer)} · ${esc(current.submission.weapon)} · ${esc(current.submission.motive)}</p>` : ''}<span class="badge">${current.progress}/5 CLUES RECOVERED · ${current.correct ? 'CASE SOLVED' : 'CASE REVEALED'}</span><p class="small-note">The other team’s investigation continues independently. Keep the solution private until both groups finish.</p>`;
}
function toggleSound() {
  if (!audioContext) audioContext = new (window.AudioContext || window.webkitAudioContext)();
  if (soundOn) {soundNodes.forEach(n => {try{n.stop();}catch{}}); soundNodes=[]; soundOn=false;}
  else {
    audioContext.resume();
    // A quiet, original suspense drone: no third-party audio download required.
    [55,82.41,110.2,164.81].forEach((frequency,i) => {
      const osc=audioContext.createOscillator(), gain=audioContext.createGain();
      osc.type='sine'; osc.frequency.value=frequency; gain.gain.value=i===0?.035:.012;
      osc.connect(gain).connect(audioContext.destination); osc.start(); soundNodes.push(osc);
    }); soundOn=true;
  }
  document.querySelector('#sound').setAttribute('aria-pressed',soundOn);
  document.querySelector('#sound span').textContent=soundOn?'Sound on':'Sound off';
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
  const clock=document.querySelector('#clock');
  if(clock&&!current.ended){clock.textContent=formatTime(Math.ceil(remaining()));clock.parentElement.classList.toggle('urgent',remaining()<180);}
},250);
setInterval(async()=>{
  if(screen!=='game'||busy)return;
  const previous=current, activeTeam=team;
  try {
    await refresh(); if(screen!=='game'||activeTeam!==team)return;
    if(previous.progress!==current.progress || previous.ended!==current.ended) renderGame();
    const c=document.querySelector('#connection');if(c)c.textContent='';
  } catch {
    const c=document.querySelector('#connection'); if(c){c.textContent='Connection interrupted. Your server timer continues; reconnect to submit answers.'; c.className='connection';}
  }
},2000);
home();
