/* ===========================================
   HaUI Chat - Admin / Counselor Side Logic
   =========================================== */

(function () {
  'use strict';

  // ---- State ----
  let socket = null;
  let counselorName = '';
  let currentFilter = 'all';
  let activeStudentId = null;
  let isAccepted = false;
  let students = {}; // { sessionId: { data, messages, status, isOnline } }
  let typingTimeout = null;

  // ---- Login ----
  window.doLogin = function (e) {
    e.preventDefault();
    const userField = document.getElementById('loginUser');
    const passField = document.getElementById('loginPass');
    const nameField = document.getElementById('counselorName');

    const user = userField ? userField.value.trim() : '';
    const pass = passField ? passField.value.trim() : '';
    counselorName = nameField ? nameField.value.trim() : 'Tư vấn viên';

    if (user === 'admin' && pass === 'haui2026') {
      sessionStorage.setItem('adminSession', JSON.stringify({ name: counselorName }));
      showDashboard();
      connectSocket();
    } else {
      showNotification('Sai tên đăng nhập hoặc mật khẩu!', 'error');
    }
  };

  window.doLogout = function () {
    if (confirm('Bạn có muốn đăng xuất?')) {
      if (socket) socket.disconnect();
      sessionStorage.removeItem('adminSession');
      location.reload();
    }
  };

  function showDashboard() {
    const loginPage = document.getElementById('loginPage');
    const adminDashboard = document.getElementById('adminDashboard');
    const adminGreeting = document.getElementById('adminGreeting');

    if (loginPage) loginPage.style.display = 'none';
    if (adminDashboard) adminDashboard.style.display = 'flex';
    if (adminGreeting) adminGreeting.textContent = `Xin chào, ${counselorName}`;
  }

  // ---- Socket ----
  function connectSocket() {
    socket = io(window.location.origin);

    socket.on('connect', () => {
      socket.emit('counselor:join', { name: counselorName });
      console.log('[Socket] Connected as counselor');
    });

    socket.on('queue:update', (queue) => {
      queue.forEach(s => {
        if (!students[s.id]) {
          students[s.id] = { 
            data: s, 
            messages: s.messages || [], 
            status: s.status, 
            isOnline: s.isOnline 
          };
        } else {
          students[s.id].data = s;
          students[s.id].isOnline = s.isOnline;
          students[s.id].messages = s.messages || [];
          if (students[s.id].status !== 'chatting') {
            students[s.id].status = s.status;
          }
        }
      });

      const currentIds = new Set(queue.map(s => s.id));
      Object.keys(students).forEach(id => {
        if (!currentIds.has(id)) {
          delete students[id];
          if (activeStudentId === id) {
            activeStudentId = null;
            isAccepted = false;
            showEmptyChat();
          }
        }
      });

      renderQueue();

      const lastStudent = sessionStorage.getItem('lastActiveStudent');
      if (lastStudent && students[lastStudent] && !activeStudentId) {
        selectStudent(lastStudent);
      }
    });

    socket.on('student:online', (data) => {
      if (students[data.sessionId]) {
        students[data.sessionId].isOnline = true;
        if (activeStudentId === data.sessionId) {
          addAdminSystemMessage('🟢 Sinh viên đã quay lại');
          updateInputAreaState();
        }
        renderQueue();
      }
    });

    socket.on('student:offline', (data) => {
      if (students[data.sessionId]) {
        students[data.sessionId].isOnline = false;
        if (activeStudentId === data.sessionId) {
          addAdminSystemMessage('⚪ Sinh viên đã tạm thời rời trang');
        }
        renderQueue();
      }
    });

    socket.on('chat:message', (data) => {
      const { sessionId, message, senderName, avatarUrl } = data;
      if (students[sessionId]) {
        students[sessionId].messages.push({
          text: message,
          type: 'received',
          sender: senderName,
          time: new Date(),
          avatarUrl: avatarUrl
        });

        if (activeStudentId === sessionId) {
          const avatar = avatarUrl ? `<img src="${avatarUrl}" style="width:100%;height:100%;border-radius:50%;object-fit:cover;">` : senderName?.charAt(0);
          appendMessage(message, 'received', avatar);
          hideAdminTyping();
        }
      }
      playNotificationSound();
      renderQueue();
    });

    socket.on('student:typing', (data) => {
      if (data.sessionId === activeStudentId) showAdminTyping();
    });

    socket.on('student:stopTyping', (data) => {
      if (data.sessionId === activeStudentId) hideAdminTyping();
    });

    socket.on('chat:ended', (data) => {
      const sId = data.sessionId || data.studentId;
      if (students[sId]) {
        delete students[sId];
        if (activeStudentId === sId) {
          activeStudentId = null;
          isAccepted = false;
          showEmptyChat();
        }
      }
      renderQueue();
    });

    socket.on('disconnect', () => {
      showNotification('Mất kết nối server!', 'error');
    });
  }

  // ---- Rendering ----
  function renderQueue() {
    const list = document.getElementById('queueList');
    if (!list) return;

    const badgeAll = document.getElementById('badgeAll');
    const studentArr = Object.entries(students).filter(([id, s]) => {
      if (currentFilter === 'all') return true;
      return s.data.branch === currentFilter;
    });

    if (badgeAll) badgeAll.textContent = Object.keys(students).length;

    const emptyEl = document.getElementById('emptyQueue');
    if (studentArr.length === 0) {
      list.innerHTML = '';
      if (emptyEl) {
        list.appendChild(emptyEl);
        emptyEl.style.display = 'flex';
      }
      return;
    }

    if (emptyEl) emptyEl.style.display = 'none';
    list.innerHTML = '';

    studentArr.forEach(([id, student]) => {
      const s = student.data;
      const item = document.createElement('div');
      item.className = `queue-item ${activeStudentId === id ? 'active' : ''} ${student.isOnline ? 'online' : 'offline'}`;
      item.onclick = () => selectStudent(id);

      const statusBadge = student.status === 'chatting'
        ? '<span class="queue-item-badge chatting">Đang chat</span>'
        : '<span class="queue-item-badge waiting">Chờ</span>';

      const branchBadge = s.branch === 'academic'
        ? '<span class="queue-item-badge academic">🎓</span>'
        : '<span class="queue-item-badge psychology">💚</span>';

      const avatarContent = s.avatarUrl 
        ? `<img src="${s.avatarUrl}" style="width:100%;height:100%;border-radius:50%;object-fit:cover;">`
        : (s.name?.charAt(0) || '?');

      const onlineIndicator = student.isOnline
        ? '<span class="online-dot" title="Online" style="width:10px;height:10px;background:#10B981;border-radius:50%;border:2px solid white;position:absolute;bottom:0;right:0;"></span>'
        : '<span class="online-dot" title="Offline" style="width:10px;height:10px;background:#9CA3AF;border-radius:50%;border:2px solid white;position:absolute;bottom:0;right:0;"></span>';

      item.style.position = 'relative';
      item.innerHTML = `
        <div style="position:relative; width:40px; height:40px;">
          <div class="queue-item-avatar">${avatarContent}</div>
          ${onlineIndicator}
        </div>
        <div class="queue-item-info">
          <div class="queue-item-name">${escapeHtml(s.name)} ${!student.isOnline ? '<small>(Offline)</small>' : ''}</div>
          <div class="queue-item-detail">${escapeHtml(s.issue?.substring(0, 40) || '...')}</div>
        </div>
        <div style="display:flex; flex-direction:column; gap:4px; align-items:flex-end;">
          ${branchBadge}
          ${statusBadge}
        </div>
      `;
      list.appendChild(item);
    });
  }

  window.selectStudent = function (sessionId) {
    if (!sessionId) return;
    activeStudentId = sessionId;
    sessionStorage.setItem('lastActiveStudent', sessionId);
    const student = students[sessionId];
    if (!student) return;

    isAccepted = student.status === 'chatting';
    const s = student.data;

    const emptyChat = document.getElementById('emptyChatState');
    const container = document.getElementById('activeChatContainer');
    if (emptyChat) emptyChat.style.display = 'none';
    if (container) container.classList.add('active');

    const avatar = document.getElementById('activeChatAvatar');
    const name = document.getElementById('activeChatName');
    const detail = document.getElementById('activeChatDetail');
    
    if (avatar) {
      avatar.innerHTML = s.avatarUrl 
        ? `<img src="${s.avatarUrl}" style="width:100%;height:100%;border-radius:50%;object-fit:cover;">`
        : (s.name?.charAt(0) || '?');
    }
    if (name) name.textContent = s.name;
    if (detail) detail.textContent = `MSV: ${s.studentId} | Lớp: ${s.className}`;

    updateInputAreaState();
    renderStudentMessages(sessionId);
    renderQueue();
  };

  function updateInputAreaState() {
    const acceptBtn = document.getElementById('acceptBtn');
    const endChatBtn = document.getElementById('endChatBtn');
    const inputArea = document.getElementById('adminInputArea');

    if (isAccepted) {
      if (acceptBtn) acceptBtn.style.display = 'none';
      if (endChatBtn) endChatBtn.style.display = 'inline-flex';
      if (inputArea) inputArea.style.display = 'block';
    } else {
      if (acceptBtn) acceptBtn.style.display = 'inline-flex';
      if (endChatBtn) endChatBtn.style.display = 'none';
      if (inputArea) inputArea.style.display = 'none';
    }
  }

  function renderStudentMessages(sessionId) {
    const container = document.getElementById('adminChatMessages');
    const typingEl = document.getElementById('adminTypingIndicator');
    if (!container) return;
    container.innerHTML = '';

    const student = students[sessionId];
    if (!student) return;

    addAdminSystemMessage(`📋 Vấn đề: "${student.data.issue}"`);

    student.messages.forEach((msg) => {
      let avatarContent;
      if (msg.type === 'sent') {
        avatarContent = counselorName.charAt(0);
      } else {
        avatarContent = msg.avatarUrl 
            ? `<img src="${msg.avatarUrl}" style="width:100%;height:100%;border-radius:50%;object-fit:cover;">` 
            : (msg.sender?.charAt(0) || '👤');
      }
      appendMessage(msg.text, msg.type, avatarContent);
    });

    if (typingEl) container.appendChild(typingEl);
    container.scrollTop = container.scrollHeight;
  }

  // ---- Interaction ----
  window.acceptChat = function () {
    if (!activeStudentId || !socket) return;
    socket.emit('counselor:accept', { sessionId: activeStudentId });
    students[activeStudentId].status = 'chatting';
    isAccepted = true;
    updateInputAreaState();
    addAdminSystemMessage(`✅ Bạn đã bắt đầu tư vấn cho ${students[activeStudentId].data.name}`);
    renderQueue();
  };

  window.sendAdminMessage = function () {
    const input = document.getElementById('adminMessageInput');
    const text = input ? input.value.trim() : '';
    if (!text || !socket || !activeStudentId) return;

    socket.emit('chat:message', { sessionId: activeStudentId, message: text });
    students[activeStudentId].messages.push({
      text,
      type: 'sent',
      sender: counselorName,
      time: new Date()
    });

    appendMessage(text, 'sent', counselorName.charAt(0));
    if (input) {
      input.value = '';
      input.style.height = 'auto';
      input.focus();
    }
  };

  window.handleAdminKeyDown = function (e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendAdminMessage();
    }
    if (socket && activeStudentId && isAccepted) {
      socket.emit('counselor:typing', { sessionId: activeStudentId });
      clearTimeout(typingTimeout);
      typingTimeout = setTimeout(() => {
        socket.emit('counselor:stopTyping', { sessionId: activeStudentId });
      }, 1000);
    }
  };

  window.endCurrentChat = function () {
    if (!activeStudentId || !socket) return;
    if (!confirm('Kết thúc cuộc tư vấn này?')) return;
    socket.emit('chat:end', { sessionId: activeStudentId });
    delete students[activeStudentId];
    activeStudentId = null;
    isAccepted = false;
    showEmptyChat();
    renderQueue();
  };

  window.filterQueue = function (filter, btn) {
    currentFilter = filter;
    document.querySelectorAll('.sidebar-tab').forEach(t => t.classList.remove('active'));
    if (btn) btn.classList.add('active');
    renderQueue();
  };

  // ---- Helpers ----
  function appendMessage(text, type, avatar) {
    const container = document.getElementById('adminChatMessages');
    if (!container) return;
    const typingEl = document.getElementById('adminTypingIndicator');

    const div = document.createElement('div');
    div.className = `message ${type}`;
    div.innerHTML = `
      <div class="message-avatar">${avatar || '?'}</div>
      <div class="message-content">
        <div class="message-bubble">${escapeHtml(text)}</div>
      </div>
    `;

    if (typingEl) container.insertBefore(div, typingEl);
    else container.appendChild(div);
    container.scrollTop = container.scrollHeight;
  }

  function addAdminSystemMessage(text) {
    const container = document.getElementById('adminChatMessages');
    if (!container) return;
    const typingEl = document.getElementById('adminTypingIndicator');
    const div = document.createElement('div');
    div.className = 'system-message';
    div.innerHTML = `<span>${text}</span>`;
    if (typingEl) container.insertBefore(div, typingEl);
    else container.appendChild(div);
    container.scrollTop = container.scrollHeight;
  }

  function showEmptyChat() {
    const empty = document.getElementById('emptyChatState');
    const container = document.getElementById('activeChatContainer');
    if (empty) empty.style.display = 'flex';
    if (container) container.classList.remove('active');
  }

  function showAdminTyping() {
    const el = document.getElementById('adminTypingIndicator');
    if (el) el.classList.add('active');
  }

  function hideAdminTyping() {
    const el = document.getElementById('adminTypingIndicator');
    if (el) el.classList.remove('active');
  }

  function showNotification(msg, type) {
    const div = document.createElement('div');
    div.className = `notification ${type}`;
    div.textContent = msg;
    document.body.appendChild(div);
    setTimeout(() => div.remove(), 3000);
  }

  function playNotificationSound() {
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain); gain.connect(ctx.destination);
      osc.frequency.value = 800; osc.start(); osc.stop(ctx.currentTime + 0.1);
    } catch(e) {}
  }

  function escapeHtml(text) {
    const d = document.createElement('div');
    d.textContent = text;
    return d.innerHTML;
  }

  // ---- Init ----
  const stored = sessionStorage.getItem('adminSession');
  if (stored) {
    const data = JSON.parse(stored);
    counselorName = data.name;
    showDashboard();
    connectSocket();
  }
})();
