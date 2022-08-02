import boto3
import os
import re

from botocore.exceptions import ClientError
from flask import Flask, request, jsonify


FROM_EMAIL = os.environ["FROM_EMAIL"]
DESTINATION_EMAIL = os.environ["DESTINATION_EMAIL"]


app = Flask(__name__)
app.debug = False

ses = boto3.client("ses")


REQUIRED_FIELDS = ["name", "email", "message"]
EMAIL_REGEXP = r"(^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$)"


@app.after_request
def after_request(response):
    response.headers.add("Access-Control-Allow-Origin", "*")
    response.headers.add("Access-Control-Allow-Headers", "Content-Type,Authorization")
    response.headers.add("Access-Control-Allow-Methods", "OPTIONS,POST")
    return response


class InvalidUsage(Exception):
    pass


@app.errorhandler(400)
def handle_bad_request(error):
    return jsonify({"status": "error", "error": str(error)}), 400


@app.errorhandler(InvalidUsage)
def handle_invalid_usage(error):
    response = jsonify({"status": "error", "error": str(error)})
    response.status_code = 400
    return response


@app.errorhandler(ClientError)
def handle_client_error(error):
    response = jsonify({"status": "error", "error": str(error)})
    response.status_code = 500
    return response


@app.route("/", methods=["POST"])
def index():
    data = request.get_json(force=True)
    if not data:
        raise InvalidUsage("Request body cannot be empty.")

    for field in REQUIRED_FIELDS:
        value = data.get(field, None)
        if value is None:
            raise InvalidUsage(f'Request body needs a "{field}" field.')
        if not value.strip():
            raise InvalidUsage(f'The "{field}" field cannot be empty or spaces.')

    if not re.match(EMAIL_REGEXP, data["email"]):
        raise InvalidUsage('The "email" field needs to be a valid email address.')

    if "_important" in data:
        # Our code should have removed this field before POSTing.
        # This is probably triggered by a bot.
        return (jsonify({"status": "ok"}), 200)

    # Create a string with those fields that we do not recognize
    other_fields = set(data.keys()) - set(REQUIRED_FIELDS)
    str_other_fields = "\n".join(
        f"<strong>{field}</strong>: {data[field]}<br>"
        for field in sorted(other_fields)
    )


    subject = (
        f'Tryolabs contact form message from {data["name"]} ({data["email"]})'
    )

    message = """<strong>name</strong>: {}<br>
<strong>email</strong>: {}<br>
{}
<p>
{}
</p>
""".format(
        data["name"],
        data["email"],
        str_other_fields,
        data["message"].replace("\n", "<br>"),
    )

    response = ses.send_email(
        Source=FROM_EMAIL,
        Destination={
            "ToAddresses": [DESTINATION_EMAIL],
        },
        Message={
            "Subject": {"Data": subject, "Charset": "utf-8"},
            "Body": {"Html": {"Data": message, "Charset": "utf-8"}},
        },
        ReplyToAddresses=[data["email"]],
        ReturnPath=FROM_EMAIL,
    )

    if response["ResponseMetadata"]["HTTPStatusCode"] != 200:
        return (
            jsonify(
                {
                    "status": "error",
                    "error": f'SES responded with {response["ResponseMetadata"]["HTTPStatusCode"]}',
                }
            ),
            500,
        )


    return jsonify({"status": "ok"}), 200
