# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import json

from flask import Flask

HEALTH_OK = "OK"

app = Flask(__name__)


@app.route("/")
def get_health() -> str:
    # import time
    # time.sleep(6)
    return json.dumps({"status": HEALTH_OK})


if __name__ == "__main__":
    app.run()
