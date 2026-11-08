import json
import os
from typing import Any

import gradio as gr
import requests

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
BOT_API_KEY = os.getenv("BOT_API_KEY", "test-bot-key-12345")


def _call(method: str, path: str, token: str | None = None, json_body: dict | None = None, params: dict | None = None, bot: bool = False) -> tuple[str, int]:
    url = f"{API_BASE_URL}{path}"
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if bot or path.startswith("/api/bot") or path.endswith("/questions"):
        headers["X-Bot-Api-Key"] = BOT_API_KEY
    try:
        resp = requests.request(method, url, json=json_body, params=params, headers=headers, timeout=30)
        try:
            body = resp.json()
        except ValueError:
            body = {"raw": resp.text}
        return json.dumps(body, indent=2, ensure_ascii=False), resp.status_code
    except requests.RequestException as e:
        return json.dumps({"error": str(e)}, indent=2), 0


def health_check() -> tuple[str, int]:
    return _call("GET", "/")


def login(username: str, password: str) -> tuple[str, int]:
    return _call("POST", "/api/login", json_body={"username": username, "password": password})


def list_users(page: int, limit: int) -> tuple[str, int]:
    return _call("GET", "/api/users", params={"page": page, "limit": limit})


def create_user(fullname: str, telnumber: str, email: str, password: str, location: str, age: int) -> tuple[str, int]:
    body = {
        "fullname": fullname,
        "telnumber": telnumber,
        "email": email,
        "password": password,
    }
    if location:
        body["location"] = location
    if age:
        body["age"] = age
    return _call("POST", "/api/users", json_body=body)


def post_question(telnumber: str, question: str) -> tuple[str, int]:
    return _call("POST", f"/api/users/{telnumber}/questions", json_body={"question": question})


def get_questions(telnumber: str) -> tuple[str, int]:
    return _call("GET", f"/api/users/{telnumber}/questions")


def post_bot_exchange(telnumber: str, question: str, response: str, request_type: str) -> tuple[str, int]:
    body = {"telnumber": telnumber, "question": question}
    if response:
        body["response"] = response
    if request_type:
        body["request_type"] = request_type
    return _call("POST", "/api/bot/exchanges", json_body=body, bot=True)


def get_bot_history(telnumber: str, limit: int) -> tuple[str, int]:
    return _call("GET", f"/api/bot/users/{telnumber}/history", params={"limit": limit}, bot=True)


def search_bot_history(telnumber: str, q: str, top_k: int) -> tuple[str, int]:
    return _call("GET", f"/api/bot/users/{telnumber}/search", params={"q": q, "top_k": top_k}, bot=True)


def build_demo() -> gr.Blocks:
    with gr.Blocks(title="HLlama API Tester") as demo:
        gr.Markdown(
            f"# HLlama API Tester\n\nTarget: `{API_BASE_URL}`\n\n"
            "Enveloppe de réponse standard : `{status, error, message, data, meta}`"
        )

        with gr.Tab("Health"):
            health_btn = gr.Button("GET /")
            health_out = gr.Code(label="Réponse")
            health_btn.click(health_check, outputs=[health_out, gr.Textbox(visible=False)])

        with gr.Tab("Connexion"):
            login_username = gr.Textbox(label="Email")
            login_password = gr.Textbox(label="Mot de passe", type="password")
            login_btn = gr.Button("POST /api/login")
            login_out = gr.Code(label="Réponse")
            login_btn.click(login, inputs=[login_username, login_password], outputs=[login_out, gr.Textbox(visible=False)])

        with gr.Tab("Utilisateurs"):
            with gr.Accordion("Créer un utilisateur", open=False):
                u_fullname = gr.Textbox(label="Nom complet")
                u_telnumber = gr.Textbox(label="Numéro de téléphone")
                u_email = gr.Textbox(label="Email")
                u_password = gr.Textbox(label="Mot de passe", type="password")
                u_location = gr.Textbox(label="Localisation (optionnel)")
                u_age = gr.Number(label="Âge (optionnel)", precision=0)
                u_create_btn = gr.Button("POST /api/users")
                u_create_out = gr.Code(label="Réponse")
                u_create_btn.click(
                    create_user,
                    inputs=[u_fullname, u_telnumber, u_email, u_password, u_location, u_age],
                    outputs=[u_create_out, gr.Textbox(visible=False)],
                )

            with gr.Accordion("Lister les utilisateurs", open=True):
                u_page = gr.Number(label="Page", value=1, precision=0)
                u_limit = gr.Number(label="Limite", value=10, precision=0)
                u_list_btn = gr.Button("GET /api/users")
                u_list_out = gr.Code(label="Réponse")
                u_list_btn.click(list_users, inputs=[u_page, u_limit], outputs=[u_list_out, gr.Textbox(visible=False)])

        with gr.Tab("Questions"):
            q_telnumber = gr.Textbox(label="Numéro de téléphone de l'utilisateur")
            q_question = gr.Textbox(label="Question", lines=3)
            q_post_btn = gr.Button("POST /api/users/{telnumber}/questions")
            q_get_btn = gr.Button("GET /api/users/{telnumber}/questions")
            q_out = gr.Code(label="Réponse")
            q_post_btn.click(post_question, inputs=[q_telnumber, q_question], outputs=[q_out, gr.Textbox(visible=False)])
            q_get_btn.click(get_questions, inputs=[q_telnumber], outputs=[q_out, gr.Textbox(visible=False)])

        with gr.Tab("Mémoire bot (exchanges)"):
            b_telnumber = gr.Textbox(label="Numéro de téléphone (wa_id)")
            b_question = gr.Textbox(label="Question", lines=2)
            b_response = gr.Textbox(label="Réponse du bot", lines=2)
            b_request_type = gr.Textbox(label="request_type", value="question")
            b_push_btn = gr.Button("POST /api/bot/exchanges")
            b_history_btn = gr.Button("GET /api/bot/users/{tel}/history")
            b_search_btn = gr.Button("GET /api/bot/users/{tel}/search")
            b_limit = gr.Number(label="limit", value=8, precision=0)
            b_search_q = gr.Textbox(label="q (recherche sémantique)")
            b_top_k = gr.Number(label="top_k", value=3, precision=0)
            b_out = gr.Code(label="Réponse")
            b_push_btn.click(
                post_bot_exchange,
                inputs=[b_telnumber, b_question, b_response, b_request_type],
                outputs=[b_out, gr.Textbox(visible=False)],
            )
            b_history_btn.click(
                get_bot_history,
                inputs=[b_telnumber, b_limit],
                outputs=[b_out, gr.Textbox(visible=False)],
            )
            b_search_btn.click(
                search_bot_history,
                inputs=[b_telnumber, b_search_q, b_top_k],
                outputs=[b_out, gr.Textbox(visible=False)],
            )

    return demo


if __name__ == "__main__":
    build_demo().launch(server_name="0.0.0.0", server_port=int(os.getenv("GRADIO_PORT", "7860")), show_error=True)
