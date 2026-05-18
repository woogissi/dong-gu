# AutoRAG 오프라인 평가

이 디렉토리는 동구대학교 RAG 챗봇을 위한 오프라인 AutoRAG 실험 환경입니다.
운영 중인 FastAPI, Kakao, `rag.pipeline` 런타임과는 의도적으로 분리되어 있습니다.

목표는 주관적인 답변 확인 방식에서 벗어나, 다음과 같은 측정 가능한 Retrieval 평가를 수행하는 것입니다.

* 기대한 문서 또는 청크가 top-3 안에 포함되었는가?
* 대학 도메인 질의에서 어떤 전략이 더 좋은 성능을 보이는가?
* reranking 또는 최신성(recency) 필터가 성능 향상에 도움이 되는가?

## 디렉토리 구조

```text
rag/evaluation/autorag/
├── configs/
│   ├── baseline.yaml
│   ├── lexical_only.yaml
│   ├── retrieval_compare.yaml
│   └── reranker_compare.yaml
├── data/
│   ├── corpus.parquet        # 생성 파일, git ignore 대상
│   └── qa.parquet            # 생성 파일, git ignore 대상
├── scripts/
│   ├── export_corpus_to_autorag.py
│   ├── convert_test_queries_to_qa.py
│   └── run_autorag_experiment.py
└── results/                  # 생성된 AutoRAG 실행 결과, git ignore 대상
```

## 사전 준비

실험은 로컬 호스트가 아닌 Docker Compose 서비스 내부에서 실행해야 합니다.

실험 전 오프라인 평가 전용 이미지를 1회 빌드합니다.

```bash
docker compose --profile eval build autorag-eval
```

실험용 이미지에는 `rag/evaluation/autorag/requirements.txt` 기반 패키지가 설치됩니다.

포함 패키지:

* `AutoRAG[ko]`
* `pandas`
* `pyarrow`

`ko_reranker` 같은 한국어 AutoRAG 모듈을 사용할 경우, 컨테이너 내부에 KoNLPy 실행에 필요한 Java 환경이 준비되어 있어야 합니다.

## 1. Corpus Export

현재 PostgreSQL의 `documents` 및 최신 `chunks` 데이터를 AutoRAG 호환 parquet 형식으로 export 합니다.

```bash
docker compose --profile eval run --rm autorag-eval python -m rag.evaluation.autorag.scripts.export_corpus_to_autorag
```

DB 연결 확인:

```bash
docker compose --profile eval run --rm autorag-eval python -m rag.evaluation.autorag.scripts.export_corpus_to_autorag --check-connection
```

DB 연결 우선순위:

```text
DATABASE_URL -> CRAWLER_DATABASE_URL -> POSTGRES_HOST/POSTGRES_DB/POSTGRES_USER/POSTGRES_PASSWORD
```

`rag` 서비스는 `.env`를 먼저 로드하므로 로컬 Compose PostgreSQL 설정보다 Supabase `DATABASE_URL`이 우선 사용됩니다.

단, AutoRAG 평가 자체는 Supabase에 직접 연결하지 않으며 생성된 `corpus.parquet` 및 `qa.parquet` 파일만 사용합니다.

출력 파일:

```text
rag/evaluation/autorag/data/corpus.parquet
```

포함되는 필드:

* `doc_id`
* `chunk_id`
* `contents`
* `metadata`
* `source_type`
* `category`
* `title`
* `source_url`
* `published_at`
* `updated_at`
* `last_modified_datetime`

AutoRAG validation에서는 `corpus.parquet.doc_id`를 chunk 단위 ID로 설정합니다.

원본 문서 ID는 `original_doc_id` 및 `metadata.original_doc_id`에 유지됩니다.

이를 통해 `retrieval_gt` 라벨이 `deu_academic_84441_v002_chunk_011` 같은 chunk ID와 정확히 일치하도록 유지합니다.

## 2. QA 데이터셋 생성

기존 integration 질문 데이터를 `qa.parquet` 형식으로 변환합니다.

```bash
docker compose --profile eval run --rm autorag-eval python -m rag.evaluation.autorag.scripts.convert_test_queries_to_qa
```

출력 파일:

```text
rag/evaluation/autorag/data/qa.parquet
rag/evaluation/autorag/data/qa_ground_truth_template.csv
```

중요:

기존 `rag/tests/integration/test_queries.json` 파일에는 ground-truth 문서 ID가 포함되어 있지 않습니다.

AutoRAG validate는 모든 QA row의 `retrieval_gt`에 최소 1개 이상의 `chunk_id` 또는 `doc_id`가 있기를 기대합니다.

따라서 기본 변환은 라벨이 없는 질문을 `qa.parquet`에서 제외하고, 수동 라벨링용 `qa_ground_truth_template.csv`에는 계속 남깁니다.

라벨이 없는 row까지 포함한 초안이 필요할 때만 `--include-unlabeled` 옵션을 사용합니다.

이 옵션으로 생성된 `qa.parquet`는 AutoRAG validate에 사용할 수 없습니다.

라벨을 제공하려면 다음과 같은 JSON 파일을 생성합니다.

```json
{
  "수강신청 기간이 언제야?": {
    "answers": ["학사 공지 또는 학사 일정의 수강신청 기간 안내"],
    "retrieval_gt": ["expected_chunk_id_or_doc_id"]
  }
}
```

이후 다음 명령으로 실행합니다.

```bash
docker compose --profile eval run --rm autorag-eval python -m rag.evaluation.autorag.scripts.convert_test_queries_to_qa --ground-truth rag/evaluation/autorag/data/ground_truth.json
```

현재 seed label 기준 예상 출력:

```text
Wrote 19 QA rows to rag/evaluation/autorag/data/qa.parquet
Labeled rows with retrieval_gt: 19/53
Skipped unlabeled rows in qa.parquet: 34
```

기본 seed 파일은 다음 경로에 포함되어 있습니다.

```text
rag/evaluation/autorag/data/ground_truth.json
```

이 파일은 현재 Supabase/PostgreSQL의 `documents`, `chunks` 테이블과 동의대학교 공식 웹페이지 기반으로 생성되었습니다.

`needs_review: true`가 표시된 항목은 초기 라벨링용으로 유용하지만, gold label로 사용하기 전 검토가 필요합니다.

## 3. AutoRAG 실행

외부 embedding API 호출 없이 parquet 형식과 ground-truth 라벨을 먼저 검증합니다.

```bash
docker compose --profile eval run --rm autorag-eval python -m rag.evaluation.autorag.scripts.run_autorag_experiment --config rag/evaluation/autorag/configs/lexical_only.yaml --validate
```

`lexical_only.yaml`은 BM25만 사용하므로 OpenAI 등 외부 embedding API를 호출하지 않습니다.

VectorDB 및 hybrid retrieval까지 포함한 baseline 설정 파일 검증:

```bash
docker compose --profile eval run --rm autorag-eval python -m rag.evaluation.autorag.scripts.run_autorag_experiment --config rag/evaluation/autorag/configs/baseline.yaml --validate
```

주의:

`baseline.yaml`, `retrieval_compare.yaml`의 `semantic_retrieval` 및 `hybrid_retrieval`은 AutoRAG 자체 VectorDB embedding 설정을 사용합니다.

KoE5 로컬 embedding 또는 운영 pgvector 경로를 별도로 연결하지 않으면 AutoRAG 기본 embedding API를 호출할 수 있습니다.

실험 실행:

```bash
docker compose --profile eval run --rm autorag-eval python -m rag.evaluation.autorag.scripts.run_autorag_experiment --config rag/evaluation/autorag/configs/retrieval_compare.yaml
```

reranker/filter 비교 실험:

```bash
docker compose --profile eval run --rm autorag-eval python -m rag.evaluation.autorag.scripts.run_autorag_experiment --config rag/evaluation/autorag/configs/reranker_compare.yaml
```

## 예상 결과

AutoRAG는 각 실행 결과를 다음 경로에 저장합니다.

```text
rag/evaluation/autorag/results/<timestamp>-<config-name>/
```

주요 확인 파일:

* `summary.csv`
* trial 폴더
* 노드별 결과 파일
* `autorag extract_best_config` 실행 시 추출된 최적 config

초기 핵심 지표:

* `retrieval_recall`
* `retrieval_precision`
* `retrieval_ndcg`
* `retrieval_mrr`
* export 결과 기준 top-k hit rate

## 제한 사항

* `qa.parquet`는 `retrieval_gt`에 실제 `chunk_id` 또는 `doc_id`가 채워진 이후에만 의미 있는 평가가 가능합니다.
* AutoRAG의 vector retrieval 기본 설정은 운영 환경의 KoE5 + pgvector 경로가 아닌 AutoRAG 자체 vector DB 및 embedding 모델을 사용할 수 있습니다.
* 외부 embedding API 호출을 피하려면 먼저 `lexical_only.yaml`로 validate하고, vector/hybrid 실험은 KoE5 embedding 경로를 별도로 연결한 뒤 실행하세요.
* YAML 파일은 실험용 템플릿입니다. 팀에서 사용하는 정확한 AutoRAG 버전에 맞춰 validate가 필요합니다.
* 해당 스크립트들은 `retrieval_policy.yaml`, FastAPI 라우트, Kakao 응답, 운영 pipeline에는 영향을 주지 않습니다.

## 추천 초기 라벨링 질문

도메인별로 우선 5~10개 질문부터 라벨링하는 것을 권장합니다.

* 수강신청
* 수강정정
* 장학금
* 기숙사
* 도서관 운영시간
* 통학버스
* 졸업요건
* 학사일정

각 질문마다 `corpus.parquet`에서 하나 이상의 예상 `chunk_id`를 라벨링합니다.