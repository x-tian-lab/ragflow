@echo off
REM lawrag 一键验证:索引重建 + 检索回归 + judge校准 + 完整评测
REM 双击运行,或在终端执行。输出同步写入 verify_run.log
chcp 65001 >nul
cd /d "%~dp0"

set "LAWRAG_ROOT=C:\Users\wxt20\Desktop\rag sys"
set "LAWRAG_META=C:\Users\wxt20\Documents\rag\metadata_output"
set "PYTHONIOENCODING=utf-8"

if not exist "%LAWRAG_ROOT%" (
    echo [错误] 语料目录不存在: %LAWRAG_ROOT%
    pause & exit /b 1
)

if "%LAWRAG_LLM_API_KEY%"=="" (
    set /p LAWRAG_LLM_API_KEY=请输入 DeepSeek API Key(仅本次会话使用,不落盘): 
)

echo ============================================== > verify_run.log
echo lawrag verify run %date% %time% >> verify_run.log

echo.
echo ===== [1/4] 重建索引(必须:新增行下标+标题加权,旧索引不兼容) =====
python -m lawrag.cli index --retriever bm25 2>&1 | powershell -NoProfile -Command "$input | Tee-Object -FilePath verify_run.log -Append"
if errorlevel 1 goto :err

echo.
echo ===== [2/4] 检索回归(免费,预期 file_hit 约0.94-0.95;M05/X03 的数据行应可被检索) =====
python -m lawrag.cli eval --mode retrieval 2>&1 | powershell -NoProfile -Command "$input | Tee-Object -FilePath verify_run.log -Append"

echo.
echo ===== [3/4] judge 校准门(约55次API调用,几毛钱;一致率大于等于95%%才可信) =====
python -m lawrag.cli calibrate 2>&1 | powershell -NoProfile -Command "$input | Tee-Object -FilePath verify_run.log -Append"

echo.
echo ===== [4/4] 完整评测(BM25+DeepSeek+LLM-judge;60题约3-5分钟) =====
python -m lawrag.cli eval --mode full --judge llm 2>&1 | powershell -NoProfile -Command "$input | Tee-Object -FilePath verify_run.log -Append"

echo.
echo ===== 完成。结果已写入 verify_run.log,请把该文件发回分析 =====
pause
exit /b 0

:err
echo [中止] 索引构建失败,后续步骤未执行,请把报错发回
pause
exit /b 1
