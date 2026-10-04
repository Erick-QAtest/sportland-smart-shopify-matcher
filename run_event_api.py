from smart_events.api import create_app

app = create_app()

if __name__ == "__main__":
    import os
    import uvicorn
    uvicorn.run(app, host=os.getenv("EVENT_CAPTURE_HOST", "0.0.0.0"), port=int(os.getenv("EVENT_CAPTURE_PORT", "8787")))
