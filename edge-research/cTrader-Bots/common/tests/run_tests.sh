#!/bin/zsh
# cBot side checks without cTrader: assembled files current, firm configs, parity vectors from engine/rules.py, core unit tests,
# compile check of every assembled cBot. Usage: cTrader-Bots/common/tests/run_tests.sh   (exit 0 = all pass)
here="${0:A:h}"; common="${here:h}"; repo="${common:h:h}"
py="${PY:-$HOME/.venvs/fastbt/bin/python}"
tmp=$(mktemp -d "${TMPDIR:-/tmp}/er-cbot-tests.XXXXXX")
cal="$common/calendar/er-calendar-test.csv"
fail=0
echo "== assembled files"; python3 "$common/assemble.py" --check || fail=1
echo "== firm configs"; python3 "$common/firms/check_configs.py" || fail=1
echo "== parity vectors (engine/rules.py)"; (cd "$repo" && "$py" -I "$here/make_vectors.py" "$cal" "$tmp/vectors.json") || fail=1
echo "== core unit tests"
(cd "$here/ErCoreTests" && dotnet run -v q -p:BaseOutputPath="$tmp/bin/" -p:BaseIntermediateOutputPath="$tmp/obj/" \
   -p:MSBuildProjectExtensionsPath="$tmp/obj/" -- "$common" "$tmp/vectors.json" "$cal") || fail=1
echo "== compile check (cTrader's cAlgo.API.dll)"; "$common/compile/compile_check.sh" || fail=1
echo "temp: $tmp"
exit $fail
