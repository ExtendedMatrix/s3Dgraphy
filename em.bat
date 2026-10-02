@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

:: ============================================================================
:: s3Dgraphy - Quick Commands (Windows)
::
:: The same commands as em.sh. Native here: setup, test, check, fingerprint,
:: drift, docs, status, propagate. Through bash (Git for Windows): bump,
:: publish, wheel, release — because what they call is bash already:
::   bump     -> bump_and_push.sh --set  (bump_and_push.bat has no --set:
::               measured 2026-10-01, it takes patch|minor|major only, and
::               those drop .devN)
::   publish  -> scripts/verifica-provenance.sh
::   wheel    -> tar + a throwaway venv, written once in em.sh
:: The long help of each command is read from em.sh, so the two cannot drift.
:: Nothing here commits; bump and publish ask before touching the remote.
:: ============================================================================

cd /d "%~dp0"
set "ROOT=%~dp0"
set "PARENT=%ROOT%.."
set "PY=%ROOT%.venv\Scripts\python.exe"
set "PYTHONPATH=%ROOT%src;%PYTHONPATH%"
set "EXTRAS=dev,docs,rdf,sync,geo,pdf,docx"

set "CMD=%~1"
if "%CMD%"=="" goto :help
if "%CMD%"=="help" goto :help
if "%CMD%"=="-h" goto :help
if "%CMD%"=="--help" goto :help
if "%CMD%"=="setup" goto :setup
if "%CMD%"=="test" goto :test
if "%CMD%"=="check" goto :check
if "%CMD%"=="fingerprint" goto :fingerprint
if "%CMD%"=="drift" goto :drift
if "%CMD%"=="docs" goto :docs
if "%CMD%"=="status" goto :status
if "%CMD%"=="propagate" goto :propagate
if "%CMD%"=="metashape" goto :metashape
if "%CMD%"=="bump" goto :via_bash
if "%CMD%"=="publish" goto :via_bash
if "%CMD%"=="wheel" goto :via_bash
if "%CMD%"=="release" goto :via_bash
echo unknown command '%CMD%'
echo.
goto :overview

:: ----------------------------------------------------------------------------
:help
if "%~2"=="" goto :overview
where bash >nul 2>&1
if errorlevel 1 (
    echo The long help of '%~2' is in em.sh ^(function help_%~2^): open it, or
    echo install Git for Windows and run: bash em.sh help %~2
    exit /b 0
)
bash "%ROOT%em.sh" help %~2
exit /b %errorlevel%

:overview
echo s3Dgraphy - em.bat ^<command^> [args]
echo.
echo Every command calls what the repository already has (pytest, the
echo s3dgraphy.tools --check modes, sphinx, bump_and_push.sh, publish.yml,
echo verifica-provenance.sh). Commands that touch the REMOTE or OTHER
echo REPOSITORIES ask for confirmation and take --dry-run.
echo.
echo   setup                 Create or repair .venv: pip install -e .[%EXTRAS%].
echo                           em.bat setup
echo   test [pytest args]    pytest on this source; names any failure not in the known list.
echo                           em.bat test
echo   check                 Every --check: i18n, glyphs, node registry, JSON, em.ttl, consumer_drift.
echo                           em.bat check
echo   fingerprint [--json]  The datamodel fingerprint: one digest, and per file with versions.
echo                           em.bat fingerprint
echo   drift                 Which consumer next door is behind (consumer_drift, wheel_drift, StratiField).
echo                           em.bat drift
echo   docs [--strict]       Build the documentation, count the warnings (--strict = -W).
echo                           em.bat docs
echo   wheel                 (bash) Build the wheel from this tree; prove the fingerprint from the install.
echo                           em.bat wheel
echo   bump ^<version^> [--dry-run] [--yes]
echo                         (bash) bump_and_push.sh --set ^<version^>: commit, tag, PUSH. Asks first.
echo                           em.bat bump 1.6.0.dev26 --dry-run
echo   publish ^<version^> [--dry-run] [--yes] [--testpypi]
echo                         (bash) publish.yml for tag v^<version^>, wait for PyPI, check provenance.
echo                           em.bat publish 1.6.0.dev26 --dry-run
echo   propagate [--dry-run] [--yes]
echo                         After a publication: templates after-bump -^> StratiField -^> EMStudio
echo                         -^> (EMtools: printed only), with the em.bat of each where it exists.
echo                           em.bat propagate --dry-run
echo   status                Branch, distance from origin, version here and on PyPI, fingerprint.
echo                           em.bat status
echo   release ^<V^> [--dtcstamp X] [--desktop] [--dry-run] [--yes]
echo                         (bash) the whole round, resumable; release status = where it stands.
echo                           em.bat release 1.6.0.dev28 --dtcstamp 0.1.3 --dry-run
echo   metashape ^<progetto.psx^> [--chunk N] [--out file.em.json]
echo                         Read a Metashape project without Metashape; --out writes its DTC chain.
echo                           em.bat metashape progetto.psx --out progetto.em.json
echo   help [command]        This list, or the long help of one command (read from em.sh).
echo                           em.bat help bump      (the five version paths are there)
echo.
echo --dry-run, everywhere it exists: shows, step by step, the commands that would be
echo run and the files that would change, and runs nothing.
exit /b 0

:: ----------------------------------------------------------------------------
:need_venv
if not exist "%PY%" (
    echo [ERROR] no .venv here. Run: em.bat setup
    exit /b 1
)
"%PY%" -c "import pytest, pandas, lxml" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] the .venv lacks the test dependencies. Run: em.bat setup
    exit /b 1
)
exit /b 0

:: ----------------------------------------------------------------------------
:setup
if "%~2"=="--recreate" if exist ".venv" (
    echo Removing .venv ^(--recreate^)
    rmdir /s /q ".venv"
)
if exist "%PY%" (
    echo Keeping .venv
) else (
    set "BASEPY=%PYTHON%"
    if "!BASEPY!"=="" set "BASEPY=py -3"
    echo Creating .venv with !BASEPY!
    !BASEPY! -m venv .venv
    if errorlevel 1 ( echo [ERROR] venv creation failed & exit /b 1 )
)
"%PY%" -m pip install --quiet --upgrade pip
echo pip install "setuptools>=61" wheel   ^(pyproject [build-system]^)
"%PY%" -m pip install --quiet "setuptools>=61" wheel
echo pip install -e .[%EXTRAS%]
"%PY%" -m pip install --quiet -e ".[%EXTRAS%]"
if errorlevel 1 ( echo [ERROR] pip install failed - read the errors above & exit /b 1 )
if exist "%PARENT%\dtcstamp\pyproject.toml" (
    echo pip install -e ..\dtcstamp ^(the stamp tests need the source's stamp_description^)
    "%PY%" -m pip install --quiet -e "%PARENT%\dtcstamp"
)
echo .venv ready
exit /b 0

:: ----------------------------------------------------------------------------
:test
call :need_venv || exit /b 1
set "OUT=%ROOT%.venv\last-pytest.txt"
set "ARGS=%*"
set "ARGS=!ARGS:~5!"
if "!ARGS!"=="" set "ARGS=tests"
"%PY%" -m pytest !ARGS! -p no:cacheprovider > "%OUT%" 2>&1
powershell -NoProfile -Command "Get-Content -Tail 3 '%OUT%'"
echo.
"%PY%" scripts\em_report.py failures "%OUT%"
if errorlevel 1 (
    echo [ERROR] new failure^(s^) above - not in scripts\known-test-failures.txt
    exit /b 1
)
echo no new failure
exit /b 0

:: ----------------------------------------------------------------------------
:check
call :need_venv || exit /b 1
set "RED=0"
echo i18n ^(datamodel_i18n --check^)
"%PY%" -m s3dgraphy.tools.datamodel_i18n --check || ( set /a RED+=1 & echo [RED] i18n )
echo glyphs ^(glyphs_from_svg --check^)
"%PY%" -m s3dgraphy.tools.glyphs_from_svg --check || ( set /a RED+=1 & echo [RED] glyphs )
echo node registry ^(sync_node_datamodel --check^)
"%PY%" -m s3dgraphy.tools.sync_node_datamodel --check || ( set /a RED+=1 & echo [RED] node registry )
echo JSON
"%PY%" scripts\em_report.py json-valid || ( set /a RED+=1 & echo [RED] JSON )
echo em.ttl
"%PY%" -m pytest -q -p no:cacheprovider tests\test_em_ttl_matches_the_datamodels.py || ( set /a RED+=1 & echo [RED] em.ttl )
echo consumer_drift --check
"%PY%" -m s3dgraphy.tools.consumer_drift --check --root "%PARENT%" || ( set /a RED+=1 & echo [RED] consumer_drift )
echo.
if "!RED!"=="0" ( echo check: all 6 green & exit /b 0 )
echo check: !RED! of 6 red
exit /b 1

:: ----------------------------------------------------------------------------
:metashape
shift
"%PY%" -m s3dgraphy.importer.metashape_project %1 %2 %3 %4 %5 %6 %7 %8 %9
exit /b %errorlevel%

:fingerprint
call :need_venv || exit /b 1
"%PY%" scripts\em_report.py fingerprint %2
exit /b %errorlevel%

:drift
call :need_venv || exit /b 1
echo consumer_drift
"%PY%" -m s3dgraphy.tools.consumer_drift --root "%PARENT%"
echo.
echo wheel_drift
"%PY%" -m s3dgraphy.tools.wheel_drift --root "%PARENT%"
if exist "%PARENT%\stratigraph-chatbot\schede\index.json" (
    echo.
    echo StratiField's vendored schede vs this datamodel
    "%PY%" scripts\em_report.py stratifield "%PARENT%\stratigraph-chatbot"
)
echo.
echo The commands that sync each consumer are printed by the tools above;
echo em.bat propagate runs them in order.
exit /b 0

:: ----------------------------------------------------------------------------
:docs
call :need_venv || exit /b 1
set "STRICT="
if "%~2"=="--strict" set "STRICT=-W"
if not exist "docs\_build" mkdir "docs\_build"
echo sphinx-build %STRICT% -b html docs docs\_build\html
"%PY%" -m sphinx %STRICT% -b html docs docs\_build\html > docs\_build\sphinx.log 2>&1
set "RC=%errorlevel%"
for /f %%n in ('findstr /c:"WARNING" docs\_build\sphinx.log ^| find /c /v ""') do set "NW=%%n"
findstr /c:"WARNING" docs\_build\sphinx.log
git status --short -- docs/generated-report.md
if not "%RC%"=="0" ( echo [ERROR] sphinx-build failed - !NW! warning^(s^), see docs\_build\sphinx.log & exit /b 1 )
echo docs built: docs\_build\html\index.html - !NW! warning^(s^) ^(log: docs\_build\sphinx.log^)
exit /b 0

:: ----------------------------------------------------------------------------
:status
call :need_venv || exit /b 1
for /f "delims=" %%b in ('git branch --show-current') do set "BR=%%b"
echo branch    !BR!
git status -sb | findstr /b "##"
for /f "tokens=3 delims= " %%v in ('findstr /b /c:"version = " pyproject.toml') do set "V=%%~v"
echo version   !V!
git rev-parse -q --verify "refs/tags/v!V!" >nul 2>&1 && echo   tag v!V! here: yes || echo   tag v!V! here: no
git ls-remote --exit-code --tags origin "refs/tags/v!V!" >nul 2>&1 && echo   tag v!V! on origin: yes || echo   tag v!V! on origin: no
<nul set /p "=PyPI      latest "
"%PY%" scripts\em_report.py pypi
"%PY%" scripts\em_report.py pypi !V!
<nul set /p "=datamodel "
"%PY%" -c "from s3dgraphy.datamodel import datamodel_fingerprint as f; print(f()['digest'])"
exit /b 0

:: ----------------------------------------------------------------------------
:propagate
call :need_venv || exit /b 1
set "DRY=0"
set "YES=0"
for %%a in (%*) do (
    if "%%~a"=="--dry-run" set "DRY=1"
    if "%%~a"=="-n" set "DRY=1"
    if "%%~a"=="--yes" set "YES=1"
    if "%%~a"=="-y" set "YES=1"
)
for /f "tokens=3 delims= " %%v in ('findstr /b /c:"version = " pyproject.toml') do set "V=%%~v"
echo propagate s3dgraphy !V! to the repositories in %PARENT%
"%PY%" scripts\em_report.py pypi !V!
if "!DRY!"=="0" if "!YES!"=="0" (
    set /p "OK=Run the sync in the repositories next door (no commit, no push)? [y/N] "
    if /i not "!OK!"=="y" ( echo stopped: nothing was done & exit /b 1 )
)
set "T_FAILED=0"
echo.
echo 1/4 stratigraph-templates: em.bat after-bump
if not exist "%PARENT%\stratigraph-templates" (
    echo     not here - skipped
) else if not exist "%PARENT%\stratigraph-templates\em.bat" (
    echo     no em.bat there - run its CLI by hand ^(DATAMODEL_PROPAGATION step 11^)
) else if "!DRY!"=="1" (
    echo     would run ^(in stratigraph-templates^): em.bat after-bump
) else (
    pushd "%PARENT%\stratigraph-templates"
    call em.bat after-bump
    if errorlevel 1 set "T_FAILED=1"
    git status --short
    popd
)
echo.
echo 2/4 stratigraph-chatbot ^(StratiField^): sync-schede
if not exist "%PARENT%\stratigraph-chatbot" (
    echo     not here - skipped
) else if "!T_FAILED!"=="1" (
    echo     SKIPPED - templates' build failed, there is nothing new to vendor
) else if exist "%PARENT%\stratigraph-chatbot\em.bat" (
    if "!DRY!"=="1" ( echo     would run: em.bat sync-schede ) else (
        pushd "%PARENT%\stratigraph-chatbot" & call em.bat sync-schede & git status --short & popd )
) else (
    echo     NO em.bat in stratigraph-chatbot ^(measured 2026-10-01: it has em.sh and
    echo     sync-schede.sh, both bash^). In Git Bash: cd ../stratigraph-chatbot ^&^& ./em.sh sync-schede
)
echo.
echo 3/4 EMStudio: sync + check:datamodel
if not exist "%PARENT%\EMStudio" (
    echo     not here - skipped
) else if exist "%PARENT%\EMStudio\em.bat" (
    if "!DRY!"=="1" ( echo     would run: em.bat sync ^& npm run check:datamodel ) else (
        pushd "%PARENT%\EMStudio" & call em.bat sync "%ROOT%." & pushd frontend & call npm run check:datamodel & popd & git status --short & popd )
) else (
    echo     NO em.bat in EMStudio ^(measured 2026-10-01: em.sh only; its sync is
    echo     frontend/scripts/sync-datamodels.sh, bash^). In Git Bash:
    echo       cd ../EMStudio ^&^& ./em.sh sync ../s3Dgraphy ^&^& ^(cd frontend ^&^& npm run check:datamodel^)
)
echo.
echo 4/4 EM-blender-tools - printed, not run ^(it rebuilds the wheels it ships^):
echo     EM-blender-tools\em.bat has NO rebundle ^(measured 2026-10-01: em.sh only^). Either
echo       Git Bash:  cd ../EM-blender-tools ^&^& ./em.sh rebundle
echo       or:        cd ..\EM-blender-tools ^&^& python scripts\rebundle_s3dgraphy.py
echo     then em.bat manifest 3.11 / 3.13 if the wheel's file name changed
echo.
echo Nothing was committed. Pins to move by hand: EMStudio tools\requirements.txt
echo ^(./em.sh s3d pin !V!^), StratiGraph Server ^(./bump-s3dgraphy.sh !V!^).
echo Both are bash scripts: in Git Bash, ./em.sh propagate --pins moves them ^(no commit^).
if "!DRY!"=="1" echo --dry-run: nothing done
exit /b 0

:: ----------------------------------------------------------------------------
:via_bash
where bash >nul 2>&1
if errorlevel 1 (
    echo [ERROR] '%CMD%' runs bash scripts ^(bump_and_push.sh --set, verifica-provenance.sh^).
    echo Install Git for Windows, then: bash em.sh %*
    exit /b 1
)
bash "%ROOT%em.sh" %*
exit /b %errorlevel%
