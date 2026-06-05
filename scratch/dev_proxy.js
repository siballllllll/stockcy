const http = require('http');
const net = require('net');

const FRONTEND_TARGET = 'http://127.0.0.1:3000';
const BACKEND_TARGET = 'http://127.0.0.1:8000';

// 업스트림(특히 백엔드)이 --reload 로 잠깐 재시작될 때 연결이 거부되면
// 즉시 502를 내지 말고 짧게 기다렸다 재시도해 재시작 창(보통 2~5초)을 흡수한다.
const RETRYABLE = new Set(['ECONNREFUSED', 'ECONNRESET', 'ETIMEDOUT', 'EPIPE', 'EHOSTUNREACH']);
const MAX_RETRIES = 15;       // 약 15회
const RETRY_DELAY_MS = 400;   // × 400ms ≈ 최대 ~6초까지 대기

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

  // 요청 본문을 모아두면 업스트림 재시작 중 연결 실패 시 그대로 재전송(재시도)할 수 있다.
  // (이 앱의 요청 본문은 작은 JSON이라 버퍼링 부담 없음. 응답은 그대로 스트리밍 — SSE 정상)
  const bodyChunks = [];
  req.on('data', (c) => bodyChunks.push(c));
  req.on('end', () => {
    const body = Buffer.concat(bodyChunks);
    let attempt = 0;

    const tryProxy = () => {
      const proxyReq = http.request({
        hostname: parsedUrl.hostname,
        port: parsedUrl.port,
        path: parsedUrl.pathname + parsedUrl.search,
        method: req.method,
        headers: { ...req.headers, host: parsedUrl.host },
      }, (proxyRes) => {
        res.writeHead(proxyRes.statusCode, proxyRes.headers);
        proxyRes.pipe(res, { end: true });
      });

      proxyReq.on('error', (err) => {
        // 재시작 중(연결 거부 등) + 아직 응답 시작 전이면 잠깐 뒤 재시도
        if (RETRYABLE.has(err.code) && attempt < MAX_RETRIES && !res.headersSent) {
          attempt++;
          setTimeout(tryProxy, RETRY_DELAY_MS);
          return;
        }
        if (!res.headersSent) {
          res.writeHead(502, { 'Content-Type': 'text/plain; charset=utf-8' });
          res.end('Bad Gateway (업스트림 재시작 중일 수 있어요. 잠시 후 새로고침)');
        }
      });

      if (body.length > 0) proxyReq.write(body);
      proxyReq.end();
    };

    tryProxy();
  });

  req.on('error', () => { if (!res.headersSent) { res.writeHead(400); res.end(); } });
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
  console.log('Stockcy Unified Proxy Gateway listening on port 3500 (retry-on-restart enabled)');
});
