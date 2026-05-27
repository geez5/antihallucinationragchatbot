/**
 * chatbot.js — Veritas AI Chat Widget
 * =====================================
 * Zero-dependency, self-contained floating chat widget.
 * Drop one <script src="chatbot.js"></script> tag into any page.
 *
 * To point at a different backend, change API_URL below.
 */
(function () {
  "use strict";

  // ============================================================
  // CONFIG — change API_URL to your deployed backend when ready
  // ============================================================
  const API_URL   = "http://localhost:8000";
  const MAX_CHARS = 500;          // mirrors backend validation
  const HISTORY_TURNS = 8;       // how many prior turns to send

  // ============================================================
  // STATE
  // ============================================================
  let isOpen      = false;
  let isWaiting   = false;
  let chatHistory = [];           // [{role, content}, ...]
  let lastQuestion = "";
  const sessionId = "sess-" + Math.random().toString(36).slice(2, 11);

  // ============================================================
  // CSS
  // ============================================================
  const CSS = `
    /* ── Reset scoped to widget ─────────────────────────────── */
    #vrt-root *, #vrt-root *::before, #vrt-root *::after {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }

    /* ── Host container ─────────────────────────────────────── */
    #vrt-root {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
                   Helvetica, Arial, sans-serif;
      font-size: 14px;
      line-height: 1.5;
      color: #111827;
      position: fixed;
      bottom: 24px;
      right: 24px;
      z-index: 2147483647;
    }

    /* ── Bubble trigger ─────────────────────────────────────── */
    #vrt-bubble {
      width: 56px;
      height: 56px;
      border-radius: 50%;
      background: #111827;
      box-shadow: 0 4px 20px rgba(17,24,39,0.35);
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      border: none;
      outline: none;
      position: relative;
      transition: transform 0.25s cubic-bezier(.34,1.56,.64,1),
                  box-shadow 0.25s ease;
    }
    #vrt-bubble:hover {
      transform: scale(1.1);
      box-shadow: 0 8px 28px rgba(17,24,39,0.45);
    }
    #vrt-bubble:active { transform: scale(0.97); }

    /* notification pulse ring */
    #vrt-bubble::after {
      content: "";
      position: absolute;
      inset: -4px;
      border-radius: 50%;
      border: 2px solid rgba(17,24,39,0.25);
      animation: vrt-pulse 2.5s ease-out infinite;
      pointer-events: none;
    }
    @keyframes vrt-pulse {
      0%   { opacity: 1;  transform: scale(1);    }
      70%  { opacity: 0;  transform: scale(1.55); }
      100% { opacity: 0;  transform: scale(1.55); }
    }

    #vrt-bubble svg { pointer-events: none; }

    /* icon morph: chat ↔ close */
    #vrt-icon-chat,
    #vrt-icon-close {
      position: absolute;
      transition: opacity 0.2s ease, transform 0.25s ease;
    }
    #vrt-icon-close {
      opacity: 0;
      transform: rotate(-90deg);
    }
    #vrt-root.vrt-open #vrt-icon-chat  { opacity: 0; transform: rotate(90deg);  }
    #vrt-root.vrt-open #vrt-icon-close { opacity: 1; transform: rotate(0deg);   }

    /* ── Chat window ────────────────────────────────────────── */
    #vrt-window {
      position: absolute;
      bottom: 68px;
      right: 0;
      width: 370px;
      height: 540px;
      background: #fff;
      border-radius: 18px;
      box-shadow: 0 12px 48px rgba(17,24,39,0.18),
                  0 2px 8px rgba(17,24,39,0.08);
      display: flex;
      flex-direction: column;
      overflow: hidden;

      /* entrance animation */
      transform-origin: bottom right;
      transform: scale(0.88) translateY(12px);
      opacity: 0;
      pointer-events: none;
      transition: transform 0.3s cubic-bezier(.34,1.28,.64,1),
                  opacity  0.25s ease;
    }
    #vrt-root.vrt-open #vrt-window {
      transform: scale(1) translateY(0);
      opacity: 1;
      pointer-events: all;
    }

    /* ── Header ─────────────────────────────────────────────── */
    #vrt-header {
      background: #111827;
      padding: 14px 18px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-shrink: 0;
      border-radius: 18px 18px 0 0;
    }
    #vrt-header-left {
      display: flex;
      align-items: center;
      gap: 10px;
    }
    #vrt-avatar {
      width: 36px;
      height: 36px;
      border-radius: 50%;
      background: linear-gradient(135deg, #1e3a5f 0%, #2563eb 100%);
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 16px;
      flex-shrink: 0;
    }
    #vrt-header-info { display: flex; flex-direction: column; gap: 2px; }
    #vrt-header-title {
      color: #fff;
      font-weight: 600;
      font-size: 14px;
      letter-spacing: -0.01em;
    }
    #vrt-status {
      display: flex;
      align-items: center;
      gap: 5px;
      color: #9ca3af;
      font-size: 11px;
    }
    #vrt-status-dot {
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: #10b981;
      box-shadow: 0 0 0 2px rgba(16,185,129,0.25);
    }
    #vrt-close-btn {
      background: rgba(255,255,255,0.1);
      border: none;
      border-radius: 8px;
      width: 30px;
      height: 30px;
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      color: #9ca3af;
      transition: background 0.2s, color 0.2s;
      flex-shrink: 0;
    }
    #vrt-close-btn:hover { background: rgba(255,255,255,0.18); color: #fff; }

    /* ── Messages area ──────────────────────────────────────── */
    #vrt-messages {
      flex: 1;
      overflow-y: auto;
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 14px;
      scroll-behavior: smooth;
    }
    /* custom scrollbar */
    #vrt-messages::-webkit-scrollbar { width: 4px; }
    #vrt-messages::-webkit-scrollbar-thumb {
      background: #e5e7eb;
      border-radius: 4px;
    }

    /* ── Message rows ───────────────────────────────────────── */
    .vrt-row {
      display: flex;
      flex-direction: column;
      max-width: 88%;
      animation: vrt-fadein 0.28s ease;
    }
    @keyframes vrt-fadein {
      from { opacity: 0; transform: translateY(6px); }
      to   { opacity: 1; transform: translateY(0);   }
    }
    .vrt-row.vrt-user { align-self: flex-end; align-items: flex-end; }
    .vrt-row.vrt-bot  { align-self: flex-start; align-items: flex-start; }

    /* ── Bubbles ────────────────────────────────────────────── */
    .vrt-bubble-text {
      padding: 11px 15px;
      border-radius: 16px;
      font-size: 13.5px;
      line-height: 1.55;
      word-break: break-word;
    }
    .vrt-row.vrt-user .vrt-bubble-text {
      background: #111827;
      color: #fff;
      border-bottom-right-radius: 4px;
    }
    .vrt-row.vrt-bot .vrt-bubble-text {
      background: #f3f4f6;
      color: #111827;
      border-bottom-left-radius: 4px;
    }

    /* ── Source citation ────────────────────────────────────── */
    .vrt-source {
      margin-top: 5px;
      font-size: 11.5px;
      color: #6b7280;
    }
    .vrt-source a {
      color: #2563eb;
      text-decoration: none;
      font-weight: 500;
    }
    .vrt-source a:hover { text-decoration: underline; }

    /* ── Feedback buttons ───────────────────────────────────── */
    .vrt-feedback {
      display: flex;
      gap: 6px;
      margin-top: 6px;
    }
    .vrt-fb-btn {
      background: #fff;
      border: 1px solid #e5e7eb;
      border-radius: 20px;
      padding: 3px 10px;
      font-size: 12px;
      cursor: pointer;
      color: #6b7280;
      transition: background 0.2s, border-color 0.2s, color 0.2s,
                  transform 0.15s;
      display: flex;
      align-items: center;
      gap: 3px;
    }
    .vrt-fb-btn:hover {
      background: #f9fafb;
      border-color: #d1d5db;
      color: #374151;
      transform: scale(1.06);
    }
    .vrt-fb-btn:active { transform: scale(0.97); }
    .vrt-feedback-thanks {
      font-size: 11.5px;
      color: #10b981;
      margin-top: 6px;
      font-weight: 500;
    }
    .vrt-feedback-sorry {
      font-size: 11.5px;
      color: #6b7280;
      margin-top: 6px;
    }

    /* ── Starter questions ──────────────────────────────────── */
    #vrt-starters {
      display: flex;
      flex-direction: column;
      gap: 7px;
      margin-top: 6px;
    }
    .vrt-starter-btn {
      background: #fff;
      border: 1.5px solid #e5e7eb;
      border-radius: 20px;
      padding: 9px 14px;
      font-size: 12.5px;
      color: #374151;
      cursor: pointer;
      text-align: left;
      transition: background 0.2s, border-color 0.2s, transform 0.15s,
                  box-shadow 0.2s;
      line-height: 1.4;
    }
    .vrt-starter-btn:hover {
      background: #f0f4ff;
      border-color: #2563eb;
      color: #1d4ed8;
      transform: translateY(-1px);
      box-shadow: 0 2px 8px rgba(37,99,235,0.1);
    }
    .vrt-starter-btn:active { transform: translateY(0); }

    /* ── Typing indicator ───────────────────────────────────── */
    #vrt-typing .vrt-bubble-text {
      display: flex;
      align-items: center;
      gap: 10px;
      color: #6b7280;
      font-style: italic;
      font-size: 13px;
      padding: 11px 15px;
    }
    .vrt-dots {
      display: flex;
      gap: 4px;
    }
    .vrt-dot {
      width: 5px;
      height: 5px;
      border-radius: 50%;
      background: #9ca3af;
      animation: vrt-bounce 1.3s ease-in-out infinite;
    }
    .vrt-dot:nth-child(1) { animation-delay: 0s;     }
    .vrt-dot:nth-child(2) { animation-delay: 0.18s;  }
    .vrt-dot:nth-child(3) { animation-delay: 0.36s;  }
    @keyframes vrt-bounce {
      0%, 60%, 100% { transform: translateY(0);    }
      30%            { transform: translateY(-5px); }
    }

    /* ── Input area ─────────────────────────────────────────── */
    #vrt-input-area {
      padding: 12px 14px;
      border-top: 1px solid #f0f0f0;
      display: flex;
      gap: 8px;
      align-items: flex-end;
      flex-shrink: 0;
      background: #fff;
    }
    #vrt-input {
      flex: 1;
      border: 1.5px solid #e5e7eb;
      border-radius: 22px;
      padding: 9px 15px;
      font-size: 13.5px;
      font-family: inherit;
      outline: none;
      resize: none;
      max-height: 100px;
      line-height: 1.5;
      color: #111827;
      background: #f9fafb;
      transition: border-color 0.2s, background 0.2s, box-shadow 0.2s;
    }
    #vrt-input::placeholder { color: #9ca3af; }
    #vrt-input:focus {
      border-color: #111827;
      background: #fff;
      box-shadow: 0 0 0 3px rgba(17,24,39,0.07);
    }
    #vrt-input:disabled { opacity: 0.5; }

    #vrt-send-btn {
      width: 38px;
      height: 38px;
      border-radius: 50%;
      background: #111827;
      border: none;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;
      transition: background 0.2s, transform 0.15s, box-shadow 0.2s;
      box-shadow: 0 2px 8px rgba(17,24,39,0.2);
    }
    #vrt-send-btn:hover:not(:disabled) {
      background: #1f2937;
      transform: scale(1.08);
      box-shadow: 0 4px 12px rgba(17,24,39,0.3);
    }
    #vrt-send-btn:active:not(:disabled) { transform: scale(0.97); }
    #vrt-send-btn:disabled { opacity: 0.4; cursor: not-allowed; }

    /* char counter */
    #vrt-char-count {
      font-size: 10px;
      color: #9ca3af;
      text-align: right;
      padding: 0 16px 6px;
      background: #fff;
      flex-shrink: 0;
    }
    #vrt-char-count.vrt-near-limit { color: #f59e0b; }
    #vrt-char-count.vrt-at-limit   { color: #ef4444; }

    /* ── Footer ─────────────────────────────────────────────── */
    #vrt-footer {
      text-align: center;
      font-size: 10.5px;
      color: #9ca3af;
      padding: 6px 0 10px;
      background: #fff;
      flex-shrink: 0;
      letter-spacing: 0.01em;
    }
    #vrt-footer a {
      color: #6b7280;
      text-decoration: none;
      font-weight: 500;
    }
    #vrt-footer a:hover { color: #374151; }

    /* ── Error / system message ─────────────────────────────── */
    .vrt-system-msg {
      align-self: center;
      background: #fef2f2;
      color: #991b1b;
      border: 1px solid #fecaca;
      border-radius: 8px;
      padding: 7px 12px;
      font-size: 12px;
      text-align: center;
      animation: vrt-fadein 0.28s ease;
    }
    .vrt-warn-msg {
      background: #fffbeb;
      color: #92400e;
      border-color: #fde68a;
    }

    /* ── Mobile ─────────────────────────────────────────────── */
    @media (max-width: 420px) {
      #vrt-window {
        width: calc(100vw - 16px);
        height: calc(100dvh - 100px);
        bottom: 66px;
        right: 0;
        border-radius: 14px;
      }
    }
  `;

  // ============================================================
  // HTML
  // ============================================================
  const HTML = `
    <!-- Chat window -->
    <div id="vrt-window" role="dialog" aria-modal="true"
         aria-label="Veritas AI Chat" aria-hidden="true">

      <!-- Header -->
      <div id="vrt-header">
        <div id="vrt-header-left">
          <div id="vrt-avatar" aria-hidden="true">✦</div>
          <div id="vrt-header-info">
            <div id="vrt-header-title">Veritas — Ask anything</div>
            <div id="vrt-status">
              <div id="vrt-status-dot"></div>
              <span>Online · Answers from our website</span>
            </div>
          </div>
        </div>
        <button id="vrt-close-btn" aria-label="Close chat">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path d="M12 4L4 12M4 4l8 8" stroke="currentColor"
                  stroke-width="1.8" stroke-linecap="round"/>
          </svg>
        </button>
      </div>

      <!-- Messages -->
      <div id="vrt-messages" aria-live="polite" aria-label="Chat messages">

        <!-- Bot greeting -->
        <div class="vrt-row vrt-bot">
          <div class="vrt-bubble-text">
            👋 Hi! I'm Veritas. Ask me anything about our services,
            pricing, or how to get started — I only answer based on
            our website content.
          </div>
        </div>

        <!-- Starter question chips -->
        <div id="vrt-starters" role="group" aria-label="Suggested questions">
          <button class="vrt-starter-btn"
                  data-q="What services do you offer?">
            💼 What services do you offer?
          </button>
          <button class="vrt-starter-btn"
                  data-q="How do I get started?">
            🚀 How do I get started?
          </button>
          <button class="vrt-starter-btn"
                  data-q="How can I contact you?">
            📬 How can I contact you?
          </button>
        </div>

      </div>

      <!-- Char counter -->
      <div id="vrt-char-count" aria-live="polite" aria-atomic="true"></div>

      <!-- Input area -->
      <div id="vrt-input-area">
        <textarea
          id="vrt-input"
          placeholder="Ask a question…"
          rows="1"
          maxlength="500"
          aria-label="Your message"
          autocomplete="off"
          autocorrect="off"
          spellcheck="true"
        ></textarea>
        <button id="vrt-send-btn" aria-label="Send message">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
            <path d="M22 2L11 13M22 2L15 22l-4-9-9-4 20-7z"
                  stroke="white" stroke-width="2"
                  stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </button>
      </div>

      <!-- Footer -->
      <div id="vrt-footer">
        Powered by <a href="#" tabindex="-1">Veritas AI</a>
      </div>
    </div>

    <!-- Floating bubble trigger -->
    <button id="vrt-bubble" aria-label="Open Veritas chat" aria-expanded="false">
      <!-- Chat icon -->
      <svg id="vrt-icon-chat" width="24" height="24" viewBox="0 0 24 24" fill="none">
        <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"
              stroke="white" stroke-width="2"
              stroke-linecap="round" stroke-linejoin="round"/>
        <path d="M8 10h8M8 14h5"
              stroke="white" stroke-width="1.8"
              stroke-linecap="round"/>
      </svg>
      <!-- Close icon -->
      <svg id="vrt-icon-close" width="20" height="20" viewBox="0 0 24 24" fill="none">
        <path d="M18 6L6 18M6 6l12 12"
              stroke="white" stroke-width="2.2"
              stroke-linecap="round"/>
      </svg>
    </button>
  `;

  // ============================================================
  // BOOTSTRAP — inject into page
  // ============================================================
  const styleEl = document.createElement("style");
  styleEl.id = "vrt-styles";
  styleEl.textContent = CSS;
  document.head.appendChild(styleEl);

  const rootEl = document.createElement("div");
  rootEl.id = "vrt-root";
  rootEl.innerHTML = HTML;
  document.body.appendChild(rootEl);

  // ============================================================
  // DOM REFS
  // ============================================================
  const $ = (id) => document.getElementById(id);
  const bubble    = $("vrt-bubble");
  const windowEl  = $("vrt-window");
  const closeBtn  = $("vrt-close-btn");
  const messages  = $("vrt-messages");
  const input     = $("vrt-input");
  const sendBtn   = $("vrt-send-btn");
  const starters  = $("vrt-starters");
  const charCount = $("vrt-char-count");

  // ============================================================
  // TOGGLE OPEN / CLOSE
  // ============================================================
  function openChat() {
    isOpen = true;
    rootEl.classList.add("vrt-open");
    bubble.setAttribute("aria-expanded", "true");
    windowEl.setAttribute("aria-hidden", "false");
    setTimeout(() => input.focus(), 320);
  }

  function closeChat() {
    isOpen = false;
    rootEl.classList.remove("vrt-open");
    bubble.setAttribute("aria-expanded", "false");
    windowEl.setAttribute("aria-hidden", "true");
  }

  function toggleChat() {
    isOpen ? closeChat() : openChat();
  }

  bubble.addEventListener("click", toggleChat);
  closeBtn.addEventListener("click", closeChat);

  // Close on Escape key
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && isOpen) closeChat();
  });

  // ============================================================
  // STARTER QUESTIONS
  // ============================================================
  starters.querySelectorAll(".vrt-starter-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const q = btn.getAttribute("data-q");
      hideStarters();
      sendMessage(q);
    });
  });

  function hideStarters() {
    if (starters && starters.parentNode) {
      starters.style.display = "none";
    }
  }

  // ============================================================
  // INPUT HANDLING
  // ============================================================
  input.addEventListener("input", () => {
    // Auto-grow textarea
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 100) + "px";

    // Char counter
    const len = input.value.length;
    if (len === 0) {
      charCount.textContent = "";
      charCount.className = "";
    } else {
      charCount.textContent = `${len} / ${MAX_CHARS}`;
      charCount.className =
        len >= MAX_CHARS       ? "vrt-at-limit"   :
        len >= MAX_CHARS * 0.8 ? "vrt-near-limit" : "";
    }
  });

  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  });

  sendBtn.addEventListener("click", handleSend);

  // ============================================================
  // SEND LOGIC
  // ============================================================
  function handleSend(forcedText) {
    const text = (forcedText || input.value).trim();
    if (!text || isWaiting) return;
    if (text.length > MAX_CHARS) return;

    hideStarters();
    input.value = "";
    input.style.height = "auto";
    charCount.textContent = "";
    charCount.className = "";

    sendMessage(text);
  }

  async function sendMessage(question) {
    isWaiting = true;
    lastQuestion = question;
    setInputDisabled(true);

    appendUserBubble(question);
    const typingEl = appendTyping();

    // Build history payload (last N turns)
    const historyPayload = chatHistory.slice(-HISTORY_TURNS);

    try {
      const res = await fetch(`${API_URL}/chat`, {
        method : "POST",
        headers: { "Content-Type": "application/json" },
        body   : JSON.stringify({
          question    : question,
          chat_history: historyPayload,
        }),
      });

      removeEl(typingEl);

      if (res.status === 429) {
        appendSystemMsg(
          "⏳ Too many questions! Please wait a moment.",
          "vrt-warn-msg"
        );
      } else if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      } else {
        const data = await res.json();
        const answer  = data.answer        || "";
        const sources = data.sources       || [];
        const titles  = data.source_titles || [];

        // Update history
        chatHistory.push({ role: "user",      content: question });
        chatHistory.push({ role: "assistant", content: answer   });

        appendBotBubble(answer, sources, titles, question);
      }
    } catch (err) {
      removeEl(typingEl);
      appendSystemMsg(
        "⚠️ Sorry, I'm having trouble connecting. Please try again.",
        ""
      );
      console.error("[Veritas] API error:", err);
    } finally {
      isWaiting = false;
      setInputDisabled(false);
      input.focus();
    }
  }

  // ============================================================
  // DOM BUILDERS
  // ============================================================
  function appendUserBubble(text) {
    const row = make("div", "vrt-row vrt-user");
    const bub = make("div", "vrt-bubble-text");
    bub.textContent = text;
    row.appendChild(bub);
    messages.appendChild(row);
    scrollBottom();
    return row;
  }

  function appendBotBubble(text, sources, titles, question) {
    const row = make("div", "vrt-row vrt-bot");

    // Answer text
    const bub = make("div", "vrt-bubble-text");
    bub.innerHTML = formatAnswer(text);
    row.appendChild(bub);

    // Source citation
    if (sources.length > 0) {
      const src = make("div", "vrt-source");
      const titleText = (titles[0] || "Source").slice(0, 60);
      src.innerHTML = `📄 Source: <a href="${esc(sources[0])}"
        target="_blank" rel="noopener noreferrer">${esc(titleText)}</a>`;
      row.appendChild(src);
    }

    // Feedback buttons (only if there's a real answer)
    if (question && text) {
      row.appendChild(makeFeedback(question, text));
    }

    messages.appendChild(row);
    scrollBottom();
    return row;
  }

  function makeFeedback(question, answer) {
    const wrap = make("div", "vrt-feedback");

    const up   = make("button", "vrt-fb-btn");
    up.innerHTML = "👍 Helpful";
    up.setAttribute("aria-label", "Mark as helpful");

    const down = make("button", "vrt-fb-btn");
    down.innerHTML = "👎 Not helpful";
    down.setAttribute("aria-label", "Mark as not helpful");

    up.addEventListener("click", () =>
      submitFeedback(1, question, answer, wrap)
    );
    down.addEventListener("click", () =>
      submitFeedback(-1, question, answer, wrap)
    );

    wrap.appendChild(up);
    wrap.appendChild(down);
    return wrap;
  }

  function appendTyping() {
    const row = make("div", "vrt-row vrt-bot");
    row.id = "vrt-typing";
    row.innerHTML = `
      <div class="vrt-bubble-text">
        <span>Thinking…</span>
        <div class="vrt-dots">
          <div class="vrt-dot"></div>
          <div class="vrt-dot"></div>
          <div class="vrt-dot"></div>
        </div>
      </div>`;
    messages.appendChild(row);
    scrollBottom();
    return row;
  }

  function appendSystemMsg(text, extraClass) {
    const el = make("div", `vrt-system-msg ${extraClass}`.trim());
    el.textContent = text;
    messages.appendChild(el);
    scrollBottom();
    return el;
  }

  // ============================================================
  // FEEDBACK
  // ============================================================
  async function submitFeedback(rating, question, answer, wrapEl) {
    // Immediately swap UI
    const thanks = make("div", rating === 1 ? "vrt-feedback-thanks" : "vrt-feedback-sorry");
    thanks.textContent = rating === 1
      ? "Thanks! Glad that helped 👍"
      : "Sorry about that — we'll improve it.";
    wrapEl.replaceWith(thanks);

    try {
      await fetch(`${API_URL}/feedback`, {
        method : "POST",
        headers: { "Content-Type": "application/json" },
        body   : JSON.stringify({
          session_id: sessionId,
          rating    : rating,
          question  : question,
          answer    : answer,
        }),
      });
    } catch (err) {
      console.warn("[Veritas] Feedback send failed:", err);
    }
  }

  // ============================================================
  // UTILITIES
  // ============================================================
  function make(tag, className) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    return el;
  }

  function removeEl(el) {
    if (el && el.parentNode) el.parentNode.removeChild(el);
  }

  function scrollBottom() {
    messages.scrollTop = messages.scrollHeight;
  }

  function setInputDisabled(disabled) {
    input.disabled   = disabled;
    sendBtn.disabled = disabled;
  }

  function esc(str) {
    if (typeof str !== "string") return "";
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  /**
   * Lightweight markdown-ish formatter:
   * - Escapes HTML
   * - **bold**
   * - _italic_
   * - Line breaks
   * - Bullet lists (- item)
   */
  function formatAnswer(raw) {
    if (typeof raw !== "string") return "";

    // Escape HTML first
    let s = esc(raw);

    // Bold **text**
    s = s.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");

    // Italic _text_
    s = s.replace(/(?<!\w)_(.+?)_(?!\w)/g, "<em>$1</em>");

    // Simple bullet list lines starting with "- "
    const lines = s.split("\n");
    const out   = [];
    let inList  = false;

    for (const line of lines) {
      const trimmed = line.trim();
      if (trimmed.startsWith("- ") || trimmed.startsWith("• ")) {
        if (!inList) { out.push("<ul style='margin:6px 0 6px 16px;padding:0'>"); inList = true; }
        out.push(`<li style='margin-bottom:3px'>${trimmed.slice(2)}</li>`);
      } else {
        if (inList) { out.push("</ul>"); inList = false; }
        out.push(trimmed ? `<p style='margin:0 0 6px'>${trimmed}</p>` : "");
      }
    }
    if (inList) out.push("</ul>");

    return out.join("");
  }

})();
