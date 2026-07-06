@echo off
REM 一键推送 ragflow_repo 到 https://github.com/x-tian-lab/ragflow
REM 在本目录双击运行,或在终端执行。需要本机已安装 git 并已登录 GitHub(git credential manager)。
chcp 65001 >nul
cd /d "%~dp0"

if exist .git goto commit
git init -b main
git remote add origin https://github.com/x-tian-lab/ragflow.git
git fetch origin
git merge origin/main --allow-unrelated-histories -m "merge remote LICENSE/README stub"

:commit
git rm -r --cached lawrag/__pycache__ 2>nul
git add -A
git commit -m "lawrag MVP: citation-first legal RAG — five-stage pipeline, law-structure parsing, 3-tier citations, version control, frozen testset (spec v0.2, D-01~D-26); BM25 baseline file_hit@5=90.9%%"
git push -u origin main
echo.
echo 完成。查看 https://github.com/x-tian-lab/ragflow
pause
