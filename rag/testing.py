import csv
import os
import sys
import json
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from rag.pipeline.chat_pipeline import ChatPipeline
from rag.pipeline.state import PipelineState
from rag.schemas.query import Query

BASE_DIR = os.path.dirname(__file__)

# CSV 출력에 포함할 필드 목록입니다. 필요 없는 필드는 주석 처리하세요.
# PipelineState(state.py)의 필드는 기본으로 모두 나열되어 있습니다.
CSV_FIELD_NAMES = [
    "index",
    "query",
    #"answer",
    #"source_count",
    #"source_titles",
    "source_categories",
    #"first_source_title",
    #"first_source_category",
    #"original_query",
    "normalized_query",
    #"rewritten_query",
    "rewritten_queries",
    "keywords",
    "entities",
    "filters",
    #"category",
    #"retrieval_strategy",
    #"retrieval_top_k",
    "retrieval_strategy_log",
    #"fallback_used",
    #"retrieved_docs",
    #"retrieved_doc_count",
    #"reranked_docs",
    #"reranked_doc_count",
    #"selected_docs",
    #"selected_doc_count",
    #"context",
    #"prompt",
    #"answer_text",
    "success",
    # "error",
    "metadata",
]

# CSV에 저장할 때 너무 긴 답변은 잘라서 저장합니다.
MAX_ANSWER_LENGTH = 120


def _state_to_csv_dict(state: PipelineState | None) -> dict[str, Any]:
    if state is None:
        return {}

    data = state.to_log_dict()
    data.update(
        {
            "retrieved_docs": [_doc_to_dict(doc) for doc in state.retrieved_docs],
            "reranked_docs": [_doc_to_dict(doc) for doc in state.reranked_docs],
            "selected_docs": [_doc_to_dict(doc) for doc in state.selected_docs],
        }
    )
    return data


def _doc_to_dict(doc: Any) -> Any:
    if hasattr(doc, "model_dump"):
        return doc.model_dump(mode="json")
    return doc


# JSON 문자열로 쿼리를 받아 처리하고 결과를 리스트로 반환
def _run_batch_queries(queries_json: str) -> list[dict[str, Any]]:
    queries = json.loads(queries_json)

    if not isinstance(queries, list):
        raise ValueError("입력 JSON은 리스트 형식이어야 합니다.")

    pipeline = ChatPipeline()
    results = []

    for idx, query_text in enumerate(queries):
        if not isinstance(query_text, str):
            results.append({
                "index": idx,
                "query": query_text,
                "error": "문자열이 아닌 항목입니다."
            })
            continue

        try:
            query = Query(text=query_text)
            result = pipeline.run(query)

            results.append({
                "index": idx,
                "query": query_text,
                "result": result.model_dump(mode="json"),
                "state": _state_to_csv_dict(pipeline.last_state),
            })

        except Exception as e:
            results.append({
                "index": idx,
                "query": query_text,
                "error": f"쿼리 처리 실패: {str(e)}",
                "state": _state_to_csv_dict(pipeline.last_state),
            })

    return results


def test_pipeline_batch(queries_json: str) -> str:
    """
    JSON 문자열로 전달된 쿼리 리스트를 받아 ChatPipeline을 반복 실행하고,
    각 쿼리에 대한 결과를 JSON 형식으로 반환합니다.

    Args:
        queries_json (str): 쿼리 리스트가 담긴 JSON 문자열
                            예: ["질문1", "질문2"]

    Returns:
        str: 결과 JSON 문자열
    """
    try:
        results = _run_batch_queries(queries_json)
        return json.dumps(results, ensure_ascii=False, indent=2)

    except json.JSONDecodeError as e:
        return json.dumps({
            "error": f"JSON 파싱 오류: {str(e)}"
        }, ensure_ascii=False, indent=2)

    except Exception as e:
        return json.dumps({
            "error": f"처리 중 오류 발생: {str(e)}"
        }, ensure_ascii=False, indent=2)


def _summarize_result_for_csv(item: dict[str, Any]) -> dict[str, Any]:
    row_data: dict[str, Any] = {
        "index": item.get("index"),
        "query": item.get("query", ""),
        "success": "",
        "answer": "",
        "source_count": 0,
        "source_titles": "",
        "source_categories": "",
        "first_source_title": "",
        "first_source_category": "",
        "error": item.get("error", ""),
    }
    state = item.get("state")
    if isinstance(state, dict):
        row_data.update(state)
        row_data["error"] = item.get("error") or state.get("error", "")

    result = item.get("result")
    if not isinstance(result, dict):
        return _select_csv_fields(row_data)

    answer = result.get("answer", "")
    if isinstance(answer, str) and len(answer) > MAX_ANSWER_LENGTH:
        answer = answer[:MAX_ANSWER_LENGTH] + "..."

    row_data["success"] = result.get("success", "")
    row_data["answer"] = answer

    sources = result.get("sources", [])
    if isinstance(sources, list):
        row_data["source_count"] = len(sources)
    if isinstance(sources, list) and sources and isinstance(sources[0], dict):
        first_source = sources[0]
        row_data["first_source_title"] = first_source.get("title", "")
        row_data["source_titles"] = _dedupe_source_values(sources, "title")
        row_data["source_categories"] = _dedupe_source_values(sources, "category")
        row_data["first_source_category"] = row_data["source_categories"]

    return _select_csv_fields(row_data)


def _select_csv_fields(row_data: dict[str, Any]) -> dict[str, Any]:
    return {field: _csv_value(row_data.get(field, "")) for field in CSV_FIELD_NAMES}


def _csv_value(value: Any) -> Any:
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False)
    return value


def _dedupe_source_values(sources: list[Any], field: str) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for source in sources:
        if not isinstance(source, dict):
            continue
        value = source.get(field)
        if not value or value in seen:
            continue
        seen.add(value)
        values.append(value)
    return values


def batch_results_to_csv(results: list[dict[str, Any]]) -> str:
    csv_rows = [_summarize_result_for_csv(item) for item in results]
    csv_path = os.path.join(BASE_DIR, "batch_test_results.csv")

    with open(csv_path, "w", encoding="utf-8", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=CSV_FIELD_NAMES)
        writer.writeheader()
        writer.writerows(csv_rows)

    return json.dumps(csv_rows, ensure_ascii=False, indent=2)


def test_pipeline_batch_csv(queries_json: str) -> str:
    """
    쿼리 리스트를 실행한 결과를 CSV 요약 형식으로 반환합니다.

    CSV 필드는 `CSV_FIELD_NAMES`에서 선택할 수 있습니다.
    """
    results = _run_batch_queries(queries_json)
    return batch_results_to_csv(results)


if __name__ == "__main__":
    json_input_path = os.path.join(BASE_DIR, "test_queries.json")
    json_output_path = os.path.join(BASE_DIR, "batch_test_results.json")

    with open(json_input_path, "r", encoding="utf-8") as f:
        queries = json.load(f)

    queries_json = json.dumps(queries, ensure_ascii=False)
    results = _run_batch_queries(queries_json)

    with open(json_output_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(results, ensure_ascii=False, indent=2))

    csv_output_path = os.path.join(BASE_DIR, "batch_test_results.csv")
    batch_results_to_csv(results)
    print(
        f"배치 테스트 완료: {len(queries)}개 쿼리 처리 결과가 '{json_output_path}'와 '{csv_output_path}'에 저장되었습니다."
    )
