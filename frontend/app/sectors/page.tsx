"use client";

import { useState, useMemo, useEffect } from "react";
import { api, connectSSE } from "@/lib/api";
import useSWR from "swr";
import { 
  Flame, Layers, Search, ChevronRight, Activity, TrendingUp, 
  ChevronDown, Info, Network, GitBranch, ShieldAlert, Sparkles, Link2, HelpCircle 
} from "lucide-react";
import { useRouter } from "next/navigation";
import { StockModal } from "@/components/ui/StockModal";
import type { StockInfo } from "@/components/ui/StockModal";

// ── 기술적 AI 시그널 판독 헬퍼 ───────────────────────────────────────────────
function getSignalBadge(changePct: number | null) {
  if (changePct === null) return { label: "⚪ 관망", color: "text-zinc-400 bg-white/5 border-white/10" };
  if (changePct >= 7) return { label: "🔥 강력 추천", color: "text-red-400 bg-red-500/10 border-red-500/20" };
  if (changePct >= 2) return { label: "🟢 매수 추천", color: "text-emerald-400 bg-emerald-500/10 border-emerald-500/20" };
  if (changePct <= -7) return { label: "🔵 매수 검토", color: "text-blue-400 bg-blue-500/10 border-blue-500/20" };
  if (changePct <= -2) return { label: "🔴 비추천", color: "text-rose-400 bg-rose-500/10 border-rose-500/20" };
  return { label: "⚪ 관망", color: "text-zinc-400 bg-white/5 border-white/10" };
}


// 세부 테마에 대한 간단한 설명 맵 (주요 테마 위주)
const SUB_SECTOR_DESC: Record<string, string> = {
  "반도체 공정": "반도체 제조 전반을 아우르는 종합 반도체 및 핵심 파운드리 관련 기업",
  "HBM·메모리": "고대역폭 메모리(HBM) 및 차세대 D램/낸드 관련 핵심 밸류체인",
  "유리기판·PCB": "차세대 반도체 패키징을 위한 유리기판 및 고다층 인쇄회로기판(PCB) 관련주",
  "반도체 소재": "웨이퍼, 특수가스, 포토레지스트(PR) 등 반도체 제조 핵심 소재 관련주",
  "반도체 장비": "노광, 식각, 증착 등 전공정 및 핵심 후공정 반도체 제조 설비 관련주",
  "반도체 패키징": "첨단 패키징(OSAT) 및 후공정 테스팅 관련 핵심 기업",
  "배터리 셀": "전기차 및 ESS용 2차전지 완제품을 생산하는 배터리 제조사",
  "양극재": "배터리의 용량과 출력을 결정하는 2차전지 핵심 소재 관련주",
  "음극재": "배터리의 수명과 충전 속도를 좌우하는 2차전지 소재 관련주",
  "전해질·분리막": "리튬이온 이동 통로 및 안전성을 담당하는 배터리 핵심 소재",
  "전지 장비·부품": "2차전지 전극/조립/화성 공정 장비 및 캔, 파우치 등 부품 관련주",
  "신약 개발": "글로벌 임상 및 블록버스터급 혁신 신약 파이프라인 보유 기업",
  "바이오벤처·신약": "ADC, 표적항암제 등 차세대 신약 플랫폼 기술을 보유한 벤처 기업",
  "의료기기": "AI 진단, 임플란트, 미용 의료기기 등 고성장 헬스케어 디바이스 관련주",
  "CMO 위탁생산": "글로벌 제약사의 바이오의약품을 위탁 생산하는 CMO/CDMO 기업",
  "진단·헬스케어": "체외진단 기기 및 디지털 헬스케어 플랫폼 관련주",
  "AI 플랫폼": "자체 거대언어모델(LLM) 및 대규모 AI 인프라를 구축하는 빅테크/소프트웨어 기업",
  "AI 반도체·NPU": "AI 연산 및 추론에 특화된 신경망처리장치(NPU) 설계 및 팹리스 기업",
  "AI 데이터센터": "폭증하는 AI 트래픽을 처리하기 위한 데이터센터 구축 및 서버 관련주",
  "AI 소프트웨어·서비스": "의료, 금융, 공공 등 산업 맞춤형 AI 솔루션을 제공하는 B2B/B2C 기업",
  "로봇": "협동로봇, 산업용 로봇 및 물류/서비스 로봇 핵심 부품 및 제조사",
  "자율주행·전장": "자율주행 소프트웨어, 라이다/레이더 및 차량용 인포테인먼트 관련주",
  "양자 보안·암호화": "양자내성암호(PQC) 및 양자키분배(QKD) 기술 기반 차세대 보안 관련주",
  "양자 컴퓨팅·소재": "양자 컴퓨터 하드웨어 설계 및 초전도체 등 핵심 소재 관련주",
  "포스트퀀텀·사이버보안": "기존 사이버 위협 방어 및 양자 기술 시대에 대응하는 정보보안 기업",
  "육상무기·장갑차": "K-방산 수출을 견인하는 전차, 자주포, 장갑차 등 지상 무기체계 관련주",
  "항공·우주": "전투기, 헬기 및 저궤도 위성통신 등 우주항공 산업 관련주",
  "함정·레이더": "이지스함, 잠수함 등 특수선 건조 및 해양 방위 레이더 체계 관련주",
  "대형 조선소": "LNG선, 컨테이너선 등 고부가가치 선박을 건조하는 국내 대형 조선 3사",
  "기자재·부품": "조선 블록, 보냉재, 엔진 밸브 등 선박 건조에 필수적인 기자재 관련주",
  "완성차": "내연기관 및 친환경 전기/수소차를 최종 조립 및 판매하는 완성차 제조사",
  "전장·부품": "자동차 차체, 샤시, 모터 등 핵심 부품 및 전장 시스템 납품 기업",
  "원전 운영·건설": "국내외 원자력 발전소 시공 및 전력 생산/유지보수 관련 핵심 대형사",
  "원전 기자재": "원자로, 증기발생기, 펌프 등 원전 핵심 주기기 및 보조기기 관련주",
  "SMR·차세대원전": "소형모듈원전(SMR) 설계 및 차세대 원자력 기술 투자 관련주",
  "변압기": "북미 전력망 교체 및 AI 데이터센터 수요에 대응하는 초고압 변압기 관련주",
  "차단기·배전기·케이블": "전력 송배전망 효율화를 위한 차단기 및 초고압 전력 케이블 관련주",
  "PC·콘솔 게임": "글로벌 IP를 기반으로 한 대형 MMORPG 및 콘솔 신작 개발사",
  "모바일 게임": "캐주얼 및 서브컬처 중심의 모바일 게임 서비스 기업",
  "K-팝·엔터테인먼트": "글로벌 팬덤을 보유한 K-POP 아티스트 소속 대형 엔터테인먼트사",
  "OTT·콘텐츠·미디어": "넷플릭스 등 글로벌 OTT향 드라마/영화 제작 및 배급사",
  "화장품 대기업": "글로벌 브랜드를 보유한 국내 대표 럭셔리 및 매스 뷰티 기업",
  "인디·ODM": "글로벌 K-뷰티 열풍을 주도하는 인디 브랜드 및 화장품 위탁생산(ODM) 기업",
  "은행·지주": "안정적인 이자이익과 주주환원 정책이 돋보이는 대표 금융지주사",
  "석유화학": "나프타 분해 등 에틸렌/프로필렌 계열 기초유분 및 합성수지 제조사",
  "철강·금속": "자동차/조선/건설 향 열연/냉연강판 및 특수강 생산 철강 기업",
  "대형 건설": "국내외 대규모 플랜트, 주택, 인프라 사업을 영위하는 1군 건설사",
  "이동통신": "5G/6G 통신망을 기반으로 통신 및 미디어/AI 신사업을 영위하는 이통 3사"
};

// 10대 대표 쉐도우 섹터 앵커 사전 데이터
interface ShadowStock {
  name: string;
  code: string;
  market: string;
  relation: string;
  rate: string;
  credibility: string;
  risk: string;
}

interface ShadowAnchor {
  id: string;
  name: string;
  desc: string;
  stocks: ShadowStock[];
}

const SHADOW_ANCHORS: ShadowAnchor[] = [
  {
    id: "dunamu",
    name: "⛓️ 두나무 & 비트코인",
    desc: "국내 최대 가상자산 거래소 업비트 운영사 지분 연동 테마",
    stocks: [
      { name: "우리기술투자", code: "041190", market: "KR", relation: "두나무 지분 약 7.2% 보유", rate: "7.2%", credibility: "상", risk: "비트코인 시세 급등락에 본업 실적과 무관하게 동조하여 변동성 극대화" },
      { name: "한화투자증권", code: "003530", market: "KR", relation: "두나무 지분 약 5.9% 보유", rate: "5.9%", credibility: "상", risk: "가상자산 열풍 시 수혜주로 엮이나 증권업 자체 실적 대조 필요" },
      { name: "에이티넘인베스트", code: "021080", market: "KR", relation: "에이티넘고성장기업투자조합을 통해 두나무 간접 보유", rate: "간접", credibility: "상", risk: "창투사 특성상 펀드 만기 및 회수 시점에 따른 변동 요인 존재" }
    ]
  },
  {
    id: "spacex",
    name: "🚀 스페이스X & 우주항공",
    desc: "일론 머스크의 민간 우주기업 지분 투자 및 밸류체인 테마",
    stocks: [
      { name: "미래에셋증권", code: "006800", market: "KR", relation: "스페이스X에 펀드 등으로 1,000억 원 이상 지분 투자", rate: "투자참여", credibility: "상", risk: "비상장 지분 평가이익 반영이 제한적이므로 테마 과열 경계 필요" },
      { name: "켄코아에어로스페이스", code: "274090", market: "KR", relation: "스페이스X에 우주 가공 원소재 공급 이력", rate: "공급", credibility: "상", risk: "실제 원소재 납품 규모 대비 주가 선반영 우려 주의" },
      { name: "AP위성", code: "211050", market: "KR", relation: "글로벌 저궤도 위성 통신 밸류체인 연계", rate: "연계", credibility: "미확인", risk: "확정되지 않은 공급 찌라시에 대한 뇌동매매 주의" }
    ]
  },
  {
    id: "openai",
    name: "🧠 오픈AI & 인공지능",
    desc: "ChatGPT 서비스 연동 및 AI 솔루션 생태계 테마",
    stocks: [
      { name: "폴라리스오피스", code: "041020", market: "KR", relation: "오픈AI의 GPT Store 연동 및 오피스 AI 서비스 상용화", rate: "서비스연동", credibility: "상", risk: "AI 구독 모델의 실제 매출 전환 지표 확인 필수" },
      { name: "이스트소프트", code: "047560", market: "KR", relation: "MS 및 오픈AI 파트너십 기반 AI 휴먼 사업 영위", rate: "파트너십", credibility: "상", risk: "실제 솔루션 공급 계약서 체결 및 로열티 정산 비율 확인 필요" }
    ]
  },
  {
    id: "toss",
    name: "💳 토스 (비바리퍼블리카)",
    desc: "종합 금융 플랫폼 토스 지분 보유 및 인터넷은행 연동 테마",
    stocks: [
      { name: "이월드", code: "084680", market: "KR", relation: "계열사 이랜드월드를 통해 토스뱅크 지분 약 7.5% 보유", rate: "7.5%", credibility: "상", risk: "본업(패션/쥬얼리)과 토스뱅크 지분 가치 괴리 발생 주의" },
      { name: "한국정보인증", code: "053300", market: "KR", relation: "토스뱅크 주주사로서 지분 보유", rate: "주주", credibility: "상", risk: "토스 IPO 기대감 소멸 및 지분 보호예수 해제 여부 체크 필요" },
      { name: "한화투자증권", code: "003530", market: "KR", relation: "토스 지분 보유", rate: "보유", credibility: "상", risk: "두나무 지분 테마와 겹쳐 변동성 증폭 가능성" }
    ]
  },
  {
    id: "kbank",
    name: "🏦 케이뱅크",
    desc: "인터넷전문은행 케이뱅크 IPO 상장설 및 지분 연동 테마",
    stocks: [
      { name: "브리지텍", code: "041270", market: "KR", relation: "케이뱅크 지분 보유 및 콜센터 솔루션 독점 공급", rate: "주주/공급", credibility: "상", risk: "상장 추진 일정 연기 시 단기 차익 실현 매물 출회 우려" },
      { name: "KG이니시스", code: "035600", market: "KR", relation: "케이뱅크 지분 보유 및 간편결제 게이트웨이 연동", rate: "주주", credibility: "상", risk: "결제 수수료 인하 압박 및 인터넷은행 성장 정체성 대조 필요" }
    ]
  },
  {
    id: "yanolja",
    name: "✈️ 야놀자 (나스닥)",
    desc: "여가 플랫폼 야놀자의 나스닥 상장 수혜 및 투자 연동 테마",
    stocks: [
      { name: "한화투자증권", code: "003530", market: "KR", relation: "야놀자 지분 보유", rate: "보유", credibility: "상", risk: "두나무, 토스, 야놀자 3대 쉐도우 테마 동시 노출주로 복잡성 큼" },
      { name: "SBI인베스트먼트", code: "019550", market: "KR", relation: "야놀자에 대규모 펀드 투자 집행", rate: "투자", credibility: "상", risk: "투자 지분 회수(엑시트)에 따른 일시적 차익 변동 주의" }
    ]
  },
  {
    id: "hyundai_robot",
    name: "🤖 현대차 & 보스턴다이내믹스",
    desc: "현대차그룹의 로봇 자회사 동조화 및 부품 납품 테마",
    stocks: [
      { name: "현대글로비스", code: "086280", market: "KR", relation: "보스턴 다이내믹스 지분 직접 보유 참여", rate: "보유", credibility: "상", risk: "종합물류 본업 대비 로봇 사업 기여도 미미, 중장기 접근 필요" },
      { name: "로보티즈", code: "108490", market: "KR", relation: "현대차그룹 자율주행 로봇 실증 밸류체인 참여", rate: "협력", credibility: "상", risk: "연구 단계 실증 성과와 실제 대량 양산 주문서 대조 필요" }
    ]
  },
  {
    id: "superconductor",
    name: "⚡ 초전도체 (퀀텀에너지)",
    desc: "초전도체 개발사 퀀텀에너지연구소 간접 지분 연동 테마",
    stocks: [
      { name: "신성델타테크", code: "018670", market: "KR", relation: "L&S벤처캐피탈 지분을 통해 퀀텀에너지연구소 연동 보유", rate: "간접", credibility: "상", risk: "초전도성 검증 학계 공방에 따라 주가 하루 30% 급등락하는 하이리스크 종목" },
      { name: "파워로직스", code: "047310", market: "KR", relation: "L&S벤처캐피탈 지분 보유로 초전도체 공동 테마 엮임", rate: "간접", credibility: "상", risk: "본업(카메라 모듈) 실적 대비 테마의 투기적 요인이 지배적" }
    ]
  },
  {
    id: "hlb",
    name: "🧪 HLB & 항암제 신약",
    desc: "항암제 리보세라닙 임상 승인에 따른 그룹사 순환 테마",
    stocks: [
      { name: "HLB제약", code: "047920", market: "KR", relation: "HLB 그룹사 지분 순환 및 리보세라닙 판권/제조 연계", rate: "계열/판권", credibility: "상", risk: "임상 진행 절차 지연 및 FDA 승인 여부에 따른 초고위험 변동성 보유" },
      { name: "HLB글로벌", code: "003520", market: "KR", relation: "HLB 그룹사 순환 테마 및 헬스케어 유통", rate: "계열", credibility: "상", risk: "본업 실적 부진 요인과 바이오 테마의 오버랩 경계 필요" }
    ]
  },
  {
    id: "nvidia_hbm",
    name: "🔌 엔비디아 & AI 가속기",
    desc: "엔비디아의 AI 반도체 독점에 따른 핵심 서플라이 체인 테마",
    stocks: [
      { name: "SK하이닉스", code: "000660", market: "KR", relation: "엔비디아향 고대역폭 메모리 (HBM3E) 독점적 공급 밸류체인", rate: "핵심공급", credibility: "상", risk: "마이크론/삼성전자 HBM 진입 및 경쟁 가속화 우려 상존" },
      { name: "한미반도체", code: "042700", market: "KR", relation: "HBM 패키징용 TC 본더 장비 엔비디아/하이닉스 공급", rate: "독점장비", credibility: "상", risk: "글로벌 경쟁사 장비 국산화 및 오버밸류에이션 논란 주의" }
    ]
  }
];

// 섹터당 표시/가격조회 종목 상한 (US 섹터는 수백~수천 개라 렌더·yfinance 과부하 방지. KR은 작아 영향 없음)
const SECTOR_STOCK_CAP = 40;

export default function SectorsPage() {
  const router = useRouter();
  const [selectedStock, setSelectedStock] = useState<StockInfo | null>(null);
  const [activeTab, setActiveTab] = useState<"hot" | "all" | "shadow">("hot");
  const [searchQuery, setSearchQuery] = useState("");
  const [mapMarket, setMapMarket] = useState<"KR" | "US">("KR");   // 전체 섹터 지도 시장 토글
  const [selectedSector, setSelectedSector] = useState<string>("전체");
  const [expandedSubs, setExpandedSubs] = useState<Record<string, boolean>>({});

  // 쉐도우 탭 상태
  const [selectedAnchor, setSelectedAnchor] = useState<string>("dunamu");
  const [shadowSearchQuery, setShadowSearchQuery] = useState("");
  const [shadowDiscoverStatus, setShadowDiscoverStatus] = useState<"idle" | "loading" | "done" | "error">("idle");
  const [shadowDiscoverMsg, setShadowDiscoverMsg] = useState("");
  const [shadowDiscoverResult, setShadowDiscoverResult] = useState<any>(null);

  // URL 쿼리(?tab=all&market=&sector=)로 진입 시 해당 탭/시장/섹터 자동 선택 (섹터 칩 클릭 연동)
  useEffect(() => {
    const sp = new URLSearchParams(window.location.search);
    const t = sp.get("tab");
    const m = sp.get("market");
    const s = sp.get("sector");
    if (t === "all" || t === "hot" || t === "shadow") setActiveTab(t);
    if (m === "KR" || m === "US") setMapMarket(m);
    if (s) { setActiveTab("all"); setSelectedSector(s); }
  }, []);

  // 전체 섹터 맵 로드 (KR — hot/shadow 탭과 codeToNameMap 공용, 그대로 유지)
  const { data: sectorMap, isLoading: mapLoading } = useSWR(
    "/api/kr/sector-map",
    () => api.kr.sectorMap(),
    { revalidateOnFocus: false }
  );

  // 미국 섹터 맵 (전체 섹터 지도 US 토글 시) — ticker → code 로 정규화해 동일 렌더링 재사용
  const { data: usSectorMap, isLoading: usMapLoading } = useSWR(
    mapMarket === "US" ? "/api/us/sector-map" : null,
    async () => {
      const raw = await api.us.sectorMap();
      const out: Record<string, Record<string, any[]>> = {};
      Object.entries((raw ?? {}) as Record<string, any>).forEach(([sec, subs]) => {
        out[sec] = {};
        Object.entries((subs ?? {}) as Record<string, any[]>).forEach(([sub, items]) => {
          out[sec][sub] = (items ?? []).map((it: any) => ({ ...it, code: it.code ?? it.ticker }));
        });
      });
      return out;
    },
    { revalidateOnFocus: false }
  );

  // 전체 섹터 지도 탭에서 실제 사용할 맵 (시장 토글 반영)
  const activeMap = mapMarket === "US" ? usSectorMap : sectorMap;
  const activeMapLoading = mapMarket === "US" ? usMapLoading : mapLoading;

  // 오늘의 핫섹터 로드
  const { data: hotSectors, isLoading: hotLoading } = useSWR(
    "/api/kr/hot-sectors",
    () => api.kr.hotSectors(),
    { revalidateOnFocus: false }
  );

  const toggleSub = (subKey: string) => {
    setExpandedSubs(prev => ({ ...prev, [subKey]: !prev[subKey] }));
  };

  // 대분류 섹터 리스트 (전체 섹터 지도 — 시장 토글 반영)
  const sectorNames = useMemo(() => {
    if (!activeMap) return [];
    return Object.keys(activeMap as Record<string, any>).sort();
  }, [activeMap]);

  // 티커 코드를 종목명으로 변환하기 위한 맵 생성
  const codeToNameMap = useMemo(() => {
    const map: Record<string, string> = {};
    if (sectorMap) {
      Object.values(sectorMap as Record<string, any>).forEach(subMap => {
        Object.values(subMap as Record<string, any[]>).forEach(stocks => {
          stocks.forEach(s => {
            if (s.code && s.name) {
              map[s.code] = s.name;
            }
          });
        });
      });
    }
    return map;
  }, [sectorMap]);

  // 필터링된 섹터 데이터 계층 구조 생성 (전체 섹터 지도 — 시장 토글 반영)
  const filteredData = useMemo(() => {
    if (!activeMap) return [];
    const query = searchQuery.trim().toLowerCase();
    const result: Array<{ sector: string; subSectors: Array<{ name: string; stocks: any[] }> }> = [];

    Object.entries(activeMap as Record<string, any>).forEach(([sectorName, subMap]) => {
      if (selectedSector !== "전체" && sectorName !== selectedSector && !query) return;

      const matchedSubs: Array<{ name: string; stocks: any[] }> = [];

      Object.entries(subMap as any).forEach(([subName, stocks]: [string, any]) => {
        const sectorMatch = sectorName.toLowerCase().includes(query);
        const subMatch = subName.toLowerCase().includes(query);
        const matchedStocks = query ? stocks.filter((s: any) => s.name.toLowerCase().includes(query) || s.code.includes(query)) : stocks;

        if (!query || sectorMatch || subMatch || matchedStocks.length > 0) {
          matchedSubs.push({
            name: subName,
            stocks: (sectorMatch || subMatch) && query ? stocks : (query ? matchedStocks : stocks),
          });
        }
      });

      if (matchedSubs.length > 0) {
        result.push({ sector: sectorName, subSectors: matchedSubs });
      }
    });

    return result;
  }, [activeMap, searchQuery, selectedSector]);

  // 현재 화면에 보이는 섹터 종목 + 쉐도우 앵커만 가격 조회 (전체 2940개 일괄 조회 방지)
  const allCodes = useMemo(() => {
    const codes = new Set<string>();

    // (1) 현재 선택된 섹터의 종목만 수집 (전체 선택 시 첫 3개 섹터만) — KR 맵일 때만
    if (mapMarket === "KR" && sectorMap && filteredData.length > 0) {
      const targetSectors = selectedSector !== "전체"
        ? filteredData
        : filteredData.slice(0, 3); // 전체 탭은 상위 3개 섹터만 미리 로드
      targetSectors.forEach(({ subSectors }) => {
        subSectors.forEach(({ stocks }) => {
          stocks.forEach((s: any) => { if (s.code) codes.add(s.code); });
        });
      });
    }

    // (2) 사전 정의된 쉐도우 앵커 종목 중 국내 종목 수집
    SHADOW_ANCHORS.forEach(anchor => {
      anchor.stocks.forEach(s => {
        if (s.market === "KR" && s.code) codes.add(s.code);
      });
    });

    // (3) 실시간 RAG 쉐도우 발굴 결과 중 국내 종목 수집
    if (shadowDiscoverResult?.stocks) {
      shadowDiscoverResult.stocks.forEach((s: any) => {
        if (s.market === "KR" && s.ticker) codes.add(s.ticker);
      });
    }

    return Array.from(codes);
  }, [sectorMap, filteredData, selectedSector, shadowDiscoverResult, mapMarket]);

  // 일괄 현재가 조회 (KR)
  const { data: bulkPrices } = useSWR(
    allCodes.length > 0 ? ["stocks-bulk", allCodes] : null,
    ([_, codes]) => api.kr.stocksBulk(codes),
    { refreshInterval: 60000, revalidateOnFocus: false }
  );

  // 전체 섹터 지도 US 토글 시: 화면에 보이는 US 종목 현재가 조회
  // (US 섹터는 종목이 수백~수천 개라 sub당 SECTOR_STOCK_CAP개로 제한 + 전체 상한으로 yfinance 과부하 방지)
  const usMapCodes = useMemo(() => {
    if (mapMarket !== "US") return [];
    const codes = new Set<string>();
    const targets = selectedSector !== "전체" ? filteredData : filteredData.slice(0, 3);
    targets.forEach(({ subSectors }) => subSectors.forEach(({ stocks }) =>
      stocks.slice(0, SECTOR_STOCK_CAP).forEach((s: any) => { if (s.code) codes.add(s.code); })));
    return Array.from(codes).slice(0, 120);
  }, [mapMarket, filteredData, selectedSector]);

  const { data: usMapPrices } = useSWR(
    usMapCodes.length > 0 ? ["us-map-prices-kis", usMapCodes] : null,
    ([_, codes]) => api.us.pricesBulk(codes as string[]),   // KIS 우선 + 서버 60초 캐시
    { refreshInterval: 60000, revalidateOnFocus: false }
  );

  // 사전 쉐도우 앵커 + 실시간 RAG 결과 내의 모든 미국(US) 고유 종목 코드 추출
  const usCodes = useMemo(() => {
    const codes = new Set<string>();

    // (1) 사전 정의된 쉐도우 앵커 종목 중 미국 종목 수집
    SHADOW_ANCHORS.forEach(anchor => {
      anchor.stocks.forEach(s => {
        if (s.market === "US" && s.code) {
          codes.add(s.code.toUpperCase());
        }
      });
    });

    // (2) 실시간 RAG 쉐도우 발굴 결과 중 미국 종목 수집
    if (shadowDiscoverResult?.stocks) {
      shadowDiscoverResult.stocks.forEach((s: any) => {
        if (s.market === "US" && s.ticker) {
          codes.add(s.ticker.toUpperCase());
        }
      });
    }

    return Array.from(codes);
  }, [shadowDiscoverResult]);

  // 미국 일괄 현재가 조회
  const { data: usPrices } = useSWR(
    usCodes.length > 0 ? ["us-stocks-bulk", usCodes] : null,
    ([_, tickers]) => api.us.stocks(tickers),
    { refreshInterval: 60000, revalidateOnFocus: false }
  );

  // 미국 종목 시세 조회 맵 파싱
  const usPriceMap = useMemo(() => {
    const map: Record<string, { price: number; change_pct: number }> = {};
    if (usPrices) {
      (usPrices as any[]).forEach(s => {
        const ticker = s["심볼"] ?? s.ticker ?? "";
        if (ticker) {
          map[ticker.trim().toUpperCase()] = {
            price: s["현재가($)"] ?? s.price ?? 0,
            change_pct: s["등락률(%)"] ?? s.change_pct ?? 0
          };
        }
      });
    }
    return map;
  }, [usPrices]);

  // 실시간 AI RAG 쉐도우 종목 발굴 즉석 탐색
  const runShadowDiscover = async () => {
    if (!shadowSearchQuery.trim()) return;
    setShadowDiscoverStatus("loading");
    setShadowDiscoverResult(null);
    setShadowDiscoverMsg("📡 실시간 구글 RAG 정보망 수집 중...");

    try {
      await connectSSE<any>(
        "/api/ai/shadow-discover",
        (evt) => {
          if (evt.status === "running") {
            setShadowDiscoverMsg(evt.message ?? "분석 중...");
          } else if (evt.status === "done" && evt.result) {
            setShadowDiscoverResult(evt.result);
            setShadowDiscoverStatus("done");
          } else if (evt.status === "error") {
            setShadowDiscoverMsg(evt.message ?? "오류 발생");
            setShadowDiscoverStatus("error");
          }
        },
        {
          method: "POST",
          body: {
            keyword: shadowSearchQuery.trim()
          }
        }
      );
    } catch (err: any) {
      setShadowDiscoverMsg(`❌ RAG 탐색 실패: ${err.message}`);
      setShadowDiscoverStatus("error");
    }
  };

  // 선택한 앵커 데이터
  const activeAnchorData = useMemo(() => {
    return SHADOW_ANCHORS.find(a => a.id === selectedAnchor);
  }, [selectedAnchor]);

  return (
    <div className="flex flex-col gap-6 animate-in fade-in duration-300">
      <header className="border-b border-white/5 pb-4">
        <h1 className="text-2xl font-bold tracking-tight text-white mb-2 flex items-center gap-3">
          🔥 오늘의 이슈 섹터 & AI 쉐도우 맵
        </h1>
        <p className="text-zinc-400 text-sm">
          시장 주도 테마 및 지분 보유·자회사 얽힘으로 연동된 숨겨진 족보를 완벽히 정복하세요.
        </p>
      </header>

      {/* 탭 네비게이션 */}
      <div className="flex gap-2 bg-white/5 p-1 rounded-xl w-fit border border-white/10">
        <button
          onClick={() => setActiveTab("hot")}
          className={`flex items-center gap-2 px-5 py-2 text-sm font-bold rounded-lg transition-all ${
            activeTab === "hot" 
              ? "bg-red-500/20 text-red-400 border border-red-500/20 shadow-lg shadow-red-500/5" 
              : "text-zinc-400 hover:bg-white/5"
          }`}
        >
          <Flame size={16} /> AI 핫 섹터
        </button>
        <button
          onClick={() => setActiveTab("all")}
          className={`flex items-center gap-2 px-5 py-2 text-sm font-bold rounded-lg transition-all ${
            activeTab === "all" 
              ? "bg-indigo-500/20 text-indigo-400 border border-indigo-500/20 shadow-lg shadow-indigo-500/5" 
              : "text-zinc-400 hover:bg-white/5"
          }`}
        >
          <Layers size={16} /> 전체 섹터 지도
        </button>
        <button
          onClick={() => setActiveTab("shadow")}
          className={`flex items-center gap-2 px-5 py-2 text-sm font-bold rounded-lg transition-all ${
            activeTab === "shadow" 
              ? "bg-amber-500/20 text-amber-400 border border-amber-500/20 shadow-lg shadow-amber-500/5" 
              : "text-zinc-400 hover:bg-white/5"
          }`}
        >
          <Network size={16} /> AI 쉐도우 & 지분 맵
        </button>
      </div>

      {/* ── 핫 섹터 탭 ──────────────────────────────────────────────────────── */}
      {activeTab === "hot" && (
        <div className="flex flex-col gap-6">
          {hotLoading ? (
            <div className="stockcy-card p-10 flex flex-col items-center justify-center text-red-400 gap-4">
              <Activity size={32} className="animate-spin opacity-50" />
              <p className="text-sm font-medium animate-pulse">AI가 오늘의 핫 섹터를 분석 중입니다...</p>
            </div>
          ) : !(hotSectors as any)?.sectors ? (
            <div className="stockcy-card p-10 text-center text-zinc-400">데이터를 불러오지 못했습니다.</div>
          ) : (
            <div className="grid grid-cols-1 gap-6">
              {(hotSectors as any).sectors.map((sec: any, idx: number) => (
                <div key={idx} className="stockcy-card p-6 border-l-4 border-l-red-500 flex flex-col gap-4 hover:bg-white/5 transition-colors">
                  <div className="flex justify-between items-start">
                    <div>
                      <div className="flex items-center gap-3 mb-2">
                        <span className="text-xl font-black text-white">{sec.keyword}</span>
                        <span className="px-2 py-1 bg-red-500/20 text-red-400 text-xs font-bold rounded border border-red-500/30">
                          Hot Score: {sec.hot_score}/10
                        </span>
                      </div>
                      <p className="text-sm text-zinc-300 leading-relaxed">{sec.reason}</p>
                    </div>
                  </div>

                  {sec.dynamic_subsectors && sec.dynamic_subsectors.length > 0 && (
                    <div className="flex flex-wrap gap-2 mt-2">
                      {sec.dynamic_subsectors.map((sub: any, i: number) => {
                        const subName = typeof sub === "string" ? sub : sub.name;
                        return subName ? (
                          <span key={i} className="px-2.5 py-1 bg-white/5 text-zinc-300 text-xs rounded-full border border-white/10 font-medium">
                            #{subName}
                          </span>
                        ) : null;
                      })}
                    </div>
                  )}
                  
                  {sec.hot_codes && sec.hot_codes.length > 0 && (
                    <div className="mt-3 pt-3 border-t border-white/5">
                      <div className="text-[0.7rem] font-bold text-zinc-500 uppercase tracking-wider mb-2">주도 종목</div>
                      <div className="flex flex-wrap gap-2">
                        {sec.hot_codes.map((code: string, i: number) => {
                          const stockName = codeToNameMap[code] || code;
                          const priceData = bulkPrices ? (bulkPrices as any)[code] : null;
                          const signal = priceData ? getSignalBadge(priceData.change_pct) : getSignalBadge(null);
                          return (
                            <button
                              key={i}
                              onClick={() => setSelectedStock({ code, name: stockName, market: "국내" })}
                              className="text-xs px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 hover:text-white rounded transition-all font-medium border border-white/5 flex items-center gap-1.5 hover:scale-[1.03] active:scale-95 shadow-sm"
                              title={`${stockName} (${code}) - 클릭 시 AI 타점 상세 분석 모달 오픈`}
                            >
                              <span className="font-extrabold">{stockName}</span>
                              {priceData && (
                                <span className={`text-[0.65rem] font-bold ${priceData.change_pct > 0 ? 'text-red-400' : priceData.change_pct < 0 ? 'text-blue-400' : 'text-zinc-500'}`}>
                                  {priceData.change_pct > 0 ? '+' : ''}{priceData.change_pct.toFixed(1)}%
                                </span>
                              )}
                              <span className={`text-[0.58rem] px-1.5 py-0.5 rounded font-black border scale-90 ${signal.color}`}>
                                {signal.label}
                              </span>
                              <ChevronRight size={11} className="opacity-40" />
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── 전체 섹터 탭 ──────────────────────────────────────────────────────── */}
      {activeTab === "all" && (
        <div className="flex flex-col gap-6">
          {/* 시장 토글 (KR / US) */}
          <div className="flex gap-2">
            {(["KR", "US"] as const).map((mk) => (
              <button
                key={mk}
                onClick={() => { if (mapMarket !== mk) { setMapMarket(mk); setSelectedSector("전체"); setSearchQuery(""); } }}
                className={`px-4 py-1.5 rounded-lg text-sm font-bold transition-all ${
                  mapMarket === mk ? "bg-indigo-500 text-white shadow-md shadow-indigo-500/20" : "bg-white/5 text-zinc-400 hover:bg-white/10"
                }`}
              >
                {mk === "KR" ? "🇰🇷 국내" : "🇺🇸 미국"}
              </button>
            ))}
          </div>
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-400" size={18} />
            <input
              type="text"
              placeholder="종목명, 섹터명 검색 (예: 한미반도체, HBM)"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="stockcy-input w-full pl-10 py-3 text-sm bg-white/5 border border-white/10 rounded-lg focus:outline-none focus:border-indigo-500 transition-colors"
            />
          </div>

          {!searchQuery && (
            <div className="flex gap-2 overflow-x-auto pb-2 scrollbar-hide snap-x">
              <button
                onClick={() => setSelectedSector("전체")}
                className={`flex-shrink-0 px-4 py-2 rounded-full text-sm font-bold transition-all snap-start ${
                  selectedSector === "전체" ? "bg-indigo-500 text-white shadow-md shadow-indigo-500/20" : "bg-white/5 text-zinc-400 hover:bg-white/10"
                }`}
              >
                전체
              </button>
              {sectorNames.map((name) => (
                <button
                  key={name}
                  onClick={() => setSelectedSector(name)}
                  className={`flex-shrink-0 px-4 py-2 rounded-full text-sm font-bold transition-all snap-start ${
                    selectedSector === name ? "bg-indigo-500 text-white shadow-md shadow-indigo-500/20" : "bg-white/5 text-zinc-400 hover:bg-white/10"
                  }`}
                >
                  {name}
                </button>
              ))}
            </div>
          )}

          {activeMapLoading ? (
            <div className="stockcy-card p-10 text-center text-zinc-400">섹터 지도를 불러오는 중...</div>
          ) : filteredData.length === 0 ? (
            <div className="stockcy-card p-10 text-center text-zinc-500">
              검색 결과가 없습니다.
            </div>
          ) : (
            <div className="flex flex-col gap-8">
              {filteredData.map((item, idx) => (
                <div key={idx} className="flex flex-col gap-4 animate-in slide-in-from-bottom-2 duration-300">
                  <h2 className="text-xl font-bold text-indigo-300 border-b border-indigo-500/20 pb-2 flex items-center gap-2">
                    <Layers size={20} className="text-indigo-400" /> {item.sector}
                  </h2>
                  
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {item.subSectors.map((sub, sIdx) => {
                      const subKey = `${item.sector}-${sub.name}`;
                      const isExpanded = expandedSubs[subKey] !== false;
                      
                      return (
                        <div key={sIdx} className="stockcy-card border border-white/5 overflow-hidden flex flex-col bg-zinc-900/50">
                          <div 
                            className="p-3 bg-white/5 flex flex-col cursor-pointer hover:bg-white/10 transition-colors"
                            onClick={() => toggleSub(subKey)}
                          >
                            <div className="flex justify-between items-center">
                              <h3 className="text-sm font-bold text-white flex items-center gap-2">
                                {sub.name}
                                <span className="text-[0.65rem] font-normal bg-black/30 text-zinc-400 px-2 py-0.5 rounded-full">
                                  {sub.stocks.length}종목
                                </span>
                              </h3>
                              <ChevronDown size={16} className={`text-zinc-500 transition-transform ${isExpanded ? "rotate-180" : ""}`} />
                            </div>
                            
                            {SUB_SECTOR_DESC[sub.name] && (
                              <p className="text-[0.7rem] text-zinc-400 mt-2 leading-relaxed flex items-start gap-1">
                                <Info size={12} className="text-indigo-400 mt-0.5 flex-shrink-0" />
                                {SUB_SECTOR_DESC[sub.name]}
                              </p>
                            )}
                          </div>

                          {isExpanded && (
                            <div className="p-3 grid grid-cols-1 sm:grid-cols-2 gap-2">
                              {sub.stocks.slice(0, SECTOR_STOCK_CAP).map((s: any, i: number) => {
                                const priceData = mapMarket === "US"
                                  ? (usMapPrices ? (usMapPrices as any)[s.code] : null)
                                  : (bulkPrices ? (bulkPrices as any)[s.code] : null);
                                const signal = priceData ? getSignalBadge(priceData.change_pct) : getSignalBadge(null);
                                return (
                                  <div 
                                    key={i}
                                    onClick={() => setSelectedStock({ code: s.code, name: s.name, market: mapMarket === "US" ? "미국" : "국내" })}
                                    className="group flex justify-between items-center p-2.5 rounded bg-black/20 hover:bg-indigo-500/10 border border-transparent hover:border-indigo-500/30 cursor-pointer transition-all hover:scale-[1.02] active:scale-98"
                                    title={`${s.name} (${s.code}) - 클릭 시 AI 타점 상세 분석 모달 오픈`}
                                  >
                                    <div className="flex flex-col overflow-hidden mr-2">
                                      <div className="flex items-center gap-1.5 flex-wrap">
                                        <span className="text-[0.85rem] font-bold text-zinc-300 group-hover:text-indigo-300 truncate" title={s.name}>
                                          {s.name}
                                        </span>
                                        <span className={`text-[0.55rem] px-1.5 py-0.2 rounded font-black border scale-[0.85] origin-left ${signal.color}`}>
                                          {signal.label}
                                        </span>
                                      </div>
                                      <span className="text-[0.65rem] text-zinc-500 font-mono mt-0.5">
                                        {s.code}
                                      </span>
                                    </div>
                                    {priceData ? (
                                      <div className="flex flex-col items-end flex-shrink-0">
                                        <span className="text-[0.8rem] font-bold text-white">
                                          {mapMarket === "US" ? `$${priceData.price.toFixed(2)}` : `₩${priceData.price.toLocaleString()}`}
                                        </span>
                                        <span className={`text-[0.65rem] font-bold mt-0.5 ${priceData.change_pct > 0 ? 'text-red-400' : priceData.change_pct < 0 ? 'text-blue-400' : 'text-zinc-500'}`}>
                                          {priceData.change_pct > 0 ? '+' : ''}{priceData.change_pct.toFixed(2)}%
                                        </span>
                                      </div>
                                    ) : (
                                      <span className="text-[0.65rem] text-zinc-600 flex-shrink-0 animate-pulse">로딩중...</span>
                                    )}
                                  </div>
                                );
                              })}
                              {sub.stocks.length > SECTOR_STOCK_CAP && (
                                <div className="col-span-full text-center text-[0.68rem] text-zinc-500 py-1">
                                  외 {sub.stocks.length - SECTOR_STOCK_CAP}종목 — 검색으로 좁혀보세요
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── AI 쉐도우 & 지분 맵 탭 ─────────────────────────────────────────────────── */}
      {activeTab === "shadow" && (
        <div className="flex flex-col gap-8 animate-in slide-in-from-bottom-2 duration-300">
          
          {/* 1. 실시간 RAG 즉석 쉐도우 검색기 (Shadow Searcher) */}
          <div className="stockcy-card p-6 border border-amber-500/10 bg-amber-500/5 shadow-lg shadow-amber-500/5 relative overflow-hidden">
            <div className="absolute top-0 right-0 p-4 opacity-5 pointer-events-none">
              <Sparkles size={100} className="text-amber-400" />
            </div>
            <div className="flex items-center gap-2 mb-3">
              <Sparkles className="text-amber-400 animate-pulse" size={20} />
              <h2 className="text-lg font-black text-amber-300">실시간 AI 쉐도우 즉석 탐색기 (Shadow Searcher)</h2>
            </div>
            <p className="text-xs text-zinc-400 mb-4 leading-relaxed">
              임의의 비상장사, 글로벌 기업, 인물 또는 메가 트렌드 키워드(예: <b>트럼프</b>, <b>스타링크</b>, <b>컬리</b>, <b>토스 IPO</b> 등)를 입력하세요.<br />
              AI가 실시간 구글 뉴스 및 DART 공시 RAG 검색을 통해 **숨겨진 지분 관계를 가진 국내/미국 상장 수혜주 족보**를 즉석 발굴해 냅니다.
            </p>
            <div className="flex gap-2">
              <div className="relative flex-1">
                <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 text-zinc-500" size={18} />
                <input
                  type="text"
                  placeholder="발굴하고 싶은 쉐도우 키워드를 입력하세요... (예: 트럼프, 스타링크, 토스)"
                  value={shadowSearchQuery}
                  onChange={(e) => setShadowSearchQuery(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && runShadowDiscover()}
                  className="stockcy-input w-full py-3 text-sm bg-black/40 border border-white/10 rounded-lg focus:outline-none focus:border-amber-500 transition-colors text-white"
                  style={{ paddingLeft: "42px" }}
                />
              </div>
              <button
                onClick={runShadowDiscover}
                disabled={shadowDiscoverStatus === "loading" || !shadowSearchQuery.trim()}
                className="px-6 py-3 bg-amber-500 hover:bg-amber-400 text-black font-black text-sm rounded-lg transition-colors flex items-center gap-2 shadow-lg shadow-amber-500/20 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {shadowDiscoverStatus === "loading" ? (
                  <>
                    <Activity size={16} className="animate-spin" />
                    RAG 분석중...
                  </>
                ) : (
                  <>
                    <Search size={16} />
                    쉐도우 탐색
                  </>
                )}
              </button>
            </div>

            {/* 1-1. 실시간 RAG 검색 진행 & 결과 노출 패널 */}
            {shadowDiscoverStatus !== "idle" && (
              <div className="mt-4 pt-4 border-t border-white/5 animate-in fade-in duration-300">
                {shadowDiscoverStatus === "loading" ? (
                  <div className="flex flex-col items-center justify-center py-6 text-amber-400/80 gap-3 bg-black/30 rounded-lg border border-white/5">
                    <Activity size={24} className="animate-spin text-amber-500" />
                    <span className="text-xs font-bold animate-pulse text-zinc-300">{shadowDiscoverMsg}</span>
                  </div>
                ) : shadowDiscoverStatus === "error" ? (
                  <div className="p-4 bg-red-500/10 border border-red-500/20 text-red-400 text-xs rounded-lg flex items-start gap-2">
                    <ShieldAlert size={16} className="flex-shrink-0 mt-0.5" />
                    <div>{shadowDiscoverMsg}</div>
                  </div>
                ) : shadowDiscoverResult ? (
                  <div className="flex flex-col gap-4 animate-in slide-in-from-top-2 duration-300">
                    <div className="bg-black/30 p-3 rounded-lg border border-white/5 flex justify-between items-center text-xs">
                      <div className="text-zinc-300">
                        발굴 키워드: <span className="text-amber-400 font-bold">"{shadowDiscoverResult.anchor_keyword}"</span>
                        <p className="text-[0.7rem] text-zinc-400 mt-1 leading-relaxed">{shadowDiscoverResult.discovery_summary}</p>
                      </div>
                      <span className="px-2 py-0.5 bg-amber-500/10 text-amber-400 rounded-full text-[0.6rem] font-bold border border-amber-500/20">
                        AI RAG Live
                      </span>
                    </div>

                    {/* 발굴된 종목 그리드 */}
                    {shadowDiscoverResult.stocks && shadowDiscoverResult.stocks.length > 0 ? (
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        {shadowDiscoverResult.stocks.map((s: any, idx: number) => {
                          const priceData = s.market === "KR" 
                            ? (bulkPrices ? (bulkPrices as any)[s.ticker] : null)
                            : (usPriceMap ? usPriceMap[s.ticker.toUpperCase()] : null);
                          const signal = priceData ? getSignalBadge(priceData.change_pct) : getSignalBadge(null);
                          return (
                            <div 
                              key={idx}
                              onClick={() => setSelectedStock({ code: s.ticker, name: s.name, market: s.market === "KR" ? "국내" : "미국" })}
                              className="stockcy-card p-4 border border-white/5 bg-zinc-950/40 hover:bg-amber-500/5 hover:border-amber-500/20 transition-all cursor-pointer group flex flex-col gap-2 relative hover:scale-[1.02] active:scale-98"
                              title={`${s.name} (${s.ticker}) - 클릭 시 AI 타점 상세 분석 모달 오픈`}
                            >
                              <div className="flex justify-between items-start">
                                <div>
                                  <div className="flex items-center gap-2 flex-wrap">
                                    <span className="text-sm font-bold text-white group-hover:text-amber-400 transition-colors">{s.name}</span>
                                    <span className="text-[0.65rem] font-mono bg-black/40 text-zinc-500 px-1.5 py-0.5 rounded">
                                      {s.ticker}
                                    </span>
                                    <span className={`text-[0.55rem] font-bold px-1.5 py-0.5 rounded ${s.market === 'KR' ? 'bg-red-500/10 text-red-400' : 'bg-blue-500/10 text-blue-400'}`}>
                                      {s.market === 'KR' ? '국내' : '미국'}
                                    </span>
                                    {priceData && (
                                      <span className="text-xs font-mono font-bold text-zinc-300 ml-1">
                                        {s.market === 'KR' ? `₩${priceData.price.toLocaleString()}` : `$${priceData.price.toFixed(2)}`}
                                        <span className={`ml-1.5 text-[0.7rem] ${priceData.change_pct > 0 ? 'text-red-400' : priceData.change_pct < 0 ? 'text-blue-400' : 'text-zinc-500'}`}>
                                          {priceData.change_pct > 0 ? '+' : ''}{priceData.change_pct.toFixed(1)}%
                                        </span>
                                      </span>
                                    )}
                                    <span className={`text-[0.55rem] px-1.5 py-0.2 rounded font-black border scale-[0.85] origin-left ${signal.color}`}>
                                      {signal.label}
                                    </span>
                                  </div>
                                  <p className="text-[0.75rem] text-zinc-300 mt-1.5 font-medium leading-relaxed flex items-center gap-1">
                                    <GitBranch size={12} className="text-amber-500" />
                                    {s.relationship}
                                  </p>
                                </div>
                                <span className={`px-1.5 py-0.5 text-[0.55rem] font-bold rounded flex items-center gap-0.5 ${s.credibility === '상' ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' : 'bg-yellow-500/10 text-yellow-400 border border-yellow-500/20'}`}>
                                  팩트: {s.credibility === '상' ? '공식' : '미확인'}
                                </span>
                              </div>
                              
                              {s.risk_guide && (
                                <div className="mt-2 pt-2 border-t border-white/5 text-[0.65rem] text-zinc-400 flex items-start gap-1 bg-black/20 p-2 rounded">
                                  <ShieldAlert size={12} className="text-amber-500 mt-0.5 flex-shrink-0" />
                                  <span className="leading-normal">{s.risk_guide}</span>
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    ) : (
                      <div className="p-6 text-center text-xs text-zinc-500 bg-black/20 rounded-lg">
                        해당 키워드와 연동된 쉐도우 종목을 발굴하지 못했습니다. 다른 키워드를 입력해 보세요.
                      </div>
                    )}
                  </div>
                ) : null}
              </div>
            )}
          </div>

          {/* 2. 10대 대표 지분연동 앵커 셀렉터 */}
          <div className="flex flex-col gap-3">
            <h3 className="text-sm font-bold text-zinc-400 uppercase tracking-wider flex items-center gap-2">
              <Network size={16} className="text-amber-500" /> 10대 시장 주도 쉐도우 앵커 선택
            </h3>
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3">
              {SHADOW_ANCHORS.map((anchor) => {
                const isActive = selectedAnchor === anchor.id;
                return (
                  <button
                    key={anchor.id}
                    onClick={() => setSelectedAnchor(anchor.id)}
                    className={`p-4 rounded-xl border flex flex-col text-left transition-all ${
                      isActive 
                        ? "bg-amber-500/10 border-amber-500/30 shadow-lg shadow-amber-500/5" 
                        : "bg-white/5 border-white/5 hover:bg-white/10 hover:border-white/10"
                    }`}
                  >
                    <span className={`text-[0.8rem] font-bold transition-colors ${isActive ? 'text-amber-400' : 'text-zinc-200'}`}>
                      {anchor.name}
                    </span>
                    <span className="text-[0.6rem] text-zinc-400 mt-1 line-clamp-1">
                      {anchor.desc}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* 3. 앵커 하위 쉐도우 연관 종목 네트워크 맵 */}
          {activeAnchorData && (
            <div className="stockcy-card p-6 border border-white/5 bg-zinc-950/40 animate-in fade-in duration-300">
              <div className="flex flex-col md:flex-row md:justify-between md:items-start gap-4 mb-6 pb-4 border-b border-white/5">
                <div>
                  <div className="flex items-center gap-2 mb-1.5">
                    <span className="text-lg font-black text-white">{activeAnchorData.name}</span>
                    <span className="px-2 py-0.5 bg-amber-500/10 text-amber-400 text-[0.65rem] font-bold rounded border border-amber-500/20">
                      Anchor Ecosystem
                    </span>
                  </div>
                  <p className="text-xs text-zinc-400">{activeAnchorData.desc}</p>
                </div>
                <div className="text-right text-[0.65rem] text-zinc-500 leading-normal max-w-xs bg-black/20 p-2.5 rounded border border-white/5 flex items-start gap-1.5">
                  <HelpCircle size={14} className="text-amber-500 flex-shrink-0 mt-0.5" />
                  <span>
                    지분 보유 및 밸류체인 관계는 공식 분기보고서 및 공시 데이터를 바탕으로 도출되었습니다. 찌라시/루머의 경우 극도 경계가 필요합니다.
                  </span>
                </div>
              </div>

              {/* 종목 연결 네트워크 그리드 */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6 relative">
                {activeAnchorData.stocks.map((stock, idx) => {
                  const priceData = stock.market === "KR" 
                    ? (bulkPrices ? (bulkPrices as any)[stock.code] : null)
                    : (usPriceMap ? usPriceMap[stock.code.toUpperCase()] : null);
                  const signal = priceData ? getSignalBadge(priceData.change_pct) : getSignalBadge(null);
                  return (
                    <div 
                      key={idx} 
                      onClick={() => setSelectedStock({ code: stock.code, name: stock.name, market: stock.market === "KR" ? "국내" : "미국" })}
                      className="stockcy-card p-5 border border-white/5 bg-black/30 hover:bg-amber-500/5 hover:border-amber-500/20 cursor-pointer group transition-all flex flex-col gap-3 relative overflow-hidden hover:scale-[1.02] active:scale-98"
                      title={`${stock.name} (${stock.code}) - 클릭 시 AI 타점 상세 분석 모달 오픈`}
                    >
                      <div className="absolute top-0 right-0 p-2 opacity-5">
                        <Link2 size={60} />
                      </div>

                      <div className="flex justify-between items-start">
                        <div>
                          <div className="flex items-center gap-1.5 flex-wrap">
                            <span className="text-[0.95rem] font-extrabold text-white group-hover:text-amber-400 transition-colors">
                              {stock.name}
                            </span>
                            <span className="text-[0.65rem] font-mono text-zinc-500 bg-black/40 px-1 py-0.5 rounded">
                              {stock.code}
                            </span>
                            {priceData && (
                              <span className="text-xs font-mono font-bold text-zinc-300 ml-1">
                                {stock.market === 'KR' ? `₩${priceData.price.toLocaleString()}` : `$${priceData.price.toFixed(2)}`}
                                <span className={`ml-1.5 text-[0.7rem] ${priceData.change_pct > 0 ? 'text-red-400' : priceData.change_pct < 0 ? 'text-blue-400' : 'text-zinc-500'}`}>
                                  {priceData.change_pct > 0 ? '+' : ''}{priceData.change_pct.toFixed(1)}%
                                </span>
                              </span>
                            )}
                            <span className={`text-[0.55rem] px-1.5 py-0.2 rounded font-black border scale-[0.85] origin-left ${signal.color}`}>
                              {signal.label}
                            </span>
                          </div>
                          <span className={`inline-block text-[0.55rem] font-bold px-1.5 py-0.5 rounded mt-1 bg-red-500/10 text-red-400`}>
                            {stock.market === 'KR' ? '국내상장' : '미국상장'}
                          </span>
                        </div>

                        <span className={`px-2 py-0.5 rounded text-[0.6rem] font-extrabold flex items-center gap-0.5 ${stock.credibility === '상' ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' : 'bg-yellow-500/10 text-yellow-400 border border-yellow-500/20'}`}>
                          팩트: {stock.credibility === '상' ? '공식' : '미확인'}
                        </span>
                      </div>

                      {/* 지분 구조 및 관계 파스 */}
                      <div className="bg-black/40 p-3 rounded-lg flex flex-col gap-1.5 border border-white/5">
                        <div className="flex justify-between text-xs">
                          <span className="text-zinc-500">지분/투자 형태</span>
                          <span className="text-amber-400 font-extrabold">{stock.rate}</span>
                        </div>
                        <p className="text-[0.7rem] text-zinc-300 leading-normal flex items-start gap-1 mt-1">
                          <GitBranch size={12} className="text-amber-500 mt-0.5 flex-shrink-0" />
                          <span>{stock.relation}</span>
                        </p>
                      </div>

                      {/* 리스크 가이드 */}
                      <div className="text-[0.65rem] text-zinc-400 flex items-start gap-1 p-2 bg-red-500/5 rounded border border-red-500/10">
                        <ShieldAlert size={12} className="text-red-400 mt-0.5 flex-shrink-0" />
                        <span className="leading-relaxed font-medium">{stock.risk}</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}
      {selectedStock && <StockModal stock={selectedStock} onClose={() => setSelectedStock(null)} />}
    </div>
  );
}
