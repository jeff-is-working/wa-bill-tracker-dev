// WA Legislative Tracker 2026 - Schema-Compliant Enhanced JavaScript Application
// Fully compliant with WA Legislature API schema
// With persistent cookies, note management, stats views, and proper sharing

// Application Configuration
const APP_CONFIG = {
    siteName: 'WA Bill Tracker',
    siteUrl: 'https://jeff-is-working.github.io/wa-bill-tracker',
    cookieDuration: 90, // days
    autoSaveInterval: 30000, // 30 seconds
    dataRefreshInterval: 3600000, // 1 hour
    githubDataUrl: 'https://raw.githubusercontent.com/jeff-is-working/wa-bill-tracker/main/data/bills.json',
    sessionEnd: new Date('2026-03-12'),
    sessionStart: new Date('2026-01-12'),
    biennium: '2025-26'
};

// Application State - Schema Compliant
const APP_STATE = {
    bills: [],                    // Array of AppBill objects (transformed from WA Legislature schema)
    trackedBills: new Set(),      // Set of bill IDs
    userNotes: {},                // { billId: [UserNote] }
    filters: {
        search: '',
        status: '',               // AppBillStatus enum
        priority: '',             // BillPriority enum
        committee: '',
        type: '',                 // BillType enum
        trackedOnly: false
    },
    lastSync: null,               // ISO 8601 datetime
    userData: {
        name: 'Guest User',
        avatar: '?',
        id: null
    },
    currentView: 'main',          // 'main' | 'stats'
    currentNoteBillId: null,
    schemaVersion: '2.0.0'        // Track data schema version
};

// Valid enums from schema
const VALID_STATUSES = ['prefiled', 'introduced', 'committee', 'passed', 'failed'];
const VALID_PRIORITIES = ['high', 'medium', 'low'];
const VALID_BILL_TYPES = ['HB', 'SB', 'HJR', 'SJR', 'HJM', 'SJM', 'HCR', 'SCR', 'I', 'R'];

// Cookie Management with Long-term Persistence
const CookieManager = {
    // Set a cookie with proper SameSite and long expiration
    set(name, value, days = APP_CONFIG.cookieDuration) {
        const expires = new Date();
        expires.setTime(expires.getTime() + (days * 24 * 60 * 60 * 1000));
        const cookieValue = typeof value === 'object' ? JSON.stringify(value) : value;
        document.cookie = `${name}=${encodeURIComponent(cookieValue)};expires=${expires.toUTCString()};path=/;SameSite=Lax`;
    },

    // Get a cookie value
    get(name) {
        const nameEQ = name + "=";
        const cookies = document.cookie.split(';');
        for (let cookie of cookies) {
            cookie = cookie.trim();
            if (cookie.indexOf(nameEQ) === 0) {
                const value = decodeURIComponent(cookie.substring(nameEQ.length));
                try {
                    return JSON.parse(value);
                } catch {
                    return value;
                }
            }
        }
        return null;
    },

    // Delete a cookie
    delete(name) {
        document.cookie = `${name}=;expires=Thu, 01 Jan 1970 00:00:01 GMT;path=/;`;
    }
};

// LocalStorage Backup for Additional Persistence
const StorageManager = {
    save() {
        try {
            // Save to cookies (primary)
            CookieManager.set('wa_tracker_tracked', Array.from(APP_STATE.trackedBills));
            CookieManager.set('wa_tracker_notes', APP_STATE.userNotes);
            CookieManager.set('wa_tracker_user', APP_STATE.userData);
            CookieManager.set('wa_tracker_filters', APP_STATE.filters);
            
            // Save to localStorage (backup)
            localStorage.setItem('wa_tracker_state', JSON.stringify({
                trackedBills: Array.from(APP_STATE.trackedBills),
                userNotes: APP_STATE.userNotes,
                userData: APP_STATE.userData,
                filters: APP_STATE.filters,
                lastSaved: new Date().toISOString(),
                schemaVersion: APP_STATE.schemaVersion
            }));
            
            return true;
        } catch (error) {
            console.error('Error saving state:', error);
            return false;
        }
    },

    load() {
        try {
            // Try cookies first (primary)
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
            
            // Fallback to localStorage
            const saved = localStorage.getItem('wa_tracker_state');
            if (saved) {
                const data = JSON.parse(saved);
                APP_STATE.trackedBills = new Set(data.trackedBills || []);
                APP_STATE.userNotes = data.userNotes || {};
                APP_STATE.userData = data.userData || APP_STATE.userData;
                APP_STATE.filters = data.filters || APP_STATE.filters;
                
                // Migrate to cookies
                StorageManager.save();
                return true;
            }
            
            return false;
        } catch (error) {
            console.error('Error loading state:', error);
            return false;
        }
    }
};

// Schema Validation Functions
const SchemaValidator = {
    // Validate a bill object against schema requirements
    validateBill(bill) {
        const errors = [];
        
        // Required fields
        if (!bill.id) errors.push('Missing required field: id');
        if (!bill.number) errors.push('Missing required field: number');
        if (!bill.title) errors.push('Missing required field: title');
        if (!bill.status) errors.push('Missing required field: status');
        if (!bill.introducedDate) errors.push('Missing required field: introducedDate');
        
        // Validate status enum
        if (bill.status && !VALID_STATUSES.includes(bill.status)) {
            errors.push(`Invalid status: ${bill.status}. Must be one of: ${VALID_STATUSES.join(', ')}`);
        }
        
        // Validate priority enum
        if (bill.priority && !VALID_PRIORITIES.includes(bill.priority)) {
            errors.push(`Invalid priority: ${bill.priority}. Must be one of: ${VALID_PRIORITIES.join(', ')}`);
        }
        
        // Validate bill type
        const billType = bill.number ? bill.number.split(' ')[0] : '';
        if (billType && !VALID_BILL_TYPES.includes(billType)) {
            console.warn(`Unusual bill type: ${billType}`);
        }
        
        // Validate hearings array
        if (bill.hearings && !Array.isArray(bill.hearings)) {
            errors.push('hearings must be an array');
        }
        
        // Validate companions array
        if (bill.companions && !Array.isArray(bill.companions)) {
            errors.push('companions must be an array');
        }
        
        // Validate biennium format (YYYY-YY)
        if (bill.biennium && !/^\d{4}-\d{2}$/.test(bill.biennium)) {
            errors.push(`Invalid biennium format: ${bill.biennium}. Must be YYYY-YY`);
        }
        
        return {
            valid: errors.length === 0,
            errors: errors
        };
    },
    
    // Validate entire bills array
    validateBillsData(data) {
        if (!data.bills || !Array.isArray(data.bills)) {
            console.error('Invalid data structure: bills must be an array');
            return false;
        }
        
        let validCount = 0;
        let errorCount = 0;
        
        data.bills.forEach((bill, index) => {
            const validation = this.validateBill(bill);
            if (validation.valid) {
                validCount++;
            } else {
                errorCount++;
                if (errorCount <= 5) { // Only log first 5 errors
                    console.error(`Bill ${index} (${bill.id || 'unknown'}) validation errors:`, validation.errors);
                }
            }
        });
        
        console.log(`Schema validation: ${validCount} valid bills, ${errorCount} errors`);
        return errorCount === 0;
    }
};

// Initialize Application
document.addEventListener('DOMContentLoaded', async () => {
    console.log('Initializing WA Bill Tracker (Schema v' + APP_STATE.schemaVersion + ')');
    initializeUser();
    StorageManager.load();
    await loadBillsData();
    setupEventListeners();
    setupAutoSave();
    updateUI();
    checkForSharedBill();
});

// User Initialization
function initializeUser() {
    // Check for existing user ID
    let userId = CookieManager.get('wa_tracker_user_id');
    
    if (!userId) {
        // Generate unique user ID
        userId = 'user_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
        CookieManager.set('wa_tracker_user_id', userId, 365); // 1 year
    }
    
    APP_STATE.userData.id = userId;
    
    // Check for saved user data
    if (!APP_STATE.userData.name || APP_STATE.userData.name === 'Guest User') {
        const savedName = CookieManager.get('wa_tracker_user_name');
        if (savedName) {
            APP_STATE.userData.name = savedName;
            APP_STATE.userData.avatar = savedName.charAt(0).toUpperCase();
        }
    }
}

// Load Bills Data with Schema Validation
async function loadBillsData() {
    try {
        const response = await fetch(APP_CONFIG.githubDataUrl);
        
        if (response.ok) {
            const data = await response.json();
            
            // Validate schema compliance
            const isValid = SchemaValidator.validateBillsData(data);
            if (!isValid) {
                console.warn('Data has schema validation errors, but continuing...');
            }
            
            APP_STATE.bills = data.bills || [];
            APP_STATE.lastSync = data.lastSync || new Date().toISOString();
            
            // Cache in localStorage
            localStorage.setItem('billsData', JSON.stringify(data));
            localStorage.setItem('lastDataFetch', new Date().toISOString());
            
            showToast(`✅ Loaded ${APP_STATE.bills.length} bills`);
        } else {
            throw new Error('Failed to fetch from GitHub');
        }
    } catch (error) {
        console.error('Error loading from GitHub:', error);
        
        // Fall back to cached data
        const cachedData = localStorage.getItem('billsData');
        if (cachedData) {
            const data = JSON.parse(cachedData);
            APP_STATE.bills = data.bills || [];
            APP_STATE.lastSync = data.lastSync || null;
            showToast('📦 Using cached data');
        } else {
            // Load sample data (schema compliant)
            loadSampleData();
            showToast('📝 Loading sample data');
        }
    }
    
    updateSyncStatus();
}

// Load Sample Data - Schema Compliant
function loadSampleData() {
    APP_STATE.bills = [
        {
            // Core identification (from Legislation.BillId, BillNumber)
            id: 'SB5872',
            number: 'SB 5872',
            
            // Basic information (from Legislation)
            title: 'Early Childhood Education and Assistance Program Account',
            description: 'An Act Relating to creating the early learning facilities revolving account; amending RCW 43.31.569 and 43.31.577',
            sponsor: 'Sen. Claire Wilson',
            
            // Status and tracking (from CurrentStatus)
            status: 'prefiled',
            committee: 'Early Learning & K-12 Education',
            priority: 'high',
            topic: 'Education',
            
            // Dates (from Legislation, CurrentStatus)
            introducedDate: '2026-01-08',
            lastUpdated: new Date().toISOString(),
            
            // References
            legUrl: 'https://app.leg.wa.gov/billsummary?BillNumber=5872&Year=2026',
            companions: ['HB2159'],
            
            // Hearings (from Hearings array)
            hearings: [{
                date: '2026-01-15',
                time: '10:00 AM',
                committee: 'Early Learning & K-12 Education',
                location: 'Senate Hearing Room 4'
            }],
            
            // Metadata (from Legislation, CurrentStatus)
            biennium: '2025-26',
            historyLine: 'Prefiled for introduction.',
            amended: false,
            vetoed: false
        },
        {
            id: 'HB2225',
            number: 'HB 2225',
            title: 'Regulating Artificial Intelligence Companion Chatbots',
            description: 'An Act Relating to requiring artificial intelligence chatbot developers to implement certain protocols to protect minors',
            sponsor: 'Rep. Lisa Callan',
            status: 'prefiled',
            committee: 'Consumer Protection & Business',
            priority: 'high',
            topic: 'Technology',
            introducedDate: '2026-01-09',
            lastUpdated: new Date().toISOString(),
            legUrl: 'https://app.leg.wa.gov/billsummary?BillNumber=2225&Year=2026',
            companions: ['SB5984'],
            hearings: [],
            biennium: '2025-26',
            historyLine: 'Prefiled for introduction.',
            amended: false,
            vetoed: false
        },
        {
            id: 'SB6026',
            number: 'SB 6026',
            title: 'Changing Commercial Zoning to Support Housing',
            description: 'An Act Relating to modifying commercial zoning regulations to facilitate housing development',
            sponsor: 'Sen. Emily Alvarado',
            status: 'prefiled',
            committee: 'Housing',
            priority: 'high',
            topic: 'Housing',
            introducedDate: '2026-01-10',
            lastUpdated: new Date().toISOString(),
            legUrl: 'https://app.leg.wa.gov/billsummary?BillNumber=6026&Year=2026',
            companions: [],
            hearings: [],
            biennium: '2025-26',
            historyLine: 'Prefiled for introduction.',
            amended: false,
            vetoed: false
        }
    ];
}

// Render Functions
function updateUI() {
    if (APP_STATE.currentView === 'main') {
        renderBills();
        updateStats();
    }
    updateUserPanel();
}

function renderBills() {
    const grid = document.getElementById('billsGrid');
    const filteredBills = filterBills();
    
    if (filteredBills.length === 0) {
        grid.innerHTML = `
            <div style="grid-column: 1/-1; text-align: center; padding: 3rem; color: var(--text-muted);">
                <h3 style="font-size: 1.5rem; margin-bottom: 1rem;">No bills found</h3>
                <p>Try adjusting your filters or search terms</p>
            </div>
        `;
        return;
    }
    
    grid.innerHTML = filteredBills.map(bill => createBillCard(bill)).join('');
}

function createBillCard(bill) {
    const isTracked = APP_STATE.trackedBills.has(bill.id);
    const hasNotes = APP_STATE.userNotes[bill.id] && APP_STATE.userNotes[bill.id].length > 0;
    const hasHearings = bill.hearings && bill.hearings.length > 0;
    const hasCompanions = bill.companions && bill.companions.length > 0;
    
    let latestNote = '';
    if (hasNotes) {
        const notes = APP_STATE.userNotes[bill.id];
        latestNote = notes[notes.length - 1].text;
        if (latestNote.length > 100) {
            latestNote = latestNote.substring(0, 100) + '...';
        }
    }
    
    // Extract bill number for URL (handles both "HB 1234" and "HB1234" formats)
    const billNumMatch = bill.number.match(/\d+/);
    const billNum = billNumMatch ? billNumMatch[0] : '';
    
    return `
        <div class="bill-card ${isTracked ? 'tracked' : ''}" data-bill-id="${bill.id}">
            <div class="bill-header">
                <a href="${bill.legUrl || `https://app.leg.wa.gov/billsummary?BillNumber=${billNum}&Year=2026`}" 
                   target="_blank" class="bill-number">${bill.number}</a>
                <div class="bill-title">${escapeHtml(bill.title)}</div>
            </div>
            
            <div class="bill-body">
                <div class="bill-meta">
                    <span class="meta-item">👤 ${escapeHtml(bill.sponsor)}</span>
                    <span class="meta-item">🏛️ ${escapeHtml(bill.committee)}</span>
                    ${hasHearings ? `<span class="meta-item" style="color: var(--warning);">📅 ${bill.hearings[0].date}${bill.hearings[0].time ? ' ' + bill.hearings[0].time : ''}</span>` : ''}
                    ${bill.biennium ? `<span class="meta-item">📋 ${bill.biennium}</span>` : ''}
                </div>
                
                <div class="bill-description">${escapeHtml(bill.description)}</div>
                
                ${hasCompanions ? `<div class="bill-companions">🔗 Companions: ${bill.companions.join(', ')}</div>` : ''}
                
                ${hasNotes ? `<div class="bill-notes-preview">📝 "${escapeHtml(latestNote)}"</div>` : ''}
                
                <div class="bill-tags">
                    <span class="tag status-${bill.status}">${bill.status}</span>
                    <span class="tag priority-${bill.priority}">${bill.priority} priority</span>
                    <span class="tag">${bill.topic}</span>
                    ${bill.amended ? '<span class="tag">Amended</span>' : ''}
                    ${bill.vetoed ? '<span class="tag" style="background: rgba(239, 68, 68, 0.1); color: var(--danger);">Vetoed</span>' : ''}
                </div>
            </div>
            
            <div class="bill-actions">
                <button class="action-btn ${isTracked ? 'active' : ''}" onclick="toggleTrack('${bill.id}')">
                    ${isTracked ? '⭐ Tracked' : '☆ Track'}
                </button>
                <button class="action-btn" onclick="openNoteModal('${bill.id}')">
                    📝 ${hasNotes ? 'Notes (' + APP_STATE.userNotes[bill.id].length + ')' : 'Add Note'}
                </button>
                <button class="action-btn" onclick="shareBill('${bill.id}')">
                    🔗 Share
                </button>
            </div>
        </div>
    `;
}

// HTML escape function for security
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Filter Bills with Schema-Aware Filtering
function filterBills() {
    let filtered = [...APP_STATE.bills];
    
    // Search filter - searches across multiple fields
    if (APP_STATE.filters.search) {
        const search = APP_STATE.filters.search.toLowerCase();
        filtered = filtered.filter(bill => 
            bill.number.toLowerCase().includes(search) ||
            bill.title.toLowerCase().includes(search) ||
            bill.description.toLowerCase().includes(search) ||
            bill.sponsor.toLowerCase().includes(search) ||
            (bill.historyLine && bill.historyLine.toLowerCase().includes(search)) ||
            (bill.companions && bill.companions.some(c => c.toLowerCase().includes(search)))
        );
    }
    
    // Status filter (enum validation)
    if (APP_STATE.filters.status && VALID_STATUSES.includes(APP_STATE.filters.status)) {
        filtered = filtered.filter(bill => bill.status === APP_STATE.filters.status);
    }
    
    // Priority filter (enum validation)
    if (APP_STATE.filters.priority && VALID_PRIORITIES.includes(APP_STATE.filters.priority)) {
        filtered = filtered.filter(bill => bill.priority === APP_STATE.filters.priority);
    }
    
    // Committee filter
    if (APP_STATE.filters.committee) {
        filtered = filtered.filter(bill => 
            bill.committee && bill.committee.toLowerCase().includes(APP_STATE.filters.committee.toLowerCase())
        );
    }
    
    // Type filter (bill type prefix)
    if (APP_STATE.filters.type && VALID_BILL_TYPES.includes(APP_STATE.filters.type)) {
        filtered = filtered.filter(bill => {
            const billType = bill.number.split(' ')[0];
            return billType === APP_STATE.filters.type;
        });
    }
    
    // Tracked only filter
    if (APP_STATE.filters.trackedOnly) {
        filtered = filtered.filter(bill => APP_STATE.trackedBills.has(bill.id));
    }
    
    return filtered;
}

// Bill Actions
function toggleTrack(billId) {
    if (APP_STATE.trackedBills.has(billId)) {
        APP_STATE.trackedBills.delete(billId);
        showToast('✖️ Bill removed from tracking');
    } else {
        APP_STATE.trackedBills.add(billId);
        showToast('⭐ Bill added to tracking');
    }
    
    StorageManager.save();
    updateUI();
}

// Note Management
function openNoteModal(billId) {
    APP_STATE.currentNoteBillId = billId;
    const bill = APP_STATE.bills.find(b => b.id === billId);
    
    if (!bill) {
        console.error('Bill not found:', billId);
        return;
    }
    
    document.getElementById('noteModalTitle').textContent = `Notes for ${bill.number}`;
    
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
    
    if (!noteText) {
        delete APP_STATE.userNotes[billId];
    } else {
        if (!APP_STATE.userNotes[billId]) {
            APP_STATE.userNotes[billId] = [];
        }
        
        APP_STATE.userNotes[billId] = [{
            id: Date.now().toString(),
            text: noteText,
            date: new Date().toISOString(),
            user: APP_STATE.userData.name
        }];
    }
    
    StorageManager.save();
    closeNoteModal();
    showToast('📝 Note saved');
    updateUI();
}

// Share Bill - Uses wa-bill-tracker URL
function shareBill(billId) {
    const bill = APP_STATE.bills.find(b => b.id === billId);
    if (!bill) {
        console.error('Bill not found for sharing:', billId);
        return;
    }
    
    const shareUrl = `${APP_CONFIG.siteUrl}#bill-${billId}`;
    const shareText = `Check out ${bill.number}: ${bill.title}`;
    
    if (navigator.share) {
        navigator.share({
            title: `${bill.number} - WA Bill Tracker`,
            text: shareText,
            url: shareUrl
        }).catch(err => {
            if (err.name !== 'AbortError') {
                navigator.clipboard.writeText(shareUrl);
                showToast('🔗 Link copied to clipboard');
            }
        });
    } else {
        navigator.clipboard.writeText(shareUrl);
        showToast('🔗 Link copied to clipboard');
    }
}

// Check for shared bill in URL
function checkForSharedBill() {
    if (window.location.hash && window.location.hash.startsWith('#bill-')) {
        const billId = window.location.hash.replace('#bill-', '');
        setTimeout(() => {
            highlightBill(billId);
        }, 1000);
    }
}

// Highlight a specific bill
function highlightBill(billId) {
    // Reset filters to show the bill
    APP_STATE.filters = {
        search: '',
        status: '',
        priority: '',
        committee: '',
        type: '',
        trackedOnly: false
    };
    
    showMainView();
    
    setTimeout(() => {
        const billCard = document.querySelector(`[data-bill-id="${billId}"]`);
        if (billCard) {
            billCard.scrollIntoView({ behavior: 'smooth', block: 'center' });
            billCard.style.animation = 'highlight 2s ease';
        } else {
            showToast('⚠️ Bill not found');
        }
    }, 100);
}

// Stats Detail Views
function showStatsDetail(type) {
    APP_STATE.currentView = 'stats';
    document.getElementById('mainView').classList.remove('active');
    document.getElementById('statsView').classList.add('active');
    
    const detailContainer = document.getElementById('statsDetail');
    let content = '';
    
    switch(type) {
        case 'total':
            content = renderTotalBillsStats();
            break;
        case 'tracked':
            content = renderTrackedBillsStats();
            break;
        case 'today':
            content = renderTodayStats();
            break;
        case 'hearings':
            content = renderHearingsStats();
            break;
        case 'remaining':
            content = renderSessionStats();
            break;
        default:
            content = '<p>Invalid stats type</p>';
    }
    
    detailContainer.innerHTML = content;
}

function renderTotalBillsStats() {
    const stats = calculateBillStats();
    return `
        <h2>Total Bills: ${APP_STATE.bills.length}</h2>
        <div class="stats-list">
            ${Object.entries(stats.byType).map(([type, count]) => `
                <div class="stats-item">
                    <span class="stats-item-label">${escapeHtml(type)} Bills</span>
                    <span class="stats-item-value">${count}</span>
                </div>
            `).join('')}
            ${Object.entries(stats.byStatus).map(([status, count]) => `
                <div class="stats-item">
                    <span class="stats-item-label">${escapeHtml(status)}</span>
                    <span class="stats-item-value">${count}</span>
                </div>
            `).join('')}
        </div>
    `;
}

function renderTrackedBillsStats() {
    const trackedBills = APP_STATE.bills.filter(bill => 
        APP_STATE.trackedBills.has(bill.id)
    );
    
    return `
        <h2>Your Tracked Bills: ${trackedBills.length}</h2>
        <div class="stats-list">
            ${trackedBills.map(bill => `
                <div class="stats-item" onclick="highlightBill('${bill.id}')" style="cursor: pointer;">
                    <span class="stats-item-label">${escapeHtml(bill.number)}: ${escapeHtml(bill.title)}</span>
                    <span class="stats-item-value">${escapeHtml(bill.status)}</span>
                </div>
            `).join('')}
            ${trackedBills.length === 0 ? '<p style="text-align: center; color: var(--text-muted);">No bills tracked yet</p>' : ''}
        </div>
    `;
}

function renderTodayStats() {
    const today = new Date().toDateString();
    const todayBills = APP_STATE.bills.filter(bill => {
        if (!bill.lastUpdated) return false;
        const updateDate = new Date(bill.lastUpdated);
        return updateDate.toDateString() === today;
    });
    
    return `
        <h2>Updated Today: ${todayBills.length}</h2>
        <div class="stats-list">
            ${todayBills.map(bill => `
                <div class="stats-item" onclick="highlightBill('${bill.id}')" style="cursor: pointer;">
                    <span class="stats-item-label">${escapeHtml(bill.number)}: ${escapeHtml(bill.title)}</span>
                    <span class="stats-item-value">${formatTime(bill.lastUpdated)}</span>
                </div>
            `).join('')}
            ${todayBills.length === 0 ? '<p style="text-align: center; color: var(--text-muted);">No updates today</p>' : ''}
        </div>
    `;
}

function renderHearingsStats() {
    const weekFromNow = new Date();
    weekFromNow.setDate(weekFromNow.getDate() + 7);
    
    const hearingBills = [];
    APP_STATE.bills.forEach(bill => {
        if (bill.hearings && Array.isArray(bill.hearings)) {
            bill.hearings.forEach(hearing => {
                const hearingDate = new Date(hearing.date);
                if (hearingDate >= new Date() && hearingDate <= weekFromNow) {
                    hearingBills.push({
                        bill,
                        hearing,
                        date: hearingDate
                    });
                }
            });
        }
    });
    
    hearingBills.sort((a, b) => a.date - b.date);
    
    return `
        <h2>Hearings This Week: ${hearingBills.length}</h2>
        <div class="stats-list">
            ${hearingBills.map(item => `
                <div class="stats-item" onclick="highlightBill('${item.bill.id}')" style="cursor: pointer;">
                    <span class="stats-item-label">
                        ${item.hearing.date} ${item.hearing.time || ''}<br>
                        ${escapeHtml(item.bill.number)}: ${escapeHtml(item.bill.title)}
                    </span>
                    <span class="stats-item-value">${escapeHtml(item.hearing.committee)}</span>
                </div>
            `).join('')}
            ${hearingBills.length === 0 ? '<p style="text-align: center; color: var(--text-muted);">No hearings scheduled this week</p>' : ''}
        </div>
    `;
}

function renderSessionStats() {
    const sessionEnd = new Date(APP_CONFIG.sessionEnd);
    const sessionStart = new Date(APP_CONFIG.sessionStart);
    const today = new Date();
    
    // Set to midnight for accurate day counting
    sessionEnd.setHours(0, 0, 0, 0);
    sessionStart.setHours(0, 0, 0, 0);
    today.setHours(0, 0, 0, 0);
    
    const totalDays = Math.ceil((sessionEnd - sessionStart) / (1000 * 60 * 60 * 24)) + 1;
    const daysLeft = Math.ceil((sessionEnd - today) / (1000 * 60 * 60 * 24)) + 1;
    const daysPassed = totalDays - daysLeft;
    const percentComplete = Math.round((daysPassed / totalDays) * 100);
    
    return `
        <h2>Session Progress</h2>
        <div class="stats-list">
            <div class="stats-item">
                <span class="stats-item-label">Days Remaining</span>
                <span class="stats-item-value">${Math.max(0, daysLeft)}</span>
            </div>
            <div class="stats-item">
                <span class="stats-item-label">Days Passed</span>
                <span class="stats-item-value">${Math.max(0, daysPassed)}</span>
            </div>
            <div class="stats-item">
                <span class="stats-item-label">Session Progress</span>
                <span class="stats-item-value">${Math.max(0, Math.min(100, percentComplete))}%</span>
            </div>
            <div class="stats-item">
                <span class="stats-item-label">Session Ends</span>
                <span class="stats-item-value">March 12, 2026</span>
            </div>
        </div>
    `;
}

// Calculate Bill Statistics - Schema Aware
function calculateBillStats() {
    const stats = {
        byStatus: {},
        byType: {},
        byTopic: {},
        byCommittee: {},
        bySponsor: {}
    };
    
    APP_STATE.bills.forEach(bill => {
        // By status
        const status = bill.status || 'unknown';
        stats.byStatus[status] = (stats.byStatus[status] || 0) + 1;
        
        // By type
        const type = bill.number ? bill.number.split(' ')[0] : 'unknown';
        stats.byType[type] = (stats.byType[type] || 0) + 1;
        
        // By topic
        const topic = bill.topic || 'General';
        stats.byTopic[topic] = (stats.byTopic[topic] || 0) + 1;
        
        // By committee
        const committee = bill.committee || 'Unknown';
        stats.byCommittee[committee] = (stats.byCommittee[committee] || 0) + 1;
        
        // By sponsor
        const sponsor = bill.sponsor || 'Unknown';
        stats.bySponsor[sponsor] = (stats.bySponsor[sponsor] || 0) + 1;
    });
    
    return stats;
}

// UI Updates
function updateStats() {
    document.getElementById('totalBills').textContent = APP_STATE.bills.length;
    document.getElementById('trackedBills').textContent = APP_STATE.trackedBills.size;
    
    const today = new Date().toDateString();
    const newToday = APP_STATE.bills.filter(bill => {
        if (!bill.lastUpdated) return false;
        return new Date(bill.lastUpdated).toDateString() === today;
    }).length;
    document.getElementById('newToday').textContent = newToday;
    
    const weekFromNow = new Date();
    weekFromNow.setDate(weekFromNow.getDate() + 7);
    const hearingsThisWeek = APP_STATE.bills.reduce((count, bill) => {
        if (!bill.hearings || !Array.isArray(bill.hearings)) return count;
        return count + bill.hearings.filter(h => {
            const hearingDate = new Date(h.date);
            return hearingDate >= new Date() && hearingDate <= weekFromNow;
        }).length;
    }, 0);
    document.getElementById('hearingsWeek').textContent = hearingsThisWeek;
    
    // Calculate remaining session days
    const sessionEnd = new Date(APP_CONFIG.sessionEnd);
    const today_date = new Date();
    
    // Set to midnight for accurate day counting
    sessionEnd.setHours(0, 0, 0, 0);
    today_date.setHours(0, 0, 0, 0);
    
    // Days from today through end of session (inclusive)
    const daysLeft = Math.ceil((sessionEnd - today_date) / (1000 * 60 * 60 * 24)) + 1;
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
            notes.forEach(note => {
                allNotes.push({
                    billId,
                    billNumber: bill.number,
                    billTitle: bill.title,
                    ...note
                });
            });
        }
    });
    
    allNotes.sort((a, b) => new Date(b.date) - new Date(a.date));
    const recentNotes = allNotes.slice(0, 5);
    
    if (recentNotes.length === 0) {
        notesList.innerHTML = '<p style="color: var(--text-muted); font-size: 0.875rem;">No notes yet</p>';
    } else {
        notesList.innerHTML = recentNotes.map(note => `
            <div class="user-note-item">
                <div class="user-note-bill" onclick="highlightBill('${note.billId}')" style="cursor: pointer;">
                    ${escapeHtml(note.billNumber)}: ${escapeHtml(note.billTitle)}
                </div>
                <div class="user-note-text">${escapeHtml(note.text.substring(0, 100))}${note.text.length > 100 ? '...' : ''}</div>
                <div class="user-note-date">${formatDate(note.date)}</div>
            </div>
        `).join('');
    }
}

function updateSyncStatus() {
    const syncText = document.getElementById('syncText');
    if (APP_STATE.lastSync) {
        const syncDate = new Date(APP_STATE.lastSync);
        const hours = Math.floor((Date.now() - syncDate) / (1000 * 60 * 60));
        
        if (hours < 1) {
            syncText.textContent = 'Last sync: Just now';
        } else if (hours < 24) {
            syncText.textContent = `Last sync: ${hours} hour${hours > 1 ? 's' : ''} ago`;
        } else {
            const days = Math.floor(hours / 24);
            syncText.textContent = `Last sync: ${days} day${days > 1 ? 's' : ''} ago`;
        }
    } else {
        syncText.textContent = 'Last sync: Never';
    }
}

// Event Listeners
function setupEventListeners() {
    const searchInput = document.getElementById('searchInput');
    if (searchInput) {
        searchInput.addEventListener('input', (e) => {
            APP_STATE.filters.search = e.target.value;
            renderBills();
        });
    }
    
    document.querySelectorAll('.filter-tag').forEach(tag => {
        tag.addEventListener('click', () => {
            const filter = tag.dataset.filter;
            const value = tag.dataset.value;
            
            if (tag.classList.contains('active')) {
                tag.classList.remove('active');
                APP_STATE.filters[filter] = '';
            } else {
                // Remove active from siblings
                tag.parentElement.querySelectorAll('.filter-tag').forEach(t => 
                    t.classList.remove('active')
                );
                tag.classList.add('active');
                APP_STATE.filters[filter] = value;
            }
            
            renderBills();
            StorageManager.save();
        });
    });
}

// Auto-save functionality
function setupAutoSave() {
    setInterval(() => {
        StorageManager.save();
    }, APP_CONFIG.autoSaveInterval);
}

// UI Controls
function toggleFilters() {
    const panel = document.getElementById('filtersPanel');
    const btn = document.getElementById('filterToggle');
    
    if (panel && btn) {
        panel.classList.toggle('active');
        btn.classList.toggle('active');
    }
}

function toggleTrackedOnly() {
    const btn = document.getElementById('trackedToggle');
    APP_STATE.filters.trackedOnly = !APP_STATE.filters.trackedOnly;
    if (btn) {
        btn.classList.toggle('active');
    }
    renderBills();
    StorageManager.save();
}

function toggleUserPanel() {
    const panel = document.getElementById('userPanel');
    const notesSection = document.getElementById('userNotesSection');
    const expandBtn = document.getElementById('expandBtn');
    
    if (panel && notesSection && expandBtn) {
        panel.classList.toggle('expanded');
        notesSection.classList.toggle('active');
        expandBtn.classList.toggle('expanded');
    }
}

async function refreshData() {
    const syncStatus = document.getElementById('syncStatus');
    if (syncStatus) {
        syncStatus.classList.add('syncing');
    }
    
    await loadBillsData();
    updateUI();
    
    setTimeout(() => {
        if (syncStatus) {
            syncStatus.classList.remove('syncing');
        }
    }, 1000);
}

function showMainView() {
    APP_STATE.currentView = 'main';
    const statsView = document.getElementById('statsView');
    const mainView = document.getElementById('mainView');
    
    if (statsView) statsView.classList.remove('active');
    if (mainView) mainView.classList.add('active');
    
    updateUI();
}

// Utility Functions
function formatDate(dateString) {
    if (!dateString) return 'Unknown date';
    
    const date = new Date(dateString);
    const now = new Date();
    const diff = now - date;
    const days = Math.floor(diff / (1000 * 60 * 60 * 24));
    
    if (days === 0) {
        const hours = Math.floor(diff / (1000 * 60 * 60));
        if (hours === 0) {
            return 'Just now';
        }
        return `${hours} hour${hours > 1 ? 's' : ''} ago`;
    } else if (days === 1) {
        return 'Yesterday';
    } else if (days < 7) {
        return `${days} days ago`;
    } else {
        return date.toLocaleDateString();
    }
}

function formatTime(dateString) {
    if (!dateString) return '';
    const date = new Date(dateString);
    return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
}

// Toast Notifications
function showToast(message) {
    const toast = document.getElementById('toast');
    if (toast) {
        toast.textContent = message;
        toast.classList.add('show');
        
        setTimeout(() => {
            toast.classList.remove('show');
        }, 3000);
    }
}

// Add highlight animation to CSS dynamically
const style = document.createElement('style');
style.textContent = `
    @keyframes highlight {
        0% { box-shadow: 0 0 0 0 var(--accent); }
        50% { box-shadow: 0 0 20px 10px var(--accent); }
        100% { box-shadow: 0 0 0 0 var(--accent); }
    }
    
    .bill-companions {
        font-size: 0.875rem;
        color: var(--text-muted);
        margin: 0.5rem 0;
    }
`;
document.head.appendChild(style);

// Console info for debugging
console.log('WA Bill Tracker initialized');
console.log('Schema version:', APP_STATE.schemaVersion);
console.log('Biennium:', APP_CONFIG.biennium);
console.log('Session:', APP_CONFIG.sessionStart.toLocaleDateString(), '-', APP_CONFIG.sessionEnd.toLocaleDateString());
