import tomllib
import os
from google import genai

# secrets.toml 파일 읽기
try:
    with open(".streamlit/secrets.toml", "rb") as f:
        config = tomllib.load(f)
        api_key = config["gemini"]["api_key"]
except Exception as e:
    print(f"설정 파일을 읽을 수 없습니다: {e}")
    exit()

client = genai.Client(api_key=api_key)

print("--- 실제 콘텐츠 생성 테스트 시작 ---")
try:
    response = client.models.generate_content(
        model="gemini-1.5-flash",
        contents="안녕? 너는 누구니?"
    )
    print(f"생성 결과: {response.text}")
except Exception as e:
    print(f"콘텐츠 생성 중 오류 발생: {e}")

print("\n--- 전체 모델 목록 확인 ---")
try:
    for m in client.models.list():
        print(f"모델명: {m.name} | 지원메서드: {getattr(m, 'supported_methods', 'N/A')}")
except Exception as e:
    print(f"목록 조회 중 오류 발생: {e}")