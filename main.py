import os
import copy
import time
import flask
import tiktoken
import requests
import threading
import ipaddress

make_request = lambda json: requests.post("https://chatgpt-api.shn.hk/v1", json=json)
if os.getenv("OPENAI_API_KEY"):
    print("Using specified OpenAI API key!")
    url = "https://api.openai.com/v1/chat/completions"
    if os.getenv("OPENAI_API_ENDPOINT"):
        print("Using OpenAI API proxy!")
        url = os.getenv("OPENAI_API_ENDPOINT")
    make_request = lambda json: requests.post(
        url,
        headers={"Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}"},
        json=json
    )

api_ratelimit_retry_count = 10
api_ratelimit_retry_wait = 3
default_host = "0.0.0.0"
default_port = 8080
conversation_dormant_time = 43200
endpoint_ratelimits = {"general": 0.5, "debug": 1, "api": 5}

conversations = {}
conversations_lock = threading.Lock()

app = flask.Flask(__name__)
ratelimits = {}
ratelimits_lock = threading.Lock()
if not os.getenv("PASSWORD"):
    print("No PASSWORD environment variable found!")
    exit()
default_html = "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">"
default_response = default_html + "<h2>Hello, world!</h2>"

def count_tokens(model, text):
    try:
        return len(tiktoken.encoding_for_model(model).encode(text))
    except Exception as error:
        print(f"Error counting tokens: {error}")
    return 0

def html_formatted(content):
    return content.strip()

def clean_up():
    while True:
        time.sleep(300)

        conversations_lock.acquire()
        for conversation in conversations.copy():
            if time.time() - conversations[conversation]["last_updated"] > conversation_dormant_time:
                print(f"Clearing dormant conversation {conversation}...")
                del conversations[conversation]
        conversations_lock.release()

        conversations_lock.acquire()
        for conversation in conversations.copy():
            while len(conversations[conversation]["messages"]) > 500:
                conversations[conversation]["messages"].pop(0)
        conversations_lock.release()

@app.before_request
def request_handler():
    request_ip = flask.request.remote_addr
    if ipaddress.IPv4Address(request_ip).is_private:
        proxy_ip = flask.request.headers.get("X-Forwarded-For")
        if proxy_ip:
            request_ip = proxy_ip

    endpoint = "general"
    request_path = flask.request.path.replace("/", "").replace(" ", "")
    if request_path.endswith("message"):
        endpoint = "api"
    elif request_path.endswith("debug"):
        endpoint = "debug"
    request_fingerprint = request_ip + endpoint

    ratelimits_lock.acquire()
    if request_fingerprint not in ratelimits:
        ratelimits[request_fingerprint] = 0
    if time.time() - ratelimits[request_fingerprint] < endpoint_ratelimits[endpoint]:
        ratelimits_lock.release()
        return default_html + "<p><b>Slow down!</b> You're sending too many requests!</p>"
    ratelimits[request_fingerprint] = time.time()
    ratelimits_lock.release()

@app.route("/")
def index():
    return default_response

@app.route("/<password>/<conversation>")
def display_messages(password, conversation):
    if password != os.getenv("PASSWORD"):
        return default_response

    response = default_html + """<title>ChatGPT</title>

<style>
    textarea {{ vertical-align: top; }}
    h3 {{ margin-bottom: 5px; }}
    pre {{ white-space: pre-wrap; word-wrap: break-word; margin-top: 0px; }}
    .inline-element {{ display: inline-block; }}
    .top-element {{ margin-bottom: 1px; }}
</style>

<body>
    <form method="POST" action="/{password}/{conversation}/message">
        <label for="content">Message
            <textarea rows="4" cols="25" name="content" id="content"></textarea>
            <button type="submit">Send</button>
        </label>
        <br>

        <label for="role">Role</label>
        <select name="role" id="role">
            <option value="user">User</option>
            <option value="system">System</option>
            <option value="assistant">ChatGPT</option>
        </select>
        <input type="checkbox" name="expect-response" id="expect-response" checked>Expect Response</input>
        <br>

        <label for="model">Model</label>
        <select name="model" id="model">
            <option value="gpt-3.5-turbo">GPT-3.5 Turbo</option>
            <option value="gpt-3.5-turbo-0301">GPT-3.5 Turbo (March 2023)</option>
        </select>
        <br>

        <label for="temperature">Temperature</label>
        <input type="range" style="width: 250px;" min="0" max="2" step="0.1" name="temperature" id="temperature">
    </form>

    <form class="inline-element top-element" action="/{password}/{conversation}/pop/top/1"><button type="submit">Pop (up)</button></form>
    <form class="inline-element top-element" action="/{password}/{conversation}/pop/bottom/1"><button type="submit">Pop (down)</button></form>
    <form class="inline-element top-element" action="/{password}/{conversation}/pop/top/5"><button type="submit">Pop x5 (up)</button></form>
    <form class="inline-element top-element" action="/{password}/{conversation}/pop/bottom/5"><button type="submit">Pop x5 (down)</button></form>
    <br>

    <form class="inline-element" action="/{password}/{conversation}/confirm-clear"><button type="submit">Reset Conversation</button></form>
    <form class="inline-element" action="/{password}/{conversation}/debug"><button type="submit">Debug Information</button></form>
    <hr>
""".format(password=password, conversation=conversation)

    if conversation in conversations:
        for message in reversed(conversations[conversation]["messages"]):
            if message["role"] == "user":
                response += f"\n    <h3><b>User:</b></h3><pre>{html_formatted(message['content'])}</pre>"
            elif message["role"] == "system":
                response += f"\n    <h3><b>System:</b></h3><pre>{html_formatted(message['content'])}</pre>"
            elif message["role"] == "assistant":
                response += f"\n    <h3><b>ChatGPT:</b></h3><pre>{html_formatted(message['content'])}</pre>"
            elif message["role"] == "error":
                response += f"\n    <h3><b>OpenAI (error):</b></h3><pre>{html_formatted(message['content'])}</pre>"

    return response + "\n</body>"

@app.route("/<password>/<conversation>/pop/<location>/<count>")
def pop_message(password, conversation, location, count):
    time.sleep(0.5)
    if password != os.getenv("PASSWORD"):
        return default_response

    if location not in ["top", "bottom"]:
        return flask.redirect(f"/{password}/{conversation}")
    try:
        count = int(count)
        if count > 50:
            count = 50
    except:
        return flask.redirect(f"/{password}/{conversation}")

    conversations_lock.acquire()
    for _ in range(count):
        try:
            if location == "top":
                conversations[conversation]["messages"].pop()
            else:
                conversations[conversation]["messages"].pop(0)
        except:
            pass
    conversations_lock.release()

    try:
        messages = conversations[conversation]["messages"]
        if len(messages) == 0:
            conversations_lock.acquire()
            conversations[conversation]["last_token_count"] = 0
            conversations[conversation]["token_count"] = 0
            conversations_lock.release()
            return flask.redirect(f"/{password}/{conversation}")

        last_tokens = count_tokens(
            conversations[conversation]["last_model"],
            list(reversed(messages))[0]["content"]
        )

        messages = ""
        for message in conversations[conversation]["messages"]:
            messages += message["content"]
        tokens = count_tokens(conversations[conversation]["last_model"], messages)

        conversations_lock.acquire()
        conversations[conversation]["last_token_count"] = last_tokens
        conversations[conversation]["token_count"] = tokens
        conversations_lock.release()
    except:
        pass

    return flask.redirect(f"/{password}/{conversation}")

@app.route("/<password>/<conversation>/confirm-clear")
def confirm_clear_messages(password, conversation):
    time.sleep(0.5)
    if password != os.getenv("PASSWORD"):
        return default_response

    return default_html + """<title>Reset Conversation</title>

<body>
    <form action="/{password}/{conversation}"><button type="submit">Back</button></form>

    <p style="margin-bottom: 0px;">Are you sure you want to reset this conversation?</p>
    <form style="display: inline-block;" action="/{password}/{conversation}"><button type="submit">No, I am not sure</button></form>
    <form style="display: inline-block;" action="/{password}/{conversation}/clear"><button type="submit">Yes, I am sure</button></form>
</body>""".format(password=password, conversation=conversation)

@app.route("/<password>/<conversation>/clear")
def clear_messages(password, conversation):
    time.sleep(0.5)
    if password != os.getenv("PASSWORD"):
        return default_response

    conversations_lock.acquire()
    try:
        del conversations[conversation]
    except:
        pass
    conversations_lock.release()

    return flask.redirect(f"/{password}/{conversation}")

@app.route("/<password>/<conversation>/debug")
def display_debug_information(password, conversation):
    if password != os.getenv("PASSWORD"):
        return default_response

    try:
        response = default_html + """<title>Debug Information</title>

<body>
    <form style="display: inline-block;" action="/{}/{}"><button type="submit">Back</button></form>

    <p>
        <b>Total Messages:</b> {}
        <br>
        <b>Total User Messages:</b> {}
        <br>
        <b>Total System Messages:</b> {}
        <br>
        <b>Total ChatGPT Messages:</b> {}
        <br>
        <b>Total Error Messages:</b> {}
        <br>
        <b>Total Token Count:</b> {}
        <br>
        <b>Last Message Token Count:</b> {}
        <br>
        <b>Last Used Model:</b> {}</b>
        <br>
        <b>Last API Request Attempts:</b> {}
        <br>
        <b>Last API Request JSON:</b> {}
        <br>
        <b>Last API Response:</b> {}
        <br>
        <b>Last Updated:</b> {}
        <br>
        <b>Conversation Data Size:</b> {:,} bytes
        <br>
        <b>Conversation Data:</b> {}
    </p>
</body>""".format(
            password,
            conversation,
            len(conversations[conversation]["messages"]),
            len(list(filter(lambda message: message["role"] == "user", conversations[conversation]["messages"]))),
            len(list(filter(lambda message: message["role"] == "system", conversations[conversation]["messages"]))),
            len(list(filter(lambda message: message["role"] == "assistant", conversations[conversation]["messages"]))),
            len(list(filter(lambda message: message["role"] == "error", conversations[conversation]["messages"]))),
            conversations[conversation]["token_count"],
            conversations[conversation]["last_token_count"],
            conversations[conversation]["last_model"],
            conversations[conversation]["last_api_request_attempts"],
            conversations[conversation]["last_api_request"],
            conversations[conversation]["last_api_response"],
            conversations[conversation]["last_updated"],
            len(str(conversations[conversation])),
            str(conversations[conversation]).encode()
        )
    except:
        response = default_html + """<title>Debug Information</title>

<body>
    <form action="/{password}/{conversation}"><button type="submit">Back</button></form>

    <p>No debug information found!</p>
</body>""".format(password=password, conversation=conversation)

    return response

@app.route("/<password>/<conversation>/message", methods=["POST"])
def handle_message(password, conversation):
    time.sleep(0.5)
    if password != os.getenv("PASSWORD"):
        return default_response

    try:
        temperature = float(flask.request.form.get("temperature"))
        if temperature < 0.0 or temperature > 2.0:
            return flask.redirect(f"/{password}/{conversation}")
    except:
        return flask.redirect(f"/{password}/{conversation}")
    model = flask.request.form.get("model").strip()
    user_input = flask.request.form.get("content").strip()
    if len(user_input) > 20000:
        return flask.redirect(f"/{password}/{conversation}")

    conversations_lock.acquire()
    if conversation not in conversations:
        conversations[conversation] = {
            "last_updated": time.time(),
            "last_model": model,
            "last_token_count": 0,
            "token_count": 0,
            "last_api_request_attempts": 0,
            "last_api_request": {},
            "last_api_response": b"",
            "messages": []
        }
    tokens = count_tokens(model, user_input)
    if len(user_input) > 0:
        conversations[conversation]["messages"].append({
            "role": flask.request.form.get("role").strip(),
            "content": user_input
        })
    conversations[conversation]["last_token_count"] = tokens
    conversations[conversation]["token_count"] += tokens
    conversations[conversation]["last_model"] = model
    conversations[conversation]["last_updated"] = time.time()
    conversations_lock.release()

    if not flask.request.form.get("expect-response"):
        return flask.redirect(f"/{password}/{conversation}")

    filtered_messages = copy.deepcopy(conversations[conversation]["messages"])
    for message in filtered_messages:
        if message["role"] == "error":
            filtered_messages.remove(message)

    success = False
    for i in range(api_ratelimit_retry_count):
        conversations_lock.acquire()
        conversations[conversation]["last_api_request_attempts"] = i + 1
        conversations_lock.release()
        if not success:
            try:
                print(f"Making API request for conversation {conversation} (attempt {i+1}/{api_ratelimit_retry_count})...")
                request_json = {
                    "model": model,
                    "temperature": temperature,
                    "messages": filtered_messages,
                }
                conversations_lock.acquire()
                conversations[conversation]["last_api_request"] = request_json
                conversations_lock.release()
                response = make_request(request_json)
                conversations_lock.acquire()
                conversations[conversation]["last_api_response"] = f"Status: {response.status_code}, Text: {response.text}"
                conversations_lock.release()
            except Exception as error:
                conversations_lock.acquire()
                conversations[conversation]["messages"].append({
                    "role": "error",
                    "content": f"Uh oh! A request error occured: {error}."
                })
                conversations_lock.release()
                print(f"Conversation {conversation} ran into a request error: {error}")
                return flask.redirect(f"/{password}/{conversation}")
            if response.status_code == 429:
                print(f"Conversation {conversation} is temporarily ratelimited! Waiting for {api_ratelimit_retry_wait} second(s)...")
                time.sleep(api_ratelimit_retry_wait)
                continue
            else:
                print(f"Successfully received API response for {conversation}!")
                success = True
                break

    try:
        json = response.json()
    except Exception as error:
        conversations_lock.acquire()
        conversations[conversation]["messages"].append({
            "role": "error",
            "content": f"Uh oh! A JSON error occured: {error}. Status: {response.status_code}, Text: {response.text}."
        })
        conversations_lock.release()
        print(f"Conversation {conversation} ran into a JSON error: {error}. Status: {response.status_code}, Text: {response.text}.")
        return flask.redirect(f"/{password}/{conversation}")

    try:
        message = json["choices"][0]["message"]
    except Exception as error:
        conversations_lock.acquire()
        conversations[conversation]["messages"].append({
            "role": "error",
            "content": f"Uh oh! A JSON error occured: {error}. Status: {response.status_code}, Text: {response.text}."
        })
        conversations_lock.release()
        print(f"Conversation {conversation} ran into a JSON error: {error}. Status: {response.status_code}, Text: {response.text}.")
        return flask.redirect(f"/{password}/{conversation}")
    tokens = count_tokens(model, message["content"])
    conversations_lock.acquire()
    conversations[conversation]["messages"].append(message)
    conversations[conversation]["last_token_count"] = tokens
    conversations[conversation]["token_count"] += tokens
    conversations[conversation]["last_updated"] = time.time()
    conversations_lock.release()

    return flask.redirect(f"/{password}/{conversation}")

if __name__ == "__main__":
    threading.Thread(target=clean_up).start()
    app.run(host=os.getenv("HOST") if os.getenv("HOST") else default_host, port=os.getenv("PORT") if os.getenv("PORT") else default_port)
