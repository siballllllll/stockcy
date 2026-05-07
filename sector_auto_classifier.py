# 자동 섹터 분류 엔진
# yfinance sector/industry + 종목명 키워드를 이용해 테마 섹터 자동 배정

# ── yfinance industry → 우리 섹터 매핑 테이블 (US) ─────────────────────────
_US_INDUSTRY_SECTOR_MAP: dict[str, tuple[str, str]] = {
    # (섹터, 세부섹터) 매핑
    # AI·반도체
    "Semiconductors":                        ("AI·반도체", "AI 가속기·GPU"),
    "Semiconductor Equipment & Materials":   ("AI·반도체", "반도체 장비"),
    "Electronic Components":                 ("AI·반도체", "AI 서버·인프라"),
    "Computer Hardware":                     ("AI·반도체", "AI 서버·인프라"),
    "Data Storage":                          ("AI·반도체", "AI 메모리"),
    # 빅테크·AI소프트
    "Software—Application":                  ("빅테크·AI소프트", "AI SaaS·엔터프라이즈"),
    "Software—Infrastructure":               ("빅테크·AI소프트", "AI SaaS·엔터프라이즈"),
    "Internet Content & Information":        ("빅테크·AI소프트", "AI 플랫폼·클라우드"),
    "Information Technology Services":       ("빅테크·AI소프트", "AI SaaS·엔터프라이즈"),
    "Cloud Computing":                       ("빅테크·AI소프트", "AI 플랫폼·클라우드"),
    # 사이버보안
    "Security & Protection Services":        ("사이버보안", "엔드포인트 보안"),
    "Security Software":                     ("사이버보안", "엔드포인트 보안"),
    # 바이오·헬스케어
    "Drug Manufacturers—General":            ("바이오·헬스케어", "신약·GLP-1"),
    "Drug Manufacturers—Specialty & Generic":("바이오·헬스케어", "바이오테크"),
    "Biotechnology":                         ("바이오·헬스케어", "바이오테크"),
    "Medical Devices":                       ("바이오·헬스케어", "의료기기·수술로봇"),
    "Medical Instruments & Supplies":        ("바이오·헬스케어", "의료기기·수술로봇"),
    "Healthcare Plans":                      ("바이오·헬스케어", "헬스케어 보험"),
    "Diagnostics & Research":               ("바이오·헬스케어", "바이오테크"),
    # 금융·핀테크
    "Banks—Diversified":                     ("금융·핀테크", "빅뱅크"),
    "Banks—Regional":                        ("금융·핀테크", "빅뱅크"),
    "Credit Services":                       ("금융·핀테크", "핀테크·결제"),
    "Financial Data & Stock Exchanges":      ("금융·핀테크", "자산운용·보험"),
    "Asset Management":                      ("금융·핀테크", "자산운용·보험"),
    "Insurance—Diversified":                 ("금융·핀테크", "자산운용·보험"),
    "Capital Markets":                       ("금융·핀테크", "자산운용·보험"),
    # 에너지·원자력
    "Oil & Gas E&P":                         ("에너지·원자력", "빅오일"),
    "Oil & Gas Integrated":                  ("에너지·원자력", "빅오일"),
    "Oil & Gas Midstream":                   ("에너지·원자력", "천연가스·LNG"),
    "Utilities—Regulated Electric":          ("에너지·원자력", "원자력·우라늄"),
    "Utilities—Renewable":                   ("에너지·원자력", "재생에너지"),
    "Solar":                                 ("에너지·원자력", "재생에너지"),
    "Uranium":                               ("에너지·원자력", "원자력·우라늄"),
    # 방산·우주
    "Aerospace & Defense":                   ("방산·우주", "전통 방산"),
    # EV·로봇·자율주행
    "Auto Manufacturers":                    ("EV·로봇·자율주행", "EV 완성차"),
    "Auto Parts":                            ("EV·로봇·자율주행", "EV 부품·충전"),
    "Electrical Equipment & Parts":          ("EV·로봇·자율주행", "EV 부품·충전"),
    # 소비재·유통
    "Internet Retail":                       ("소비재·유통", "이커머스·소매"),
    "Specialty Retail":                      ("소비재·유통", "오프라인 유통"),
    "Discount Stores":                       ("소비재·유통", "오프라인 유통"),
    "Grocery Stores":                        ("소비재·유통", "오프라인 유통"),
    "Food Distribution":                     ("소비재·유통", "필수 소비재"),
    "Beverages—Non-Alcoholic":              ("소비재·유통", "필수 소비재"),
    "Restaurants":                           ("소비재·유통", "음식·외식"),
    "Apparel—Retail":                        ("소비재·유통", "명품·패션·스포츠"),
    # 미디어·엔터·게임
    "Entertainment":                         ("미디어·엔터·게임", "스트리밍·OTT"),
    "Electronic Gaming & Multimedia":        ("미디어·엔터·게임", "게임·메타버스"),
    "Broadcasting":                          ("미디어·엔터·게임", "스트리밍·OTT"),
    "Publishing":                            ("미디어·엔터·게임", "광고·디지털미디어"),
    # 통신·네트워크
    "Telecom Services":                      ("통신·네트워크", "이동통신"),
    "Communication Services":               ("통신·네트워크", "이동통신"),
    "Telecom Equipment":                     ("통신·네트워크", "네트워크 장비"),
    # 항공·여행
    "Airlines":                              ("항공·여행·관광", "항공사"),
    "Travel Services":                       ("항공·여행·관광", "온라인 여행"),
    "Hotels & Motels":                       ("항공·여행·관광", "크루즈·호텔"),
    "Lodging":                               ("항공·여행·관광", "크루즈·호텔"),
    # 리츠·부동산
    "REIT—Diversified":                      ("리츠·부동산", "주거·상업 리츠"),
    "REIT—Office":                           ("리츠·부동산", "주거·상업 리츠"),
    "REIT—Retail":                           ("리츠·부동산", "주거·상업 리츠"),
    "REIT—Industrial":                       ("리츠·부동산", "물류·인프라 리츠"),
    "REIT—Specialty":                        ("리츠·부동산", "데이터센터 리츠"),
    # 전통 산업·소재
    "Steel":                                 ("전통 산업·소재", "철강·금속"),
    "Aluminum":                              ("전통 산업·소재", "철강·금속"),
    "Copper":                                ("전통 산업·소재", "철강·금속"),
    "Chemicals":                             ("전통 산업·소재", "화학·소재"),
    "Specialty Chemicals":                   ("전통 산업·소재", "화학·소재"),
    "Farm & Heavy Construction Machinery":   ("전통 산업·소재", "건설·인프라"),
    "Building Materials":                    ("전통 산업·소재", "건설·인프라"),
}

# ── 종목명 키워드 → 섹터 자동 배정 (US) ─────────────────────────────────────
_US_NAME_KEYWORDS: list[tuple[list[str], str, str]] = [
    # ([키워드목록], 섹터, 세부섹터)
    (["quantum", "quant"],                    "양자컴퓨터·암호",  "순수 양자컴퓨팅"),
    (["cyber", "security", "secure", "hack"], "사이버보안",       "엔드포인트 보안"),
    (["encrypt", "crypti"],                   "양자컴퓨터·암호",  "양자 암호·보안"),
    (["solar", "photovoltaic"],               "에너지·원자력",    "재생에너지"),
    (["nuclear", "uranium", "nuscale"],       "에너지·원자력",    "원자력·우라늄"),
    (["biotech", "bioscience", "genomic"],    "바이오·헬스케어",  "바이오테크"),
    (["pharma", "therapeutics", "oncology"],  "바이오·헬스케어",  "신약·GLP-1"),
    (["robot", "automation", "autonomous"],   "EV·로봇·자율주행", "인간형 로봇·AI 하드웨어"),
    (["drone", "uav", "aerial"],              "방산·우주",        "드론·무인기"),
    (["satellite", "space", "rocket"],        "방산·우주",        "우주·발사체"),
    (["fintech", "payment", "wallet"],        "금융·핀테크",      "핀테크·결제"),
    (["blockchain", "crypto", "defi"],        "금융·핀테크",      "암호화폐·블록체인"),
    (["gaming", "esport", "metaverse"],       "미디어·엔터·게임", "게임·메타버스"),
    (["streaming", "content", "media"],       "미디어·엔터·게임", "스트리밍·OTT"),
    (["lidar", "radar", "adas"],              "EV·로봇·자율주행", "자율주행·라이다"),
    (["ev", "electric vehicle", "charging"],  "EV·로봇·자율주행", "EV 완성차"),
    (["defense", "missile", "weapon"],        "방산·우주",        "전통 방산"),
    (["reit", "realty", "properties"],        "리츠·부동산",      "주거·상업 리츠"),
    (["data center", "datacenter"],           "리츠·부동산",      "데이터센터 리츠"),
    (["cloud", "saas", "paas"],               "빅테크·AI소프트",  "AI SaaS·엔터프라이즈"),
]

# ── FDR 업종명 → KR 섹터 매핑 테이블 ────────────────────────────────────────
_KR_INDUSTRY_SECTOR_MAP: dict[str, tuple[str, str]] = {
    # (섹터, 세부섹터) 매핑
    "반도체":                   ("반도체", "반도체 공정"),
    "반도체 및 반도체장비":      ("반도체", "반도체 장비"),
    "전자부품":                  ("반도체", "반도체 소재"),
    "소프트웨어":                ("AI·로봇", "AI 플랫폼"),
    "IT서비스":                  ("AI·로봇", "AI 데이터센터"),
    "정보기술서비스":            ("AI·로봇", "AI 데이터센터"),
    "인터넷서비스":              ("AI·로봇", "AI 플랫폼"),
    "바이오":                    ("바이오·제약", "바이오벤처·신약"),
    "제약":                      ("바이오·제약", "제약"),
    "의료장비":                  ("바이오·제약", "의료기기"),
    "2차전지":                   ("2차전지", "배터리셀"),
    "전기차":                    ("2차전지", "전기차 부품"),
    "방위산업":                  ("방산", "육상무기·장갑차"),
    "조선":                      ("조선", "대형 조선사"),
    "해운":                      ("조선·해운", "해운·물류"),
    "철강":                      ("전통 산업·소재", "철강·금속"),
    "화학":                      ("전통 산업·소재", "화학·소재"),
    "건설":                      ("건설·부동산", "건설"),
    "금융":                      ("금융·핀테크", "증권·자산운용"),
    "은행":                      ("금융·핀테크", "은행"),
    "보험":                      ("금융·핀테크", "보험"),
    "디스플레이":                ("반도체·디스플레이 (일반)", "디스플레이"),
    "통신":                      ("플랫폼·통신", "통신"),
    "미디어":                    ("플랫폼·통신", "미디어·콘텐츠"),
    "게임":                      ("플랫폼·통신", "게임"),
    "의류":                      ("소비재", "패션·의류"),
    "식품":                      ("소비재", "식품·음료"),
    "자동차":                    ("소비재", "자동차·전장"),
    "항공":                      ("방산·우주항공 (일반)", "항공·MRO"),
    "유통":                      ("소비재", "유통·이커머스"),
    "수소":                      ("수소·친환경에너지", "수소 생산·저장"),
    "태양광":                    ("수소·친환경에너지", "태양광"),
    "원자력":                    ("원전·에너지", "원전 기자재"),
}

# ── 종목명 키워드 → KR 섹터 자동 배정 ───────────────────────────────────────
_KR_NAME_KEYWORDS: list[tuple[list[str], str, str]] = [
    (["양자", "퀀텀"],            "양자컴퓨터·암호",  "양자 보안·암호화"),
    (["보안", "시큐"],            "양자컴퓨터·암호",  "포스트퀀텀·사이버보안"),
    (["인증", "암호"],            "양자컴퓨터·암호",  "정보보호·인증"),
    (["로봇", "자동화"],          "AI·로봇",          "로봇"),
    (["드론", "무인기"],          "방산",             "방산전자·드론"),
    (["위성", "우주", "발사체"],  "우주·항공우주",    "발사체·위성 제조"),
    (["수소", "연료전지"],        "수소·친환경에너지","수소 생산·저장"),
    (["태양광", "솔라"],          "수소·친환경에너지","태양광·풍력"),
    (["원전", "원자력"],          "원전·에너지",      "원전 기자재"),
    (["바이오", "제약", "신약"],  "바이오·제약",      "바이오벤처·신약"),
    (["배터리", "2차전지", "셀"], "2차전지",          "배터리셀"),
    (["핀테크", "페이"],          "금융·핀테크",      "핀테크·결제"),
    (["블록체인", "NFT", "코인"], "금융·핀테크",      "암호화폐·블록체인"),
    (["메타버스", "XR", "VR"],    "메타버스·XR",      "메타버스 플랫폼"),
    (["게임"],                    "플랫폼·통신",      "게임"),
    (["클라우드", "데이터센터"],  "AI·로봇",          "AI 데이터센터"),
    (["AI", "인공지능"],          "AI·로봇",          "AI 플랫폼"),
    (["자율주행", "라이다"],      "AI·로봇",          "자율주행·전장"),
]


def classify_us_stock(ticker: str, name: str, yf_sector: str = "", yf_industry: str = "") -> tuple[str, str] | None:
    """US 종목을 섹터·세부섹터로 자동 분류. 분류 불가 시 None 반환."""
    # 1차: yfinance industry 기반
    if yf_industry and yf_industry in _US_INDUSTRY_SECTOR_MAP:
        return _US_INDUSTRY_SECTOR_MAP[yf_industry]
    if yf_sector and yf_sector in _US_INDUSTRY_SECTOR_MAP:
        return _US_INDUSTRY_SECTOR_MAP[yf_sector]

    # 2차: 종목명 키워드 기반
    name_lower = name.lower()
    ticker_lower = ticker.lower()
    for keywords, sector, sub in _US_NAME_KEYWORDS:
        if any(kw in name_lower or kw in ticker_lower for kw in keywords):
            return sector, sub

    return None


def classify_kr_stock(name: str, fdr_industry: str = "") -> tuple[str, str] | None:
    """KR 종목을 섹터·세부섹터로 자동 분류. 분류 불가 시 None 반환."""
    # 1차: FDR 업종 기반
    if fdr_industry:
        for ind_key, mapping in _KR_INDUSTRY_SECTOR_MAP.items():
            if ind_key in fdr_industry:
                return mapping

    # 2차: 종목명 키워드 기반
    for keywords, sector, sub in _KR_NAME_KEYWORDS:
        if any(kw in name for kw in keywords):
            return sector, sub

    return None


def enrich_sector_map_us(base_map: dict, ticker_map: dict) -> dict:
    """ticker_map의 종목을 자동 분류해서 base_map에 병합.

    ticker_map: {ticker: {"name": str, "exchange": str, "sector": str, "industry": str}}
    """
    existing_tickers: set = {
        s["ticker"]
        for subs in base_map.values()
        for stocks in subs.values()
        for s in stocks
        if isinstance(s, dict) and s.get("ticker")
    }
    for ticker, info in ticker_map.items():
        if ticker in existing_tickers:
            continue
        name     = info.get("name", ticker)
        exchange = info.get("exchange", "NASDAQ")
        sector_i = info.get("sector", "")
        industry = info.get("industry", "")
        result = classify_us_stock(ticker, name, sector_i, industry)
        if result:
            sec, sub = result
            base_map.setdefault(sec, {}).setdefault(sub, []).append(
                {"name": name, "ticker": ticker, "exchange": exchange}
            )
            existing_tickers.add(ticker)
    return base_map


def enrich_sector_map_kr(base_map: dict, fdr_all: list[dict]) -> dict:
    """FDR 전종목 리스트를 자동 분류해서 base_map에 병합.

    fdr_all: [{"name": str, "code": str, "suffix": str, "industry": str}]
    """
    existing_codes: set = {
        s["code"]
        for subs in base_map.values()
        for stocks in subs.values()
        for s in stocks
        if isinstance(s, dict) and s.get("code")
    }
    for stock in fdr_all:
        code = stock.get("code", "")
        if not code or code in existing_codes:
            continue
        name     = stock.get("name", "")
        suffix   = stock.get("suffix", ".KS")
        industry = stock.get("industry", "")
        result = classify_kr_stock(name, industry)
        if result:
            sec, sub = result
            base_map.setdefault(sec, {}).setdefault(sub, []).append(
                {"name": name, "code": code, "suffix": suffix}
            )
            existing_codes.add(code)
    return base_map
