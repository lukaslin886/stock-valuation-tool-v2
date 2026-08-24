@ECHO OFF

set SPHINXBUILD=sphinx-build
set SOURCEDIR=source
set BUILDDIR=_build

if "%1"=="" goto help

%SPHINXBUILD% -b %1% %SOURCEDIR% %BUILDDIR%\%1%
goto end

:help
echo Usage: make.bat [builder]
echo Example: make.bat html

:end
