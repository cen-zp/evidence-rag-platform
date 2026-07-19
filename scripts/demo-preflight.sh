#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_dir="$(cd -- "${script_dir}/.." && pwd)"
python_bin="${project_dir}/apps/api/.venv/bin/python"

cd "${project_dir}"

if [[ ! -x "${python_bin}" ]]; then
  echo "Missing ${python_bin}. Install the locked API dependencies before recording." >&2
  exit 1
fi

running_services="$(docker compose ps --services --filter status=running)"
for service in postgres redis qdrant api worker web; do
  if ! grep -qx "${service}" <<<"${running_services}"; then
    echo "Service is not running: ${service}" >&2
    exit 1
  fi
done

curl --fail --silent --show-error --max-time 5 --output /dev/null http://127.0.0.1:8000/health
curl --fail --silent --show-error --max-time 5 --output /dev/null http://127.0.0.1:3000/
curl --fail --silent --show-error --max-time 5 --output /dev/null http://127.0.0.1:3000/evaluation
curl --fail --silent --show-error --max-time 5 --output /dev/null http://127.0.0.1:3000/review

"${python_bin}" -c '
import json
from urllib.request import urlopen

expected_batch_id = "02dbf511-6853-4dac-b420-779d74befa9c"
expected_report_sha256 = "0050e4ed89e394a278a955da240d6545a24419286fe777e96cd2f5542db55fef"
with urlopen("http://127.0.0.1:3000/api/formal-answer-review", timeout=5) as response:
    payload = json.load(response)
assert payload["batch"]["id"] == expected_batch_id
assert payload["batch"]["reportSha256"] == expected_report_sha256
assert len(payload["cases"]) == 72
print("fixed_review_batch=ok cases=72")
'

(
  cd "${project_dir}/apps/api"
  "${python_bin}" -m app.evaluation.answer_review \
    --report ../../evals/results/fastapi-official-formal-answer-batch.json \
    --review ../../evals/independent/fastapi-official-formal-answer-review-human.csv \
    > /dev/null
)
echo "committed_human_review=valid"

test -s "${project_dir}/demo-assets/mvp-acceptance-handbook.md"
echo "upload_asset=ok demo-assets/mvp-acceptance-handbook.md"
test -s "${project_dir}/demo-assets/privacy-account-overlay.svg"
echo "privacy_overlay=ok demo-assets/privacy-account-overlay.svg"
"${script_dir}/demo-model-call-snapshot.sh"
echo "preflight=ok no_model_endpoint_called"
