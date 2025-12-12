import hmac
import hashlib
from urllib.parse import parse_qsl

BOT_TOKEN = "8002298411:AAFCzEulvP93YtUUd9eLfKJdi4DtM02wHV8"

INIT_DATA = (
    "user=%7B%22id%22%3A367184933%2C%22first_name%22%3A%22Gleb%22%2C%22last_name%22%3A%22%22%2C"
    "%22username%22%3A%22Gribson_Micro%22%2C%22language_code%22%3A%22ru%22%2C%22allows_write_to_pm%22"
    "%3Atrue%2C%22photo_url%22%3A%22https%3A%5C%2F%5C%2Ft.me%5C%2Fi%5C%2Fuserpic%5C%2F320%5C%2F"
    "E6AV3Anf7jApEFXj5LBMdt5ZUwGmLISkIE3r1ya7DKI.svg%22%7D"
    "&chat_instance=-8007712947264016079"
    "&chat_type=sender"
    "&auth_date=1763737490"
    "&signature=Ka4CvTXC8CiDba95UAvPwDWTyNXWKxtgHgDRxGE1fnXtazURsbraHAT7Yhovm7oPWbOetkO87KFeNLY9DyHdBA"
    "&hash=a480525e960ec05d1fc01039bbe8858e12e25f9a33b5f183330fb40467f3458c"
)

def check(init_data: str, token: str) -> None:
    data = dict(parse_qsl(init_data, keep_blank_values=True))
    given_hash = data.pop("hash", None)
    print("given hash:", given_hash)

    # как в доке Mini Apps: исключаем hash, сортируем пары
    items = [f"{k}={v}" for k, v in sorted(data.items())]
    data_check_string = "\n".join(items)
    print("data_check_string:\n", data_check_string)

    # шаг 1: HMAC_SHA256("WebAppData", bot_token)
    secret_key = hmac.new(
        b"WebAppData",
        token.encode(),
        hashlib.sha256,
    ).digest()

    # шаг 2: HMAC_SHA256(secret_key, data_check_string)
    expected = hmac.new(
        secret_key,
        data_check_string.encode(),
        hashlib.sha256,
    ).hexdigest()

    print("expected :", expected)
    print("equal    :", expected == given_hash)

if __name__ == "__main__":
    check(INIT_DATA, BOT_TOKEN)

