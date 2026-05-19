# RAG 품질 저하 단계별 진단 리포트

## 전체 요약

- 총 분석 query 수: 54
- 실패/의심 케이스 수: 30
- 원인별 분포:
  - crawler/data 부족: 9
  - query rewrite 문제: 0
  - keyword/category/filter: 5
  - lexical search 문제: 3
  - vector search 문제: 0
  - hybrid merge 문제: 2
  - rerank 문제: 1
  - fallback 문제: 0
  - final generation 문제: 1
  - mixed: 6
  - out_of_scope: 3

## 데이터/크롤러 품질

| gap | count |
| --- | --- |
| documents_without_chunks | 0 |
| chunks_without_embeddings | 0 |
| documents_without_contents | 0 |
| assets_without_extracted_content | 4532 |
| very_short_chunks_lt_120 | 88 |

해석: documents/chunks/embeddings의 큰 적재 누락은 제한적이지만, assets_without_extracted_content와 very_short_chunks가 검색 잡음 및 답변 누락 리스크다.

## 대표 실패 케이스

### Query ID: 279

원 질문: 콜라보라운지 운영 시간
Rewrite: 콜라보라운지 운영 시간
Intent: GENERAL
Keywords: ['콜라보라운지', '운영', '시간']
Category: None
Filters: {}

최종 답변: 잘 이해하지 못했어요.
학교 관련 질문을 해주시면 더 정확히 도와드릴게요!
문제 요약: DB evidence exists, but intent/routing bypassed RAG.

검색 후보:
- lexical top 결과: 1. [대학혁신지원사업] 2026-1 지역사회와 시퀀스포토 교과 운영 안내 (0.375000013969838); 2. 연구∙개발 성과 | 연구∙개발 | 콜라보교육센터 (0.375000013969838); 3. [대학혁신지원사업] 2026-1 로컬 케어 인류의 모험 교과 운영 안내 (0.333333338631524)
- vector top 결과: 1. 동의대학교 대외협력팀 (0.446988562287946); 2. [대학혁신지원사업] 2026-1 로컬 케어 인류의 모험 교과 운영 안내 (0.443776673820415); 3. 찾아오시는 길 | 센터 소개 | 콜라보교육센터 (0.440426545130417)
- hybrid top 결과: 1. 동의대학교 대외협력팀 (0.6); 2. [대학혁신지원사업] 2026-1 로컬 케어 인류의 모험 교과 운영 안내 (0.5956886299938987); 3. 찾아오시는 길 | 센터 소개 | 콜라보교육센터 (0.5911916978940926)
- rerank 후 결과: 1. [대학혁신지원사업] 2026-1 로컬 케어 인류의 모험 교과 운영 안내 (3.868757); 2. [대학혁신지원사업] 2026-1학기 콜라보체험활동 팀 프로젝트 신청 안내 (2.78533); 3. [대학혁신지원사업] 2025-2학기 콜라보체험활동 팀활동지원비 서류 제출 및 환수 관련 안내 (2.731336)
- selected chunks: 1. [대학혁신지원사업] 2026-1 로컬 케어 인류의 모험 교과 운영 안내 (3.868757); 2. [대학혁신지원사업] 2026-1학기 콜라보체험활동 팀 프로젝트 신청 안내 (2.78533); 3. [대학혁신지원사업] 2025-2학기 콜라보체험활동 팀활동지원비 서류 제출 및 환수 관련 안내 (2.731336)

정답 근거 DB 존재 여부: 있음
- 근거 탐색어: 콜라보라운지, 콜라보라운지 운영 시간
- evidence ranks: {'lexical': None, 'vector': None, 'hybrid': None, 'reranked': None, 'selected': None}

원인 분류: keyword/category/filter / query_analysis
수정 제안: intent/category/filter 추출을 보수화하고, 고유명사 보존 및 filter relaxation fallback을 추가한다.

### Query ID: 281

원 질문: 정보관 학생 식당 몇시에 열어?
Rewrite: 정보관 학생 식당 몇시 열어
Intent: INFO
Keywords: ['정보관', '학생', '식당', '몇시', '열어']
Category: None
Filters: {}

최종 답변: 안녕하세요. 동의대학교 정보 안내를 도와드리고 있어요. 학사, 장학, 기숙사, 통학버스 같은 학교 정보를 물어봐 주세요.

사이트 바로가기: https://www.deu.ac.kr/
문제 요약: Evidence exists, but logged retrieval returned or selected zero chunks.

검색 후보:
- lexical top 결과: 1. 모바일학생증 발급 (0.555555553200804); 2. [현장실습지원센터] 2026학년도 하계 단기 표준현장실습학기제 학생 참여 안내 (0.512195124787847); 3. 모바일학생증 발급 (0.500000000372529)
- vector top 결과: 1. 동의대학교 효민생활관 (0.489304574893814); 2. 동의대학교 효민생활관 (0.481536452403914); 3. 기숙사 | 유학생활 | 외국인 입학 | 국제교류처 국제교류팀 (0.461225991102938)
- hybrid top 결과: 1. 기숙사 | 유학생활 | 외국인 입학 | 국제교류처 국제교류팀 (0.9163384297773547); 2. 복지문화시설 | 편의·복지 | 대학생활 (0.8494603045949323); 3. 동의대학교 효민생활관 (0.6)
- rerank 후 결과: 1. 기숙사 | 유학생활 | 외국인 입학 | 국제교류처 국제교류팀 (2.36); 2. 복지문화시설 | 편의·복지 | 대학생활 (2.272419); 3. 복지문화시설 | 편의·복지 | 대학생활 (1.865127)
- selected chunks: 1. 기숙사 | 유학생활 | 외국인 입학 | 국제교류처 국제교류팀 (2.36); 2. 복지문화시설 | 편의·복지 | 대학생활 (2.272419); 3. 동의대학교 효민생활관 (1.126902)

정답 근거 DB 존재 여부: 있음
- 근거 탐색어: 정보관, 정보관 학생 식당 몇시 열어, 정보관 학생 식당 몇시에 열어?
- evidence ranks: {'lexical': None, 'vector': None, 'hybrid': None, 'reranked': None, 'selected': None}

원인 분류: lexical search 문제 / retrieval_empty
수정 제안: 후보 로그를 추가한 뒤 동일 query를 재실행해 탈락 단계를 확정한다.

### Query ID: 285

원 질문: 정보공학관 정보
Rewrite: 정보공학관
Intent: GENERAL
Keywords: ['정보공학관', '정보']
Category: None
Filters: {}

최종 답변: 잘 이해하지 못했어요.
학교 관련 질문을 해주시면 더 정확히 도와드릴게요!
문제 요약: DB evidence exists, but intent/routing bypassed RAG.

검색 후보:
- lexical top 결과: 1. 임용정보 | 교직과 (0.523809524147419); 2. [한국장애인개발원] 장애청년 채용 취업 정보 안내(12월 2차) (0.5); 3. [한국장애인개발원] 장애청년 채용 취업 정보 안내(12월 1차) (0.5)
- vector top 결과: 1. 약사 | 학과소개 | 컴퓨터공학과 (0.547877426002681); 2. 진로 | 학과소개 | 컴퓨터공학과 (0.525668504913871); 3. 대학 | 교육 (0.516321005382661)
- hybrid top 결과: 1. 약사 | 학과소개 | 컴퓨터공학과 (0.6); 2. 진로 | 학과소개 | 컴퓨터공학과 (0.5756782228636286); 3. 대학 | 교육 (0.5654414446126143)
- rerank 후 결과: 1. 학과사무실 위치 및 연락처 | 학과소개 | 컴퓨터공학과 (3.863428); 2. 컴퓨터 시스템 실습실 | 실습실 | 컴퓨터공학과 (3.850909); 3. 인사말 | 학과소개 | 컴퓨터공학과 (-0.138567)
- selected chunks: 1. 학과사무실 위치 및 연락처 | 학과소개 | 컴퓨터공학과 (3.863428); 2. 컴퓨터 시스템 실습실 | 실습실 | 컴퓨터공학과 (3.850909); 3. 인사말 | 학과소개 | 컴퓨터공학과 (-0.138567)

정답 근거 DB 존재 여부: 있음
- 근거 탐색어: 정보공학관, 정보공학관 정보
- evidence ranks: {'lexical': 4, 'vector': None, 'hybrid': None, 'reranked': None, 'selected': None}

원인 분류: keyword/category/filter / query_analysis
수정 제안: intent/category/filter 추출을 보수화하고, 고유명사 보존 및 filter relaxation fallback을 추가한다.

### Query ID: 286

원 질문: 정보공학관 위치
Rewrite: 정보공학관 위치
Intent: GENERAL
Keywords: ['정보공학관', '위치']
Category: None
Filters: {}

최종 답변: 잘 이해하지 못했어요.
학교 관련 질문을 해주시면 더 정확히 도와드릴게요!
문제 요약: DB evidence exists, but intent/routing bypassed RAG.

검색 후보:
- lexical top 결과: 1. 컴퓨터 시스템 실습실 | 실습실 | 컴퓨터공학과 (0.333333334657881); 2. 컴퓨터 소프트웨어 실습실 | 실습실 | 컴퓨터공학과 (0.333333334657881); 3. 임용정보 | 교직과 (0.333333334657881)
- vector top 결과: 1. 학과사무실 위치 및 연락처 | 학과소개 | 컴퓨터공학과 (0.562189120854894); 2. 위치 및 연락처 | 학과소개 | 컴퓨터소프트웨어학과 (0.53434377499297); 3. 2026학년도 신입생 수강신청 관련 안내(신입생 필독) (0.522342500407398)
- hybrid top 결과: 1. 2026학년도 신입생 수강신청 관련 안내(신입생 필독) (0.8449403351352236); 2. 학과사무실 위치 및 연락처 | 학과소개 | 컴퓨터공학과 (0.6); 3. 위치 및 연락처 | 학과소개 | 컴퓨터소프트웨어학과 (0.5702818733102687)
- rerank 후 결과: 1. 2026학년도 1학기 1학년 신입생 및 복학생 수강신청 안내 (6.044427); 2. 학과사무실 위치 및 연락처 | 학과소개 | 컴퓨터공학과 (5.052131); 3. 위치 및 연락처 | 학과소개 | 컴퓨터소프트웨어학과 (4.359925)
- selected chunks: 1. 2026학년도 1학기 1학년 신입생 및 복학생 수강신청 안내 (6.044427); 2. 학과사무실 위치 및 연락처 | 학과소개 | 컴퓨터공학과 (5.052131); 3. 위치 및 연락처 | 학과소개 | 컴퓨터소프트웨어학과 (4.359925)

정답 근거 DB 존재 여부: 있음
- 근거 탐색어: 정보공학관, 정보공학관 위치
- evidence ranks: {'lexical': None, 'vector': None, 'hybrid': None, 'reranked': None, 'selected': None}

원인 분류: keyword/category/filter / query_analysis
수정 제안: intent/category/filter 추출을 보수화하고, 고유명사 보존 및 filter relaxation fallback을 추가한다.

### Query ID: 289

원 질문: 셔틀 버스 정보
Rewrite: 셔틀 버스 정보
Intent: INFO
Keywords: ['셔틀', '버스', '정보']
Category: None
Filters: {}

최종 답변: 안녕하세요. 동의대학교 정보 안내를 도와드리고 있어요. 학사, 장학, 기숙사, 통학버스 같은 학교 정보를 물어봐 주세요.

사이트 바로가기: https://www.deu.ac.kr/
문제 요약: No precise DB evidence was found for strong query terms.

검색 후보:
- lexical top 결과: 1. [한국장애인개발원] 장애청년 채용 취업 정보 안내(1월 1차) (0.523809524485313); 2. [한국장애인개발원] 장애청년 채용 취업 정보 안내(1월 1차) (0.523809524485313); 3. [한국장애인개발원] 장애청년 채용 취업 정보 안내(12월 2차) (0.523809524485313)
- vector top 결과: 1. 셔틀버스 안내 | 캠퍼스안내 | DEU (0.525972275377973); 2. 시외통학버스 | 편의·복지 | 대학생활 (0.445375422719906); 3. 시외통학버스 | 편의·복지 | 대학생활 (0.442385478090807)
- hybrid top 결과: 1. 셔틀버스 안내 | 캠퍼스안내 | DEU (0.9818181813255817); 2. 시외통학버스 | 편의·복지 | 대학생활 (0.5080595805927428); 3. 시외통학버스 | 편의·복지 | 대학생활 (0.5046488175897496)
- rerank 후 결과: 1. 셔틀버스 안내 | 캠퍼스안내 | DEU (5.683333); 2. 2026학년도 1학기 시외통학버스 신청 안내(수정) (5.095695); 3. 2026학년도 1학기 시외통학버스 신청 안내(수정) (4.581279)
- selected chunks: 1. 셔틀버스 안내 | 캠퍼스안내 | DEU (5.683333); 2. 2026학년도 1학기 시외통학버스 신청 안내(수정) (5.095695); 3. 시외통학버스 | 편의·복지 | 대학생활 (4.354295)

정답 근거 DB 존재 여부: 없음/불확실
- 근거 탐색어: 셔틀 버스 정보
- evidence ranks: {'lexical': None, 'vector': None, 'hybrid': None, 'reranked': None, 'selected': None}

원인 분류: crawler/data 부족 / data
수정 제안: 첨부/본문 추출 누락과 짧은 chunk를 우선 정리하고 source metadata를 강화한다.

### Query ID: 290

원 질문: 안녕
Rewrite: 안녕
Intent: GENERAL
Keywords: ['안녕']
Category: None
Filters: {}

최종 답변: 안녕하세요! 동의대 신입생 정보 안내 챗봇 동구입니다.
문제 요약: RAG was bypassed and no precise DB evidence was found.

검색 후보:
- lexical top 결과: 1. [RISE] 제 6회 지역상생 네트워크 부산진구 연합 청년창업캠프 모집 (0.333333333333333); 2. [RISE] 제 12회 부산 창업 아이디어 경진대회 참가자 모집 안내 (0.333333333333333); 3. [동의대학교] 2026학년도 D-COSS BIO 포렌식 범죄 프로파일링 경진대회 신청 안내 (0.333333333333333)
- vector top 결과: 1. 동의대학교 미래교육원 > 학점은행제 > 경영과 > 인사말 (0.299976891283366); 2. 어린이집 소개 (0.266900376492762); 3. 동의대학교 미래교육원 > 학점은행제 > 경영과 > 인사말 (0.257183447052039)
- hybrid top 결과: 1. 동의대학교 미래교육원 > 학점은행제 > 경영과 > 인사말 (0.6); 2. 어린이집 소개 (0.5338418743208607); 3. 동의대학교 미래교육원 > 학점은행제 > 경영과 > 인사말 (0.5144065183523022)
- rerank 후 결과: 1. 동의대학교 미래교육원 > 학점은행제 > 경영과 > 인사말 (-0.8); 2. 어린이집 소개 (-0.932316); 3. 동의대학교 미래교육원 > 학점은행제 > 경영과 > 인사말 (-0.971187)
- selected chunks: 1. 동의대학교 미래교육원 > 학점은행제 > 경영과 > 인사말 (-0.8); 2. 어린이집 소개 (-0.932316); 3. 동의대학교 미래교육원 > 학점은행제 > 재무부동산과 > 인사말 (-1.02947)

정답 근거 DB 존재 여부: 없음/불확실
- 근거 탐색어: 없음
- evidence ranks: {'lexical': None, 'vector': None, 'hybrid': None, 'reranked': None, 'selected': None}

원인 분류: crawler/data 부족 / data
수정 제안: 첨부/본문 추출 누락과 짧은 chunk를 우선 정리하고 source metadata를 강화한다.

### Query ID: 291

원 질문: 셔틀 버스 정보
Rewrite: 셔틀 버스 정보
Intent: INFO
Keywords: ['셔틀', '버스', '정보']
Category: None
Filters: {}

최종 답변: 안녕하세요. 동의대학교 정보 안내를 도와드리고 있어요. 학사, 장학, 기숙사, 통학버스 같은 학교 정보를 물어봐 주세요.

사이트 바로가기: https://www.deu.ac.kr/
문제 요약: No precise DB evidence was found for strong query terms.

검색 후보:
- lexical top 결과: 1. [한국장애인개발원] 장애청년 채용 취업 정보 안내(1월 1차) (0.523809524485313); 2. [한국장애인개발원] 장애청년 채용 취업 정보 안내(1월 1차) (0.523809524485313); 3. [한국장애인개발원] 장애청년 채용 취업 정보 안내(12월 2차) (0.523809524485313)
- vector top 결과: 1. 셔틀버스 안내 | 캠퍼스안내 | DEU (0.525972275377973); 2. 시외통학버스 | 편의·복지 | 대학생활 (0.445375422719906); 3. 시외통학버스 | 편의·복지 | 대학생활 (0.442385478090807)
- hybrid top 결과: 1. 셔틀버스 안내 | 캠퍼스안내 | DEU (0.9818181813255817); 2. 시외통학버스 | 편의·복지 | 대학생활 (0.5080595805927428); 3. 시외통학버스 | 편의·복지 | 대학생활 (0.5046488175897496)
- rerank 후 결과: 1. 셔틀버스 안내 | 캠퍼스안내 | DEU (5.683333); 2. 2026학년도 1학기 시외통학버스 신청 안내(수정) (5.095695); 3. 2026학년도 1학기 시외통학버스 신청 안내(수정) (4.581279)
- selected chunks: 1. 셔틀버스 안내 | 캠퍼스안내 | DEU (5.683333); 2. 2026학년도 1학기 시외통학버스 신청 안내(수정) (5.095695); 3. 시외통학버스 | 편의·복지 | 대학생활 (4.354295)

정답 근거 DB 존재 여부: 없음/불확실
- 근거 탐색어: 셔틀 버스 정보
- evidence ranks: {'lexical': None, 'vector': None, 'hybrid': None, 'reranked': None, 'selected': None}

원인 분류: crawler/data 부족 / data
수정 제안: 첨부/본문 추출 누락과 짧은 chunk를 우선 정리하고 source metadata를 강화한다.

### Query ID: 292

원 질문: 셔틀버스 정보
Rewrite: 셔틀버스 정보
Intent: INFO
Keywords: ['셔틀버스', '정보']
Category: None
Filters: {}

최종 답변: 안녕하세요. 동의대학교 정보 안내를 도와드리고 있어요. 학사, 장학, 기숙사, 통학버스 같은 학교 정보를 물어봐 주세요.

사이트 바로가기: https://www.deu.ac.kr/
문제 요약: Evidence exists, but logged retrieval returned or selected zero chunks.

검색 후보:
- lexical top 결과: 1. [한국장애인개발원] 장애청년 채용 취업 정보 안내(12월 2차) (0.5); 2. [한국장애인개발원] 장애청년 채용 취업 정보 안내(12월 1차) (0.5); 3. [한국장애인개발원] 장애청년 채용 취업 정보 안내(5월 2차) (0.487179490314511)
- vector top 결과: 1. 셔틀버스 안내 | 캠퍼스안내 | DEU (0.50939956139334); 2. 시외통학버스 | 편의·복지 | 대학생활 (0.440854029630014); 3. 시외통학버스 | 편의·복지 | 대학생활 (0.438124975133694)
- hybrid top 결과: 1. 셔틀버스 안내 | 캠퍼스안내 | DEU (0.6); 2. 시외통학버스 | 편의·복지 | 대학생활 (0.5192631439542239); 3. 시외통학버스 | 편의·복지 | 대학생활 (0.5160487071507974)
- rerank 후 결과: 1. 셔틀버스 안내 | 캠퍼스안내 | DEU (3.7); 2. [한국장애인개발원] 장애청년 채용 취업 정보 안내(12월 2차) (0.361597); 3. 2026학년도 1학기 시외통학버스 신청 안내(수정) (-0.381216)
- selected chunks: 1. 셔틀버스 안내 | 캠퍼스안내 | DEU (3.7); 2. [한국장애인개발원] 장애청년 채용 취업 정보 안내(12월 2차) (0.361597); 3. 2026학년도 1학기 시외통학버스 신청 안내(수정) (-0.381216)

정답 근거 DB 존재 여부: 있음
- 근거 탐색어: 셔틀버스, 셔틀버스 정보
- evidence ranks: {'lexical': 3, 'vector': 1, 'hybrid': 1, 'reranked': 1, 'selected': 1}

원인 분류: lexical search 문제 / retrieval_empty
수정 제안: 후보 로그를 추가한 뒤 동일 query를 재실행해 탈락 단계를 확정한다.

### Query ID: 293

원 질문: 버스 알려줘
Rewrite: 버스
Intent: GENERAL
Keywords: ['버스']
Category: None
Filters: {}

최종 답변: 잘 이해하지 못했어요.
학교 관련 질문을 해주시면 더 정확히 도와드릴게요!
문제 요약: RAG was bypassed and no precise DB evidence was found.

검색 후보:
- lexical top 결과: 1. 2026학년도 1학기 시외통학버스 신청 안내(수정) (0.607843137254902); 2. 제5회 광주버스킹월드컵 경연 참가자 모집 (0.565217391304348); 3. 순환버스에서 지갑 분실 (0.565217391304348)
- vector top 결과: 1. [입찰공고]제2025-21호_동의대학교 2026학년도 시외통학버스 운행 용역 입찰공고(재공고) (0.409730659175398); 2. [입찰공고]제2025-21호_동의대학교 2026학년도 시외통학버스 운행 용역 입찰공고 (0.406454108606789); 3. 시외통학버스 | 편의·복지 | 대학생활 (0.360149074788427)
- hybrid top 결과: 1. 셔틀버스 안내 | 캠퍼스안내 | DEU (0.8678128031628948); 2. 2026학년도 1학기 시외통학버스 신청 안내(수정) (0.8148751051203438); 3. 시외통학버스 | 편의·복지 | 대학생활 (0.8094215365437561)
- rerank 후 결과: 1. 2026학년도 1학기 시외통학버스 신청 안내(수정) (10.431774); 2. [입찰공고]제2025-21호_동의대학교 2026학년도 시외통학버스 운행 용역 입찰공고(재공고) (9.247442); 3. [입찰공고]제2025-21호_동의대학교 2026학년도 시외통학버스 운행 용역 입찰공고 (9.207044)
- selected chunks: 1. 2026학년도 1학기 시외통학버스 신청 안내(수정) (10.431774); 2. 시외통학버스 | 편의·복지 | 대학생활 (7.719257); 3. 셔틀버스 안내 | 캠퍼스안내 | DEU (7.35)

정답 근거 DB 존재 여부: 없음/불확실
- 근거 탐색어: 버스 알려줘
- evidence ranks: {'lexical': None, 'vector': None, 'hybrid': None, 'reranked': None, 'selected': None}

원인 분류: crawler/data 부족 / data
수정 제안: 첨부/본문 추출 누락과 짧은 chunk를 우선 정리하고 source metadata를 강화한다.

### Query ID: 296

원 질문: 6-1번 버스 정보
Rewrite: 1번 버스 정보 6
Intent: GENERAL
Keywords: ['1번', '버스', '정보', '6']
Category: None
Filters: {}

최종 답변: 잘 이해하지 못했어요.
학교 관련 질문을 해주시면 더 정확히 도와드릴게요!
문제 요약: RAG was bypassed and no precise DB evidence was found.

검색 후보:
- lexical top 결과: 1. 2026학년도 교육과정 (0.746835446094133); 2. 2026학년도 교육과정 경과조치 안내문(학점적용 관련 사항)_전학년 필독 (0.696969694780362); 3. 학칙/규정 | 대학기관/규정 | DEU (0.682539696956527)
- vector top 결과: 1. 2026학년도 1학기 시외통학버스 신청 안내(수정) (0.50886794871879); 2. 셔틀버스 안내 | 캠퍼스안내 | DEU (0.443085975279096); 3. 2026학년도 1학기 시외통학버스 신청 안내(수정) (0.440655834596654)
- hybrid top 결과: 1. 2026학년도 1학기 시외통학버스 신청 안내(수정) (0.921355930888355); 2. 셔틀버스 안내 | 캠퍼스안내 | DEU (0.5224372763834103); 3. 2026학년도 1학기 시외통학버스 신청 안내(수정) (0.5195719271053976)
- rerank 후 결과: 1. 2026학년도 1학기 시외통학버스 신청 안내(수정) (5.354976); 2. 2026학년도 1학기 시외통학버스 신청 안내(수정) (4.431681); 3. 시외통학버스 | 편의·복지 | 대학생활 (4.055695)
- selected chunks: 1. 2026학년도 1학기 시외통학버스 신청 안내(수정) (5.354976); 2. 시외통학버스 | 편의·복지 | 대학생활 (4.055695); 3. 셔틀버스 안내 | 캠퍼스안내 | DEU (3.480437)

정답 근거 DB 존재 여부: 없음/불확실
- 근거 탐색어: 1번 버스 정보 6, 6-1번 버스 정보
- evidence ranks: {'lexical': None, 'vector': None, 'hybrid': None, 'reranked': None, 'selected': None}

원인 분류: crawler/data 부족 / data
수정 제안: 첨부/본문 추출 누락과 짧은 chunk를 우선 정리하고 source metadata를 강화한다.

### Query ID: 297

원 질문: 6-1번 버스 운행 정보
Rewrite: 1번 버스 운행 정보 6
Intent: GENERAL
Keywords: ['1번', '버스', '운행', '정보', '6']
Category: None
Filters: {}

최종 답변: 잘 이해하지 못했어요.
학교 관련 질문을 해주시면 더 정확히 도와드릴게요!
문제 요약: RAG was bypassed and no precise DB evidence was found.

검색 후보:
- lexical top 결과: 1. 2026학년도 교육과정 (0.746835446094133); 2. 2026학년도 교육과정 경과조치 안내문(학점적용 관련 사항)_전학년 필독 (0.696969694780362); 3. 학칙/규정 | 대학기관/규정 | DEU (0.682539696956527)
- vector top 결과: 1. 2026학년도 1학기 시외통학버스 신청 안내(수정) (0.529546606202122); 2. 셔틀버스 안내 | 캠퍼스안내 | DEU (0.463382466536243); 3. 2026학년도 1학기 시외통학버스 신청 안내(수정) (0.441398514550885)
- hybrid top 결과: 1. 2026학년도 1학기 시외통학버스 신청 안내(수정) (0.9599888845000728); 2. 2026학년도 1학기 시외통학버스 신청 안내(수정) (0.8033343942016988); 3. 셔틀버스 안내 | 캠퍼스안내 | DEU (0.5250330691679007)
- rerank 후 결과: 1. 2026학년도 1학기 시외통학버스 신청 안내(수정) (5.944976); 2. 2026학년도 1학기 시외통학버스 신청 안내(수정) (5.109156); 3. [입찰공고]제2025-21호_동의대학교 2026학년도 시외통학버스 운행 용역 입찰공고(재공고) (4.325588)
- selected chunks: 1. 2026학년도 1학기 시외통학버스 신청 안내(수정) (5.944976); 2. 시외통학버스 | 편의·복지 | 대학생활 (4.216353); 3. 셔틀버스 안내 | 캠퍼스안내 | DEU (3.126299)

정답 근거 DB 존재 여부: 없음/불확실
- 근거 탐색어: 1번 버스 운행 정보 6, 6-1번 버스 운행 정보
- evidence ranks: {'lexical': None, 'vector': None, 'hybrid': None, 'reranked': None, 'selected': None}

원인 분류: crawler/data 부족 / data
수정 제안: 첨부/본문 추출 누락과 짧은 chunk를 우선 정리하고 source metadata를 강화한다.

### Query ID: 306

원 질문: 26년 1학기 보강일정 알려줘
Rewrite: 보강일정 26년 1학기 기간 마감일
Intent: INFO
Keywords: ['기간', '일정', '보강일정', '26년', '1학기', '1학기보강일정', '학기보강일정', '1학기보강', '학기보강', '26', '학기', '보강']
Category: None
Filters: {'time': ['1학기', '기간'], 'time_scope': ['1학기']}

최종 답변: 26년 1학기 보강일정은 제공된 문서에서 관련 정보를 찾을 수 없습니다. 

26년 1학기의 주요 일정은 다음과 같습니다.

*   학기개시일: 3월 1일
*   개강일: 3월 3일
*   중간시험: 4월 21일 ~ 27일
*   기말 시험: 6월 16일 ~ 22일

사이트 바로가기: https://www.deu.ac.kr/
문제 요약: Selected context contains query evidence, but final answer is negative or contradicts it.

검색 후보:
- lexical top 결과: 1. 2026-1학기 주거안정장학금 시행안내 (0.666666665342119); 2. [혁신융합대학] 2026학년도 1학기 수강신청을 위한 마이크로디그리 및 다전공 신청 안내 (0.642857142857143); 3. 2026-1학기 주거안정장학금 시행안내 (0.622641509858346)
- vector top 결과: 1. 2026학년도 1학기 휴학안내 (2025-12-26부터) (0.575769885022024); 2. 2026학년도 1학기 1학년 신입생 및 복학생 수강신청 안내 (0.571161593669891); 3. 2026학년도 1학기 1차 폐강 및 수강정정 안내 (0.560525314823554)
- hybrid top 결과: 1. 2026학년도 1학기 수강신청 안내 (0.9410360455392035); 2. 2026학년도 1학기 수강신청 안내 (0.9148032081544933); 3. 2026학년도 1학기 휴학안내 (2025-12-26부터) (0.6)
- rerank 후 결과: 1. 2026학년도 1학기 수강신청 안내 (1.70236); 2. 2026학년도 1학기 수강신청 안내 (1.425812); 3. 2026학년도 1학기 1학년 신입생 및 복학생 수강신청 안내 (0.983966)
- selected chunks: 1. 2026학년도 1학기 수강신청 안내 (1.70236)

정답 근거 DB 존재 여부: 있음
- 근거 탐색어: 보강일정, 26년, 1학기, 보강일정 26년 1학기, 26년 1학기 보강일정 알려줘
- evidence ranks: {'lexical': None, 'vector': None, 'hybrid': None, 'reranked': None, 'selected': None}

원인 분류: final generation 문제 / generation
수정 제안: selected context의 핵심 문장 인용률을 높이고, 답변 전 grounding 검증을 추가한다.

## 6단계 개선안

### 크롤러 개선

- 본문 추출 품질 개선: document_assets 중 document_contents가 없는 첨부를 우선 재처리한다.
- UI/메뉴/목록/preview 텍스트 제거: 메뉴, breadcrumb, 목록 preview, 회의록/공고 하단 반복 텍스트를 chunk 전처리에서 제거한다.
- PDF/첨부 본문 추출 여부 확인: file_ext/parser_type별 추출 실패율을 로그화하고 ZIP/HWP/PDF를 별도 retry queue로 분리한다.
- static/index 페이지 chunk 제외 또는 낮은 가중치: source_type이 static/index/menu 성격이면 검색 score penalty를 적용한다.
- 중복 chunk 제거: content_hash뿐 아니라 normalized title+body 기반 중복 제거를 추가한다.
- 짧은/무의미 chunk 필터링: 120자 미만 또는 날짜/메뉴/링크 중심 chunk는 embedding/search 대상에서 제외하거나 낮은 가중치를 준다.
- 문서 타입별 metadata 강화: building/facility, department, scholarship, academic_calendar, shuttle/bus 같은 domain 태그를 crawler 단계에서 확정한다.

### Retrieval 개선

- keyword/category/filter 추출 검증: 건물명, 학과명, 부서명, 숫자/호관/버스번호가 rewrite 뒤에도 보존되는지 테스트한다.
- rewrite 전후 검색 결과 비교: original_query, rewritten_query, keywords 각각의 lexical/vector top-k를 저장해 나빠진 rewrite를 감지한다.
- filter relaxation 전략: selected_doc_count=0뿐 아니라 low-confidence일 때 department/category/time filter 제거 retry를 수행한다.
- lexical/vector top-k 확대: merge 전 후보를 최소 60개 이상 유지하고, short/static/source penalty는 merge 후가 아니라 후보 점수에 반영한다.
- hybrid RRF 또는 weighted merge 개선: 현재 weighted 모드에서 vector_norm이 강하게 작동하므로 lexical exact/strong term match를 더 크게 보정한다.
- score normalization 점검: lexical_score null, vector-only 후보가 final_score를 지배하는 케이스를 분리 로그화한다.
- doc type/source별 penalty: external_notice, council, attachment, static 메뉴성 문서가 domain query를 덮지 않도록 penalty를 둔다.
- attachment 공고/회의자료 잡음 완화: 제목/본문에 핵심 고유명사가 없으면 첨부 chunk의 rerank 상향을 제한한다.
- 정답 후보가 2~5위에 있을 때 selection 보정: selected top3가 모두 같은 source_type 또는 low evidence면 다음 후보를 섞는다.

### Rerank 개선

- rerank 전후 정답 후보 순위 비교 로그 추가: hybrid_rank, rerank_rank, selected_rank를 request_id별로 저장한다.
- reranker 입력 텍스트 길이 제한 점검: 제목/section/앞부분만 보고 첨부 공고를 과대평가하지 않도록 핵심문장 추출을 적용한다.
- 제목/본문/metadata 조합 개선: title exact match, source_type domain match, department match를 별도 신호로 기록한다.
- UI성 문서 penalty 적용: static/index/menu/회의록/외부채용 공고는 query family mismatch 시 강한 penalty를 둔다.
- rerank threshold 조정: strong_term_match가 낮은 후보는 base_score가 높아도 selected에서 제외한다.

### Fallback 개선

- fallback 조건 명확화: empty result뿐 아니라 top score 낮음, selected evidence 없음, answer negative 예상 케이스에도 fallback한다.
- category/filter 제거 fallback: filters/category/time_scope를 제거한 검색 결과와 원 결과를 비교한다.
- rewrite 제거 fallback: rewritten_query가 고유명사를 손상시키면 original_query 기반 검색으로 되돌린다.
- lexical-only/vector-only fallback 비교: 두 branch 중 evidence rank가 더 좋은 쪽을 selected 후보에 강제로 포함한다.

### Logging 개선

현재 로그는 selected_chunks 중심이라 후보 탈락 위치를 사후에 완전히 복원하기 어렵다. 다음 로그를 추가해야 한다.

- original_query
- rewritten_query
- extracted_keywords
- extracted_category
- applied_filters
- lexical_candidates
- vector_candidates
- merged_candidates
- reranked_candidates
- selected_chunks
- rejected_chunks
- rejection_reason
- fallback_reason
- final_context
- answer_grounding_score