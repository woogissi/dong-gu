# RAG Goldset Failure Cases

생성일시: 2026-06-02 10:42:45
총 실패 케이스: 13

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
제공된 문서에서 하계 계절수업 신청 방법에 대한 구체적인 정보는 찾을 수 없었습니다. 하지만, 일반적으로 계절수업 신청은 학교의 온라인 서비스나 관련 앱을 통해 이루어지는 경우가 많습니다. 추가적인 세부사항은 학교의 공식 웹사이트나 공지사항을 통해 확인하시기 바랍니다.
```

---

### G016: 장학금 지급일 언제야

- **카테고리**: 장학 | **난이도**: hard | **소스**: db
- **실패 단계**: `answer_generation_issue`
- **Top5 Hit**: True | **Context Hit**: True

**정답 문서:**
  - [2026-1학기 "동의사랑" 장학식비 지급 안내](https://www.deu.ac.kr/www/deu-scholarship.do?article.offset=30&articleLimit=10&articleNo=82858&mode=view) (doc_id: deu_scholarship_82858)

**검색된 문서 (상위 3개):**
  - rank 1: [재단법인 서울미래인재재단 2026년 서울독립유공자후손장학금 장학생 선발 안내](https://www.deu.ac.kr/www/deu-scholarship.do?article.offset=10&articleLimit=10&articleNo=84477&mode=view) (score=0.444)
  - rank 2: [2026년 우아한 사장님 자녀장학금 지원 안내](https://www.deu.ac.kr/www/deu-scholarship.do?article.offset=30&articleLimit=10&articleNo=82832&mode=view) (score=0.444)
  - rank 3: [2026학년도 나눔·희망장학금 신청 안내](https://swcc.deu.ac.kr/ai/sub06_03.do?article.offset=50&articleLimit=10&articleNo=81810&mode=view) (score=0.441)

**생성 답변 (앞 200자):**
```
제공된 문서에서 장학금 지급일에 대한 구체적인 정보는 찾을 수 없었습니다. 장학금 신청 기간과 관련된 내용은 있지만, 지급일에 대한 언급은 없습니다. 추가적인 정보가 필요하시면 관련 부서에 문의하시기 바랍니다.
```

---

### G030: 학점포기 어떻게 해?

- **카테고리**: 성적 | **난이도**: hard | **소스**: db
- **실패 단계**: `answer_generation_issue`
- **Top5 Hit**: True | **Context Hit**: True

**정답 문서:**
  - [학사정보 종합안내 가이드(2026)](https://www.deu.ac.kr/www/gra-notice.do?article.offset=0&articleLimit=10&articleNo=80309&mode=view) (doc_id: deu_academic_notice_80309)

**검색된 문서 (상위 3개):**
  - rank 1: [2026학년도 교육과정 경과조치 안내문(학점적용 관련 사항)_전학년 필독](https://www.deu.ac.kr/www/gra-notice.do?article.offset=10&articleLimit=10&articleNo=81208&mode=view) (score=0.524)
  - rank 2: [2026학년도 일반 및 특별 전과생 학점 이수방법](https://swcc.deu.ac.kr/se/sub06_03.do?article.offset=30&articleLimit=10&articleNo=81029&mode=view) (score=0.521)
  - rank 3: [군입대 휴학중 취득학점 인정절차 안내](https://www.deu.ac.kr/www/gra-notice.do?article.offset=20&articleLimit=10&articleNo=81144&mode=view) (score=0.512)

**생성 답변 (앞 200자):**
```
제공된 문서에서 학점포기와 관련된 정보를 찾지 못했습니다.
```

---

### G031: 기숙사 신청 어디서 해?

- **카테고리**: 기숙사 | **난이도**: easy | **소스**: web
- **실패 단계**: `rerank_issue`
- **Top5 Hit**: True | **Context Hit**: False

**정답 문서:**
  - [기숙사 신청 안내](https://dorm.deu.ac.kr/30/3010.do) (doc_id: static_9da619eb2fa46324)

**검색된 문서 (상위 3개):**
  - rank 1: [동의대학교 효민생활관](https://dorm.deu.ac.kr/30/3010.do) (score=0.528)
  - rank 2: [동의대학교 효민생활관](https://dorm.deu.ac.kr/40/4050.do) (score=0.523)
  - rank 3: [동의대학교 효민생활관](https://dorm.deu.ac.kr/60/6010.do) (score=0.515)

**생성 답변 (앞 200자):**
```
기숙사 신청은 동의대학교의 효민생활관 및 행복기숙사에서 진행됩니다. 구체적인 모집 요강은 해당 링크를 통해 확인할 수 있습니다. 

- 제2효민생활관 모집요강: https://myip.kr/wMjZl
- 행복기숙사 모집요강: https://myip.kr/oQCmU

자세한 내용은 동의대학교 기숙사 관련 웹사이트를 참고하세요.
```

---

### G032: 기숙사 비용 알려줘

- **카테고리**: 기숙사 | **난이도**: medium | **소스**: web
- **실패 단계**: `db_data_quality_issue`
- **Top5 Hit**: False | **Context Hit**: False

**정답 문서:**
  - [학생생활관 비용 안내](https://dorm.deu.ac.kr)

**검색된 문서 (상위 3개):**
  - rank 1: [동의대학교 효민생활관](https://dorm.deu.ac.kr/40/4050.do) (score=0.438)
  - rank 2: [동의대학교 효민생활관](https://dorm.deu.ac.kr/20/2031.do) (score=0.438)
  - rank 3: [동의대학교 신입생 가이드](https://www.deu.ac.kr/guide/freshmen-2026) (score=0.344)

**생성 답변 (앞 200자):**
```
제공된 문서에서 기숙사 비용에 대한 정보는 다음과 같습니다.

1. 1개월 사용료: 495,000원 (식대 및 침구류 대여료 별도, 침구사용료: 10,000원)
2. 1일 사용료: 33,000원

기숙사 비용은 식대와 침구류 대여료가 별도로 발생하니 참고하시기 바랍니다.
```

---

### G033: 기숙사 생활 규칙 알려줘

- **카테고리**: 기숙사 | **난이도**: medium | **소스**: web
- **실패 단계**: `db_data_quality_issue`
- **Top5 Hit**: False | **Context Hit**: False

**정답 문서:**
  - [학생생활관 생활 규정](https://dorm.deu.ac.kr/40/4020.do) (doc_id: static_014ee735a1b20c1b)

**검색된 문서 (상위 3개):**
  - rank 1: [동의대학교 효민생활관](https://dorm.deu.ac.kr/20/2030.do) (score=0.513)
  - rank 2: [동의대학교 효민생활관](https://dorm.deu.ac.kr/60/6060.do) (score=0.512)
  - rank 3: [동의대학교 신입생 가이드](https://www.deu.ac.kr/guide/freshmen-2026) (score=0.509)

**생성 답변 (앞 200자):**
```
제공된 문서에서 기숙사 생활 규칙에 대한 구체적인 내용은 확인되지 않았습니다. 기숙사 생활에 대한 규칙이나 수칙은 효민생활관 홈페이지에서 확인할 수 있을 것으로 보입니다. 추가적인 정보가 필요하시면 해당 홈페이지를 방문하시기 바랍니다.
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
학생식당은 다음과 같은 위치에 있습니다:

1. 정보공학관: 2층
2. 제1효민생활관: 1층
3. 행복기숙사: 1층

각 건물의 층수를 참고하여 방문하시면 됩니다.
```

---

### G037: 도서관 이용 시간 알려줘

- **카테고리**: 복지/시설 | **난이도**: easy | **소스**: web
- **실패 단계**: `answer_generation_issue`
- **Top5 Hit**: False | **Context Hit**: True

**정답 문서:**
  - [도서관 이용시간 (도서관 규정) | 도서관소개](https://lib.deu.ac.kr/intro_rule.mir) (doc_id: static_28c37295f426efc7)

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
- **실패 단계**: `rerank_issue`
- **Top5 Hit**: True | **Context Hit**: False

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
- **실패 단계**: `db_data_quality_issue`
- **Top5 Hit**: False | **Context Hit**: False

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
2. 기타 전공선택 과목은 문서에 명시되어 있지 않습니다.

더 자세한 내용은 해당 학과의 공식 자료를 참고하시기 바랍니다.
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
제공된 문서에서 사회봉사 학점 이수 방법에 대한 정보는 찾을 수 없었습니다.
```

---

### G064: 전과하면 기존 학점 인정돼?

- **카테고리**: 규정/시행세칙 | **난이도**: hard | **소스**: web
- **실패 단계**: `lexical_search_issue`
- **Top5 Hit**: False | **Context Hit**: False

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
3. 2017학년도 이후에 이수한 계열기초 학점은 전과 전과 후 학과의 계열이 동일할 경우, 전과 후 학과의 계열교
```
