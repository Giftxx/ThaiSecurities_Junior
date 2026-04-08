// ===== CONFIG =====
const API_BASE = window.location.origin; // same host as FastAPI

const md = window.markdownit({ html: false, linkify: true, typographer: true,
    highlight: (str, lang) => {
        if (lang && hljs.getLanguage(lang)) {
            try { return '<pre><code class="hljs">' + hljs.highlight(str, { language: lang, ignoreIllegals: true }).value + '</code></pre>'; }
            catch (_) {}
        }
        return '<pre><code class="hljs">' + md.utils.escapeHtml(str) + '</code></pre>';
    }
});

// ===== STATE =====
let chats = JSON.parse(localStorage.getItem('qs_chats') || '[]'); // [{id, title, messages:[]}]
let activeChatId = null;
let isLoading = false;

// ===== DOM REFS =====
const messagesEl   = document.getElementById('messages');
const userInput    = document.getElementById('userInput');
const sendBtn      = document.getElementById('sendButton');
const stopBtn      = document.getElementById('stopButton');
const clearBtn     = document.getElementById('clearBtn');
const nsSelector   = document.getElementById('nsSelector');
const topkRange    = document.getElementById('topkRange');
const topkLabel    = document.getElementById('topkLabel');
const chatListEl   = document.getElementById('chatListEle');
const newChatBtn   = document.getElementById('newChatButton');
const themeBtn     = document.getElementById('themeToggleBtn');
const fileInput    = document.getElementById('fileInput');
const uploadedFilesEl = document.getElementById('uploadedFiles');
const themeIcon    = document.getElementById('themeIcon');
const themeLabel   = document.getElementById('themeLabel');
const toggleSidebarBtn = document.getElementById('toggleSidebarButton');
const sidebar      = document.getElementById('chatList');

// ===== FILE UPLOAD =====
// Track which files have been successfully uploaded per chat_id
const _uploadedFiles = {}; // { chat_id: [{name, chunks}] }

function getUploadedFiles(chatId) {
    return _uploadedFiles[chatId] || [];
}

function renderUploadedFiles(chatId) {
    const files = getUploadedFiles(chatId);
    if (files.length === 0) {
        uploadedFilesEl.style.display = 'none';
        uploadedFilesEl.innerHTML = '';
        return;
    }
    uploadedFilesEl.style.display = 'flex';
    uploadedFilesEl.innerHTML = '';
    files.forEach((f, idx) => {
        const chip = document.createElement('span');
        chip.className = 'file-chip';
        chip.innerHTML = `<i class="fas fa-file-alt"></i><span title="${f.name}">${f.name}</span>
            <button class="chip-remove" title="Remove file" data-idx="${idx}"><i class="fas fa-times"></i></button>`;
        chip.querySelector('.chip-remove').addEventListener('click', () => removeFile(chatId, idx));
        uploadedFilesEl.appendChild(chip);
    });
}

async function removeFile(chatId, idx) {
    if (!_uploadedFiles[chatId]) return;
    const file = _uploadedFiles[chatId][idx];
    // Remove individual file from server
    try {
        await fetch(`${API_BASE}/upload/file?chat_id=${encodeURIComponent(chatId)}&filename=${encodeURIComponent(file.name)}`, { method: 'DELETE' });
    } catch {}
    _uploadedFiles[chatId].splice(idx, 1);
    renderUploadedFiles(chatId);
}

function fileToBase64(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => {
            // Remove data URL prefix ("data:...;base64,")
            const b64 = reader.result.split(',')[1];
            resolve(b64);
        };
        reader.onerror = reject;
        reader.readAsDataURL(file);
    });
}

async function uploadFile(file, chatId) {
    // Show uploading chip
    const tempChip = document.createElement('span');
    tempChip.className = 'file-chip uploading';
    tempChip.innerHTML = `<i class="fas fa-spinner fa-spin"></i><span>${file.name}</span>`;
    uploadedFilesEl.style.display = 'flex';
    uploadedFilesEl.appendChild(tempChip);

    try {
        const b64 = await fileToBase64(file);
        const res = await fetch(`${API_BASE}/upload`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ chat_id: chatId, filename: file.name, content_b64: b64 }),
        });
        tempChip.remove();
        if (!res.ok) {
            const err = await res.json();
            appendSystemMessage(`⚠️ Upload failed for **${file.name}**: ${err.detail || res.status}`);
            return;
        }
        const data = await res.json();
        if (!_uploadedFiles[chatId]) _uploadedFiles[chatId] = [];
        _uploadedFiles[chatId].push({ name: file.name, chunks: data.chunks_added });
        renderUploadedFiles(chatId);
        appendSystemMessage(`✅ **${file.name}** uploaded — ${data.chunks_added} chunks indexed.`);
    } catch (e) {
        tempChip.remove();
        appendSystemMessage(`⚠️ Upload error for **${file.name}**: ${e.message}`);
    }
}

fileInput.addEventListener('change', async () => {
    const chat = getActiveChat();
    if (!chat) return;
    const files = Array.from(fileInput.files);
    for (const f of files) {
        await uploadFile(f, chat.id);
    }
    fileInput.value = '';
});

function appendSystemMessage(markdownText) {
    const welcome = messagesEl.querySelector('.welcome-card');
    if (welcome) welcome.remove();
    const div = document.createElement('div');
    div.className = 'agent-message system-msg';
    div.innerHTML = md.render(markdownText);
    messagesEl.appendChild(div);
    scrollToBottom();
}

// ===== THEME =====
function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    document.body.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
    if (theme === 'dark') {
        themeIcon.className = 'fas fa-moon';
        themeLabel.textContent = 'Dark Mode';
    } else {
        themeIcon.className = 'fas fa-sun';
        themeLabel.textContent = 'Light Mode';
    }
}

themeBtn.addEventListener('click', () => {
    const current = document.documentElement.getAttribute('data-theme') || 'dark';
    applyTheme(current === 'dark' ? 'light' : 'dark');
});

// Apply saved theme on load
applyTheme(localStorage.getItem('theme') || 'dark');

// ===== SIDEBAR TOGGLE =====
toggleSidebarBtn.addEventListener('click', () => {
    sidebar.classList.toggle('collapsed');
});

// ===== TOP-K SLIDER =====
topkRange.addEventListener('input', () => { topkLabel.textContent = topkRange.value; });

// ===== API STATUS + NAMESPACES =====
async function checkAPI() {
    try {
        const r = await fetch(`${API_BASE}/namespaces`);
        const data = await r.json();
        (data.namespaces || []).forEach(ns => {
            const opt = document.createElement('option');
            opt.value = ns;
            opt.textContent = ns.replace(/_/g, ' ');
            nsSelector.appendChild(opt);
        });
    } catch {}
}

// ===== CHAT MANAGEMENT =====
function saveChats() { localStorage.setItem('qs_chats', JSON.stringify(chats)); }

function createNewChat() {
    const id = Date.now().toString();
    chats.unshift({ id, title: 'New chat', messages: [] });
    activeChatId = id;
    saveChats();
    renderChatList();
    renderMessages();
}

function loadChat(id) {
    activeChatId = id;
    renderChatList();
    renderMessages();
    // Fetch server-side uploaded files (survives page reload while server is up)
    fetchUploadedFiles(id);
}

async function fetchUploadedFiles(chatId) {
    try {
        const r = await fetch(`${API_BASE}/upload/files?chat_id=${encodeURIComponent(chatId)}`);
        if (!r.ok) return;
        const data = await r.json();
        const serverFiles = (data.files || []);
        if (serverFiles.length > 0) {
            // Merge: prefer server truth, keep local chunk counts where available
            const localFiles = _uploadedFiles[chatId] || [];
            const localMap = {};
            localFiles.forEach(f => { localMap[f.name] = f.chunks; });
            _uploadedFiles[chatId] = serverFiles.map(name => ({ name, chunks: localMap[name] || '?' }));
        }
    } catch {}
    renderUploadedFiles(chatId);
}

function getActiveChat() { return chats.find(c => c.id === activeChatId); }

function renderChatList() {
    chatListEl.innerHTML = '';
    chats.forEach(chat => {
        const div = document.createElement('div');
        div.className = 'chat-history-item' + (chat.id === activeChatId ? ' active' : '');
        div.textContent = chat.title;
        div.title = chat.title;
        div.addEventListener('click', () => loadChat(chat.id));
        chatListEl.appendChild(div);
    });
}

// ===== RENDER MESSAGES =====
function renderMessages() {
    const chat = getActiveChat();
    if (!chat || chat.messages.length === 0) {
        messagesEl.innerHTML = `
            <div class="welcome-card">
                <div class="welcome-icon">📈</div>
                <h2>Thai Securities Q&A</h2>
                <p>Ask anything about Thai stocks, market data, SET regulations, and investment research.</p>
                <div class="welcome-tags">
                    <span class="tag">Stock Ratings</span>
                    <span class="tag">Market Reports</span>
                    <span class="tag">Regulations</span>
                    <span class="tag">Company Profiles</span>
                </div>
            </div>`;
        return;
    }
    messagesEl.innerHTML = '';
    chat.messages.forEach(msg => appendMessageToDOM(msg, false));
    scrollToBottom();
}

function appendMessageToDOM(msg, doScroll = true) {
    if (msg.role === 'user') {
        const div = document.createElement('div');
        div.className = 'user-message';
        div.textContent = msg.content;
        messagesEl.appendChild(div);
    } else {
        const div = document.createElement('div');
        div.className = 'agent-message';

        if (msg.namespace_used) {
            const badge = document.createElement('span');
            badge.className = 'ns-badge';
            badge.textContent = '🗂 ' + msg.namespace_used.replace(/_/g, ' ');
            div.appendChild(badge);
        }

        const body = document.createElement('div');
        body.innerHTML = md.render(msg.content);
        div.appendChild(body);

        if (msg.sources && msg.sources.length > 0) {
            const row = document.createElement('div');
            row.className = 'sources-row';
            row.innerHTML = '<span class="sources-label">Sources:</span>';
            msg.sources.forEach(s => {
                const chip = document.createElement('span');
                chip.className = 'source-chip';
                chip.textContent = s;
                row.appendChild(chip);
            });
            div.appendChild(row);
        }

        if (msg.latency_ms != null) {
            const lat = document.createElement('span');
            lat.className = 'latency-badge';
            lat.textContent = `⚡ ${Math.round(msg.latency_ms)} ms`;
            div.appendChild(lat);
        }

        messagesEl.appendChild(div);
    }
    if (doScroll) scrollToBottom();
}

function scrollToBottom() {
    messagesEl.scrollTop = messagesEl.scrollHeight;
}

// ===== TYPING INDICATOR =====
function showTyping() {
    const div = document.createElement('div');
    div.className = 'agent-message';
    div.id = 'typingIndicator';
    div.innerHTML = '<div class="typing-dots"><span></span><span></span><span></span></div>';
    messagesEl.appendChild(div);
    scrollToBottom();
}

function removeTyping() {
    const el = document.getElementById('typingIndicator');
    if (el) el.remove();
}

// ===== SEND MESSAGE =====
async function sendMessage() {
    const question = userInput.value.trim();
    if (!question || isLoading) return;

    let chat = getActiveChat();
    if (!chat) { createNewChat(); chat = getActiveChat(); }

    // Remove welcome card
    const welcome = messagesEl.querySelector('.welcome-card');
    if (welcome) welcome.remove();

    // User message
    const userMsg = { role: 'user', content: question };
    chat.messages.push(userMsg);
    if (chat.title === 'New chat') { chat.title = question.slice(0, 40) + (question.length > 40 ? '…' : ''); }
    saveChats();
    renderChatList();
    appendMessageToDOM(userMsg);

    userInput.value = '';
    autoResizeTextarea();
    sendBtn.disabled = true;
    isLoading = true;
    showTyping();

    try {
        const payload = {
            question,
            top_k: parseInt(topkRange.value),
            chat_id: chat.id,
        };
        const ns = nsSelector.value;
        if (ns) payload.namespace = ns;

        const t0 = performance.now();
        const r = await fetch(`${API_BASE}/query`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });

        removeTyping();

        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const data = await r.json();
        const latency = data.latency_ms ?? (performance.now() - t0);

        const assistantMsg = {
            role: 'assistant',
            content: data.answer,
            sources: data.sources || [],
            namespace_used: data.namespace_used || '',
            latency_ms: latency,
        };
        chat.messages.push(assistantMsg);
        saveChats();
        appendMessageToDOM(assistantMsg);

    } catch (err) {
        removeTyping();
        const errMsg = {
            role: 'assistant',
            content: `**Error:** ${err.message}\n\nMake sure the API server is running at \`${API_BASE}\``,
            sources: [],
        };
        chat.messages.push(errMsg);
        saveChats();
        appendMessageToDOM(errMsg);
    } finally {
        isLoading = false;
        sendBtn.disabled = false;
    }
}

// ===== CLEAR CHAT =====
clearBtn.addEventListener('click', () => {
    const chat = getActiveChat();
    if (!chat) return;
    chat.messages = [];
    chat.title = 'New chat';
    // Also clear uploaded files for this chat
    if (_uploadedFiles[chat.id]) {
        delete _uploadedFiles[chat.id];
        fetch(`${API_BASE}/upload/files?chat_id=${encodeURIComponent(chat.id)}`, { method: 'DELETE' }).catch(() => {});
    }
    saveChats();
    renderChatList();
    renderMessages();
    renderUploadedFiles(chat.id);
});

// ===== NEW CHAT =====
newChatBtn.addEventListener('click', createNewChat);

// ===== SEND BUTTON + ENTER KEY =====
sendBtn.addEventListener('click', sendMessage);

userInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

// ===== AUTO-RESIZE TEXTAREA =====
function autoResizeTextarea() {
    userInput.style.height = 'auto';
    userInput.style.height = Math.min(userInput.scrollHeight, 200) + 'px';
}
userInput.addEventListener('input', autoResizeTextarea);

// ===== INIT =====
checkAPI();

// Load or create first chat
if (chats.length === 0) {
    createNewChat();
} else {
    activeChatId = chats[0].id;
    renderChatList();
    renderMessages();
    fetchUploadedFiles(activeChatId);
}
