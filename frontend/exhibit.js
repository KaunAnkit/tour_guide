/**
 * Exhibit page — homepage voice UI plus QR artifact narration.
 */

(function () {
  'use strict';

  const API_BASE = window.location.origin;
  const SCAN_INTERVAL_MS = 100;

  const app = document.getElementById('app');
  const orb = document.getElementById('orb');
  const orbLabel = document.getElementById('orb-label');
  const orbGlow = document.getElementById('orb-glow');
  const orbRingOuter = document.getElementById('orb-ring-outer');
  const orbRingInner = document.getElementById('orb-ring-inner');
  const transcriptUser = document.getElementById('transcript-user');
  const transcriptGuide = document.getElementById('transcript-guide');
  const userTextEl = transcriptUser.querySelector('.transcript-text');
  const guideTextEl = transcriptGuide.querySelector('.transcript-text');
  const artifactsGrid = document.getElementById('artifacts-grid');
  const audioPlayer = document.getElementById('audio-player');
  const layoutContainer = document.getElementById('main');
  const responseColumn = document.getElementById('response-column');
  const artifactsBadge = document.getElementById('artifacts-badge');
  const artifactsArea = document.getElementById('artifacts-area');
  const archivesTitle = document.getElementById('archives-title');
  const headerSubtitle = document.getElementById('header-subtitle');
  const scanQrChip = document.getElementById('scan-qr-chip');
  const scannerOverlay = document.getElementById('scanner-overlay');
  const scannerVideo = document.getElementById('scanner-video');
  const scannerCanvas = document.getElementById('scanner-canvas');
  const scannerStatus = document.getElementById('scanner-status');
  const closeScanner = document.getElementById('close-scanner');
  const manualForm = document.getElementById('manual-form');
  const manualInput = document.getElementById('manual-id');
  const languageOverlay = document.getElementById('language-overlay');
  const languageOptions = languageOverlay.querySelectorAll('[data-language]');

  let state = 'idle';
  let currentQrId = null;
  let mediaRecorder = null;
  let audioChunks = [];
  let micStream = null;
  let cameraStream = null;
  let scanTimer = null;
  let isCurrentHindi = false;
  let selectedLanguage = 'en';

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
    if (audioCtx.state === 'suspended') audioCtx.resume();
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
    return micAnalyser;
  }

  function setState(next) {
    state = next;
    const scanning = !scannerOverlay.classList.contains('hidden');
    app.className = '';
    if (next !== 'idle') app.classList.add('state-' + next);

    const labels = {
      idle: currentQrId
        ? (isCurrentHindi ? 'प्रदर्शनी के बारे में पूछें / Tap to ask' : 'Ask about this exhibit')
        : (isCurrentHindi ? 'बोलने के लिए टैप करें / Tap to speak' : 'Tap to speak'),
      listening: isCurrentHindi ? 'सुन रहे हैं… समाप्त करने के लिए टैप करें' : 'Listening… Tap to finish',
      processing: isCurrentHindi ? 'संग्रहालय अभिलेखागार खोज रहे हैं…' : 'Consulting museum archives…',
      speaking: isCurrentHindi ? 'मार्गदर्शक बोल रहे हैं…' : 'Memorial Guide Speaking…'
    };
    orbLabel.textContent = scanning ? 'Scanning QR…' : (labels[next] || '');
  }

  function setLayoutActive(active) {
    layoutContainer.classList.toggle('layout-active', active);
  }

  function showToast(msg) {
    const t = document.createElement('div');
    t.className = 'error-toast';
    t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(function () { t.classList.add('out'); }, 3000);
    setTimeout(function () { t.remove(); }, 3400);
  }

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
      for (let i = 0; i < bufferLength; i++) sum += dataArray[i];
      const avg = (sum / bufferLength) / 255;
      orb.style.transform = 'scale(' + (1 + avg * 0.42).toFixed(3) + ')';
      orbGlow.style.opacity = (0.35 + avg * 0.65).toFixed(2);
      orbRingOuter.style.transform = 'scale(' + (1 + avg * 0.22).toFixed(3) + ')';
      orbRingInner.style.transform = 'scale(' + (1 + avg * 0.14).toFixed(3) + ')';
      animFrame = requestAnimationFrame(tick);
    }
    tick();
  }

  function stopOrbPulse() {
    if (animFrame) cancelAnimationFrame(animFrame);
    animFrame = null;
    activeAnalyser = null;
    orb.style.transform = '';
    orbGlow.style.opacity = '';
    orbRingOuter.style.transform = '';
    orbRingInner.style.transform = '';
  }

  function getSupportedMime() {
    const prefs = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4'];
    for (let i = 0; i < prefs.length; i++) {
      if (MediaRecorder.isTypeSupported(prefs[i])) return prefs[i];
    }
    return '';
  }

  function clearTourTurn() {
    transcriptUser.classList.add('hidden');
    transcriptUser.classList.remove('entering');
    transcriptGuide.classList.add('hidden');
    transcriptGuide.classList.remove('entering');
    userTextEl.textContent = '';
    guideTextEl.textContent = '';
    if (!currentQrId) {
      artifactsGrid.innerHTML = '';
      artifactsArea.classList.add('hidden');
    }
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

  function renderArtifacts(artifacts) {
    artifactsGrid.innerHTML = '';
    if (!artifacts || artifacts.length === 0) {
      artifactsArea.classList.add('hidden');
      return;
    }

    artifactsArea.classList.remove('hidden');
    artifactsGrid.classList.toggle('single-record', artifacts.length === 1);

    artifactsBadge.textContent = artifacts.length === 1
      ? 'Featured Exhibit'
      : artifacts.length + ' Records';
    archivesTitle.textContent = currentQrId ? 'This Exhibit' : 'Exhibition Archives';

    artifacts.forEach(function (artifact, index) {
      const card = document.createElement('div');
      card.className = 'artifact-card';
      card.style.animationDelay = (index * 130) + 'ms';
      const type = (artifact.type || 'photo').toLowerCase();
      let html = '';
      if (artifact.url && (type === 'image' || type === 'photo')) {
        const imgUrl = artifact.url.startsWith('http') ? artifact.url : (API_BASE + artifact.url);
        html += '<img class="card-image" src="' + escHtml(imgUrl) + '" alt="' + escHtml(artifact.title || 'Museum Exhibit') + '" loading="eager" />';
      }
      html += '<div class="card-body">';
      html += '<span class="card-type type-' + type + '">' + escHtml(type) + '</span>';
      if (artifact.title) html += '<h3 class="card-title">' + escHtml(artifact.title) + '</h3>';
      if (artifact.caption) html += '<p class="card-caption">' + escHtml(artifact.caption) + '</p>';
      html += '</div>';
      card.innerHTML = html;
      artifactsGrid.appendChild(card);
    });
  }

  function playGuideSpeech(url, onStarted) {
    setState('speaking');
    const fullUrl = url.startsWith('http') ? url : (API_BASE + url);
    audioPlayer.src = fullUrl;
    audioPlayer.load();
    const analyser = setupPlayerAudio();
    audioPlayer.play().then(function () {
      startOrbPulse(analyser);
      if (onStarted) onStarted();
    }).catch(function () {
      stopOrbPulse();
      setState('idle');
    });
    audioPlayer.onended = function () {
      stopOrbPulse();
      setState('idle');
    };
    audioPlayer.onerror = function () {
      stopOrbPulse();
      setState('idle');
    };
  }

  function applyTranscript(data, includeUser, onSpeechStarted) {
    const hasHindi = (data.text && /[\u0900-\u097F]/.test(data.text)) ||
      (data.transcript && /[\u0900-\u097F]/.test(data.transcript));
    isCurrentHindi = Boolean(hasHindi);
    const userTag = transcriptUser.querySelector('.transcript-tag');
    const guideTag = transcriptGuide.querySelector('.transcript-tag');
    if (userTag) userTag.textContent = isCurrentHindi ? 'आप / You' : 'You';
    if (guideTag) guideTag.textContent = isCurrentHindi ? 'मार्गदर्शक / Memorial Guide' : 'Memorial Guide';

    if (includeUser && data.transcript) {
      userTextEl.textContent = data.transcript;
      transcriptUser.classList.remove('hidden');
      transcriptUser.classList.add('entering');
    } else if (!includeUser) {
      transcriptUser.classList.add('hidden');
    }

    if (data.text) {
      guideTextEl.textContent = data.text;
      transcriptGuide.classList.remove('hidden');
      transcriptGuide.classList.add('entering');
    }

    if (data.audio_url) playGuideSpeech(data.audio_url, onSpeechStarted);
    else setState('idle');
  }

  async function sendConverseRequest(formData) {
    try {
      if (!formData.has('language')) formData.append('language', selectedLanguage);
      const path = currentQrId
        ? '/artifact/' + encodeURIComponent(currentQrId) + '/converse'
        : '/converse';
      const resp = await fetch(API_BASE + path, { method: 'POST', body: formData });
      if (!resp.ok) throw new Error('Server ' + resp.status);
      const data = await resp.json();
      if (!currentQrId) renderArtifacts(data.artifacts || []);
      applyTranscript(data, true);
    } catch (err) {
      console.error(err);
      showToast('Guide communication error — please try again');
      setState('idle');
    }
  }

  async function startListening() {
    try {
      getAudioContext();
      micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (e) {
      showToast('Microphone access unavailable — use Scan QR or chips');
      return;
    }
    setState('listening');
    audioChunks = [];
    clearTourTurn();
    startOrbPulse(setupMicAudio(micStream));
    const mime = getSupportedMime();
    mediaRecorder = mime ? new MediaRecorder(micStream, { mimeType: mime }) : new MediaRecorder(micStream);
    mediaRecorder.ondataavailable = function (e) {
      if (e.data && e.data.size > 0) audioChunks.push(e.data);
    };
    mediaRecorder.onstop = function () {
      const blob = new Blob(audioChunks, { type: audioChunks[0] && audioChunks[0].type || 'audio/webm' });
      audioChunks = [];
      const fd = new FormData();
      fd.append('audio', blob, 'recording.webm');
      sendConverseRequest(fd);
    };
    mediaRecorder.start();
  }

  function stopListening() {
    if (mediaRecorder && mediaRecorder.state !== 'inactive') mediaRecorder.stop();
    if (micStream) {
      micStream.getTracks().forEach(function (t) { t.stop(); });
      micStream = null;
    }
    stopOrbPulse();
    setState('processing');
    setLayoutActive(true);
  }

  function sendTextQuery(query) {
    clearTourTurn();
    isCurrentHindi = /[\u0900-\u097F]/.test(query);
    setState('processing');
    setLayoutActive(true);
    userTextEl.textContent = query;
    transcriptUser.classList.remove('hidden');
    transcriptUser.classList.add('entering');
    const fd = new FormData();
    fd.append('query', query);
    sendConverseRequest(fd);
  }

  function pickIdFromText(text) {
    if (!text) return null;
    const decoded = decodeURIComponent(text).trim();
    const museumId = decoded.match(/DANM-EXH-\d+/i);
    if (museumId) return museumId[0];
    return decoded.replace(/^\/+|\/+$/g, '') || null;
  }

  function parseQrPayload(raw) {
    if (!raw) return null;
    const trimmed = raw.trim();
    try {
      const url = new URL(trimmed);
      const fromQuery = url.searchParams.get('qr_id') || url.searchParams.get('id') ||
        url.searchParams.get('artifact') || url.searchParams.get('exhibit');
      if (fromQuery) return pickIdFromText(fromQuery);
      const parts = url.pathname.split('/').filter(Boolean);
      const last = parts[parts.length - 1];
      if (last && last.toLowerCase() !== 'exhibit') return pickIdFromText(last);
    } catch (_) { /* not a URL */ }
    return pickIdFromText(trimmed);
  }

  function stopScanner() {
    if (scanTimer) {
      clearInterval(scanTimer);
      scanTimer = null;
    }
    if (cameraStream) {
      cameraStream.getTracks().forEach(function (t) { t.stop(); });
      cameraStream = null;
    }
    scannerVideo.srcObject = null;
  }

  function closeScannerOverlay() {
    stopScanner();
    scannerOverlay.classList.add('hidden');
    scannerOverlay.setAttribute('aria-hidden', 'true');
    setState(state === 'processing' || state === 'speaking' ? state : 'idle');
  }

  async function openScanner() {
    audioPlayer.pause();
    stopOrbPulse();
    if (state === 'listening') stopListening();
    scannerOverlay.classList.remove('hidden');
    scannerOverlay.setAttribute('aria-hidden', 'false');
    scannerStatus.textContent = 'Starting camera…';
    stopScanner();
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: 'environment' }, width: { ideal: 640 }, height: { ideal: 480 } },
        audio: false
      });
      cameraStream = stream;
      scannerVideo.srcObject = stream;
      await scannerVideo.play();
      scannerStatus.textContent = 'Point camera at exhibit QR code';
      scanTimer = setInterval(tickScan, SCAN_INTERVAL_MS);
    } catch (err) {
      scannerStatus.textContent = 'Camera unavailable — enter exhibit ID below';
    }
  }

  function tickScan() {
    if (!scannerVideo.videoWidth || typeof jsQR !== 'function') return;
    const ctx = scannerCanvas.getContext('2d', { willReadFrequently: true });
    scannerCanvas.width = scannerVideo.videoWidth;
    scannerCanvas.height = scannerVideo.videoHeight;
    ctx.drawImage(scannerVideo, 0, 0, scannerCanvas.width, scannerCanvas.height);
    const imageData = ctx.getImageData(0, 0, scannerCanvas.width, scannerCanvas.height);
    const code = jsQR(imageData.data, imageData.width, imageData.height, { inversionAttempts: 'dontInvert' });
    if (code && code.data) {
      const qrId = parseQrPayload(code.data);
      if (qrId) {
        closeScannerOverlay();
        openArtifact(qrId);
      }
    }
  }

  async function openArtifact(qrId) {
    audioPlayer.pause();
    stopOrbPulse();
    currentQrId = qrId;
    setLayoutActive(true);
    setState('processing');
    clearTourTurn();
    artifactsGrid.innerHTML = '';
    artifactsArea.classList.add('hidden');
    headerSubtitle.textContent = 'Exhibit Voice Guide';

    try {
      const language = await chooseLanguage();
      if (!language) {
        currentQrId = null;
        headerSubtitle.textContent = 'Exhibit Voice Guide';
        setState('idle');
        return;
      }
      selectedLanguage = language;
      const resp = await fetch(API_BASE + '/artifact/' + encodeURIComponent(qrId));
      if (resp.status === 404) {
        showToast('Unknown exhibit: ' + qrId);
        currentQrId = null;
        setState('idle');
        return;
      }
      if (!resp.ok) throw new Error('load failed');
      const data = await resp.json();
      currentQrId = data.qr_id || qrId;
      headerSubtitle.textContent = data.title || 'Exhibit Voice Guide';

      const narrate = await fetch(API_BASE + '/artifact/' + encodeURIComponent(currentQrId) + '/narrate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ language: selectedLanguage })
      });
      if (!narrate.ok) throw new Error('narrate failed');
      const spoken = await narrate.json();
      applyTranscript(spoken, false, function () {
        renderArtifacts(data.images || []);
        requestAnimationFrame(function () {
          responseColumn.scrollIntoView({ behavior: 'smooth', block: 'start' });
        });
      });
    } catch (err) {
      console.error(err);
      showToast('Could not load exhibit. Try again.');
      setState('idle');
    }
  }

  function chooseLanguage() {
    languageOverlay.classList.remove('hidden');
    languageOverlay.setAttribute('aria-hidden', 'false');
    return new Promise(function (resolve) {
      function finish(language) {
        languageOverlay.classList.add('hidden');
        languageOverlay.setAttribute('aria-hidden', 'true');
        languageOptions.forEach(function (option) {
          option.removeEventListener('click', option._languageHandler);
        });
        resolve(language);
      }
      languageOptions.forEach(function (option) {
        option._languageHandler = function () { finish(option.dataset.language); };
        option.addEventListener('click', option._languageHandler);
      });
    });
  }

  orb.addEventListener('click', function () {
    getAudioContext();
    if (state === 'idle') startListening();
    else if (state === 'listening') stopListening();
    else if (state === 'speaking') {
      audioPlayer.pause();
      stopOrbPulse();
      setState('idle');
    }
  });

  orb.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      orb.click();
    }
  });

  scanQrChip.addEventListener('click', function () {
    getAudioContext();
    openScanner();
  });

  closeScanner.addEventListener('click', closeScannerOverlay);

  manualForm.addEventListener('submit', function (e) {
    e.preventDefault();
    const id = manualInput.value.trim();
    if (!id) return;
    closeScannerOverlay();
    openArtifact(id);
  });

  setState('idle');
})();
