"""Run the application locally with python -m whatsapp_ai_agent."""

def main() -> None:
    import uvicorn
    uvicorn.run("whatsapp_ai_agent.api:app", host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
