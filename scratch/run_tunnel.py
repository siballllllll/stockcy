import os
import sys
import time
import ssl
from dotenv import load_dotenv

# SSL 인증 우회 추가 (Python 3.14+ 및 특정 환경의 pyngrok 바이너리 다운로드 SSL EOF 에러 방지)
ssl._create_default_https_context = ssl._create_unverified_context

# .env 파일 로드
load_dotenv()

# pyngrok 설치 여부 확인 및 자동 설치
try:
    from pyngrok import ngrok, conf
except ImportError:
    print("Installing 'pyngrok' package automatically...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyngrok"])
    from pyngrok import ngrok, conf

# Ngrok Auth Token 설정 권장 안내
# Ngrok은 최근 무료 계정이라도 Auth Token을 등록해야 터널을 열어줍니다.
auth_token = os.getenv("NGROK_AUTHTOKEN", "")
if auth_token:
    ngrok.set_auth_token(auth_token)
    print("Ngrok Authtoken configured from .env")
else:
    print("[경고] NGROK_AUTHTOKEN이 환경 변수에 없습니다.")
    print("Ngrok은 Auth Token을 설정해야 외부 터널이 열립니다.")
    print("구글이나 이메일로 ngrok.com에 무료 회원가입 후 대시보드에서 Authtoken을 얻을 수 있습니다.")
    print("토큰 설정 방법: 'python -m pyngrok authtoken <YOUR_TOKEN>'을 실행하거나 .env 파일에 NGROK_AUTHTOKEN=<TOKEN> 을 기록하세요.\n")

print("Starting ngrok tunnel for Unified Proxy Gateway (Port 3500)...")
try:
    # 3500 포트용 터널 생성 (프론트엔드 + 백엔드 통합 우회 프록시)
    public_url = ngrok.connect("127.0.0.1:3500", bind_tls=True)
    print("\n" + "="*60)
    print(f"[성공] 스톡시 외부 원격 주소가 생성되었습니다.")
    print(f"[주소] 외부 접속 주소: {public_url}")
    print(f"핸드폰이나 다른 기기의 브라우저 주소창에 위 주소를 치고 접속하세요!")
    print("="*60 + "\n")
    
    # 터널 유지
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\nShutting down ngrok tunnel...")
    ngrok.kill()
except Exception as e:
    print(f"\n[실패] 터널 기동 실패: {e}")
