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
            {"name": "만도",        "code": "204320", "suffix": ".KS"},
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
}
