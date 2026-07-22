import json
import os

import requests


def main() -> None:
    wp = "https://chasingdings.com/wp-json/wp/v2/posts"
    auth = (os.getenv("WP_USER"), os.getenv("WP_APP_PASSWORD"))
    print(auth)
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "application/json",
        "User-Agent": "DailyBlogrollBot/1.0 (+https://chasingdings.com)",
    }
    payload = {"title": "API test", "status": "draft", "content": "Hello from the API."}

    response = requests.post(wp, auth=auth, headers=headers, data=json.dumps(payload))
    print(response.status_code, response.text)
    response.raise_for_status()


if __name__ == "__main__":
    main()
