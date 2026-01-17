// WA Legislative Tracker 2026 - Enhanced JavaScript Application
// With committee meetings display, persistent cookies, note management, and proper sharing

const APP_CONFIG = {
    siteName: 'WA Bill Tracker',
    siteUrl: 'https://jeff-is-working.github.io/wa-bill-tracker',
    cookieDuration: 90,
    autoSaveInterval: 30000,
    dataRefreshInterval: 3600000,
    githubDataUrl: 'https://raw.githubusercontent.com/jeff-is-working/wa-bill-tracker/main/data/bills.json',
    meetingsDataUrl: 'https://raw.githubusercontent.com/jeff-is-working/wa-bill-tracker/main/data/meetings.json',
    sessionEnd: new Date('2026-03-12')
};

const APP_STATE = {
    bills: [],
    meetings: [],
    trackedBills: new Set(),
    userNotes: {},
    filters: { search: '', status: '', priority: '', committee: '', type: '', trackedOnly: false },
    lastSync: null,
    userData: { name: 'Guest User', avatar: '?', id: null },
    currentView: 'main',
    currentNoteBillId: null
};

const CookieManager = {
    set(name, value, days = APP_CONFIG.cookieDuration) {
        const expires = new Date();
        expires.setTime(expires.getTime() + (days * 24 * 60 * 60 * 1000));
        const cookieValue = typeof value === 'object' ? JSON.stringify(value) : value;
        document.cookie = name + '=' + encodeURIComponent(cookieValue) + ';expires=' + expires.toUTCString() + ';path=/;SameSite=Lax';
    },
    get(name) {
        const nameEQ = name + "=";
        const cookies = document.cookie.split(';');
        for (let cookie of cookies) {
            cookie = cookie.trim();
            if (cookie.indexOf(nameEQ) === 0) {
                const value = decodeURIComponent(cookie.substring(nameEQ.length));
                try { return JSON.parse(value); } catch { return value; }
            }
        }
        return null;
    },
    delete(name) { document.cookie = name + '=;expires=Thu, 01 Jan 1970 00:00:01 GMT;path=/;'; }
};

const StorageManager = {
    save() {
        try {
            CookieManager.set('wa_tracker_tracked', Array.from(APP_STATE.trackedBills));
            CookieManager.set('wa_tracker_notes', APP_STATE.userNotes);
            CookieManager.set('wa_tracker_user', APP_STATE.userData);
            CookieManager.set('wa_tracker_filters', APP_STATE.filters);
            localStorage.setItem('wa_tracker_state', JSON.stringify({
                trackedBills: Array.from(APP_STATE.trackedBills),
                userNotes: APP_STATE.userNotes,
                userData: APP_STATE.userData,
                filters: APP_STATE.filters,
                lastSaved: new Date().toISOString()
            }));
            return true;
        } catch (error) { console.error('Error saving state:', error); return false; }
    },
    load() {
        try {
            const trackedFromCookie = CookieManager.get('wa_tracker_tracked');
            const notesFromCookie = CookieManager.get('wa_tracker_notes');
            const userFromCookie = CookieManager.get('wa_tracker_user');
            const filtersFromCookie = CookieManager.get('wa_tracker_filters');
            if (trackedFromCookie || notesFromCookie || userFromCookie) {
                APP_STATE.trackedBills = new Set(trackedFromCookie || []);
                APP_STATE.userNotes = notesFromCookie || {};
                APP_STATE.userData = userFromCookie || APP_STATE.userData;
                APP_STATE.filters = filtersFromCookie || APP_STATE.filters;
                return true;
            }
            const saved = localStorage.getItem('wa_tracker_state');
            if (saved) {
                const data = JSON.parse(saved);
                APP_STATE.trackedBills = new Set(data.trackedBills || []);
                APP_STATE.userNotes = data.userNotes || {};
                APP_STATE.userData = data.userData || APP_STATE.userData;
                APP_STATE.filters = data.filters || APP_STATE.filters;
                StorageManager.save();
                return true;
            }
            return false;
        } catch (error) { console.error('Error loading state:', error); return false; }
    }
};

document.addEventListener('DOMContentLoaded', async () => {
    initializeUser();
    StorageManager.load();
    await loadAllData();
    setupEventListeners();
    setupAutoSave();
    updateUI();
    checkForSharedBill();
});

function initializeUser() {
    let userId = CookieManager.get('wa_tracker_user_id');
    if (!userId) {
        userId = 'user_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
        CookieManager.set('wa_tracker_user_id', userId, 365);
    }
    APP_STATE.userData.id = userId;
    if (!APP_STATE.userData.name || APP_STATE.userData.name === 'Guest User') {
        const savedName = CookieManager.get('wa_tracker_user_name');
        if (savedName) {
            APP_STATE.userData.name = savedName;
            APP_STATE.userData.avatar = savedName.charAt(0).toUpperCase();
        }
    }
}

async function loadAllData() {
    await Promise.all([loadBillsData(), loadMeetingsData()]);
}

async function loadBillsData() {
    try {
        const response = await fetch(APP_CONFIG.githubDataUrl);
        if (response.ok) {
            const data = await response.json();
            APP_STATE.bills = data.bills || [];
            APP_STATE.lastSync = data.lastSync || new Date().toISOString();
            localStorage.setItem('billsData', JSON.stringify(data));
            showToast('Loaded ' + APP_STATE.bills.length + ' bills');
        } else { throw new Error('Failed to fetch from GitHub'); }
    } catch (error) {
        console.error('Error loading from GitHub:', error);
        const cachedData = localStorage.getItem('billsData');
        if (cachedData) {
            const data = JSON.parse(cachedData);
            APP_STATE.bills = data.bills || [];
            APP_STATE.lastSync = data.lastSync || null;
            showToast('Using cached data');
        }
    }
    updateSyncStatus();
}

async function loadMeetingsData() {
    try {
        const response = await fetch(APP_CONFIG.meetingsDataUrl);
        if (response.ok) {
            const data = await response.json();
            APP_STATE.meetings = data.meetings || [];
            localStorage.setItem('meetingsData', JSON.stringify(data));
        }
    } catch (error) {
        console.error('Error loading meetings:', error);
        const cachedData = localStorage.getItem('meetingsData');
        if (cachedData) { APP_STATE.meetings = JSON.parse(cachedData).meetings || []; }
    }
}

function getMeetingsThisWeek() {
    const today = new Date(); today.setHours(0, 0, 0, 0);
    const weekEnd = new Date(today); weekEnd.setDate(weekEnd.getDate() + 7);
    return APP_STATE.meetings.filter(m => {
        if (!m.date || m.cancelled) return false;
        try {
            const meetingDate = new Date(m.date); meetingDate.setHours(0, 0, 0, 0);
            return meetingDate >= today && meetingDate <= weekEnd;
        } catch { return false; }
    });
}

function updateUI() {
    if (APP_STATE.currentView === 'main') { renderBills(); updateStats(); }
    updateUserPanel();
}

function renderBills() {
    const grid = document.getElementById('billsGrid');
    const filteredBills = filterBills();
    if (filteredBills.length === 0) {
        grid.innerHTML = '<div style="grid-column: 1/-1; text-align: center; padding: 3rem; color: var(--text-muted);"><h3>No bills found</h3><p>Try adjusting your filters</p></div>';
        return;
    }
    grid.innerHTML = filteredBills.map(bill => createBillCard(bill)).join('');
}

function createBillCard(bill) {
    const isTracked = APP_STATE.trackedBills.has(bill.id);
    const hasNotes = APP_STATE.userNotes[bill.id] && APP_STATE.userNotes[bill.id].length > 0;
    let latestNote = '';
    if (hasNotes) {
        const notes = APP_STATE.userNotes[bill.id];
        latestNote = notes[notes.length - 1].text;
        if (latestNote.length > 100) latestNote = latestNote.substring(0, 100) + '...';
    }
    return '<div class="bill-card ' + (isTracked ? 'tracked' : '') + '" data-bill-id="' + bill.id + '">' +
        '<div class="bill-header">' +
        '<a href="https://app.leg.wa.gov/billsummary?BillNumber=' + bill.number.split(' ')[1] + '&Year=2026" target="_blank" class="bill-number">' + bill.number + '</a>' +
        '<div class="bill-title">' + bill.title + '</div></div>' +
        '<div class="bill-body"><div class="bill-meta">' +
        '<span class="meta-item">Sponsor: ' + bill.sponsor + '</span>' +
        '<span class="meta-item">Committee: ' + bill.committee + '</span></div>' +
        '<div class="bill-description">' + (bill.description || '') + '</div>' +
        (hasNotes ? '<div class="bill-notes-preview">Note: "' + latestNote + '"</div>' : '') +
        '<div class="bill-tags">' +
        '<span class="tag status-' + bill.status + '">' + bill.status + '</span>' +
        '<span class="tag priority-' + bill.priority + '">' + bill.priority + ' priority</span>' +
        '<span class="tag">' + bill.topic + '</span></div></div>' +
        '<div class="bill-actions">' +
        '<button class="action-btn ' + (isTracked ? 'active' : '') + '" onclick="toggleTrack(\'' + bill.id + '\')">' + (isTracked ? 'Tracked' : 'Track') + '</button>' +
        '<button class="action-btn" onclick="openNoteModal(\'' + bill.id + '\')">' + (hasNotes ? 'Notes (' + APP_STATE.userNotes[bill.id].length + ')' : 'Add Note') + '</button>' +
        '<button class="action-btn" onclick="shareBill(\'' + bill.id + '\')">Share</button></div></div>';
}

function filterBills() {
    let filtered = [...APP_STATE.bills];
    if (APP_STATE.filters.search) {
        const search = APP_STATE.filters.search.toLowerCase();
        filtered = filtered.filter(bill => 
            bill.number.toLowerCase().includes(search) ||
            bill.title.toLowerCase().includes(search) ||
            (bill.description || '').toLowerCase().includes(search) ||
            bill.sponsor.toLowerCase().includes(search)
        );
    }
    if (APP_STATE.filters.status) filtered = filtered.filter(bill => bill.status === APP_STATE.filters.status);
    if (APP_STATE.filters.priority) filtered = filtered.filter(bill => bill.priority === APP_STATE.filters.priority);
    if (APP_STATE.filters.committee) filtered = filtered.filter(bill => bill.committee.toLowerCase().includes(APP_STATE.filters.committee));
    if (APP_STATE.filters.type) filtered = filtered.filter(bill => bill.number.split(' ')[0] === APP_STATE.filters.type);
    if (APP_STATE.filters.trackedOnly) filtered = filtered.filter(bill => APP_STATE.trackedBills.has(bill.id));
    return filtered;
}

function toggleTrack(billId) {
    if (APP_STATE.trackedBills.has(billId)) {
        APP_STATE.trackedBills.delete(billId);
        showToast('Bill removed from tracking');
    } else {
        APP_STATE.trackedBills.add(billId);
        showToast('Bill added to tracking');
    }
    StorageManager.save();
    updateUI();
}

function openNoteModal(billId) {
    APP_STATE.currentNoteBillId = billId;
    const bill = APP_STATE.bills.find(b => b.id === billId);
    document.getElementById('noteModalTitle').textContent = 'Notes for ' + bill.number;
    const existingNotes = APP_STATE.userNotes[billId] || [];
    let notesText = existingNotes.map(note => note.text).join('\n\n---\n\n');
    document.getElementById('noteTextarea').value = notesText;
    document.getElementById('noteModal').classList.add('active');
}

function closeNoteModal() {
    document.getElementById('noteModal').classList.remove('active');
    APP_STATE.currentNoteBillId = null;
}

function saveNote() {
    const billId = APP_STATE.currentNoteBillId;
    const noteText = document.getElementById('noteTextarea').value.trim();
    if (!noteText) { delete APP_STATE.userNotes[billId]; }
    else {
        APP_STATE.userNotes[billId] = [{ id: Date.now().toString(), text: noteText, date: new Date().toISOString(), user: APP_STATE.userData.name }];
    }
    StorageManager.save();
    closeNoteModal();
    showToast('Note saved');
    updateUI();
}

function shareBill(billId) {
    const bill = APP_STATE.bills.find(b => b.id === billId);
    const shareUrl = APP_CONFIG.siteUrl + '#bill-' + billId;
    if (navigator.share) {
        navigator.share({ title: bill.number + ' - WA Bill Tracker', text: 'Check out ' + bill.number + ': ' + bill.title, url: shareUrl }).catch(() => {
            navigator.clipboard.writeText(shareUrl);
            showToast('Link copied to clipboard');
        });
    } else {
        navigator.clipboard.writeText(shareUrl);
        showToast('Link copied to clipboard');
    }
}

function checkForSharedBill() {
    if (window.location.hash && window.location.hash.startsWith('#bill-')) {
        const billId = window.location.hash.replace('#bill-', '');
        setTimeout(() => highlightBill(billId), 1000);
    }
}

function highlightBill(billId) {
    APP_STATE.filters = { search: '', status: '', priority: '', committee: '', type: '', trackedOnly: false };
    showMainView();
    setTimeout(() => {
        const billCard = document.querySelector('[data-bill-id="' + billId + '"]');
        if (billCard) {
            billCard.scrollIntoView({ behavior: 'smooth', block: 'center' });
            billCard.style.animation = 'highlight 2s ease';
        }
    }, 100);
}

function showStatsDetail(type) {
    APP_STATE.currentView = 'stats';
    document.getElementById('mainView').classList.remove('active');
    document.getElementById('statsView').classList.add('active');
    const detailContainer = document.getElementById('statsDetail');
    let content = '';
    switch(type) {
        case 'total': content = renderTotalBillsStats(); break;
        case 'tracked': content = renderTrackedBillsStats(); break;
        case 'today': content = renderTodayStats(); break;
        case 'hearings': content = renderHearingsStats(); break;
        case 'remaining': content = renderSessionStats(); break;
    }
    detailContainer.innerHTML = content;
}

function renderTotalBillsStats() {
    const stats = calculateBillStats();
    let html = '<h2>Total Bills: ' + APP_STATE.bills.length + '</h2><div class="stats-list">';
    for (const [type, count] of Object.entries(stats.byType)) {
        html += '<div class="stats-item"><span class="stats-item-label">' + type + ' Bills</span><span class="stats-item-value">' + count + '</span></div>';
    }
    for (const [status, count] of Object.entries(stats.byStatus)) {
        html += '<div class="stats-item"><span class="stats-item-label">' + status + '</span><span class="stats-item-value">' + count + '</span></div>';
    }
    return html + '</div>';
}

function renderTrackedBillsStats() {
    const trackedBills = APP_STATE.bills.filter(bill => APP_STATE.trackedBills.has(bill.id));
    let html = '<h2>Your Tracked Bills: ' + trackedBills.length + '</h2><div class="stats-list">';
    for (const bill of trackedBills) {
        html += '<div class="stats-item" onclick="highlightBill(\'' + bill.id + '\')" style="cursor: pointer;"><span class="stats-item-label">' + bill.number + ': ' + bill.title + '</span><span class="stats-item-value">' + bill.status + '</span></div>';
    }
    if (trackedBills.length === 0) html += '<p style="text-align: center; color: var(--text-muted);">No bills tracked yet</p>';
    return html + '</div>';
}

function renderTodayStats() {
    const today = new Date().toDateString();
    const todayBills = APP_STATE.bills.filter(bill => new Date(bill.lastUpdated).toDateString() === today);
    let html = '<h2>Updated Today: ' + todayBills.length + '</h2><div class="stats-list">';
    for (const bill of todayBills) {
        html += '<div class="stats-item" onclick="highlightBill(\'' + bill.id + '\')" style="cursor: pointer;"><span class="stats-item-label">' + bill.number + ': ' + bill.title + '</span><span class="stats-item-value">' + formatTime(bill.lastUpdated) + '</span></div>';
    }
    if (todayBills.length === 0) html += '<p style="text-align: center; color: var(--text-muted);">No updates today</p>';
    return html + '</div>';
}

function renderHearingsStats() {
    const meetingsThisWeek = getMeetingsThisWeek();
    let html = '<h2>Committee Meetings This Week: ' + meetingsThisWeek.length + '</h2><div class="stats-list">';
    meetingsThisWeek.sort((a, b) => new Date(a.date) - new Date(b.date));
    for (const meeting of meetingsThisWeek) {
        html += '<div class="stats-item"><span class="stats-item-label">' + meeting.date + ' ' + (meeting.time || '') + '<br>' + meeting.committee + '</span><span class="stats-item-value">' + (meeting.location || 'TBD') + '</span></div>';
    }
    if (meetingsThisWeek.length === 0) html += '<p style="text-align: center; color: var(--text-muted);">No committee meetings scheduled this week</p>';
    return html + '</div>';
}

function renderSessionStats() {
    const daysLeft = Math.ceil((APP_CONFIG.sessionEnd - new Date()) / (1000 * 60 * 60 * 24));
    const sessionStart = new Date('2026-01-12');
    const totalDays = Math.ceil((APP_CONFIG.sessionEnd - sessionStart) / (1000 * 60 * 60 * 24));
    const daysPassed = totalDays - daysLeft;
    const percentComplete = Math.round((daysPassed / totalDays) * 100);
    return '<h2>Session Progress</h2><div class="stats-list">' +
        '<div class="stats-item"><span class="stats-item-label">Days Remaining</span><span class="stats-item-value">' + Math.max(0, daysLeft) + '</span></div>' +
        '<div class="stats-item"><span class="stats-item-label">Days Passed</span><span class="stats-item-value">' + daysPassed + '</span></div>' +
        '<div class="stats-item"><span class="stats-item-label">Session Progress</span><span class="stats-item-value">' + percentComplete + '%</span></div>' +
        '<div class="stats-item"><span class="stats-item-label">Session Ends</span><span class="stats-item-value">March 12, 2026</span></div></div>';
}

function calculateBillStats() {
    const stats = { byStatus: {}, byType: {}, byTopic: {}, byCommittee: {} };
    APP_STATE.bills.forEach(bill => {
        const status = bill.status || 'unknown';
        stats.byStatus[status] = (stats.byStatus[status] || 0) + 1;
        const type = bill.number.split(' ')[0];
        stats.byType[type] = (stats.byType[type] || 0) + 1;
        const topic = bill.topic || 'General';
        stats.byTopic[topic] = (stats.byTopic[topic] || 0) + 1;
        const committee = bill.committee || 'Unknown';
        stats.byCommittee[committee] = (stats.byCommittee[committee] || 0) + 1;
    });
    return stats;
}

function updateStats() {
    document.getElementById('totalBills').textContent = APP_STATE.bills.length;
    document.getElementById('trackedBills').textContent = APP_STATE.trackedBills.size;
    const today = new Date().toDateString();
    const newToday = APP_STATE.bills.filter(bill => new Date(bill.lastUpdated).toDateString() === today).length;
    document.getElementById('newToday').textContent = newToday;
    const meetingsThisWeek = getMeetingsThisWeek();
    document.getElementById('hearingsWeek').textContent = meetingsThisWeek.length;
    const daysLeft = Math.ceil((APP_CONFIG.sessionEnd - new Date()) / (1000 * 60 * 60 * 24));
    document.getElementById('daysLeft').textContent = Math.max(0, daysLeft);
}

function updateUserPanel() {
    document.getElementById('userName').textContent = APP_STATE.userData.name;
    document.getElementById('userAvatar').textContent = APP_STATE.userData.avatar;
    document.getElementById('userTrackedCount').textContent = APP_STATE.trackedBills.size;
    const totalNotes = Object.values(APP_STATE.userNotes).reduce((sum, notes) => sum + notes.length, 0);
    document.getElementById('userNotesCount').textContent = totalNotes;
    updateUserNotesList();
}

function updateUserNotesList() {
    const notesList = document.getElementById('userNotesList');
    const allNotes = [];
    Object.entries(APP_STATE.userNotes).forEach(([billId, notes]) => {
        const bill = APP_STATE.bills.find(b => b.id === billId);
        if (bill) {
            notes.forEach(note => allNotes.push({ billId, billNumber: bill.number, billTitle: bill.title, ...note }));
        }
    });
    allNotes.sort((a, b) => new Date(b.date) - new Date(a.date));
    const recentNotes = allNotes.slice(0, 5);
    if (recentNotes.length === 0) { notesList.innerHTML = '<p style="color: var(--text-muted); font-size: 0.875rem;">No notes yet</p>'; }
    else {
        notesList.innerHTML = recentNotes.map(note => '<div class="user-note-item"><div class="user-note-bill" onclick="highlightBill(\'' + note.billId + '\')" style="cursor: pointer;">' + note.billNumber + ': ' + note.billTitle + '</div><div class="user-note-text">' + note.text.substring(0, 100) + (note.text.length > 100 ? '...' : '') + '</div><div class="user-note-date">' + formatDate(note.date) + '</div></div>').join('');
    }
}

function updateSyncStatus() {
    const syncText = document.getElementById('syncText');
    if (APP_STATE.lastSync) {
        const syncDate = new Date(APP_STATE.lastSync);
        const hours = Math.floor((Date.now() - syncDate) / (1000 * 60 * 60));
        if (hours < 1) syncText.textContent = 'Last sync: Just now';
        else if (hours < 24) syncText.textContent = 'Last sync: ' + hours + ' hour' + (hours > 1 ? 's' : '') + ' ago';
        else { const days = Math.floor(hours / 24); syncText.textContent = 'Last sync: ' + days + ' day' + (days > 1 ? 's' : '') + ' ago'; }
    } else { syncText.textContent = 'Last sync: Never'; }
}

function setupEventListeners() {
    document.getElementById('searchInput').addEventListener('input', (e) => {
        APP_STATE.filters.search = e.target.value;
        renderBills();
    });
    document.querySelectorAll('.filter-tag').forEach(tag => {
        tag.addEventListener('click', () => {
            const filter = tag.dataset.filter;
            const value = tag.dataset.value;
            if (tag.classList.contains('active')) {
                tag.classList.remove('active');
                APP_STATE.filters[filter] = '';
            } else {
                tag.parentElement.querySelectorAll('.filter-tag').forEach(t => t.classList.remove('active'));
                tag.classList.add('active');
                APP_STATE.filters[filter] = value;
            }
            renderBills();
            StorageManager.save();
        });
    });
}

function setupAutoSave() { setInterval(() => StorageManager.save(), APP_CONFIG.autoSaveInterval); }

function toggleFilters() {
    const panel = document.getElementById('filtersPanel');
    const btn = document.getElementById('filterToggle');
    panel.classList.toggle('active');
    btn.classList.toggle('active');
}

function toggleTrackedOnly() {
    const btn = document.getElementById('trackedToggle');
    APP_STATE.filters.trackedOnly = !APP_STATE.filters.trackedOnly;
    btn.classList.toggle('active');
    renderBills();
    StorageManager.save();
}

function toggleUserPanel() {
    const panel = document.getElementById('userPanel');
    const notesSection = document.getElementById('userNotesSection');
    const expandBtn = document.getElementById('expandBtn');
    panel.classList.toggle('expanded');
    notesSection.classList.toggle('active');
    expandBtn.classList.toggle('expanded');
}

async function refreshData() {
    const syncStatus = document.getElementById('syncStatus');
    syncStatus.classList.add('syncing');
    await loadAllData();
    updateUI();
    setTimeout(() => syncStatus.classList.remove('syncing'), 1000);
}

function showMainView() {
    APP_STATE.currentView = 'main';
    document.getElementById('statsView').classList.remove('active');
    document.getElementById('mainView').classList.add('active');
    updateUI();
}

function formatDate(dateString) {
    const date = new Date(dateString);
    const now = new Date();
    const diff = now - date;
    const days = Math.floor(diff / (1000 * 60 * 60 * 24));
    if (days === 0) {
        const hours = Math.floor(diff / (1000 * 60 * 60));
        if (hours === 0) return 'Just now';
        return hours + ' hour' + (hours > 1 ? 's' : '') + ' ago';
    } else if (days === 1) { return 'Yesterday'; }
    else if (days < 7) { return days + ' days ago'; }
    else { return date.toLocaleDateString(); }
}

function formatTime(dateString) {
    const date = new Date(dateString);
    return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
}

function showToast(message) {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.classList.add('show');
    setTimeout(() => toast.classList.remove('show'), 3000);
}

// Add highlight animation CSS
const style = document.createElement('style');
style.textContent = '@keyframes highlight { 0% { box-shadow: 0 0 0 0 var(--accent); } 50% { box-shadow: 0 0 20px 10px var(--accent); } 100% { box-shadow: 0 0 0 0 var(--accent); } }';
document.head.appendChild(style);
