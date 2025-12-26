export CI_TEST_LOGIN_SECRET="BzH6kP8qN2vMxLrT9wYcF1jGd7sAeK3pZ0oIuJ5nX4yQtCbVhRlUmOaSfWDiEg"
export ENV=ci

TOKEN=$(
  curl -fsS -X POST http://127.0.0.1:8001/__test__/login \
    -H 'Content-Type: application/json' \
    -d "{\"secret\":\"$CI_TEST_LOGIN_SECRET\"}" \
  | python -c "import sys,json; print(json.load(sys.stdin)['token'])"
)

export API_TOKEN="$TOKEN"
schemathesis run http://127.0.0.1:8001/openapi.json

