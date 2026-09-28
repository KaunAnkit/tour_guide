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
  const imageViewer     = document.getElementById('image-viewer');
  const imageViewerImage = document.getElementById('image-viewer-image');
  const closeImageViewerButton = document.getElementById('close-image-viewer');
  const kioskMic = document.getElementById('kiosk-mic');
  const kioskAnswer = document.getElementById('kiosk-answer');
  const kioskQuestion = document.getElementById('kiosk-question');
  const kioskAnswerCopy = document.getElementById('kiosk-answer-copy');
  const kioskAnswerState = document.getElementById('kiosk-answer-state');
  const kioskRelatedWrap = document.getElementById('kiosk-related-wrap');
  const kioskRelated = document.getElementById('kiosk-related');
  const voiceStatus = document.getElementById('kiosk-voice-status');
  const kioskAttract = document.getElementById('kiosk-attract');

  /* ===== Config ===== */
  const API_BASE = window.location.origin;
  const KIOSK_CONTENT = {
    exhibits: window.KIOSK_EXHIBITS || [],
    books: window.KIOSK_BOOKS || [],
    speeches: window.KIOSK_SPEECHES || [],
    interviews: window.KIOSK_INTERVIEWS || [],
    media: window.KIOSK_MEDIA || []
  };

  let state = 'idle';
  let mediaRecorder = null;
  let audioChunks = [];
  let micStream = null;
  let imageViewerOpen = false;
  let imageViewerScrollTop = 0;
  let imageViewerReturnFocus = null;
  let kioskIdleTimer = null;
  let kioskModalOpen = false;
  let currentExhibit = null;
  let assistantContextId = '';
  let kioskRequestVersion = 0;
  let kioskLanguage = 'en';

  const kioskTranslations = {
    en: {
      guide: 'VOICE TOUR GUIDE', navExplore: 'EXPLORE', navBooks: 'BOOKS', navSpeeches: 'SPEECHES', navInterviews: 'INTERVIEWS', navMedia: 'MEDIA', navAsk: 'ASK', home: 'HOME',
      heroKicker: 'SEE · ASK · LISTEN · DISCOVER', heroTitle: 'Explore the Life<br />&amp; Legacy of<br /><em>Dr. B. R. Ambedkar</em>', heroIntro: 'Explore exhibits, listen to speeches, discover books and ask questions.', speak: 'TAP TO SPEAK', explore: 'EXPLORE EXHIBITS', heroCaption: 'A VOICE-GUIDED JOURNEY THROUGH HISTORY',
      askKicker: '01 / ASK', askTitle: 'Ask the Guide', askIntro: "Ask about Ambedkar's life, ideas, speeches, writings and legacy.", promptHeading: 'QUESTIONS TO BEGIN WITH', qEducation: 'What did Ambedkar say about education?', qMahad: 'Why was the Mahad Satyagraha important?', qConstitution: 'What happened during the drafting of the Constitution?', qBooks: 'Which books discuss social justice?',
      exhibitsKicker: '02 / EXPLORE', exhibitsTitle: 'Explore the Memorial', exhibitsIntro: 'Stories of courage, scholarship and a nation in the making.', collection: 'THE COLLECTION', booksKicker: '03 / READ', booksTitle: 'Books & Writings', booksIntro: 'Explore selected writings and publications related to Dr. B. R. Ambedkar.', library: 'THE LIBRARY',
      speechKicker: '04 / LISTEN', speechTitle: 'Speeches', speechIntro: 'Browse speeches with verified archival media and source details.', oralHistory: 'ORAL HISTORY', interviewsKicker: '05 / REMEMBER', interviewsTitle: 'Interviews', interviewsIntro: 'Browse interviews and oral histories from verified sources.', mediaKicker: '06 / SEE', mediaTitle: 'Historical Media', mediaIntro: "Photographs and visual records from the memorial's local collection.", records: 'ARCHIVAL RECORDS',
      discoverKicker: '07 / DISCOVER', discoverTitle: 'Discover Connections', discoverIntro: 'Explore related topics across people, places, events and ideas.', startOver: 'START OVER', micIdle: 'TAP TO SPEAK', micListening: 'LISTENING · TAP TO FINISH', micProcessing: 'SEARCHING THE ARCHIVE', micSpeaking: 'ANSWER PLAYING · TAP TO PAUSE',
      statusIdle: 'Ask naturally. Your question will be answered from the available archival knowledge.', statusListening: 'Listening… Tap the microphone again when you have finished speaking.', statusProcessing: 'Searching the archive… Preparing your answer.', statusSpeaking: 'Your archive answer is playing. Tap the microphone to pause.', statusReady: 'Your answer is ready. Continue exploring the connected archive.',
      queries: ['What did Ambedkar say about education?', 'Why was the Mahad Satyagraha important?', 'What happened during the drafting of the Constitution?', 'Which books discuss social justice?']
    },
    hi: {
      guide: 'आवाज़ से संग्रहालय भ्रमण', navExplore: 'प्रदर्शनियाँ', navBooks: 'पुस्तकें', navSpeeches: 'भाषण', navInterviews: 'साक्षात्कार', navMedia: 'मीडिया', navAsk: 'पूछें', home: 'मुखपृष्ठ',
      heroKicker: 'देखें · पूछें · सुनें · जानें', heroTitle: 'जीवन और विरासत<br />को जानें<br /><em>डॉ. बी. आर. आंबेडकर की</em>', heroIntro: 'प्रदर्शनियाँ देखें, भाषण सुनें, पुस्तकें जानें और प्रश्न पूछें।', speak: 'बोलने के लिए टैप करें', explore: 'प्रदर्शनियाँ देखें', heroCaption: 'इतिहास की आवाज़-निर्देशित यात्रा',
      askKicker: '01 / पूछें', askTitle: 'मार्गदर्शक से पूछें', askIntro: 'आंबेडकर के जीवन, विचारों, भाषणों, लेखन और विरासत के बारे में पूछें।', promptHeading: 'इन प्रश्नों से शुरुआत करें', qEducation: 'आंबेडकर ने शिक्षा के बारे में क्या कहा?', qMahad: 'महाड सत्याग्रह क्यों महत्वपूर्ण था?', qConstitution: 'संविधान निर्माण के दौरान क्या हुआ?', qBooks: 'सामाजिक न्याय पर कौन-सी पुस्तकें हैं?',
      exhibitsKicker: '02 / जानें', exhibitsTitle: 'स्मारक की प्रदर्शनी देखें', exhibitsIntro: 'साहस, विद्वत्ता और एक राष्ट्र के निर्माण की कहानियाँ।', collection: 'प्रदर्शनी संग्रह', booksKicker: '03 / पढ़ें', booksTitle: 'पुस्तकें और लेखन', booksIntro: 'डॉ. बी. आर. आंबेडकर से संबंधित चुनिंदा लेखन और प्रकाशन देखें।', library: 'पुस्तकालय',
      speechKicker: '04 / सुनें', speechTitle: 'भाषण', speechIntro: 'सत्यापित अभिलेखीय मीडिया और स्रोत विवरण वाले भाषण देखें।', oralHistory: 'मौखिक इतिहास', interviewsKicker: '05 / याद करें', interviewsTitle: 'साक्षात्कार', interviewsIntro: 'सत्यापित स्रोतों से साक्षात्कार और मौखिक इतिहास देखें।', mediaKicker: '06 / देखें', mediaTitle: 'ऐतिहासिक मीडिया', mediaIntro: 'स्मारक के स्थानीय संग्रह के छायाचित्र और दृश्य अभिलेख।', records: 'अभिलेखीय सामग्री',
      discoverKicker: '07 / खोजें', discoverTitle: 'संबंधों की खोज करें', discoverIntro: 'लोगों, स्थानों, घटनाओं और विचारों से जुड़े विषय देखें।', startOver: 'फिर से शुरू करें', micIdle: 'बोलने के लिए टैप करें', micListening: 'सुन रहे हैं · समाप्त करने के लिए टैप करें', micProcessing: 'अभिलेखागार खोज रहे हैं', micSpeaking: 'उत्तर चल रहा है · रोकने के लिए टैप करें',
      statusIdle: 'स्वाभाविक रूप से प्रश्न पूछें। उत्तर उपलब्ध अभिलेखागार पर आधारित होगा।', statusListening: 'सुन रहे हैं… बोलना समाप्त होने पर माइक्रोफ़ोन फिर से टैप करें।', statusProcessing: 'अभिलेखागार खोज रहे हैं… उत्तर तैयार हो रहा है।', statusSpeaking: 'अभिलेख का उत्तर चल रहा है। रोकने के लिए माइक्रोफ़ोन टैप करें।', statusReady: 'आपका उत्तर तैयार है। संबंधित अभिलेख देखें।',
      queries: ['आंबेडकर ने शिक्षा के बारे में क्या कहा?', 'महाड सत्याग्रह क्यों महत्वपूर्ण था?', 'संविधान निर्माण के दौरान क्या हुआ?', 'सामाजिक न्याय पर कौन-सी पुस्तकें हैं?']
    },
    mr: {
      guide: 'आवाज मार्गदर्शित संग्रहालय फेरी', navExplore: 'प्रदर्शने', navBooks: 'पुस्तके', navSpeeches: 'भाषणे', navInterviews: 'मुलाखती', navMedia: 'माध्यम', navAsk: 'विचारा', home: 'मुख्यपृष्ठ',
      heroKicker: 'पाहा · विचारा · ऐका · जाणून घ्या', heroTitle: 'जीवन आणि वारसा<br />जाणून घ्या<br /><em>डॉ. बी. आर. आंबेडकरांचा</em>', heroIntro: 'प्रदर्शने पाहा, भाषणे ऐका, पुस्तके जाणून घ्या आणि प्रश्न विचारा.', speak: 'बोलण्यासाठी टॅप करा', explore: 'प्रदर्शने पाहा', heroCaption: 'इतिहासाचा आवाज मार्गदर्शित प्रवास',
      askKicker: '01 / विचारा', askTitle: 'मार्गदर्शकाला विचारा', askIntro: 'आंबेडकरांचे जीवन, विचार, भाषणे, लेखन आणि वारसा याबद्दल विचारा.', promptHeading: 'या प्रश्नांपासून सुरुवात करा', qEducation: 'आंबेडकरांनी शिक्षणाबद्दल काय सांगितले?', qMahad: 'महाड सत्याग्रह महत्त्वाचा का होता?', qConstitution: 'संविधान निर्मितीदरम्यान काय घडले?', qBooks: 'सामाजिक न्यायावरील पुस्तके कोणती?',
      exhibitsKicker: '02 / जाणून घ्या', exhibitsTitle: 'स्मारकाची प्रदर्शने पाहा', exhibitsIntro: 'धैर्य, विद्वत्ता आणि राष्ट्रनिर्मितीच्या कथा.', collection: 'प्रदर्शन संग्रह', booksKicker: '03 / वाचा', booksTitle: 'पुस्तके आणि लेखन', booksIntro: 'डॉ. बी. आर. आंबेडकरांशी संबंधित निवडक लेखन आणि प्रकाशने पाहा.', library: 'ग्रंथालय',
      speechKicker: '04 / ऐका', speechTitle: 'भाषणे', speechIntro: 'पडताळलेली अभिलेखीय माध्यमे आणि स्रोत तपशील असलेली भाषणे पाहा.', oralHistory: 'मौखिक इतिहास', interviewsKicker: '05 / आठवा', interviewsTitle: 'मुलाखती', interviewsIntro: 'पडताळलेल्या स्रोतांमधील मुलाखती आणि मौखिक इतिहास पाहा.', mediaKicker: '06 / पाहा', mediaTitle: 'ऐतिहासिक माध्यमे', mediaIntro: 'स्मारकाच्या स्थानिक संग्रहातील छायाचित्रे आणि दृश्य नोंदी.', records: 'अभिलेखीय नोंदी',
      discoverKicker: '07 / शोधा', discoverTitle: 'संबंध शोधा', discoverIntro: 'व्यक्ती, ठिकाणे, घटना आणि विचारांशी संबंधित विषय पाहा.', startOver: 'पुन्हा सुरू करा', micIdle: 'बोलण्यासाठी टॅप करा', micListening: 'ऐकत आहे · पूर्ण झाल्यावर टॅप करा', micProcessing: 'अभिलेख शोधत आहे', micSpeaking: 'उत्तर सुरू आहे · थांबवण्यासाठी टॅप करा',
      statusIdle: 'नैसर्गिकपणे प्रश्न विचारा. उत्तर उपलब्ध अभिलेखांवर आधारित असेल.', statusListening: 'ऐकत आहे… बोलणे पूर्ण झाल्यावर मायक्रोफोन पुन्हा टॅप करा.', statusProcessing: 'अभिलेख शोधत आहे… उत्तर तयार होत आहे.', statusSpeaking: 'अभिलेखातील उत्तर सुरू आहे. थांबवण्यासाठी मायक्रोफोन टॅप करा.', statusReady: 'तुमचे उत्तर तयार आहे. संबंधित अभिलेख पाहा.',
      queries: ['आंबेडकरांनी शिक्षणाबद्दल काय सांगितले?', 'महाड सत्याग्रह महत्त्वाचा का होता?', 'संविधान निर्मितीदरम्यान काय घडले?', 'सामाजिक न्यायावरील पुस्तके कोणती?']
    }
  };

  function setKioskLanguage(language) {
    kioskLanguage = kioskTranslations[language] ? language : 'en';
    const copy = kioskTranslations[kioskLanguage];
    document.documentElement.lang = kioskLanguage;
    document.querySelectorAll('.kiosk-languages button').forEach((button) => {
      const selected = button.dataset.language === kioskLanguage;
      button.classList.toggle('is-selected', selected);
      button.setAttribute('aria-pressed', String(selected));
    });
    document.querySelectorAll('[data-kcopy]').forEach((element) => {
      const value = copy[element.dataset.kcopy];
      if (value) element.innerHTML = value;
    });
    document.querySelectorAll('.prompt-question').forEach((button, index) => {
      button.dataset.question = copy.queries[index];
    });
    setState(state);
  }

  function scrollToSection(id) {
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  const kioskRouteViews = {
    '/': null,
    '/exhibits': 'exhibits',
    '/books': 'books',
    '/speeches': 'speeches',
    '/interviews': 'interviews',
    '/media': 'media',
    '/assistant': 'ask'
  };

  function routeTo(path, { replace = false } = {}) {
    const method = replace ? 'replaceState' : 'pushState';
    history[method]({ kiosk: true, from: location.pathname }, '', path);
    renderRoute();
  }

  function renderRoute() {
    const pathname = decodeURIComponent(location.pathname.replace(/\/+$/, '') || '/');
    document.querySelectorAll('#route-content audio, #route-content video').forEach((media) => media.pause());
    const detailMatch = pathname.match(/^\/(exhibits|books|speeches|interviews)\/([^/]+)$/);
    const root = pathname === '/';
    const detailPage = document.getElementById('route-page');
    const visibleSections = ['ask', 'exhibits', 'books', 'speeches', 'interviews', 'media', 'connections'];

    document.getElementById('welcome').hidden = !root;
    document.getElementById('home-featured').hidden = !root;
    visibleSections.forEach((id) => { document.getElementById(id).hidden = true; });
    detailPage.hidden = true;
    document.getElementById('route-back').hidden = root;
    document.getElementById('exhibit-detail').hidden = true;
    const routeSection = detailMatch ? `/${detailMatch[1]}` : pathname;
    document.querySelectorAll('.kiosk-nav a[data-route]').forEach((link) => {
      if (link.href === `${location.origin}${routeSection}`) link.setAttribute('aria-current', 'page');
      else link.removeAttribute('aria-current');
    });

    if (root) {
      document.getElementById('assistant-context').hidden = true;
      document.getElementById('route-content').replaceChildren();
      window.scrollTo({ top: 0, behavior: 'smooth' });
      return;
    }

    const contextParam = new URLSearchParams(location.search).get('context');
    if (detailMatch) {
      const [, kind, id] = detailMatch;
      const item = getContentItem(kind, id);
      detailPage.hidden = false;
      if (item) renderDetailPage(kind, item);
      else renderNotFound(pathname);
      window.scrollTo({ top: 0, behavior: 'smooth' });
      return;
    }

    const viewId = kioskRouteViews[pathname];
    if (!viewId) {
      detailPage.hidden = false;
      renderNotFound(pathname);
      window.scrollTo({ top: 0, behavior: 'smooth' });
      return;
    }

    const view = document.getElementById(viewId);
    view.hidden = false;
    if (viewId === 'ask') {
      showAssistantContext(contextParam);
    } else {
      document.getElementById('assistant-context').hidden = true;
    }
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function getContentItem(kind, id) {
    const collection = {
      exhibits: KIOSK_CONTENT.exhibits,
      books: KIOSK_CONTENT.books,
      speeches: KIOSK_CONTENT.speeches,
      interviews: KIOSK_CONTENT.interviews
    }[kind];
    return collection?.find((item) => item.id === id) || null;
  }

  function showAssistantContext(contextId) {
    assistantContextId = contextId || '';
    const panel = document.getElementById('assistant-context');
    const label = panel.querySelector('strong');
    let item = KIOSK_CONTENT.exhibits.find((exhibit) => exhibit.id === contextId);
    if (!item) item = KIOSK_CONTENT.books.find((book) => book.id === contextId);
    if (!item) item = KIOSK_CONTENT.speeches.find((speech) => speech.id === contextId);
    const knownTopics = { education: 'Education', mahad: 'Mahad Satyagraha', constitution: 'Constitution', socialjustice: 'Social Justice' };
    const title = item?.title || knownTopics[contextId] || contextId;
    panel.hidden = !contextId;
    label.textContent = title || '';
    currentExhibit = item && item.query ? item : null;
  }

  const relatedConcepts = [
    ['education', 'educate', 'school', 'schools', 'student', 'students', 'learning', 'learn', 'study', 'studies', 'university', 'शिक्षा', 'विद्यालय', 'छात्र'],
    ['mahad', 'satyagraha', 'chavdar', 'chawdar', 'tank', 'water access', 'महाड', 'सत्याग्रह'],
    ['constitution', 'drafting', 'draft', 'democracy', 'republic', 'संविधान', 'लोकतंत्र'],
    ['social justice', 'justice', 'equality', 'equal', 'rights', 'caste', 'discrimination', 'सामाजिक न्याय', 'समानता', 'जाति'],
    ['buddhism', 'buddhist', 'dhamma', 'deeksha', 'deekshabhoomi', 'conversion', 'बौद्ध', 'दीक्षाभूमि'],
    ['labour', 'labor', 'worker', 'workers', 'employment', 'कामगार', 'श्रम'],
    ['london', 'columbia', 'new york', 'economics', 'law', 'education abroad']
  ];

  function normalizeSearch(value) {
    return String(value || '').toLocaleLowerCase().normalize('NFKD').replace(/[\u0300-\u036f]/g, '').replace(/[^\p{L}\p{N}\s]/gu, ' ').replace(/\s+/g, ' ').trim();
  }

  function resolveRelatedContent(question, contextId = '') {
    let query = normalizeSearch(question);
    const contextItem = [...KIOSK_CONTENT.exhibits, ...KIOSK_CONTENT.books, ...KIOSK_CONTENT.speeches, ...KIOSK_CONTENT.interviews].find((item) => item.id === contextId);
    if (contextItem) query += ` ${normalizeSearch([contextItem.title, ...(contextItem.topics || []), ...(contextItem.keywords || [])].join(' '))}`;
    const expanded = new Set(query.split(' ').filter((word) => word.length > 2));
    relatedConcepts.forEach((concept) => {
      const normalizedConcept = concept.map(normalizeSearch);
      if (normalizedConcept.some((term) => term && query.includes(term))) normalizedConcept.forEach((term) => term.split(' ').forEach((word) => expanded.add(word)));
    });
    const searchText = ` ${[...expanded].join(' ')} `;
    const scoreRecord = (record) => {
      let score = 0;
      const addMatches = (values, weight) => {
        for (const value of values || []) {
          const term = normalizeSearch(value);
          if (term && (query.includes(term) || searchText.includes(` ${term} `))) score += weight;
        }
      };
      addMatches(record.topics, 4);
      addMatches(record.keywords, 2);
      addMatches(record.events, 2.5);
      addMatches(record.places, 2);
      addMatches(record.people, 0.5);
      return score;
    };
    const select = (records) => records.map((record) => ({ record, score: scoreRecord(record) })).filter((entry) => entry.score >= 3).sort((a, b) => b.score - a.score).slice(0, 3).map((entry) => entry.record);
    return {
      books: select(KIOSK_CONTENT.books),
      speeches: select(KIOSK_CONTENT.speeches),
      interviews: select(KIOSK_CONTENT.interviews),
      exhibits: select(KIOSK_CONTENT.exhibits),
      media: select(KIOSK_CONTENT.media)
    };
  }

  function renderRelatedGroups(groups, heading = 'RELATED TO THIS QUESTION') {
    const entries = Object.entries(groups || {}).filter(([, records]) => records?.length);
    if (!entries.length) return null;
    const panel = makeKioskElement('section', 'related-groups-panel');
    panel.appendChild(makeKioskElement('p', 'mini-label', heading));
    entries.forEach(([type, records]) => {
      const group = makeKioskElement('section', 'related-route-group');
      group.appendChild(makeKioskElement('h3', '', type.toUpperCase()));
      const cards = makeKioskElement('div', 'related-route-cards');
      records.forEach((record) => {
        const link = makeKioskElement('a', 'related-route-card');
        link.href = type === 'media' ? '/media' : `/${type}/${record.id}`;
        link.dataset.route = '';
        if (record.image || record.cover || record.thumbnail) {
          const image = makeKioskElement('img');
          image.src = record.image || record.cover || record.thumbnail;
          image.alt = '';
          link.appendChild(image);
        }
        link.append(makeKioskElement('strong', '', record.title), makeKioskElement('small', '', 'EXPLORE →'));
        cards.appendChild(link);
      });
      group.appendChild(cards);
      panel.appendChild(group);
    });
    return panel;
  }

  function renderNotFound(pathname) {
    const container = document.getElementById('route-content');
    container.replaceChildren();
    const wrapper = makeKioskElement('div', 'route-not-found');
    wrapper.append(makeKioskElement('p', 'section-kicker', 'ARCHIVE ROUTE'), makeKioskElement('h1', '', 'This collection record is not available.'), makeKioskElement('p', '', pathname));
    const back = makeKioskElement('a', 'button-secondary', '← BACK TO COLLECTIONS');
    back.href = '/';
    back.dataset.route = '';
    wrapper.appendChild(back);
    container.appendChild(wrapper);
  }

  function renderDetailPage(kind, item) {
    const container = document.getElementById('route-content');
    container.replaceChildren();
    const page = makeKioskElement('article', 'detail-page');
    const back = makeKioskElement('a', 'detail-back', '← BACK');
    back.href = `/${kind}`;
    back.dataset.route = '';
    page.appendChild(back);
    const imagePath = item.image || item.cover || item.thumbnail;
    const routedMediaUrl = (kind === 'speeches' || kind === 'interviews') ? safeResourceUrl(item.video || item.audio || '') : '';
    const media = makeKioskElement('div', 'detail-page-media');
    if (routedMediaUrl && getYouTubeId(routedMediaUrl)) {
      const frame = makeKioskElement('iframe');
      frame.src = `https://www.youtube-nocookie.com/embed/${encodeURIComponent(getYouTubeId(routedMediaUrl))}`;
      frame.title = item.title;
      frame.allow = 'accelerometer; autoplay; encrypted-media; gyroscope; picture-in-picture; fullscreen';
      frame.allowFullscreen = true;
      media.appendChild(frame);
    } else if (routedMediaUrl && /\.(?:mp3|wav|ogg|m4a)(?:[?#].*)?$/i.test(routedMediaUrl)) {
      const audio = makeKioskElement('audio');
      audio.controls = true;
      audio.src = routedMediaUrl;
      media.appendChild(audio);
    } else if (routedMediaUrl) {
      const video = makeKioskElement('video');
      video.controls = true;
      video.playsInline = true;
      video.src = routedMediaUrl;
      media.appendChild(video);
    } else if (imagePath) {
      const image = makeKioskElement('img');
      image.src = imagePath;
      image.alt = item.title || '';
      media.appendChild(image);
    } else if (kind === 'speeches' || kind === 'interviews') {
      media.append(makeKioskElement('span', '', 'VIDEO ARCHIVE'), makeKioskElement('small', '', 'RECORDING PENDING'));
    } else {
      media.innerHTML = '<span>ARCHIVAL RECORD</span><small>MEDIA PENDING</small>';
    }
    const copy = makeKioskElement('div', 'detail-page-copy');
    copy.append(makeKioskElement('p', 'section-kicker', `${kind.toUpperCase()} / DETAIL`), makeKioskElement('h1', '', item.title));
    const byline = item.author || item.speaker || item.interviewee || '';
    if (byline) copy.appendChild(makeKioskElement('p', 'detail-byline', byline));
    const metadata = [item.year, item.date, item.location, item.duration].filter(Boolean).join(' · ');
    if (metadata) copy.appendChild(makeKioskElement('p', 'detail-metadata', metadata));
    copy.appendChild(makeKioskElement('p', 'detail-description', item.description || 'Description pending.'));

    const facts = item.keyFacts || [];
    if (facts.length) {
      const factList = makeKioskElement('ul', 'detail-facts');
      facts.forEach((fact) => factList.appendChild(makeKioskElement('li', '', fact)));
      copy.appendChild(factList);
    }

    const topics = makeKioskElement('div', 'detail-topics');
    (item.topics || []).forEach((topic) => topics.appendChild(makeKioskElement('span', 'topic-tag', topic)));
    if (topics.childElementCount) copy.appendChild(topics);

    const actions = makeKioskElement('div', 'detail-actions');
    const localFile = safeResourceUrl(item.localFile || '');
    const source = safeExternalUrl(item.sourceUrl || item.source || item.url || '');
    if (kind === 'books') {
      const readUrl = localFile || source;
      const read = makeKioskElement(readUrl ? 'a' : 'button', 'button-primary', readUrl ? (localFile ? 'READ BOOK' : 'OPEN SOURCE') : 'SOURCE PENDING');
      if (readUrl) {
        read.href = readUrl;
        if (!localFile) { read.target = '_blank'; read.rel = 'noopener noreferrer'; }
      } else { read.type = 'button'; read.disabled = true; }
      actions.appendChild(read);
      if (localFile && source) {
        const sourceLink = makeKioskElement('a', 'detail-source-link', 'OPEN SOURCE ↗');
        sourceLink.href = source;
        sourceLink.target = '_blank';
        sourceLink.rel = 'noopener noreferrer';
        actions.appendChild(sourceLink);
      }
    } else if (kind === 'speeches' || kind === 'interviews') {
      const mediaUrl = safeResourceUrl(item.video || item.audio || '');
      const play = makeKioskElement(mediaUrl ? 'button' : 'button', 'button-primary', mediaUrl ? 'PLAY' : 'RECORDING PENDING');
      play.type = 'button';
      play.disabled = !mediaUrl;
      if (mediaUrl) play.addEventListener('click', () => openRoutedMedia(item, mediaUrl));
      actions.appendChild(play);
    }
    const ask = makeKioskElement('a', 'button-secondary', `ASK ABOUT THIS ${kind === 'books' ? 'BOOK' : kind === 'exhibits' ? 'EXHIBIT' : 'TOPIC'}`);
    ask.href = `/assistant?context=${encodeURIComponent(item.id)}`;
    ask.dataset.route = '';
    actions.appendChild(ask);
    if (source && kind !== 'books') {
      const sourceLink = makeKioskElement('a', 'detail-source-link', 'SOURCE ↗');
      sourceLink.href = source;
      sourceLink.target = '_blank';
      sourceLink.rel = 'noopener noreferrer';
      actions.appendChild(sourceLink);
    }
    copy.appendChild(actions);

    if (localFile && /\.pdf(?:[?#].*)?$/i.test(localFile)) {
      const reader = makeKioskElement('iframe', 'book-reader');
      reader.src = localFile;
      reader.title = `${item.title} PDF reader`;
      page.appendChild(reader);
    }
    if (item.transcript || item.segments?.length) {
      const transcript = makeKioskElement('section', 'detail-transcript');
      transcript.appendChild(makeKioskElement('h2', '', 'TRANSCRIPT'));
      if (item.transcript) transcript.appendChild(makeKioskElement('p', '', item.transcript));
      (item.segments || []).forEach((segment) => transcript.appendChild(makeKioskElement('p', 'timestamp-segment', `${segment.timestamp} ${segment.text}`)));
      page.appendChild(transcript);
    }

    const related = resolveRelatedContent(`${item.title} ${(item.topics || []).join(' ')}`, item.id);
    const relatedPanel = renderRelatedGroups(related, 'RELATED COLLECTIONS');
    if (relatedPanel) page.appendChild(relatedPanel);
    back.after(media);
    media.after(copy);
    container.appendChild(page);
  }

  function openRoutedMedia(item, url) {
    const stage = document.getElementById('speech-viewer-stage');
    stage.replaceChildren();
    const youtubeId = getYouTubeId(url);
    if (youtubeId) {
      const frame = makeKioskElement('iframe');
      frame.src = `https://www.youtube-nocookie.com/embed/${encodeURIComponent(youtubeId)}`;
      frame.title = item.title;
      frame.allow = 'accelerometer; autoplay; encrypted-media; gyroscope; picture-in-picture; fullscreen';
      frame.allowFullscreen = true;
      stage.appendChild(frame);
    } else if (/\.(?:mp3|wav|ogg|m4a)(?:[?#].*)?$/i.test(url)) {
      const player = makeKioskElement('audio');
      player.controls = true;
      player.src = url;
      stage.appendChild(player);
    } else {
      const video = makeKioskElement('video');
      video.controls = true;
      video.playsInline = true;
      video.src = url;
      stage.appendChild(video);
    }
    document.getElementById('speech-viewer-title').textContent = item.title;
    document.getElementById('speech-viewer-meta').textContent = [item.speaker || item.interviewee, item.date, item.location, item.duration].filter(Boolean).join(' · ');
    document.getElementById('speech-viewer-description').textContent = item.description || '';
    openKioskModal(document.getElementById('speech-viewer'));
  }

  document.addEventListener('click', (event) => {
    const link = event.target.closest('a[data-route]');
    if (!link || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const target = new URL(link.href, location.href);
    if (target.origin !== location.origin) return;
    event.preventDefault();
    routeTo(`${target.pathname}${target.search}${target.hash}`);
  });
  document.getElementById('route-back').addEventListener('click', () => {
    const path = decodeURIComponent(location.pathname);
    const match = path.match(/^\/(exhibits|books|speeches|interviews)\/[^/]+$/);
    const fallback = match ? `/${match[1]}` : '/';
    if (history.state?.kiosk && history.state.from === fallback) history.back();
    else routeTo(fallback);
  });
  window.addEventListener('popstate', renderRoute);

  function closeKioskModals() {
    document.querySelectorAll('.kiosk-modal:not([hidden])').forEach((modal) => {
      modal.hidden = true;
      const video = modal.querySelector('video');
      if (video) {
        video.pause();
        video.removeAttribute('src');
        video.load();
      }
      modal.querySelectorAll('iframe').forEach((frame) => frame.remove());
    });
    kioskModalOpen = false;
  }

  function clearKioskAnswer() {
    kioskAnswer.hidden = true;
    kioskQuestion.textContent = '';
    kioskAnswerCopy.textContent = '';
    kioskRelated.innerHTML = '';
    kioskRelatedWrap.hidden = true;
    document.getElementById('answer-audio-toggle').disabled = true;
    document.getElementById('answer-audio-toggle').textContent = '▶ LISTEN';
    document.getElementById('answer-audio-time').textContent = '';
  }

  function resetKiosk({ showAttract = false } = {}) {
    clearTimeout(kioskIdleTimer);
    kioskRequestVersion += 1;
    closeKioskModals();
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
      mediaRecorder.onstop = null;
      mediaRecorder.stop();
    }
    if (micStream) {
      micStream.getTracks().forEach((track) => track.stop());
      micStream = null;
    }
    stopOrbPulse();
    audioPlayer.pause();
    audioPlayer.removeAttribute('src');
    audioPlayer.load();
    clearTourTurn();
    setState('idle');
    setLayoutActive(false);
    currentExhibit = null;
    assistantContextId = '';
    document.getElementById('exhibit-detail').hidden = true;
    kioskAttract.hidden = !showAttract;
    if (location.pathname !== '/') history.pushState({ kiosk: true }, '', '/');
    renderRoute();
    window.scrollTo({ top: 0, behavior: 'smooth' });
    if (!showAttract) scheduleKioskIdleReset();
  }

  function scheduleKioskIdleReset() {
    clearTimeout(kioskIdleTimer);
    kioskIdleTimer = setTimeout(() => {
      const mediaPlaying = [...document.querySelectorAll('.kiosk-modal audio, .kiosk-modal video, #route-content audio, #route-content video')].some((media) => !media.paused);
      if (state !== 'idle' || !audioPlayer.paused || kioskModalOpen || mediaPlaying) {
        scheduleKioskIdleReset();
        return;
      }
      resetKiosk({ showAttract: true });
    }, 60000);
  }

  function registerKioskActivity(event) {
    if (!kioskAttract.hidden) {
      if (!['pointerdown', 'touchstart', 'click', 'keydown'].includes(event.type)) return;
      kioskAttract.hidden = true;
      scrollToSection('welcome');
    }
    scheduleKioskIdleReset();
  }

  document.getElementById('start-over').addEventListener('click', () => resetKiosk());
  document.getElementById('floating-ask').addEventListener('click', () => routeTo('/assistant'));
  kioskMic.addEventListener('click', () => orb.click());
  document.querySelectorAll('.kiosk-languages button').forEach((button) => {
    button.addEventListener('click', () => setKioskLanguage(button.dataset.language));
  });
  ['pointerdown', 'touchmove', 'wheel', 'scroll', 'keydown'].forEach((eventName) => {
    document.addEventListener(eventName, registerKioskActivity, { passive: eventName !== 'keydown' });
  });
  scheduleKioskIdleReset();

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
      const copy = kioskTranslations[kioskLanguage];
      const kioskLabels = { idle: copy.micIdle, listening: copy.micListening, processing: copy.micProcessing, speaking: copy.micSpeaking };
      document.getElementById('kiosk-mic-label').textContent = kioskLabels[next] || kioskLabels.idle;
      document.querySelector('.voice-station').classList.toggle('is-listening', next === 'listening');
      if (next === 'listening') {
        voiceStatus.textContent = copy.statusListening;
      } else if (next === 'processing') {
        voiceStatus.textContent = copy.statusProcessing;
        kioskAnswer.hidden = false;
        kioskAnswerState.textContent = 'SEARCHING THE ARCHIVE';
        if (!kioskAnswerCopy.textContent) kioskAnswerCopy.textContent = copy.statusProcessing;
      } else if (next === 'speaking') {
        voiceStatus.textContent = copy.statusSpeaking;
      } else if (!kioskAnswer.hidden && kioskAnswerCopy.textContent) {
        voiceStatus.textContent = copy.statusReady;
        if (kioskAnswerState.textContent !== 'SEARCHING THE ARCHIVE') kioskAnswerState.textContent = 'ARCHIVE ANSWER';
      } else {
        voiceStatus.textContent = copy.statusIdle;
      }
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
      kioskMic.style.setProperty('--voice-scale', scale.toFixed(3));
      const voiceHalo = document.querySelector('.voice-halo');
      if (voiceHalo) voiceHalo.style.opacity = glowOpacity.toFixed(2);

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
    kioskMic.style.removeProperty('--voice-scale');
    const voiceHalo = document.querySelector('.voice-halo');
    if (voiceHalo) voiceHalo.style.opacity = '';
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
    getAudioContext();
    audioPlayer.pause();
    stopOrbPulse();
    clearTourTurn();
    isCurrentHindi = /[\u0900-\u097F]/.test(query);
    const userTag = transcriptUser.querySelector('.transcript-tag');
    if (userTag) userTag.textContent = isCurrentHindi ? 'आप / You' : 'You';
    setState('processing');
    setLayoutActive(true);
    userTextEl.textContent = query;
    transcriptUser.classList.remove('hidden');
    transcriptUser.classList.add('entering');
    kioskQuestion.textContent = query;
    kioskAnswer.hidden = false;
    kioskAnswerCopy.textContent = 'Searching the memorial archive…';

    const fd = new FormData();
    fd.append('query', query);
    sendConverseRequest(fd);
  }

  /* ===== Send to FastAPI backend ===== */
  async function sendConverseRequest(formData) {
    const requestVersion = ++kioskRequestVersion;
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
      if (requestVersion !== kioskRequestVersion) return;
      kioskAnswerState.textContent = 'PREPARING YOUR ANSWER';
      handleConverseResponse(data);
    } catch (err) {
      if (requestVersion !== kioskRequestVersion) return;
      console.error('Converse request failed:', err);
      showToast('Guide communication error — please try again');
      kioskAnswer.hidden = false;
      kioskQuestion.textContent = userTextEl.textContent || 'Your question';
      kioskAnswerCopy.textContent = 'The archive could not be reached. Please try again.';
      kioskAnswerState.textContent = 'CONNECTION UNAVAILABLE';
      setState('idle');
      voiceStatus.textContent = 'The archive could not be reached. Please try again.';
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
    renderArtifacts(data.artifacts || [], data);
    renderKioskAnswer(data);

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
    clearKioskAnswer();
  }

  /* ===== Staggered Artifact Cards Rendering ===== */
  function renderArtifacts(artifacts, related = {}) {
    artifactsGrid.innerHTML = '';
    const relatedItems = [
      ...(Array.isArray(related.related_speeches) ? related.related_speeches.map(item => ({ ...item, type: 'speech' })) : []),
      ...(Array.isArray(related.related_locations) ? related.related_locations.map(item => ({ ...item, type: 'location' })) : []),
      ...(Array.isArray(related.related_books) ? related.related_books.map(item => ({ ...item, type: 'book' })) : []),
    ];
    const allArtifacts = [...(artifacts || []), ...relatedItems];
    if (allArtifacts.length === 0) {
      if (artifactsArea) artifactsArea.classList.add('hidden');
      return;
    }

    if (artifactsArea) artifactsArea.classList.remove('hidden');

    if (allArtifacts.length === 1) {
      artifactsGrid.classList.add('single-record');
    } else {
      artifactsGrid.classList.remove('single-record');
    }

    if (artifactsBadge) {
      const badgeText = isCurrentHindi
        ? (allArtifacts.length === 1 ? 'विशेष प्रदर्शनी' : `${allArtifacts.length} अभिलेख`)
        : (allArtifacts.length === 1 ? 'Featured Exhibit' : `${allArtifacts.length} Records`);
      artifactsBadge.textContent = badgeText;
    }

    const panelTitle = document.querySelector('.artifacts-panel-header h2');
    if (panelTitle) {
      panelTitle.textContent = isCurrentHindi ? 'प्रदर्शनी अभिलेखागार' : 'Exhibition Archives';
    }

    allArtifacts.forEach((artifact, index) => {
      const card = document.createElement('div');
      card.className = 'artifact-card';
      // Staggered slide-in animation delay
      card.style.animationDelay = (index * 130) + 'ms';

      const type = (artifact.type || 'photo').toLowerCase();
      if (type === 'speech' || type === 'location' || type === 'book') {
        const labels = { speech: 'Related Speech', location: 'Related Location', book: 'Related Book' };
        let details = '';
        if (type === 'speech') {
          if (artifact.speaker) details += `<p class="related-meta">${escHtml(artifact.speaker)}</p>`;
          if (artifact.date) details += `<p class="related-meta">${escHtml(artifact.date)}</p>`;
          if (artifact.venue) details += `<p class="related-meta">${escHtml(artifact.venue)}</p>`;
        } else if (type === 'location') {
          if (artifact.city) details += `<p class="related-meta">${escHtml(artifact.city)}</p>`;
        } else {
          const publication = [artifact.author, artifact.year].filter(value => value !== undefined && value !== null && value !== '').join(' · ');
          if (publication) details += `<p class="related-meta">${escHtml(publication)}</p>`;
          if (artifact.publisher) details += `<p class="related-meta">${escHtml(artifact.publisher)}</p>`;
        }
        const description = artifact.summary || artifact.description || '';
        const sourceUrl = safeExternalUrl(artifact.source_url);
        card.classList.add('related-card', `related-${type}`);
        card.innerHTML = `<div class="card-body"><span class="card-type type-${type}">${labels[type]}</span><h3 class="card-title">${escHtml(artifact.title || artifact.name || '')}</h3>${details}${description ? `<p class="card-caption">${escHtml(description)}</p>` : ''}${sourceUrl ? `<a class="card-action" href="${escHtml(sourceUrl)}" target="_blank" rel="noopener noreferrer">Read speech</a>` : ''}</div>`;
        artifactsGrid.appendChild(card);
        return;
      }

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

      const cardImage = card.querySelector('.card-image');
      if (cardImage) {
        cardImage.tabIndex = 0;
        cardImage.setAttribute('role', 'button');
        cardImage.setAttribute('aria-label', `View full image: ${artifact.title || 'Museum Exhibit'}`);
      }

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

  function makeKioskElement(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  }

  function renderKioskContent() {
    const content = KIOSK_CONTENT;
    const exhibitGrid = document.getElementById('exhibit-grid');
    const bookGrid = document.getElementById('book-grid');
    const speechGrid = document.getElementById('speech-grid');
    const interviewGrid = document.getElementById('interview-grid');
    const mediaGrid = document.getElementById('media-grid');
    const featuredGrid = document.getElementById('home-featured-grid');

    content.exhibits.forEach((exhibit, index) => {
      const card = makeKioskElement('a', 'exhibit-card');
      card.href = `/exhibits/${exhibit.id}`;
      card.dataset.route = '';
      card.style.setProperty('--card-image', `url("${exhibit.image}")`);
      card.innerHTML = `<span class="card-index">0${index + 1}</span><span class="exhibit-card-copy"><strong></strong><span class="exhibit-card-description"></span><small>EXPLORE <b>↗</b></small></span>`;
      card.querySelector('strong').textContent = exhibit.title;
      card.querySelector('.exhibit-card-description').textContent = exhibit.description;
      exhibitGrid.appendChild(card);
    });

    content.books.forEach((book, index) => {
      const card = makeKioskElement('article', 'book-record');
      const cover = makeKioskElement('div', 'book-cover');
      if (book.cover) {
        const image = makeKioskElement('img');
        image.src = book.cover;
        image.alt = `${book.title} cover`;
        cover.appendChild(image);
      } else {
        cover.innerHTML = '<span>BOOK COVER</span><i></i><small>SOURCE LINK<br />PENDING</small>';
      }
      const body = makeKioskElement('div', 'book-record-copy');
      body.append(makeKioskElement('span', 'record-index', `RECORD 0${index + 1}`), makeKioskElement('h3', '', book.title), makeKioskElement('p', 'record-author', book.author));
      if (book.year) body.appendChild(makeKioskElement('p', 'record-meta', book.year));
      body.appendChild(makeKioskElement('p', 'record-description', book.description));
      const action = makeKioskElement('a', 'record-action', 'BOOK DETAILS ↗');
      action.href = `/books/${book.id}`;
      action.dataset.route = '';
      body.appendChild(action);
      card.append(cover, body);
      bookGrid.appendChild(card);
    });

    content.speeches.forEach((speech, index) => speechGrid.appendChild(renderIndexedMediaCard(speech, 'speeches', index)));
    content.interviews.forEach((interview, index) => interviewGrid.appendChild(renderIndexedMediaCard(interview, 'interviews', index)));

    content.media.forEach((item, index) => {
      const card = makeKioskElement('button', 'media-card');
      card.type = 'button';
      card.setAttribute('aria-label', `View ${item.title}`);
      const image = makeKioskElement('img');
      image.src = item.image;
      image.alt = '';
      card.append(image, makeKioskElement('span', 'media-card-title', item.title), makeKioskElement('span', 'media-card-number', `0${index + 1}`));
      card.addEventListener('click', () => openMedia(item));
      mediaGrid.appendChild(card);
    });

    const featured = [
      ...content.exhibits.slice(0, 2).map((item) => ({ ...item, kind: 'exhibits', image: item.image })),
      ...content.books.slice(0, 1).map((item) => ({ ...item, kind: 'books', image: item.cover })),
      ...content.speeches.slice(0, 1).map((item) => ({ ...item, kind: 'speeches', image: item.thumbnail }))
    ];
    featured.forEach((item) => {
      const link = makeKioskElement('a', 'home-featured-card');
      link.href = `/${item.kind}/${item.id}`;
      link.dataset.route = '';
      if (item.image) link.style.setProperty('--feature-image', `url("${item.image}")`);
      link.append(makeKioskElement('small', '', item.kind.toUpperCase()), makeKioskElement('strong', '', item.title), makeKioskElement('span', '', 'OPEN RECORD →'));
      featuredGrid.appendChild(link);
    });
  }

  function renderIndexedMediaCard(item, kind, index) {
    const card = makeKioskElement('article', 'speech-card');
    const image = makeKioskElement('div', 'speech-card-image');
    if (item.thumbnail) {
      const thumbnail = makeKioskElement('img');
      thumbnail.src = item.thumbnail;
      thumbnail.alt = '';
      image.appendChild(thumbnail);
    } else {
      image.innerHTML = '<span class="record-play" aria-hidden="true">▶</span><small>MEDIA ARCHIVE</small>';
    }
    const info = makeKioskElement('div', 'speech-card-copy');
    info.append(makeKioskElement('span', 'record-index', `MEDIA RECORD 0${index + 1}`), makeKioskElement('h3', '', item.title));
    const person = item.speaker || item.interviewee;
    if (person) info.appendChild(makeKioskElement('p', 'record-author', person));
    if (item.date || item.location || item.duration) info.appendChild(makeKioskElement('p', 'record-meta', [item.date, item.location, item.duration].filter(Boolean).join(' · ')));
    info.appendChild(makeKioskElement('p', 'record-description', item.description));
    const action = makeKioskElement('a', 'record-action', 'VIEW DETAIL ↗');
    action.href = `/${kind}/${item.id}`;
    action.dataset.route = '';
    info.appendChild(action);
    card.append(image, info);
    return card;
  }

  function openKioskModal(modal) {
    closeKioskModals();
    modal.hidden = false;
    kioskModalOpen = true;
  }

  function openMedia(item) {
    const stage = document.getElementById('media-viewer-stage');
    stage.replaceChildren();
    const image = makeKioskElement('img');
    image.src = item.image;
    image.alt = item.title;
    stage.appendChild(image);
    document.getElementById('media-viewer-title').textContent = item.title;
    document.getElementById('media-viewer-description').textContent = [item.caption, item.source].filter(Boolean).join(' ');
    openKioskModal(document.getElementById('kiosk-media-viewer'));
  }

  function openSpeech(speech) {
    const stage = document.getElementById('speech-viewer-stage');
    stage.replaceChildren();
    if (speech.video) {
      const youtubeId = getYouTubeId(speech.video);
      if (youtubeId) {
        const frame = makeKioskElement('iframe');
        frame.src = `https://www.youtube-nocookie.com/embed/${encodeURIComponent(youtubeId)}`;
        frame.title = speech.title;
        frame.allow = 'accelerometer; autoplay; encrypted-media; gyroscope; picture-in-picture; fullscreen';
        frame.allowFullscreen = true;
        stage.appendChild(frame);
      } else {
        const video = makeKioskElement('video');
        video.controls = true;
        video.playsInline = true;
        video.src = speech.video;
        stage.appendChild(video);
      }
    } else {
      stage.innerHTML = '<span class="record-play" aria-hidden="true">▶</span><p>VIDEO ARCHIVE</p><small>Recording will be added</small>';
    }
    document.getElementById('speech-viewer-title').textContent = speech.title;
    document.getElementById('speech-viewer-meta').textContent = [speech.speaker, speech.date, speech.duration].filter(Boolean).join(' · ');
    document.getElementById('speech-viewer-description').textContent = speech.description || '';
    const transcript = document.getElementById('speech-transcript');
    transcript.hidden = !speech.transcript && !speech.segments?.length;
    transcript.querySelector('p:last-child').textContent = speech.transcript || '';
    transcript.querySelectorAll('.timestamp-segment').forEach((segment) => segment.remove());
    (speech.segments || []).forEach((segment) => {
      const item = makeKioskElement('p', 'timestamp-segment', `${segment.timestamp} ${segment.text}`);
      transcript.appendChild(item);
    });
    openKioskModal(document.getElementById('speech-viewer'));
  }

  function getYouTubeId(value) {
    try {
      const url = new URL(value);
      if (url.hostname.endsWith('youtu.be')) return url.pathname.slice(1);
      if (url.hostname.includes('youtube.com')) return url.searchParams.get('v') || url.pathname.split('/').filter(Boolean).at(-1);
    } catch (_) {
      return '';
    }
    return '';
  }

  function renderKioskAnswer(data) {
    kioskQuestion.textContent = data.transcript || userTextEl.textContent || 'Your question';
    kioskAnswerCopy.textContent = data.text || '';
    kioskAnswerState.textContent = 'ARCHIVE ANSWER';
    kioskAnswer.hidden = false;
    kioskRelated.replaceChildren();
    const resolved = resolveRelatedContent(data.transcript || userTextEl.textContent, assistantContextId);
    const localGroups = renderRelatedGroups(resolved, `EXPLORE THIS TOPIC · ${data.transcript || 'RELATED CONTENT'}`);
    if (localGroups) kioskRelated.appendChild(localGroups);

    const backendItems = [
      ...(data.artifacts || []).map((item) => ({ ...item, recordType: item.type || 'archive' })),
      ...(data.related_speeches || []).map((item) => ({ ...item, recordType: 'speech' })),
      ...(data.related_locations || []).map((item) => ({ ...item, recordType: 'location' })),
      ...(data.related_books || []).map((item) => ({ ...item, recordType: 'book' }))
    ];
    if (backendItems.length) {
      const sourceGroup = makeKioskElement('section', 'related-groups-panel');
      sourceGroup.appendChild(makeKioskElement('p', 'mini-label', 'ARCHIVE SOURCES'));
      const cards = makeKioskElement('div', 'related-route-cards');
      backendItems.forEach((item) => {
        const record = makeKioskElement('article', 'related-record');
        record.append(makeKioskElement('span', 'record-index', String(item.recordType).toUpperCase()), makeKioskElement('h3', '', item.title || item.name || item.city || 'Archive record'));
        const description = item.summary || item.description || item.caption || [item.speaker, item.author, item.year, item.date, item.city].filter(Boolean).join(' · ');
        if (description) record.appendChild(makeKioskElement('p', 'related-record-description', description));
        const sourceUrl = safeExternalUrl(item.source_url);
        if (sourceUrl) {
          const source = makeKioskElement('a', 'related-record-source', 'SOURCE ↗');
          source.href = sourceUrl;
          source.target = '_blank';
          source.rel = 'noopener noreferrer';
          record.appendChild(source);
        }
        cards.appendChild(record);
      });
      sourceGroup.appendChild(cards);
      kioskRelated.appendChild(sourceGroup);
    }
    if (!kioskRelated.childElementCount) kioskRelated.appendChild(makeKioskElement('p', 'no-related-records', 'No indexed local records match this topic yet.'));
    kioskRelatedWrap.hidden = false;
    document.getElementById('answer-audio-toggle').disabled = !data.audio_url;
    if (location.pathname === '/assistant') kioskAnswer.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  function safeExternalUrl(value) {
    if (!value) return '';
    try {
      const url = new URL(value);
      return url.protocol === 'https:' || url.protocol === 'http:' ? url.href : '';
    } catch (_) {
      return '';
    }
  }

  function safeResourceUrl(value) {
    if (!value || typeof value !== 'string') return '';
    const external = safeExternalUrl(value);
    if (external) return external;
    return /^(?:\/static\/|\.\/|\.\.\/)[^\s]*\.(?:pdf|mp4|webm|mp3|wav|ogg|m4a)(?:[?#].*)?$/i.test(value) ? value : '';
  }

  function openImageViewer(image) {
    imageViewerOpen = true;
    imageViewerScrollTop = window.scrollY;
    imageViewerReturnFocus = image;
    imageViewerImage.src = image.currentSrc || image.src;
    imageViewerImage.alt = image.alt || 'Exhibit image';
    imageViewer.classList.remove('hidden');
    imageViewer.setAttribute('aria-hidden', 'false');
    document.documentElement.classList.add('viewer-open');
    app.inert = true;
    closeImageViewerButton.focus({ preventScroll: true });
  }

  function closeImageViewer() {
    if (!imageViewerOpen) return;
    imageViewerOpen = false;
    imageViewer.classList.add('hidden');
    imageViewer.setAttribute('aria-hidden', 'true');
    imageViewerImage.removeAttribute('src');
    imageViewerImage.alt = '';
    document.documentElement.classList.remove('viewer-open');
    app.inert = false;
    window.scrollTo(0, imageViewerScrollTop);
    if (imageViewerReturnFocus && imageViewerReturnFocus.isConnected) {
      imageViewerReturnFocus.focus({ preventScroll: true });
    }
    imageViewerReturnFocus = null;
  }

  function setupMousePageScroll() {
    let gesture = null;
    app.addEventListener('pointerdown', (event) => {
      if (imageViewerOpen || event.pointerType !== 'mouse' || event.button !== 0) return;
      if (event.target.closest('button, input, textarea, select, a, [role="button"], [role="link"], [contenteditable="true"]')) return;
      gesture = { pointerId: event.pointerId, startY: event.clientY, lastY: event.clientY, moved: false };
      app.setPointerCapture(event.pointerId);
    });
    app.addEventListener('pointermove', (event) => {
      if (!gesture || event.pointerId !== gesture.pointerId) return;
      if (Math.abs(event.clientY - gesture.startY) > 3) {
        gesture.moved = true;
        app.classList.add('pointer-scrolling');
      }
      if (gesture.moved) window.scrollBy(0, gesture.lastY - event.clientY);
      gesture.lastY = event.clientY;
    });
    function finishGesture(event) {
      if (!gesture || (event && event.pointerId !== gesture.pointerId)) return;
      gesture = null;
      app.classList.remove('pointer-scrolling');
    }
    app.addEventListener('pointerup', finishGesture);
    app.addEventListener('pointercancel', finishGesture);
    app.addEventListener('lostpointercapture', finishGesture);
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

  artifactsGrid.addEventListener('click', (event) => {
    const image = event.target.closest?.('.card-image');
    if (image) openImageViewer(image);
  });

  artifactsGrid.addEventListener('keydown', (event) => {
    const image = event.target.closest?.('.card-image');
    if (!image || (event.key !== 'Enter' && event.key !== ' ')) return;
    event.preventDefault();
    openImageViewer(image);
  });

  closeImageViewerButton.addEventListener('click', closeImageViewer);
  imageViewer.addEventListener('click', (event) => {
    if (event.target === imageViewer) closeImageViewer();
  });
  document.addEventListener('keydown', (event) => {
    if (imageViewerOpen && event.key === 'Escape') {
      event.preventDefault();
      closeImageViewer();
    }
  });

  document.querySelectorAll('.prompt-question').forEach((button) => {
    button.addEventListener('click', () => sendTextQuery(button.dataset.question));
  });
  document.getElementById('exhibit-ask').addEventListener('click', () => {
    document.getElementById('exhibit-detail').hidden = true;
    voiceStatus.textContent = currentExhibit
      ? `Ask a question about ${currentExhibit.title}. The guide will use the available archive.`
      : 'Ask about a topic from the memorial archive.';
    scrollToSection('ask');
  });
  document.getElementById('exhibit-close').addEventListener('click', () => {
    document.getElementById('exhibit-detail').hidden = true;
    currentExhibit = null;
  });
  document.querySelectorAll('[data-close-modal]').forEach((button) => {
    button.addEventListener('click', closeKioskModals);
  });
  document.querySelectorAll('.kiosk-modal').forEach((modal) => {
    modal.addEventListener('pointerdown', (event) => {
      if (event.target === modal) closeKioskModals();
    });
  });
  const answerAudioToggle = document.getElementById('answer-audio-toggle');
  answerAudioToggle.addEventListener('click', () => {
    if (!audioPlayer.src) return;
    if (audioPlayer.paused) {
      getAudioContext();
      audioPlayer.play().then(() => startOrbPulse(setupPlayerAudio())).catch(() => {});
    } else {
      audioPlayer.pause();
      stopOrbPulse();
      setState('idle');
    }
  });
  audioPlayer.addEventListener('play', () => { answerAudioToggle.textContent = 'Ⅱ PAUSE'; });
  audioPlayer.addEventListener('pause', () => {
    answerAudioToggle.textContent = '▶ LISTEN';
    document.getElementById('answer-audio-time').textContent = '';
  });
  audioPlayer.addEventListener('timeupdate', () => {
    const formatTime = (seconds) => `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`;
    document.getElementById('answer-audio-time').textContent = `${formatTime(audioPlayer.currentTime)} / ${formatTime(audioPlayer.duration || 0)}`;
  });

  renderKioskContent();
  setKioskLanguage('en');
  renderRoute();

  /* ===== Initial demo state ===== */
  setState('idle');

})();
