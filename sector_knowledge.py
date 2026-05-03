# 증권사 스타일 섹터 테마 지식 베이스
# relevance: "core" = 직접 수혜, "mid" = 간접 수혜, "watch" = 관찰
# AI가 이 데이터를 참고해 오늘의 핫 섹터를 선별·보완합니다.

SECTOR_KNOWLEDGE = {

    # ─────────────────────────────────────────────
    # AI·반도체
    # ─────────────────────────────────────────────
    "HBM·AI메모리": {
        "desc": "AI 가속기용 고대역폭 메모리(HBM) 수혜 – 엔비디아 GPU 탑재",
        "search_keywords": ["HBM", "고대역폭메모리", "HBM4", "AI메모리", "온디바이스AI"],
        "kr": [
            {"name": "SK하이닉스",   "code": "000660", "suffix": ".KS", "r": "core"},
            {"name": "삼성전자",     "code": "005930", "suffix": ".KS", "r": "core"},
            {"name": "한미반도체",   "code": "042700", "suffix": ".KQ", "r": "core"},
            {"name": "HPSP",         "code": "403870", "suffix": ".KQ", "r": "mid"},
            {"name": "이오테크닉스", "code": "039030", "suffix": ".KQ", "r": "mid"},
            {"name": "솔브레인",     "code": "357780", "suffix": ".KQ", "r": "mid"},
        ],
        "us": [
            {"name": "마이크론",   "ticker": "MU",   "exchange": "NASDAQ"},
            {"name": "엔비디아",   "ticker": "NVDA", "exchange": "NASDAQ"},
        ],
    },

    "AI 서버·데이터센터": {
        "desc": "하이퍼스케일러 AI 인프라 투자 확대 – 서버·스위치·냉각 수혜",
        "search_keywords": ["AI서버", "데이터센터", "GPU서버", "하이퍼스케일러", "CSP투자"],
        "kr": [
            {"name": "삼성전자",     "code": "005930", "suffix": ".KS", "r": "core"},
            {"name": "SK하이닉스",   "code": "000660", "suffix": ".KS", "r": "core"},
            {"name": "이수페타시스", "code": "007660", "suffix": ".KS", "r": "core"},
            {"name": "심텍",         "code": "222800", "suffix": ".KQ", "r": "mid"},
            {"name": "코리아써키트", "code": "007810", "suffix": ".KS", "r": "mid"},
            {"name": "삼성전기",     "code": "009150", "suffix": ".KS", "r": "mid"},
        ],
        "us": [
            {"name": "엔비디아",       "ticker": "NVDA", "exchange": "NASDAQ"},
            {"name": "슈퍼마이크로",   "ticker": "SMCI", "exchange": "NASDAQ"},
            {"name": "마이크로소프트", "ticker": "MSFT", "exchange": "NASDAQ"},
        ],
    },

    "반도체 유리기판·첨단패키징": {
        "desc": "AI 가속기·HBM 성능 한계 극복 – 유리기판·CoWoS 패키징 확대",
        "search_keywords": ["유리기판", "CoWoS", "첨단패키징", "SLP", "ABF기판"],
        "kr": [
            {"name": "삼성전기",     "code": "009150", "suffix": ".KS", "r": "core"},
            {"name": "이수페타시스", "code": "007660", "suffix": ".KS", "r": "core"},
            {"name": "심텍",         "code": "222800", "suffix": ".KQ", "r": "core"},
            {"name": "코리아써키트", "code": "007810", "suffix": ".KS", "r": "mid"},
            {"name": "대덕전자",     "code": "353200", "suffix": ".KQ", "r": "mid"},
        ],
        "us": [
            {"name": "AMD",  "ticker": "AMD",  "exchange": "NASDAQ"},
            {"name": "TSMC", "ticker": "TSM",  "exchange": "NYSE"},
        ],
    },

    "반도체 소부장": {
        "desc": "반도체 소재·부품·장비 국산화 및 수출 확대",
        "search_keywords": ["소부장", "반도체장비", "반도체소재", "EUV", "건식세정"],
        "kr": [
            {"name": "원익IPS",       "code": "240810", "suffix": ".KQ", "r": "core"},
            {"name": "주성엔지니어링","code": "036930", "suffix": ".KQ", "r": "core"},
            {"name": "피에스케이",    "code": "319660", "suffix": ".KQ", "r": "core"},
            {"name": "유진테크",      "code": "084370", "suffix": ".KQ", "r": "core"},
            {"name": "솔브레인",      "code": "357780", "suffix": ".KQ", "r": "mid"},
            {"name": "동진쎄미켐",    "code": "005290", "suffix": ".KS", "r": "mid"},
            {"name": "원익머트리얼즈","code": "104830", "suffix": ".KQ", "r": "mid"},
        ],
        "us": [
            {"name": "어플라이드머티어리얼즈", "ticker": "AMAT", "exchange": "NASDAQ"},
            {"name": "ASML",                   "ticker": "ASML", "exchange": "NASDAQ"},
        ],
    },

    # ─────────────────────────────────────────────
    # AI 인프라·전력
    # ─────────────────────────────────────────────
    "AI 전력인프라·변압기": {
        "desc": "AI 데이터센터 전력 수요 폭증 – 변압기·차단기·전력기기 수혜",
        "search_keywords": ["AI전력", "변압기", "전력인프라", "전력기기", "그리드"],
        "kr": [
            {"name": "효성중공업",   "code": "298040", "suffix": ".KS", "r": "core"},
            {"name": "현대일렉트릭", "code": "267260", "suffix": ".KS", "r": "core"},
            {"name": "LS ELECTRIC",  "code": "010120", "suffix": ".KS", "r": "core"},
            {"name": "제룡전기",     "code": "033100", "suffix": ".KQ", "r": "core"},
            {"name": "일진전기",     "code": "103590", "suffix": ".KS", "r": "mid"},
            {"name": "대한전선",     "code": "001440", "suffix": ".KS", "r": "mid"},
        ],
        "us": [
            {"name": "이튼",       "ticker": "ETN",  "exchange": "NYSE"},
            {"name": "버티브",     "ticker": "VRT",  "exchange": "NYSE"},
            {"name": "GE버노바",   "ticker": "GEV",  "exchange": "NYSE"},
        ],
    },

    "ESS·에너지저장": {
        "desc": "재생에너지 확대 + AI 데이터센터 무정전 수요 → ESS 시장 급성장",
        "search_keywords": ["ESS", "에너지저장", "배터리저장시스템", "UPS", "전력저장"],
        "kr": [
            {"name": "삼성SDI",       "code": "006400", "suffix": ".KS", "r": "core"},
            {"name": "LG에너지솔루션","code": "373220", "suffix": ".KS", "r": "core"},
            {"name": "비나텍",        "code": "002070", "suffix": ".KQ", "r": "mid"},
            {"name": "에너테크인터내셔널","code": "016250", "suffix": ".KQ", "r": "mid"},
            {"name": "LS전선",        "code": "229640", "suffix": ".KQ", "r": "mid"},
        ],
        "us": [
            {"name": "테슬라",       "ticker": "TSLA", "exchange": "NASDAQ"},
            {"name": "인페이즈에너지","ticker": "ENPH", "exchange": "NASDAQ"},
        ],
    },

    "전력케이블·수출": {
        "desc": "해저케이블·초고압케이블 글로벌 수주 확대",
        "search_keywords": ["해저케이블", "초고압케이블", "전력케이블", "HVDC"],
        "kr": [
            {"name": "LS전선",    "code": "229640", "suffix": ".KQ", "r": "core"},
            {"name": "대한전선",  "code": "001440", "suffix": ".KS", "r": "core"},
            {"name": "가온전선",  "code": "000500", "suffix": ".KS", "r": "mid"},
            {"name": "일진전기",  "code": "103590", "suffix": ".KS", "r": "mid"},
        ],
        "us": [
            {"name": "넥상스(ADR)", "ticker": "NEXXY", "exchange": "NYSE"},
        ],
    },

    # ─────────────────────────────────────────────
    # 로봇·자동화
    # ─────────────────────────────────────────────
    "국내 로봇·자동화": {
        "desc": "인건비 상승 + AI 융합으로 협동로봇·물류로봇 수요 급증",
        "search_keywords": ["협동로봇", "인간형로봇", "로봇", "자동화", "AMR", "물류로봇"],
        "kr": [
            {"name": "두산로보틱스",   "code": "454910", "suffix": ".KS", "r": "core"},
            {"name": "레인보우로보틱스","code": "277810", "suffix": ".KQ", "r": "core"},
            {"name": "현대로보틱스",   "code": "267270", "suffix": ".KS", "r": "core"},
            {"name": "티로보틱스",     "code": "117730", "suffix": ".KQ", "r": "mid"},
            {"name": "에스피지",       "code": "058610", "suffix": ".KQ", "r": "mid"},
            {"name": "하이젠알앤엠",   "code": "106080", "suffix": ".KQ", "r": "watch"},
        ],
        "us": [
            {"name": "테슬라(옵티머스)", "ticker": "TSLA", "exchange": "NASDAQ"},
            {"name": "ABB",              "ticker": "ABB",  "exchange": "NYSE"},
        ],
    },

    "스마트팩토리·자동화 장비": {
        "desc": "제조업 디지털전환 – FA장비·PLC·산업용 소프트웨어",
        "search_keywords": ["스마트팩토리", "FA장비", "PLC", "산업용AI", "공장자동화"],
        "kr": [
            {"name": "LS ELECTRIC", "code": "010120", "suffix": ".KS", "r": "core"},
            {"name": "현대위아",    "code": "011210", "suffix": ".KS", "r": "mid"},
            {"name": "에스에프에이","code": "056190", "suffix": ".KQ", "r": "mid"},
            {"name": "고영테크놀러지","code": "098460", "suffix": ".KQ", "r": "mid"},
        ],
        "us": [
            {"name": "로크웰오토메이션", "ticker": "ROK", "exchange": "NYSE"},
            {"name": "키엔스(ADR)",      "ticker": "KYCCF", "exchange": "NYSE"},
        ],
    },

    # ─────────────────────────────────────────────
    # 방산·우주
    # ─────────────────────────────────────────────
    "K-방산 수출": {
        "desc": "유럽·중동 국방 예산 확대 → K2전차·K9자주포·천궁 수출 수주",
        "search_keywords": ["방산수출", "K2전차", "K9자주포", "천궁", "방위산업"],
        "kr": [
            {"name": "한화에어로스페이스","code": "012450", "suffix": ".KS", "r": "core"},
            {"name": "현대로템",          "code": "064350", "suffix": ".KS", "r": "core"},
            {"name": "LIG넥스원",         "code": "079550", "suffix": ".KS", "r": "core"},
            {"name": "한국항공우주",      "code": "047810", "suffix": ".KS", "r": "core"},
            {"name": "한화시스템",        "code": "272210", "suffix": ".KS", "r": "mid"},
            {"name": "한화오션",          "code": "042660", "suffix": ".KS", "r": "mid"},
        ],
        "us": [
            {"name": "록히드마틴",   "ticker": "LMT", "exchange": "NYSE"},
            {"name": "레이시온",     "ticker": "RTX", "exchange": "NYSE"},
        ],
    },

    "우주·위성": {
        "desc": "저궤도 위성통신 + 우주 발사체 산업 확대",
        "search_keywords": ["저궤도위성", "LEO", "우주발사체", "위성통신", "우주산업"],
        "kr": [
            {"name": "한국항공우주","code": "047810", "suffix": ".KS", "r": "core"},
            {"name": "한화시스템",  "code": "272210", "suffix": ".KS", "r": "core"},
            {"name": "AP위성",      "code": "211270", "suffix": ".KQ", "r": "mid"},
            {"name": "쎄트렉아이",  "code": "099550", "suffix": ".KQ", "r": "mid"},
            {"name": "LIG넥스원",   "code": "079550", "suffix": ".KS", "r": "watch"},
        ],
        "us": [
            {"name": "로켓랩",             "ticker": "RKLB", "exchange": "NASDAQ"},
            {"name": "인튜이티브머신스",   "ticker": "LUNR", "exchange": "NASDAQ"},
        ],
    },

    # ─────────────────────────────────────────────
    # 조선·해운
    # ─────────────────────────────────────────────
    "조선·LNG선": {
        "desc": "LNG선·VLCC 수주 호황 지속 – 친환경 선박 전환 수혜",
        "search_keywords": ["조선", "LNG선", "VLCC", "선박수주", "친환경선박", "암모니아선"],
        "kr": [
            {"name": "HD한국조선해양","code": "009540", "suffix": ".KS", "r": "core"},
            {"name": "HD현대중공업",   "code": "329180", "suffix": ".KS", "r": "core"},
            {"name": "삼성중공업",     "code": "010140", "suffix": ".KS", "r": "core"},
            {"name": "한화오션",       "code": "042660", "suffix": ".KS", "r": "core"},
            {"name": "HD현대마린엔진", "code": "082740", "suffix": ".KS", "r": "mid"},
            {"name": "세진중공업",     "code": "075580", "suffix": ".KQ", "r": "mid"},
        ],
        "us": [
            {"name": "셰니어에너지", "ticker": "LNG", "exchange": "NYSE"},
        ],
    },

    "조선기자재": {
        "desc": "대형 조선소 수주 잔고 → 기자재 업체 동반 수혜",
        "search_keywords": ["조선기자재", "선박부품", "해양플랜트"],
        "kr": [
            {"name": "동성화인텍",  "code": "033500", "suffix": ".KQ", "r": "core"},
            {"name": "세진중공업",  "code": "075580", "suffix": ".KQ", "r": "core"},
            {"name": "TKG태광",     "code": "023160", "suffix": ".KQ", "r": "mid"},
            {"name": "화성밸브",    "code": "038530", "suffix": ".KQ", "r": "mid"},
            {"name": "STX엔진",     "code": "077970", "suffix": ".KQ", "r": "mid"},
        ],
        "us": [],
    },

    # ─────────────────────────────────────────────
    # 원자력·에너지
    # ─────────────────────────────────────────────
    "SMR·소형원전": {
        "desc": "AI 데이터센터 무탄소 전력 + 에너지 안보 → SMR 수요 부각",
        "search_keywords": ["SMR", "소형원전", "차세대원전", "원전수출", "AP1000"],
        "kr": [
            {"name": "두산에너빌리티","code": "034020", "suffix": ".KS", "r": "core"},
            {"name": "한전기술",      "code": "053590", "suffix": ".KS", "r": "core"},
            {"name": "한전KPS",       "code": "051600", "suffix": ".KS", "r": "mid"},
            {"name": "비에이치아이",  "code": "083650", "suffix": ".KQ", "r": "mid"},
            {"name": "우진",          "code": "105840", "suffix": ".KQ", "r": "mid"},
        ],
        "us": [
            {"name": "NuScale",          "ticker": "SMR",  "exchange": "NYSE"},
            {"name": "컨스텔레이션에너지","ticker": "CEG",  "exchange": "NASDAQ"},
        ],
    },

    "원전 기자재·운영": {
        "desc": "국내외 원전 신규 건설 + 기존 원전 정비 수혜",
        "search_keywords": ["원전기자재", "원전정비", "원전건설", "한울원전", "APR1400"],
        "kr": [
            {"name": "한국전력",     "code": "015760", "suffix": ".KS", "r": "core"},
            {"name": "한전KPS",      "code": "051600", "suffix": ".KS", "r": "core"},
            {"name": "두산에너빌리티","code": "034020", "suffix": ".KS", "r": "core"},
            {"name": "보성파워텍",   "code": "006910", "suffix": ".KQ", "r": "mid"},
            {"name": "우진",         "code": "105840", "suffix": ".KQ", "r": "mid"},
        ],
        "us": [
            {"name": "비스트라", "ticker": "VST", "exchange": "NYSE"},
        ],
    },

    # ─────────────────────────────────────────────
    # 2차전지
    # ─────────────────────────────────────────────
    "2차전지 소재·장비": {
        "desc": "EV 수요 회복 기대 + 북미 IRA 보조금 수혜 소재·장비주",
        "search_keywords": ["2차전지", "양극재", "음극재", "전해질", "배터리소재"],
        "kr": [
            {"name": "에코프로비엠",  "code": "247540", "suffix": ".KQ", "r": "core"},
            {"name": "포스코퓨처엠",  "code": "003670", "suffix": ".KS", "r": "core"},
            {"name": "엘앤에프",      "code": "066970", "suffix": ".KQ", "r": "core"},
            {"name": "솔브레인홀딩스","code": "036830", "suffix": ".KQ", "r": "mid"},
            {"name": "SK아이이테크", "code": "361610", "suffix": ".KS", "r": "mid"},
            {"name": "대주전자재료",  "code": "078600", "suffix": ".KQ", "r": "mid"},
        ],
        "us": [
            {"name": "알버말",   "ticker": "ALB",  "exchange": "NYSE"},
            {"name": "리튬아메리카스","ticker": "LAC", "exchange": "NYSE"},
        ],
    },

    # ─────────────────────────────────────────────
    # 바이오·헬스케어
    # ─────────────────────────────────────────────
    "바이오 ADC·항체신약": {
        "desc": "ADC(항체-약물 접합체) 기술 수출 + 글로벌 임상 모멘텀",
        "search_keywords": ["ADC", "항체신약", "바이오시밀러", "임상", "FDA승인"],
        "kr": [
            {"name": "한미약품",     "code": "128940", "suffix": ".KS", "r": "core"},
            {"name": "유한양행",     "code": "000100", "suffix": ".KS", "r": "core"},
            {"name": "HLB",          "code": "028300", "suffix": ".KQ", "r": "core"},
            {"name": "레고켐바이오", "code": "141080", "suffix": ".KQ", "r": "core"},
            {"name": "셀트리온",     "code": "068270", "suffix": ".KS", "r": "mid"},
            {"name": "에스티팜",     "code": "237690", "suffix": ".KQ", "r": "mid"},
        ],
        "us": [
            {"name": "일라이릴리",  "ticker": "LLY",  "exchange": "NYSE"},
            {"name": "아스트라제네카","ticker": "AZN", "exchange": "NASDAQ"},
        ],
    },

    "CMO·바이오위탁생산": {
        "desc": "글로벌 바이오의약품 CMO 수요 증가 – 삼성바이오 등 수혜",
        "search_keywords": ["CMO", "CDMO", "위탁생산", "바이오의약품", "mRNA"],
        "kr": [
            {"name": "삼성바이오로직스","code": "207940", "suffix": ".KS", "r": "core"},
            {"name": "에스티팜",        "code": "237690", "suffix": ".KQ", "r": "mid"},
            {"name": "바이넥스",        "code": "053030", "suffix": ".KQ", "r": "mid"},
        ],
        "us": [
            {"name": "론자그룹(ADR)", "ticker": "LZAGY", "exchange": "NYSE"},
        ],
    },

    # ─────────────────────────────────────────────
    # K-콘텐츠·소비
    # ─────────────────────────────────────────────
    "K-뷰티 ODM": {
        "desc": "미국·유럽·동남아 K-뷰티 수출 급증 – ODM 제조사 최대 수혜",
        "search_keywords": ["K뷰티", "K-뷰티", "ODM", "화장품수출", "인디뷰티"],
        "kr": [
            {"name": "코스맥스",       "code": "192820", "suffix": ".KS", "r": "core"},
            {"name": "한국콜마",       "code": "161890", "suffix": ".KS", "r": "core"},
            {"name": "씨앤씨인터내셔널","code": "352480", "suffix": ".KQ", "r": "core"},
            {"name": "코스메카코리아", "code": "241710", "suffix": ".KQ", "r": "core"},
            {"name": "에이피알",       "code": "032120", "suffix": ".KQ", "r": "mid"},
            {"name": "클리오",         "code": "237880", "suffix": ".KQ", "r": "mid"},
        ],
        "us": [],
    },

    "엔터·IP 수출": {
        "desc": "K-팝·K-드라마 글로벌 팬덤 + IP 수익화 확대",
        "search_keywords": ["K팝", "K드라마", "엔터", "IP수익화", "웹툰"],
        "kr": [
            {"name": "HYBE",           "code": "352820", "suffix": ".KS", "r": "core"},
            {"name": "SM엔터테인먼트", "code": "041510", "suffix": ".KQ", "r": "core"},
            {"name": "JYP Ent.",        "code": "035900", "suffix": ".KQ", "r": "core"},
            {"name": "YG엔터테인먼트", "code": "122870", "suffix": ".KQ", "r": "core"},
            {"name": "CJ ENM",          "code": "035760", "suffix": ".KQ", "r": "mid"},
            {"name": "스튜디오드래곤", "code": "253450", "suffix": ".KQ", "r": "mid"},
        ],
        "us": [],
    },

    # ─────────────────────────────────────────────
    # 금융·밸류업
    # ─────────────────────────────────────────────
    "저PBR·밸류업": {
        "desc": "정부 코리아 디스카운트 해소 정책 – 은행·지주·보험 PBR 재평가",
        "search_keywords": ["밸류업", "PBR", "주주환원", "자사주", "배당확대", "코리아디스카운트"],
        "kr": [
            {"name": "KB금융",        "code": "105560", "suffix": ".KS", "r": "core"},
            {"name": "신한지주",      "code": "055550", "suffix": ".KS", "r": "core"},
            {"name": "하나금융지주",  "code": "086790", "suffix": ".KS", "r": "core"},
            {"name": "우리금융지주",  "code": "316140", "suffix": ".KS", "r": "core"},
            {"name": "삼성생명",      "code": "032830", "suffix": ".KS", "r": "mid"},
            {"name": "현대차",        "code": "005380", "suffix": ".KS", "r": "mid"},
            {"name": "기아",          "code": "000270", "suffix": ".KS", "r": "mid"},
        ],
        "us": [],
    },

    "핀테크·인터넷은행": {
        "desc": "카카오뱅크·토스 등 인터넷은행 성장 + 간편결제 확대",
        "search_keywords": ["인터넷은행", "핀테크", "카카오뱅크", "토스", "간편결제"],
        "kr": [
            {"name": "카카오뱅크",  "code": "323410", "suffix": ".KS", "r": "core"},
            {"name": "카카오",      "code": "035720", "suffix": ".KS", "r": "mid"},
            {"name": "키움증권",    "code": "039490", "suffix": ".KQ", "r": "mid"},
            {"name": "한국금융지주","code": "071050", "suffix": ".KS", "r": "watch"},
        ],
        "us": [],
    },

    # ─────────────────────────────────────────────
    # 자동차·모빌리티
    # ─────────────────────────────────────────────
    "자율주행·전장부품": {
        "desc": "자율주행 Level 3+ 상용화 + 전기차 전장 수요 증가",
        "search_keywords": ["자율주행", "ADAS", "전장부품", "카메라모듈", "레이더"],
        "kr": [
            {"name": "현대모비스",  "code": "012330", "suffix": ".KS", "r": "core"},
            {"name": "HL만도",      "code": "204320", "suffix": ".KS", "r": "core"},
            {"name": "현대위아",    "code": "011210", "suffix": ".KS", "r": "mid"},
            {"name": "모비스",      "code": "012330", "suffix": ".KS", "r": "mid"},
        ],
        "us": [
            {"name": "모빌아이",    "ticker": "MBLY", "exchange": "NASDAQ"},
            {"name": "온세미컨덕터","ticker": "ON",   "exchange": "NASDAQ"},
        ],
    },

    "완성차·EV": {
        "desc": "HEV 판매 호조 + 전기차 신모델 출시 모멘텀",
        "search_keywords": ["현대차", "기아", "EV", "하이브리드", "수소차"],
        "kr": [
            {"name": "현대차", "code": "005380", "suffix": ".KS", "r": "core"},
            {"name": "기아",   "code": "000270", "suffix": ".KS", "r": "core"},
        ],
        "us": [
            {"name": "테슬라", "ticker": "TSLA", "exchange": "NASDAQ"},
        ],
    },

    # ─────────────────────────────────────────────
    # 디스플레이·소재
    # ─────────────────────────────────────────────
    "차세대 디스플레이 OLED": {
        "desc": "IT용 OLED 확대 + 차량용 디스플레이 성장",
        "search_keywords": ["OLED", "폴더블", "차량용디스플레이", "WOLED", "QLED"],
        "kr": [
            {"name": "LG디스플레이", "code": "034220", "suffix": ".KS", "r": "core"},
            {"name": "삼성전자",     "code": "005930", "suffix": ".KS", "r": "mid"},
            {"name": "덕산네오룩스", "code": "213420", "suffix": ".KQ", "r": "mid"},
            {"name": "솔루스첨단소재","code": "336370", "suffix": ".KQ", "r": "mid"},
        ],
        "us": [
            {"name": "애플", "ticker": "AAPL", "exchange": "NASDAQ"},
        ],
    },

    # ─────────────────────────────────────────────
    # 헬스케어
    # ─────────────────────────────────────────────
    "디지털헬스케어": {
        "desc": "AI 진단·원격의료·웨어러블 헬스 디바이스 성장",
        "search_keywords": ["디지털헬스", "원격의료", "AI진단", "웨어러블", "의료AI"],
        "kr": [
            {"name": "인바디",      "code": "041830", "suffix": ".KQ", "r": "core"},
            {"name": "씨젠",        "code": "096530", "suffix": ".KQ", "r": "mid"},
            {"name": "오스템임플란트","code": "048260", "suffix": ".KQ", "r": "mid"},
            {"name": "바텍",        "code": "043150", "suffix": ".KQ", "r": "mid"},
        ],
        "us": [
            {"name": "인튜이티브서지컬", "ticker": "ISRG", "exchange": "NASDAQ"},
            {"name": "덱스콤",           "ticker": "DXCM", "exchange": "NASDAQ"},
        ],
    },

    # ─────────────────────────────────────────────
    # 소재·화학
    # ─────────────────────────────────────────────
    "구리·희소금속": {
        "desc": "AI 인프라·EV·재생에너지 수요 급증 → 구리·리튬 가격 상승",
        "search_keywords": ["구리", "동", "희소금속", "리튬", "니켈", "코발트"],
        "kr": [
            {"name": "고려아연",  "code": "010130", "suffix": ".KS", "r": "core"},
            {"name": "풍산",      "code": "103140", "suffix": ".KS", "r": "core"},
            {"name": "POSCO홀딩스","code": "005490", "suffix": ".KS", "r": "mid"},
        ],
        "us": [
            {"name": "프리포트맥모란", "ticker": "FCX", "exchange": "NYSE"},
        ],
    },

    "수소에너지": {
        "desc": "청정수소 정책 + 연료전지 상용화 확대",
        "search_keywords": ["수소", "연료전지", "그린수소", "수전해", "FCEV"],
        "kr": [
            {"name": "두산퓨얼셀",  "code": "336260", "suffix": ".KQ", "r": "core"},
            {"name": "현대차",      "code": "005380", "suffix": ".KS", "r": "mid"},
            {"name": "일진하이솔루스","code": "271940", "suffix": ".KQ", "r": "mid"},
            {"name": "에이치투",    "code": "317850", "suffix": ".KQ", "r": "watch"},
        ],
        "us": [
            {"name": "플러그파워", "ticker": "PLUG", "exchange": "NASDAQ"},
        ],
    },

    # ─────────────────────────────────────────────
    # 유통·소비
    # ─────────────────────────────────────────────
    "이커머스·리오프닝": {
        "desc": "소비 회복 + 이커머스 시장 재성장 모멘텀",
        "search_keywords": ["이커머스", "온라인쇼핑", "소비회복", "리오프닝", "쿠팡"],
        "kr": [
            {"name": "이마트",   "code": "139480", "suffix": ".KS", "r": "core"},
            {"name": "롯데쇼핑", "code": "023530", "suffix": ".KS", "r": "mid"},
            {"name": "GS리테일", "code": "007070", "suffix": ".KS", "r": "mid"},
            {"name": "BGF리테일","code": "027410", "suffix": ".KS", "r": "mid"},
        ],
        "us": [
            {"name": "쿠팡", "ticker": "CPNG", "exchange": "NYSE"},
        ],
    },

    "항공·여행": {
        "desc": "국제선 수요 회복 + 여름 성수기 효과",
        "search_keywords": ["항공", "LCC", "여행", "국제선", "관광"],
        "kr": [
            {"name": "대한항공",   "code": "003490", "suffix": ".KS", "r": "core"},
            {"name": "진에어",     "code": "272450", "suffix": ".KS", "r": "core"},
            {"name": "제주항공",   "code": "089590", "suffix": ".KQ", "r": "mid"},
            {"name": "호텔신라",   "code": "008770", "suffix": ".KS", "r": "mid"},
            {"name": "하나투어",   "code": "039130", "suffix": ".KQ", "r": "mid"},
        ],
        "us": [
            {"name": "유나이티드항공", "ticker": "UAL", "exchange": "NASDAQ"},
        ],
    },

    "게임 신작 모멘텀": {
        "desc": "블록버스터 신작 출시 + 콘솔·PC·모바일 동시 런칭",
        "search_keywords": ["게임신작", "신작출시", "모바일게임", "콘솔게임", "PC게임"],
        "kr": [
            {"name": "크래프톤",   "code": "259960", "suffix": ".KS", "r": "core"},
            {"name": "엔씨소프트", "code": "036570", "suffix": ".KS", "r": "mid"},
            {"name": "넷마블",     "code": "251270", "suffix": ".KS", "r": "mid"},
            {"name": "카카오게임즈","code": "293490", "suffix": ".KQ", "r": "mid"},
            {"name": "펄어비스",   "code": "263750", "suffix": ".KQ", "r": "watch"},
        ],
        "us": [
            {"name": "마이크로소프트(Xbox)", "ticker": "MSFT", "exchange": "NASDAQ"},
            {"name": "로블록스",             "ticker": "RBLX", "exchange": "NYSE"},
        ],
    },
}
