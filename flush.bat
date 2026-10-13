@echo off
setlocal

echo Cleaning Python cache folders...

for %%D in (
    __pycache__
    .pytest_cache
    .mypy_cache
    .ruff_cache
    .pytype
    .hypothesis
) do (
    for /d /r %%F in (%%D) do (
        if exist "%%F" (
            echo Removing: %%F
            rd /s /q "%%F"
        )
    )
)

echo.
echo Cache cleanup complete.
endlocal
pause