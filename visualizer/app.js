// Hardcoded configuration
// Using local proxy server to bypass CORS restrictions
const BASE_URL = 'http://localhost:3000';
const API_KEY = 'Harcivizibusz';

// State
let state = {
    interval: 1.0,
    revealBoards: true,
    selectedLobby: null,
    selectedMatch: null,
    selectedGame: null,
    lobbies: {},
    matches: {},
    currentData: null,
    currentHistory: [],
    currentStep: 0,
    maxStep: 0,
    isPlaying: false,
    lastUpdate: 0,
    isFetching: false,
    boardWidgets: {}
};

// DOM elements
const elements = {
    intervalSlider: document.getElementById('intervalSlider'),
    intervalLabel: document.getElementById('intervalLabel'),
    revealBoards: document.getElementById('revealBoards'),
    lobbySelect: document.getElementById('lobbySelect'),
    deleteLobbyBtn: document.getElementById('deleteLobbyBtn'),
    newLobbyKey: document.getElementById('newLobbyKey'),
    createLobbyBtn: document.getElementById('createLobbyBtn'),
    lobbyInfo: document.getElementById('lobbyInfo'),
    matchSelect: document.getElementById('matchSelect'),
    gameSelect: document.getElementById('gameSelect'),
    playBtn: document.getElementById('playBtn'),
    stepBackBtn: document.getElementById('stepBackBtn'),
    stepForwardBtn: document.getElementById('stepForwardBtn'),
    stepLabel: document.getElementById('stepLabel'),
    replaySlider: document.getElementById('replaySlider'),
    progressSection: document.getElementById('progressSection'),
    gameInfo: document.getElementById('gameInfo'),
    boardsContainer: document.getElementById('boardsContainer'),
    historyBox: document.getElementById('historyBox'),
    statusBar: document.getElementById('statusBar')
};

// Event listeners
elements.intervalSlider.addEventListener('input', (e) => {
    state.interval = parseFloat(e.target.value);
    elements.intervalLabel.textContent = state.interval.toFixed(1) + 's';
});

elements.revealBoards.addEventListener('change', (e) => {
    state.revealBoards = e.target.checked;
    redrawBoards();
});

elements.lobbySelect.addEventListener('change', (e) => {
    onLobbySelected(e.target.value);
});

elements.deleteLobbyBtn.addEventListener('click', deleteLobby);
elements.createLobbyBtn.addEventListener('click', createLobby);

elements.matchSelect.addEventListener('change', (e) => {
    onMatchSelected(e.target.value);
});

elements.gameSelect.addEventListener('change', (e) => {
    onGameSelected(e.target.value);
});

elements.playBtn.addEventListener('click', togglePlay);
elements.stepBackBtn.addEventListener('click', stepBack);
elements.stepForwardBtn.addEventListener('click', stepForward);
elements.replaySlider.addEventListener('input', (e) => {
    state.isPlaying = false;
    state.currentStep = parseInt(e.target.value);
    syncReplayControls();
    renderCurrentState();
});

// API functions
async function apiRequest(endpoint, options = {}) {
    const url = `${BASE_URL}${endpoint}`;
    const headers = {
        'x-api-key': API_KEY,
        'Content-Type': 'application/json',
        ...options.headers
    };

    try {
        const response = await fetch(url, { ...options, headers });
        if (!response.ok) {
            const text = await response.text();
            throw new Error(`HTTP ${response.status}: ${text.substring(0, 200)}`);
        }
        return await response.json();
    } catch (error) {
        throw error;
    }
}

async function fetchMatches() {
    return await apiRequest('/api/v1/admin/matches');
}

async function fetchLobbies() {
    return await apiRequest('/api/v1/lobby/list');
}

async function fetchMatchInsight(matchId, gameId = null) {
    const params = gameId ? `?game_id=${gameId}` : '';
    return await apiRequest(`/api/v1/admin/match/${matchId}/insight${params}`);
}

async function createLobby() {
    const key = elements.newLobbyKey.value.trim();
    if (!key) {
        elements.statusBar.textContent = 'Enter a lobby key before creating.';
        return;
    }

    try {
        await apiRequest('/api/v1/lobby/create', {
            method: 'POST',
            body: JSON.stringify({ lobby_key: key })
        });
        elements.statusBar.textContent = `Lobby '${key}' created.`;
        elements.newLobbyKey.value = '';
    } catch (error) {
        elements.statusBar.textContent = `Create lobby failed: ${error.message}`;
    }
}

async function deleteLobby() {
    if (!state.selectedLobby) {
        elements.statusBar.textContent = 'Select a lobby to delete.';
        return;
    }

    const key = state.selectedLobby;
    try {
        await apiRequest(`/api/v1/lobby/${encodeURIComponent(key)}`, {
            method: 'DELETE'
        });
        elements.statusBar.textContent = `Lobby '${key}' deleted.`;
        state.selectedLobby = null;
        elements.lobbySelect.value = '';
        elements.deleteLobbyBtn.disabled = true;
        updateLobbyDisplay(null);
    } catch (error) {
        elements.statusBar.textContent = `Delete lobby failed: ${error.message}`;
    }
}

// Update functions
function applyMatchList(payload) {
    const matches = payload.matches || [];
    state.matches = {};
    
    elements.matchSelect.innerHTML = '<option value="">Select a match</option>';
    
    matches.forEach(match => {
        state.matches[match.match_id] = match;
        const p1 = match.player1.player_name;
        const p2 = match.player2.player_name;
        const status = match.match_active ? 'LIVE' : 'FINAL';
        const label = `${p1} vs ${p2} [${status}] · ${match.match_id.substring(0, 8)}`;
        
        const option = document.createElement('option');
        option.value = match.match_id;
        option.textContent = label;
        elements.matchSelect.appendChild(option);
    });

    // Restore selection if match still exists
    if (state.selectedMatch && state.matches[state.selectedMatch]) {
        elements.matchSelect.value = state.selectedMatch;
    }
}

function applyLobbyList(payload) {
    const lobbies = payload.lobbies || [];
    state.lobbies = {};
    
    elements.lobbySelect.innerHTML = '<option value="">Select a lobby</option>';
    
    lobbies.forEach(lobby => {
        state.lobbies[lobby.lobby_key] = lobby;
        const joined = lobby.players.filter(p => p.joined).length;
        const status = (lobby.status || 'waiting').toUpperCase();
        const label = `${lobby.lobby_key} [${status}] ${joined}/2`;
        
        const option = document.createElement('option');
        option.value = lobby.lobby_key;
        option.textContent = label;
        elements.lobbySelect.appendChild(option);
    });

    // Restore selection if lobby still exists
    if (state.selectedLobby && state.lobbies[state.selectedLobby]) {
        elements.lobbySelect.value = state.selectedLobby;
        const lobby = state.lobbies[state.selectedLobby];
        updateLobbyDisplay(lobby);
        
        // Auto-select match if lobby has one
        if (lobby.match_id && state.selectedMatch !== lobby.match_id) {
            setActiveMatch(lobby.match_id);
        }
    }
}

function updateLobbyDisplay(lobby) {
    if (!lobby) {
        elements.lobbyInfo.textContent = 'Select a lobby to view status.';
        return;
    }

    const status = (lobby.status || 'waiting').toUpperCase();
    const lines = [`Lobby: ${lobby.lobby_key} — ${status}`];
    
    const sortedPlayers = lobby.players.sort((a, b) => a.slot - b.slot);
    sortedPlayers.forEach(player => {
        if (player.joined) {
            const tagline = player.tagline ? ` — ${player.tagline}` : '';
            lines.push(`Slot ${player.slot}: ${player.player_name}${tagline}`);
        } else {
            lines.push(`Slot ${player.slot}: awaiting player`);
        }
    });
    
    if (lobby.match_id) {
        lines.push(`Match ID: ${lobby.match_id.substring(0, 8)}`);
    }
    
    elements.lobbyInfo.textContent = lines.join('\n');
}

function onLobbySelected(lobbyKey) {
    state.selectedLobby = lobbyKey || null;
    elements.deleteLobbyBtn.disabled = !lobbyKey;
    
    const lobby = lobbyKey ? state.lobbies[lobbyKey] : null;
    updateLobbyDisplay(lobby);
    
    if (lobby && lobby.match_id) {
        setActiveMatch(lobby.match_id);
    } else if (lobbyKey) {
        elements.statusBar.textContent = `Lobby '${lobbyKey}' selected.`;
    }
}

function onMatchSelected(matchId) {
    state.selectedLobby = null;
    elements.lobbySelect.value = '';
    elements.deleteLobbyBtn.disabled = true;
    updateLobbyDisplay(null);
    
    setActiveMatch(matchId);
}

function setActiveMatch(matchId) {
    state.selectedMatch = matchId || null;
    state.selectedGame = null;
    
    if (!matchId) {
        elements.matchSelect.value = '';
        elements.gameSelect.value = '';
        elements.gameSelect.disabled = true;
        elements.statusBar.textContent = 'Select a lobby or match to begin.';
        clearMatchDisplay();
        return;
    }
    
    elements.matchSelect.value = matchId;
    elements.gameSelect.value = '';
    elements.gameSelect.disabled = true;
    
    resetViewState();
    
    const match = state.matches[matchId];
    if (match) {
        const p1 = match.player1.player_name;
        const p2 = match.player2.player_name;
        const score = `${match.player1_points}–${match.player2_points}`;
        const status = match.match_active ? 'LIVE' : 'FINAL';
        elements.statusBar.textContent = `Viewing ${p1} vs ${p2} (${score}) — ${status}. Awaiting update…`;
    } else {
        elements.statusBar.textContent = 'Match selected — awaiting update…';
    }
}

function onGameSelected(gameId) {
    state.selectedGame = gameId || null;
    state.isPlaying = false;
    state.currentStep = 0;
    syncReplayControls();
    
    const mode = gameId ? 'replay' : 'live';
    elements.statusBar.textContent = `Viewing ${mode} data — awaiting update…`;
}

function clearMatchDisplay() {
    state.currentData = null;
    state.currentHistory = [];
    state.currentStep = 0;
    state.maxStep = 0;
    state.isPlaying = false;
    
    elements.gameInfo.textContent = 'No match selected.';
    elements.progressSection.innerHTML = '';
    elements.boardsContainer.innerHTML = '';
    elements.historyBox.innerHTML = '';
    
    syncReplayControls();
}

function resetViewState() {
    state.currentData = null;
    state.currentHistory = [];
    state.currentStep = 0;
    state.maxStep = 0;
    state.isPlaying = false;
    
    elements.gameInfo.textContent = 'Awaiting data…';
    elements.gameSelect.innerHTML = '<option value="">Live view</option>';
    elements.gameSelect.disabled = true;
    elements.boardsContainer.innerHTML = '';
    elements.historyBox.innerHTML = '';
    
    syncReplayControls();
}

function applyData(data) {
    state.currentData = data;
    
    // Update progress bars
    const progress = data.progress || {};
    const players = progress.players || [];
    const target = progress.target_points || 0;
    
    updateProgressBars(players, target);
    
    // Build player lookup
    const playerLookup = {};
    players.forEach(entry => {
        playerLookup[entry.player.player_id] = entry.player.player_name;
    });
    
    // Update game options
    updateGameOptions(data, playerLookup);
    
    // Update match status
    const matchActive = data.match_active !== false;
    const viewMode = state.selectedGame ? 'Replay' : 'Live';
    const timestamp = new Date().toLocaleTimeString();
    elements.statusBar.textContent = 
        `Last update: ${timestamp} — Match ${matchActive ? 'active' : 'complete'} — ${viewMode} mode`;
    
    // Update game data
    const gameData = data.current_game;
    state.currentHistory = gameData ? gameData.shot_history || [] : [];
    state.maxStep = state.currentHistory.length;
    
    if (!state.selectedGame) {
        state.currentStep = state.maxStep;
    } else {
        state.currentStep = Math.min(state.currentStep, state.maxStep);
    }
    
    elements.replaySlider.max = state.maxStep;
    elements.replaySlider.value = state.currentStep;
    
    syncReplayControls();
    
    if (!gameData) {
        if (state.selectedGame) {
            elements.gameInfo.textContent = 'Selected game unavailable or not found.';
        } else {
            elements.gameInfo.textContent = 'No active games. Waiting for the next game to begin.';
        }
        elements.boardsContainer.innerHTML = '';
        elements.historyBox.innerHTML = '';
        return;
    }
    
    renderCurrentState();
}

function updateProgressBars(players, target) {
    elements.progressSection.innerHTML = '';
    
    players.forEach(entry => {
        const player = entry.player;
        const progress = entry.progress || 0;
        const points = entry.points || 0;
        const remaining = entry.points_remaining || 0;
        
        const progressItem = document.createElement('div');
        progressItem.className = 'progress-item';
        
        progressItem.innerHTML = `
            <div class="progress-label">${player.player_name}</div>
            <div class="progress-bar">
                <div class="progress-fill" style="width: ${progress * 100}%"></div>
            </div>
            <div class="progress-text">${points} / ${target} (remaining: ${remaining})</div>
        `;
        
        elements.progressSection.appendChild(progressItem);
    });
}

function updateGameOptions(data, playerLookup) {
    const history = (data.game_history || []).sort((a, b) => a.game_number - b.game_number);
    
    elements.gameSelect.innerHTML = '<option value="">Live view</option>';
    
    const gameOptions = [];
    
    history.forEach(entry => {
        let label = `Game ${entry.game_number || '?'}`;
        if (entry.winner_id) {
            const winnerName = playerLookup[entry.winner_id] || entry.winner_id.substring(0, 8);
            label += ` — Winner ${winnerName}`;
        } else {
            label += ' — Pending';
        }
        label += ` (${entry.shots || 0} shots)`;
        
        const option = document.createElement('option');
        option.value = entry.game_id;
        option.textContent = label;
        elements.gameSelect.appendChild(option);
        gameOptions.push(entry.game_id);
    });
    
    const currentGame = data.current_game;
    if (currentGame && !gameOptions.includes(currentGame.game_id)) {
        const status = currentGame.game_active ? 'in progress' : 'completed';
        const label = `Game ${currentGame.game_number} — ${status}`;
        
        const option = document.createElement('option');
        option.value = currentGame.game_id;
        option.textContent = label;
        elements.gameSelect.appendChild(option);
    }
    
    elements.gameSelect.disabled = false;
    
    // Restore selection
    if (state.selectedGame) {
        elements.gameSelect.value = state.selectedGame;
    }
}

function renderCurrentState() {
    if (!state.currentData) return;
    
    const gameData = state.currentData.current_game;
    if (!gameData) return;
    
    // Build player lookup
    const playerMap = {};
    gameData.boards.forEach(board => {
        playerMap[board.player.player_id] = board.player.player_name;
    });
    
    // Update game info
    const currentTurn = gameData.current_turn;
    const turnLabel = currentTurn && playerMap[currentTurn] ? playerMap[currentTurn] : '-';
    const statusLabel = gameData.game_active ? 'active' : 'completed';
    
    elements.gameInfo.textContent = 
        `Game ${gameData.game_number} (${statusLabel}) — Current turn: ${turnLabel} — Shots: ${state.currentStep}/${state.maxStep}`;
    
    elements.stepLabel.textContent = `Shot ${state.currentStep}/${state.maxStep}`;
    
    // Draw boards
    drawBoards(gameData);
    
    // Update history
    updateHistory(state.currentHistory.slice(0, state.currentStep));
}

function drawBoards(gameData) {
    const boards = gameData.boards;
    const [gridRows, gridCols] = gameData.grid_size;
    
    // Create board containers if needed
    boards.forEach(board => {
        const playerId = board.player.player_id;
        
        if (!state.boardWidgets[playerId]) {
            const wrapper = document.createElement('div');
            wrapper.className = 'board-wrapper';
            wrapper.id = `board-${playerId}`;
            
            const title = document.createElement('div');
            title.className = 'board-title';
            wrapper.appendChild(title);
            
            const canvas = document.createElement('canvas');
            canvas.className = 'board-canvas';
            wrapper.appendChild(canvas);
            
            elements.boardsContainer.appendChild(wrapper);
            
            state.boardWidgets[playerId] = { wrapper, title, canvas };
        }
    });
    
    // Draw each board
    boards.forEach(board => {
        const playerId = board.player.player_id;
        const widgets = state.boardWidgets[playerId];
        
        if (!widgets) return;
        
        // Update title
        const teleportUsed = board.teleport_used ? 'Yes' : 'No';
        widgets.title.textContent = `${board.player.player_name} (Teleport used: ${teleportUsed})`;
        
        // Draw on canvas
        drawBoardCanvas(widgets.canvas, board, gameData.grid_size, state.currentStep);
    });
}

function drawBoardCanvas(canvas, board, gridSize, shotLimit) {
    const ctx = canvas.getContext('2d');
    const [gridRows, gridCols] = gridSize;
    
    const width = canvas.clientWidth;
    const height = canvas.clientHeight;
    canvas.width = width;
    canvas.height = height;
    
    const cellSize = Math.min(
        (width - 8) / gridCols,
        (height - 8) / gridRows
    );
    
    const offsetX = (width - cellSize * gridCols) / 2;
    const offsetY = (height - cellSize * gridRows) / 2;
    
    // Clear canvas
    ctx.fillStyle = 'white';
    ctx.fillRect(0, 0, width, height);
    
    // Draw grid
    ctx.strokeStyle = '#cccccc';
    ctx.lineWidth = 1;
    
    for (let row = 0; row <= gridRows; row++) {
        const y = offsetY + row * cellSize;
        ctx.beginPath();
        ctx.moveTo(offsetX, y);
        ctx.lineTo(offsetX + gridCols * cellSize, y);
        ctx.stroke();
    }
    
    for (let col = 0; col <= gridCols; col++) {
        const x = offsetX + col * cellSize;
        ctx.beginPath();
        ctx.moveTo(x, offsetY);
        ctx.lineTo(x, offsetY + gridRows * cellSize);
        ctx.stroke();
    }
    
    // Collect hits and misses
    const hits = new Set();
    const misses = new Set();
    
    board.shots_received.forEach(shot => {
        if ((shot.turn || 0) <= shotLimit) {
            const key = `${shot.coordinate.row},${shot.coordinate.col}`;
            if (shot.result === 'miss') {
                misses.add(key);
            } else {
                hits.add(key);
            }
        }
    });
    
    const sunkCells = new Set();
    
    // Draw ships if revealed
    if (state.revealBoards) {
        board.ships.forEach(ship => {
            const coords = ship.coordinates.map(c => [c.row, c.col]);
            const hitsOnShip = (ship.hits || []).map(c => [c.row, c.col]);
            const sunk = ship.sunk || false;
            
            if (sunk) {
                coords.forEach(([row, col]) => {
                    sunkCells.add(`${row},${col}`);
                });
            }
            
            // Draw previous positions
            const previousPositions = ship.previous_positions || [];
            previousPositions.forEach(prevCoords => {
                prevCoords.forEach(coord => {
                    const row = coord.row;
                    const col = coord.col;
                    const isCurrentPos = coords.some(([r, c]) => r === row && c === col);
                    if (!isCurrentPos) {
                        drawCell(ctx, cellSize, offsetX, offsetY, row, col, '#BDBDBD');
                    }
                });
            });
            
            // Draw ship
            const baseColor = sunk ? '#9E9E9E' : '#4A90E2';
            coords.forEach(([row, col]) => {
                drawCell(ctx, cellSize, offsetX, offsetY, row, col, baseColor);
            });
            
            // Draw hits on ship
            hitsOnShip.forEach(([row, col]) => {
                drawCell(ctx, cellSize, offsetX, offsetY, row, col, '#D0021B');
            });
        });
    }
    
    // Draw misses
    misses.forEach(key => {
        const [row, col] = key.split(',').map(Number);
        drawMiss(ctx, cellSize, offsetX, offsetY, row, col);
    });
    
    // Draw sunk markers
    sunkCells.forEach(key => {
        const [row, col] = key.split(',').map(Number);
        drawSunkMarker(ctx, cellSize, offsetX, offsetY, row, col);
    });
}

function drawCell(ctx, cellSize, offsetX, offsetY, row, col, fill) {
    const x0 = offsetX + col * cellSize + 1;
    const y0 = offsetY + row * cellSize + 1;
    const x1 = x0 + cellSize - 2;
    const y1 = y0 + cellSize - 2;
    
    ctx.fillStyle = fill;
    ctx.fillRect(x0, y0, x1 - x0, y1 - y0);
}

function drawMiss(ctx, cellSize, offsetX, offsetY, row, col) {
    const radius = cellSize * 0.2;
    const centerX = offsetX + col * cellSize + cellSize / 2;
    const centerY = offsetY + row * cellSize + cellSize / 2;
    
    ctx.strokeStyle = '#333333';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
    ctx.stroke();
}

function drawSunkMarker(ctx, cellSize, offsetX, offsetY, row, col) {
    const margin = Math.max(cellSize * 0.15, 2);
    const x0 = offsetX + col * cellSize + margin;
    const y0 = offsetY + row * cellSize + margin;
    const x1 = offsetX + (col + 1) * cellSize - margin;
    const y1 = offsetY + (row + 1) * cellSize - margin;
    
    ctx.strokeStyle = '#222222';
    ctx.lineWidth = 2;
    
    ctx.beginPath();
    ctx.moveTo(x0, y0);
    ctx.lineTo(x1, y1);
    ctx.stroke();
    
    ctx.beginPath();
    ctx.moveTo(x0, y1);
    ctx.lineTo(x1, y0);
    ctx.stroke();
}

function updateHistory(history) {
    elements.historyBox.innerHTML = '';
    
    history.forEach(entry => {
        const coord = entry.coordinate;
        const result = entry.result.toUpperCase();
        const shipInfo = entry.ship_id !== null && entry.ship_id !== undefined 
            ? ` (ship ${entry.ship_id})` 
            : '';
        
        const line = document.createElement('div');
        line.className = 'history-entry';
        line.textContent = 
            `Turn ${String(entry.turn).padStart(2, '0')}: ${entry.player_name} -> ` +
            `(${coord.row}, ${coord.col}) ${result}${shipInfo}`;
        
        elements.historyBox.appendChild(line);
    });
    
    // Auto-scroll to bottom
    elements.historyBox.scrollTop = elements.historyBox.scrollHeight;
}

function redrawBoards() {
    if (state.currentData && state.currentData.current_game) {
        drawBoards(state.currentData.current_game);
    }
}

// Replay controls
function togglePlay() {
    if (!state.currentData || !state.selectedGame) return;
    
    state.isPlaying = !state.isPlaying;
    
    if (state.isPlaying && state.currentStep >= state.maxStep) {
        state.currentStep = 0;
    }
    
    syncReplayControls();
}

function stepForward() {
    if (!state.currentData || state.maxStep === 0) return;
    
    state.isPlaying = false;
    state.currentStep = Math.min(state.currentStep + 1, state.maxStep);
    elements.replaySlider.value = state.currentStep;
    
    syncReplayControls();
    renderCurrentState();
}

function stepBack() {
    if (!state.currentData) return;
    
    state.isPlaying = false;
    state.currentStep = Math.max(state.currentStep - 1, 0);
    elements.replaySlider.value = state.currentStep;
    
    syncReplayControls();
    renderCurrentState();
}

function syncReplayControls() {
    if (!state.selectedGame || state.maxStep === 0) {
        elements.playBtn.disabled = true;
        elements.stepBackBtn.disabled = true;
        elements.stepForwardBtn.disabled = true;
        elements.replaySlider.disabled = true;
        elements.playBtn.textContent = 'Play';
    } else {
        elements.playBtn.disabled = false;
        elements.stepBackBtn.disabled = false;
        elements.stepForwardBtn.disabled = false;
        elements.replaySlider.disabled = false;
        elements.playBtn.textContent = state.isPlaying ? 'Pause' : 'Play';
    }
    
    elements.stepLabel.textContent = `Shot ${state.currentStep}/${state.maxStep}`;
}

// Main update loop
let lastStepTime = Date.now();

async function updateLoop() {
    const now = Date.now();
    
    // Handle replay playback
    if (state.selectedGame && state.isPlaying && state.maxStep > 0) {
        if (state.currentStep < state.maxStep && (now - lastStepTime) >= state.interval * 1000) {
            state.currentStep++;
            elements.replaySlider.value = state.currentStep;
            lastStepTime = now;
            renderCurrentState();
        } else if (state.currentStep >= state.maxStep) {
            state.isPlaying = false;
            syncReplayControls();
        }
    }
    
    // Fetch data
    if (!state.isFetching && (now - state.lastUpdate) >= state.interval * 1000) {
        state.isFetching = true;
        
        try {
            // Fetch matches and lobbies
            const [matchesData, lobbiesData] = await Promise.all([
                fetchMatches().catch(() => null),
                fetchLobbies().catch(() => null)
            ]);
            
            if (matchesData) {
                applyMatchList(matchesData);
            }
            
            if (lobbiesData) {
                applyLobbyList(lobbiesData);
            }
            
            // Fetch match insight if match selected
            if (state.selectedMatch) {
                const insightData = await fetchMatchInsight(
                    state.selectedMatch, 
                    state.selectedGame
                );
                applyData(insightData);
            }
            
            state.lastUpdate = now;
        } catch (error) {
            elements.statusBar.textContent = `Error: ${error.message}`;
        } finally {
            state.isFetching = false;
        }
    }
    
    requestAnimationFrame(updateLoop);
}

// Start the application
updateLoop();
