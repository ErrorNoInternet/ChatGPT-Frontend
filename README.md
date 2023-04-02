# ChatGPT-Frontend
A very simple HTML + CSS frontend for ChatGPT, powered by [ChatGPTAPIFree](https://github.com/ayaka14732/ChatGPTAPIFree)!\
Designed to work on Kindles (and other old browsers) without any JavaScript.

![ChatGPT-Frontend](/screenshot.png)

## Running
### Environment variables
- `PASSWORD`
  - Used to prevent other people from accessing the frontend
- `OPENAI_API_KEY`
  - Your own API key if you don't want to use the free API
- `OPENAI_API_PROXY`
  - Supply a custom API endpoint if the official API is blocked
- `HOST`
- `PORT`

After starting the web server, you can visit it at `http://localhost:8080`.\
Then, navigate to `/<PASSWORD>/<CONVERSATION>` to enter your messages.\
`CONVERSATION` can be anything you want, its purpose is to separate conversations.
