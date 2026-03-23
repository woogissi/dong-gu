@echo off
chcp 65001

echo ===============================
echo Donggu Crawling Pipeline START
echo ===============================

echo.
echo [1/4] Run Full Pipeline (공지 + 첨부)
python -m crawler.run.run_full_pipeline
IF %ERRORLEVEL% NEQ 0 (
    echo ERROR in run_full_pipeline
    pause
    exit /b
)

echo.
echo [2/4] Run Static Discovery (정적 페이지)
python -m crawler.run.run_static_discovery
IF %ERRORLEVEL% NEQ 0 (
    echo ERROR in run_static_discovery
    pause
    exit /b
)

echo.
echo [3/4] Run Ingestion (Chunk 생성)
python -m crawler.run.run_ingestion_pipeline
IF %ERRORLEVEL% NEQ 0 (
    echo ERROR in run_ingestion_pipeline
    pause
    exit /b
)

echo.
echo [4/4] Run Vector Ingestion (Embedding + DB)
python -m crawler.run.run_vector_ingestion
IF %ERRORLEVEL% NEQ 0 (
    echo ERROR in run_vector_ingestion
    pause
    exit /b
)

echo.
echo ===============================
echo ALL PIPELINE DONE SUCCESSFULLY
echo ===============================

pause