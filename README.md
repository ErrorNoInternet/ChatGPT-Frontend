# ChatGPT-Frontend
A very simple HTML + CSS frontend for ChatGPT, powered by [ChatGPTAPIFree](https://github.com/ayaka14732/ChatGPTAPIFree)!\
Designed to work on Kindles (and other old browsers) without any JavaScript.

![ChatGPT-Frontend](/screenshot.png)

## Running
### Environment variables
- `PASSWORD`
  - Used to prevent other people from accessing the frontend
- `OPENAI_API_KEY`
  - Use your own API key if you don't want to use the free API
- `OPENAI_API_ENDPOINT`
  - Supply a custom API endpoint if the official API is inaccessible
- `HOST`
- `PORT`

```sh
git clone https://github.com/ErrorNoInternet/ChatGPT-Frontend
cd ChatGPT-Frontend
pip install -r requirements.txt
PASSWORD=HelloWorld1234 python3 main.py

# firefox http://localhost:8080/HelloWorld1234/Conversation0
```
