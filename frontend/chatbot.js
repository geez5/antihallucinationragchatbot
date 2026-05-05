(function() {
  const API_URL = "http://localhost:8000";
  let chatHistory = [];
  let isOpen = false;
  let isWaiting = false;
  let sessionId = Math.random().toString(36).substring(2, 15);

  // CSS styles
  const styles = `
    #veritas-widget-container {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      position: fixed;
      bottom: 24px;
      right: 24px;
      z-index: 999999;
      color: #111827;
    }
    
    .veritas-bubble {
      width: 56px;
      height: 56px;
      background-color: #111827;
      border-radius: 50%;
      box-shadow: 0 4px 12px rgba(0,0,0,0.15);
      display: flex;
      justify-content: center;
      align-items: center;
      cursor: pointer;
      transition: transform 0.2s ease;
      position: absolute;
      bottom: 0;
      right: 0;
    }
    
    .veritas-bubble:hover {
      transform: scale(1.05);
    }
    
    .veritas-bubble svg {
      fill: white;
      width: 28px;
      height: 28px;
    }
    
    .veritas-window {
      position: absolute;
      bottom: 80px;
      right: 0;
      width: 370px;
      height: 540px;
      background: white;
      border-radius: 18px;
      box-shadow: 0 8px 32px rgba(0,0,0,0.15);
      display: flex;
      flex-direction: column;
      overflow: hidden;
      transition: opacity 0.3s ease, transform 0.3s ease;
      transform-origin: bottom right;
    }
    
    .veritas-hidden {
      opacity: 0;
      transform: scale(0.95);
      pointer-events: none;
    }
    
    .veritas-header {
      background: #111827;
      color: white;
      padding: 16px 20px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-weight: 600;
      font-size: 16px;
    }
    
    .veritas-header-title {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    
    .veritas-status-dot {
      width: 8px;
      height: 8px;
      background-color: #10b981;
      border-radius: 50%;
    }
    
    #veritas-close-btn {
      background: none;
      border: none;
      color: white;
      font-size: 24px;
      cursor: pointer;
      line-height: 1;
      padding: 0;
    }
    
    .veritas-messages {
      flex: 1;
      overflow-y: auto;
      padding: 20px;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
    
    .veritas-message {
      display: flex;
      flex-direction: column;
      max-width: 85%;
    }
    
    .veritas-message.user {
      align-self: flex-end;
    }
    
    .veritas-message.bot {
      align-self: flex-start;
    }
    
    .veritas-bubble-text {
      padding: 12px 16px;
      border-radius: 16px;
      font-size: 14px;
      line-height: 1.5;
      word-wrap: break-word;
    }
    
    .veritas-message.user .veritas-bubble-text {
      background: #111827;
      color: white;
      border-bottom-right-radius: 4px;
    }
    
    .veritas-message.bot .veritas-bubble-text {
      background: #f3f4f6;
      color: #111827;
      border-bottom-left-radius: 4px;
    }
    
    .veritas-source {
      font-size: 12px;
      margin-top: 6px;
      color: #6b7280;
    }
    
    .veritas-source a {
      color: #2563eb;
      text-decoration: none;
    }
    
    .veritas-source a:hover {
      text-decoration: underline;
    }
    
    .veritas-feedback {
      display: flex;
      gap: 8px;
      margin-top: 6px;
    }
    
    .veritas-feedback button {
      background: none;
      border: 1px solid #e5e7eb;
      border-radius: 4px;
      padding: 4px 8px;
      font-size: 12px;
      cursor: pointer;
      color: #4b5563;
      transition: background 0.2s;
    }
    
    .veritas-feedback button:hover {
      background: #f3f4f6;
    }
    
    .veritas-feedback-thanks {
      font-size: 12px;
      color: #10b981;
      margin-top: 6px;
    }
    
    .veritas-starter-questions {
      display: flex;
      flex-direction: column;
      gap: 8px;
      margin-top: 4px;
    }
    
    .veritas-starter-btn {
      background: white;
      border: 1px solid #e5e7eb;
      border-radius: 16px;
      padding: 8px 12px;
      font-size: 13px;
      color: #111827;
      cursor: pointer;
      transition: all 0.2s;
      text-align: left;
    }
    
    .veritas-starter-btn:hover {
      background: #f9fafb;
      border-color: #d1d5db;
    }
    
    .veritas-input-area {
      padding: 16px;
      border-top: 1px solid #e5e7eb;
      display: flex;
      gap: 8px;
    }
    
    #veritas-input {
      flex: 1;
      border: 1px solid #d1d5db;
      border-radius: 20px;
      padding: 10px 16px;
      font-size: 14px;
      outline: none;
    }
    
    #veritas-input:focus {
      border-color: #111827;
    }
    
    #veritas-send-btn {
      background: #111827;
      color: white;
      border: none;
      border-radius: 20px;
      padding: 0 16px;
      font-weight: 500;
      cursor: pointer;
      transition: opacity 0.2s;
    }
    
    #veritas-send-btn:hover {
      opacity: 0.9;
    }
    
    .veritas-footer {
      text-align: center;
      font-size: 11px;
      color: #9ca3af;
      padding-bottom: 12px;
    }
    
    .veritas-typing-container .veritas-bubble-text {
      display: flex;
      align-items: center;
      gap: 8px;
      font-style: italic;
      color: #6b7280;
    }
    
    .veritas-typing {
      display: flex;
      gap: 4px;
    }
    
    .veritas-dot {
      width: 4px;
      height: 4px;
      background: #9ca3af;
      border-radius: 50%;
      animation: veritas-bounce 1.4s infinite ease-in-out both;
    }
    
    .veritas-dot:nth-child(1) { animation-delay: -0.32s; }
    .veritas-dot:nth-child(2) { animation-delay: -0.16s; }
    
    @keyframes veritas-bounce {
      0%, 80%, 100% { transform: scale(0); }
      40% { transform: scale(1); }
    }
    
    @media (max-width: 480px) {
      .veritas-window {
        width: calc(100vw - 32px);
        height: calc(100vh - 120px);
        bottom: 70px;
        right: 0;
      }
    }
  `;

  // Inject CSS
  const styleEl = document.createElement('style');
  styleEl.textContent = styles;
  document.head.appendChild(styleEl);

  // HTML content
  const htmlContent = `
    <div id="veritas-chat-window" class="veritas-window veritas-hidden">
      <div class="veritas-header">
        <div class="veritas-header-title">
          <div class="veritas-status-dot"></div>
          Veritas — Ask anything
        </div>
        <button id="veritas-close-btn">&times;</button>
      </div>
      
      <div id="veritas-messages" class="veritas-messages">
        <div class="veritas-message bot">
          <div class="veritas-bubble-text">Hi! How can I help you today?</div>
        </div>
        <div class="veritas-starter-questions" id="veritas-starters">
           <button class="veritas-starter-btn">What services do you offer?</button>
           <button class="veritas-starter-btn">How do I get started?</button>
           <button class="veritas-starter-btn">How can I contact you?</button>
        </div>
      </div>
      
      <div class="veritas-input-area">
        <input type="text" id="veritas-input" placeholder="Type your message..." autocomplete="off" />
        <button id="veritas-send-btn">Send</button>
      </div>
      
      <div class="veritas-footer">
        Powered by DoIT(geetangi)
      </div>
    </div>
    
    <div id="veritas-bubble" class="veritas-bubble">
      <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
        <path d="M20 2H4C2.9 2 2 2.9 2 4V22L6 18H20C21.1 18 22 17.1 22 16V4C22 2.9 21.1 2 20 2ZM20 16H5.17L4 17.17V4H20V16Z" fill="white"/>
        <path d="M7 9H17V11H7V9Z" fill="white"/>
        <path d="M7 13H14V15H7V13Z" fill="white"/>
      </svg>
    </div>
  `;

  // Inject HTML
  const container = document.createElement('div');
  container.id = 'veritas-widget-container';
  container.innerHTML = htmlContent;
  document.body.appendChild(container);

  // DOM Elements
  const bubble = document.getElementById('veritas-bubble');
  const windowEl = document.getElementById('veritas-chat-window');
  const closeBtn = document.getElementById('veritas-close-btn');
  const messagesEl = document.getElementById('veritas-messages');
  const inputEl = document.getElementById('veritas-input');
  const sendBtn = document.getElementById('veritas-send-btn');
  const startersEl = document.getElementById('veritas-starters');

  // Event Listeners
  bubble.addEventListener('click', toggleChat);
  closeBtn.addEventListener('click', toggleChat);
  
  inputEl.addEventListener('keypress', function(e) {
    if (e.key === 'Enter') handleSend();
  });
  
  sendBtn.addEventListener('click', () => handleSend());

  // Starter questions listener
  document.querySelectorAll('.veritas-starter-btn').forEach(btn => {
    btn.addEventListener('click', function() {
      if (startersEl) startersEl.style.display = 'none';
      handleSend(this.textContent);
    });
  });

  function toggleChat() {
    isOpen = !isOpen;
    if (isOpen) {
      windowEl.classList.remove('veritas-hidden');
      setTimeout(() => inputEl.focus(), 100);
    } else {
      windowEl.classList.add('veritas-hidden');
    }
  }

  function appendUserMessage(text) {
    const msgDiv = document.createElement('div');
    msgDiv.className = 'veritas-message user';
    msgDiv.innerHTML = `<div class="veritas-bubble-text">${escapeHtml(text)}</div>`;
    messagesEl.appendChild(msgDiv);
    scrollToBottom();
  }

  function appendBotMessage(text, sources = [], sourceTitles = [], question = '') {
    const msgDiv = document.createElement('div');
    msgDiv.className = 'veritas-message bot';
    
    const formattedText = escapeHtml(text).replace(/\n/g, '<br>');
    let html = `<div class="veritas-bubble-text">${formattedText}</div>`;
    
    if (sources && sources.length > 0 && sourceTitles && sourceTitles.length > 0) {
      html += `<div class="veritas-source">📄 Source: <a href="${sources[0]}" target="_blank">${escapeHtml(sourceTitles[0] || 'Link')}</a></div>`;
    }

    if (question && text) {
      const feedbackId = 'fb-' + Math.random().toString(36).substr(2, 9);
      html += `
        <div class="veritas-feedback" id="${feedbackId}">
          <button class="veritas-upvote">👍</button>
          <button class="veritas-downvote">👎</button>
        </div>
      `;
      msgDiv.innerHTML = html;
      messagesEl.appendChild(msgDiv);

      const fbContainer = document.getElementById(feedbackId);
      if (fbContainer) {
        const upBtn = fbContainer.querySelector('.veritas-upvote');
        const downBtn = fbContainer.querySelector('.veritas-downvote');
        upBtn.onclick = () => submitFeedback(1, question, text, fbContainer);
        downBtn.onclick = () => submitFeedback(-1, question, text, fbContainer);
      }
    } else {
      msgDiv.innerHTML = html;
      messagesEl.appendChild(msgDiv);
    }

    scrollToBottom();
  }

  function appendTypingIndicator() {
    const typingDiv = document.createElement('div');
    typingDiv.className = 'veritas-message bot veritas-typing-container';
    typingDiv.id = 'veritas-typing-indicator';
    typingDiv.innerHTML = `
      <div class="veritas-bubble-text">
        Thinking...
        <div class="veritas-typing">
          <div class="veritas-dot"></div>
          <div class="veritas-dot"></div>
          <div class="veritas-dot"></div>
        </div>
      </div>
    `;
    messagesEl.appendChild(typingDiv);
    scrollToBottom();
  }

  function removeTypingIndicator() {
    const typingDiv = document.getElementById('veritas-typing-indicator');
    if (typingDiv) {
      typingDiv.remove();
    }
  }

  function scrollToBottom() {
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function escapeHtml(unsafe) {
    if (typeof unsafe !== 'string') return '';
    return unsafe
         .replace(/&/g, "&amp;")
         .replace(/</g, "&lt;")
         .replace(/>/g, "&gt;")
         .replace(/"/g, "&quot;")
         .replace(/'/g, "&#039;");
  }

  async function handleSend(forcedText = null) {
    const text = forcedText || inputEl.value.trim();
    if (!text || isWaiting) return;

    if (startersEl) startersEl.style.display = 'none';

    inputEl.value = '';
    appendUserMessage(text);
    isWaiting = true;
    appendTypingIndicator();

    const recentHistory = chatHistory.slice(-8);
    
    const payload = {
      question: text,
      chat_history: recentHistory
    };

    try {
      const response = await fetch(`${API_URL}/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload)
      });

      removeTypingIndicator();
      isWaiting = false;

      if (response.status === 429) {
        appendBotMessage("Too many questions! Please wait a moment.");
        return;
      }

      if (!response.ok) {
        throw new Error('Network response was not ok');
      }

      const data = await response.json();
      
      chatHistory.push([text, data.answer]);
      
      appendBotMessage(data.answer, data.sources, data.source_titles, text);

    } catch (error) {
      console.error("Chat API error:", error);
      removeTypingIndicator();
      isWaiting = false;
      appendBotMessage("Sorry, I'm having trouble connecting right now. Please try again later.");
    }
  }

  async function submitFeedback(rating, question, answer, containerEl) {
    try {
      if (rating === 1) {
        containerEl.innerHTML = '<div class="veritas-feedback-thanks">Thanks! Glad that helped 👍</div>';
      } else {
        containerEl.innerHTML = '<div class="veritas-feedback-thanks" style="color: #6b7280;">Sorry about that — we\'ll improve it.</div>';
      }

      await fetch(`${API_URL}/feedback`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          session_id: sessionId,
          rating: rating,
          question: question,
          answer: answer
        })
      });
    } catch (error) {
      console.error('Feedback error:', error);
    }
  }

})();
