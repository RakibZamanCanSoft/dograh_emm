/**
 * Dograh Text Chat Widget
 * Embeddable text chat widget for Dograh workflows
 * Version: 1.0.0
 */

(function() {
  'use strict';

  // Widget configuration defaults
  const DEFAULT_CONFIG = {
    position: 'bottom-right',
    autoStart: false,
    apiBaseUrl: window.location.hostname === 'localhost'
      ? 'http://localhost:8000'
      : 'https://api.dograh.com'
  };

    const state = {
    config: {},
    isInitialized: false,
    isOpen: false,
    sessionToken: null,
    workflowRunId: null,
    isConnecting: false,
    isSending: false,
    isCompleted: false,
    turns: [],
  };

  async function init() {
    if (state.isInitialized) return;

    const script = document.currentScript || document.querySelector('script[src*="dograh-text-widget.js"]');
    if (!script) {
      console.error('Dograh Widget: Script not found');
      return;
    }

    const scriptUrl = new URL(script.src);
    const token = scriptUrl.searchParams.get('token');
    const apiEndpoint = scriptUrl.searchParams.get('apiEndpoint');

    if (!token) {
      console.error('Dograh Widget: No token found in script URL');
      return;
    }

    let apiBaseUrl = DEFAULT_CONFIG.apiBaseUrl;
    if (apiEndpoint) {
      if (!apiEndpoint.startsWith('http://') && !apiEndpoint.startsWith('https://')) {
        apiBaseUrl = 'https://' + apiEndpoint.replace(/\/+$/, '');
      } else {
        apiBaseUrl = apiEndpoint.replace(/\/+$/, '');
      }
    } else if (scriptUrl.origin.includes('localhost')) {
      apiBaseUrl = 'http://localhost:8000';
    } else {
      apiBaseUrl = scriptUrl.origin.replace(/:\d+$/, ':8000');
    }

    state.config = {
      ...DEFAULT_CONFIG,
      token: token,
      apiBaseUrl: apiBaseUrl,
    };

    try {
      // Re-use the existing config endpoint to get styles
      const configResponse = await fetch(`${state.config.apiBaseUrl}/api/v1/public/embed/config/${token}`, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        }
      });

      if (configResponse.ok) {
        const configData = await configResponse.json();
        state.config = {
          ...state.config,
          workflowId: configData.workflow_id,
          position: configData.position || DEFAULT_CONFIG.position,
          buttonColor: configData.settings?.buttonColor || '#10b981',
          autoStart: configData.auto_start || false
        };
      }
    } catch (error) {
      console.warn('Dograh Widget: Failed to fetch configuration, using defaults', error);
    }

    state.isInitialized = true;
    injectStyles();
    createFloatingWidget();

    if (state.config.autoStart) {
      setTimeout(() => toggleWidget(), 1000);
    }
  }

  function injectStyles() {
    if (document.getElementById('dograh-text-widget-styles')) return;

    const styles = `
      .dograh-tw-container {
        position: fixed;
        z-index: 999999;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      }
      .dograh-tw-container.bottom-right { bottom: 20px; right: 20px; }
      .dograh-tw-container.bottom-left { bottom: 20px; left: 20px; }
      
      .dograh-tw-button {
        width: 60px;
        height: 60px;
        border-radius: 30px;
        background-color: ${state.config.buttonColor};
        color: white;
        border: none;
        box-shadow: 0 4px 14px rgba(0, 0, 0, 0.2);
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        transition: transform 0.2s;
      }
      .dograh-tw-button:hover { transform: scale(1.05); }
      
      .dograh-tw-window {
        position: absolute;
        bottom: 80px;
        right: 0;
        width: 350px;
        height: 500px;
        background: white;
        border-radius: 12px;
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.15);
        display: none;
        flex-direction: column;
        overflow: hidden;
      }
      .dograh-tw-container.bottom-left .dograh-tw-window {
        right: auto;
        left: 0;
      }

      .dograh-tw-header {
        background: ${state.config.buttonColor};
        color: white;
        padding: 16px;
        font-weight: 600;
        display: flex;
        justify-content: space-between;
        align-items: center;
      }
      .dograh-tw-close {
        background: none;
        border: none;
        color: white;
        cursor: pointer;
        padding: 4px;
      }
      
      .dograh-tw-messages {
        flex: 1;
        padding: 16px;
        overflow-y: auto;
        display: flex;
        flex-direction: column;
        gap: 12px;
        background: #f9fafb;
      }
      
      .dograh-tw-msg {
        max-width: 80%;
        padding: 10px 14px;
        border-radius: 12px;
        font-size: 14px;
        line-height: 1.4;
      }
      .dograh-tw-msg.user {
        background: ${state.config.buttonColor};
        color: white;
        align-self: flex-end;
        border-bottom-right-radius: 2px;
      }
      .dograh-tw-msg.agent {
        background: white;
        color: #111827;
        align-self: flex-start;
        border-bottom-left-radius: 2px;
        border: 1px solid #e5e7eb;
      }
      
      .dograh-tw-input-area {
        padding: 16px;
        background: white;
        border-top: 1px solid #e5e7eb;
        display: flex;
        gap: 8px;
      }
      .dograh-tw-input {
        flex: 1;
        padding: 10px 12px;
        border: 1px solid #d1d5db;
        border-radius: 20px;
        outline: none;
        font-size: 14px;
      }
      .dograh-tw-input:focus {
        border-color: ${state.config.buttonColor};
      }
      .dograh-tw-send {
        background: ${state.config.buttonColor};
        color: white;
        border: none;
        border-radius: 20px;
        padding: 0 16px;
        font-weight: 600;
        cursor: pointer;
      }
      .dograh-tw-send:disabled {
        opacity: 0.5;
        cursor: not-allowed;
      }

      .dograh-tw-typing {
        font-size: 12px;
        color: #6b7280;
        margin-left: 4px;
      }
    `;

    const styleSheet = document.createElement('style');
    styleSheet.id = 'dograh-text-widget-styles';
    styleSheet.textContent = styles;
    document.head.appendChild(styleSheet);
  }

  function createFloatingWidget() {
    const container = document.createElement('div');
    container.className = `dograh-tw-container ${state.config.position}`;
    container.id = 'dograh-tw-root';

    // Toggle Button
    const button = document.createElement('button');
    button.id = 'dograh-tw-button';
    button.className = 'dograh-tw-button';
    button.onclick = toggleWidget;
    button.innerHTML = `
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
      </svg>
    `;
    container.appendChild(button);

    // Chat Window
    const chatWindow = document.createElement('div');
    chatWindow.className = 'dograh-tw-window';
    chatWindow.id = 'dograh-tw-window';
    
    chatWindow.innerHTML = `
      <div class="dograh-tw-header">
        <span>Chat with Agent</span>
        <button class="dograh-tw-close" onclick="document.getElementById('dograh-tw-button').click()">✕</button>
      </div>
      <div class="dograh-tw-messages" id="dograh-tw-messages">
        <!-- Messages will appear here -->
      </div>
      <form class="dograh-tw-input-area" id="dograh-tw-form">
        <input type="text" class="dograh-tw-input" id="dograh-tw-input" placeholder="Type your message..." autocomplete="off">
        <button type="submit" class="dograh-tw-send" id="dograh-tw-send">Send</button>
      </form>
    `;

    // Ensure the close button works
    setTimeout(() => {
        const closeBtn = chatWindow.querySelector('.dograh-tw-close');
        if(closeBtn) closeBtn.onclick = toggleWidget;
        
        const form = chatWindow.querySelector('#dograh-tw-form');
        if(form) form.onsubmit = handleSend;
    }, 0);

    container.appendChild(chatWindow);
    document.body.appendChild(container);
  }

  function toggleWidget() {
    const chatWindow = document.getElementById('dograh-tw-window');
    if (!chatWindow) return;

    state.isOpen = !state.isOpen;
    chatWindow.style.display = state.isOpen ? 'flex' : 'none';

    if (state.isOpen && !state.sessionToken) {
      startSession();
    }
  }

  function renderMessages() {
    const container = document.getElementById('dograh-tw-messages');
    if (!container) return;

    let html = '';
    for (const turn of state.turns) {
      if (turn.user_message) {
        html += `<div class="dograh-tw-msg user">${escapeHtml(turn.user_message.text)}</div>`;
      }
      if (turn.assistant_message) {
        html += `<div class="dograh-tw-msg agent">${escapeHtml(turn.assistant_message.text)}</div>`;
      }
    }

    if (state.isConnecting) {
      html += `<div class="dograh-tw-typing">Connecting...</div>`;
    } else if (state.isSending) {
      html += `<div class="dograh-tw-typing">Agent is typing...</div>`;
    } else if (state.isCompleted) {
      html += `<div class="dograh-tw-typing">Chat ended</div>`;
    }

    container.innerHTML = html;
    container.scrollTop = container.scrollHeight;

    const input = document.getElementById('dograh-tw-input');
    const sendBtn = document.getElementById('dograh-tw-send');
    if (state.isCompleted) {
      if (input) {
        input.disabled = true;
        input.placeholder = "Chat ended";
      }
      if (sendBtn) {
        sendBtn.disabled = true;
      }
    }
  }

  function escapeHtml(unsafe) {
    return (unsafe || '').replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
  }

  async function startSession() {
    if (state.isConnecting) return;
    
    state.isConnecting = true;
    renderMessages();

    try {
      const response = await fetch(`${state.config.apiBaseUrl}/api/v1/public/text-embed/init`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: state.config.token })
      });

      if (!response.ok) throw new Error('Failed to start session');

      const data = await response.json();
      state.sessionToken = data.session_token;
      state.workflowRunId = data.workflow_run_id;
      
      if (data.text_session && data.text_session.session_data && data.text_session.session_data.turns) {
          state.turns = data.text_session.session_data.turns;
      }
      if (data.is_completed || (data.text_session && data.text_session.is_completed)) {
          state.isCompleted = true;
      }
    } catch (error) {
      console.error('Dograh Widget Error:', error);
      alert('Failed to connect to chat agent.');
    } finally {
      state.isConnecting = false;
      renderMessages();
    }
  }

  async function handleSend(e) {
    e.preventDefault();
    if (!state.sessionToken || state.isSending) return;

    const input = document.getElementById('dograh-tw-input');
    const text = input.value.trim();
    if (!text) return;

    input.value = '';
    state.isSending = true;
    
    // Optimistically add user message
    const tempTurnId = 'temp-' + Date.now();
    state.turns.push({
      id: tempTurnId,
      user_message: { text: text }
    });
    renderMessages();

    try {
      const response = await fetch(`${state.config.apiBaseUrl}/api/v1/public/text-embed/${state.sessionToken}/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: text })
      });

      if (!response.ok) throw new Error('Failed to send message');

      const data = await response.json();
      if (data.session_data && data.session_data.turns) {
          state.turns = data.session_data.turns;
      }
      if (data.is_completed) {
          state.isCompleted = true;
      }
    } catch (error) {
      console.error('Dograh Widget Error:', error);
      // Remove temp message on error
      state.turns = state.turns.filter(t => t.id !== tempTurnId);
      alert('Failed to send message.');
    } finally {
      state.isSending = false;
      renderMessages();
    }
  }

  // Initialize on load
  if (document.readyState === 'complete') {
    init();
  } else {
    window.addEventListener('load', init);
  }

})();
