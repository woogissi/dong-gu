# RAG Goldset Failure Cases

생성일시: 2026-06-02 07:45:50
총 실패 케이스: 10

---

### G011: 하계 계절수업 신청 방법 알려줘

- **카테고리**: 수강신청 | **난이도**: medium | **소스**: db
- **실패 단계**: `answer_generation_issue`
- **Top5 Hit**: True | **Context Hit**: True

**정답 문서:**
  - [2026-하계 계절수업 안내](https://www.deu.ac.kr/www/gra-notice.do?article.offset=0&articleLimit=10&articleNo=84378&mode=view) (doc_id: deu_academic_notice_84378)

**검색된 문서 (상위 3개):**
  - rank 1: [타대학 2026-하계계절수업 수강 안내(본교생이 타대학의 계절수업을 수강하는 경우)](https://www.deu.ac.kr/www/gra-notice.do?article.offset=0&articleLimit=10&articleNo=84385&mode=view) (score=0.444)
  - rank 2: [2026-하계 계절수업 안내](https://www.deu.ac.kr/www/gra-notice.do?article.offset=0&articleLimit=10&articleNo=84378&mode=view) (score=0.313)
  - rank 3: [공지사항 게시판목록 | 컴퓨터공학과](https://swcc.deu.ac.kr/computer/sub06_03.do) (score=0.312)

**생성 답변 (앞 200자):**
```
제공된 문서에서 하계 계절수업 신청 방법에 대한 구체적인 정보는 찾을 수 없었습니다. 하지만, 일반적으로 계절수업 신청은 학교의 온라인 서비스나 관련 앱을 통해 이루어질 수 있습니다. 추가적인 세부사항은 학교의 공식 웹사이트나 공지사항을 통해 확인하시기 바랍니다.
```

---

### G034: 학생식당 위치 어디야

- **카테고리**: 복지/시설 | **난이도**: easy | **소스**: db
- **실패 단계**: `topk_selector_issue`
- **Top5 Hit**: True | **Context Hit**: False

**정답 문서:**
  - [교내식당 | 편의·복지 | 대학생활](https://www.deu.ac.kr/www/deu-dining-hall.do) (doc_id: static_a4971bb8fbfc5b4c)

**검색된 문서 (상위 3개):**
  - rank 1: [교내식당 | 편의·복지 | 대학생활](https://www.deu.ac.kr/www/deu-dining-hall.do) (score=0.740)
  - rank 2: [동의대학교 신입생 가이드](https://www.deu.ac.kr/guide/freshmen-2026) (score=0.507)
  - rank 3: [동의대학교 효민생활관](https://dorm.deu.ac.kr/20/2031.do) (score=0.473)

**생성 답변 (앞 200자):**
```
학생식당은 정보공학관 2층과 제1효민생활관 1층에 위치해 있습니다. 추가로 행복기숙사 1층에도 학생식당이 있습니다. 각 위치에서 편리하게 이용하실 수 있습니다.
```

---

### G037: 도서관 이용 시간 알려줘

- **카테고리**: 복지/시설 | **난이도**: easy | **소스**: web
- **실패 단계**: `answer_generation_issue`
- **Top5 Hit**: True | **Context Hit**: True

**정답 문서:**
  - [중앙도서관 이용 안내](https://lib.deu.ac.kr)

**검색된 문서 (상위 3개):**
  - rank 1: [공지사항](https://lib.deu.ac.kr/sb/default_notice_list.mir) (score=0.525)
  - rank 2: [LIB Today](https://lib.deu.ac.kr/sb/libtoday_libtoday_list.mir) (score=0.524)
  - rank 3: [2026학년도 1학기 중앙도서관 신입생/학부생 비대면 정보활용교육](https://police2001.deu.ac.kr/police/sub02_01.do?article.offset=40&articleLimit=10&articleNo=82597&mode=view) (score=0.522)

**생성 답변 (앞 200자):**
```
제공된 문서에서 도서관 이용 시간에 대한 정보는 찾을 수 없었습니다.
```

---

### G038: 중앙도서관 콜라보라운지 운영시간 알려줘

- **카테고리**: 복지/시설 | **난이도**: hard | **소스**: db
- **실패 단계**: `answer_generation_issue`
- **Top5 Hit**: True | **Context Hit**: True

**정답 문서:**
  - [콜라보라운지 이용 안내](https://lib.deu.ac.kr) (doc_id: static_fa25acc254f018a3)

**검색된 문서 (상위 3개):**
  - rank 1: [공지사항](https://lib.deu.ac.kr/sb/default_notice_list.mir) (score=0.526)
  - rank 2: [LIB Today](https://lib.deu.ac.kr/sb/libtoday_libtoday_list.mir) (score=0.526)
  - rank 3: [도서관소개](https://lib.deu.ac.kr/intro_staff.mir) (score=0.525)

**생성 답변 (앞 200자):**
```
제공된 문서에서 중앙도서관 콜라보라운지의 운영시간에 대한 정보는 찾지 못했습니다.
```

---

### G044: 교환학생 신청 방법 알려줘

- **카테고리**: 국제교류 | **난이도**: medium | **소스**: web
- **실패 단계**: `db_data_quality_issue`
- **Top5 Hit**: False | **Context Hit**: False

**정답 문서:**
  - [교환학생 파견 신청 안내](https://exchange.deu.ac.kr/exchange/sub02_02.do)

**검색된 문서 (상위 3개):**
  - rank 1: [2026학년도 2학기 파견 예정 교비 교환학생 모집(260319_수정)](https://www.deu.ac.kr/www/deu-education.do?article.offset=30&articleLimit=10&articleNo=83314&mode=view) (score=0.659)
  - rank 2: [2026학년도 2학기 파견 예정 교비 교환학생 모집](https://police2001.deu.ac.kr/police/sub02_01.do?article.offset=40&articleLimit=10&articleNo=83350&mode=view) (score=0.622)
  - rank 3: [2026학년도 2학기 파견 예정 교비 교환학생 모집](https://urban.deu.ac.kr/urban/sub06_03.do?article.offset=40&articleLimit=10&articleNo=83357&mode=view) (score=0.615)

**생성 답변 (앞 200자):**
```
교환학생 신청 방법은 다음과 같습니다:

1. 신청장소 및 기한: 2026년 3월 25일(수) 12:00까지 학부(과) 또는 전공사무실에 제출해야 합니다. 대학원생은 대학원 행정지원실로 제출합니다.
2. 제출서류: 신청서, 자기소개서, 세부이수계획서, 재학증명서, 성적증명서, 자격증 사본(필요한 경우) 각 1부를 준비해야 합니다.
3. 문의처: 추가 문의는
```

---

### G046: 컴퓨터공학과 홈페이지 알려줘

- **카테고리**: 학과별 | **난이도**: easy | **소스**: web
- **실패 단계**: `db_data_quality_issue`
- **Top5 Hit**: False | **Context Hit**: False

**정답 문서:**
  - [컴퓨터공학과 홈페이지](https://swcc.deu.ac.kr/computer/index.do) (doc_id: static_90734dd063deeb60)

**검색된 문서 (상위 3개):**
  - rank 1: [컴퓨터 응용 실습실 | 실습실 | 컴퓨터공학과](https://swcc.deu.ac.kr/computer/sub04_04.do) (score=0.446)
  - rank 2: [컴퓨터 소프트웨어 실습실 | 실습실 | 컴퓨터공학과](https://swcc.deu.ac.kr/computer/sub04_03.do) (score=0.446)
  - rank 3: [약사 | 학과소개 | 컴퓨터공학과](https://swcc.deu.ac.kr/computer/sub01_02.do) (score=0.446)

**생성 답변 (앞 200자):**
```
선택된 문서 기준으로 확인된 내용입니다.
- 이수표 | 교육과정 | 컴퓨터공학과: 이수표 | 교육과정 | 컴퓨터공학과 소프트웨어융합대학 컴퓨터공학과 학 년 과정구분 1 학 기 2 학 기 전공명 이수구분 교과목 번호 교 과 목 명 학점 시간 교과목 번호 교 과 목 명 학점 시간 2 컴퓨터공 학과 공통교양 컴퓨터공 학과 전공필수 컴퓨터공 학과 전공선택 3 컴퓨
```

---

### G060: 경찰행정학과 3학년 2학기 전공선택 알려줘

- **카테고리**: 첨부파일 기반 | **난이도**: hard | **소스**: attachment
- **실패 단계**: `topk_selector_issue`
- **Top5 Hit**: True | **Context Hit**: False

**정답 문서:**
  - [경찰행정학과 교육과정](https://police2001.deu.ac.kr) (doc_id: static_8bf177a16c1c540e)

**검색된 문서 (상위 3개):**
  - rank 1: [2026학년도 AX 마이크로디그리 과정 안내](https://urban.deu.ac.kr/urban/sub06_03.do?article.offset=90&articleLimit=10&articleNo=80187&mode=view) (score=0.724)
  - rank 2: [2026학년도 AX 마이크로디그리 과정 신설 안내 및 홍보 협조 요청(수정)](https://police2001.deu.ac.kr/police/sub02_01.do?article.offset=80&articleLimit=10&articleNo=80233&mode=view) (score=0.723)
  - rank 3: [[안내] 2026학년도 AX 마이크로디그리 과정 신설 안내 및 홍보](https://swcc.deu.ac.kr/computer/sub06_03.do?article.offset=40&articleLimit=10&articleNo=80328&mode=view) (score=0.722)

**생성 답변 (앞 200자):**
```
제공된 문서에서 경찰행정학과 3학년 2학기 전공선택 과목에 대한 정보는 다음과 같습니다:

1. 미래지향적 경찰활동 (키스톤디자인)
2. 이 과목은 전공선택으로 이수할 수 있습니다.

추가적인 과목 정보는 문서에 포함되어 있지 않습니다.
```

---

### G063: 사회봉사 학점 이수 방법 알려줘

- **카테고리**: 규정/시행세칙 | **난이도**: hard | **소스**: web
- **실패 단계**: `answer_generation_issue`
- **Top5 Hit**: True | **Context Hit**: True

**정답 문서:**
  - [학사정보 종합안내 가이드(2026)](https://www.deu.ac.kr/www/gra-notice.do?article.offset=0&articleLimit=10&articleNo=80309&mode=view) (doc_id: deu_academic_notice_80309)

**검색된 문서 (상위 3개):**
  - rank 1: [2026-1학기 제2전공(부ㆍ복수ㆍ융합ㆍ연계전공) 및 마이크로디그리 신청/변경 일정 및 이수기준 안내](https://www.deu.ac.kr/www/gra-notice.do?article.offset=30&articleLimit=10&articleNo=80071&mode=view) (score=0.511)
  - rank 2: [이수표 | 교육과정 | 라이프복지학과](https://llc.deu.ac.kr/llc/sub03_01.do) (score=0.509)
  - rank 3: [이수표 | 교육과정 | 라이프복지학과](https://deuhome.deu.ac.kr/llc/sub03_01.do) (score=0.508)

**생성 답변 (앞 200자):**
```
제공된 문서에서 사회봉사 학점 이수 방법에 대한 정보는 찾지 못했습니다.
```

---

### G064: 전과하면 기존 학점 인정돼?

- **카테고리**: 규정/시행세칙 | **난이도**: hard | **소스**: web
- **실패 단계**: `rerank_issue`
- **Top5 Hit**: True | **Context Hit**: False

**정답 문서:**
  - [전과 관련 학사 규정](https://advising.deu.ac.kr) (doc_id: deu_advising_80352)

**검색된 문서 (상위 3개):**
  - rank 1: [군입대 휴학중 취득학점 인정절차 안내](https://www.deu.ac.kr/www/gra-notice.do?article.offset=20&articleLimit=10&articleNo=81144&mode=view) (score=0.511)
  - rank 2: [AX마이크로디그리 K-MOOC강좌 수강 및 학점인정 관련 사항 안내](https://www.deu.ac.kr/www/gra-notice.do?article.offset=10&articleLimit=10&articleNo=81503&mode=view) (score=0.511)
  - rank 3: [2026학년도 1학기 전과 신청기간 공지](https://www.deu.ac.kr/www/gra-notice.do?article.offset=30&articleLimit=10&articleNo=79965&mode=view) (score=0.511)

**생성 답변 (앞 200자):**
```
전과 시 기존 학점 인정에 대한 내용은 다음과 같습니다:

1. 동일 계열로 전과할 경우, 이수한 계열교양(계열기초, 학문기초) 학점은 승계됩니다.
2. 2016학년도 이전에 이수한 학문기초 학점은 전과 후 계열교양 이수 구분으로 인정됩니다.
3. 2017학년도 이후 이수한 계열기초 학점은 전과 전후의 계열이 동일할 경우, 전과 후 학과의 계열교양 학점으로
```

---

### G066: 학생처 전화번호 알려줘

- **카테고리**: 학적 | **난이도**: medium | **소스**: web
- **실패 단계**: `db_data_quality_issue`
- **Top5 Hit**: False | **Context Hit**: False

**정답 문서:**
  - [학생지원처 안내](https://www.deu.ac.kr/www/deu-organization.do)

**검색된 문서 (상위 3개):**
  - rank 1: [전화번호 | 대학기관/규정 | DEU](https://www.deu.ac.kr/www/phone.do?schGubun=dept_nm&schKeyword=%ED%95%99%EC%83%9D%EC%83%81%EB%8B%B4%EC%84%BC%ED%84%B0) (score=0.445)
  - rank 2: [전화번호 | 대학기관/규정 | DEU](https://www.deu.ac.kr/www/phone.do?schGubun=dept_nm&schKeyword=%ED%95%99%EC%83%9D%EC%A7%80%EC%9B%90%ED%8C%80) (score=0.445)
  - rank 3: [전화번호 | 대학기관/규정 | DEU](https://www.deu.ac.kr/www/phone.do?schGubun=dept_nm&schKeyword=%EC%A7%84%EB%A1%9C%EA%B5%90%EC%9C%A1%EC%84%BC%ED%84%B0) (score=0.444)

**생성 답변 (앞 200자):**
```
학생처의 전화번호는 다음과 같습니다:

1. 학생지원팀 팀장: 051-890-1041
2. 학생지원팀 (학생자치기구 관련 업무 등): 051-890-1042
3. 학생상담센터 소장: 051-890-1785
4. 학생상담센터 상담교수: 051-890-1291, 051-890-0000

필요한 경우 해당 번호로 문의하시기 바랍니다.
```
