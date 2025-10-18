# Battleship Match Visualizer - Web Application

A modern web-based visualizer for battleship matches, converted from the original Tkinter application.

## Features

- 🎮 **Live Match Viewing** - Watch matches in real-time
- 🔄 **Game Replay** - Step through completed games move by move
- 🏢 **Lobby Management** - Create, join, and delete lobbies
- 📊 **Progress Tracking** - Visual progress bars for match scores
- 🗺️ **Board Visualization** - Interactive canvas-based board rendering
- 📜 **Move History** - Complete shot history with results
- ⚙️ **Adjustable Refresh Rate** - Control update frequency

## Files Structure

```
visualizer/
├── index.html          # Main HTML structure
├── styles.css          # All styling and layout
├── app.js              # Application logic and API handling
├── proxy-server.js     # CORS proxy server (Node.js)
└── README.md           # This file
```

## Setup and Running

### Prerequisites

- Node.js (for the server)
- A web browser

### Step 1: Start the Server

The server serves static files AND proxies API requests (bypassing CORS).

```bash
cd /home/babos/Documents/battleship/visualizer
node server.js
```

You should see:
```
╔════════════════════════════════════════════════════╗
║  Battleship Visualizer Server                     ║
╠════════════════════════════════════════════════════╣
║  Server running on: http://localhost:3000         ║
║  API forwarding to: https://battle.piratesonline.us  ║
╚════════════════════════════════════════════════════╝
```

### Step 2: Open in Browser

Open your web browser and navigate to:
```
http://localhost:3000
```

That's it! Just one server to run. 🚀

## Configuration

The API configuration is in `app.js`:

```javascript
const BASE_URL = 'http://localhost:3000';  // Proxy server URL
const API_KEY = 'Harcivizibusz';            // API key
```

The proxy server configuration is in `proxy-server.js`:

```javascript
const BASE_URL = 'https://battle.piratesonline.us';
const API_KEY = 'Harcivizibusz';
const PORT = 3000;
```

## Usage

### Viewing Matches

1. **Select a Lobby** - Choose from available lobbies in the dropdown
2. **Create a Lobby** - Enter a lobby key and click "Create"
3. **Select a Match** - Choose from active or completed matches
4. **View Live** - Watch the current game in real-time

### Replay Controls

- **Play/Pause** - Start or stop automatic replay
- **◀ / ▶** - Step backward or forward through shots
- **Slider** - Jump to any point in the game
- **Reveal Boards** - Toggle ship visibility

### Features

- **Update Interval** - Adjust polling frequency (0.2s - 5.0s)
- **Game Selection** - Switch between live view and historical games
- **Progress Bars** - Visual representation of match scores
- **Move History** - Detailed log of all shots and results

## How It Works

The server handles two types of requests:

1. **Static Files** - Serves HTML, CSS, JS files directly
2. **API Proxy** - Forwards `/api/*` requests to the battleship API with CORS headers

This solves the CORS issue because:
- Browser connects to `http://localhost:3000` (same origin)
- Server forwards API requests to `https://battle.piratesonline.us`
- Server adds proper CORS headers to responses
- Automatically includes the API key

## Troubleshooting

### Connection Refused
Make sure the server is running:
```bash
node server.js
```

### Port Already in Use
Change the port in:
- `server.js` (line: `const PORT = 3000`)
- `app.js` (line: `const BASE_URL = 'http://localhost:3000'`)

## Development

To modify the application:

1. **HTML** - Edit `index.html` for structure changes
2. **Styling** - Edit `styles.css` for appearance changes
3. **Logic** - Edit `app.js` for functionality changes
4. **Proxy** - Edit `proxy-server.js` for API configuration

Changes to HTML, CSS, and JS require a browser refresh. The proxy server needs to be restarted if modified.

## Original Application

This is a web port of the original Tkinter-based visualizer (`match_viewer.py`). The functionality remains the same while providing a more accessible browser-based interface.

## License

Same as the original battleship project.
