#!/bin/zsh
# Makes today's puzzle. Run every morning by launchd (scripts/com.hopetoday.daily.plist).
#   scripts/run_daily.sh          the real run: saves the day in history.json
#   DRY=1 scripts/run_daily.sh    test run: builds the puzzle but records nothing
cd "${0:A:h}/.." || exit 1
mkdir -p daily/logs
log="daily/logs/$(date +%F).log"
flags=(--save --blind)              # --blind: the log never spoils the answer
[[ -n "$DRY" ]] && flags=(--blind)

{
  echo "=== $(date '+%F %T') daily run ${DRY:+(dry)}"
  .venv/bin/python harness/daily.py "${flags[@]}"
} >> "$log" 2>&1
code=$?

if [[ $code -eq 0 ]]; then
  ln -sfn "$(date +%F)" daily/latest          # daily/latest/index.html is always today's puzzle
  osascript -e 'display notification "Today'"'"'s puzzle is ready." with title "Hope Today"'
else
  osascript -e "display notification \"Daily run failed. See $log\" with title \"Hope Today\""
fi
exit $code
