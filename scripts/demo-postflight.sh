#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -ne 2 ]]; then
  echo "Usage: $0 /absolute/path/demo.mp4 /tmp/evidence-rag-model-calls.before" >&2
  exit 2
fi

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
video_path="$1"
baseline_path="$2"

if [[ ! -s "${video_path}" ]]; then
  echo "Video is missing or empty: ${video_path}" >&2
  exit 1
fi
if [[ "${video_path##*.}" != "mp4" ]]; then
  echo "Expected an .mp4 recording: ${video_path}" >&2
  exit 1
fi
if [[ ! -s "${baseline_path}" ]]; then
  echo "Model-call baseline is missing or empty: ${baseline_path}" >&2
  exit 1
fi

before_snapshot="$(<"${baseline_path}")"
after_snapshot="$("${script_dir}/demo-model-call-snapshot.sh")"
if [[ "${before_snapshot}" != "${after_snapshot}" ]]; then
  echo "Model-call snapshot changed during recording." >&2
  echo "Before:" >&2
  echo "${before_snapshot}" >&2
  echo "After:" >&2
  echo "${after_snapshot}" >&2
  exit 1
fi

if command -v ffprobe >/dev/null 2>&1; then
  duration_seconds="$(ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "${video_path}")"
  if ! awk -v duration="${duration_seconds}" 'BEGIN { exit !(duration >= 180 && duration <= 300) }'; then
    echo "Video duration must be 180-300 seconds; got ${duration_seconds}." >&2
    exit 1
  fi
  echo "duration_seconds=${duration_seconds}"
elif command -v mdls >/dev/null 2>&1; then
  duration_seconds="$(mdls -raw -name kMDItemDurationSeconds "${video_path}" 2>/dev/null || true)"
  if [[ "${duration_seconds}" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
    if ! awk -v duration="${duration_seconds}" 'BEGIN { exit !(duration >= 180 && duration <= 300) }'; then
      echo "Video duration must be 180-300 seconds; got ${duration_seconds}." >&2
      exit 1
    fi
    echo "duration_seconds=${duration_seconds}"
  else
    echo "duration_check=manual metadata_unavailable"
  fi
else
  echo "duration_check=manual ffprobe_not_found"
fi

echo "successful_model_call_snapshot=unchanged"
shasum -a 256 "${video_path}"
echo "postflight=automated_checks_passed"
echo "manual_check=watch_once_for_audio_readability_and_sensitive_data"
