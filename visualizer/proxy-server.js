const http = require('http');
const https = require('https');
const url = require('url');

// Allow overriding configuration from environment variables.
const BASE_URL = process.env.BASE_URL || 'https://battle.piratesonline.us';
const API_KEY = process.env.API_KEY || 'Harcivizibusz';
const PORT = parseInt(process.env.PORT || '3000', 10);

const server = http.createServer((req, res) => {
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
    
    // Parse the URL
    const parsedUrl = url.parse(req.url, true);
    
    // Only proxy API requests
    if (!parsedUrl.pathname.startsWith('/api/')) {
        res.writeHead(404);
        res.end('Not found');
        return;
    }
    
    // Build the target URL
    const targetUrl = BASE_URL + parsedUrl.pathname + (parsedUrl.search || '');
    
    console.log(`[${new Date().toISOString()}] ${req.method} ${targetUrl}`);
    
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
});

server.listen(PORT, () => {
    console.log(`╔════════════════════════════════════════════════════╗`);
    console.log(`║  Battleship API Proxy Server                      ║`);
    console.log(`╠════════════════════════════════════════════════════╣`);
    console.log(`║  Proxy running on: http://localhost:${PORT}         ║`);
    console.log(`║  Forwarding to:    ${BASE_URL}  ║`);
    console.log(`║  API Key:          ${API_KEY}                ║`);
    console.log(`╚════════════════════════════════════════════════════╝`);
    console.log('');
    console.log('Ready to proxy requests...');
});
