/* ===========================================
   HaUI Chat - Student Side Logic
   =========================================== */

(function () {
  'use strict';

  // ---- DOM Elements ----
  const chatMessages = document.getElementById('chatMessages');
  const messageInput = document.getElementById('messageInput');
  const sendBtn = document.getElementById('sendBtn');
  const statusBar = document.getElementById('statusBar');
  let statusText = document.getElementById('statusText');
  const typingIndicator = document.getElementById('typingIndicator');
  const chatTitle = document.getElementById('chatTitle');
  const chatSubtitle = document.getElementById('chatSubtitle');

  // ---- State ----
  let studentData = null;
  let socket = null;
  let chatState = 'connecting'; // connecting | waiting | bot | counselor
  let typingTimeout = null;

  // ---- Init ----
  function init() {
    // Get student data from sessionStorage
    const stored = sessionStorage.getItem('studentData');
    if (!stored) {
      window.location.href = 'index.html';
      return;
    }

    studentData = JSON.parse(stored);

    // Update header based on branch
    if (studentData.branch === 'academic') {
      chatTitle.textContent = '🎓 Hỗ Trợ Học Tập';
    } else {
      chatTitle.textContent = '💚 Tư Vấn Tâm Lý';
    }
    chatSubtitle.textContent = `Xin chào, ${studentData.name}`;

    // Connect to server
    connectSocket();

    // Auto-resize textarea
    messageInput.addEventListener('input', autoResize);
  }

  // ---- Socket Connection ----
  function connectSocket() {
    socket = io(window.location.origin);

    socket.on('connect', () => {
      console.log('Connected to server');
      // Register as student with data (including avatarUrl if exists)
      socket.emit('student:join', studentData);
    });

    // When placed in queue or reconnected
    socket.on('student:queued', (data) => {
      // If we have history and the chat is empty, render it
      if (data.history && data.history.length > 0 && chatMessages.children.length <= 1) { 
        data.history.forEach(msg => {
          let avatarContent;
          if (msg.senderName === 'Bot') {
            avatarContent = '🤖';
          } else if (msg.type === 'sent') {
            avatarContent = studentData.avatarUrl ? `<img src="${studentData.avatarUrl}" style="width:100%;height:100%;border-radius:50%;object-fit:cover;">` : studentData.name.charAt(0);
          } else {
            avatarContent = msg.avatarUrl ? `<img src="${msg.avatarUrl}" style="width:100%;height:100%;border-radius:50%;object-fit:cover;">` : (msg.senderName?.charAt(0) || '👤');
          }
          addMessage(msg.text, msg.type, msg.senderName === 'Bot' ? 'bot' : '', avatarContent, msg.time);
        });
      }

      // Restore status
      if (data.status === 'chatting' && data.counselorName) {
        setStatus('counselor');
        statusText.textContent = `Đang chat với ${data.counselorName}`;
      } else if (data.status === 'waiting') {
        setStatus('waiting');
      }
    });

    // Bot starts chatting
    socket.on('bot:message', (data) => {
      if (chatState !== 'counselor') {
        setStatus('bot');
      }
      showTyping();
      setTimeout(() => {
        hideTyping();
        addMessage(data.message, 'received', 'bot', '🤖');
      }, 800 + Math.random() * 700);
    });

    // Counselor connected
    socket.on('counselor:connected', (data) => {
      setStatus('counselor');
      addSystemMessage(`Tư vấn viên ${data.counselorName} đã kết nối với bạn`);
    });

    // Receive message from counselor
    socket.on('chat:message', (data) => {
      hideTyping();
      const avatar = data.avatarUrl ? `<img src="${data.avatarUrl}" style="width:100%;height:100%;border-radius:50%;object-fit:cover;">` : (data.senderName?.charAt(0) || 'TV');
      addMessage(data.message, 'received', 'received', avatar);
    });

    // Counselor typing
    socket.on('counselor:typing', () => {
      showTyping();
    });

    socket.on('counselor:stopTyping', () => {
      hideTyping();
    });

    // Chat ended
    socket.on('chat:ended', (data) => {
      addSystemMessage(data.message || 'Cuộc trò chuyện đã kết thúc');
      messageInput.disabled = true;
      sendBtn.disabled = true;
      setStatus('waiting');
      statusText.textContent = 'Cuộc tư vấn đã kết thúc';
    });

    socket.on('disconnect', () => {
      addSystemMessage('Mất kết nối với server...');
    });

    socket.on('connect_error', () => {
      addSystemMessage('Không thể kết nối đến server. Vui lòng thử lại sau.');
    });
  }

  // ---- Messages ----
  function addMessage(text, type, msgClass, avatar, timestamp) {
    const div = document.createElement('div');
    div.className = `message ${type} ${msgClass || ''}`;

    const dateObj = timestamp ? new Date(timestamp * 1000) : new Date();
    const time = dateObj.toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' });

    div.innerHTML = `
      <div class="message-avatar">${avatar || (type === 'sent' ? '👤' : '📋')}</div>
      <div class="message-content">
        <div class="message-bubble">${escapeHtml(text)}</div>
        <span class="message-time">${time}</span>
      </div>
    `;

    chatMessages.insertBefore(div, typingIndicator);
    scrollToBottom();
  }

  function addSystemMessage(text) {
    const div = document.createElement('div');
    div.className = 'system-message';
    div.innerHTML = `<span>${text}</span>`;
    chatMessages.insertBefore(div, typingIndicator);
    scrollToBottom();
  }

  // ---- Send Message ----
  function sendMessage() {
    const text = messageInput.value.trim();
    if (!text || !socket) return;

    const myAvatar = studentData.avatarUrl ? `<img src="${studentData.avatarUrl}" style="width:100%;height:100%;border-radius:50%;object-fit:cover;">` : studentData.name?.charAt(0);
    addMessage(text, 'sent', '', myAvatar);
    socket.emit('chat:message', { message: text });

    messageInput.value = '';
    messageInput.style.height = 'auto';
    messageInput.focus();
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }

    // Send typing indicator
    if (socket && chatState === 'counselor') {
      socket.emit('student:typing');
      clearTimeout(typingTimeout);
      typingTimeout = setTimeout(() => {
        socket.emit('student:stopTyping');
      }, 1000);
    }
  }

  // ---- Status ----
  function setStatus(state) {
    chatState = state;
    statusBar.className = 'chat-status-bar';

    switch (state) {
      case 'waiting':
        statusBar.classList.add('waiting');
        statusBar.innerHTML = `<span class="pulse yellow"></span><span id="statusText">Đang chờ tư vấn viên...</span>`;
        break;
      case 'bot':
        statusBar.classList.add('bot');
        statusBar.innerHTML = `<span class="pulse purple"></span><span id="statusText">🤖 Bot tự động đang hỗ trợ bạn</span>`;
        break;
      case 'counselor':
        statusBar.classList.add('connected');
        statusBar.innerHTML = `<span class="pulse green"></span><span id="statusText">Đang chat với tư vấn viên</span>`;
        break;
    }
    statusText = document.getElementById('statusText');
  }

  // ---- Typing ----
  function showTyping() {
    typingIndicator.classList.add('active');
    scrollToBottom();
  }

  function hideTyping() {
    typingIndicator.classList.remove('active');
  }

  // ---- Helpers ----
  function scrollToBottom() {
    requestAnimationFrame(() => {
      chatMessages.scrollTop = chatMessages.scrollHeight;
    });
  }

  function autoResize() {
    this.style.height = 'auto';
    this.style.height = Math.min(this.scrollHeight, 120) + 'px';
  }

  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  // ---- End Chat ----
  window.endChat = function () {
    try {
      if (socket) {
        socket.emit('chat:end');
        socket.disconnect();
      }
    } catch (e) {
      console.error('Error ending chat:', e);
    }
    sessionStorage.removeItem('studentData');
    window.location.href = 'index.html';
  };

  // ---- Expose ----
  window.sendMessage = sendMessage;
  window.handleKeyDown = handleKeyDown;

  // ---- Start ----
  init();
})();
