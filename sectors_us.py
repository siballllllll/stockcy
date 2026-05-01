# 미국 주식 섹터 / 서브섹터 / 종목 데이터베이스
# exchange: NASDAQ | NYSE | AMEX

US_SECTOR_MAP = {
    "AI·반도체": {
        "AI 가속기·GPU": [
            {"name": "엔비디아",     "ticker": "NVDA",  "exchange": "NASDAQ"},
            {"name": "AMD",         "ticker": "AMD",   "exchange": "NASDAQ"},
            {"name": "브로드컴",     "ticker": "AVGO",  "exchange": "NASDAQ"},
            {"name": "마벨테크",     "ticker": "MRVL",  "exchange": "NASDAQ"},
        ],
        "AI 서버·인프라": [
            {"name": "슈퍼마이크로", "ticker": "SMCI",  "exchange": "NASDAQ"},
            {"name": "ARM홀딩스",   "ticker": "ARM",   "exchange": "NASDAQ"},
            {"name": "아스테라랩스", "ticker": "ALAB",  "exchange": "NASDAQ"},
            {"name": "인텔",        "ticker": "INTC",  "exchange": "NASDAQ"},
        ],
        "파운드리·EDA": [
            {"name": "TSMC",        "ticker": "TSM",   "exchange": "NYSE"},
            {"name": "시놉시스",    "ticker": "SNPS",  "exchange": "NASDAQ"},
            {"name": "케이던스",    "ticker": "CDNS",  "exchange": "NASDAQ"},
        ],
        "반도체 장비": [
            {"name": "어플라이드머티어리얼즈","ticker": "AMAT","exchange": "NASDAQ"},
            {"name": "램리서치",    "ticker": "LRCX",  "exchange": "NASDAQ"},
            {"name": "KLA",         "ticker": "KLAC",  "exchange": "NASDAQ"},
            {"name": "ASML",        "ticker": "ASML",  "exchange": "NASDAQ"},
        ],
        "AI 메모리": [
            {"name": "마이크론",    "ticker": "MU",    "exchange": "NASDAQ"},
            {"name": "웨스턴디지털","ticker": "WDC",   "exchange": "NASDAQ"},
        ],
    },
    "빅테크·AI소프트": {
        "AI 플랫폼·클라우드": [
            {"name": "마이크로소프트","ticker": "MSFT",  "exchange": "NASDAQ"},
            {"name": "알파벳(구글)", "ticker": "GOOGL", "exchange": "NASDAQ"},
            {"name": "아마존",      "ticker": "AMZN",  "exchange": "NASDAQ"},
            {"name": "메타",        "ticker": "META",  "exchange": "NASDAQ"},
        ],
        "소비자 AI·기기": [
            {"name": "애플",        "ticker": "AAPL",  "exchange": "NASDAQ"},
            {"name": "팔란티어",    "ticker": "PLTR",  "exchange": "NYSE"},
            {"name": "C3.ai",       "ticker": "AI",    "exchange": "NYSE"},
        ],
        "AI SaaS·엔터프라이즈": [
            {"name": "세일즈포스",  "ticker": "CRM",   "exchange": "NYSE"},
            {"name": "서비스나우",  "ticker": "NOW",   "exchange": "NYSE"},
            {"name": "스노우플레이크","ticker": "SNOW",  "exchange": "NYSE"},
            {"name": "유아이패스",  "ticker": "PATH",  "exchange": "NYSE"},
        ],
        "AI 음성·검색": [
            {"name": "사운드하운드","ticker": "SOUN",  "exchange": "NASDAQ"},
            {"name": "퍼플렉시티(미상장)","ticker": "GOOGL","exchange": "NASDAQ"},
            {"name": "오라클",      "ticker": "ORCL",  "exchange": "NYSE"},
        ],
    },
    "바이오·헬스케어": {
        "신약·GLP-1": [
            {"name": "일라이릴리",  "ticker": "LLY",   "exchange": "NYSE"},
            {"name": "노보노디스크","ticker": "NVO",   "exchange": "NYSE"},
            {"name": "화이자",      "ticker": "PFE",   "exchange": "NYSE"},
            {"name": "머크",        "ticker": "MRK",   "exchange": "NYSE"},
        ],
        "mRNA·백신": [
            {"name": "모더나",      "ticker": "MRNA",  "exchange": "NASDAQ"},
            {"name": "바이오엔텍",  "ticker": "BNTX",  "exchange": "NASDAQ"},
            {"name": "노바백스",    "ticker": "NVAX",  "exchange": "NASDAQ"},
        ],
        "바이오테크": [
            {"name": "길리어드",    "ticker": "GILD",  "exchange": "NASDAQ"},
            {"name": "암젠",        "ticker": "AMGN",  "exchange": "NASDAQ"},
            {"name": "버텍스",      "ticker": "VRTX",  "exchange": "NASDAQ"},
            {"name": "리제네론",    "ticker": "REGN",  "exchange": "NASDAQ"},
        ],
        "의료기기·수술로봇": [
            {"name": "인튜이티브서지컬","ticker": "ISRG","exchange": "NASDAQ"},
            {"name": "애보트",      "ticker": "ABT",   "exchange": "NYSE"},
            {"name": "메드트로닉",  "ticker": "MDT",   "exchange": "NYSE"},
            {"name": "덱스콤",      "ticker": "DXCM",  "exchange": "NASDAQ"},
        ],
    },
    "방산·우주": {
        "전통 방산": [
            {"name": "록히드마틴",  "ticker": "LMT",   "exchange": "NYSE"},
            {"name": "레이시온",    "ticker": "RTX",   "exchange": "NYSE"},
            {"name": "노스롭그루먼","ticker": "NOC",   "exchange": "NYSE"},
            {"name": "제너럴다이내믹스","ticker": "GD", "exchange": "NYSE"},
        ],
        "우주·발사체": [
            {"name": "로켓랩",      "ticker": "RKLB",  "exchange": "NASDAQ"},
            {"name": "인튜이티브머신스","ticker": "LUNR","exchange": "NASDAQ"},
            {"name": "트랜스디지엄","ticker": "TDIG",  "exchange": "NYSE"},
        ],
        "드론·무인기": [
            {"name": "에어버스(ADR)","ticker": "EADSY","exchange": "NYSE"},
            {"name": "텍스트론",    "ticker": "TXT",   "exchange": "NYSE"},
            {"name": "AeroVironment","ticker": "AVAV", "exchange": "NASDAQ"},
        ],
        "사이버·전자전": [
            {"name": "L3해리스",    "ticker": "LHX",   "exchange": "NYSE"},
            {"name": "CACI인터내셔널","ticker": "CACI", "exchange": "NYSE"},
            {"name": "부즈앨런해밀턴","ticker": "BAH",  "exchange": "NYSE"},
        ],
    },
    "사이버보안": {
        "엔드포인트 보안": [
            {"name": "크라우드스트라이크","ticker": "CRWD","exchange": "NASDAQ"},
            {"name": "센티넬원",    "ticker": "S",     "exchange": "NYSE"},
            {"name": "팔로알토",    "ticker": "PANW",  "exchange": "NASDAQ"},
        ],
        "클라우드·제로트러스트": [
            {"name": "지스케일러",  "ticker": "ZS",    "exchange": "NASDAQ"},
            {"name": "포티넷",      "ticker": "FTNT",  "exchange": "NASDAQ"},
            {"name": "옥타",        "ticker": "OKTA",  "exchange": "NASDAQ"},
            {"name": "사이버아크",  "ticker": "CYBR",  "exchange": "NASDAQ"},
        ],
        "네트워크 보안": [
            {"name": "체크포인트",  "ticker": "CHKP",  "exchange": "NASDAQ"},
            {"name": "배럿파이어",  "ticker": "VRNS",  "exchange": "NASDAQ"},
            {"name": "테너블",      "ticker": "TENB",  "exchange": "NASDAQ"},
        ],
        "ID·인증 보안": [
            {"name": "베욘드트러스트","ticker": "BTRU",  "exchange": "NASDAQ"},
            {"name": "핑아이덴티티","ticker": "PING",  "exchange": "NYSE"},
            {"name": "퀄리스",      "ticker": "QLYS",  "exchange": "NASDAQ"},
        ],
    },
    "에너지·원자력": {
        "원자력·우라늄": [
            {"name": "카메코",      "ticker": "CCJ",   "exchange": "NYSE"},
            {"name": "컨스텔레이션에너지","ticker": "CEG","exchange": "NASDAQ"},
            {"name": "비스트라",    "ticker": "VST",   "exchange": "NYSE"},
            {"name": "NuScale",     "ticker": "SMR",   "exchange": "NYSE"},
        ],
        "천연가스·LNG": [
            {"name": "셰니어에너지","ticker": "LNG",   "exchange": "NYSE"},
            {"name": "EQT",         "ticker": "EQT",   "exchange": "NYSE"},
            {"name": "EQT미드스트림","ticker": "AM",    "exchange": "NYSE"},
        ],
        "재생에너지": [
            {"name": "인페이즈에너지","ticker": "ENPH", "exchange": "NASDAQ"},
            {"name": "퍼스트솔라",  "ticker": "FSLR",  "exchange": "NASDAQ"},
            {"name": "넥스트에라에너지","ticker": "NEE","exchange": "NYSE"},
            {"name": "솔라엣지",    "ticker": "SEDG",  "exchange": "NASDAQ"},
        ],
        "빅오일": [
            {"name": "엑슨모빌",    "ticker": "XOM",   "exchange": "NYSE"},
            {"name": "셰브론",      "ticker": "CVX",   "exchange": "NYSE"},
            {"name": "옥시덴탈",    "ticker": "OXY",   "exchange": "NYSE"},
        ],
    },
    "금융·핀테크": {
        "빅뱅크": [
            {"name": "JP모건",      "ticker": "JPM",   "exchange": "NYSE"},
            {"name": "뱅크오브아메리카","ticker": "BAC","exchange": "NYSE"},
            {"name": "골드만삭스",  "ticker": "GS",    "exchange": "NYSE"},
            {"name": "모건스탠리",  "ticker": "MS",    "exchange": "NYSE"},
        ],
        "핀테크·결제": [
            {"name": "페이팔",      "ticker": "PYPL",  "exchange": "NASDAQ"},
            {"name": "블록(스퀘어)","ticker": "SQ",    "exchange": "NYSE"},
            {"name": "어펌",        "ticker": "AFRM",  "exchange": "NASDAQ"},
            {"name": "소파이",      "ticker": "SOFI",  "exchange": "NASDAQ"},
        ],
        "암호화폐·블록체인": [
            {"name": "코인베이스",  "ticker": "COIN",  "exchange": "NASDAQ"},
            {"name": "마이크로스트래티지","ticker": "MSTR","exchange": "NASDAQ"},
            {"name": "로빈후드",    "ticker": "HOOD",  "exchange": "NASDAQ"},
        ],
        "자산운용·보험": [
            {"name": "버크셔해서웨이","ticker": "BRK-B","exchange": "NYSE"},
            {"name": "블랙록",      "ticker": "BLK",   "exchange": "NYSE"},
            {"name": "비자",        "ticker": "V",     "exchange": "NYSE"},
            {"name": "마스터카드",  "ticker": "MA",    "exchange": "NYSE"},
        ],
    },
    "EV·로봇": {
        "EV 완성차": [
            {"name": "테슬라",      "ticker": "TSLA",  "exchange": "NASDAQ"},
            {"name": "리비안",      "ticker": "RIVN",  "exchange": "NASDAQ"},
            {"name": "루시드",      "ticker": "LCID",  "exchange": "NASDAQ"},
            {"name": "니오",        "ticker": "NIO",   "exchange": "NYSE"},
        ],
        "EV 부품·충전": [
            {"name": "온세미컨덕터","ticker": "ON",    "exchange": "NASDAQ"},
            {"name": "차지포인트",  "ticker": "CHPT",  "exchange": "NYSE"},
            {"name": "블링크차징",  "ticker": "BLNK",  "exchange": "NASDAQ"},
        ],
        "인간형 로봇·AI 하드웨어": [
            {"name": "Figure(미상장 테슬라로대체)","ticker": "TSLA","exchange": "NASDAQ"},
            {"name": "엔비디아(Isaac ROS)","ticker": "NVDA","exchange": "NASDAQ"},
            {"name": "어질리티로보틱스(미상장-ABB)","ticker": "ABB","exchange": "NYSE"},
        ],
        "자율주행·라이다": [
            {"name": "모빌아이",    "ticker": "MBLY",  "exchange": "NASDAQ"},
            {"name": "루미나테크",  "ticker": "LAZR",  "exchange": "NASDAQ"},
            {"name": "우버",        "ticker": "UBER",  "exchange": "NYSE"},
            {"name": "리프트",      "ticker": "LYFT",  "exchange": "NASDAQ"},
        ],
    },
}
