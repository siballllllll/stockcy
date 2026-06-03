const http = require('http');
const net = require('net');

const FRONTEND_TARGET = 'http://127.0.0.1:3000';
const BACKEND_TARGET = 'http://127.0.0.1:8000';

const server = http.createServer((req, res) => {
  const isBackend = req.url.startsWith('/backend') || req.url.startsWith('/api');
  const target = isBackend ? BACKEND_TARGET : FRONTEND_TARGET;
  
  // 백엔드 요청인 경우 /backend 접두사를 제거하여 FastAPI 엔드포인트와 매핑
  let path = req.url;
  if (isBackend && path.startsWith('/backend')) {
    path = path.substring(8);
    if (!path.startsWith('/')) path = '/' + path;
  }

  const parsedUrl = new URL(target + path);
  
  const proxyReq = http.request({
    hostname: parsedUrl.hostname,
    port: parsedUrl.port,
    path: parsedUrl.pathname + parsedUrl.search,
    method: req.method,
    headers: {
      ...req.headers,
      host: parsedUrl.host,
    }
  }, (proxyRes) => {
    res.writeHead(proxyRes.statusCode, proxyRes.headers);
    proxyRes.pipe(res, { end: true });
  });

  proxyReq.on('error', (err) => {
    console.error('Proxy request error:', err);
    res.writeHead(502);
    res.end('Bad Gateway');
  });

  req.pipe(proxyReq, { end: true });
});

// Next.js Turbopack HMR 웹소켓 업그레이드 요청 시 RAW TCP 파이핑 터널링 (WS MASK 에러 원천 해결)
server.on('upgrade', (req, socket, head) => {
  // 웹소켓(HMR)은 100% 프론트엔드(3000포트)로 TCP 다이렉트 터널 연결
  const proxySocket = net.connect(3000, '127.0.0.1', () => {
    // 101 Switching Protocols 핸드셰이크를 포함하여, 수신한 웹소켓 업그레이드 HTTP 헤더 복원하여 전송
    let rawRequest = `${req.method} ${req.url} HTTP/${req.httpVersion}\r\n`;
    for (const [key, val] of Object.entries(req.headers)) {
      rawRequest += `${key}: ${val}\r\n`;
    }
    rawRequest += '\r\n';
    
    proxySocket.write(rawRequest);
    if (head && head.length > 0) {
      proxySocket.write(head);
    }
    
    // RAW TCP 데이터 스트림 수준에서 다이렉트 파이핑 결합 (프로토콜 미간섭 완벽 구조)
    proxySocket.pipe(socket);
    socket.pipe(proxySocket);
  });

  proxySocket.on('error', (err) => {
    console.error('WS TCP Tunnel connection error:', err);
    socket.end();
  });
});

server.listen(3500, '0.0.0.0', () => {
  console.log('Stockcy Unified Proxy Gateway listening on port 3500');
});
