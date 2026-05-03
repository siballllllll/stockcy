# 국내 주식 섹터 / 서브섹터 / 종목 데이터베이스
# suffix: .KS = KOSPI, .KQ = KOSDAQ

KR_SECTOR_MAP = {
    "반도체": {
        "반도체 공정": [
            {"name": "삼성전자",     "code": "005930", "suffix": ".KS"},
            {"name": "SK하이닉스",   "code": "000660", "suffix": ".KS"},
            {"name": "DB하이텍",     "code": "000990", "suffix": ".KS"},
        ],
        "HBM·메모리": [
            {"name": "SK하이닉스",   "code": "000660", "suffix": ".KS"},
            {"name": "한미반도체",   "code": "042700", "suffix": ".KQ"},
            {"name": "HPSP",        "code": "403870", "suffix": ".KQ"},
            {"name": "이오테크닉스", "code": "039030", "suffix": ".KQ"},
        ],
        "유리기판": [
            {"name": "삼성전기",     "code": "009150", "suffix": ".KS"},
            {"name": "이수페타시스", "code": "007660", "suffix": ".KS"},
            {"name": "심텍",        "code": "222800", "suffix": ".KQ"},
            {"name": "코리아써키트", "code": "007810", "suffix": ".KS"},
        ],
        "반도체 소재": [
            {"name": "솔브레인",     "code": "357780", "suffix": ".KQ"},
            {"name": "동진쎄미켐",   "code": "005290", "suffix": ".KS"},
            {"name": "한솔케미칼",   "code": "014680", "suffix": ".KS"},
            {"name": "원익머트리얼즈","code": "104830", "suffix": ".KQ"},
        ],
        "반도체 장비": [
            {"name": "원익IPS",      "code": "240810", "suffix": ".KQ"},
            {"name": "주성엔지니어링","code": "036930", "suffix": ".KQ"},
            {"name": "피에스케이",   "code": "319660", "suffix": ".KQ"},
            {"name": "유진테크",     "code": "084370", "suffix": ".KQ"},
        ],
    },
    "2차전지": {
        "배터리 셀": [
            {"name": "LG에너지솔루션","code": "373220", "suffix": ".KS"},
            {"name": "삼성SDI",      "code": "006400", "suffix": ".KS"},
            {"name": "SK이노베이션", "code": "096770", "suffix": ".KS"},
        ],
        "양극재": [
            {"name": "에코프로비엠",  "code": "247540", "suffix": ".KQ"},
            {"name": "포스코퓨처엠",  "code": "003670", "suffix": ".KS"},
            {"name": "엘앤에프",     "code": "066970", "suffix": ".KQ"},
            {"name": "코스모신소재",  "code": "005070", "suffix": ".KS"},
        ],
        "음극재": [
            {"name": "포스코홀딩스",  "code": "005490", "suffix": ".KS"},
            {"name": "대주전자재료",  "code": "078600", "suffix": ".KQ"},
            {"name": "일진머티리얼즈","code": "020150", "suffix": ".KS"},
        ],
        "전해질·분리막": [
            {"name": "솔브레인홀딩스","code": "036830", "suffix": ".KQ"},
            {"name": "SK아이이테크", "code": "361610", "suffix": ".KS"},
            {"name": "더블유씨피",   "code": "393890", "suffix": ".KQ"},
        ],
    },
    "바이오·제약": {
        "신약 개발": [
            {"name": "셀트리온",     "code": "068270", "suffix": ".KS"},
            {"name": "유한양행",     "code": "000100", "suffix": ".KS"},
            {"name": "한미약품",     "code": "128940", "suffix": ".KS"},
            {"name": "HLB",         "code": "028300", "suffix": ".KQ"},
        ],
        "의료기기": [
            {"name": "오스템임플란트","code": "048260", "suffix": ".KQ"},
            {"name": "바텍",        "code": "043150", "suffix": ".KQ"},
            {"name": "인바디",      "code": "041830", "suffix": ".KQ"},
        ],
        "CMO 위탁생산": [
            {"name": "삼성바이오로직스","code": "207940", "suffix": ".KS"},
            {"name": "에스티팜",     "code": "237690", "suffix": ".KQ"},
            {"name": "바이넥스",     "code": "053030", "suffix": ".KQ"},
        ],
        "진단·헬스케어": [
            {"name": "씨젠",        "code": "096530", "suffix": ".KQ"},
            {"name": "레고켐바이오", "code": "141080", "suffix": ".KQ"},
            {"name": "오리온홀딩스", "code": "001800", "suffix": ".KS"},
        ],
    },
    "AI·로봇": {
        "AI 플랫폼": [
            {"name": "NAVER",       "code": "035420", "suffix": ".KS"},
            {"name": "카카오",      "code": "035720", "suffix": ".KS"},
            {"name": "크래프톤",    "code": "259960", "suffix": ".KS"},
        ],
        "AI 반도체": [
            {"name": "리노공업",     "code": "058470", "suffix": ".KQ"},
            {"name": "오픈엣지테크", "code": "394730", "suffix": ".KQ"},
            {"name": "파두",        "code": "440110", "suffix": ".KQ"},
        ],
        "로봇": [
            {"name": "두산로보틱스",  "code": "454910", "suffix": ".KS"},
            {"name": "레인보우로보틱스","code": "277810", "suffix": ".KQ"},
            {"name": "현대로보틱스",  "code": "267270", "suffix": ".KS"},
            {"name": "티로보틱스",   "code": "117730", "suffix": ".KQ"},
        ],
        "자율주행·전장": [
            {"name": "현대모비스",   "code": "012330", "suffix": ".KS"},
            {"name": "HL만도",      "code": "204320", "suffix": ".KS"},
        ],
    },
    "방산": {
        "육상무기·장갑차": [
            {"name": "한화에어로스페이스","code": "012450", "suffix": ".KS"},
            {"name": "현대로템",     "code": "064350", "suffix": ".KS"},
            {"name": "LIG넥스원",    "code": "079550", "suffix": ".KS"},
        ],
        "항공·우주": [
            {"name": "한국항공우주", "code": "047810", "suffix": ".KS"},
            {"name": "한화시스템",   "code": "272210", "suffix": ".KS"},
            {"name": "AP위성",      "code": "211270", "suffix": ".KQ"},
            {"name": "쎄트렉아이",  "code": "099550", "suffix": ".KQ"},
        ],
        "함정·레이더": [
            {"name": "한화오션",     "code": "042660", "suffix": ".KS"},
            {"name": "빅텍",        "code": "065450", "suffix": ".KQ"},
            {"name": "스페코",      "code": "013810", "suffix": ".KQ"},
        ],
    },
    "조선": {
        "대형 조선소": [
            {"name": "HD한국조선해양","code": "009540", "suffix": ".KS"},
            {"name": "삼성중공업",   "code": "010140", "suffix": ".KS"},
            {"name": "한화오션",     "code": "042660", "suffix": ".KS"},
        ],
        "LNG선·특수선": [
            {"name": "HD현대중공업", "code": "329180", "suffix": ".KS"},
            {"name": "HD현대마린엔진","code": "082740", "suffix": ".KS"},
            {"name": "STX엔진",     "code": "077970", "suffix": ".KQ"},
        ],
        "기자재·부품": [
            {"name": "동성화인텍",   "code": "033500", "suffix": ".KQ"},
            {"name": "세진중공업",   "code": "075580", "suffix": ".KQ"},
            {"name": "TKG태광",     "code": "023160", "suffix": ".KQ"},
            {"name": "화성밸브",     "code": "038530", "suffix": ".KQ"},
        ],
        "해운": [
            {"name": "HMM",         "code": "011200", "suffix": ".KS"},
            {"name": "팬오션",      "code": "028670", "suffix": ".KS"},
            {"name": "대한해운",     "code": "005880", "suffix": ".KS"},
        ],
    },
    "자동차·전장": {
        "완성차": [
            {"name": "현대차",       "code": "005380", "suffix": ".KS"},
            {"name": "기아",         "code": "000270", "suffix": ".KS"},
            {"name": "쌍용차",       "code": "003620", "suffix": ".KS"},
        ],
        "전장·부품": [
            {"name": "현대모비스",   "code": "012330", "suffix": ".KS"},
            {"name": "현대위아",     "code": "011210", "suffix": ".KS"},
            {"name": "한온시스템",   "code": "018880", "suffix": ".KS"},
            {"name": "HL만도",      "code": "204320", "suffix": ".KS"},
        ],
        "타이어": [
            {"name": "한국타이어앤테크놀로지","code": "161390", "suffix": ".KS"},
            {"name": "금호타이어",   "code": "073240", "suffix": ".KS"},
            {"name": "넥센타이어",   "code": "002350", "suffix": ".KS"},
        ],
        "EV 충전·인프라": [
            {"name": "SK시그넷",     "code": "009180", "suffix": ".KQ"},
            {"name": "대영채비",     "code": "084670", "suffix": ".KQ"},
            {"name": "클린일렉스",   "code": "030520", "suffix": ".KQ"},
        ],
    },
    "원자력": {
        "원전 운영·건설": [
            {"name": "한국전력",     "code": "015760", "suffix": ".KS"},
            {"name": "한전KPS",     "code": "051600", "suffix": ".KS"},
            {"name": "한전기술",     "code": "053590", "suffix": ".KS"},
        ],
        "원전 기자재": [
            {"name": "두산에너빌리티","code": "034020", "suffix": ".KS"},
            {"name": "비에이치아이", "code": "083650", "suffix": ".KQ"},
            {"name": "우진",        "code": "105840", "suffix": ".KQ"},
            {"name": "보성파워텍",   "code": "006910", "suffix": ".KQ"},
        ],
        "SMR·차세대원전": [
            {"name": "두산에너빌리티","code": "034020", "suffix": ".KS"},
            {"name": "현대건설",     "code": "000720", "suffix": ".KS"},
            {"name": "SK이엔에스",   "code": "017900", "suffix": ".KQ"},
        ],
        "방사성폐기물·해체": [
            {"name": "한국원자력환경공단","code": "059090", "suffix": ".KQ"},
            {"name": "웰크론한텍",   "code": "076080", "suffix": ".KQ"},
        ],
    },
    "전력기기": {
        "변압기": [
            {"name": "효성중공업",   "code": "298040", "suffix": ".KS"},
            {"name": "현대일렉트릭", "code": "267260", "suffix": ".KS"},
            {"name": "LS ELECTRIC", "code": "010120", "suffix": ".KS"},
            {"name": "제룡전기",     "code": "033100", "suffix": ".KQ"},
        ],
        "차단기·배전기": [
            {"name": "누리텔레콤",   "code": "040160", "suffix": ".KQ"},
            {"name": "일진전기",     "code": "103590", "suffix": ".KS"},
            {"name": "대한전선",     "code": "001440", "suffix": ".KS"},
        ],
        "초전도·ESS": [
            {"name": "LS전선",      "code": "229640", "suffix": ".KQ"},
            {"name": "비나텍",      "code": "002070", "suffix": ".KQ"},
            {"name": "에너테크인터내셔널","code": "016250", "suffix": ".KQ"},
        ],
        "전력 솔루션·스마트그리드": [
            {"name": "우리기술투자", "code": "041190", "suffix": ".KQ"},
            {"name": "KT&G",        "code": "033780", "suffix": ".KS"},
            {"name": "비츠로시스",   "code": "054220", "suffix": ".KQ"},
        ],
    },
    "게임·엔터": {
        "PC·콘솔 게임": [
            {"name": "크래프톤",    "code": "259960", "suffix": ".KS"},
            {"name": "넥슨코리아",  "code": "225130", "suffix": ".KS"},
            {"name": "엔씨소프트",  "code": "036570", "suffix": ".KS"},
            {"name": "넷마블",     "code": "251270", "suffix": ".KS"},
        ],
        "모바일 게임": [
            {"name": "컴투스",      "code": "078340", "suffix": ".KQ"},
            {"name": "카카오게임즈", "code": "293490", "suffix": ".KQ"},
            {"name": "위메이드",    "code": "112040", "suffix": ".KQ"},
            {"name": "펄어비스",    "code": "263750", "suffix": ".KQ"},
        ],
        "K-팝·엔터테인먼트": [
            {"name": "HYBE",        "code": "352820", "suffix": ".KS"},
            {"name": "SM엔터테인먼트","code": "041510", "suffix": ".KQ"},
            {"name": "JYP Ent.",    "code": "035900", "suffix": ".KQ"},
            {"name": "YG엔터테인먼트","code": "122870", "suffix": ".KQ"},
        ],
        "OTT·콘텐츠": [
            {"name": "CJ ENM",     "code": "035760", "suffix": ".KQ"},
            {"name": "스튜디오드래곤","code": "253450", "suffix": ".KQ"},
            {"name": "콘텐트리중앙", "code": "036420", "suffix": ".KS"},
        ],
    },
    "뷰티·K-뷰티": {
        "화장품 대기업": [
            {"name": "아모레퍼시픽", "code": "090430", "suffix": ".KS"},
            {"name": "LG생활건강",  "code": "051900", "suffix": ".KS"},
        ],
        "인디·ODM": [
            {"name": "코스맥스",    "code": "192820", "suffix": ".KS"},
            {"name": "한국콜마",    "code": "161890", "suffix": ".KS"},
            {"name": "코스메카코리아","code": "241710", "suffix": ".KQ"},
            {"name": "씨앤씨인터내셔널","code": "352480", "suffix": ".KQ"},
        ],
        "기능성·이너뷰티": [
            {"name": "클리오",      "code": "237880", "suffix": ".KQ"},
            {"name": "에이피알",    "code": "032120", "suffix": ".KQ"},
            {"name": "브이티",      "code": "018990", "suffix": ".KQ"},
        ],
        "면세·유통": [
            {"name": "호텔신라",    "code": "008770", "suffix": ".KS"},
            {"name": "현대백화점",  "code": "069960", "suffix": ".KS"},
            {"name": "신세계",     "code": "004170", "suffix": ".KS"},
        ],
    },
    "금융·은행": {
        "은행·지주": [
            {"name": "KB금융",        "code": "105560", "suffix": ".KS"},
            {"name": "신한지주",      "code": "055550", "suffix": ".KS"},
            {"name": "하나금융지주",   "code": "086790", "suffix": ".KS"},
            {"name": "우리금융지주",   "code": "316140", "suffix": ".KS"},
            {"name": "기업은행",      "code": "024110", "suffix": ".KS"},
        ],
        "보험": [
            {"name": "삼성생명",      "code": "032830", "suffix": ".KS"},
            {"name": "삼성화재",      "code": "000810", "suffix": ".KS"},
            {"name": "한화생명",      "code": "088350", "suffix": ".KS"},
            {"name": "현대해상",      "code": "001450", "suffix": ".KS"},
        ],
        "증권": [
            {"name": "미래에셋증권",   "code": "006800", "suffix": ".KS"},
            {"name": "키움증권",      "code": "039490", "suffix": ".KQ"},
            {"name": "한국금융지주",   "code": "071050", "suffix": ".KS"},
            {"name": "NH투자증권",    "code": "005940", "suffix": ".KS"},
        ],
        "카드·캐피탈": [
            {"name": "삼성카드",      "code": "029780", "suffix": ".KS"},
            {"name": "현대캐피탈(현대차)","code": "005380", "suffix": ".KS"},
            {"name": "롯데지주",      "code": "004990", "suffix": ".KS"},
        ],
    },
    "화학·소재": {
        "석유화학": [
            {"name": "LG화학",        "code": "051910", "suffix": ".KS"},
            {"name": "롯데케미칼",    "code": "011170", "suffix": ".KS"},
            {"name": "한화솔루션",    "code": "009830", "suffix": ".KS"},
            {"name": "금호석유",      "code": "011780", "suffix": ".KS"},
        ],
        "정밀화학": [
            {"name": "효성첨단소재",   "code": "298050", "suffix": ".KS"},
            {"name": "SKC",           "code": "011790", "suffix": ".KS"},
            {"name": "코오롱인더",    "code": "120110", "suffix": ".KS"},
            {"name": "OCI홀딩스",     "code": "010060", "suffix": ".KS"},
        ],
        "철강·금속": [
            {"name": "POSCO홀딩스",   "code": "005490", "suffix": ".KS"},
            {"name": "현대제철",      "code": "004020", "suffix": ".KS"},
            {"name": "고려아연",      "code": "010130", "suffix": ".KS"},
            {"name": "풍산",          "code": "103140", "suffix": ".KS"},
        ],
    },
    "건설·인프라": {
        "대형 건설": [
            {"name": "삼성물산",      "code": "028260", "suffix": ".KS"},
            {"name": "현대건설",      "code": "000720", "suffix": ".KS"},
            {"name": "GS건설",        "code": "006360", "suffix": ".KS"},
            {"name": "DL이앤씨",      "code": "375500", "suffix": ".KS"},
        ],
        "주택·부동산": [
            {"name": "HDC현대산업개발","code": "294870", "suffix": ".KS"},
            {"name": "대우건설",      "code": "047040", "suffix": ".KS"},
            {"name": "태영건설",      "code": "009410", "suffix": ".KS"},
            {"name": "두산건설",      "code": "011160", "suffix": ".KS"},
        ],
        "인프라·시멘트": [
            {"name": "한국전력",      "code": "015760", "suffix": ".KS"},
            {"name": "쌍용C&E",      "code": "003410", "suffix": ".KS"},
            {"name": "아세아시멘트",  "code": "183190", "suffix": ".KS"},
            {"name": "성신양회",      "code": "004980", "suffix": ".KQ"},
        ],
    },
    "통신": {
        "이동통신": [
            {"name": "SK텔레콤",      "code": "017670", "suffix": ".KS"},
            {"name": "KT",            "code": "030200", "suffix": ".KS"},
            {"name": "LG유플러스",    "code": "032640", "suffix": ".KS"},
        ],
        "미디어·플랫폼": [
            {"name": "카카오",        "code": "035720", "suffix": ".KS"},
            {"name": "NAVER",         "code": "035420", "suffix": ".KS"},
            {"name": "SK브로드밴드(SKT)","code": "017670", "suffix": ".KS"},
        ],
        "유통·이커머스": [
            {"name": "롯데쇼핑",      "code": "023530", "suffix": ".KS"},
            {"name": "이마트",        "code": "139480", "suffix": ".KS"},
            {"name": "GS리테일",      "code": "007070", "suffix": ".KS"},
            {"name": "BGF리테일",     "code": "027410", "suffix": ".KS"},
        ],
    },
}
