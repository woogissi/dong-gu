-- Domain coverage report for RAG corpus health checks.
-- Run:
--   docker compose exec postgres psql -U chatbot -d chatbot -f /app/crawler/sql/domain_coverage_report.sql

WITH domains(domain, source_types, terms) AS (
    VALUES
        ('club_activity', ARRAY['club_activity','student_life'], ARRAY['동아리','중앙동아리','학생활동']),
        ('dormitory', ARRAY['dormitory'], ARRAY['기숙사','생활관','효민생활관','입사신청']),
        ('cafeteria', ARRAY['cafeteria','welfare','facility'], ARRAY['학생식당','교내식당','식당','운영시간','정보공학관']),
        ('shuttle', ARRAY['shuttle','campus','student_life'], ARRAY['셔틀','통학버스','시외통학버스','버스']),
        ('library', ARRAY['library'], ARRAY['도서관','중앙도서관','운영시간']),
        ('tuition', ARRAY['tuition','admission','academic_notice','academic_support','notice'], ARRAY['등록금','납부','고지서','분할납부'])
),
matched_documents AS (
    SELECT
        d.domain,
        doc.doc_id,
        doc.source_type,
        doc.page_kind,
        doc.title,
        doc.source_url
    FROM domains d
    JOIN documents doc
      ON doc.source_type = ANY(d.source_types)
      OR doc.title ILIKE ANY(SELECT '%' || unnest(d.terms) || '%')
      OR COALESCE(doc.metadata::text, '') ILIKE ANY(SELECT '%' || unnest(d.terms) || '%')
      OR EXISTS (
          SELECT 1
          FROM chunks c
          WHERE c.doc_id = doc.doc_id
            AND (
                c.section_title ILIKE ANY(SELECT '%' || unnest(d.terms) || '%')
                OR c.content ILIKE ANY(SELECT '%' || unnest(d.terms) || '%')
            )
      )
)
SELECT
    md.domain,
    COUNT(DISTINCT md.doc_id) AS documents,
    COUNT(DISTINCT c.chunk_id) AS chunks,
    COUNT(DISTINCT e.chunk_id) AS embeddings,
    STRING_AGG(DISTINCT md.source_type, ', ' ORDER BY md.source_type) AS source_types,
    STRING_AGG(DISTINCT md.page_kind, ', ' ORDER BY md.page_kind) AS page_kinds
FROM matched_documents md
LEFT JOIN chunks c ON c.doc_id = md.doc_id
LEFT JOIN chunk_embeddings e ON e.chunk_id = c.chunk_id
GROUP BY md.domain
ORDER BY md.domain;

SELECT
    source_type,
    page_kind,
    COUNT(*) AS documents
FROM documents
WHERE source_type IN (
    'club_activity',
    'student_life',
    'dormitory',
    'cafeteria',
    'welfare',
    'facility',
    'shuttle',
    'campus',
    'library',
    'tuition',
    'admission',
    'academic_notice',
    'academic_support'
)
GROUP BY source_type, page_kind
ORDER BY source_type, page_kind;
