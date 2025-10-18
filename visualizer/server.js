const http = require('http');
const https = require('https');
const fs = require('fs');
const path = require('path');
const url = require('url');

const BASE_URL = 'https://battle.piratesonline.us';
const API_KEY = 'Harcivizibusz';
const PORT = 3000;

// MIME types for different file extensions
const MIME_TYPES = {
    '.html': 'text/html',
    '.css': 'text/css',
    '.js': 'application/javascript',
    '.json': 'application/json',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.gif': 'image/gif',
    '.svg': 'image/svg+xml',
    '.ico': 'image/x-icon'
};

function serveStaticFile(filePath, res) {
    fs.readFile(filePath, (err, data) => {
        if (err) {
            if (err.code === 'ENOENT') {
                res.writeHead(404);
                res.end('File not found');
            } else {
                res.writeHead(500);
                res.end('Internal server error');
            }
            return;
        }
        
        const ext = path.extname(filePath);
        const contentType = MIME_TYPES[ext] || 'application/octet-stream';
        
        res.writeHead(200, { 'Content-Type': contentType });
        res.end(data);
    });
}

function proxyApiRequest(req, res, parsedUrl) {
    // Enable CORS
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type, x-api-key');
    
    // Handle preflight requests
    if (req.method === 'OPTIONS') {
        res.writeHead(200);
        res.end();
        return;
    }
    
    // Build the target URL
    const targetUrl = BASE_URL + parsedUrl.pathname + (parsedUrl.search || '');
    
    console.log(`[API] ${req.method} ${targetUrl}`);
    
    // Prepare request options
    const options = {
        method: req.method,
        headers: {
            'x-api-key': API_KEY,
            'Content-Type': 'application/json'
        }
    };
    
    // Make the request to the actual API
    const proxyReq = https.request(targetUrl, options, (proxyRes) => {
        // Forward status code
        res.writeHead(proxyRes.statusCode, {
            'Content-Type': proxyRes.headers['content-type'] || 'application/json',
            'Access-Control-Allow-Origin': '*'
        });
        
        // Forward response body
        proxyRes.pipe(res);
    });
    
    // Handle errors
    proxyReq.on('error', (error) => {
        console.error('Proxy error:', error.message);
        res.writeHead(500);
        res.end(JSON.stringify({ error: error.message }));
    });
    
    // Forward request body for POST/PUT/DELETE
    if (req.method !== 'GET' && req.method !== 'HEAD') {
        req.pipe(proxyReq);
    } else {
        proxyReq.end();
    }
}

const server = http.createServer((req, res) => {
    const parsedUrl = url.parse(req.url, true);
    
    // Proxy API requests
    if (parsedUrl.pathname.startsWith('/api/')) {
        proxyApiRequest(req, res, parsedUrl);
        return;
    }
    
    // Serve static files
    let filePath = parsedUrl.pathname;
    
    // Default to index.html for root
    if (filePath === '/') {
        filePath = '/index.html';
    }
    
    // Build absolute file path
    const absolutePath = path.join(__dirname, filePath);
    
    // Security check: prevent directory traversal
    if (!absolutePath.startsWith(__dirname)) {
        res.writeHead(403);
        res.end('Forbidden');
        return;
    }
    
    console.log(`[FILE] ${filePath}`);
    serveStaticFile(absolutePath, res);
});

server.listen(PORT, () => {
    console.log(`╔════════════════════════════════════════════════════╗`);
    console.log(`║  Battleship Visualizer Server                     ║`);
    console.log(`╠════════════════════════════════════════════════════╣`);
    console.log(`║  Server running on: http://localhost:${PORT}         ║`);
    console.log(`║  API forwarding to: ${BASE_URL}  ║`);
    console.log(`╚════════════════════════════════════════════════════╝`);
    console.log('');
    console.log('📂 Serving static files from:', __dirname);
    console.log('🔗 Open in browser: http://localhost:3000');
    console.log('🔄 API requests to /api/* will be proxied');
    console.log('');
    console.log('Press Ctrl+C to stop the server');
    console.log('');
});
