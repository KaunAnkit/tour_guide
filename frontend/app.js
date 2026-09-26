/**
 * Dr Ambedkar National Memorial — Voice Tour Guide
 * -------------------------------------------------
 * Vanilla JS: mic capture, Web Audio AnalyserNode live amplitude pulsing,
 * FastAPI round-trip, Orpheus speech playback, and staggered artifact cards.
 */

(function () {
  'use strict';

  /* ===== DOM references ===== */
  const app             = document.getElementById('app');
  const orb             = document.getElementById('orb');
  const orbLabel        = document.getElementById('orb-label');
  const orbGlow         = document.getElementById('orb-glow');
  const orbRingOuter    = document.getElementById('orb-ring-outer');
  const orbRingInner    = document.getElementById('orb-ring-inner');
  const transcriptUser  = document.getElementById('transcript-user');
  const transcriptGuide = document.getElementById('transcript-guide');
  const userTextEl      = transcriptUser.querySelector('.transcript-text');
  const guideTextEl     = transcriptGuide.querySelector('.transcript-text');
  const artifactsGrid   = document.getElementById('artifacts-grid');
  const audioPlayer     = document.getElementById('audio-player');
  const chipButtons     = document.querySelectorAll('.chip');

  /* ===== Config ===== */
  const API_BASE = window.location.origin;

  /* ===== State ===== */
  let state = 'idle'; // 'idle' | 'listening' | 'processing' | 'speaking'
  let mediaRecorder = null;
  let audioChunks = [];
  let micStream = null;

  /* ===== Web Audio API ===== */
  let audioCtx = null;
  let playerSource = null;
  let playerAnalyser = null;
  let micSource = null;
  let micAnalyser = null;
  let activeAnalyser = null;
  let animFrame = null;

  function getAudioContext() {
    if (!audioCtx) {
      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      audioCtx = new AudioContextClass();
    }
    if (audioCtx.state === 'suspended') {
      audioCtx.resume();
    }
    return audioCtx;
  }

  function setupPlayerAudio() {
    const ctx = getAudioContext();
    if (!playerSource) {
      playerAnalyser = ctx.createAnalyser();
      playerAnalyser.fftSize = 256;
      playerAnalyser.smoothingTimeConstant = 0.75;
      playerSource = ctx.createMediaElementSource(audioPlayer);
      playerSource.connect(playerAnalyser);
      playerAnalyser.connect(ctx.destination);
    }
    return playerAnalyser;
  }

  function setupMicAudio(stream) {
    const ctx = getAudioContext();
    micAnalyser = ctx.createAnalyser();
    micAnalyser.fftSize = 256;
    micAnalyser.smoothingTimeConstant = 0.75;
    micSource = ctx.createMediaStreamSource(stream);
    micSource.connect(micAnalyser);
    // Mic is deliberately NOT connected to ctx.destination to avoid feedback squeal
    return micAnalyser;
  }

    let isCurrentHindi = false;

    /* ===== State management ===== */
    function setState(next) {
      state = next;
      app.className = '';
      if (next !== 'idle') {
        app.classList.add('state-' + next);
      }
      const labels = {
        idle: isCurrentHindi ? 'बोलने के लिए टैप करें / Tap to speak' : 'Tap to speak',
        listening: isCurrentHindi ? 'सुन रहे हैं… समाप्त करने के लिए टैप करें' : 'Listening… Tap to finish',
        processing: isCurrentHindi ? 'संग्रहालय अभिलेखागार खोज रहे हैं…' : 'Consulting museum archives…',
        speaking: isCurrentHindi ? 'मार्गदर्शक बोल रहे हैं…' : 'Memorial Guide Speaking…'
      };
      orbLabel.textContent = labels[next] || '';
    }

  function showToast(msg) {
    const t = document.createElement('div');
    t.className = 'error-toast';
    t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(() => { t.classList.add('out'); }, 3000);
    setTimeout(() => { t.remove(); }, 3400);
  }

  /* ===== Real-time Orb Pulsing (Web Audio AnalyserNode) ===== */
  function startOrbPulse(analyserNode) {
    activeAnalyser = analyserNode;
    if (!activeAnalyser) return;
    if (animFrame) cancelAnimationFrame(animFrame);

    const bufferLength = activeAnalyser.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);

    function tick() {
      if (!activeAnalyser) return;
      activeAnalyser.getByteFrequencyData(dataArray);

      let sum = 0;
      for (let i = 0; i < bufferLength; i++) {
        sum += dataArray[i];
      }
      const avg = (sum / bufferLength) / 255; // 0.0 to 1.0

      // Calculate dynamic scaling based on real acoustic amplitude
      const scale = 1.0 + avg * 0.42;
      const ringOuter = 1.0 + avg * 0.22;
      const ringInner = 1.0 + avg * 0.14;
      const glowOpacity = 0.35 + avg * 0.65;

      orb.style.transform = `scale(${scale.toFixed(3)})`;
      orbGlow.style.opacity = glowOpacity.toFixed(2);
      orbRingOuter.style.transform = `scale(${ringOuter.toFixed(3)})`;
      orbRingInner.style.transform = `scale(${ringInner.toFixed(3)})`;

      animFrame = requestAnimationFrame(tick);
    }
    tick();
  }

  function stopOrbPulse() {
    if (animFrame) {
      cancelAnimationFrame(animFrame);
      animFrame = null;
    }
    activeAnalyser = null;
    orb.style.transform = '';
    orbGlow.style.opacity = '';
    orbRingOuter.style.transform = '';
    orbRingInner.style.transform = '';
  }

  /* ===== Microphone Capture ===== */
  function getSupportedMime() {
    const prefs = [
      'audio/webm;codecs=opus',
      'audio/webm',
      'audio/ogg;codecs=opus',
      'audio/mp4'
    ];
    for (const m of prefs) {
      if (MediaRecorder.isTypeSupported(m)) return m;
    }
    return '';
  }

  async function startListening() {
    try {
      getAudioContext();
      micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (e) {
      console.warn('Microphone error or permission denied:', e);
      showToast('Microphone access unavailable — using prompt chips');
      return;
    }

    setState('listening');
    audioChunks = [];

    // Clear previous transcript & artifacts
    clearTourTurn();

    // Hook AnalyserNode to mic stream for live reactive pulsing
    const analyser = setupMicAudio(micStream);
    startOrbPulse(analyser);

    const mime = getSupportedMime();
    mediaRecorder = mime ? new MediaRecorder(micStream, { mimeType: mime }) : new MediaRecorder(micStream);
    mediaRecorder.ondataavailable = (e) => {
      if (e.data && e.data.size > 0) {
        audioChunks.push(e.data);
      }
    };
    mediaRecorder.onstop = onRecordingDone;
    mediaRecorder.start();
  }

  const layoutContainer = document.getElementById('main');
  const artifactsBadge  = document.getElementById('artifacts-badge');
  const artifactsArea   = document.getElementById('artifacts-area');

  function setLayoutActive(active) {
    if (active) {
      layoutContainer.classList.add('layout-active');
    } else {
      layoutContainer.classList.remove('layout-active');
    }
  }

  function stopListening() {
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
      mediaRecorder.stop();
    }
    if (micStream) {
      micStream.getTracks().forEach(t => t.stop());
      micStream = null;
    }
    stopOrbPulse();
    setState('processing');
    setLayoutActive(true);
  }

  async function onRecordingDone() {
    const mime = audioChunks[0]?.type || 'audio/webm';
    const blob = new Blob(audioChunks, { type: mime });
    audioChunks = [];

    const fd = new FormData();
    fd.append('audio', blob, 'recording.webm');

    sendConverseRequest(fd);
  }

  /* ===== Text query for chips & testing ===== */
  async function sendTextQuery(query) {
    clearTourTurn();
    isCurrentHindi = /[\u0900-\u097F]/.test(query);
    const userTag = transcriptUser.querySelector('.transcript-tag');
    if (userTag) userTag.textContent = isCurrentHindi ? 'आप / You' : 'You';
    setState('processing');
    setLayoutActive(true);
    userTextEl.textContent = query;
    transcriptUser.classList.remove('hidden');
    transcriptUser.classList.add('entering');

    const fd = new FormData();
    fd.append('query', query);
    sendConverseRequest(fd);
  }

  /* ===== Send to FastAPI backend ===== */
  async function sendConverseRequest(formData) {
    try {
      const resp = await fetch(API_BASE + '/converse', {
        method: 'POST',
        body: formData,
      });

      if (!resp.ok) {
        const errText = await resp.text();
        throw new Error(errText || `Server responded with ${resp.status}`);
      }

      const data = await resp.json();
      handleConverseResponse(data);
    } catch (err) {
      console.error('Converse request failed:', err);
      showToast('Guide communication error — please try again');
      setState('idle');
    }
  }

  /* ===== Handle API Response ===== */
  function handleConverseResponse(data) {
    const hasHindi = (data.text && /[\u0900-\u097F]/.test(data.text)) ||
                     (data.transcript && /[\u0900-\u097F]/.test(data.transcript));
    isCurrentHindi = Boolean(hasHindi);

    const userTag = transcriptUser.querySelector('.transcript-tag');
    const guideTag = transcriptGuide.querySelector('.transcript-tag');
    if (userTag) userTag.textContent = isCurrentHindi ? 'आप / You' : 'You';
    if (guideTag) guideTag.textContent = isCurrentHindi ? 'मार्गदर्शक / Memorial Guide' : 'Memorial Guide';

    // 1. Show user transcript
    if (data.transcript) {
      userTextEl.textContent = data.transcript;
      transcriptUser.classList.remove('hidden');
      transcriptUser.classList.add('entering');
    }

    // 2. Show guide answer text
    if (data.text) {
      guideTextEl.textContent = data.text;
      transcriptGuide.classList.remove('hidden');
      transcriptGuide.classList.add('entering');
    }

    // 3. Render artifacts with staggered slide-in
    renderArtifacts(data.artifacts || []);

    // 4. Play audio and pulse orb to the guide's voice
    if (data.audio_url) {
      playGuideSpeech(data.audio_url);
    } else {
      setState('idle');
    }
  }

  /* ===== Guide Audio Playback with AnalyserNode ===== */
  function playGuideSpeech(url) {
    setState('speaking');
    const fullUrl = url.startsWith('http') ? url : (API_BASE + url);

    audioPlayer.src = fullUrl;
    audioPlayer.load();

    const analyser = setupPlayerAudio();

    audioPlayer.play().then(() => {
      startOrbPulse(analyser);
    }).catch(err => {
      console.warn('Audio playback error:', err);
      stopOrbPulse();
      setState('idle');
    });

    audioPlayer.onended = () => {
      stopOrbPulse();
      setState('idle');
    };

    audioPlayer.onerror = (e) => {
      console.error('Audio player error:', e);
      stopOrbPulse();
      setState('idle');
    };
  }

  /* ===== Clear previous turn artifacts & transcripts ===== */
  function clearTourTurn() {
    transcriptUser.classList.add('hidden');
    transcriptUser.classList.remove('entering');
    transcriptGuide.classList.add('hidden');
    transcriptGuide.classList.remove('entering');
    userTextEl.textContent = '';
    guideTextEl.textContent = '';
    artifactsGrid.innerHTML = '';
    if (artifactsArea) artifactsArea.classList.add('hidden');
  }

  /* ===== Staggered Artifact Cards Rendering ===== */
  function renderArtifacts(artifacts) {
    artifactsGrid.innerHTML = '';
    if (!artifacts || artifacts.length === 0) {
      if (artifactsArea) artifactsArea.classList.add('hidden');
      return;
    }

    if (artifactsArea) artifactsArea.classList.remove('hidden');

    if (artifacts.length === 1) {
      artifactsGrid.classList.add('single-record');
    } else {
      artifactsGrid.classList.remove('single-record');
    }

    if (artifactsBadge) {
      const badgeText = isCurrentHindi
        ? (artifacts.length === 1 ? 'विशेष प्रदर्शनी' : `${artifacts.length} अभिलेख`)
        : (artifacts.length === 1 ? 'Featured Exhibit' : `${artifacts.length} Records`);
      artifactsBadge.textContent = badgeText;
    }

    const panelTitle = document.querySelector('.artifacts-panel-header h2');
    if (panelTitle) {
      panelTitle.textContent = isCurrentHindi ? 'प्रदर्शनी अभिलेखागार' : 'Exhibition Archives';
    }

    artifacts.forEach((artifact, index) => {
      const card = document.createElement('div');
      card.className = 'artifact-card';
      // Staggered slide-in animation delay
      card.style.animationDelay = (index * 130) + 'ms';

      const type = (artifact.type || 'photo').toLowerCase();
      let html = '';

      if (artifact.url && (type === 'image' || type === 'photo')) {
        const imgUrl = artifact.url.startsWith('http') ? artifact.url : (API_BASE + artifact.url);
        html += `<img class="card-image" src="${escHtml(imgUrl)}" alt="${escHtml(artifact.title || 'Museum Exhibit')}" loading="eager" />`;
      }

      html += `<div class="card-body">`;
      html += `<span class="card-type type-${type}">${escHtml(type)}</span>`;
      if (artifact.title) {
        html += `<h3 class="card-title">${escHtml(artifact.title)}</h3>`;
      }
      if (artifact.caption) {
        html += `<p class="card-caption">${escHtml(artifact.caption)}</p>`;
      }
      html += `</div>`;

      card.innerHTML = html;

      if (artifact.url && type === 'article') {
        card.setAttribute('role', 'link');
        card.setAttribute('tabindex', '0');
        card.style.cursor = 'pointer';
        card.addEventListener('click', () => {
          window.open(artifact.url, '_blank', 'noopener,noreferrer');
        });
      }

      artifactsGrid.appendChild(card);
    });
  }

  function escHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  /* ===== Interaction Event Listeners ===== */
  // Orb click / tap
  orb.addEventListener('click', () => {
    getAudioContext();
    if (state === 'idle') {
      startListening();
    } else if (state === 'listening') {
      stopListening();
    } else if (state === 'speaking') {
      // Allow tapping during speech to pause/interrupt
      audioPlayer.pause();
      stopOrbPulse();
      setState('idle');
    }
  });

  // Keyboard accessibility
  orb.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      orb.click();
    }
  });

  // Suggestion chips
  chipButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      getAudioContext();
      if (state === 'listening') {
        stopListening();
      }
      const q = btn.getAttribute('data-query');
      if (q) {
        sendTextQuery(q);
      }
    });
  });

  /* ===== Initial demo state ===== */
  setState('idle');

})();
