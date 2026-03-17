// ========== js/script.js ==========
// SINGLE JAVASCRIPT FILE FOR ALL PAGES
// All HTML files link to this same script

document.addEventListener('DOMContentLoaded', function() {
    
    // ============================================
    // 1. MOBILE HAMBURGER MENU (Works on all pages)
    // ============================================
    const hamburger = document.querySelector('.hamburger');
    const navMenu = document.querySelector('.nav-menu');

    if (hamburger && navMenu) {
        hamburger.addEventListener('click', () => {
            navMenu.classList.toggle('active');
            hamburger.classList.toggle('active');
        });

        document.querySelectorAll('.nav-menu a').forEach(link => {
            link.addEventListener('click', () => {
                navMenu.classList.remove('active');
                hamburger.classList.remove('active');
            });
        });
    }

    // ============================================
    // 2. ACTIVE PAGE HIGHLIGHTING
    // ============================================
    const currentPage = window.location.pathname.split('/').pop() || 'index.html';
    const navLinks = document.querySelectorAll('.nav-menu a');
    
    navLinks.forEach(link => {
        const linkPage = link.getAttribute('href');
        if (linkPage === currentPage) {
            link.classList.add('active');
        }
    });

    // ============================================
    // 3. GRID GENERATION (for terrain and preview)
    // ============================================
    function generateGrid(containerId, isInteractive = true) {
        const container = document.getElementById(containerId);
        if (!container) return;

        container.innerHTML = '';

        for (let i = 0; i < 25; i++) {
            const tile = document.createElement('div');
            tile.className = 'grid-tile';
            
            if (i === 6 || i === 12 || i === 18) {
                tile.classList.add('player');
                tile.textContent = '👤';
            } else if (i === 8 || i === 16) {
                tile.classList.add('empty');
            }
            
            if (isInteractive) {
                tile.addEventListener('click', function(e) {
                    if (!this.classList.contains('empty') && !this.classList.contains('player')) {
                        this.classList.add('empty');
                        this.textContent = '';
                    } else if (this.classList.contains('player')) {
                        alert('A player is standing here! Attack them to make the tile disappear.');
                    }
                });
            }
            
            container.appendChild(tile);
        }
    }

    if (document.getElementById('game-grid')) {
        generateGrid('game-grid', true);
    }
    if (document.getElementById('preview-grid')) {
        generateGrid('preview-grid', false);
    }

    // ============================================
    // 4. REAL-TIME DOWNLOAD STATISTICS (Shared across pages)
    // ============================================
    const totalDownloadsElem = document.getElementById('total-downloads');
    const activeUsersElem = document.getElementById('active-users');
    const onlinePlayersElem = document.getElementById('online-players');
    const homeDownloadsElem = document.getElementById('home-downloads');
    const homeActiveElem = document.getElementById('home-active');
    const headerDownloadsElem = document.getElementById('total-downloads-header');

    let totalDownloads = 15432;
    let activeUsers = 1243;
    let onlinePlayers = 876;

    function updateStats() {
        totalDownloads += Math.floor(Math.random() * 5) + 1;
        activeUsers = Math.floor(Math.random() * 1500) + 1000;
        onlinePlayers = Math.floor(Math.random() * 1500) + 500;

        const formattedDownloads = totalDownloads.toLocaleString();
        const formattedActive = activeUsers.toLocaleString();
        const formattedOnline = onlinePlayers.toLocaleString();

        if (totalDownloadsElem) totalDownloadsElem.textContent = formattedDownloads;
        if (activeUsersElem) activeUsersElem.textContent = formattedActive;
        if (onlinePlayersElem) onlinePlayersElem.textContent = formattedOnline;
        
        if (homeDownloadsElem) homeDownloadsElem.textContent = (totalDownloads/1000).toFixed(1) + 'k';
        if (homeActiveElem) homeActiveElem.textContent = (activeUsers/1000).toFixed(1) + 'k';
        
        if (headerDownloadsElem) headerDownloadsElem.textContent = formattedDownloads;
    }

    setInterval(updateStats, 5000);
    updateStats();

    // ============================================
    // 5. DOWNLOAD BUTTON TRACKING
    // ============================================
    const downloadButtons = document.querySelectorAll('.platform-card');
    
    downloadButtons.forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            
            totalDownloads += 1;
            updateStats();
            
            const platform = this.getAttribute('data-platform') || 'Desktop';
            alert(`⬇️ Download started for ${platform}! (Demo - download counted)`);
        });
    });

    // ============================================
    // 6. SIMULATED TILE DISAPPEARANCE
    // ============================================
    setInterval(() => {
        const tiles = document.querySelectorAll('.grid-tile:not(.player):not(.empty)');
        if (tiles.length > 0) {
            const randomTile = tiles[Math.floor(Math.random() * tiles.length)];
            randomTile.classList.add('empty');
            randomTile.textContent = '';
        }
    }, 15000);

    console.log(`Grid Survival - Current page: ${currentPage} - All files relate to this JS`);
});