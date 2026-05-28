# RAG 로그 실패 분석 리포트

- 생성 시각: 2026-05-20T23:20:10
- 분석 범위: 최근 INFO query 15개 중 실패 가능성 상위 15개
- DB 변경 없음: `.env`의 Postgres 접속으로 읽기 전용 조회만 수행

## 스키마 확인
- query_logs: rows=15, first=2026-05-20T13:52:06.786482+09:00, last=2026-05-20T14:05:30.207350+09:00
- response_logs: rows=15, first=2026-05-20T13:53:00.656363+09:00, last=2026-05-20T14:05:57.558912+09:00
- retrieval_logs: rows=15, first=2026-05-20T13:52:59.278122+09:00, last=2026-05-20T14:05:56.534371+09:00
- retrieval_selected_chunks: rows=38, first=2026-05-20T13:52:59.278122+09:00, last=2026-05-20T14:05:56.534371+09:00
- documents: rows=3235, first=2026-05-20T06:35:33.044750+09:00, last=2026-05-20T13:34:33.712187+09:00
- document_contents: rows=8557, first=2026-05-20T06:35:33.044750+09:00, last=2026-05-20T13:34:33.712187+09:00
- chunks: rows=13527, first=2026-05-20T06:35:33.044750+09:00, last=2026-05-20T13:34:33.712187+09:00
- chunk_embeddings: rows=13527, first=2026-05-20T06:36:22.539463+09:00, last=2026-05-20T13:34:37.804207+09:00
- crawl_logs: rows=106, first=2026-05-20T02:25:22.907784+09:00, last=2026-05-20T04:43:46.646258+09:00

## 전체 관찰 요약
- failure_type_counts_top25: {'D. 노이즈 문서가 상위에 섞임': 9, 'B. 데이터는 있지만 검색 실패': 3, 'C. 검색은 됐지만 selection/rerank 실패': 3}
- negative_answer_cases_top25: 2
- fallback_cases_top25: 2
- with_db_evidence_probe_top25: 15

## 대표 실패 케이스

### [Case 1] query_id=482 / request_id=6ecd326f-c11e-4b7d-8d25-972f15b936c5
- created_at: 2026-05-20T14:03:30.286274+09:00
- 질문: 정보공학관 2층에 뭐 있어
- 답변: 인포마션 공학관 2층에 교직과목이 있습니다.   교직과목은 다음과 같습니다.  *   교육철학및교육사 *   교육학개론 *   교육사회 *   교육심리 *   교육방법및교육공학 *   특수교육학개론 *   교육평가 *   교직실무 *   디지털교육 *   학교폭력예방및학생의이해 *   교육봉사  사이트 바로가기: https://www.deu.ac.kr/
- 문제 유형: D. 노이즈 문서가 상위에 섞임
- intent/category/filters/rewrite: INFO / None / {} / 정보공학관 2층에 뭐 있어
- 원인 분석: selected chunk에 메뉴/공유/SNS/게시판 등 UI성 텍스트가 포함됨
- 수정 필요 지점: text cleaning / noise filter
- 검색된 문서:
  - lexical#1 🟣2026학년도 2학기 학생설계전공(제2전공) 이수 신청 안내🟣 doc=deu_advising_85097 chunk=deu_advising_85097_v001_chunk_047 lex=7.25 vec=None final=0.878787878787879
  - lexical#2 2026학년도 교육과정 doc=deu_safety_80836 chunk=deu_safety_80836_v001_chunk_045 lex=7.25 vec=None final=0.878787878787879
  - lexical#3 📝 다전공 진로로드맵 작성을 위한 워크시트 📝 doc=deu_advising_80497 chunk=deu_advising_80497_v001_chunk_046 lex=6.99999990463257 vec=None final=0.874999998509884
  - lexical#4 🟣2026학년도 2학기 학생설계전공(제2전공) 이수 신청 안내🟣 doc=deu_advising_85097 chunk=deu_advising_85097_v001_chunk_043 lex=6.9 vec=None final=0.873417721518987
  - lexical#5 2026학년도 교육과정 doc=deu_safety_80836 chunk=deu_safety_80836_v001_chunk_041 lex=6.9 vec=None final=0.873417721518987
  - vector#1 캠퍼스맵 | 캠퍼스안내 | DEU doc=static_19b132e7ab559d4e chunk=static_19b132e7ab559d4e_v001_chunk_009 lex=None vec=0.572542003090147 final=0.572542003090147
- 선택된 chunk:
  - rank=1 title=교직과정 이수조건 | 교직과정 이수 | 교직과 source_type=institution content_type=clean score=1.874237 rerank=1.874237 lex=None vec=None final=None
    source_url=https://www.deu.ac.kr/teacher/sub02_03.do
    원문 일부: [TITLE] 교직과정 이수조건 | 교직과정 이수 | 교직과  [BODY] 학점 | 시간 | 학점 | 시간  교직과목 | 2 | 700075 | 교육철학및교육사 | 2 | 2 | 동의지천교양대학 | 교직이론 700077 | 교육학개론 | 2 | 2 | 동의지천교양대학 | 교직이론 700070 | 교육사회 | 2 | 2 | 동의지천교양대학 | 교직이론 700072 | 교육심리 | 2 | 2 | 동의지천교양대학 | 교직이론 3 | 700068 | 교육방법및교육공학 | 2 | 2 | 동의지천교양대학 | 교직이론 700162 | 특수...
  - rank=2 title=교직과정 이수조건 | 교직과정 이수 | 교직과 source_type=teacher content_type=table score=1.468046 rerank=1.468046 lex=None vec=None final=None
    source_url=https://deuhome.deu.ac.kr/teacher/sub02_03.do
    원문 일부: [TITLE] 교직과정 이수조건 | 교직과정 이수 | 교직과  [TABLE] table  | 교육철학및교육사 | 2 | 2 | 동의지천교양대학 | 교직이론 700077 | 교육학개론 | 2 | 2 | 동의지천교양대학 | 교직이론 700070 | 교육사회 | 2 | 2 | 동의지천교양대학 | 교직이론 700072 | 교육심리 | 2 | 2 | 동의지천교양대학 | 교직이론 3 | 700068 | 교육방법및교육공학 | 2 | 2 | 동의지천교양대학 | 교직이론 700162 | 특수교육학개론 | 2 | 2 | 동의지천교양대학 | 교직...
  - rank=3 title=교육대학원 | 대학원 | 간호학과 source_type=department content_type=clean score=-0.891294 rerank=-0.891294 lex=None vec=None final=None
    source_url=https://nursing.deu.ac.kr/nursing/sub07_09.do
    원문 일부: [TITLE] 교육대학원 | 대학원 | 간호학과  [BODY] 간호교육 교과과정표  [TABLE] 교과목 번호 | 과목명 | 학점(시간) 5W6A01 | 간호교육이론 (Theory in Nursing Education) | 2(2) 5W6A02 | 간호교육연구 (Research in Nursing Education) | 2(2) 5W6A03 | 간호교육통계 (Statistics in Nursing Education) | 2(2) 5W6A04 | 간호교육상담 (Counselling in Nursing Education) | 2(...
- 정답 후보 문서 존재 여부:
  - hits=3 title=복지문화시설 | 편의·복지 | 대학생활 doc=static_8c67a21f12589149 chunk=static_8c67a21f12589149_v001_chunk_002 source_type=foundation content_type=clean
    source_url=https://www.deu.ac.kr/www/deu-culture.do
  - hits=2 title=2026-하계 계절수업 안내 doc=deu_academic_notice_84378 chunk=deu_academic_notice_84378_v001_chunk_010 source_type=academic_notice content_type=None
    source_url=https://www.deu.ac.kr/www/gra-notice.do?article.offset=0&articleLimit=10&articleNo=84378&mode=view
  - hits=2 title=2026-하계 계절수업 안내 doc=deu_academic_notice_84378 chunk=deu_academic_notice_84378_v001_chunk_022 source_type=academic_notice content_type=None
    source_url=https://www.deu.ac.kr/www/gra-notice.do?article.offset=0&articleLimit=10&articleNo=84378&mode=view
  - hits=2 title=2026-하계 계절수업 안내 doc=deu_academic_notice_84378 chunk=deu_academic_notice_84378_v001_chunk_011 source_type=academic_notice content_type=None
    source_url=https://www.deu.ac.kr/www/gra-notice.do?article.offset=0&articleLimit=10&articleNo=84378&mode=view
  - hits=2 title=[첨단산업인재양성부트캠프반도체사업단] 연구원 신규채용 공고 doc=deu_job_84269 chunk=deu_job_84269_v001_chunk_001 source_type=job content_type=clean
    source_url=https://www.deu.ac.kr/www/deu-job.do?article.offset=0&articleLimit=10&articleNo=84269&mode=view

### [Case 2] query_id=477 / request_id=482df737-be3b-4c86-a8fb-5ba0ce76af9b
- created_at: 2026-05-20T13:59:18.869339+09:00
- 질문: 1번 건물 이름
- 답변: 동의대학교 1번 건물 이름은 동의대학교 본관입니다.  사이트 바로가기: https://www.deu.ac.kr/
- 문제 유형: D. 노이즈 문서가 상위에 섞임
- intent/category/filters/rewrite: INFO / None / {} / 1번 건물 이름
- 원인 분석: selected chunk에 메뉴/공유/SNS/게시판 등 UI성 텍스트가 포함됨
- 수정 필요 지점: text cleaning / noise filter
- 검색된 문서:
  - lexical#1 📝 다전공 진로로드맵 작성을 위한 워크시트 📝 doc=deu_advising_80497 chunk=deu_advising_80497_v001_chunk_028 lex=7.24999990463257 vec=None final=0.878787877386704
  - lexical#2 🟣2026학년도 2학기 학생설계전공(제2전공) 이수 신청 안내🟣 doc=deu_advising_85097 chunk=deu_advising_85097_v001_chunk_029 lex=7.05000009536743 vec=None final=0.875776398987191
  - lexical#3 2026학년도 교육과정 doc=deu_safety_80836 chunk=deu_safety_80836_v001_chunk_027 lex=7.05000009536743 vec=None final=0.875776398987191
  - lexical#4 2026학년도 1학년 1학기 신입생 및 복학생 수강신청 안내 doc=deu_department_81033 chunk=deu_department_81033_v001_chunk_123 lex=4.45000004768372 vec=None final=0.816513763073267
  - lexical#5 2026학년도 1학기 1학년 신입생 및 복학생 수강신청 안내 doc=deu_academic_notice_80856 chunk=deu_academic_notice_80856_v001_chunk_120 lex=4.45000004768372 vec=None final=0.816513763073267
  - vector#1 2026학년도 1학기 1학년 신입생 및 복학생 수강신청 안내 doc=deu_academic_notice_80856 chunk=deu_academic_notice_80856_v001_chunk_006 lex=None vec=0.54088205586458 final=0.54088205586458
- 선택된 chunk:
  - rank=1 title=2026학년도 교육과정 source_type=safety content_type=None score=-2.339971 rerank=-2.339971 lex=7.05000009536743 vec=None final=0.875776398987191
    source_url=https://www.deu.ac.kr/www/deu-curriculum.do?article.offset=0&articleLimit=10&articleNo=80836&mode=view
    원문 일부: [TITLE] 2026학년도 교육과정  [ATTACHMENT] 2026학년도 교육과정 편람.pdf  14 DONG-EUI UNIVERSITY CURRICULUM | 2026 1. 교양과정 동의대학교(콜라보) 교양교육은 인간, 사회, 자연의 원리에 대한 기본 지식과 도덕적 인성, 예술적 감수성과 창조성, 개방적 소통 능력과 생애 설계 능력을 함양하여 ‘진리를 공유하고 정의에 공감하며 창의로 공명하는 동의지천 교양인’ 을 양성하기 위하여 콜라보 교양교육과정을 편성, 운영한다. 1) 공통교양 ① 다음과 같이 학문경험 제공 및 역량함...
- 정답 후보 문서 존재 여부:
  - hits=3 title=2026-1학기 주거안정장학금 시행안내 doc=deu_scholarship_81842 chunk=deu_scholarship_81842_v001_chunk_007 source_type=scholarship content_type=table
    source_url=https://www.deu.ac.kr/www/deu-scholarship.do?article.offset=0&articleLimit=10&articleNo=81842&mode=view
  - hits=3 title=2026-1학기 주거안정장학금 시행안내 doc=deu_scholarship_81842 chunk=deu_scholarship_81842_v001_chunk_003 source_type=scholarship content_type=clean
    source_url=https://www.deu.ac.kr/www/deu-scholarship.do?article.offset=0&articleLimit=10&articleNo=81842&mode=view
  - hits=3 title=[한국장애인개발원] 장애청년 채용 취업 정보 안내(3월 1차) doc=deu_disability_support_81812 chunk=deu_disability_support_81812_v001_chunk_007 source_type=disability_support content_type=None
    source_url=https://www.deu.ac.kr/www/deu-support-notice.do?article.offset=10&articleLimit=10&articleNo=81812&mode=view
  - hits=3 title=[장애인기업종합지원센터] 2026년 제1차 장애인 창업사업화 지원사업 안내 doc=deu_disability_support_80697 chunk=deu_disability_support_80697_v001_chunk_003 source_type=disability_support content_type=None
    source_url=https://www.deu.ac.kr/www/deu-support-notice.do?article.offset=20&articleLimit=10&articleNo=80697&mode=view
  - hits=3 title=인권센터 | 부속기관 | 대학기관/규정 | DEU doc=static_17d10073e3884b5e chunk=static_17d10073e3884b5e_v001_chunk_001 source_type=institution content_type=clean
    source_url=https://www.deu.ac.kr/www/deu-human-rights.do

### [Case 3] query_id=483 / request_id=8e04c92f-cbe1-4f3f-8b6a-7af19d42f2da
- created_at: 2026-05-20T14:05:30.207350+09:00
- 질문: 동의대 동아리 정보
- 답변: 동아리 정보는 다음과 같습니다.  * 로봇공학과 동아리는 학습 및 기술 교류의 중심지로서 성적 향상과 기술 습득에 중점을 둡니다. 다양한 경진대회와 참여하고 선도 기술 체험 및 연구 활동에 참여할 기회를 제공합니다. * 경찰행정학과는 범죄 예방 동아리 "퍼펙트(Perfect)"를 운영하고 있습니다. 이 동아리는 지역사회에서 할 수 있는 다양한 활동에 관심을 가지고 참여해 보고자 합니다. * 자동차공학과 LAZO는 CAE 분야의 전문 지식을 갖춘 인재를 양성하기 위해 자기주도적으로 설계, 해석을 수행합니다.  이러한 동아리 정보는 제공된 문서에서 확인할 수 있습니다.  사이트 바로가기: https://www.deu.ac.kr/
- 문제 유형: B. 데이터는 있지만 검색 실패
- intent/category/filters/rewrite: INFO / None / {} / 동의대 동아리 정보
- 원인 분석: DB 후보는 있으나 retrieval 후보/selected와 겹치지 않음
- 수정 필요 지점: lexical/vector query
- 검색된 문서:
  - lexical#1 2026년 푸른등대 삼성기부장학금 신청 안내 (학부-AI핵심분야 진로 희망자, 대학원-인문사회계열 학과 전공자) doc=deu_scholarship_83658 chunk=deu_scholarship_83658_v001_chunk_023 lex=1.85000004768372 vec=None final=0.649122812888115
  - lexical#2 LAZO | 동아리 | 자동차공학과 doc=static_6ccb121656507be2 chunk=static_6ccb121656507be2_v001_chunk_002 lex=1.75000002384186 vec=None final=0.636363639516279
  - lexical#3 DECA | 동아리 | 자동차공학과 doc=static_a3d41f5826791a2c chunk=static_a3d41f5826791a2c_v001_chunk_002 lex=1.75000002384186 vec=None final=0.636363639516279
  - lexical#4 동의로봇작업단 | 동아리/지원사업 | 로봇공학과 doc=static_a5d0b005d9edd54b chunk=static_a5d0b005d9edd54b_v001_chunk_002 lex=1.75000002384186 vec=None final=0.636363639516279
  - lexical#5 디메카 | 동아리 | 기계공학과 doc=static_6f6465e82657e59b chunk=static_6f6465e82657e59b_v001_chunk_002 lex=1.65 vec=None final=0.622641509433962
  - vector#1 동아리 | 학생회 | 체육학과 doc=static_6f298b131184fe8e chunk=static_6f298b131184fe8e_v001_chunk_001 lex=None vec=0.667479375901301 final=0.667479375901301
- 선택된 chunk:
  - rank=1 title=동의로봇작업단 | 동아리/지원사업 | 로봇공학과 source_type=department content_type=clean score=4.744447 rerank=4.744447 lex=None vec=None final=None
    source_url=https://mecha.deu.ac.kr/mecha/sub08_06.do
    원문 일부: [TITLE] 동의로봇작업단 | 동아리/지원사업 | 로봇공학과  [BODY] 동아리 목적  - 학습 및 기술 교류의 중심지로서 성적 향상과 기술 습득에 중점을 두고 있으며, 다양한 경진대회와 참여와 선도 기술 체험 및 연구 활동에 참여할 기회를 제공합니다.
  - rank=2 title=동아리 | 학생 활동 | 경찰행정학과 source_type=department content_type=clean score=4.530448 rerank=4.530448 lex=None vec=None final=None
    source_url=https://police2001.deu.ac.kr/police/sub03_05.do
    원문 일부: [TITLE] 동아리 | 학생 활동 | 경찰행정학과  [BODY] ◆ 퍼펙트(범죄 예방 동아리)  - 동아리 소개 범죄 예방 동아리 "퍼펙트(Perfect)"는 '우리 사회에서 발생하고 있는 범죄와 범죄로 인한 두려움을 완전히(Perfect) 제거하겠다는 의미'로 만들어진 동아리입니다. 특히, 자치경찰제 시행과 더불어 지역사회에서 할 수 있는 다양한 활동에 대해서 관심을 가지고 참여해 보고자 합니다. 경찰행정학과 학생회와 자치경찰운영, 피해자 인권 보호 및 관련 대책 마련에 관심이 있는 학생들을 주축으로 운영하고 있습니다. -...
  - rank=3 title=LAZO | 동아리 | 자동차공학과 source_type=department content_type=clean score=4.530448 rerank=4.530448 lex=None vec=None final=None
    source_url=https://automotive-engineering.deu.ac.kr/automotive-engineering/sub08_02.do
    원문 일부: [TITLE] LAZO | 동아리 | 자동차공학과  [BODY] 동아리 목적  - CAE에 관심이 있는 학생들이 자기주도적으로 설계, 해석을 수행함으로써 CAE 분야의 전문 지식과 기술을 갖춘 인재를 양성하는 것에 목적을 두고 있습니다.
- 정답 후보 문서 존재 여부:
  - hits=1 title=KUSF 클럽챔피언십 2026 교내대회 지원 안내 doc=deu_external_notice_85576 chunk=deu_external_notice_85576_v001_chunk_001 source_type=external_notice content_type=clean
    source_url=https://www.deu.ac.kr/www/deu-external.do?article.offset=0&articleLimit=10&articleNo=85576&mode=view
  - hits=1 title='2026년도 국회의장배 청년 토론대회' 실시 doc=deu_external_notice_84552 chunk=deu_external_notice_84552_v001_chunk_002 source_type=external_notice content_type=None
    source_url=https://www.deu.ac.kr/www/deu-external.do?article.offset=30&articleLimit=10&articleNo=84552&mode=view
  - hits=1 title=홍보 서포터즈 모집안내(국토교통부 전세사기 피해 예방 홍보) doc=deu_external_notice_84495 chunk=deu_external_notice_84495_v001_chunk_002 source_type=external_notice content_type=None
    source_url=https://www.deu.ac.kr/www/deu-external.do?article.offset=30&articleLimit=10&articleNo=84495&mode=view
  - hits=1 title=2026년 대통령과학장학금 신규장학생 선발 공고 doc=deu_scholarship_84060 chunk=deu_scholarship_84060_v001_chunk_101 source_type=scholarship content_type=None
    source_url=https://www.deu.ac.kr/www/deu-scholarship.do?article.offset=10&articleLimit=10&articleNo=84060&mode=view
  - hits=1 title=2026년 대통령과학장학금 신규장학생 선발 공고 doc=deu_scholarship_84060 chunk=deu_scholarship_84060_v001_chunk_097 source_type=scholarship content_type=None
    source_url=https://www.deu.ac.kr/www/deu-scholarship.do?article.offset=10&articleLimit=10&articleNo=84060&mode=view

### [Case 4] query_id=473 / request_id=3575e5db-df1e-4c17-a277-69de599a8579
- created_at: 2026-05-20T13:55:39.274312+09:00
- 질문: 컴퓨터공학과 2학년 전공필수 과목
- 답변: 컴퓨터공학과 2학년의 전공필수 과목은 다음과 같습니다.  *   토목공학과: 도시정책론, 교통조사분석및실습, 토지이용계획(키스톤디자인) *   환경공학과: 환경기초계산  사이트 바로가기: https://www.deu.ac.kr/
- 문제 유형: D. 노이즈 문서가 상위에 섞임
- intent/category/filters/rewrite: INFO / None / {'department': ['학과사무실']} / 컴퓨터공학과 2학년 전공필수 과목
- 원인 분석: duplicate_doc_ratio=0.4285714285714286로 동일/유사 문서 반복 위험
- 수정 필요 지점: dedupe / TopK selection
- 검색된 문서:
  - lexical#1 🧿2026학년도 AX마이크로디그리 학과별 교과목 편성현황 및 K-MOOC 교과목 상세🧿 doc=deu_advising_80889 chunk=deu_advising_80889_v001_chunk_027 lex=5.95000028610229 vec=None final=0.856115113836805
  - lexical#2 📌2026학년도 학과(전공)별 비교과프로그램 안내📌 doc=deu_advising_83383 chunk=deu_advising_83383_v001_chunk_004 lex=5.85000019073486 vec=None final=0.854014602605037
  - lexical#3 2026학년도 1학기 동의대학교 비전임교원 공개채용 안내 doc=deu_job_80080 chunk=deu_job_80080_v001_chunk_010 lex=5.85000009536743 vec=None final=0.854014600572592
  - lexical#4 🧿2026학년도 AX마이크로디그리 학과별 교과목 편성현황 및 K-MOOC 교과목 상세🧿 doc=deu_advising_80889 chunk=deu_advising_80889_v001_chunk_026 lex=5.75 vec=None final=0.851851851851852
  - lexical#5 2026학년도 1학기 동의대학교 비전임교원 공개채용 안내 doc=deu_job_80080 chunk=deu_job_80080_v001_chunk_009 lex=5.24999995231628 vec=None final=0.839999998779297
- 선택된 chunk:
  - rank=1 title=🧿2026학년도 AX 마이크로디그리 운영 안내🧿 source_type=advising content_type=None score=3.176304 rerank=3.176304 lex=None vec=None final=None
    source_url=https://advising.deu.ac.kr/advising/sub04_01.do?article.offset=0&articleLimit=10&articleNo=80146&mode=view
    원문 일부: [TITLE] 🧿2026학년도 AX 마이크로디그리 운영 안내🧿  [ATTACHMENT] 1. 2026학년도 학과(전공)별 AX마이크로디그리 편성 현황.xlsx   500211 건축환경공학 N 전공선택 학년 학년 503758 철근콘크리트구조Ⅰ N 전공선택 학점 학년 511190 건축BIM설계 N 전공선택 학점 학년 510709 건축설비BIM설계 N 자유선택 - 학년 토목공학과 K-MOOC(6) 생성형인공지능입문 Y 전공필수 교과목명 학년 400523 토목공학개론 N • 국가직, 공기업 등 건설 AI 관련 분야의 전문직 • 설계,...
- 정답 후보 문서 존재 여부:
  - hits=4 title=🟣2026학년도 2학기 학생설계전공(제2전공) 이수 신청 안내🟣 doc=deu_advising_85097 chunk=deu_advising_85097_v001_chunk_055 source_type=advising content_type=None
    source_url=https://advising.deu.ac.kr/advising/sub04_01.do?article.offset=0&articleLimit=10&articleNo=85097&mode=view
  - hits=4 title=2026학년도 교육과정 doc=deu_safety_80836 chunk=deu_safety_80836_v001_chunk_053 source_type=safety content_type=None
    source_url=https://www.deu.ac.kr/www/deu-curriculum.do?article.offset=0&articleLimit=10&articleNo=80836&mode=view
  - hits=4 title=📝 다전공 진로로드맵 작성을 위한 워크시트 📝 doc=deu_advising_80497 chunk=deu_advising_80497_v001_chunk_054 source_type=advising content_type=None
    source_url=https://advising.deu.ac.kr/advising/sub04_02.do?article.offset=0&articleLimit=10&articleNo=80497&mode=view
  - hits=3 title=🟣2026학년도 2학기 학생설계전공(제2전공) 이수 신청 안내🟣 doc=deu_advising_85097 chunk=deu_advising_85097_v001_chunk_057 source_type=advising content_type=None
    source_url=https://advising.deu.ac.kr/advising/sub04_01.do?article.offset=0&articleLimit=10&articleNo=85097&mode=view
  - hits=3 title=2026-하계 계절수업 안내 doc=deu_academic_notice_84378 chunk=deu_academic_notice_84378_v001_chunk_020 source_type=academic_notice content_type=None
    source_url=https://www.deu.ac.kr/www/gra-notice.do?article.offset=0&articleLimit=10&articleNo=84378&mode=view

### [Case 5] query_id=472 / request_id=0d9e799a-ccf7-42f9-b2b1-bd58ea86270f
- created_at: 2026-05-20T13:54:47.815411+09:00
- 질문: 컴퓨터공학과 이수표 정보
- 답변: 컴퓨터공학과 이수표 정보를 제공해 드리겠습니다.  이수표는 각 실습실의 주요실습과목을 포함하여 컴퓨터공학 학부 학생들이 이수할 수 있는 과목입니다.   *   컴퓨터 시스템 실습실 (Computer System Lab) : 기초프로그래밍 I, II, 객체지향 프로그래밍, 비주얼프로그래밍, 어셈블리언어 실습, 공학기술프로그래밍, 자바프로그래밍, 데이터베이스응용, 소프트웨어공학, 웹프로그래밍, 캡스톤디자인 I, II, 머신러닝 프로그래밍 등 *   컴퓨터 소프트웨어 실습실 (Computer Software Lab) : 객체지향 프로그래밍, 비주얼프로그래밍, 어셈블리언어 실습, 공학기술프로그래밍, 자바프로그래밍, 데이터베이스응용, 소프트웨어공학, 웹프로그래밍, 캡스톤디자인 I, II 등 *   컴퓨터 하드웨어 실습실 (Computer Hardware Lab)  사이트 바로가기: https://www.deu.ac.kr/
- 문제 유형: D. 노이즈 문서가 상위에 섞임
- intent/category/filters/rewrite: INFO / None / {'department': ['학과사무실']} / 컴퓨터공학과 이수표 정보
- 원인 분석: duplicate_doc_ratio=0.4로 동일/유사 문서 반복 위험
- 수정 필요 지점: dedupe / TopK selection
- 검색된 문서:
  - lexical#1 📝 다전공 진로로드맵 작성을 위한 워크시트 📝 doc=deu_advising_80497 chunk=deu_advising_80497_v001_chunk_092 lex=3.89999995231628 vec=None final=0.795918365360945
  - lexical#2 2025학년도 후기(2026년 8월 졸업) 학위청구논문심사 신청 안내 doc=deu_department_84194 chunk=deu_department_84194_v001_chunk_035 lex=3.35 vec=None final=0.770114942528736
  - lexical#3 학과 취업 공지사항 게시판목록 | 컴퓨터공학과 doc=static_176071885c1ffbf8 chunk=static_176071885c1ffbf8_v001_chunk_001 lex=2.89999997615814 vec=None final=0.743589742022232
  - lexical#4 컴퓨터 시스템 실습실 | 실습실 | 컴퓨터공학과 doc=static_0d0570e71e6e207f chunk=static_0d0570e71e6e207f_v001_chunk_001 lex=2.85000002384186 vec=None final=0.740259741868231
  - lexical#5 컴퓨터 소프트웨어 실습실 | 실습실 | 컴퓨터공학과 doc=static_15012905bc502fd7 chunk=static_15012905bc502fd7_v001_chunk_001 lex=2.85000002384186 vec=None final=0.740259741868231
- 선택된 chunk:
  - rank=1 title=컴퓨터 시스템 실습실 | 실습실 | 컴퓨터공학과 source_type=department content_type=clean score=3.702079 rerank=3.702079 lex=None vec=None final=None
    source_url=https://swcc.deu.ac.kr/computer/sub04_01.do
    원문 일부: [TITLE] 컴퓨터 시스템 실습실 | 실습실 | 컴퓨터공학과  [BODY] 컴퓨터 시스템 실습실 (Computer System Lab)  컴퓨터 시스템을 구성하는 하드웨어와 소프트웨어의 구성 및 동작 원리를 배우고, 이를 바탕으로 응용 소프트웨어 개발을 익히는 실습실입니다. - 주요실습과목 : 기초프로그래밍 I, II, 객체지향 프로그래밍, 비주얼프로그래밍, 어셈블리언어 실습, 공학기술프로그래밍, 자바프로그래밍, 데이터베이스응용, 소프트웨어공학, 웹프로그래밍, 캡스톤디자인 I, II, 머신러닝 프로그래밍 등 - 위치 : 정보...
  - rank=2 title=컴퓨터 소프트웨어 실습실 | 실습실 | 컴퓨터공학과 source_type=department content_type=clean score=3.702079 rerank=3.702079 lex=None vec=None final=None
    source_url=https://swcc.deu.ac.kr/computer/sub04_03.do
    원문 일부: [TITLE] 컴퓨터 소프트웨어 실습실 | 실습실 | 컴퓨터공학과  [BODY] 컴퓨터 소프트웨어 실습실(Computer Software Lab)  컴퓨터 시스템을 구성하는 소프트웨어 개발 및 응용을 익히는 실습실입니다. - 주요실습과목 : 객체지향 프로그래밍, 비주얼프로그래밍, 어셈블리언어 실습, 공학기술프로그래밍, 자바프로그래밍, 데이터베이스응용, 소프트웨어공학, 웹프로그래밍, 캡스톤디자인 I, II 등 - 위치 : 정보공학관 816호실 - 보유 기자재 : 최신 실습용 컴퓨터와 LCD 모니터, 빔프로젝터, 전자교탁, 레이저...
  - rank=3 title=컴퓨터 하드웨어 실습실 | 실습실 | 컴퓨터공학과 source_type=department content_type=clean score=3.702079 rerank=3.702079 lex=None vec=None final=None
    source_url=https://swcc.deu.ac.kr/computer/sub04_02.do
    원문 일부: [TITLE] 컴퓨터 하드웨어 실습실 | 실습실 | 컴퓨터공학과  [BODY] 컴퓨터 하드웨어 실습실(Computer Hardware Lab)  컴퓨터 시스템을 구성하는 하드웨어와 마이크로컨트롤러, 임베디드 소프트웨어와 하드웨어 개발과 응용을 익히는 실습실입니다. - 주요실습과목 : 디지털논리회로및실습, 논리설계및실습, 마이크로컨트롤러응용, 임베디드시시템및실습, 캡스톤디자인 I, II 등 - 위치 : 정보공학관 815호실 - 보유 기자재 : 최신 실습용 컴퓨터와 LCD 모니터, 빔프로젝터, 전자교탁, 레이저프린터, 논리회로설계...
- 정답 후보 문서 존재 여부:
  - hits=3 title=2026학년도 신입생 수강신청 관련 안내(신입생 필독) doc=deu_notice_81190 chunk=deu_notice_81190_v001_chunk_014 source_type=notice content_type=None
    source_url=https://www.deu.ac.kr/www/deu-notice.do?article.offset=30&articleLimit=10&articleNo=81190&mode=view
  - hits=3 title=2026학년도 1학년 1학기 신입생 및 복학생 수강신청 안내 doc=deu_department_81033 chunk=deu_department_81033_v001_chunk_009 source_type=department content_type=None
    source_url=https://swcc.deu.ac.kr/swcc/sub01_04.do?article.offset=20&articleLimit=10&articleNo=81033&mode=view
  - hits=3 title=2026학년도 1학기 1학년 신입생 및 복학생 수강신청 안내 doc=deu_academic_notice_80856 chunk=deu_academic_notice_80856_v001_chunk_009 source_type=academic_notice content_type=None
    source_url=https://www.deu.ac.kr/www/gra-notice.do?article.offset=10&articleLimit=10&articleNo=80856&mode=view
  - hits=3 title=이수표 | 교육과정 | 컴퓨터공학과 doc=static_06b9d3809cb12e19 chunk=static_06b9d3809cb12e19_v001_chunk_001 source_type=department content_type=clean
    source_url=https://swcc.deu.ac.kr/computer/sub03_01.do
  - hits=3 title=학과사무실 위치 및 연락처 | 학과소개 | 컴퓨터공학과 doc=static_01840b5a30b433c1 chunk=static_01840b5a30b433c1_v001_chunk_002 source_type=department content_type=clean
    source_url=https://swcc.deu.ac.kr/computer/sub01_05.do

### [Case 6] query_id=469 / request_id=d6ed704e-d169-4f34-bb77-2f92a387f4db
- created_at: 2026-05-20T13:52:06.786482+09:00
- 질문: 7대 총장 누구야?
- 답변: 동의대학교 제 7대 총장은 whom이세요?  제공된 문서에서 관련 정보를 찾지 못했습니다.  사이트 바로가기: https://www.deu.ac.kr/
- 문제 유형: D. 노이즈 문서가 상위에 섞임
- intent/category/filters/rewrite: INFO / None / {} / 7대 총장 누구
- 원인 분석: selected chunk에 메뉴/공유/SNS/게시판 등 UI성 텍스트가 포함됨
- 수정 필요 지점: text cleaning / noise filter
- 검색된 문서:
  - lexical#1 역대총장 | 총장 | DEU doc=static_7fe939fbbc6bdf3b chunk=static_7fe939fbbc6bdf3b_v001_chunk_001 lex=2.19999997615814 vec=None final=0.687499997671694
  - lexical#2 2026학년도 신입생 수강신청 관련 안내(신입생 필독) doc=deu_notice_81190 chunk=deu_notice_81190_v001_chunk_026 lex=1.30000003576279 vec=None final=0.565217398064799
  - lexical#3 2026학년도 1학기 성적우수장학생 선발안내(1/19~1/21) doc=deu_scholarship_79493 chunk=deu_scholarship_79493_v001_chunk_004 lex=1.25000002384186 vec=None final=0.555555560265058
  - lexical#4 2026년 전반기 육군 학군사관후보생 67, 68기 선발계획공고 doc=deu_job_82096 chunk=deu_job_82096_v001_chunk_003 lex=1.25 vec=None final=0.555555555555556
  - lexical#5 제138차 대학평의원회 회의록 doc=deu_council_notice_79841 chunk=deu_council_notice_79841_v001_chunk_071 lex=1.15 vec=None final=0.534883720930233
  - vector#1 역대총장 | 총장 | DEU doc=static_7fe939fbbc6bdf3b chunk=static_7fe939fbbc6bdf3b_v001_chunk_001 lex=None vec=0.450242853135726 final=0.450242853135726
- 선택된 chunk:
  - rank=1 title=역대총장 | 총장 | DEU source_type=institution content_type=clean score=4.85 rerank=4.85 lex=2.19999997615814 vec=None final=0.687499997671694
    source_url=https://www.deu.ac.kr/www/former-university-presidents.do
    원문 일부: [TITLE] 역대총장 | 총장 | DEU  [BODY] body  동의대학교 제12대 · 13대총장 한 수 환 ( 韓 洙 桓 ) 학력 1986. 2. 연세대학교 전자공학과 (공학사) 1990. 3. 플로리다공대 전기전자공학 (공학석사) 1993. 6. 플로리다공대 전기전자공학 (공학박사) 경력 2005. 3. ~ 2009. 2. 영상정보대학장 2014. 8. ~ 2019. 1. 교무처장 2017. 8. ~ 2019. 2. 동의PRIME사업단장 2017. 8. ~ 2020. 7. 교학부총장 2020. 8. ~ 2023. 8. ...
  - rank=2 title=총장메세지 | 총장 | DEU source_type=institution content_type=clean score=3.443323 rerank=3.443323 lex=None vec=0.385531521705901 final=0.385531521705901
    source_url=https://www.deu.ac.kr/www/deu-message.do
    원문 일부: [TITLE] 총장메세지 | 총장 | DEU  [BODY] body  에도 앞장서고 있습니다. 이러한 대학의 기능과 역할을 성실히 수행하며 학생들이 꿈을 펼칠 수 있는 대학으로 거듭나고 있습니다. 앞으로도 동의대는 오늘보다 내일이 더욱 기대되는 ‘대학다운 대학’으로 전진할 것을 약속드립니다. 동의대학교 총장 최종수정일 2025.03.10
  - rank=3 title=동의대학교 미래교육원 > 학점은행제 > 경영과 > 모집안내 source_type=lifelong content_type=clean score=2.208337 rerank=2.208337 lex=None vec=None final=None
    source_url=https://lifelong.deu.ac.kr/Contents/Contents.aspx?MENU_ID=140&PAGE_NO=35
    원문 일부: [TITLE] 동의대학교 미래교육원 > 학점은행제 > 경영과 > 모집안내  [BODY] 동의대학교 총장 명의 학위증  - 개인정보처리방침 - 사이트 이용약관 -  47340 부산광역시 부산진구 엄광로 176 동의대학교 지천관 2층 207호 미래교육원 TEL. 051)890-1947~8 FAX. 0502-600-9396 Copyright 2014 lifelong.deu.ac.kr All Rights Reserved.
- 정답 후보 문서 존재 여부:
  - hits=3 title=역대총장 | 총장 | DEU doc=static_7fe939fbbc6bdf3b chunk=static_7fe939fbbc6bdf3b_v001_chunk_001 source_type=institution content_type=clean
    source_url=https://www.deu.ac.kr/www/former-university-presidents.do
  - hits=2 title=2026년도 산학협동재단 장학금 지원사업 장학생 선발 공고 안내 [사회적배려대상자 및 외국인 근로자 자녀 학생 해당] doc=deu_scholarship_85702 chunk=deu_scholarship_85702_v001_chunk_010 source_type=scholarship content_type=None
    source_url=https://www.deu.ac.kr/www/deu-scholarship.do?article.offset=0&articleLimit=10&articleNo=85702&mode=view
  - hits=2 title=2026년도 산학협동재단 장학금 지원사업 장학생 선발 공고 안내 [사회적배려대상자 및 외국인 근로자 자녀 학생 해당] doc=deu_scholarship_85702 chunk=deu_scholarship_85702_v001_chunk_024 source_type=scholarship content_type=None
    source_url=https://www.deu.ac.kr/www/deu-scholarship.do?article.offset=0&articleLimit=10&articleNo=85702&mode=view
  - hits=2 title=릴레이 토크콘서트「청년담(談)장」참가자(이야기 영상) 공모전 doc=deu_external_notice_85712 chunk=deu_external_notice_85712_v001_chunk_004 source_type=external_notice content_type=None
    source_url=https://www.deu.ac.kr/www/deu-external.do?article.offset=0&articleLimit=10&articleNo=85712&mode=view
  - hits=2 title=2026년도 산학협동재단 장학금 지원사업 장학생 선발 공고 안내 [사회적배려대상자 및 외국인 근로자 자녀 학생 해당] doc=deu_scholarship_85702 chunk=deu_scholarship_85702_v001_chunk_023 source_type=scholarship content_type=None
    source_url=https://www.deu.ac.kr/www/deu-scholarship.do?article.offset=0&articleLimit=10&articleNo=85702&mode=view

### [Case 7] query_id=478 / request_id=b39d3a2e-7868-4b26-92c9-afd5f1362b2a
- created_at: 2026-05-20T14:00:49.777694+09:00
- 질문: 동의대 23번 건물 이름
- 답변: 동의대학교 23번 건물 이름은 "HOME 후원의 집"입니다.  사이트 바로가기: https://www.deu.ac.kr/
- 문제 유형: D. 노이즈 문서가 상위에 섞임
- intent/category/filters/rewrite: INFO / None / {} / 동의대 23번 건물 이름
- 원인 분석: selected chunk에 메뉴/공유/SNS/게시판 등 UI성 텍스트가 포함됨
- 수정 필요 지점: text cleaning / noise filter
- 검색된 문서:
  - lexical#1 ✨📚 동의대학교 자유전공(유형Ⅰ) 가이드북✨📚 doc=deu_advising_81177 chunk=deu_advising_81177_v001_chunk_025 lex=2.05000004768372 vec=None final=0.672131152666887
  - lexical#2 ✨📚 동의대학교 자유전공(유형Ⅰ) 가이드북✨📚 doc=deu_advising_81177 chunk=deu_advising_81177_v001_chunk_063 lex=1.95000002384186 vec=None final=0.661016951892199
  - lexical#3 동의대학교 대외협력팀 doc=static_52a3f8268c2cafd0 chunk=static_52a3f8268c2cafd0_v001_chunk_001 lex=1.60000002384186 vec=None final=0.615384618911517
  - lexical#4 동의대학교 인재개발처 홈페이지 doc=static_2539e5b4db27a7fd chunk=static_2539e5b4db27a7fd_v001_chunk_002 lex=1.34999998807907 vec=None final=0.574468082947772
  - lexical#5 공지사항 doc=static_58179eceebcb1218 chunk=static_58179eceebcb1218_v001_chunk_003 lex=1.00000001192093 vec=None final=0.500000002980232
  - vector#1 2026학년도 신입생 수강신청 관련 안내(신입생 필독) doc=deu_notice_81190 chunk=deu_notice_81190_v001_chunk_011 lex=None vec=0.622574306879897 final=0.622574306879897
- 선택된 chunk:
  - rank=1 title=공지사항 source_type=academic_support content_type=clean score=3.844731 rerank=3.844731 lex=1.00000001192093 vec=None final=0.500000002980232
    source_url=http://dess.deu.ac.kr/index.php?mid=Notice&document_srl=2052
    원문 일부: [TITLE] 공지사항  [BODY] 코로나 19로 인한 ‘동의 모바일 학생증’을 이용한 QR인증 건물 출입 시행안내  20126 49 | 2021학년도 1학기 경남대학교 학점교류 수학 안내문 | 학사지원팀 | 2021.01.20 | 3720 » | 코로나 19로 인한 ‘동의 모바일 학생증’을 이용한 QR인증 건물 출입 시행안내 | 학사지원팀 | 2020.10.06 | 12092 47 | 2020학년도 2학기 모바일 학생증 사용에 따른 증명사진 등록 안내 | 학사지원팀 | 2020.08.26 | 5310 46 | 2020학년도...
  - rank=2 title=[박물관 교육 - 유아 대상] 반짝반짝 내 이름 키링 만들기 source_type=institution content_type=clean score=3.088244 rerank=3.088244 lex=None vec=None final=None
    source_url=https://www.deu.ac.kr/www/deu-museum-notice.do?article.offset=0&articleLimit=10&articleNo=83028&mode=view
    원문 일부: [TITLE] [박물관 교육 - 유아 대상] 반짝반짝 내 이름 키링 만들기  [BODY] body  박물관 소개 관람안내·자료이용 공지사항 전시마당 교육·행사 소장품 [박물관 교육 - 유아 대상] 반짝반짝 내 이름 키링 만들기 안녕하세요. 동의대학교 박물관 입니다. 박물관에서는 6~7세 유아들을 대상으로 「반짝반짝 내 이름 키링 만들기 체험교육을 진행합니다. 갓 한글을 배우기 시작한 아이들이 자신의 이름 자음 모음을 조합하여 키링으로 제작하는 활동을 통해 한글에 쉽게 다가가고, 비즈 체험을 통해 소근육 강화와 창의적 활동 경험...
  - rank=3 title=동의대학교 대외협력팀 source_type=fund content_type=clean score=1.747286 rerank=1.747286 lex=None vec=None final=None
    source_url=https://deufund.deu.ac.kr/exchange/na/ntt/selectNttList.do?mi=1085&bbsId=1063
    원문 일부: [TITLE] 동의대학교 대외협력팀  [BODY] 음식점 HOME 후원의 집 후원의 집 현황 음식점 공유 페이스북 트위터 youtube 블로그 카카오톡 인스타그램 카카오스토리 인쇄  - 재능기부 기관 - 음식점 - 병원/약국 - 도서/자동차/기타 - 게시되는 글의 본문이나 첨부파일에 개인정보(주민등록번호, 휴대폰번호, 주소, 은행계좌번호, 신용카드번호 등 개인을 식별할 수 있는 모든 정보)를 포함시키지 않도록 주의 하시기 바랍니다. - 개인정보가 게시되어 노출 될 경우 해당 게시물 작성자가 관련 법령에 따라 처분 을 받을 수 ...
- 정답 후보 문서 존재 여부:
  - hits=3 title=학과사무실 위치 및 연락처 | 학과소개 | 컴퓨터공학과 doc=static_01840b5a30b433c1 chunk=static_01840b5a30b433c1_v001_chunk_001 source_type=department content_type=clean
    source_url=https://swcc.deu.ac.kr/computer/sub01_05.do
  - hits=2 title=제141차 대학평의원회 회의록 doc=deu_council_notice_85699 chunk=deu_council_notice_85699_v001_chunk_034 source_type=council_notice content_type=None
    source_url=https://www.deu.ac.kr/www/deu-council-notice.do?article.offset=0&articleLimit=10&articleNo=85699&mode=view
  - hits=2 title=[한국장애인개발원] 장애청년 채용 취업 정보 안내(5월 1차) doc=deu_disability_support_84954 chunk=deu_disability_support_84954_v001_chunk_013 source_type=disability_support content_type=None
    source_url=https://www.deu.ac.kr/www/deu-support-notice.do?article.offset=0&articleLimit=10&articleNo=84954&mode=view
  - hits=2 title=2026-하계 계절수업 안내 doc=deu_academic_notice_84378 chunk=deu_academic_notice_84378_v001_chunk_024 source_type=academic_notice content_type=None
    source_url=https://www.deu.ac.kr/www/gra-notice.do?article.offset=0&articleLimit=10&articleNo=84378&mode=view
  - hits=2 title=[한국장애인개발원] 장애청년 채용 취업 정보 안내(4월 1차) doc=deu_disability_support_83929 chunk=deu_disability_support_83929_v001_chunk_009 source_type=disability_support content_type=None
    source_url=https://www.deu.ac.kr/www/deu-support-notice.do?article.offset=0&articleLimit=10&articleNo=83929&mode=view

### [Case 8] query_id=475 / request_id=61ad5d83-25b3-46ee-8b83-718d16f57ece
- created_at: 2026-05-20T13:57:55.954147+09:00
- 질문: 동의대 23번 건물 정보
- 답변: 동의대학교 23번 건물은 동의대학교 미래교육원이 있는 지천관 2층 207호입니다.  지천관 2층 207호로 찾아오시는 길을 알려드리겠습니다. 1. 학교 정문에서 자연대 로터리(회차로)로 이동합니다. 2. 정문에서 제일 가까운 좌측 건물 (자연과학대학 아래 건물)에 도착합니다.  이건물을 찾는 경우, 캠퍼스맵을 참고해 주세요.  동의대학교 23번 건물은 지천관 2층 207호로 위치하고 있습니다.  사이트 바로가기: https://www.deu.ac.kr/
- 문제 유형: D. 노이즈 문서가 상위에 섞임
- intent/category/filters/rewrite: INFO / None / {} / 동의대 23번 건물 정보
- 원인 분석: selected chunk에 메뉴/공유/SNS/게시판 등 UI성 텍스트가 포함됨
- 수정 필요 지점: text cleaning / noise filter
- 검색된 문서:
  - lexical#1 ✨📚 동의대학교 자유전공(유형Ⅰ) 가이드북✨📚 doc=deu_advising_81177 chunk=deu_advising_81177_v001_chunk_025 lex=2.20000004768372 vec=None final=0.687500004656613
  - lexical#2 2026년 푸른등대 삼성기부장학금 신청 안내 (학부-AI핵심분야 진로 희망자, 대학원-인문사회계열 학과 전공자) doc=deu_scholarship_83658 chunk=deu_scholarship_83658_v001_chunk_023 lex=2.10000007152557 vec=None final=0.677419362281537
  - lexical#3 ✨📚 동의대학교 자유전공(유형Ⅰ) 가이드북✨📚 doc=deu_advising_81177 chunk=deu_advising_81177_v001_chunk_063 lex=2.10000002384186 vec=None final=0.677419357319652
  - lexical#4 동의대학교 대외협력팀 doc=static_52a3f8268c2cafd0 chunk=static_52a3f8268c2cafd0_v001_chunk_001 lex=1.60000002384186 vec=None final=0.615384618911517
  - lexical#5 연간일정 | 정보마당 | 전공설계지원센터 doc=static_0559aa12f2af4696 chunk=static_0559aa12f2af4696_v001_chunk_002 lex=1.45000001192093 vec=None final=0.591836736679871
  - vector#1 2026학년도 신입생 수강신청 관련 안내(신입생 필독) doc=deu_notice_81190 chunk=deu_notice_81190_v001_chunk_011 lex=None vec=0.629652180054915 final=0.629652180054915
- 선택된 chunk:
  - rank=1 title=동의대학교 대외협력팀 source_type=fund content_type=clean score=2.628572 rerank=2.628572 lex=None vec=None final=None
    source_url=https://deufund.deu.ac.kr/exchange/na/ntt/selectNttList.do?mi=1085&bbsId=1063
    원문 일부: [TITLE] 동의대학교 대외협력팀  [BODY] 음식점 HOME 후원의 집 후원의 집 현황 음식점 공유 페이스북 트위터 youtube 블로그 카카오톡 인스타그램 카카오스토리 인쇄  - 재능기부 기관 - 음식점 - 병원/약국 - 도서/자동차/기타 - 게시되는 글의 본문이나 첨부파일에 개인정보(주민등록번호, 휴대폰번호, 주소, 은행계좌번호, 신용카드번호 등 개인을 식별할 수 있는 모든 정보)를 포함시키지 않도록 주의 하시기 바랍니다. - 개인정보가 게시되어 노출 될 경우 해당 게시물 작성자가 관련 법령에 따라 처분 을 받을 수 ...
  - rank=2 title=동의대학교 미래교육원 > 미래교육원 소개 > 찾아오시는길 source_type=lifelong content_type=clean score=3.606317 rerank=3.606317 lex=None vec=None final=None
    source_url=https://lifelong.deu.ac.kr/Contents/Contents.aspx?MENU_ID=123&PAGE_NO=6
    원문 일부: [TITLE] 동의대학교 미래교육원 > 미래교육원 소개 > 찾아오시는길  [BODY] 미래교육원 위치 안내  동의대학교 가야캠퍼스 내에서 미래교육원이 있는 건물로 찾아오시는 길을 안내합니다. "지천관 2층 207호" 학교 정문 → 자연대 로터리(회차로) → 정문에서 제일 가까운 좌측 건물 (자연과학대학 아래 건물) 동의대학교 캠퍼스맵 안내 ≫ - 개인정보처리방침 - 사이트 이용약관 -  47340 부산광역시 부산진구 엄광로 176 동의대학교 지천관 2층 207호 미래교육원 TEL. 051)890-1947~8 FAX. 0502-...
  - rank=3 title=캠퍼스맵 | 캠퍼스안내 | DEU source_type=institution content_type=clean score=2.829545 rerank=2.829545 lex=None vec=0.552037358283997 final=0.552037358283997
    source_url=https://www.deu.ac.kr/www/deu-campus-map.do
    원문 일부: [TITLE] 캠퍼스맵 | 캠퍼스안내 | DEU  [BODY] body  장:3 간호학관 동의대학교 간호학관입니다. 참고 경사로:O, 장애인주차장:5 부속한방병원 ‘몸과 마음이 편안한 병원’, 동의의료원은 양방병원과 한방병원으로 이루어져 고객을 위해 최선의 의료를 제공하고 있습니다. 동의의료원 ‘몸과 마음이 편안한 병원’, 동의의료원은 양방병원과 한방병원으로 이루어져 고객을 위해 최선의 의료를 제공하고 있습니다. 닫기 가야캠퍼스 VR 캠퍼스 영상 대학본관 법정관 상경관 국제관 동의스포츠센터 상영관(제2학생회관) 수덕전(학생회관...
- 정답 후보 문서 존재 여부:
  - hits=3 title=학과사무실 위치 및 연락처 | 학과소개 | 컴퓨터공학과 doc=static_01840b5a30b433c1 chunk=static_01840b5a30b433c1_v001_chunk_001 source_type=department content_type=clean
    source_url=https://swcc.deu.ac.kr/computer/sub01_05.do
  - hits=2 title=제141차 대학평의원회 회의록 doc=deu_council_notice_85699 chunk=deu_council_notice_85699_v001_chunk_034 source_type=council_notice content_type=None
    source_url=https://www.deu.ac.kr/www/deu-council-notice.do?article.offset=0&articleLimit=10&articleNo=85699&mode=view
  - hits=2 title=[한국장애인개발원] 장애청년 채용 취업 정보 안내(5월 1차) doc=deu_disability_support_84954 chunk=deu_disability_support_84954_v001_chunk_013 source_type=disability_support content_type=None
    source_url=https://www.deu.ac.kr/www/deu-support-notice.do?article.offset=0&articleLimit=10&articleNo=84954&mode=view
  - hits=2 title=2026-하계 계절수업 안내 doc=deu_academic_notice_84378 chunk=deu_academic_notice_84378_v001_chunk_024 source_type=academic_notice content_type=None
    source_url=https://www.deu.ac.kr/www/gra-notice.do?article.offset=0&articleLimit=10&articleNo=84378&mode=view
  - hits=2 title=[한국장애인개발원] 장애청년 채용 취업 정보 안내(4월 1차) doc=deu_disability_support_83929 chunk=deu_disability_support_83929_v001_chunk_009 source_type=disability_support content_type=None
    source_url=https://www.deu.ac.kr/www/deu-support-notice.do?article.offset=0&articleLimit=10&articleNo=83929&mode=view

### [Case 9] query_id=474 / request_id=153e77b8-11b5-4a55-a5ad-01b71d198b8f
- created_at: 2026-05-20T13:56:21.354887+09:00
- 질문: IPP사업 정보
- 답변: 안녕하세요. 동의대학교 정보 안내를 도와드리고 있어요. 학사, 장학, 기숙사, 통학버스 같은 학교 정보를 물어봐 주세요.  사이트 바로가기: https://www.deu.ac.kr/
- 문제 유형: B. 데이터는 있지만 검색 실패
- intent/category/filters/rewrite: INFO / None / {} / None
- 원인 분석: DB 후보는 있지만 selected chunk가 없음
- 수정 필요 지점: retrieval / selection
- 검색된 문서:
- 선택된 chunk:
- 정답 후보 문서 존재 여부:
  - hits=1 title=제138차 대학평의원회 회의록 doc=deu_council_notice_79841 chunk=deu_council_notice_79841_v001_chunk_009 source_type=council_notice content_type=None
    source_url=https://www.deu.ac.kr/www/deu-council-notice.do?article.offset=0&articleLimit=10&articleNo=79841&mode=view
  - hits=1 title=제138차 대학평의원회 회의록 doc=deu_council_notice_79841 chunk=deu_council_notice_79841_v001_chunk_004 source_type=council_notice content_type=None
    source_url=https://www.deu.ac.kr/www/deu-council-notice.do?article.offset=0&articleLimit=10&articleNo=79841&mode=view
  - hits=1 title=학칙/규정 | 대학기관/규정 | DEU doc=static_d5c577516805bc01 chunk=static_d5c577516805bc01_v001_chunk_010 source_type=institution content_type=clean
    source_url=https://www.deu.ac.kr/www/rules.do
  - hits=1 title=동의대학교 장기현장실습시스템 doc=static_c6ef8d39a34bee3c chunk=static_c6ef8d39a34bee3c_v001_chunk_016 source_type=ipp content_type=clean
    source_url=https://ipp.deu.ac.kr/Admin/PageDetail.aspx?ID=115&PageNo=3&KeyWord=
  - hits=1 title=동의대학교 장기현장실습시스템 doc=static_c6ef8d39a34bee3c chunk=static_c6ef8d39a34bee3c_v001_chunk_001 source_type=ipp content_type=clean
    source_url=https://ipp.deu.ac.kr/Admin/PageDetail.aspx?ID=115&PageNo=3&KeyWord=

### [Case 10] query_id=481 / request_id=82e9feda-4e38-42e7-82c7-36d86a758143
- created_at: 2026-05-20T14:02:53.215066+09:00
- 질문: 정보공학관 편의점 위치
- 답변: 정보공학관 편의점 위치는 정보공학관 613호실입니다.  사이트 바로가기: https://www.deu.ac.kr/
- 문제 유형: C. 검색은 됐지만 selection/rerank 실패
- intent/category/filters/rewrite: INFO / None / {} / 정보공학관 편의점 위치
- 원인 분석: DB 후보 chunk가 retrieval/rerank 후보에는 있으나 selected chunk에는 없음
- 수정 필요 지점: rerank / TopK selection
- 검색된 문서:
  - lexical#1 2025학년도 후기(2026년 8월 졸업) 학위청구논문심사 신청 안내 doc=deu_department_84194 chunk=deu_department_84194_v001_chunk_035 lex=2.59999995231628 vec=None final=0.722222218542923
  - lexical#2 2025학년도 후기(2026년 8월 졸업) 학위청구논문심사 신청 안내 doc=deu_department_84194 chunk=deu_department_84194_v001_chunk_036 lex=2.19999997615814 vec=None final=0.687499997671694
  - lexical#3 2026년 푸른등대 삼성기부장학금 신청 안내 (학부-AI핵심분야 진로 희망자, 대학원-인문사회계열 학과 전공자) doc=deu_scholarship_83658 chunk=deu_scholarship_83658_v001_chunk_023 lex=1.85000004768372 vec=None final=0.649122812888115
  - lexical#4 제어시스템공학/지능형 로봇 연구실 | 실험실 | 전자공학과 doc=static_3f6b5e4027fed81c chunk=static_3f6b5e4027fed81c_v001_chunk_002 lex=1.50000001192093 vec=None final=0.600000001907349
  - lexical#5 멤브레인 공학 연구실 | 연구실 | 환경공학과 doc=static_a70082e6fb482bd6 chunk=static_a70082e6fb482bd6_v001_chunk_001 lex=1.44999998807907 vec=None final=0.591836732707884
  - vector#1 캠퍼스맵 | 캠퍼스안내 | DEU doc=static_19b132e7ab559d4e chunk=static_19b132e7ab559d4e_v001_chunk_010 lex=None vec=0.49915735405986 final=0.49915735405986
- 선택된 chunk:
  - rank=1 title=제어시스템공학/지능형 로봇 연구실 | 실험실 | 전자공학과 source_type=department content_type=clean score=3.205714 rerank=3.205714 lex=1.50000001192093 vec=None final=0.600000001907349
    source_url=https://ee.deu.ac.kr/ee/sub04_01.do
    원문 일부: [TITLE] 제어시스템공학/지능형 로봇 연구실 | 실험실 | 전자공학과  [BODY] 제어시스템공학/지능형 로봇 연구실  DC/BLDC 서보 모터 제어 시스템을 비롯하여 각종 제어 시스템과 스마트 자동화 시스템을 연구하며 로봇 제어 기술을 학습합니다. 로봇 매니퓰레이터, 밸런싱 로봇, 자율주행 로봇 제작을 위한 마이크로컨트롤러(ATmega, Cortex-M 등), 라즈베리파이, ROS(Robot Operating System), 리눅스 기반 프로그래밍, TCP/IP 인터넷 기반 원격 모니터링 시스템, 로봇 위치 인식과 비젼 ...
  - rank=2 title=제어실험실 | 실험실 | 로봇공학과 source_type=department content_type=clean score=2.859672 rerank=2.859672 lex=None vec=None final=None
    source_url=https://mecha.deu.ac.kr/mecha/sub04_02.do
    원문 일부: [TITLE] 제어실험실 | 실험실 | 로봇공학과  [BODY] 제어 실험(연구)실  제어공학이란 각종 공학시스템을 제어대상으로 하여 제어대상이 주어진 설계사양에 따라 동작하도록 제어입력을 조절하는 제어기 설계기술을 말합니다. 이러한 제어공학의 요소기술로는 센서를 활용한 제어대상의 정보 획득기술, 제어 알고리즘의 설계기술, 제어입력을 구현하는 구동기 활용기술 그리고 제어 알고리즘을 하드웨어로 구현하는 공학기술을 들 수 있으며, 이들을 융합하여 설계된 제어기는 제어대상을 외란 및 센서잡음을 포함하는 불확실성에도 견실한 안정성을 ...
  - rank=3 title=계측실험실 | 실험실 | 로봇공학과 source_type=department content_type=clean score=2.859672 rerank=2.859672 lex=None vec=None final=None
    source_url=https://mecha.deu.ac.kr/mecha/sub04_03.do
    원문 일부: [TITLE] 계측실험실 | 실험실 | 로봇공학과  [BODY] 계측 실험(연구)실  계측공학 기술은 센서를 통하여 공학 시스템의 정보(물리량)을 획득하는 기술로서 획득한 정보는 시스템의 모니터링, 제어, 고장/진단 등에 활용됩니다. 계측 실험실은 계측 시스템의 거동, 신호 변환, 신호 추출. 디지털 장치와 데이터 획득, 그리고 센서를 활용하여 온도, 압력, 유동, 스트레인, 힘, 토크 등의 물리량에 대한 측정 방법을 학습하며, LabVIEW 사용법, 신호분석 및 저장, DAQ 시스템 및 자동 계측 시스템을 구축하는 기술을 학...
- 정답 후보 문서 존재 여부:
  - hits=4 title=2026년 중대산업재해 등 사고 발생 대비 매뉴얼 doc=deu_reference_83242 chunk=deu_reference_83242_v001_chunk_010 source_type=reference content_type=None
    source_url=https://www.deu.ac.kr/www/deu-reference.do?article.offset=0&articleLimit=10&articleNo=83242&mode=view
  - hits=4 title=2026년 중대산업재해 등 사고 발생 대비 매뉴얼 doc=deu_reference_83242 chunk=deu_reference_83242_v001_chunk_009 source_type=reference content_type=None
    source_url=https://www.deu.ac.kr/www/deu-reference.do?article.offset=0&articleLimit=10&articleNo=83242&mode=view
  - hits=4 title=✨📚 동의대학교 자유전공(유형Ⅰ) 가이드북✨📚 doc=deu_advising_81177 chunk=deu_advising_81177_v001_chunk_063 source_type=advising content_type=None
    source_url=https://advising.deu.ac.kr/advising/sub04_02.do?article.offset=0&articleLimit=10&articleNo=81177&mode=view
  - hits=4 title=2026학년도 신입생 수강신청 관련 안내(신입생 필독) doc=deu_notice_81190 chunk=deu_notice_81190_v001_chunk_011 source_type=notice content_type=None
    source_url=https://www.deu.ac.kr/www/deu-notice.do?article.offset=30&articleLimit=10&articleNo=81190&mode=view
  - hits=4 title=2026학년도 1학년 1학기 신입생 및 복학생 수강신청 안내 doc=deu_department_81033 chunk=deu_department_81033_v001_chunk_006 source_type=department content_type=None
    source_url=https://swcc.deu.ac.kr/swcc/sub01_04.do?article.offset=20&articleLimit=10&articleNo=81033&mode=view

### [Case 11] query_id=480 / request_id=10de84ca-b933-4eb1-824b-f102dcd9eef4
- created_at: 2026-05-20T14:02:13.143164+09:00
- 질문: 정보공학관은 몇번 건물?
- 답변: 정보공학관은 정보공학관 613호실과 814호실이 있습니다.  사이트 바로가기: https://www.deu.ac.kr/
- 문제 유형: C. 검색은 됐지만 selection/rerank 실패
- intent/category/filters/rewrite: INFO / None / {} / 정보공학관 몇번 건물
- 원인 분석: DB 후보 chunk가 retrieval/rerank 후보에는 있으나 selected chunk에는 없음
- 수정 필요 지점: rerank / TopK selection
- 검색된 문서:
  - lexical#1 ✨📚 동의대학교 자유전공(유형Ⅰ) 가이드북✨📚 doc=deu_advising_81177 chunk=deu_advising_81177_v001_chunk_063 lex=2.84999995231628 vec=None final=0.740259737042758
  - lexical#2 2025학년도 후기(2026년 8월 졸업) 학위청구논문심사 신청 안내 doc=deu_department_84194 chunk=deu_department_84194_v001_chunk_035 lex=2.59999995231628 vec=None final=0.722222218542923
  - lexical#3 2025학년도 후기(2026년 8월 졸업) 학위청구논문심사 신청 안내 doc=deu_department_84194 chunk=deu_department_84194_v001_chunk_036 lex=2.19999997615814 vec=None final=0.687499997671694
  - lexical#4 2026년 푸른등대 삼성기부장학금 신청 안내 (학부-AI핵심분야 진로 희망자, 대학원-인문사회계열 학과 전공자) doc=deu_scholarship_83658 chunk=deu_scholarship_83658_v001_chunk_023 lex=2.10000007152557 vec=None final=0.677419362281537
  - lexical#5 ✨📚 동의대학교 자유전공(유형Ⅰ) 가이드북✨📚 doc=deu_advising_81177 chunk=deu_advising_81177_v001_chunk_025 lex=1.45000004768372 vec=None final=0.591836742637853
  - vector#1 학과사무실 위치 및 연락처 | 학과소개 | 컴퓨터공학과 doc=static_01840b5a30b433c1 chunk=static_01840b5a30b433c1_v001_chunk_001 lex=None vec=0.549362236337399 final=0.549362236337399
- 선택된 chunk:
  - rank=1 title=제어시스템공학/지능형 로봇 연구실 | 실험실 | 전자공학과 source_type=department content_type=clean score=2.984121 rerank=2.984121 lex=None vec=None final=None
    source_url=https://ee.deu.ac.kr/ee/sub04_01.do
    원문 일부: [TITLE] 제어시스템공학/지능형 로봇 연구실 | 실험실 | 전자공학과  [BODY] 제어시스템공학/지능형 로봇 연구실  DC/BLDC 서보 모터 제어 시스템을 비롯하여 각종 제어 시스템과 스마트 자동화 시스템을 연구하며 로봇 제어 기술을 학습합니다. 로봇 매니퓰레이터, 밸런싱 로봇, 자율주행 로봇 제작을 위한 마이크로컨트롤러(ATmega, Cortex-M 등), 라즈베리파이, ROS(Robot Operating System), 리눅스 기반 프로그래밍, TCP/IP 인터넷 기반 원격 모니터링 시스템, 로봇 위치 인식과 비젼 ...
  - rank=2 title=컴퓨터 시스템 실습실 | 실습실 | 컴퓨터공학과 source_type=department content_type=clean score=2.753333 rerank=2.753333 lex=None vec=None final=None
    source_url=https://swcc.deu.ac.kr/computer/sub04_01.do
    원문 일부: [TITLE] 컴퓨터 시스템 실습실 | 실습실 | 컴퓨터공학과  [BODY] 컴퓨터 시스템 실습실 (Computer System Lab)  컴퓨터 시스템을 구성하는 하드웨어와 소프트웨어의 구성 및 동작 원리를 배우고, 이를 바탕으로 응용 소프트웨어 개발을 익히는 실습실입니다. - 주요실습과목 : 기초프로그래밍 I, II, 객체지향 프로그래밍, 비주얼프로그래밍, 어셈블리언어 실습, 공학기술프로그래밍, 자바프로그래밍, 데이터베이스응용, 소프트웨어공학, 웹프로그래밍, 캡스톤디자인 I, II, 머신러닝 프로그래밍 등 - 위치 : 정보...
  - rank=3 title=컴퓨터 응용 실습실 | 실습실 | 컴퓨터공학과 source_type=department content_type=clean score=2.752334 rerank=2.752334 lex=None vec=None final=None
    source_url=https://swcc.deu.ac.kr/computer/sub04_04.do
    원문 일부: [TITLE] 컴퓨터 응용 실습실 | 실습실 | 컴퓨터공학과  [BODY] 컴퓨터 응용 실습실(Computer Application Lab)  컴퓨터 하드웨어와 소프트웨어를 활용하는 통합 설계와 실생활 응용을 익히는 실습실입니다. - 주요실습과목 : 디지털 신호처리, 디지털 영상처리, 어셈블리언어 실습, 공학기술프로그래밍, 자바프로그래밍, 데이터베이스응용, 소프트웨어공학, 캡스톤디자인 I, II, 머신러닝 프로그래밍 등 - 위치 : 정보공학관 817호실 - 보유 기자재 : 최신 실습용 컴퓨터와 LCD 모니터, 빔프로젝터, 전자...
- 정답 후보 문서 존재 여부:
  - hits=3 title=2026년 중대산업재해 등 사고 발생 대비 매뉴얼 doc=deu_reference_83242 chunk=deu_reference_83242_v001_chunk_009 source_type=reference content_type=None
    source_url=https://www.deu.ac.kr/www/deu-reference.do?article.offset=0&articleLimit=10&articleNo=83242&mode=view
  - hits=3 title=2026학년도 편입생 대상 수강신청 및 학점관련 안내 doc=deu_academic_notice_81202 chunk=deu_academic_notice_81202_v001_chunk_007 source_type=academic_notice content_type=None
    source_url=https://www.deu.ac.kr/www/gra-notice.do?article.offset=10&articleLimit=10&articleNo=81202&mode=view
  - hits=3 title=✨📚 동의대학교 자유전공(유형Ⅰ) 가이드북✨📚 doc=deu_advising_81177 chunk=deu_advising_81177_v001_chunk_063 source_type=advising content_type=None
    source_url=https://advising.deu.ac.kr/advising/sub04_02.do?article.offset=0&articleLimit=10&articleNo=81177&mode=view
  - hits=3 title=2026학년도 신입생 수강신청 관련 안내(신입생 필독) doc=deu_notice_81190 chunk=deu_notice_81190_v001_chunk_011 source_type=notice content_type=None
    source_url=https://www.deu.ac.kr/www/deu-notice.do?article.offset=30&articleLimit=10&articleNo=81190&mode=view
  - hits=3 title=2026학년도 신입생 수강신청 관련 안내(신입생 필독) doc=deu_notice_81190 chunk=deu_notice_81190_v001_chunk_010 source_type=notice content_type=None
    source_url=https://www.deu.ac.kr/www/deu-notice.do?article.offset=30&articleLimit=10&articleNo=81190&mode=view

### [Case 12] query_id=476 / request_id=b796d8ca-03b0-4a37-b059-38f9c16ca2e5
- created_at: 2026-05-20T13:58:42.453738+09:00
- 질문: 정보공학관 정보
- 답변: 정보공학관에 대한 정보를 제공해 드리겠습니다.  *   정보공학관에는 3개의 실습실이 있습니다.      *   컴퓨터 시스템 실습실 (Computer System Lab) : 정보공학관 814호실         *   주요실습과목: 기초프로그래밍 I, II, 객체지향 프로그래밍, 비주얼프로그래밍, 어셈블리언어 실습, 공학기술프로그래밍, 자바프로그래밍, 데이터베이스응용, 소프트웨어공학, 웹프로그래밍, 캡스톤디자인 I, II, 머신러닝 프로그래밍 등     *   컴퓨터 응용 실습실(Computer Application Lab) : 정보공학관 817호실         *   주요실습과목: 디지털 신호처리, 디지털 영상처리, 어셈블리언어 실습, 공학기술프로그래밍, 자바프로그래밍, 데이터베이스응용, 소프트웨어공학, 캡스톤디자인 I, II, 머신러닝 프  사이트 바로가기: https://www.deu.ac.kr/
- 문제 유형: B. 데이터는 있지만 검색 실패
- intent/category/filters/rewrite: INFO / None / {} / 정보공학관
- 원인 분석: DB 후보는 있으나 retrieval 후보/selected와 겹치지 않음
- 수정 필요 지점: lexical/vector query
- 검색된 문서:
  - lexical#1 2025학년도 후기(2026년 8월 졸업) 학위청구논문심사 신청 안내 doc=deu_department_84194 chunk=deu_department_84194_v001_chunk_035 lex=2.59999995231628 vec=None final=0.722222218542923
  - lexical#2 2025학년도 후기(2026년 8월 졸업) 학위청구논문심사 신청 안내 doc=deu_department_84194 chunk=deu_department_84194_v001_chunk_036 lex=2.19999997615814 vec=None final=0.687499997671694
  - lexical#3 2026년 푸른등대 삼성기부장학금 신청 안내 (학부-AI핵심분야 진로 희망자, 대학원-인문사회계열 학과 전공자) doc=deu_scholarship_83658 chunk=deu_scholarship_83658_v001_chunk_023 lex=1.85000004768372 vec=None final=0.649122812888115
  - lexical#4 RECS연구실 | 동아리/지원사업 | 로봇공학과 doc=static_1d82f8cff4cad490 chunk=static_1d82f8cff4cad490_v001_chunk_002 lex=1.65000000149012 vec=None final=0.622641509646154
  - lexical#5 제어시스템공학/지능형 로봇 연구실 | 실험실 | 전자공학과 doc=static_3f6b5e4027fed81c chunk=static_3f6b5e4027fed81c_v001_chunk_002 lex=1.65000000149012 vec=None final=0.622641509646154
  - vector#1 대학 | 교육 doc=static_ec6037f81cccc29b chunk=static_ec6037f81cccc29b_v001_chunk_004 lex=None vec=0.54639208316803 final=0.54639208316803
- 선택된 chunk:
  - rank=1 title=제어시스템공학/지능형 로봇 연구실 | 실험실 | 전자공학과 source_type=department content_type=clean score=4.878513 rerank=4.878513 lex=1.65000000149012 vec=None final=0.622641509646154
    source_url=https://ee.deu.ac.kr/ee/sub04_01.do
    원문 일부: [TITLE] 제어시스템공학/지능형 로봇 연구실 | 실험실 | 전자공학과  [BODY] 제어시스템공학/지능형 로봇 연구실  DC/BLDC 서보 모터 제어 시스템을 비롯하여 각종 제어 시스템과 스마트 자동화 시스템을 연구하며 로봇 제어 기술을 학습합니다. 로봇 매니퓰레이터, 밸런싱 로봇, 자율주행 로봇 제작을 위한 마이크로컨트롤러(ATmega, Cortex-M 등), 라즈베리파이, ROS(Robot Operating System), 리눅스 기반 프로그래밍, TCP/IP 인터넷 기반 원격 모니터링 시스템, 로봇 위치 인식과 비젼 ...
  - rank=2 title=컴퓨터 시스템 실습실 | 실습실 | 컴퓨터공학과 source_type=department content_type=clean score=4.45 rerank=4.45 lex=None vec=None final=None
    source_url=https://swcc.deu.ac.kr/computer/sub04_01.do
    원문 일부: [TITLE] 컴퓨터 시스템 실습실 | 실습실 | 컴퓨터공학과  [BODY] 컴퓨터 시스템 실습실 (Computer System Lab)  컴퓨터 시스템을 구성하는 하드웨어와 소프트웨어의 구성 및 동작 원리를 배우고, 이를 바탕으로 응용 소프트웨어 개발을 익히는 실습실입니다. - 주요실습과목 : 기초프로그래밍 I, II, 객체지향 프로그래밍, 비주얼프로그래밍, 어셈블리언어 실습, 공학기술프로그래밍, 자바프로그래밍, 데이터베이스응용, 소프트웨어공학, 웹프로그래밍, 캡스톤디자인 I, II, 머신러닝 프로그래밍 등 - 위치 : 정보...
  - rank=3 title=컴퓨터 응용 실습실 | 실습실 | 컴퓨터공학과 source_type=department content_type=clean score=4.447885 rerank=4.447885 lex=None vec=None final=None
    source_url=https://swcc.deu.ac.kr/computer/sub04_04.do
    원문 일부: [TITLE] 컴퓨터 응용 실습실 | 실습실 | 컴퓨터공학과  [BODY] 컴퓨터 응용 실습실(Computer Application Lab)  컴퓨터 하드웨어와 소프트웨어를 활용하는 통합 설계와 실생활 응용을 익히는 실습실입니다. - 주요실습과목 : 디지털 신호처리, 디지털 영상처리, 어셈블리언어 실습, 공학기술프로그래밍, 자바프로그래밍, 데이터베이스응용, 소프트웨어공학, 캡스톤디자인 I, II, 머신러닝 프로그래밍 등 - 위치 : 정보공학관 817호실 - 보유 기자재 : 최신 실습용 컴퓨터와 LCD 모니터, 빔프로젝터, 전자...
- 정답 후보 문서 존재 여부:
  - hits=3 title=2026-하계 계절수업 안내 doc=deu_academic_notice_84378 chunk=deu_academic_notice_84378_v001_chunk_022 source_type=academic_notice content_type=None
    source_url=https://www.deu.ac.kr/www/gra-notice.do?article.offset=0&articleLimit=10&articleNo=84378&mode=view
  - hits=3 title=2026-하계 계절수업 안내 doc=deu_academic_notice_84378 chunk=deu_academic_notice_84378_v001_chunk_010 source_type=academic_notice content_type=None
    source_url=https://www.deu.ac.kr/www/gra-notice.do?article.offset=0&articleLimit=10&articleNo=84378&mode=view
  - hits=3 title=2026-하계 계절수업 안내 doc=deu_academic_notice_84378 chunk=deu_academic_notice_84378_v001_chunk_011 source_type=academic_notice content_type=None
    source_url=https://www.deu.ac.kr/www/gra-notice.do?article.offset=0&articleLimit=10&articleNo=84378&mode=view
  - hits=3 title=[첨단산업인재양성부트캠프반도체사업단] 연구원 신규채용 공고 doc=deu_job_84269 chunk=deu_job_84269_v001_chunk_001 source_type=job content_type=clean
    source_url=https://www.deu.ac.kr/www/deu-job.do?article.offset=0&articleLimit=10&articleNo=84269&mode=view
  - hits=3 title=[첨단산업인재양성부트캠프반도체사업단] 연구원 신규채용 공고 doc=deu_job_84269 chunk=deu_job_84269_v001_chunk_008 source_type=job content_type=None
    source_url=https://www.deu.ac.kr/www/deu-job.do?article.offset=0&articleLimit=10&articleNo=84269&mode=view

### [Case 13] query_id=471 / request_id=c871f104-2bab-481a-aa57-5b75fab966d0
- created_at: 2026-05-20T13:54:02.528921+09:00
- 질문: 7대 총장 정보
- 답변: 동의대학교 제7대 총장 인 강창석 (姜昌錫)의 정보는 [문서 1]에서 제공됩니다.   강 창 석 (姜昌錫) 박사은 영남大学 문학박사입니다. 동의대학교 대학원장을 역임하고 있으며, 동의대학교 교학부 총장과 동의대학교 대학원 장을 지냈습니다.  동의대학교 제7대 총장은 2023년 8월에 취임했습니다.  사이트 바로가기: https://www.deu.ac.kr/
- 문제 유형: D. 노이즈 문서가 상위에 섞임
- intent/category/filters/rewrite: INFO / None / {} / 7대 총장 정보
- 원인 분석: selected chunk에 메뉴/공유/SNS/게시판 등 UI성 텍스트가 포함됨
- 수정 필요 지점: text cleaning / noise filter
- 검색된 문서:
  - lexical#1 역대총장 | 총장 | DEU doc=static_7fe939fbbc6bdf3b chunk=static_7fe939fbbc6bdf3b_v001_chunk_001 lex=2.34999997615814 vec=None final=0.701492535188963
  - lexical#2 2026년 푸른등대 삼성기부장학금 신청 안내 (학부-AI핵심분야 진로 희망자, 대학원-인문사회계열 학과 전공자) doc=deu_scholarship_83658 chunk=deu_scholarship_83658_v001_chunk_023 lex=1.85000004768372 vec=None final=0.649122812888115
  - lexical#3 2026년도 1학기 고졸 후학습자 장학사업(희망사다리Ⅱ유형) 신규장학생 신청 안내(3/4 ~ 3/27까지 연장) doc=deu_scholarship_82175 chunk=deu_scholarship_82175_v001_chunk_072 lex=1.55000003576279 vec=None final=0.607843142754754
  - lexical#4 2026학년도 신입생 수강신청 관련 안내(신입생 필독) doc=deu_notice_81190 chunk=deu_notice_81190_v001_chunk_026 lex=1.45000003576279 vec=None final=0.59183674065186
  - lexical#5 2026년도 1학기 고졸 후학습자 장학사업(희망사다리Ⅱ유형) 신규장학생 신청 안내(3/4 ~ 3/27까지 연장) doc=deu_scholarship_82175 chunk=deu_scholarship_82175_v001_chunk_071 lex=1.30000004768372 vec=None final=0.565217400318283
  - vector#1 역대총장 | 총장 | DEU doc=static_7fe939fbbc6bdf3b chunk=static_7fe939fbbc6bdf3b_v001_chunk_001 lex=None vec=0.439651992300272 final=0.439651992300272
- 선택된 chunk:
  - rank=1 title=역대총장 | 총장 | DEU source_type=institution content_type=clean score=5.32 rerank=5.32 lex=2.34999997615814 vec=None final=0.701492535188963
    source_url=https://www.deu.ac.kr/www/former-university-presidents.do
    원문 일부: [TITLE] 역대총장 | 총장 | DEU  [BODY] body  동의대학교 제12대 · 13대총장 한 수 환 ( 韓 洙 桓 ) 학력 1986. 2. 연세대학교 전자공학과 (공학사) 1990. 3. 플로리다공대 전기전자공학 (공학석사) 1993. 6. 플로리다공대 전기전자공학 (공학박사) 경력 2005. 3. ~ 2009. 2. 영상정보대학장 2014. 8. ~ 2019. 1. 교무처장 2017. 8. ~ 2019. 2. 동의PRIME사업단장 2017. 8. ~ 2020. 7. 교학부총장 2020. 8. ~ 2023. 8. ...
  - rank=2 title=총장메세지 | 총장 | DEU source_type=institution content_type=clean score=3.791914 rerank=3.791914 lex=None vec=None final=None
    source_url=https://www.deu.ac.kr/www/deu-message.do
    원문 일부: [TITLE] 총장메세지 | 총장 | DEU  [BODY] body  학생과 함께 성장하는 대학, 지역과 함께 발전하는 대학 동의대학교에서 여러분의 꿈을 펼치세요. 동의대학교는 대한민국 제2의 도시이자 해양수도인 부산의 중심부에 자리잡고 있는 종합대학교입니다. 1977년 공업입국이라는 사명감으로 개교한 이래 사회 각계에 필요한 우수한 산업 역군을 배출하며 대한민국의 산업화에 이바지하는 등 나라의 발전과 함께 성장해 왔습니다. 현대 사회는 산업화 시대를 거쳐 정보화와 디지털 시대를 뛰어넘어 인공지능과 로봇 시대를 맞이하고 있습니...
  - rank=3 title=동의대학교 미래교육원 > 학점은행제 > 경영과 > 모집안내 source_type=lifelong content_type=clean score=2.667542 rerank=2.667542 lex=None vec=0.366545192393375 final=0.366545192393375
    source_url=https://lifelong.deu.ac.kr/Contents/Contents.aspx?MENU_ID=140&PAGE_NO=35
    원문 일부: [TITLE] 동의대학교 미래교육원 > 학점은행제 > 경영과 > 모집안내  [BODY] 동의대학교 총장 명의 학위증  - 개인정보처리방침 - 사이트 이용약관 -  47340 부산광역시 부산진구 엄광로 176 동의대학교 지천관 2층 207호 미래교육원 TEL. 051)890-1947~8 FAX. 0502-600-9396 Copyright 2014 lifelong.deu.ac.kr All Rights Reserved.
- 정답 후보 문서 존재 여부:
  - hits=3 title=역대총장 | 총장 | DEU doc=static_7fe939fbbc6bdf3b chunk=static_7fe939fbbc6bdf3b_v001_chunk_001 source_type=institution content_type=clean
    source_url=https://www.deu.ac.kr/www/former-university-presidents.do
  - hits=2 title=2026년도 산학협동재단 장학금 지원사업 장학생 선발 공고 안내 [사회적배려대상자 및 외국인 근로자 자녀 학생 해당] doc=deu_scholarship_85702 chunk=deu_scholarship_85702_v001_chunk_010 source_type=scholarship content_type=None
    source_url=https://www.deu.ac.kr/www/deu-scholarship.do?article.offset=0&articleLimit=10&articleNo=85702&mode=view
  - hits=2 title=2026년도 산학협동재단 장학금 지원사업 장학생 선발 공고 안내 [사회적배려대상자 및 외국인 근로자 자녀 학생 해당] doc=deu_scholarship_85702 chunk=deu_scholarship_85702_v001_chunk_024 source_type=scholarship content_type=None
    source_url=https://www.deu.ac.kr/www/deu-scholarship.do?article.offset=0&articleLimit=10&articleNo=85702&mode=view
  - hits=2 title=2026년도 산학협동재단 장학금 지원사업 장학생 선발 공고 안내 [사회적배려대상자 및 외국인 근로자 자녀 학생 해당] doc=deu_scholarship_85702 chunk=deu_scholarship_85702_v001_chunk_023 source_type=scholarship content_type=None
    source_url=https://www.deu.ac.kr/www/deu-scholarship.do?article.offset=0&articleLimit=10&articleNo=85702&mode=view
  - hits=2 title=2026년도 산학협동재단 장학금 지원사업 장학생 선발 공고 안내 [사회적배려대상자 및 외국인 근로자 자녀 학생 해당] doc=deu_scholarship_85702 chunk=deu_scholarship_85702_v001_chunk_012 source_type=scholarship content_type=None
    source_url=https://www.deu.ac.kr/www/deu-scholarship.do?article.offset=0&articleLimit=10&articleNo=85702&mode=view

### [Case 14] query_id=470 / request_id=e8426254-7623-48ca-9107-3a3643ed4ed8
- created_at: 2026-05-20T13:53:21.619685+09:00
- 질문: 동의대 7대 총장 정보
- 답변: 동의대학교 7대 총장은 강창석(姜昌錫)입니다.  사이트 바로가기: https://www.deu.ac.kr/
- 문제 유형: D. 노이즈 문서가 상위에 섞임
- intent/category/filters/rewrite: INFO / None / {} / 동의대 7대 총장 정보
- 원인 분석: selected chunk에 메뉴/공유/SNS/게시판 등 UI성 텍스트가 포함됨
- 수정 필요 지점: text cleaning / noise filter
- 검색된 문서:
  - lexical#1 역대총장 | 총장 | DEU doc=static_7fe939fbbc6bdf3b chunk=static_7fe939fbbc6bdf3b_v001_chunk_001 lex=2.34999997615814 vec=None final=0.701492535188963
  - lexical#2 2026년 푸른등대 삼성기부장학금 신청 안내 (학부-AI핵심분야 진로 희망자, 대학원-인문사회계열 학과 전공자) doc=deu_scholarship_83658 chunk=deu_scholarship_83658_v001_chunk_023 lex=1.85000004768372 vec=None final=0.649122812888115
  - lexical#3 동의대학교 대외협력팀 doc=static_52a3f8268c2cafd0 chunk=static_52a3f8268c2cafd0_v001_chunk_001 lex=1.60000002384186 vec=None final=0.615384618911517
  - lexical#4 2026년도 1학기 고졸 후학습자 장학사업(희망사다리Ⅱ유형) 신규장학생 신청 안내(3/4 ~ 3/27까지 연장) doc=deu_scholarship_82175 chunk=deu_scholarship_82175_v001_chunk_072 lex=1.55000003576279 vec=None final=0.607843142754754
  - lexical#5 동의대학교 2026학년도 가을학기 영어연수과정(D-4-7) 모집 doc=deu_exchange_84585 chunk=deu_exchange_84585_v001_chunk_014 lex=1.55000000596046 vec=None final=0.607843138171544
  - vector#1 역대총장 | 총장 | DEU doc=static_7fe939fbbc6bdf3b chunk=static_7fe939fbbc6bdf3b_v001_chunk_001 lex=None vec=0.693849861621857 final=0.693849861621857
- 선택된 chunk:
  - rank=1 title=역대총장 | 총장 | DEU source_type=institution content_type=clean score=4.92 rerank=4.92 lex=2.34999997615814 vec=None final=0.701492535188963
    source_url=https://www.deu.ac.kr/www/former-university-presidents.do
    원문 일부: [TITLE] 역대총장 | 총장 | DEU  [BODY] body  동의대학교 제12대 · 13대총장 한 수 환 ( 韓 洙 桓 ) 학력 1986. 2. 연세대학교 전자공학과 (공학사) 1990. 3. 플로리다공대 전기전자공학 (공학석사) 1993. 6. 플로리다공대 전기전자공학 (공학박사) 경력 2005. 3. ~ 2009. 2. 영상정보대학장 2014. 8. ~ 2019. 1. 교무처장 2017. 8. ~ 2019. 2. 동의PRIME사업단장 2017. 8. ~ 2020. 7. 교학부총장 2020. 8. ~ 2023. 8. ...
  - rank=2 title=총장메세지 | 총장 | DEU source_type=institution content_type=clean score=3.846522 rerank=3.846522 lex=None vec=0.617160558700562 final=0.617160558700562
    source_url=https://www.deu.ac.kr/www/deu-message.do
    원문 일부: [TITLE] 총장메세지 | 총장 | DEU  [BODY] body  학생과 함께 성장하는 대학, 지역과 함께 발전하는 대학 동의대학교에서 여러분의 꿈을 펼치세요. 동의대학교는 대한민국 제2의 도시이자 해양수도인 부산의 중심부에 자리잡고 있는 종합대학교입니다. 1977년 공업입국이라는 사명감으로 개교한 이래 사회 각계에 필요한 우수한 산업 역군을 배출하며 대한민국의 산업화에 이바지하는 등 나라의 발전과 함께 성장해 왔습니다. 현대 사회는 산업화 시대를 거쳐 정보화와 디지털 시대를 뛰어넘어 인공지능과 로봇 시대를 맞이하고 있습니...
  - rank=3 title=동의대학교 미래교육원 > 학점은행제 > 경영과 > 모집안내 source_type=lifelong content_type=clean score=3.247754 rerank=3.247754 lex=None vec=None final=None
    source_url=https://lifelong.deu.ac.kr/Contents/Contents.aspx?MENU_ID=140&PAGE_NO=35
    원문 일부: [TITLE] 동의대학교 미래교육원 > 학점은행제 > 경영과 > 모집안내  [BODY] 동의대학교 총장 명의 학위증  - 개인정보처리방침 - 사이트 이용약관 -  47340 부산광역시 부산진구 엄광로 176 동의대학교 지천관 2층 207호 미래교육원 TEL. 051)890-1947~8 FAX. 0502-600-9396 Copyright 2014 lifelong.deu.ac.kr All Rights Reserved.
- 정답 후보 문서 존재 여부:
  - hits=3 title=역대총장 | 총장 | DEU doc=static_7fe939fbbc6bdf3b chunk=static_7fe939fbbc6bdf3b_v001_chunk_001 source_type=institution content_type=clean
    source_url=https://www.deu.ac.kr/www/former-university-presidents.do
  - hits=2 title=2026년도 산학협동재단 장학금 지원사업 장학생 선발 공고 안내 [사회적배려대상자 및 외국인 근로자 자녀 학생 해당] doc=deu_scholarship_85702 chunk=deu_scholarship_85702_v001_chunk_010 source_type=scholarship content_type=None
    source_url=https://www.deu.ac.kr/www/deu-scholarship.do?article.offset=0&articleLimit=10&articleNo=85702&mode=view
  - hits=2 title=2026년도 산학협동재단 장학금 지원사업 장학생 선발 공고 안내 [사회적배려대상자 및 외국인 근로자 자녀 학생 해당] doc=deu_scholarship_85702 chunk=deu_scholarship_85702_v001_chunk_024 source_type=scholarship content_type=None
    source_url=https://www.deu.ac.kr/www/deu-scholarship.do?article.offset=0&articleLimit=10&articleNo=85702&mode=view
  - hits=2 title=2026년도 산학협동재단 장학금 지원사업 장학생 선발 공고 안내 [사회적배려대상자 및 외국인 근로자 자녀 학생 해당] doc=deu_scholarship_85702 chunk=deu_scholarship_85702_v001_chunk_023 source_type=scholarship content_type=None
    source_url=https://www.deu.ac.kr/www/deu-scholarship.do?article.offset=0&articleLimit=10&articleNo=85702&mode=view
  - hits=2 title=2026년도 산학협동재단 장학금 지원사업 장학생 선발 공고 안내 [사회적배려대상자 및 외국인 근로자 자녀 학생 해당] doc=deu_scholarship_85702 chunk=deu_scholarship_85702_v001_chunk_012 source_type=scholarship content_type=None
    source_url=https://www.deu.ac.kr/www/deu-scholarship.do?article.offset=0&articleLimit=10&articleNo=85702&mode=view

### [Case 15] query_id=479 / request_id=9c649b3e-3dde-4bff-beeb-b20b7f158ef6
- created_at: 2026-05-20T14:01:20.427191+09:00
- 질문: 23번 건물은 정보공학관?
- 답변: 23번 건물이 정보공학관이라고 합니다.  사이트 바로가기: https://www.deu.ac.kr/
- 문제 유형: C. 검색은 됐지만 selection/rerank 실패
- intent/category/filters/rewrite: INFO / None / {} / 정보공학관 23번 건물
- 원인 분석: retrieval_quality.top_strong_term_match=0으로 상위 선택 chunk의 핵심어 적합도가 낮음
- 수정 필요 지점: rerank scoring
- 검색된 문서:
  - lexical#1 ✨📚 동의대학교 자유전공(유형Ⅰ) 가이드북✨📚 doc=deu_advising_81177 chunk=deu_advising_81177_v001_chunk_063 lex=2.84999995231628 vec=None final=0.740259737042758
  - lexical#2 2025학년도 후기(2026년 8월 졸업) 학위청구논문심사 신청 안내 doc=deu_department_84194 chunk=deu_department_84194_v001_chunk_035 lex=2.59999995231628 vec=None final=0.722222218542923
  - lexical#3 2025학년도 후기(2026년 8월 졸업) 학위청구논문심사 신청 안내 doc=deu_department_84194 chunk=deu_department_84194_v001_chunk_036 lex=2.19999997615814 vec=None final=0.687499997671694
  - lexical#4 2026년 푸른등대 삼성기부장학금 신청 안내 (학부-AI핵심분야 진로 희망자, 대학원-인문사회계열 학과 전공자) doc=deu_scholarship_83658 chunk=deu_scholarship_83658_v001_chunk_023 lex=2.10000007152557 vec=None final=0.677419362281537
  - lexical#5 ✨📚 동의대학교 자유전공(유형Ⅰ) 가이드북✨📚 doc=deu_advising_81177 chunk=deu_advising_81177_v001_chunk_025 lex=1.45000004768372 vec=None final=0.591836742637853
  - vector#1 캠퍼스맵 | 캠퍼스안내 | DEU doc=static_19b132e7ab559d4e chunk=static_19b132e7ab559d4e_v001_chunk_011 lex=None vec=0.542037487030033 final=0.542037487030033
- 선택된 chunk:
  - rank=1 title=학과사무실 위치 및 연락처 | 학과소개 | 컴퓨터공학과 source_type=department content_type=clean score=5.440502 rerank=5.440502 lex=None vec=None final=None
    source_url=https://swcc.deu.ac.kr/computer/sub01_05.do
    원문 일부: [TITLE] 학과사무실 위치 및 연락처 | 학과소개 | 컴퓨터공학과  [BODY] ★ 컴퓨터공학과 강의실, 실습실, 교수 연구실 및 학생회실 위치  - 부산광역시 부산진구 엄광로 176, 동의대학교 정보공학관(교내 건물 번호 23번) 8층
  - rank=2 title=캠퍼스맵 | 캠퍼스안내 | DEU source_type=institution content_type=clean score=3.151354 rerank=3.151354 lex=None vec=0.542037487030033 final=0.542037487030033
    source_url=https://www.deu.ac.kr/www/deu-campus-map.do
    원문 일부: [TITLE] 캠퍼스맵 | 캠퍼스안내 | DEU  [BODY] body  동창회 사무실 3F 기계공학과, 산업경영빅데이터공학과, 화학공학과 강의지원실, 교수연구실, 강의실, 실습실, 산업융합시스템공학부(산업경영빅데이터공학전공), 화학공학과, 환경공학과 학회실, 산업기술개발연구소 4F 도시공학과, 환경공학과 강의지원실, 교수연구실, 강의실, 실습실, 전산실, 도시공학과 학회실 5F 신소재공학과, 고분자나노공학과 강의지원실, 교수연구실, 강의실, 실습실, 신소재공학과, 고분자나노공학과 학회실 6F 건축공학과 강의지원실, 교수연구실...
  - rank=3 title=멤브레인 공학 연구실 | 연구실 | 환경공학과 source_type=department content_type=clean score=3.098848 rerank=3.098848 lex=None vec=None final=None
    source_url=https://env.deu.ac.kr/env/sub04_04.do
    원문 일부: [TITLE] 멤브레인 공학 연구실 | 연구실 | 환경공학과  [BODY] 멤브레인 공학 연구실  환경공학전공은 수질, 대기, 폐기물과 같이 오염원의 특성에 따라 각각 다양한 공정이 적용됩니다. 충분한 실험 실습을 통하여 산업 현장에서 필요로 하는 전문 엔지니어로 양성하기 위하여 실험 시수가 많은 교과과정이 특징입니다. 실험 실습 공간으로 환경공학전공에서는 환경공학 공동실험실습실, 수처리 공학 실험실, 대기 오염 제어 공학 실험실, 폐기물 공학 실험실, 멤브레인 공학 실험실의 5개 실험실로 운영되고 있습니다. 환경공학 공동실험...
- 정답 후보 문서 존재 여부:
  - hits=4 title=학과사무실 위치 및 연락처 | 학과소개 | 컴퓨터공학과 doc=static_01840b5a30b433c1 chunk=static_01840b5a30b433c1_v001_chunk_001 source_type=department content_type=clean
    source_url=https://swcc.deu.ac.kr/computer/sub01_05.do
  - hits=3 title=2026년 중대산업재해 등 사고 발생 대비 매뉴얼 doc=deu_reference_83242 chunk=deu_reference_83242_v001_chunk_009 source_type=reference content_type=None
    source_url=https://www.deu.ac.kr/www/deu-reference.do?article.offset=0&articleLimit=10&articleNo=83242&mode=view
  - hits=3 title=2026학년도 편입생 대상 수강신청 및 학점관련 안내 doc=deu_academic_notice_81202 chunk=deu_academic_notice_81202_v001_chunk_007 source_type=academic_notice content_type=None
    source_url=https://www.deu.ac.kr/www/gra-notice.do?article.offset=10&articleLimit=10&articleNo=81202&mode=view
  - hits=3 title=✨📚 동의대학교 자유전공(유형Ⅰ) 가이드북✨📚 doc=deu_advising_81177 chunk=deu_advising_81177_v001_chunk_063 source_type=advising content_type=None
    source_url=https://advising.deu.ac.kr/advising/sub04_02.do?article.offset=0&articleLimit=10&articleNo=81177&mode=view
  - hits=3 title=2026학년도 신입생 수강신청 관련 안내(신입생 필독) doc=deu_notice_81190 chunk=deu_notice_81190_v001_chunk_011 source_type=notice content_type=None
    source_url=https://www.deu.ac.kr/www/deu-notice.do?article.offset=30&articleLimit=10&articleNo=81190&mode=view

## 파이프라인별 진단

### query preprocessing
- 현재 관찰된 문제: 숫자/짧은 질의에서 일반어가 많이 남아 위치/건물 질의가 넓은 문서군으로 확산됨
- 근거 로그: keywords, rewritten_queries, retrieval_quality.top_strong_term_match
- 재현 query id: 482, 477, 478, 475, 481
- 수정 방향: 숫자+건물, 건물명+층, 학과+이수표 같은 질의 패턴을 별도 엔티티로 보호
- 우선순위: P1
- 주의사항: 일반 공지 검색까지 과하게 좁아지지 않도록 패턴별로만 적용

### intent classification
- 현재 관찰된 문제: 최근 INFO 로그는 대부분 RAG로 진입하지만, DB 후보가 있는데 retrieval_log가 없을 가능성은 별도 감시 필요
- 근거 로그: query_logs.intent_type, retrieval_logs 존재 여부
- 재현 query id: 
- 수정 방향: INFO인데 retrieval_log가 없는 케이스를 경고 지표로 추가
- 우선순위: P2
- 주의사항: 욕설/일반대화 우회 경로와 혼동하지 말 것

### query rewriting
- 현재 관찰된 문제: protected term 누락 또는 형태 변형이 보임
- 근거 로그: metadata.query_understanding.rewrite_quality.missing_protected_terms
- 재현 query id: 482, 477, 483, 473, 472
- 수정 방향: protected_terms가 rewrite/query_variants 전체에 보존되도록 테스트 추가
- 우선순위: P1
- 주의사항: 동의대 같은 범용어는 보호 대상에서 제외

### keyword extraction
- 현재 관찰된 문제: 핵심어보다 범용어가 top keyword에 섞여 lexical branch가 넓어짐
- 근거 로그: retrieval_logs.keywords, retrieval_branch_candidates.lexical
- 재현 query id: 483, 474, 476
- 수정 방향: 질문별 강한 명사/숫자 토큰을 strong_terms로 분리하고 점수 로그에 남김
- 우선순위: P1
- 주의사항: 한국어 복합명사 분해와 원형 보존을 같이 유지

### filter/category extraction
- 현재 관찰된 문제: department filter에 `학과사무실` 같은 조직명이 들어가 검색 범위를 왜곡하는 사례가 있음
- 근거 로그: retrieval_logs.filters, metadata.query_understanding.extracted_entities.department
- 재현 query id: 
- 수정 방향: department/site/page_type 필터는 실제 corpus facet 값과 매칭될 때만 적용
- 우선순위: P1
- 주의사항: 필터 적용 전/후 후보 수를 로그로 남겨야 회귀를 잡을 수 있음

### lexical search
- 현재 관찰된 문제: DB에는 lexical probe 후보가 있는데 retrieval 후보와 겹치지 않는 케이스가 있음
- 근거 로그: db_evidence_probe vs retrieval_branch_candidates.lexical
- 재현 query id: 483, 474, 476
- 수정 방향: strong_terms 필수 포함 옵션과 title/section_title 가중치 재조정
- 우선순위: P1
- 주의사항: 부분일치만 강화하면 UI/메뉴 노이즈가 같이 올라올 수 있음

### vector search
- 현재 관찰된 문제: 짧은 시설/건물 질의에서 의미적으로 가까운 학과/공지 문서가 섞임
- 근거 로그: retrieval_branch_candidates.vector vector_score
- 재현 query id: 482, 481, 480, 476, 479
- 수정 방향: 시설/위치 질의는 lexical/title exact signal을 vector보다 우선
- 우선순위: P2
- 주의사항: 일반 의미 질의에서는 vector branch 비중을 유지

### hybrid merge
- 현재 관찰된 문제: lexical/vector 점수의 final_score가 rerank 이전 후보 적합성을 충분히 보장하지 못함
- 근거 로그: retrieval_branch_candidates final_score, rerank_comparison rank_before
- 재현 query id: 482, 477, 483, 473, 472
- 수정 방향: query family별 fusion weight와 branch별 minimum evidence gate 적용
- 우선순위: P2
- 주의사항: 가중치 조정 전후 20개 대표 질의 회귀셋 필요

### rerank
- 현재 관찰된 문제: 후보에는 있으나 selected에서 밀리는 C 유형이 확인됨
- 근거 로그: rerank_comparison selected/rank_after/rerank_score
- 재현 query id: 481, 480, 479
- 수정 방향: rerank_signals에 strong_term_match와 exact heading match 하한 조건 추가
- 우선순위: P1
- 주의사항: reranker가 긴 첨부문서의 반복어에 끌리지 않게 attachment_noise 유지

### TopK selection
- 현재 관찰된 문제: duplicate_doc_ratio가 높은 케이스에서 반복 chunk가 context를 잠식함
- 근거 로그: retrieval_quality.duplicate_doc_ratio, selected_chunks doc_id
- 재현 query id: 482, 477, 473, 472, 469
- 수정 방향: max_chunks_per_doc, near-duplicate content hash, source diversity를 selection gate로 적용
- 우선순위: P1
- 주의사항: 한 문서 내 표/본문이 모두 필요한 공지형 답변은 예외 필요

### context formatting
- 현재 관찰된 문제: selected chunk 원문에 제목/본문 경계와 출처가 섞여 있어 LLM이 근거를 구분하기 어려운 사례가 있음
- 근거 로그: retrieval_logs.context, selected_chunks.content_preview
- 재현 query id: 482, 477, 483, 473, 472
- 수정 방향: chunk별 title/source_url/content_type/score를 명시한 구조화 context로 정리
- 우선순위: P2
- 주의사항: 프롬프트 토큰을 늘리지 않도록 chunk 수와 preview 길이 제한

### answer generation
- 현재 관찰된 문제: 근거 후보가 선택됐는데 답변이 부정확하거나 근거 부족형으로 나오는 E 유형이 있음
- 근거 로그: selected_chunks vs response_logs.answer_text
- 재현 query id: 
- 수정 방향: 답변 전 evidence sufficiency/self-check와 인용 강제 규칙 추가
- 우선순위: P2
- 주의사항: 근거 없음일 때는 억지 답변을 막는 현재 안전장치 유지

### citation/source mapping
- 현재 관찰된 문제: selected chunk에는 source_url이 있으나 답변이 어떤 근거에서 왔는지 추적성이 약함
- 근거 로그: retrieval_selected_chunks.source_snapshot/documents.source_url
- 재현 query id: 482, 477, 483, 473, 472
- 수정 방향: answer에 사용된 chunk_id/source_url을 response metadata로 별도 저장
- 우선순위: P3
- 주의사항: 사용자 노출 citation과 내부 디버그 citation을 분리

## 수정 계획
- 1차: 로그에 남은 대표 25개 query_id를 회귀셋으로 고정하고 기대 source/chunk를 수동 라벨링
- 2차: filter/category extraction에서 corpus facet 검증과 protected term 보존 테스트 추가
- 3차: lexical strong_terms/title/section_title 가중치와 hybrid fusion weight를 회귀셋으로 튜닝
- 4차: rerank/TopK에 duplicate doc 제한, UI noise gate, strong_term 하한을 추가
- 5차: context formatting과 response metadata에 사용 chunk/source_url/citation trace를 저장
- 승인 전까지 제품 코드 수정은 하지 않음
