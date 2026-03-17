// ========== script.js ==========

// Wait for DOM to fully load
document.addEventListener('DOMContentLoaded', function() {
    
    // --- 1. TERRAIN GRID GENERATION (Interactive Demo) ---
    const gridContainer = document.getElementById('game-grid');
    if (gridContainer) {
        // Create a 5x5 grid
        for (let i = 0; i < 25; i++) {
            const tile = document.createElement('div');
            tile.className = 'grid-tile';
            
            // Randomly assign some tiles as 'player' occupied for visual effect, others normal
            // Make it look like a game in progress: 3 players on grid
            if (i === 6 || i === 12 || i === 18) {
                tile.classList.add('player');
                tile.textContent = '🧑'; // Player icon
            } else if (i === 8 || i === 16) {
                tile.classList.add('empty'); // empty/disappeared tiles
                tile.textContent = ' ';
            } else {
                tile.textContent = ' '; // normal tile
            }
            
            // Add click interaction to simulate disappearing (for demo)
            tile.addEventListener('click', function(e) {
                if (!this.classList.contains('empty') && !this.classList.contains('player')) {
                    this.classList.add('empty');
                    this.textContent = '';
                    // Simple feedback: after click, tile "disappears"
                } else if (this.classList.contains('player')) {
                    alert('A player is standing here! Attack them to make the tile disappear.');
                } else {
                    alert('This tile is already gone.');
                }
            });
            
            gridContainer.appendChild(tile);
        }
    }

    // --- 2. REAL-TIME DOWNLOAD STATISTICS (Simulated) ---
    const totalDownloadsElem = document.getElementById('total-downloads');
    const activeUsersElem = document.getElementById('active-users');
    const onlinePlayersElem = document.getElementById('online-players');
    const downloadLink = document.getElementById('download-link');

    // Starting values
    let totalDownloads = 15432;
    let activeUsers = 1243;
    let onlinePlayers = 876;

    // Function to update stats with random increments
    function updateStats() {
        // Simulate real-time changes: increase downloads and fluctuate active/online
        totalDownloads += Math.floor(Math.random() * 10) + 1; // increase by 1-10
        // Active users fluctuate between 1000 and 2500
        activeUsers = Math.floor(Math.random() * 1500) + 1000;
        // Online players fluctuate between 500 and 2000
        onlinePlayers = Math.floor(Math.random() * 1500) + 500;

        // Update the DOM
        if (totalDownloadsElem) totalDownloadsElem.textContent = totalDownloads.toLocaleString();
        if (activeUsersElem) activeUsersElem.textContent = activeUsers.toLocaleString();
        if (onlinePlayersElem) onlinePlayersElem.textContent = onlinePlayers.toLocaleString();

        // Optional: Change color briefly to indicate update
        [totalDownloadsElem, activeUsersElem, onlinePlayersElem].forEach(elem => {
            if (elem) {
                elem.style.transition = 'color 0.5s';
                elem.style.color = '#4a6fa5';
                setTimeout(() => { elem.style.color = ''; }, 500);
            }
        });
    }

    // Update stats every 5 seconds (simulating real-time data)
    setInterval(updateStats, 5000);

    // Also update immediately on page load
    updateStats();

    // --- 3. DOWNLOAD LINK TRACKING (Simulated real-time counter increment on click) ---
    if (downloadLink) {
        downloadLink.addEventListener('click', function(e) {
            e.preventDefault(); // Prevent actual download for demo
            
            // Simulate download count increase
            totalDownloads += 1;
            if (totalDownloadsElem) totalDownloadsElem.textContent = totalDownloads.toLocaleString();
            
            // Show a friendly message
            alert('Thank you for downloading Grid Survival! (Demo simulation - your download has been counted.)');
            
            // You could also open a real link here: window.open('https://example.com/download', '_blank');
        });
    }

    // --- 4. MOBILE HAMBURGER MENU ---
    const hamburger = document.querySelector('.hamburger');
    const navMenu = document.querySelector('.nav-menu');

    if (hamburger && navMenu) {
        hamburger.addEventListener('click', () => {
            navMenu.classList.toggle('active');
            // Animate hamburger
            hamburger.classList.toggle('active');
        });

        // Close menu when a link is clicked
        document.querySelectorAll('.nav-menu a').forEach(link => {
            link.addEventListener('click', () => {
                navMenu.classList.remove('active');
                hamburger.classList.remove('active');
            });
        });
    }

    // --- 5. SMOOTH SCROLL FOR NAVIGATION (fallback) ---
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            e.preventDefault();
            const target = document.querySelector(this.getAttribute('href'));
            if (target) {
                target.scrollIntoView({
                    behavior: 'smooth',
                    block: 'start'
                });
            }
        });
    });

    // --- 6. ADD MINIMAL INTERACTIVITY TO PLAYER CARDS (hover effect already in CSS) ---
    // Optional: log which mode user is interested in
    const playerCards = document.querySelectorAll('.player-card');
    playerCards.forEach(card => {
        card.addEventListener('mouseenter', () => {
            const mode = card.getAttribute('data-mode') || 'unknown';
            console.log(`User hovering over ${mode} mode`);
        });
    });

    // --- 7. SIMULATE REAL-TIME PLAYER COUNT ON TERRAIN (tiny extra) ---
    // Change player positions on grid every 10 seconds to simulate movement? No, keep static but add a little flavor.
    // Instead, we can randomly toggle one tile to 'empty' every 15 sec to show dynamic terrain
    setInterval(() => {
        const tiles = document.querySelectorAll('.grid-tile:not(.player):not(.empty)');
        if (tiles.length > 0) {
            const randomTile = tiles[Math.floor(Math.random() * tiles.length)];
            randomTile.classList.add('empty');
            randomTile.textContent = '';
            // After 3 seconds, maybe bring it back? No, but we can show a message
            console.log('A tile disappeared! (simulated)');
        }
    }, 15000); // every 15 seconds one random normal tile disappears
});